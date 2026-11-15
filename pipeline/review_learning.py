"""Small event classifier: fit only independently reviewed, spatially separated groups.
The default queue is one development AOI: it CANNOT train/evaluate this model.
No dependency beyond NumPy; all transforms are fitted on train events only.
"""
import argparse
import hashlib
import json
import math
from datetime import date
from pathlib import Path
import numpy as np
from pipeline.review_queue import ROOT, distance, METHODS

BASE = ['c_drop_db', 'c_last_change_db', 'c_post_support']
FEATURES = {'s1_only': BASE,
            's1_nisar': BASE + ['l_drop_db', 'l_last_change_db', 'l_post_support'],
            's1_nisar_context': BASE + ['l_drop_db', 'l_last_change_db', 'l_post_support', 'clear_optical_pair_missing', 'rain_pre_post_difference_mm']}


def extract(row, method):
    result = []
    for band in ('c_band', 'l_band') if method != 's1_only' else ('c_band',):
        s = row.get(band) or {}
        result.extend(s.get(k) for k in ('drop_db', 'last_residual_change_db', 'post_support_fraction'))
    if method == 's1_nisar_context':
        result.append(0. if row['optical']['status'] == 'point_clear_pair_available' else 1.)
        result.append(row.get('rain_pre_post_difference_mm'))
    return np.array([np.nan if x is None else x for x in result], dtype=float)


def reviewed_events(queue, labels, method):
    """Labels cannot override event membership/splits assigned by the data protocol."""
    lookup = {r['sample_id']: r for r in queue['rows']}
    groups = {}; seen = set()
    for review in labels.get('records', []):
        sample_id = review.get('sample_id')
        if sample_id in seen:
            raise ValueError('Duplicate sample review')
        seen.add(sample_id)
        if sample_id not in lookup:
            raise ValueError('Review sample is absent from source queue')
        row = lookup[sample_id]
        if review.get('label') == 'unknown':
            continue
        if review.get('label') not in ('confirmed', 'refuted'):
            raise ValueError('Labels must be confirmed/refuted/unknown')
        if review.get('independent') is not True or review.get('blind_to_scores') is not True or not review.get('reviewer'):
            raise ValueError('Training requires independent, score-blind review with reviewer provenance')
        if not review.get('sources') or not all(s.get('url') and s.get('sha256') and s.get('observed_date') for s in review['sources']):
            raise ValueError('Dated independent source receipts are required')
        for s in review['sources']:
            if len(s['sha256']) != 64 or any(c not in '0123456789abcdef' for c in s['sha256']):
                raise ValueError('Invalid independent source SHA-256')
            date.fromisoformat(s['observed_date'])
        if review.get('spatial_support_match') is not True:
            raise ValueError('Independent evidence must cover the sample/event spatial support')
        if review.get('event_group') != row['event_group'] or review.get('split') != row['split']:
            raise ValueError('Reviews cannot reassign event groups/splits')
        if row['split'] not in ('train', 'calibration', 'test'):
            raise ValueError('Development AOI is not an independent training/test split')
        start, end = review.get('interval', [None, None])
        if not start or not end or start > end:
            raise ValueError('Dated event/stable interval is required')
        date.fromisoformat(start); date.fromisoformat(end)
        dates = row.get('dates', [])
        if sum(d < start for d in dates) < 2 or sum(d > end for d in dates) < 2:
            raise ValueError('Require two guaranteed SAR dates before and after the event/stable interval')
        if len(dates) != 6 or dates != sorted(set(dates)) or not (dates[2] < start and end < dates[3]):
            raise ValueError('Frozen three-before/three-after features require six chronological dates bracketing the entire interval')
        y = int(review['label'] == 'confirmed'); key = row['event_group']
        group = groups.setdefault(key, {'id': key, 'split': row['split'], 'y': y, 'rows': [], 'x': []})
        if group['split'] != row['split'] or group['y'] != y:
            raise ValueError('Event group crosses splits or contains conflicting labels')
        group['rows'].append(row); group['x'].append(extract(row, method))
    events = list(groups.values())
    for i, a in enumerate(events):
        for b in events[i+1:]:
            if a['split'] != b['split'] and any(distance(p, q) < 2400 for p in a['rows'] for q in b['rows']):
                raise ValueError('Cross-split neighbourhoods overlap within 2400 m; larger events may require larger buffers')
    for e in events:
        # Require complete feature support for all compared variants: one common cohort.
        matrix = np.array(e['x']); e['x'] = np.mean(matrix, axis=0)
        if not np.isfinite(e['x']).all():
            raise ValueError('Comparison requires complete sensor features; missing is not zero')
    return events


def sigmoid(x):
    return 1 / (1 + np.exp(-np.clip(x, -35, 35)))


def fit_logistic(x, y, penalty=.1, iterations=1500):
    w = np.zeros(x.shape[1] + 1); design = np.column_stack([np.ones(len(x)), x])
    for _ in range(iterations):
        gradient = design.T @ (sigmoid(design @ w) - y) / len(y)
        gradient[1:] += penalty * w[1:]
        w -= .1 * gradient
    return w


