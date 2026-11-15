"""Offline tests for cached regional Leaflet RGB overlays."""
import hashlib
import json
import unittest
from pathlib import Path

import numpy as np
from PIL import Image
from rasterio.transform import from_origin
from rasterio.warp import calculate_default_transform, transform_bounds

ROOT = Path(__file__).resolve().parents[1]


class RegionalOverlayTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = json.loads((ROOT / "data/investigation/regional-events.json").read_text())

    def test_six_georeferenced_rgba_exports_and_hashes(self):
        products = [(event, p) for event in self.report["optical_catalogue_checks"] for p in event["products"]]
        self.assertEqual(len(products), 6)
        self.assertEqual(self.report["regional_map_overlays"]["network_requests"], 0)
        for event, product in products:
            overlay = product["map_overlay"]
            path = ROOT / overlay["path"]
            self.assertTrue(path.is_file())
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), overlay["sha256"])
            self.assertEqual(overlay["date"], product["datetime"][:10])
            self.assertEqual(overlay["source_scene"], product["scene_id"])
            self.assertEqual(overlay["mask_policy"], "strict SCL classes [4,5,6]; nodata/non-finite RGB alpha=0; SCL nearest-neighbor")
            self.assertIn("not native 10 m", overlay["resolution_qualification"])
            with Image.open(path) as im:
                self.assertEqual(im.mode, "RGBA")
                rgba = np.asarray(im)
            self.assertEqual([rgba.shape[1], rgba.shape[0]], overlay["dimensions_px"])
            alpha = rgba[:, :, 3]
            self.assertTrue(set(np.unique(alpha).tolist()).issubset({0,255}))
            self.assertIn(255, np.unique(alpha))
            self.assertEqual(int((alpha == 255).sum()), overlay["alpha"]["valid_pixels"])
            self.assertEqual(int((alpha == 0).sum()), overlay["alpha"]["transparent_pixels"])
            self.assertEqual(overlay["alpha"]["nonzero_values"], [0,255])

    def test_northup_pixel_edge_bounds_match_original_utm_window(self):
        for event in self.report["optical_catalogue_checks"]:
            for product in event["products"]:
                o = product["map_overlay"]
                w,s,e,n = o["bounds_wgs84"]
                self.assertLess(w,e); self.assertLess(s,n)
                self.assertGreater(w,-50); self.assertLess(e,-49)
                self.assertGreater(s,-5); self.assertLess(n,-4.5)
                a,b,c,d,ee,f = o["wgs84_affine"]
                self.assertEqual((b,d),(0.0,0.0))
                width,height=o["dimensions_px"]
                affine_bounds=[c,f+ee*height,c+a*width,f]
                np.testing.assert_allclose(affine_bounds,[w,s,e,n],rtol=0,atol=1e-12)
                src=product["bounds_m"]
                expected=transform_bounds("EPSG:32722","EPSG:4326",*src,densify_pts=21)
                tolerance=max(abs(a),abs(ee))*1.1+1e-9
                np.testing.assert_allclose([w,s,e,n],expected,rtol=0,atol=tolerance)
                self.assertEqual(o["source_grid"]["bounds_m"],product["bounds_m"])
                self.assertEqual(o["source_grid"]["resolution_m"],20.0)

    def test_existing_numerical_receipts_and_raw_archives_stay_linked(self):
        for event in self.report["optical_catalogue_checks"]:
            for product in event["products"]:
                self.assertIn("map_overlay", product)
                self.assertTrue(product["prior_summary_values_unchanged"])
                self.assertEqual(product["calibration"]["red"]["offset"],0)
                self.assertTrue((ROOT / product["raw_band_window"]["path"]).is_file())
        self.assertEqual(self.report["offline_calibration_recompute"]["products_recomputed"],6)


if __name__ == "__main__":
    unittest.main()
