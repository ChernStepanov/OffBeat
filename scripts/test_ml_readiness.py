"""Guard the audit's missing-data and reconstruction semantics."""
import unittest
from scripts.assess_ml_readiness import reconstruction


def sample_site(n_dates=4):
    return {'dates': [f'2026-01-{i+1:02d}' for i in range(n_dates)],
            'pixels': [{'lat': r * .001, 'lon': c * .001, 'cover': 10,
                        'hv': [0.] * (n_dates-1) + [10.]}
                       for r in range(11) for c in range(11)]}


class ReadinessTests(unittest.TestCase):
    def test_common_shift_is_reconstruction_not_event_detection(self):
        result = reconstruction(sample_site())
        self.assertGreater(result['methods']['persistence']['n'], 0)
        self.assertEqual(result['methods']['persistence']['mae_db'], 10.)
        self.assertEqual(result['methods']['peer_residual_reconstruction']['mae_db'], 0.)
        # A real widespread event could cause this exact shift; zero error cannot validate its detection.
        self.assertEqual(result['status'], 'descriptive_reconstruction_only')

    def test_missing_targets_do_not_become_zero(self):
        site = sample_site()
        for p in site['pixels']: p['hv'][-1] = None
        for metric in reconstruction(site)['methods'].values():
            self.assertEqual(metric['n'], 0)
            self.assertIsNone(metric['mae_db'])

    def test_no_same_class_support(self):
        site = sample_site()
        for i, p in enumerate(site['pixels']): p['cover'] = i
        self.assertEqual(reconstruction(site)['methods']['persistence']['n'], 0)

    def test_two_dates_are_not_training_history(self):
        self.assertEqual(reconstruction(sample_site(2))['status'], 'insufficient_dates')


if __name__ == '__main__':
    unittest.main()
