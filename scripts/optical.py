"""Найти Sentinel-2 рядом с датами NISAR и сохранить индексы без скачивания сцен.

Запуск: python scripts/optical.py [--site amazon] [--window-days 15]
Проверки без сети: python scripts/optical.py --self-test
Зависимость: requests из scripts/requirements.txt. Earthdata не требуется.
"""
import argparse
from datetime import date, datetime, time, timedelta, timezone
import json
import math
from pathlib import Path
import tempfile
import unittest
from urllib.parse import urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

ROOT = Path(__file__).resolve().parents[1]
ENDPOINT = 'https://earth-search.aws.element84.com/v1'
COLLECTION = 'sentinel-2-l2a'
SITES = ('mexico', 'amazon', 'venezuela')


def bbox_values(site):
    bbox = site['grid']['bbox']
    result = [float(bbox[k]) for k in ('w', 's', 'e', 'n')]
    w, s, e, n = result
    if not all(math.isfinite(x) for x in result) or not (-180 <= w < e <= 180 and -90 <= s < n <= 90):
        raise ValueError('Некорректные границы участка')
    return result


def fetch_scenes(session, bbox, dates, window_days):
    """Прочитать все страницы каталога. Неполный ответ не считается отсутствием сцен."""
    start = min(dates) - timedelta(days=window_days)
    end = max(dates) + timedelta(days=window_days)
    params = {
        'collections': COLLECTION, 'bbox': ','.join(map(str, bbox)),
        'datetime': f'{start.isoformat()}T00:00:00Z/{end.isoformat()}T23:59:59.999999Z',
        'limit': 100,
    }
    query = requests.Request('GET', ENDPOINT + '/search', params=params).prepare().url
    url, seen, scenes = query, set(), {}
    for _ in range(100):
        if url in seen:
            raise ValueError('Каталог повторяет страницу; индекс не сохранён')
        seen.add(url)
        response = session.get(url, timeout=(10, 60))
        response.raise_for_status()
        page = response.json()
        if page.get('type') != 'FeatureCollection' or not isinstance(page.get('features'), list):
            raise ValueError('Некорректный ответ STAC')
        for item in page['features']:
            if item.get('collection') != COLLECTION or not item.get('id'):
                raise ValueError('Некорректная коллекция или ID сцены')
            scenes[item['id']] = item
        links = [link for link in page.get('links', []) if link.get('rel') == 'next']
        if not links:
            return list(scenes.values()), query, len(seen)
        if len(links) != 1 or links[0].get('method', 'GET') != 'GET':
            raise ValueError('Неподдерживаемая пагинация STAC')
        url = links[0]['href']
        target = urlparse(url)
        if target.scheme != 'https' or target.netloc != urlparse(ENDPOINT).netloc:
            raise ValueError('Ссылка следующей страницы ведёт вне каталога')
    raise ValueError('Превышен предел страниц; индекс не сохранён')


def scene_record(item, bbox):
    """Нормализовать доступную сцену. Облачность участка не подменяется облачностью тайла."""
    properties = item.get('properties', {})
    timestamp = properties.get('datetime')
    if not timestamp:
        return None
    acquired = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
    if acquired.tzinfo is None:
        return None
    acquired = acquired.astimezone(timezone.utc)
    cloud = properties.get('eo:cloud_cover')
    if isinstance(cloud, bool) or not isinstance(cloud, (int, float)) or not math.isfinite(cloud) or not 0 <= cloud <= 100:
        return None
    footprint = item.get('bbox', [])
    if len(footprint) != 4 or not all(isinstance(v, (int, float)) and math.isfinite(v) for v in footprint):
        return None
    w, s, e, n = bbox
    # Это проверка bbox, а не проверка наличия валидных пикселей внутри участка.
    if not (footprint[0] <= w and footprint[1] <= s and footprint[2] >= e and footprint[3] >= n):
        return None
    assets = item.get('assets', {})
    bands = {key: assets.get(key, {}).get('href') for key in ('red', 'green', 'blue')}
    if any(not isinstance(value, str) or not value.startswith('https://') for value in bands.values()):
        return None
    self_url = next((link['href'] for link in item.get('links', [])
                     if link.get('rel') == 'self' and link.get('href', '').startswith('https://')), None)
    return {
        'scene_id': item['id'], 'source': 'Copernicus Sentinel-2 L2A via Earth Search',
        'collection': COLLECTION, 'datetime': acquired.isoformat().replace('+00:00', 'Z'),
        'date': acquired.date().isoformat(), 'scene_cloud_cover_pct': float(cloud),
        'aoi_cloud_cover_pct': None, 'aoi_valid_fraction': None,
        'coverage_check': 'scene_bbox_contains_aoi; valid pixels not checked',
        'scene_bbox': footprint, 'stac_url': self_url, 'assets': bands,
        'scl_url': assets.get('scl', {}).get('href'),
        'epsg': properties.get('proj:epsg'),
    }


