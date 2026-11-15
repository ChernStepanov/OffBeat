"""Scientific guardrails and synthetic algorithm tests; no synthetic production labels."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
from pipeline.review_queue import prior_match, signature, point_optical, priority, diverse, distance, ROOT, build
from pipeline.review_learning import run, reviewed_events

CONFIG = json.loads((ROOT / 'data/review-queue/protocol-v1.json').read_text())


def synthetic_events():
    """Only software fixtures: deliberately not saved as independent real event evidence."""
    rows = []; reviews = []
    for s, split in enumerate(['train', 'calibration', 'test']):
        for y in (0, 1):
            for n in range(2):
                i = len(rows); pid = f'TEST {i}'
                signal = {'drop_db': 4. * y + n * .1, 'last_residual_change_db': 3. * y, 'post_support_fraction': float(y)}
                row = {'sample_id': pid, 'event_group': f'synthetic-{i}', 'split': split,
                       'lat': i * .1, 'lon': 0., 'c_band': signal, 'l_band': signal,
                       'rain_pre_post_difference_mm': 2.,
                       'dates': ['2026-01-01', '2026-01-13', '2026-01-25', '2026-02-06', '2026-02-18', '2026-03-02'],
                       'optical': {'status': 'point_clear_pair_not_established'}}
                rows.append(row)
                reviews.append({'sample_id': pid, 'event_group': row['event_group'], 'split': split,
                                'label': 'confirmed' if y else 'refuted', 'independent': True,
                                'blind_to_scores': True, 'reviewer': 'SYNTHETIC TEST FIXTURE',
                                'spatial_support_match': True, 'interval': ['2026-01-26', '2026-02-05'],
                                'sources': [{'url': 'https://example.invalid/fixture', 'sha256': '0' * 64, 'observed_date': '2026-02-06'}]})
    return {'rows': rows}, {'records': reviews}


class QueueTests(unittest.TestCase):
    def test_only_prior_sensor_dates(self):
        self.assertEqual(prior_match(['2026-09-02', '2026-09-05'], '2026-09-04', 2), 0)
        self.assertIsNone(prior_match(['2026-09-05'], '2026-09-04', 2))
        self.assertIsNone(prior_match(['2026-08-30'], '2026-09-04', 2))

    def test_drop_and_missing_are_distinct(self):
        self.assertIsNone(signature(np.array([0, 0, 0, np.nan, 0, 0]), np.zeros(6)))
        s = signature(np.array([0., 0, 0, -3, -3, -3]), np.zeros(6))
        self.assertEqual(s['drop_db'], 3.)
        self.assertEqual(s['post_below_history'], 3)
        r = priority(s, None, {'status': 'point_clear_pair_not_established'}, CONFIG)
        self.assertIsNone(r['scores']['s1_nisar'])
        self.assertIsNone(r['scores']['s1_only'])
        self.assertEqual(r['agreement'], 'unavailable')

    def test_point_quality_excludes_shadow_and_future(self):
        audit = {'sentinel2': {'results_by_row_col': {'5,15': {'inventory': {'pre': [
            {'datetime': '2026-08-14T10:00:00Z', 'pixel_value': 4, 'item_id': 'a'}], 'post': [
            {'datetime': '2026-09-21T10:00:00Z', 'pixel_value': 3, 'item_id': 'b'},
            {'datetime': '2026-10-01T10:00:00Z', 'pixel_value': 5, 'item_id': 'c'}]}}}}}
        result = point_optical(audit, {'id': 'AMA r5 c15'}, {'dates': CONFIG['dates']}, '2026-09-28')
        self.assertIsNotNone(result['clear_before']); self.assertIsNone(result['clear_after'])
        self.assertEqual(result['status'], 'point_clear_pair_not_established')

    def test_same_class_spacing_and_missing_scores(self):
        self.assertLess(distance({'lat': 0, 'lon': 179.999}, {'lat': 0, 'lon': -179.999}), 300)
        rows = [{'sample_id': str(i), 'lat': i * .001, 'lon': 0., 'scores': {'s1_only': i}} for i in range(10)]
        rows.append({'sample_id': 'missing', 'lat': 9., 'lon': 0., 'scores': {'s1_only': None}})
        chosen = diverse(rows, 's1_only', CONFIG)
        self.assertTrue(all(distance(a, b) >= 300 for i, a in enumerate(chosen) for b in chosen[i+1:]))
        self.assertNotIn('missing', [r['sample_id'] for r in chosen])

    def test_s1_coordinate_receipt_is_enforced(self):
        original = json.loads
        def changed(text):
            d = original(text)
            if isinstance(d, dict) and d.get('collection') == 'C2777436413-ASF':
                d['provenance']['points_sha256'] = 'bad'
            return d
        with patch('pipeline.review_queue.json.loads', side_effect=changed):
            with self.assertRaisesRegex(ValueError, 'coordinate-order'):
                build()

    def test_production_queue_has_no_fake_truth(self):
        d = json.loads((ROOT / 'data/review-queue/amazon-v1.json').read_text())
        self.assertEqual({r['label'] for r in d['rows']}, {'unknown'})
        self.assertEqual({r['event_group'] for r in d['rows']}, {'amazon-development-aoi'})
        for method in d['comparison'].values():
            self.assertIsNone(method['event_precision']); self.assertIsNone(method['manual_work_reduction'])
        self.assertTrue(all(pair['s1'] <= pair['nisar'] for pair in d['aligned_dates'] if pair['s1']))


class LearningTests(unittest.TestCase):
    def test_empty_truth_does_not_train(self):
        self.assertEqual(run({'rows': []}, {'records': []})['status'], 'not_trained_missing_independent_events')

    def test_development_labels_cannot_be_promoted(self):
        q, labels = synthetic_events(); q['rows'][0]['split'] = 'development'; labels['records'][0]['split'] = 'development'
        with self.assertRaisesRegex(ValueError, 'Development AOI'):
            run(q, labels)

    def test_no_training_on_post_score_notes_or_unknowns(self):
        q, labels = synthetic_events(); labels['records'][0]['blind_to_scores'] = False
        with self.assertRaisesRegex(ValueError, 'score-blind'):
            run(q, labels)
        q, labels = synthetic_events(); labels['records'][0]['label'] = 'unknown'
        es = reviewed_events(q, labels, 's1_only')
        self.assertEqual(len(es), 11)

    def test_nearby_event_split_leaks_are_rejected(self):
        q, labels = synthetic_events(); q['rows'][4]['lat'] = .0001
        with self.assertRaisesRegex(ValueError, 'neighbourhoods overlap'):
            run(q, labels)

    def test_time_support_before_after_is_required(self):
        q, labels = synthetic_events(); labels['records'][0]['interval'] = ['2025-01-01', '2026-02-05']
        with self.assertRaisesRegex(ValueError, 'two guaranteed SAR'):
            run(q, labels)
        q, labels = synthetic_events(); labels['records'][0]['interval'] = ['2026-01-20', '2026-02-05']
        with self.assertRaisesRegex(ValueError, 'three-before/three-after'):
            run(q, labels)

    def test_synthetic_training_and_train_only_transforms(self):
        q, labels = synthetic_events(); result = run(q, labels, budget=2)
        for model in result['models'].values():
            self.assertEqual(model['test_metrics']['event_count'], 4)
            self.assertEqual(model['test_metrics']['precision_at_budget'], 1.)
            self.assertEqual(model['test_metrics']['reviews_to_target_recall'], 2)
        self.assertEqual(result['manual_work_reduction']['s1_nisar'], 0.)
        changed = copy.deepcopy(q)
        for r in changed['rows']:
            if r['split'] == 'test': r['c_band']['drop_db'] = 99999.
        later = run(changed, labels, budget=2)
        self.assertEqual(result['models']['s1_only']['train_mean'], later['models']['s1_only']['train_mean'])
        self.assertEqual(result['models']['s1_only']['weights'], later['models']['s1_only']['weights'])


if __name__ == '__main__':
    unittest.main()