def event_metrics(events, probabilities, budget, target_recall=.8):
    order = sorted(range(len(events)), key=lambda i: (-probabilities[i], events[i]['id']))
    top = order[:budget]; positive = sum(e['y'] for e in events)
    tp = sum(events[i]['y'] for i in top)
    required = None
    if positive:
        target = math.ceil(target_recall * positive)
        found = 0
        for k, i in enumerate(order, 1):
            found += events[i]['y']
            if found >= target:
                required = k
                break
    return {'event_count': len(events), 'positive_events': positive, 'budget': budget, 'reviewed': len(top),
            'precision_at_budget': tp / budget if len(top) == budget else None,
            'recall_at_budget': tp / positive if positive else None,
            'brier': float(np.mean([(p - e['y']) ** 2 for p, e in zip(probabilities, events)])),
            'target_recall': target_recall, 'reviews_to_target_recall': required,
            'top_event_ids': [events[i]['id'] for i in top]}


def run(queue, labels, budget=10, target_recall=.8):
    if budget < 1:
        raise ValueError('Positive review budget required')
    if not 0 < target_recall <= 1:
        raise ValueError('Recall target must be in (0,1] and fixed before test inspection')
    if not labels.get('records'):
        return {'status': 'not_trained_missing_independent_events', 'models': {}, 'accuracy': None,
                'manual_work_reduction': None,
                'next_step': 'Collect new independently reviewed event groups; do not relabel development pixels as test.'}
    output = {'status': 'retrospective_event_evaluation', 'models': {}, 'manual_work_reduction': None,
              'limitations': ['Model probabilities require independent calibration validation; small event counts give uncertain estimates.',
                              'Point buffer checks are necessary but not sufficient for event extent/atmospheric dependence.',
                              'No operational availability or field-damage claims. No hyperparameters were tuned on test.']}
    for method in METHODS:
        events = reviewed_events(queue, labels, method)
        parts = {split: [e for e in events if e['split'] == split] for split in ('train', 'calibration', 'test')}
        for split, es in parts.items():
            if any(sum(e['y'] == c for e in es) < 2 for c in (0, 1)):
                raise ValueError(f'{split} requires at least two distinct positive and two negative event groups; this is a software minimum, not adequate evidence of global accuracy')
        train = np.array([e['x'] for e in parts['train']]); mean = train.mean(axis=0); scale = train.std(axis=0)
        scale[scale < 1e-8] = 1.
        w = fit_logistic((train - mean) / scale, np.array([e['y'] for e in parts['train']]))
        def raw(es):
            x = (np.array([e['x'] for e in es]) - mean) / scale
            return np.column_stack([np.ones(len(x)), x]) @ w
        # Platt transform fitted only to separate calibration EVENTS, not pixel CV.
        cal_raw = raw(parts['calibration'])
        cal_w = fit_logistic(cal_raw[:, None], np.array([e['y'] for e in parts['calibration']]), penalty=.01)
        scores = sigmoid(cal_w[0] + raw(parts['test']) * cal_w[1])
        output['models'][method] = {'feature_names': FEATURES[method], 'train_mean': mean.tolist(), 'train_scale': scale.tolist(),
             'weights': w.tolist(), 'calibration_weights': cal_w.tolist(),
             'event_groups': {split: [e['id'] for e in es] for split, es in parts.items()},
             'test_metrics': event_metrics(parts['test'], scores, budget, target_recall),
             'predictions': [{'event_group': e['id'], 'p_change': float(p), 'label': e['y']} for e, p in zip(parts['test'], scores)]}
    reference = output['models']['s1_only']['test_metrics']['reviews_to_target_recall']
    output['manual_work_reduction'] = {
        method: 1 - model['test_metrics']['reviews_to_target_recall'] / reference if reference else None
        for method, model in output['models'].items()}
    output['comparison_target_recall'] = target_recall
    return output


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--queue', default='data/review-queue/amazon-v1.json')
    parser.add_argument('--labels', default='data/review-queue/independent-labels-v1.json')
    parser.add_argument('--output', default='data/review-queue/learning-status-v1.json')
    parser.add_argument('--budget', type=int, default=10)
    parser.add_argument('--target-recall', type=float, default=.8); args = parser.parse_args()
    paths = [Path(args.queue), Path(args.labels)]
    queue, labels = [json.loads(p.read_text()) for p in paths]
    if labels.get('queue_sha256') != hashlib.sha256(paths[0].read_bytes()).hexdigest():
        raise SystemExit('Labels must identify the exact source queue SHA-256')
    for review in labels.get('records', []):
        if review.get('label') == 'unknown':
            continue
        for source in review.get('sources', []):
            path = Path(source.get('path', ''))
            if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != source.get('sha256'):
                raise SystemExit('Independent source receipt file/hash does not match')
            if source['sha256'] in queue.get('input_sha256', {}).values():
                raise SystemExit('Predictor inputs cannot also serve as independent event-label receipts')
    try:
        result = run(queue, labels, args.budget, args.target_recall)
    except ValueError as error:
        raise SystemExit(str(error))
    result['input_sha256'] = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    result['code_sha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    result['training_config'] = {'architecture': 'binary logistic regression + held-out-event Platt calibration',
                                 'train_penalty': .1, 'calibration_penalty': .01, 'iterations': 1500,
                                 'learning_rate': .1, 'budget': args.budget, 'target_recall': args.target_recall,
                                 'feature_names': FEATURES}
    Path(args.output).write_text(json.dumps(result, indent=2, allow_nan=False) + '\n')
    print(result['status'])
