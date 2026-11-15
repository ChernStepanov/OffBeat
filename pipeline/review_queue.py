"""Retrospective multi-sensor review priorities, with no fabricated event labels."""
import argparse
import hashlib
import json
import math
from datetime import date
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
METHODS = ('s1_only', 's1_nisar', 's1_nisar_context')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def days(a, b):
    return (date.fromisoformat(a[:10]) - date.fromisoformat(b[:10])).days


def prior_match(dates, target, max_days):
    eligible = [(days(target, d), i) for i, d in enumerate(dates) if 0 <= days(target, d) <= max_days]
    return min(eligible)[1] if eligible else None


def distance(a, b):
    dlon = a['lon'] - b['lon']
    if abs(dlon) > 180:
        dlon = (dlon + 180) % 360 - 180
    return 111320 * math.hypot(a['lat'] - b['lat'],
                             dlon * math.cos(math.radians((a['lat'] + b['lat']) / 2)))


def values(series):
    return np.array([np.nan if x is None else x for x in series], dtype=float)


def signature(series, peers, pre=3):
    if not np.isfinite(series).all() or not np.isfinite(peers).all() or len(series) < pre + 2:
        return None
    residual = series - peers
    reference = float(np.mean(residual[:pre]))
    post = residual[pre:]
    return {'drop_db': round(reference - float(np.mean(post)), 5),
            'raw_drop_db': round(float(np.mean(series[:pre]) - np.mean(series[pre:])), 5),
            'post_below_history': int(np.sum(post < reference)),
            'post_count': len(post),
            'post_support_fraction': round(float(np.mean(post < reference)), 5),
            'last_residual_change_db': round(reference - float(residual[-1]), 5)}


def channel(site, matrix, config):
    result = []
    for i, p in enumerate(site['pixels']):
        neighbours = [j for j, q in enumerate(site['pixels']) if q['cover'] == p['cover']
                      and config['peer_min_m'] <= distance(p, q) <= config['peer_max_m']]
        support = np.isfinite(matrix[neighbours]).sum(axis=0) if neighbours else np.zeros(matrix.shape[1])
        if len(support) and int(min(support)) >= config['minimum_peers']:
            s = signature(matrix[i], np.nanmedian(matrix[neighbours], axis=0), config['pre_count'])
        else:
            s = None
        if s:
            s['minimum_peers'] = int(min(support))
        result.append(s)
    return result


def point_optical(audit, pixel, site, cutoff):
    # Only point-level SCL observations are used. AOI clear fraction is not point quality.
    parts = pixel['id'].split()
    key = f"{int(parts[1][1:])},{int(parts[2][1:])}"
    entry = audit.get('sentinel2', {}).get('results_by_row_col', {}).get(key)
    clear = []
    if entry:
        seen = set()
        for scenes in entry.get('inventory', {}).values():
            for scene in scenes:
                dt = scene.get('datetime', '')[:10]
                if dt and dt <= cutoff and scene.get('pixel_value') in (4, 5, 6) and scene.get('item_id') not in seen:
                    seen.add(scene.get('item_id'))
                    clear.append({'date': dt, 'scl': scene['pixel_value'], 'scene_id': scene['item_id'],
                                  'scl_asset': scene.get('scl_asset')})
    boundary = site['dates'][3]
    before = [x for x in clear if x['date'] <= site['dates'][2]]
    after = [x for x in clear if x['date'] >= boundary]
    return {'point_quality_reviewed': entry is not None,
            'clear_before': max(before, key=lambda x: x['date']) if before else None,
            'clear_after': max(after, key=lambda x: x['date']) if after else None,
            'status': 'point_clear_pair_available' if before and after else 'point_clear_pair_not_established',
            'interpretation': 'SCL describes visibility/class, not independently verified forest loss.'}


