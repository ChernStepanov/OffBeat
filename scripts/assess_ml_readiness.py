"""Audit stored data and a masked-value baseline; no event labels are invented.
Run: python3 scripts/assess_ml_readiness.py --local-draft ../OffBeat
Current-neighbour values are allowed context: this is reconstruction, NOT forecasting.
"""
import argparse
import hashlib
import json
import subprocess
from collections import Counter
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def matrix(pixels, key):
    return np.array([[np.nan if v is None else v for v in p[key]] for p in pixels], dtype=float)


def reconstruction(site):
    """Mask each test target, reconstruct from its past and contemporaneous OTHER points.
    References exclude the central 300 m to reduce direct event-neighbour contamination.
    The 1.2 km radius and >=10 references follow the existing development benchmark.
    """
    pixels = site['pixels']
    if len(site['dates']) < 4:
        return {'status': 'insufficient_dates', 'minimum_dates': 4}
    hv = matrix(pixels, 'hv')
    lat = np.array([p['lat'] for p in pixels]); lon = np.array([p['lon'] for p in pixels])
    cover = np.array([p['cover'] for p in pixels])
    distance = 111320 * np.hypot(lat[:, None] - lat[None, :],
                               (lon[:, None] - lon[None, :]) * np.cos(np.deg2rad(lat.mean())))
    neighbours = (cover[:, None] == cover[None, :]) & (distance >= 300) & (distance <= 1200)
    peer = np.full_like(hv, np.nan)
    for i in range(len(pixels)):
        for t in range(hv.shape[1]):
            values = hv[neighbours[i], t]
            values = values[np.isfinite(values)]
            if len(values) >= 10:
                peer[i, t] = np.median(values)
    residual = hv - peer
    errors = {k: [] for k in ['persistence', 'history_median', 'peer_residual_reconstruction']}
    per_date = []
    for t in range(3, hv.shape[1]):
        # Require all prior observations rather than silently imputing missing channels.
        valid = np.isfinite(hv[:, :t+1]).all(axis=1) & np.isfinite(peer[:, :t+1]).all(axis=1)
        pred = {'persistence': hv[:, t-1], 'history_median': np.median(hv[:, :t], axis=1),
                'peer_residual_reconstruction': np.median(residual[:, :t], axis=1) + peer[:, t]}
        per_date.append({'date': site['dates'][t], 'eligible_targets': int(valid.sum())})
        for method, values in pred.items():
            errors[method].extend((values[valid] - hv[valid, t]).tolist())
    return {'status': 'descriptive_reconstruction_only', 'test_dates': per_date,
            'methods': {k: {'n': len(v), 'mae_db': round(float(np.mean(np.abs(v))), 4) if v else None,
                            'rmse_db': round(float(np.sqrt(np.mean(np.square(v)))), 4) if v else None}
                        for k, v in errors.items()},
            'limitations': ['Current OTHER-point observations are supplied to the peer method; it is not a future forecast.',
                           'No independent event labels; lower MAE does not establish disturbance detection quality.',
                           'Previously explored AOIs; correlated points/dates; no independent generalisation estimate.',
                           'Approximate geographic distances; residual baseline can absorb spatially widespread change.']}


def assess(local=None):
    sites = []; inputs = {}
    for path in sorted((ROOT / 'data').glob('*.json')):
        data = json.loads(path.read_text())
        if not isinstance(data, dict) or data.get('schema_version') != 2 or not isinstance(data.get('pixels'), list):
            continue
        inputs[str(path.relative_to(ROOT))] = sha(path)
        p = data['pixels']; hv = matrix(p, 'hv')
        sites.append({'id': data['id'], 'samples': len(p), 'dates': data['dates'],
                      'complete_hv_samples': int(np.isfinite(hv).all(axis=1).sum()),
                      'displacement_samples_with_two_finite_values': int(sum(sum(v is not None and np.isfinite(v) for v in (x.get('disp') or [])) >= 2 for x in p)),
                      'reconstruction': reconstruction(data)})
    result = {'schema_version': 1, 'assessment_date': '2026-11-15',
              'base_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
              'input_sha256': inputs, 'sites': sites, 'total_samples': sum(s['samples'] for s in sites),
              'independent_event_accuracy': None}
    if local:
        local = Path(local).resolve()
        paths = ['pipeline/ml_engine.py', 'pipeline/phenomena.py', 'data/analysis/ml_model_evaluation.json', 'data/analysis/ml-facts.json']
        result['local_draft_inputs'] = {str(local / p): sha(local / p) for p in paths if (local / p).exists()}
        ep = local / 'data/analysis/ml_model_evaluation.json'
        if ep.exists():
            d = json.loads(ep.read_text()); m = np.array(d['confusion_matrix']['matrix'])
            metrics = d['per_class_metrics']
            result['local_draft_evaluation'] = {'reported_samples': d['sample_count'], 'confusion_total': int(m.sum()),
                'reported_accuracy_percent': d['cv_accuracy_mean'], 'confusion_accuracy_percent': round(float(m.trace()/m.sum()*100), 4),
                'macro_f1_from_rounded_receipt': round(float(np.mean([v['f1_score'] for v in metrics.values()])), 4),
                'majority_label_fraction': round(float(m.sum(axis=1).max()/m.sum()), 4),
                'per_class': metrics,
                'interpretation': 'Agreement with heuristic labels under random pixel cross-validation, not independent event accuracy.',
                'rerun_training': False}
        result['local_dataset_sha256'] = {p.name: sha(p) for p in sorted((local / 'data').glob('*.json')) if isinstance((d := json.loads(p.read_text())), dict) and d.get('schema_version') == 2 and isinstance(d.get('pixels'), list)}
        result['local_phenomenon_sha256'] = {}
        result['local_phenomenon_counts'] = {}
        for p in sorted((local / 'data/phenomena').glob('*.json')):
            d = json.loads(p.read_text())
            result['local_phenomenon_sha256'][p.name] = sha(p)
            result['local_phenomenon_counts'][p.stem] = dict(Counter(x.get('phenomenon', 'missing') for x in d.get('pixels', {}).values()))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--local-draft'); args = parser.parse_args()
    result = assess(args.local_draft)
    out = ROOT / 'data/analysis/ml-readiness-2026-11-15.json'
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print('Samples:', result['total_samples'], 'sites:', len(result['sites']))
    for s in result['sites']:
        r = s['reconstruction']
        print(s['id'], len(s['dates']), 'dates', r.get('methods', r['status']))
    print(out.relative_to(ROOT))