def build_index(site, items, query, pages, window_days=15):
    bbox = bbox_values(site)
    candidates = [record for item in items if (record := scene_record(item, bbox)) is not None]
    entries = []
    for nisar_date in site['dates']:
        reference = date.fromisoformat(nisar_date)
        eligible = [record for record in candidates
                    if abs((date.fromisoformat(record['date']) - reference).days) <= window_days]
        eligible.sort(key=lambda record: (
            record['scene_cloud_cover_pct'],
            abs((datetime.fromisoformat(record['datetime'].replace('Z', '+00:00')) -
                 datetime.combine(reference, time(), timezone.utc)).total_seconds()),
            record['scene_id'],
        ))
        chosen = eligible[0] if eligible else None
        entries.append({
            'nisar_date': nisar_date, 'status': 'selected' if chosen else 'unavailable',
            'candidate_count': len(eligible), 'scene': chosen,
            'delta_days': (date.fromisoformat(chosen['date']) - reference).days if chosen else None,
            'reason': None if chosen else 'Нет сцены с облачностью, RGB и bbox участка в заданном окне',
        })
    return {
        'schema_version': 1, 'site': site['id'], 'bbox': bbox,
        'created_at': datetime.now(timezone.utc).isoformat(),
        'catalogue': ENDPOINT, 'collection': COLLECTION, 'query': query, 'pages': pages,
        'window_days': window_days, 'catalogue_items': len(items),
        'eligible_items': len(candidates),
        'selection': 'Минимум eo:cloud_cover в пределах ±window_days календарных дней UTC; затем близость к дате NISAR и ID сцены',
        'limitations': [
            'Облачность сообщается по целому тайлу; облака, тени и валидность пикселей над участком не проверены',
            'Выбранная сцена может быть облачной; selected не означает чистый снимок или подтверждение радарной аномалии',
            'Проверено включение bbox участка в bbox сцены, а не полное покрытие валидными пикселями',
            'Изображения не скачаны и ещё не подключены к карте; текущая подложка Esri остаётся географическим контекстом',
        ],
        'summary': {
            'nisar_dates': len(entries), 'selected': sum(row['scene'] is not None for row in entries),
            'unavailable': sum(row['scene'] is None for row in entries),
            'selected_scene_cloud_le_20_pct': sum(
                row['scene'] is not None and row['scene']['scene_cloud_cover_pct'] <= 20 for row in entries),
        },
        'entries': entries,
    }


def save_index(index, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(index, ensure_ascii=False, allow_nan=False, indent=2) + '\n')
    temporary.replace(path)