def priority(l, c, optical, config):
    threshold = config['drop_threshold_db']
    def score(s):
        return max(0., s['drop_db'] / threshold) + config['persistence_weight'] * s['post_support_fraction'] if s else None
    s1 = score(c)
    lscore = score(l)
    if lscore is None and s1 is None:
        return None
    if l is None or c is None:
        agreement = 'unavailable'
    elif l['drop_db'] >= threshold and c['drop_db'] >= threshold:
        agreement = 'both_drop'
    elif (l['drop_db'] >= threshold) != (c['drop_db'] >= threshold):
        agreement = 'threshold_disagreement'
    else:
        agreement = 'neither_above_threshold'
    # A missing sensor is not a zero score. Fusion requires both available channels.
    fused = max(lscore, s1) + (config['disagreement_weight'] if agreement == 'threshold_disagreement' else 0.) if lscore is not None and s1 is not None else None
    context = fused + (config['context_gap_weight'] if optical['status'] != 'point_clear_pair_available' else 0.) if fused is not None else None
    return {'scores': {'s1_only': s1, 's1_nisar': fused, 's1_nisar_context': context}, 'agreement': agreement}


def diverse(rows, method, config, limit=None):
    chosen = []
    ranked = sorted((r for r in rows if r['scores'].get(method) is not None),
                    key=lambda r: (-r['scores'][method], r['sample_id']))
    for row in ranked:
        if all(distance(row, q) >= config['review_spacing_m'] for q in chosen):
            chosen.append(row)
            if limit and len(chosen) >= limit:
                break
    return chosen


