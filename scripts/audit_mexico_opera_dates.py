"""Verify the saved Mexico OPERA sample and compare dates, not LOS values.

Quality masks have already been applied by the extraction script. This audit
cannot verify the remote mask or establish a stable reference or a velocity.
"""
import hashlib
import json
import math
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def read(path):
    return json.loads((ROOT / path).read_text(encoding='utf-8'))

def audit():
    site = read('data/mexico.json')
    opera = read('data/mexico/opera-disp.json')
    quality = read('data/analysis/mexico-gunw-postgap-quality.json')
    coords = [(p['lat'], p['lon']) for p in site['pixels']]
    digest = hashlib.sha256(json.dumps(coords).encode()).hexdigest()
    if digest != opera['points_sha256']:
        raise ValueError('OPERA sampling coordinates do not match the site')
    dates = []
    for g in opera['granules']:
        if g['reference_date'] != opera['reference_date'] or not g['id'] or not g['concept_id'] or not g['url']:
            raise ValueError('Missing provenance or mixed OPERA references')
        day = date.fromisoformat(g['secondary_date'])
        if day <= date.fromisoformat(opera['reference_date']):
            raise ValueError('Secondary date precedes OPERA reference')
        if dates and day <= dates[-1]:
            raise ValueError('OPERA dates not strictly increasing')
        dates.append(day)
        for key in ('displacement', 'short_wavelength_displacement'):
            values = g['values'][key]
            if len(values) != len(coords):
                raise ValueError('OPERA series size does not match site')
            if any(v is not None and (not isinstance(v, (int, float)) or not math.isfinite(v)) for v in values):
                raise ValueError('Invalid OPERA value')
            if sum(v is not None for v in values) != g['valid_samples']:
                raise ValueError('OPERA accepted count does not match saved values')
    pairs = {}
    for direction in ('ascending', 'descending'):
        pairs[direction] = []
        for p in quality['directions'][direction]['pairs']:
            obs = []
            for key in ('reference_date', 'secondary_date'):
                target = date.fromisoformat(p[key])
                nearest = min(dates, key=lambda d: (abs((d-target).days), d))
                obs.append({'nisar': target.isoformat(), 'nearest_opera': nearest.isoformat(), 'offset_days': (nearest-target).days})
            pairs[direction].append(obs)
    inputs = ('data/mexico.json', 'data/mexico/opera-disp.json', 'data/analysis/mexico-gunw-postgap-quality.json')
    return {'input_sha256': {path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for path in inputs},
            'site_points': len(coords), 'opera_count': len(dates),
            'opera_reference': opera['reference_date'], 'opera_dates': [dates[0].isoformat(), dates[-1].isoformat()],
            'accepted_min': min(g['valid_samples'] for g in opera['granules']),
            'accepted_max': max(g['valid_samples'] for g in opera['granules']),
            'nisar_opera_date_offsets': pairs,
            'limitations': 'Temporal proximity is not a deformation comparison; geometry, reference, filtering, atmospheric residuals, phase signs and quality differ. No velocity or vertical decomposition is estimated.'}

if __name__ == '__main__':
    print(json.dumps(audit(), indent=2))
