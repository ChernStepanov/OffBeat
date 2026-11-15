"""Retrospective local two-date checks around prepared Amazon radar candidates."""
import hashlib
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / 'data/change-candidates/amazon-6f219605b533.json'
OUT = ROOT / 'data/analysis/amazon-dense-polarizations-2026-11-15.json'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def summary(values):
    values = values[np.isfinite(values)]
    if not values.size:
        return {'count': 0, 'median_db': None, 'p10_db': None, 'p90_db': None}
    return {'count': int(values.size), 'median_db': round(float(np.median(values)), 3),
            'p10_db': round(float(np.quantile(values, .1)), 3),
            'p90_db': round(float(np.quantile(values, .9)), 3)}


def run():
    report = json.loads(REPORT.read_text(encoding='utf-8'))
    arrays = []
    for item in report['inputs']:
        path = ROOT / item['subset_path']
        if sha(path) != item['sha256']:
            raise ValueError('Radar subset hash mismatch')
        arrays.append(np.load(path))
    shape = tuple(report['grid']['shape'])
    channels = {}
    for name in ('hh', 'hv'):
        valid = np.ones(shape, dtype=bool)
        for a in arrays:
            valid &= (a['mask'] > 0) & (a['mask'] < 255) & np.isfinite(a[name]) & (a[name] > 0)
        delta = np.full(shape, np.nan, dtype=np.float64)
        delta[valid] = 10 * np.log10(arrays[1][name][valid] / arrays[0][name][valid])
        channels[name] = delta
    items = []
    for marker in report['markers']:
        row, col = marker['row'], marker['col']
        bounds = (max(0, row-15), min(shape[0], row+16), max(0, col-15), min(shape[1], col+16))
        r0, r1, c0, c1 = bounds
        entry = {k: marker[k] for k in ('id', 'row', 'col', 'lat', 'lon', 'score')}
        for name, delta in channels.items():
            cell = float(delta[row, col])
            near = delta[max(0,row-1):min(shape[0],row+2), max(0,col-1):min(shape[1],col+2)]
            local = delta[r0:r1, c0:c1].copy()
            local[max(0,row-1)-r0:min(shape[0],row+2)-r0,
                  max(0,col-1)-c0:min(shape[1],col+2)-c0] = np.nan
            entry[name] = {'cell_delta_db': round(cell, 3) if np.isfinite(cell) else None,
                           'near_3x3': summary(near), 'surrounding_31x31_excluding_3x3': summary(local)}
        entry['context_truncated_at_edge'] = r0 == 0 or c0 == 0 or r1 == shape[0] or c1 == shape[1]
        items.append(entry)
    result = {'schema_version': 1, 'kind': 'retrospective_exploratory_not_independent_validation',
              'source_report': REPORT.relative_to(ROOT).as_posix(), 'source_report_sha256': sha(REPORT),
              'dates': report['dates'], 'inputs': report['inputs'], 'grid_spacing_m': 20,
              'method': 'For HH and HV separately, require mask 1..254 and finite positive power in both scenes; compute 10 log10(later/earlier). For each previously selected marker report cell value, 3x3 median and percentiles, and 31x31 context excluding the 3x3. Clip windows to the available grid; no imputation.',
              'limitations': ['Retrospective checks are not independent event confirmation or a blind test.',
                              'The existing mask rule is not a complete quality assessment.',
                              'Spatial neighbours can share the same event, land cover, speckle and weather; they are not independent observations.',
                              'Two dates cannot establish cause, event area, longer-term trend, or detector accuracy.',
                              'Context is not restricted to the same land-cover class and can include edges of the same patch.'],
              'items': items}
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    print(OUT)
    for item in items:
        print(item['id'], 'HH', item['hh']['cell_delta_db'], 'HV', item['hv']['cell_delta_db'],
              '3x3', item['hh']['near_3x3']['median_db'], item['hv']['near_3x3']['median_db'])


if __name__ == '__main__':
    run()
