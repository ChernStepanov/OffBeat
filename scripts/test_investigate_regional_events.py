"""Offline integrity checks for the bounded regional-event investigation."""
import hashlib
import json
import unittest
from pathlib import Path

from shapely.geometry import shape, box
from reconcile_regional_provenance import resolve

ROOT = Path(__file__).resolve().parents[1]


class RegionalEventsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = json.loads((ROOT / "data/investigation/regional-events.json").read_text())
        cls.geo = json.loads((ROOT / "data/investigation/regional/deter-selected.geojson").read_text())

    def test_exact_center_and_radius(self):
        self.assertEqual(self.report["study_center"]["lon"], -49.275)
        self.assertEqual(self.report["study_center"]["lat"], -4.775)
        self.assertEqual(self.report["search_radius_m"], 25_000)
        self.assertEqual(self.report["source"]["source_receipt"]["number_matched"], 20)
        self.assertEqual(self.report["source"]["source_receipt"]["in_radius_count"], 12)

    def test_three_distinct_2026_events_outside_aoi(self):
        selected = self.report["selected_leads"]
        self.assertEqual({x["id"] for x in selected}, {
            "deter_amz.31637_curr", "deter_amz.26062_curr", "deter_amz.23558_curr"})
        aoi = box(-49.2875, -4.7875, -49.2625, -4.7625)
        features = {x["id"]: x for x in self.geo["features"]}
        for event in selected:
            self.assertEqual(event["properties"]["classname"], "DESMATAMENTO_CR")
            self.assertTrue(event["properties"]["view_date"].startswith("2026-"))
            self.assertLessEqual(event["distance_center_m"], 25_000)
            geom = shape(features[event["id"]]["geometry"])
            self.assertFalse(geom.intersects(aoi))
        receipt = self.report["selected_geometry"]
        path = ROOT / receipt["path"]
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), receipt["sha256"])

    def test_optical_windows_are_dated_clear_and_inside_polygon(self):
        self.assertEqual(len(self.report["optical_catalogue_checks"]), 3)
        for result in self.report["optical_catalogue_checks"]:
            self.assertEqual(result["status"], "dated_windows_ready")
            products = {x["phase"]: x for x in result["products"]}
            self.assertEqual(set(products), {"before", "after"})
            for product in products.values():
                self.assertIsNotNone(product["catalogue_created_at"])
                self.assertIn("acquisition observation time", product["timestamp_note"])
                self.assertGreaterEqual(product["event_polygon_clear_fraction"], .8)
                self.assertGreater(product["event_polygon_clear_pixels"], 0)
                self.assertLess(product["bytes"], 30_000_000)
                path = ROOT / product["npz"]
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), product["sha256"])
                self.assertTrue((ROOT / product["rgb_preview"]).is_file())
            self.assertLess(products["before"]["days_from_view_date"], 0)
            self.assertGreater(products["after"]["days_from_view_date"], 0)

    def test_no_sar_or_blind_accuracy_claim(self):
        interpretation = self.report["interpretation"]
        self.assertIn("not independent blind validation", interpretation["not_accuracy"])
        self.assertIn("no NISAR/SAR detection", interpretation["nisar"])

    def test_cached_paired_falsification_and_all_map_hashes(self):
        events = self.report["targeted_falsification"]["events"]
        self.assertEqual(len(events), 3)
        by_id = {e["event_id"]: e for e in events}
        expected = {
            "deter_amz.31637_curr": "supported_localized_optical_decrease",
            "deter_amz.26062_curr": "supported_localized_optical_decrease",
            "deter_amz.23558_curr": "registry_only_background_similar"}
        for event_id, status in expected.items():
            event = by_id[event_id]
            self.assertEqual(event["evidence_observations"]["calibrated_assessment"]["status"], status)
            self.assertFalse(event["maps"]["inside_prepared_nisar_aoi"])
            self.assertFalse(event["comparisons"]["background_is_verified_negative"])
            for phase in ("before", "after"):
                p = event["maps"][phase]
                path = ROOT / p["path"]
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), p["sha256"])
            for policy in ("strict_456", "extended_4567"):
                metrics = event["comparisons"]["mask_ablation"][policy]
                self.assertGreater(metrics["paired_common_valid_event_pixels"], 100)
                self.assertEqual(set(metrics["zone_statistics"]),
                                 {"event_polygon", "ring_60_120m", "ring_120_240m"})
                for ring in ("ring_60_120m", "ring_120_240m"):
                    match = metrics["pre_ndvi_matched_ring_comparison"][ring]
                    self.assertTrue(match["sufficient_support"])
                    self.assertGreaterEqual(match["support_n"], 20)
            self.assertIn("No p-values", event["comparisons"]["statistics_note"])

        # The third event is locally indistinguishable from paired ring browning in NDVI.
        third = by_id["deter_amz.23558_curr"]["comparisons"]["mask_ablation"]["strict_456"]
        inside = third["zone_statistics"]["event_polygon"]["ndvi"]["median_pixelwise_delta"]
        near = third["zone_statistics"]["ring_60_120m"]["ndvi"]["median_pixelwise_delta"]
        self.assertLess(abs(inside-near), .02)

    def test_offline_calibration_branch_semantics(self):
        def item(flag_marker="missing", band_offset_marker="missing"):
            props = {"s2:processing_baseline": "05.12"}
            if flag_marker != "missing":
                props["earthsearch:boa_offset_applied"] = flag_marker
            band = {"scale": .0001}
            if band_offset_marker != "missing":
                band["offset"] = band_offset_marker
            return {"properties": props, "assets": {name: {"raster:bands": [band]}
                for name in ("red", "green", "blue", "nir", "swir16")}}

        true_flag = resolve(item(True, -.1))
        self.assertIs(true_flag["flag"], True)
        self.assertEqual(true_flag["flag_type"], "bool")
        self.assertEqual(true_flag["bands"]["red"]["original_band_offset"], -.1)
        self.assertEqual(true_flag["bands"]["red"]["effective_offset"], 0)
        self.assertEqual(true_flag["bands"]["red"]["calibration_branch"],
                         "boa_offset_applied_true_effective_offset_zero")

        false_flag = resolve(item(False, -.1))
        self.assertIs(false_flag["flag"], False)
        self.assertEqual(false_flag["flag_type"], "bool")
        self.assertEqual(false_flag["bands"]["red"]["effective_offset"], -.1)
        self.assertEqual(false_flag["bands"]["red"]["calibration_branch"], "asset_band_offset")

        string_flag = resolve(item("true", -.1))
        self.assertEqual(string_flag["flag_type"], "str")
        self.assertEqual(string_flag["bands"]["red"]["effective_offset"], -.1)
        self.assertEqual(string_flag["bands"]["red"]["calibration_branch"], "asset_band_offset")

        missing_flag = resolve(item("missing", "missing"))
        self.assertIsNone(missing_flag["flag"])
        self.assertEqual(missing_flag["flag_type"], "missing")
        self.assertEqual(missing_flag["bands"]["red"]["effective_offset"], -.1)
        self.assertEqual(missing_flag["bands"]["red"]["calibration_branch"],
                         "processing_baseline_ge_4_inferred_offset")

    def test_archived_original_payloads_and_reconciled_calibration(self):
        manifest_path = ROOT / self.report["raw_provenance_archive"]["manifest_path"]
        manifest = json.loads(manifest_path.read_text())
        self.assertEqual(hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
                         self.report["raw_provenance_archive"]["manifest_sha256"])
        wfs = self.report["source"]["raw_original_response"]
        self.assertEqual(wfs["request_url"], self.report["source"]["source_receipt"]["url"])
        self.assertIsNone(wfs["request_body"])
        self.assertFalse(wfs["prior_response_body_available"])
        self.assertIn("unverifiable", wfs["version_drift_from_initial_response"])
        wfs_path = ROOT / wfs["path"]
        self.assertEqual(hashlib.sha256(wfs_path.read_bytes()).hexdigest(), wfs["sha256"])
        raw_wfs = json.loads(wfs_path.read_text())
        self.assertEqual(len(raw_wfs["features"]), 20)
        derived = {f["id"]: f for f in self.geo["features"]}
        original = {f["id"]: f for f in raw_wfs["features"]}
        self.assertTrue(wfs["selected_geometry_comparison"]["all_selected_features_match"])
        for ident, feature in derived.items():
            self.assertEqual(original[ident]["geometry"], feature["geometry"])
            for key, value in original[ident]["properties"].items():
                self.assertEqual(feature["properties"][key], value)

        raw_items = {x["stac_id"]: x for x in manifest["stac_unique_items"]}
        self.assertEqual(len(raw_items), 4)
        self.assertEqual(len(manifest["scene_uses"]), 6)
        for scene_id, receipt in raw_items.items():
            self.assertEqual(receipt["method"], "GET")
            self.assertIsNone(receipt["request_body"])
            self.assertTrue(receipt["source_time_utc"])
            path = ROOT / receipt["path"]
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), receipt["sha256"])
            raw_item = json.loads(path.read_text())
            flag = raw_item["properties"]["earthsearch:boa_offset_applied"]
            self.assertIs(flag, True)
            self.assertEqual(type(flag).__name__, "bool")
            for band in ("red", "green", "blue", "nir", "swir16"):
                cal = receipt["asset_calibration"][band]
                self.assertEqual(cal["original_band_scale"], .0001)
                self.assertEqual(cal["original_band_offset"], -.1)
                self.assertEqual(cal["effective_scale"], .0001)
                self.assertEqual(cal["effective_offset"], 0)

        uses = 0
        first_npz_hash = None
        for event in self.report["optical_catalogue_checks"]:
            for product in event["products"]:
                uses += 1
                self.assertTrue(product["prior_summary_values_unchanged"])
                self.assertEqual(product["offline_recompute_status"], "recomputed_from_hash_verified_local_raw_windows")
                self.assertFalse(product["prior_calibration_matches_verified_source"])
                raw_receipt = product["raw_band_window"]
                raw_path = ROOT / raw_receipt["path"]
                self.assertEqual(hashlib.sha256(raw_path.read_bytes()).hexdigest(), raw_receipt["sha256"])
                arrays = __import__("numpy").load(raw_path)
                self.assertEqual(set(arrays.files), {"raw_blue", "raw_green", "raw_red", "raw_nir", "raw_swir16", "raw_scl", "event_polygon_mask"})
                self.assertEqual(product["calibration"]["red"]["earthsearch:boa_offset_applied"], True)
                self.assertEqual(product["calibration"]["red"]["offset"], 0)
                if event["event_id"] == "deter_amz.31637_curr" and product["phase"] == "before":
                    first_npz_hash = product["sha256"]
        self.assertEqual(uses, 6)
        self.assertEqual(self.report["offline_calibration_recompute"]["network_requests"], 0)
        self.assertEqual(self.report["offline_calibration_recompute"]["products_recomputed"], 6)
        before_fix = {x["event_id"]: x for x in self.report["targeted_falsification_before_provenance_fix"]["events"]}
        after_fix = {x["event_id"]: x for x in self.report["targeted_falsification"]["events"]}
        for event_id in before_fix:
            self.assertEqual(before_fix[event_id]["comparisons"], after_fix[event_id]["comparisons"])
            self.assertEqual(before_fix[event_id]["evidence_observations"]["calibrated_assessment"],
                             after_fix[event_id]["evidence_observations"]["calibrated_assessment"])
        # This hash was recorded for the original first NPZ before any reprocessing.
        self.assertEqual(first_npz_hash, "9786a37eb90d36fedcfc9e2c91c793484a2c0e4b4818f214109fc487dbf1686c")


if __name__ == "__main__":
    unittest.main()