def build(root=ROOT):
    paths = ['data/review-queue/protocol-v1.json', 'data/amazon.json', 'data/amazon/sentinel1.json',
             'data/amazon-spatial-external-audit-v2.json', 'data/analysis/amazon-era5.json']
    config, site, s1, audit, weather = [json.loads((root / p).read_text()) for p in paths]
    if site['id'] != config['site'] or s1.get('site') != config['site'] or s1.get('units') != 'dB':
        raise ValueError('Sensor site/units do not match the protocol')
    if s1['dates'] != sorted(set(s1['dates'])):
        raise ValueError('S1 dates must be unique and chronological')
    if site['dates'] != config['dates']:
        raise ValueError('Protocol dates differ; create a new protocol version')
    if len(site['pixels']) != site['grid']['n'] ** 2:
        raise ValueError('Unexpected sample grid')
    coords = [(p['lat'], p['lon']) for p in site['pixels']]
    if hashlib.sha256(json.dumps(coords).encode()).hexdigest() != s1['provenance'].get('points_sha256'):
        raise ValueError('S1 coordinate-order receipt does not match NISAR samples')
    cutoff = config['dates'][-1]
    rain_by_date = {x['nisar_date']: x['previous_7_utc_days_mm'] for x in weather['acquisitions']}
    rain = values([rain_by_date.get(d) for d in site['dates']])
    rain_difference = round(float(np.mean(rain[3:]) - np.mean(rain[:3])), 5) if np.isfinite(rain).all() else None
    match = [prior_match(s1['dates'], d, config['s1_max_prior_gap_days']) for d in site['dates']]
    if len({i for i in match if i is not None}) != len([i for i in match if i is not None]):
        raise ValueError('Repeated S1 observations cannot be counted as independent dates')
    lmatrix = np.array([values(p['hv']) for p in site['pixels']])
    cmatrix = np.array([values(s1['points']['vh'][i]) if i is not None else np.full(len(site['pixels']), np.nan) for i in match]).T
    if lmatrix.shape != cmatrix.shape:
        raise ValueError('S1/NISAR spatial membership differs')
    ls = channel(site, lmatrix, config); cs = channel(site, cmatrix, config)
    rows = []
    for index, pixel in enumerate(site['pixels']):
        if pixel['cover'] not in config['eligibility_cover']:
            continue
        optical = point_optical(audit, pixel, site, cutoff)
        rank = priority(ls[index], cs[index], optical, config)
        if rank is None:
            continue
        l, c = ls[index], cs[index]
        candidate = any(s and s['drop_db'] >= config['drop_threshold_db'] and s['post_below_history'] >= config['minimum_post_support'] for s in (l, c))
        if rank['agreement'] == 'unavailable':
            action = 'obtain_missing_sensor'
        elif optical['status'] != 'point_clear_pair_available':
            action = 'obtain_clear_optical'
        elif rank['agreement'] == 'threshold_disagreement':
            action = 'inspect_sensor_disagreement'
        else:
            action = 'independent_image_review'
        rows.append({'sample_id': pixel['id'], 'sample_index': index, 'site': site['id'],
                     'dates': site['dates'],
                     'lat': pixel['lat'], 'lon': pixel['lon'], 'cover_2021': pixel['cover'],
                     'event_group': config['event_group'], 'split': config['split'],
                     'label': 'unknown', 'candidate': candidate,
                     'rain_pre_post_difference_mm': rain_difference,
                     'l_band': l, 'c_band': c, 'optical': optical, 'next_action': action,
                     'scores': {k: round(v, 5) if v is not None else None for k, v in rank['scores'].items()},
                     'agreement': rank['agreement'],
                     'point_support': 'Sparse sample; no event polygon or event area estimate.'})
    rankings = {method: [r['sample_id'] for r in diverse(rows, method, config)] for method in METHODS}
    candidate_rankings = {method: [r['sample_id'] for r in diverse([r for r in rows if r['candidate']], method, config)] for method in METHODS}
    budget = config['review_budget']
    common = [r for r in rows if all(r['scores'][m] is not None for m in METHODS)]
    comparisons = {}
    for m in METHODS:
        top = diverse(common, m, config, budget)
        comparisons[m] = {'eligible_common_samples': len(common), 'review_budget': budget,
                          'review_locations_returned': len(top), 'top_ids': [r['sample_id'] for r in top],
                          'independent_labels': 0, 'event_precision': None, 'event_recall': None,
                          'manual_work_reduction': None}
    reference_ids = set(comparisons['s1_only']['top_ids'])
    ranking_changes = {}
    for m in METHODS[1:]:
        selected_ids = set(comparisons[m]['top_ids'])
        ranking_changes[m] = {'shared_with_s1_top_budget': len(reference_ids & selected_ids),
                              'new_review_locations': sorted(selected_ids - reference_ids),
                              'interpretation': 'A changed priority list is not an improvement in event accuracy.'}
    return {'schema_version': 1, 'id': config['id'], 'site': site['id'], 'decision_date': cutoff,
            'generator_sha256': digest(Path(__file__)),
            'mode': 'retrospective_development', 'protocol': config,
            'input_sha256': {p: digest(root / p) for p in paths},
            'aligned_dates': [{'nisar': d, 's1': s1['dates'][i] if i is not None else None} for d, i in zip(site['dates'], match)],
            'weather_context': {'source': weather['source'], 'acquisitions': weather['acquisitions'],
                                'availability': weather.get('availability'),
                                'usage': 'Retrospective context only; not a causal correction or ranked event label.'},
            'rows': rows, 'rankings': rankings, 'candidate_rankings': candidate_rankings, 'comparison': comparisons,
            'ranking_changes': ranking_changes,
            'evaluation': {'status': 'blocked_missing_independent_events', 'independent_event_groups': 0,
                           'accuracy': None, 'manual_work_reduction': None,
                           'target_manual_work_reduction': 0.25},
            'limitations': [config['independence'], config['availability_policy'],
                           'Heuristic scores are not event probabilities. Sensor thresholds do not establish the same physical response.',
                           'Spacing reduces duplicate inspections, not event dependence. All samples remain one development group.',
                           'A clear SCL pair is not a reviewed disturbance label. Absence of alerts is not a negative label.']}


def geojson(data):
    return {'type': 'FeatureCollection', 'features': [
        {'type': 'Feature', 'geometry': {'type': 'Point', 'coordinates': [r['lon'], r['lat']]},
         'properties': dict(r, decision_date=data['decision_date'])} for r in data['rows']]}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--check', action='store_true'); args = parser.parse_args()
    result = build()
    comparison = {k: result[k] for k in ('id', 'mode', 'decision_date', 'generator_sha256', 'input_sha256', 'comparison', 'ranking_changes', 'evaluation', 'limitations')}
    for name, data in [('amazon-v1.json', result), ('amazon-v1.geojson', geojson(result)), ('comparison-v1.json', comparison)]:
        path = ROOT / 'data/review-queue' / name
        text = json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + '\n'
        if args.check:
            if not path.exists() or path.read_text() != text:
                raise SystemExit('Stale queue artifact: ' + str(path))
        else:
            path.write_text(text)
    print(f"{len(result['rows'])} forest samples; {sum(r['candidate'] for r in result['rows'])} candidate samples; independent event accuracy unknown")
