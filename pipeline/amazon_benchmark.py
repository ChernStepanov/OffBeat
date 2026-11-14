"""Frozen, event-grouped Amazon ranking. No event labels enter scoring."""
import hashlib
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def metrics(rows, k):
    """Unknowns stay in the denominator; never silently count them as negatives."""
    top = rows[:k]
    n = len(top)
    positive = sum(r['label'] == 'confirmed' for r in top)
    negative = sum(r['label'] == 'refuted' for r in top)
    unknown = n - positive - negative
    return {'requested_k': k, 'n': n, 'confirmed': positive, 'refuted': negative,
            'unknown': unknown, 'precision_at_k': positive / n if n and not unknown else None,
            'precision_bounds': [positive / n, (positive + unknown) / n] if n else None,
            'false_discoveries': negative, 'false_discovery_fraction': negative / n if n and not unknown else None,
            'label_coverage': (positive + negative) / n if n else None}


def validate_protocol(protocol, site):
    if set(protocol['ids']) != {p['id'] for p in site['pixels']}:
        raise ValueError('Frozen sample membership changed')
    groups = {}
    for item in protocol['assignments']:
        groups.setdefault(item['event_group'], set()).add(item['split'])
    if any(len(splits) != 1 for splits in groups.values()):
        raise ValueError('Event group crosses development/test boundary')
    if len(protocol['assignments']) != len(protocol['ids']):
        raise ValueError('Missing assignments')
    if {a['id'] for a in protocol['assignments']} != set(protocol['ids']):
        raise ValueError('Duplicate or missing assignments')


def rank(site, weather, protocol):
    validate_protocol(protocol, site)
    pixels = site['pixels']
    # The whole small AOI is one conservative event group. Never random pixel split.
    values = np.array([[np.nan if v is None else v for v in p['hv']] for p in pixels])
    rain_by_date = {r['nisar_date']: r['previous_7_utc_days_mm'] for r in weather['acquisitions']}
    rain = np.array([np.nan if rain_by_date.get(d) is None else rain_by_date[d] for d in site['dates']])
    if values.shape[1] != 6:
        raise ValueError('Protocol requires the frozen six-date series')
    rows = []
    assignments = {a['id']: a for a in protocol['assignments']}
    for i, p in enumerate(pixels):
        own = peer = corrected = None
        v = values[i]
        # Exclude target and its 300 m neighbourhood: nearby disturbed points cannot
        # directly subtract the candidate event. Historical cover remains imperfect.
        neighbours = [j for j, q in enumerate(pixels) if q['cover'] == p['cover']
                      and 300 <= np.hypot((q['lat'] - p['lat']) * 111320,
                                          (q['lon'] - p['lon']) * 110930) <= 1200]
        counts = np.isfinite(values[neighbours]).sum(axis=0) if neighbours else np.zeros(6)
        beta = None
        if np.isfinite(v).all() and p['cover'] in (10, 20, 30, 40):
            own = float(np.mean(v[:3]) - np.mean(v[3:]))
            if min(counts) >= 10:
                med = np.nanmedian(values[neighbours], axis=0)
                residual = v - med
                peer = float(np.mean(residual[:3]) - np.mean(residual[3:]))
            # Fixed ridge fit to *pre-change dates only*, with centred rain / 10 mm.
            # Three dates cannot identify a validated causal weather model.
            if np.isfinite(rain).all():
                x = (rain - rain[:3].mean()) / 10
                y = v[:3] - v[:3].mean()
                beta = float(np.dot(x[:3], y) / (np.dot(x[:3], x[:3]) + 1.0))
                w = v - beta * x
                corrected = float(w[:3].mean() - w[3:].mean())
        rows.append({'id': p['id'], 'lat': p['lat'], 'lon': p['lon'], 'cover': p['cover'],
                     'event_group': assignments[p['id']]['event_group'], 'split': assignments[p['id']]['split'],
                     'label': 'unknown', 'history_drop_db': own, 'peer_drop_db': peer,
                     'weather_drop_db': corrected, 'rain_slope_db_per_10mm': beta,
                     'post_dates_below_history': int(np.sum(v[3:] < np.mean(v[:3]))) if np.isfinite(v).all() else None,
                     'hh': p['hh'], 'hv': p['hv'], 'dates': site['dates'],
                     'minimum_peers': int(min(counts))})
    return rows


def run():
    folder = ROOT / 'data/benchmark/amazon-v1'
    protocol = json.loads((folder / 'protocol.json').read_text())
    for name, expected in protocol['input_sha256'].items():
        if digest(ROOT / name) != expected:
            raise ValueError(f'Frozen input changed: {name}; create a new benchmark version')
    site = json.loads((ROOT / 'data/amazon.json').read_text())
    weather = json.loads((ROOT / 'data/analysis/amazon-era5.json').read_text())
    rows = rank(site, weather, protocol)
    evidence = json.loads((folder / 'evidence.json').read_text())
    for r in rows:
        r['evidence'] = evidence['samples'].get(r['id'], [])
    results = {}
    for key in ('history_drop_db', 'peer_drop_db', 'weather_drop_db'):
        valid = sorted((r for r in rows if r[key] is not None), key=lambda r: (-r[key], r['id']))
        negatives = [r for r in valid if r['label'] == 'refuted' and r['split'] == 'test']
        results[key] = {'eligible': len(valid), 'eligible_fraction': len(valid) / len(rows),
                        'fixed_threshold_db': protocol['threshold_db'],
                        'flagged_at_threshold': sum(r[key] >= protocol['threshold_db'] for r in valid),
                        'independent_negative_controls': len(negatives),
                        'false_positive_rate': sum(r[key] >= protocol['threshold_db'] for r in negatives) / len(negatives) if negatives else None,
                        'ranking': [r['id'] for r in valid],
                        'development': [metrics(valid, k) for k in protocol['k']],
                        'independent_test': [metrics([r for r in valid if r['split'] == 'test'], k)
                                             for k in protocol['k']]}
    # Controls are frozen before scoring, not picked to make a method look good.
    report = {'protocol_sha256': digest(folder / 'protocol.json'),
              'evidence_sha256': digest(folder / 'evidence.json'),
              'n_samples': len(rows), 'independent_test_events': 0,
              'methods': results, 'samples': rows,
              'controls': protocol['control_ids'],
              'limitations': ['All existing AOI data are development: previously inspected.',
                              'No eligible independently labelled test events; precision and FPR unavailable.',
                              'Archived visual interpretations are evidence, not blind ground truth.',
                              'Weather is retrospective, availability unknown; no operational claim.',
                              'Weather ablation has only three fitting dates; not validated correction.',
                              'Sparse samples: no area, continuous raster or population recall.',
                              'Point precision is not event precision; one conservative event group.']}
    (folder / 'results.json').write_text(json.dumps(report, indent=2, allow_nan=False) + '\n')
    print(json.dumps({k: {a: b for a, b in v.items() if a != 'ranking'} for k, v in results.items()}, indent=2))


if __name__ == '__main__':
    run()
