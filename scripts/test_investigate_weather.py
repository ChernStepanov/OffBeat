import unittest

import numpy as np

from investigate_weather import common_mode_decompose, corr, seasonal_residual_corr, windows


class WeatherInvestigationTests(unittest.TestCase):
    def test_windows_exclude_acquisition_day_and_make_future_control(self):
        daily = {"time": [f"2026-01-{i:02d}" for i in range(1, 20)],
                 "precipitation_sum": list(range(1, 20))}
        result = windows(daily, "2026-01-16")
        self.assertEqual(result["rain_prev_1d_mm"], 15)
        self.assertEqual(result["rain_prev_3d_mm"], 42)
        self.assertEqual(result["rain_prev_7d_mm"], 84)
        self.assertEqual(result["rain_prev_14d_mm"], 119)
        self.assertEqual(result["rain_future_3d_negative_control_mm"], 54)

    def test_missing_days_are_not_silently_zero_filled(self):
        result = windows({"time": ["2026-01-15", "2026-01-16"],
                          "precipitation_sum": [1, 2]}, "2026-01-16")
        self.assertEqual(result["rain_prev_1d_mm"], 1)
        self.assertIsNone(result["rain_prev_3d_mm"])
        self.assertIsNone(result["rain_future_3d_negative_control_mm"])

    def test_correlations_use_date_pairs_and_leave_one_date_out(self):
        result = corr([1, 2, 3, 4, 5], [2, 4, 6, 8, 10])
        self.assertEqual(result["n_dates"], 5)
        self.assertAlmostEqual(result["pearson_r"], 1)
        self.assertEqual(result["loo_pearson_range"], [1, 1])
        self.assertIsNone(corr([1, 1, 1, 1], [2, 3, 4, 5])["pearson_r"])

    def test_common_mode_is_removed_after_point_own_baseline(self):
        # The step of +2 shared by every point remains in d_it, becomes g_t,
        # and is removed from r_it; prior observations are untouched.
        x = [[0, 2, 1], [5, 7, 6], [10, 12, 11]]
        d, g, r = common_mode_decompose(x)
        self.assertEqual(d[:, 1].tolist(), [1, 1, 1])
        self.assertEqual(g.tolist(), [-1.0, 1.0, 0.0])
        self.assertEqual(r[:, 1].tolist(), [0, 0, 0])
        self.assertEqual(np.asarray(x).tolist(), [[0, 2, 1], [5, 7, 6], [10, 12, 11]])

    def test_seasonal_adjustment_reports_low_df(self):
        dates = [f"2025-{m:02d}-15" for m in range(1, 13)]
        result = seasonal_residual_corr(list(range(12)), list(range(12)), dates)
        self.assertEqual(result["residual_df_approx"], 8)
        self.assertIn("warning", result)


if __name__ == "__main__":
    unittest.main()