class OpticalTests(unittest.TestCase):
    """Маленькие офлайн-фикстуры; не подменяют проверку живого каталога."""
    def setUp(self):
        self.site = {'id': 'test', 'grid': {'bbox': dict(w=1, s=2, e=3, n=4)}, 'dates': ['2026-07-20']}

    def item(self, scene_id='scene', day='2026-07-20', cloud=10):
        return dict(id=scene_id, collection=COLLECTION, bbox=[0, 1, 4, 5],
                    properties={'datetime': day + 'T12:00:00Z', 'eo:cloud_cover': cloud},
                    assets={key: {'href': f'https://example.test/{key}.tif'} for key in ('red', 'green', 'blue')})

    def index(self, items):
        return build_index(self.site, items, 'https://example.test/search', 1)

    def test_cloud_precedes_distance_and_ties_are_stable(self):
        items = [self.item('near', cloud=30), self.item('far', '2026-07-05', 5), self.item('tie', '2026-07-06', 5)]
        row = self.index(items)['entries'][0]
        self.assertEqual(row['scene']['scene_id'], 'tie')
        self.assertEqual(self.index(list(reversed(items)))['entries'], self.index(items)['entries'])

    def test_window_boundary_and_explicit_missing(self):
        row = self.index([self.item(day='2026-08-04')])['entries'][0]
        self.assertEqual(row['delta_days'], 15)
        row = self.index([self.item(day='2026-08-05')])['entries'][0]
        self.assertEqual(row['status'], 'unavailable')
        self.assertIsNone(row['scene'])

    def test_missing_cloud_rgb_or_incomplete_bbox_are_not_selected(self):
        a = self.item(cloud=None)
        b = self.item(); b['assets'].pop('red')
        c = self.item(); c['bbox'] = [0, 1, 2, 3]
        d = self.item(cloud=float('nan'))
        self.assertEqual(self.index([a, b, c, d])['summary']['selected'], 0)

    def test_cloudy_is_explicit_and_not_aoi_cloud(self):
        index = self.index([self.item(cloud=99)])
        self.assertEqual(index['summary']['selected_scene_cloud_le_20_pct'], 0)
        self.assertIsNone(index['entries'][0]['scene']['aoi_cloud_cover_pct'])

    def test_pagination_and_cycle_detection(self):
        outer = self
        class Response:
            def __init__(self, payload): self.payload = payload
            def raise_for_status(self): pass
            def json(self): return self.payload
        class Session:
            def __init__(self): self.calls = 0
            def get(self, url, timeout):
                self.calls += 1
                return Response(dict(type='FeatureCollection', features=[outer.item(str(self.calls))],
                                     links=[dict(rel='next', href=ENDPOINT + '/search?next=page2')] if self.calls == 1 else []))
        items, _, pages = fetch_scenes(Session(), [1, 2, 3, 4], [date(2026, 7, 20)], 15)
        self.assertEqual((len(items), pages), (2, 2))
        class Cycle:
            def get(self, url, timeout):
                return Response(dict(type='FeatureCollection', features=[], links=[dict(rel='next', href=url)]))
        with self.assertRaises(ValueError):
            fetch_scenes(Cycle(), [1, 2, 3, 4], [date(2026, 7, 20)], 15)

    def test_save_roundtrip(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'optical/index.json'
            index = self.index([])
            save_index(index, path)
            self.assertEqual(json.loads(path.read_text()), index)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--site', choices=['all', *SITES], default='all')
    parser.add_argument('--window-days', type=int, default=15)
    parser.add_argument('--self-test', action='store_true')
    args = parser.parse_args()
    if args.self_test:
        suite = unittest.defaultTestLoader.loadTestsFromTestCase(OpticalTests)
        result = unittest.TextTestRunner(verbosity=2).run(suite)
        raise SystemExit(0 if result.wasSuccessful() else 1)
    if not 0 <= args.window_days <= 30:
        parser.error('--window-days: допустимы значения от 0 до 30')
    session = requests.Session()
    session.mount('https://', HTTPAdapter(max_retries=Retry(total=3, backoff_factor=1, status_forcelist=[429, 502, 503, 504])))
    session.headers['User-Agent'] = 'OffBeat-optical/1.0'
    for name in SITES if args.site == 'all' else [args.site]:
        site = json.loads((ROOT / 'data' / f'{name}.json').read_text())
        if site['id'] != name or not site['dates']:
            raise ValueError('Неожиданный ID участка или пустой ряд дат')
        dates = [date.fromisoformat(value) for value in site['dates']]
        items, query, pages = fetch_scenes(session, bbox_values(site), dates, args.window_days)
        index = build_index(site, items, query, pages, args.window_days)
        save_index(index, ROOT / 'data' / name / 'optical/index.json')
        print(name, json.dumps(index['summary'], ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
