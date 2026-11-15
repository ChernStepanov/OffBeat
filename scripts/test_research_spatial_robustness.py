"""Regression checks for the offline dense-grid robustness study."""
import unittest

import numpy as np

from research_spatial_robustness import (
    DATES, linear_mean_ratio_db, peer_complete_mask, require_complete_masks,
    run, validate_peer_grid,
)


class SpatialRobustnessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = run()

    def test_matching_and_completeness(self):
        q = self.result["quality"]
        self.assertEqual(self.result["dates"], DATES)
        self.assertEqual(q["grid_shape"], [141, 141])
        self.assertEqual(q["valid_all_six_both_bands"], 19881)
        self.assertEqual(q["valid_fraction_per_date"], [1.0] * 6)
        audit = self.result["matching"]["dense_receipt_audit"]
        self.assertEqual(audit["track_orbit_frame_tokens"], {"track": "146", "orbit_direction": "A", "frame": "175"})
        self.assertEqual(audit["common_product_processing_id_suffix"], "P05023_N_F_J_001")
        self.assertIn("not performed", self.result["matching"]["sparse_32x32_to_dense_141x141_join"])

    def test_reversal_is_visible_in_full_forest_distribution(self):
        p = self.result["persistence_reversion"]
        self.assertLess(p["2026-09-16"]["HH"]["median"], 0)
        self.assertGreater(p["2026-09-28"]["HH"]["median"], 0)
        self.assertLess(p["2026-09-28"]["both_negative_fraction"], p["2026-09-16"]["both_negative_fraction"])

    def test_threshold_sweep_is_monotone_and_not_accuracy(self):
        rows = self.result["threshold_sweep"]
        counts = [x["forest_cells_both_bands_at_least_2_of_3_post_dates"] for x in rows]
        self.assertEqual(counts, sorted(counts, reverse=True))
        self.assertIn("threshold", rows[0]["definition"])
        self.assertEqual(self.result["polarization_agreement"]["forest_n"], 11265)

    def test_ablation_scales_and_block_uncertainty_are_recorded(self):
        scales = [x["window_cells"] for x in self.result["scale_and_nonlinearity_ablation"]["spatial_median_windows"]]
        self.assertEqual(scales, [1, 3, 5, 9])
        blocks = self.result["spatial_block_bootstrap"]
        self.assertEqual([x["block_px"] for x in blocks], [10, 20, 40])
        self.assertTrue(all(x["mean_ci95"] is not None for x in blocks))

    def test_temporal_estimands_are_separately_reported(self):
        ablation = self.result["scale_and_nonlinearity_ablation"]["per_band"]["HH"]
        self.assertEqual(ablation["paired_dates"], [["2026-07-18", "2026-09-04"], ["2026-08-11", "2026-09-16"], ["2026-08-23", "2026-09-28"]])
        self.assertNotEqual(ablation["median_of_date_dB_difference"]["median"], ablation["median_of_three_paired_post_minus_pre_dB_differences"]["median"])

    def test_peer_dates_and_all_six_date_completeness(self):
        forest = np.ones((1, 2), dtype=bool)
        z = np.zeros((6, 1, 2), dtype=float)
        z[0, 0, 0] = np.nan  # missing only on a pre-period date must exclude it
        mask = peer_complete_mask(forest, z)
        np.testing.assert_array_equal(mask, [[False, True]])
        with self.assertRaises(AssertionError):
            validate_peer_grid(z, DATES[1:], {}, DATES, {}, (1, 2))

    def test_incomplete_mask_policy_for_spatial_filter_and_linear_mean(self):
        masks = np.ones((6, 1, 1), dtype=bool)
        masks[0] = False
        with self.assertRaisesRegex(ValueError, "requires complete valid masks"):
            require_complete_masks(masks, "test spatial filter")

        arr_db = np.array([[[100.0]], [[0.0]], [[0.0]], [[0.0]], [[0.0]], [[0.0]]])
        result = linear_mean_ratio_db(arr_db, masks)
        self.assertAlmostEqual(float(result[0, 0]), 0.0, places=10)


if __name__ == "__main__":
    unittest.main()
