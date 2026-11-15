import unittest

from investigate_hydrology import (
    conservative_composite_prior,
    haversine_km,
    nearest,
    parse_plot,
    variable_source_classification,
)


class HydrologyInvestigationTests(unittest.TestCase):
    def test_parse_preserves_missing_measurements(self):
        values, meta = parse_plot("Plot 1 date:2026-01-01,2026-01-09,2026-01-17\nPlot 1 mean:12.5,,NaN\nPlot 1 clim:1,2,3")
        self.assertEqual(meta["date_count"], 3)
        self.assertEqual(meta["valid_value_count"], 1)
        self.assertIsNone(values[1]["value"])
        self.assertIsNone(values[2]["value"])

    def test_nearest_is_not_interpolated_and_prior_only_excludes_future(self):
        series = [{"date": "2026-09-22", "value": 100}, {"date": "2026-09-30", "value": 80}]
        self.assertEqual(nearest(series, "2026-09-28")["measurement_date"], "2026-09-30")
        prior = nearest(series, "2026-09-28", prior_only=True)
        self.assertEqual(prior["measurement_date"], "2026-09-22")
        self.assertEqual(prior["lag_days_measurement_minus_nisar"], -6)
        self.assertFalse(prior["interpolated"])

    def test_8day_composite_overlap_guard_excludes_label_that_may_overlap_scene(self):
        series = [
            {"date": "2026-09-14", "value": 90},
            {"date": "2026-09-22", "value": 80},
            {"date": "2026-09-30", "value": 70},
        ]
        match = conservative_composite_prior(series, "2026-09-28")
        self.assertEqual(match["composite_label"], "2026-09-14")
        self.assertEqual(match["label_plus_assumed_duration"], "2026-09-22")
        self.assertEqual(match["value"], 90)
        self.assertEqual(match["rule"], "label + 8 days <= NISAR date")
        self.assertIsNone(conservative_composite_prior(series, "2026-09-21"))

    def test_overlap_guard_handles_missing_or_malformed_timestamps(self):
        series = [
            {"date": "2026-09-14", "value": None},
            {"date": "", "value": 55},
            {"date": "not-a-date", "value": 44},
        ]
        self.assertIsNone(conservative_composite_prior(series, "2026-09-28"))

    def test_product_variable_source_labels_distinguish_observed_and_derived(self):
        area = variable_source_classification("area")
        elevation = variable_source_classification("elevation")
        storage = variable_source_classification("storage")
        self.assertIn("classification estimate", area["classification"])
        self.assertEqual(elevation["classification"], "provider-derived estimate")
        self.assertEqual(storage["classification"], "provider-derived estimate")
        self.assertFalse(elevation["independent_observation"])
        self.assertEqual(elevation["not_independent_of"], "the product's area estimate")

    def test_tucurui_distance_is_about_113_km(self):
        self.assertAlmostEqual(haversine_km([-4.775, -49.275], [-3.83, -49.65]), 113, delta=1)


if __name__ == "__main__":
    unittest.main()
