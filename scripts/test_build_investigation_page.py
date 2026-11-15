import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("build_investigation_page", ROOT / "scripts/build_investigation_page.py")
MOD = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(MOD)


class InvestigationPayloadTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.payload = MOD.build_payload()
        cls.sources = {key: MOD.read_json(path) for key, path in MOD.INPUTS.items()}

    def test_rebuild_is_deterministic_and_check_mode_passes(self):
        self.assertEqual(MOD.render_json(self.payload), MOD.render_json(MOD.build_payload()))
        result = subprocess.run([sys.executable, str(ROOT / "scripts/build_investigation_page.py"), "--check"], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        grid = self.sources["external_maps"]["native_grid"]
        rows, cols = grid["shape"]
        x0, y0, dx, dy = (grid[key] for key in ("x_first", "y_first", "x_step", "y_step"))
        x1, y1 = x0 + (cols - 1) * dx, y0 + (rows - 1) * dy
        corners = [MOD._utm22s_to_lonlat(x, y) for x in (min(x0, x1) - abs(dx) / 2, max(x0, x1) + abs(dx) / 2) for y in (min(y0, y1) - abs(dy) / 2, max(y0, y1) + abs(dy) / 2)]
        expected = [min(lat for _, lat in corners), min(lon for lon, _ in corners), max(lat for _, lat in corners), max(lon for lon, _ in corners)]
        bounds = self.payload["prepared_sar"]["bounds"]
        for actual, reference in zip(bounds, expected):
            self.assertAlmostEqual(actual, reference, places=12)
        self.assertEqual(rows, 141)
        # Every native pixel centre, including all four outermost rows/columns, lies inside the advertised geographic extent.
        for row in range(rows):
            for col in range(cols):
                lon, lat = MOD._utm22s_to_lonlat(x0 + col * dx, y0 + row * dy)
                self.assertLessEqual(bounds[0], lat)
                self.assertGreaterEqual(bounds[2], lat)
                self.assertLessEqual(bounds[1], lon)
                self.assertGreaterEqual(bounds[3], lon)
        negative = MOD.prepared_bounds({"native_grid": {"shape": [3, 4], "x_first": x0, "y_first": y0, "x_step": -20, "y_step": -30}})
        negative_corners = [MOD._utm22s_to_lonlat(x, y) for x in (x0 - 70, x0 + 10) for y in (y0 - 75, y0 + 15)]
        negative_reference = [min(lat for _, lat in negative_corners), min(lon for lon, _ in negative_corners), max(lat for _, lat in negative_corners), max(lon for lon, _ in negative_corners)]
        for actual, reference in zip(negative, negative_reference):
            self.assertAlmostEqual(actual, reference, places=12)

    def test_payload_hashes_every_present_source_and_optional_source_state(self):
        for path in MOD.INPUTS.values():
            expected = MOD.sha256(path)
            self.assertEqual(self.payload["source_hashes"][path], expected)
        self.assertIsNone(MOD.make_weather(None)["mexico_context"])
        self.assertEqual(MOD.make_events(None, None, "no-file.geojson")[1]["status"], "unavailable")
        self.assertEqual(MOD.make_hydrology(None)["status"], "unavailable")
        self.assertIsNone(MOD.local_asset("../../etc/passwd"))

    def test_candidates_are_source_rows_not_synthetic_and_keep_hh_hv_and_optical_dates(self):
        original = self.sources["map_candidates"]
        rows = {x["id"]: x for x in self.payload["candidates"]}
        self.assertEqual(set(rows), {x["id"] for x in original["maps"]})
        self.assertEqual(len(rows), 8)
        self.assertEqual(rows["candidate-01"]["worldcover"]["code"], 10)
        self.assertEqual(rows["candidate-02"]["worldcover"]["code"], 30)
        self.assertEqual(rows["candidate-03"]["worldcover"]["code"], 30)
        self.assertEqual(rows["candidate-04"]["worldcover"]["code"], 10)
        self.assertTrue(all(rows[f"control-{i:02d}"]["worldcover"]["code"] == 10 for i in range(1, 5)))
        self.assertTrue(all(r["worldcover"]["ground_truth"] is False for r in rows.values()))
        self.assertEqual(rows["candidate-01"]["sar_series"]["dates"], original["maps"][0]["sar_series_db"]["dates"])
        self.assertEqual(rows["candidate-01"]["sar_series"]["HH"], original["maps"][0]["sar_series_db"]["HH"])
        self.assertEqual(rows["candidate-01"]["sar_series"]["HV"], original["maps"][0]["sar_series_db"]["HV"])
        self.assertEqual([x["date"] for x in rows["candidate-01"]["optical_scenes"]], ["2026-10-03", "2026-10-21"])
        self.assertEqual(rows["candidate-01"]["evidence_status"], "unknown")
        self.assertAlmostEqual(rows["candidate-01"]["local_cloud_fraction_by_date"]["2026-10-03"], 1 - 0.8092)
        self.assertNotIn("2026-09-28", rows["candidate-01"]["local_cloud_fraction_by_date"], "no cloud estimate is fabricated for a date without local SCL metadata")

    def test_shared_amazon_weather_and_separate_mexico_falsification(self):
        weather = self.payload["weather"]
        self.assertTrue(weather["shared_cell"])
        self.assertEqual(len(weather["dates"]), 6)
        self.assertEqual(len(weather["mexico_context"]["dates"]), 29)
        self.assertEqual([x["date"] for x in weather["dates"]], [x["date"] for x in self.sources["weather"]["sites"]["amazon"]["dates"]])
        mexico = weather["mexico_context"]["targeted_temperature"]
        self.assertAlmostEqual(mexico["level_temperature_vs_hv_scene_median"]["pearson_r"], -0.6644)
        self.assertAlmostEqual(mexico["first_differences_temperature_vs_hv_scene_median"]["pearson_r"], 0.1309)
        self.assertAlmostEqual(mexico["seasonal_trend_adjusted_temperature_vs_hv_scene_median"]["pearson_r"], 0.2201)
        self.assertAlmostEqual(mexico["future_3d_temperature_vs_hv_scene_median_negative_control"]["pearson_r"], -0.5707)
        self.assertIn("not causal", mexico["seasonal_trend_adjusted_temperature_vs_hv_scene_median"]["warning"])

    def test_final_regional_events_include_only_real_registry_features_and_source_falsification(self):
        events = self.payload["events"]
        source = self.sources["regional_events"]
        self.assertEqual(len(events), 3)
        self.assertEqual({x["id"] for x in events}, {x["id"] for x in source["selected_leads"]})
        self.assertEqual(self.payload["regional_events"]["status"], "obtained")
        self.assertEqual([x["class_name"] for x in events], ["DESMATAMENTO_CR"] * 3)
        self.assertTrue(all(x["kind"] == "regional_event" and x["geometry"] for x in events))
        self.assertTrue(all(x["overlaps_prepared_sar"] is False for x in events))
        self.assertTrue(all(x["optical_status"] == "paired_local_pre_post" and len(x["optical_products"]) == 2 for x in events))
        self.assertTrue(all("weather_dates" not in x and "weather_cell_id" not in x for x in events))
        self.assertEqual(self.payload["regional_events"]["assessment_summary"]["supported_localized_optical_change"], 2)
        self.assertEqual(self.payload["regional_events"]["assessment_summary"]["registry_only_background_similar"], 1)
        src_fals = {x["event_id"]: x for x in source["targeted_falsification"]["events"]}
        for event in events:
            self.assertEqual(event["falsification"], src_fals[event["id"]])
        third = next(x for x in events if x["id"].startswith("deter_amz.23558"))
        self.assertEqual(third["falsification"]["evidence_observations"]["calibrated_assessment"]["status"], "registry_only_background_similar")
        first = next(x for x in events if x["id"].startswith("deter_amz.31637"))
        stats = first["falsification"]["comparisons"]["mask_ablation"]["strict_456"]["zone_statistics"]
        self.assertAlmostEqual(stats["event_polygon"]["ndvi"]["median_pixelwise_delta"], -0.28370068222284317)
        self.assertAlmostEqual(stats["ring_60_120m"]["ndvi"]["median_pixelwise_delta"], -0.0954103171825409)
        self.assertAlmostEqual(stats["ring_120_240m"]["ndvi"]["median_pixelwise_delta"], -0.10383838415145874)
        self.assertEqual(self.payload["prepared_sar"]["crs"], 32722)

    def test_hydrology_is_separate_context_and_retains_conservative_prior_semantics(self):
        hydro = self.payload["hydrology"]
        if not self.sources["hydrology"]:
            self.assertEqual(hydro["status"], "unavailable")
            return
        self.assertEqual(hydro["status"], "obtained")
        self.assertEqual(hydro["site_name"], "TucuruiReservoir")
        self.assertEqual(hydro["distance_from_study_km"], 113.0)
        self.assertEqual(hydro["temporal_support"]["product_resolution_days"], 8)
        self.assertEqual(hydro["temporal_support"]["composite_label_semantics"], "unknown")
        self.assertIn("independent altimetry", hydro["note"]["en"])
        self.assertEqual(hydro["area_series_2026"], [r for r in self.sources["hydrology"]["series"]["SNPPJ1_area"] if r["date"].startswith("2026-")])

    def test_all_verified_overlays_are_hash_checked_clipped_and_default_off_metadata(self):
        layers = self.payload["raster_layers"]
        self.assertEqual(len(layers), 5)
        self.assertEqual(sum(layer.get("kind") == "dated_optical" for layer in layers), 2)
        self.assertEqual({layer["date"] for layer in layers if layer.get("kind") == "dated_optical"}, {"2026-10-03", "2026-10-21"})
        sar_s, sar_w, sar_n, sar_e = self.payload["prepared_sar"]["bounds"]
        for layer in layers:
            self.assertEqual(MOD.sha256(layer["path"]), layer["sha256"])
            s, w, n, e = layer["clip_bounds"]
            self.assertGreaterEqual(s, sar_s)
            self.assertGreaterEqual(w, sar_w)
            self.assertLessEqual(n, sar_n)
            self.assertLessEqual(e, sar_e)
        optical = {x["date"]: x for x in layers if x.get("kind") == "dated_optical"}
        self.assertAlmostEqual(optical["2026-10-03"]["valid_fraction"], 0.6112616885756877)
        self.assertAlmostEqual(optical["2026-10-21"]["valid_fraction"], 0.9972557257080905)

    def test_regional_local_scenes_are_real_georeferenced_and_hash_checked(self):
        count = 0
        for event in self.payload["events"]:
            west, south, east, north = event["bounds_wgs84"]
            for product in event["optical_products"]:
                overlay = product["map_overlay"]
                self.assertEqual(MOD.sha256(overlay["path"]), overlay["sha256"])
                self.assertEqual(overlay["date"], product["date"])
                self.assertEqual(overlay["source_scene"], product["scene_id"])
                ow, os, oe, on = overlay["bounds_wgs84"]
                self.assertLessEqual(ow, west)
                self.assertLessEqual(os, south)
                self.assertGreaterEqual(oe, east)
                self.assertGreaterEqual(on, north)
                self.assertIn(overlay["path"], self.payload["source_hashes"])
                self.assertIsNone(MOD.make_local_map_overlay({"map_overlay": {**overlay, "sha256": "0" * 64}}))
                self.assertIsNone(MOD.make_local_map_overlay({"map_overlay": {**overlay, "bounds_wgs84": [False, south, east, north]}}))
                count += 1
        self.assertEqual(count, 6)
        self.assertIsNone(MOD.make_local_map_overlay({}))

    def test_external_historical_zero_loss_code_is_not_event_absence(self):
        rows = {r["id"]: r for r in self.payload["candidates"]}
        self.assertEqual(rows["candidate-01"]["external_features"]["lossyear_calendar_year"], 2006)
        self.assertEqual(rows["candidate-04"]["external_features"]["lossyear_calendar_year"], 2016)
        for key in ("candidate-02", "candidate-03"):
            ext = rows[key]["external_features"]
            self.assertEqual(ext["lossyear_code"], 0)
            self.assertIsNone(ext["lossyear_calendar_year"])
            self.assertEqual(ext["lossyear_source_year"], 2024)


if __name__ == "__main__":
    unittest.main()
