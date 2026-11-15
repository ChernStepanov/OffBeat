import json
import unittest

import numpy as np

from scripts.research_cross_sensor import build, date_pairs, paired_level_change_bootstrap


class CrossSensorResearchTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = build()

    def test_temporal_matching_has_no_reused_rtc_dates(self):
        result = self.result
        pairs = result["matching"]["by_tolerance_days"]["6"]
        self.assertEqual(len(pairs), 6)
        self.assertEqual(len({p["rtc_date"] for p in pairs}), len(pairs))
        self.assertTrue(all(abs(p["lag_days_calendar"]) <= 6 for p in pairs))
        self.assertTrue(all(p["lag_days_calendar"] == -1 for p in pairs))
        self.assertTrue(all(p["rtc_acquisition_times_utc"] for p in pairs))
        self.assertIn("per-point source granule", pairs[0]["utc_lag_scope"])

    def test_zero_day_matching_does_not_fabricate_pairs(self):
        self.assertEqual(date_pairs(["2026-07-18"], ["2026-07-17"], 0), [])

    def test_paired_coordinate_match_and_independent_unit_are_recorded(self):
        result = self.result
        self.assertEqual(result["metadata"]["coordinates"]["count"], 1024)
        self.assertIn("SHA-256", result["metadata"]["coordinates"]["matching"])
        for analysis in result["analyses"].values():
            self.assertIn("blocks", analysis["spatial_block_bootstrap_pooled"]["unit"])
            self.assertEqual(analysis["change_observation_count"], 5120)

    def test_data_show_static_association_is_not_temporal_agreement(self):
        result = self.result
        a = result["analyses"]["HV_vs_VH"]
        self.assertGreater(a["pooled_level_correlation"], .3)
        self.assertLess(abs(a["consecutive_matched_change_correlation"]), .3)
        self.assertGreater(a["pooled_level_correlation"], a["within_class_and_date_centered_correlation"])
        self.assertIsNotNone(a["class_and_interval_centered_change_correlation"])

    def test_contrast_bootstrap_is_paired_seeded_and_reports_all_scales(self):
        a = self.result["analyses"]["HV_vs_VH"]
        scales = a["level_change_contrast_spatial_bootstrap"]
        self.assertEqual(set(scales), {"2", "4", "8"})
        for size, result in scales.items():
            self.assertTrue(result["paired_same_block_draw_for_level_and_change"])
            self.assertEqual(result["seed"], 20261115 + int(size))
            contrast = result["point_estimates"]["contrast_r_levels_minus_r_changes"]
            self.assertAlmostEqual(contrast,
                                   result["point_estimates"]["r_levels"]-result["point_estimates"]["r_changes"])
            ci = result["ci95"]["contrast_r_levels_minus_r_changes"]
            self.assertLessEqual(ci[0], ci[1])
            self.assertEqual(result["replicates_valid"], result["replicates_requested"])

    def test_bootstrap_seed_reproduces_contrast_interval(self):
        rows, cols = np.repeat(np.arange(32), 32), np.tile(np.arange(32), 32)
        x = np.sin(np.arange(1024)); y = x + .2*np.cos(np.arange(1024))
        cx, cy = np.diff(x), np.diff(y)
        args = (x, y, rows, cols, cx, cy, rows[1:], cols[1:], 8)
        first = paired_level_change_bootstrap(*args, n=100, seed=2718)
        second = paired_level_change_bootstrap(*args, n=100, seed=2718)
        self.assertEqual(first["ci95"], second["ci95"])
        self.assertEqual(first["seed"], 2718)
        self.assertTrue(first["paired_same_block_draw_for_level_and_change"])

    def test_output_contains_no_synthetic_or_accuracy_claim(self):
        result = self.result
        text = json.dumps(result).lower()
        self.assertNotIn("synthetic", text)
        self.assertTrue(any("independent event labels" in x for x in result["limitations"]))


if __name__ == "__main__":
    unittest.main()
