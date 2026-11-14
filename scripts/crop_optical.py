"""Вырезать RGB из удалённых COG и перепроецировать точно в bbox демо.

python scripts/crop_optical.py [--site amazon] [--refresh]
Шкала отражательной способности 0..0.3, gamma 2.2 одинакова для всех дат.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np
from PIL import Image
import rasterio
from rasterio.enums import Resampling
from rasterio.transform import from_bounds
from rasterio.warp import reproject, transform_bounds
from rasterio.windows import Window, from_bounds as window_from_bounds
import requests

from optical import ROOT, SITES, bbox_values, save_index

RENDER_VERSION = 2
STRETCH = {'reflectance_min': 0.0, 'reflectance_max': 0.3, 'gamma': 2.2}


def calibration(item, asset):
    band = asset.get('raster:bands', [{}])[0]
    scale, declared_offset = band.get('scale'), band.get('offset')
    if not all(isinstance(v, (int, float)) and math.isfinite(v) for v in (scale, declared_offset)) or scale <= 0:
        raise ValueError('Нет явной калибровки отражательной способности в STAC')
    applied = item.get('properties', {}).get('earthsearch:boa_offset_applied')
    # У legacy COG offset уже применён к DN, хотя raster:bands всё ещё содержит -0.1.
    # https://github.com/Element84/earth-search/discussions/26
    if item.get('collection') == 'sentinel-2-l2a':
        if applied is not True:
            raise ValueError('Неоднозначный BOA offset legacy-коллекции: нужна проверка источника')
        offset = 0.0
    else:
        offset = declared_offset
    return scale, offset, declared_offset, applied


def output_shape(bbox, longest=256):
    w, s, e, n = bbox
    ratio = (e - w) * math.cos(math.radians((s + n) / 2)) / (n - s)
    return (longest, max(1, round(longest / ratio))) if ratio >= 1 else (max(1, round(longest * ratio)), longest)


def read_band(href, bbox, width, height, scale, offset):
    """Читать только окно нативного растра; nodata остаётся прозрачным."""
    with rasterio.open(href) as source:
        bounds = transform_bounds('EPSG:4326', source.crs, *bbox, densify_pts=21)
        window = window_from_bounds(*bounds, transform=source.transform)
        left, top = math.floor(window.col_off) - 2, math.floor(window.row_off) - 2
        right, bottom = math.ceil(window.col_off + window.width) + 2, math.ceil(window.row_off + window.height) + 2
        window = Window(left, top, right-left, bottom-top).intersection(Window(0, 0, source.width, source.height))
        if window.width * window.height > 2_000_000:
            raise ValueError('Окно слишком большое для демо; целая сцена не читается')
        raw = source.read(1, window=window, masked=True).astype(np.float32)
        reflectance = raw.filled(np.nan) * scale + offset
        destination = np.full((height, width), np.nan, np.float32)
        reproject(reflectance, destination,
                  src_transform=source.window_transform(window), src_crs=source.crs,
                  src_nodata=np.nan, dst_transform=from_bounds(*bbox, width, height),
                  dst_crs='EPSG:4326', dst_nodata=np.nan, resampling=Resampling.bilinear)
        receipt = dict(url=href, source_crs=source.crs.to_string(),
                       window=[int(window.col_off), int(window.row_off), int(window.width), int(window.height)],
                       scale=scale, offset=offset)
        return destination, receipt


def to_rgba(channels):
    rgb = np.stack(channels, axis=-1)
    valid = np.isfinite(rgb).all(axis=-1)
    normalized = np.clip(np.nan_to_num(rgb, nan=0) / STRETCH['reflectance_max'], 0, 1)
    image = np.rint(255 * normalized ** (1 / STRETCH['gamma'])).astype(np.uint8)
    return np.dstack([image, valid.astype(np.uint8) * 255]), float(valid.mean())


def render_scene(scene, bbox, directory, session):
    response = session.get(scene['stac_url'], timeout=(10, 60))
    response.raise_for_status()
    item = response.json()
    if item['id'] != scene['scene_id']:
        raise ValueError('ID исходной STAC-сцены изменился')
    width, height = output_shape(bbox)
    channels, receipts = [], {}
    for key in ('red', 'green', 'blue'):
        asset = item['assets'][key]
        if asset['href'] != scene['assets'][key]:
            raise ValueError('URL исходного канала изменился')
        scale, offset, declared_offset, applied = calibration(item, asset)
        channel, receipt = read_band(asset['href'], bbox, width, height, scale, offset)
        receipt.update(declared_stac_offset=declared_offset, boa_offset_applied=applied)
        channels.append(channel); receipts[key] = receipt
    rgba, fraction = to_rgba(channels)
    if fraction == 0:
        raise ValueError('Нет валидных RGB-пикселей в участке')
    # Дата и ID различают сцены одного дня; имя не задаётся произвольным путём из STAC.
    name = f"{scene['date']}-{hashlib.sha256(scene['scene_id'].encode()).hexdigest()[:10]}.png"
    path = directory / name
    temporary = path.with_suffix('.tmp')
    Image.fromarray(rgba).save(temporary, format='PNG', optimize=True)
    if temporary.stat().st_size > 300_000:
        raise ValueError('PNG превышает 300 КБ')
    temporary.replace(path)
    return dict(version=RENDER_VERSION, file=name, bbox=bbox, crs='EPSG:4326',
                width=width, height=height, stretch=STRETCH, resampling='bilinear',
                valid_fraction=fraction, bytes=path.stat().st_size,
                sha256=hashlib.sha256(path.read_bytes()).hexdigest(), bands=receipts,
                stac_url=scene['stac_url'])


def valid_cache(render, scene, bbox, directory):
    if not render or render.get('version') != RENDER_VERSION or render.get('bbox') != bbox or render.get('stretch') != STRETCH:
        return False
    name = render.get('file', '')
    if not name or Path(name).name != name:
        return False
    path = directory / name
    return (path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == render.get('sha256')
            and all(render.get('bands', {}).get(k, {}).get('url') == scene['assets'][k] for k in ('red', 'green', 'blue')))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--site', choices=['all', *SITES], default='all')
    parser.add_argument('--refresh', action='store_true')
    args = parser.parse_args()
    session = requests.Session()
    failures = 0
    # GDAL читает диапазоны COG, не скачивает целый tif и не ищет побочные файлы.
    with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN='EMPTY_DIR', CPL_VSIL_CURL_ALLOWED_EXTENSIONS='.tif',
                      GDAL_HTTP_TIMEOUT='45', GDAL_HTTP_MAX_RETRY='2', GDAL_HTTP_RETRY_DELAY='1'):
        for name in SITES if args.site == 'all' else [args.site]:
            site = json.loads((ROOT / 'data' / f'{name}.json').read_text())
            directory = ROOT / 'data' / name / 'optical'
            index_path = directory / 'index.json'
            index = json.loads(index_path.read_text())
            bbox = bbox_values(site)
            if index['site'] != name or index['bbox'] != bbox:
                raise ValueError('Индекс не соответствует участку')
            processed = {}
            for entry in index['entries']:
                scene = entry.get('scene')
                if scene is None:
                    continue
                identity = scene['scene_id']
                if identity not in processed:
                    try:
                        cached = scene.get('render')
                        if not args.refresh and valid_cache(cached, scene, bbox, directory):
                            processed[identity] = cached
                        else:
                            processed[identity] = render_scene(scene, bbox, directory, session)
                        print(name, identity, processed[identity]['bytes'], 'bytes', flush=True)
                    except (requests.RequestException, rasterio.errors.RasterioError, ValueError, KeyError) as error:
                        processed[identity] = {'error': str(error)}
                        failures += 1
                        print(name, identity, 'FAILED:', error, flush=True)
                result = processed[identity]
                scene.pop('render', None)
                scene['aoi_valid_fraction'] = None
                entry['crop_status'] = 'failed' if 'error' in result else 'ready'
                entry['crop_error'] = result.get('error')
                if 'error' not in result:
                    scene['render'] = result
                    scene['aoi_valid_fraction'] = result['valid_fraction']
                    scene['coverage_check'] = 'RGB window reprojected into aoi; see render.valid_fraction; clouds not checked'
            index['rendering'] = dict(version=RENDER_VERSION, stretch=STRETCH,
                                      note='RGB B04/B03/B02, EPSG:4326, точный bbox; прозрачный nodata; облака не удалены')
            index['limitations'] = [note for note in index['limitations']
                                    if not note.startswith(('Изображения не скачаны', 'Облачность сообщается', 'Проверено включение bbox'))]
            if not any('RGB valid_fraction' in note for note in index['limitations']):
                index['limitations'].append('Облачность дана для тайла; облака и тени над участком не оценены. RGB valid_fraction показывает только наличие данных, не ясное небо.')
            if not any('BOA offset' in note for note in index['limitations']):
                index['limitations'].append('BOA offset legacy COG учтён по earthsearch:boa_offset_applied; противоречащий raster:bands offset повторно не вычитается. Независимая радиометрическая валидация не выполнена.')
            index['summary']['rendered_dates'] = sum(bool(row.get('scene', {}).get('render')) for row in index['entries'] if row.get('scene'))
            save_index(index, index_path)
    if failures:
        raise SystemExit(f'Не удалось вырезать {failures} сцен; ошибки записаны в индексах')


if __name__ == '__main__':
    main()
