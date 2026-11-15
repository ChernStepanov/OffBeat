"""Checks for benchmark leakage and insufficient test samples; no network required."""
import unittest
from pipeline.amazon_benchmark import metrics, validate_protocol

class BenchmarkAudit(unittest.TestCase):
    def test_unknown_not_negative(self):
        m = metrics([{'label': 'confirmed'}, {'label': 'unknown'}, {'label': 'refuted'}], 3)
        self.assertIsNone(m['precision_at_k'])
        self.assertEqual(m['precision_bounds'], [1 / 3, 2 / 3])

    def test_insufficient_top_k_is_not_precision_at_k(self):
        m = metrics([{'label': 'confirmed'}], 5)
        self.assertIsNone(m['precision_at_k'])
        self.assertIsNone(m['precision_bounds'])
        with self.assertRaises(ValueError): metrics([], 0)

    def test_spatial_leakage_rejected_even_with_different_groups(self):
        site = {'pixels': [{'id': 'a', 'lat': -4.7, 'lon': -49.2}, {'id': 'b', 'lat': -4.701, 'lon': -49.2}]}
        protocol = {'ids': ['a', 'b'], 'assignments': [
            {'id': 'a', 'event_group': 'one', 'split': 'development'},
            {'id': 'b', 'event_group': 'two', 'split': 'test'}]}
        with self.assertRaisesRegex(ValueError, 'neighbourhoods overlap'):
            validate_protocol(protocol, site)
        site['pixels'][1]['lat'] = -4.8
        validate_protocol(protocol, site)
        protocol['assignments'][1]['event_group'] = 'one'
        with self.assertRaisesRegex(ValueError, 'Event group'):
            validate_protocol(protocol, site)

    def test_invalid_split_cannot_evade_guard(self):
        site = {'pixels': [{'id': 'a'}]}
        protocol = {'ids': ['a'], 'assignments': [{'id': 'a', 'event_group': 'one', 'split': 'holdout'}]}
        with self.assertRaisesRegex(ValueError, 'valid split'):
            validate_protocol(protocol, site)

if __name__ == '__main__':
    unittest.main()
