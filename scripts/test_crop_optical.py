"""Проверки ориентации, nodata, калибровки и общих шкал RGB-вырезок."""
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image
import pytest
import rasterio
from rasterio.transform import from_bounds

from crop_optical import read_band, to_rgba, calibration, RENDER_VERSION


def test_crop_keeps_north_up_bounds_and_nodata(tmp_path):
    path = tmp_path / 'band.tif'
    raw = np.arange(1, 101, dtype=np.uint16).reshape(10, 10)
    raw[2, 2] = 0
    with rasterio.open(path, 'w', driver='GTiff', count=1, dtype='uint16',
                       crs='EPSG:4326', transform=from_bounds(0, 0, 1, 1, 10, 10),
                       width=10, height=10, nodata=0) as target:
        target.write(raw, 1)
    band, receipt = read_band(str(path), [0.2, 0.2, 0.8, 0.8], 6, 6, 0.01, -0.1)
    expected = raw[2:8, 2:8].astype(float) * 0.01 - 0.1
    expected[0, 0] = np.nan
    np.testing.assert_allclose(band, expected, atol=1e-6, equal_nan=True)
    rgba, fraction = to_rgba([band] * 3)
    assert rgba[0, 0, 3] == 0 and rgba[-1, -1, 3] == 255
    assert fraction == pytest.approx(35 / 36)
    assert receipt['source_crs'] == 'EPSG:4326'


def test_stretch_is_fixed_between_scenes():
    a = np.array([[0.03, 0.1]], dtype=float)
    b = np.array([[0.03, 0.3]], dtype=float)
    first, _ = to_rgba([a] * 3)
    second, _ = to_rgba([b] * 3)
    np.testing.assert_array_equal(first[0, 0], second[0, 0])
    assert first[0, 0, 0] == round(255 * (0.03 / 0.3) ** (1 / 2.2))


def test_boa_offset_is_not_subtracted_twice():
    item = {'collection': 'sentinel-2-l2a', 'properties': {'earthsearch:boa_offset_applied': True}}
    asset = {'raster:bands': [{'scale': 0.0001, 'offset': -0.1}]}
    assert calibration(item, asset) == (0.0001, 0, -0.1, True)
    item['properties']['earthsearch:boa_offset_applied'] = False
    with pytest.raises(ValueError, match='BOA offset'):
        calibration(item, asset)


@pytest.mark.parametrize('name', ['mexico', 'amazon', 'venezuela'])
def test_saved_images_match_receipts_and_site_bounds(name):
    root = Path(__file__).resolve().parents[1]
    site = json.loads((root / 'data' / f'{name}.json').read_text())
    directory = root / 'data' / name / 'optical'
    index = json.loads((directory / 'index.json').read_text())
    expected = [site['grid']['bbox'][key] for key in ('w', 's', 'e', 'n')]
    assert index['summary']['rendered_dates'] == len(site['dates'])
    for row in index['entries']:
        assert row['crop_status'] == 'ready'
        render = row['scene']['render']
        assert render['version'] == RENDER_VERSION
        assert render['bbox'] == expected and render['crs'] == 'EPSG:4326'
        image_path = directory / render['file']
        content = image_path.read_bytes()
        assert len(content) == render['bytes'] <= 300_000
        assert hashlib.sha256(content).hexdigest() == render['sha256']
        with Image.open(image_path) as image:
            image.load()
            assert image.size == (render['width'], render['height'])
            alpha = np.array(image)[..., 3]
            assert (alpha > 0).mean() == pytest.approx(render['valid_fraction'])
        for band in render['bands'].values():
            assert band['window'][2] * band['window'][3] < 2_000_000
            assert band['offset'] == 0 and band['boa_offset_applied'] is True
