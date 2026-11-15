"""Integrity checks for the georeferenced Amazon visual-review outputs."""
import hashlib, json, unittest
from pathlib import Path
from PIL import Image
import numpy as np
import rasterio
from rasterio.transform import from_origin
from rasterio.warp import reproject, Resampling, transform_bounds
ROOT=Path(__file__).resolve().parents[1]

class MapCandidateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data=json.loads((ROOT/'data/investigation/map-candidates.json').read_text())

    def test_candidate_and_control_sheets_are_real_and_hashed(self):
        self.assertEqual(sum(x['role']=='candidate' for x in self.data['maps']),4)
        self.assertEqual(sum(x['role']=='control' for x in self.data['maps']),4)
        for x in self.data['maps']:
            p=ROOT/x['optical_contact_sheet']
            self.assertTrue(p.is_file())
            self.assertEqual(hashlib.sha256(p.read_bytes()).hexdigest(),x['sha256'])
            with Image.open(p) as image:
                self.assertEqual(image.size,(816,236))

    def test_optical_sources_are_dated_and_receipts_present(self):
        self.assertEqual(len(self.data['optical_scenes']),4)
        self.assertTrue(all(x['date'] and x['item_url'].startswith('https://') and len(x['sha256'])==64 for x in self.data['optical_scenes']))
        self.assertEqual(len(self.data['sar_inputs']),6)
        self.assertTrue(all(len(x['sha256'])==64 for x in self.data['sar_inputs']))

    def test_coordinates_and_roles(self):
        for x in self.data['maps']:
            self.assertTrue(-50<x['lon']<-49 and -5<x['lat']<-4)
            self.assertIn(x['role'],('candidate','control'))

    def test_bilingual_literal_annotations_are_bound_to_native_images(self):
        for x in self.data['maps']:
            self.assertEqual(set(x['observation']),{'ru','en'})
            self.assertEqual(set(x['interpretation']),{'ru','en'})
            self.assertIn(x['status'],('not_visually_confirmed','inconclusive','control_context','unreviewed'))
            self.assertTrue(x['limitations'])
            key=x['visual_annotation_key']
            self.assertEqual(key['native_row'],x['native_row'])
            self.assertEqual(key['native_col'],x['native_col'])
            self.assertEqual(key['coordinate_fingerprint'],x['coordinate_fingerprint'])
            self.assertEqual(key['contact_sheet_sha256'],x['sha256'])
            self.assertEqual(key['new_contact_sheet_sha256'],x['new_optical_contact_sheet']['sha256'])
            self.assertTrue(key['source_fingerprint'])

    def test_sar_series_and_hv_selector_are_explicit(self):
        self.assertEqual(self.data['selection']['candidate_count_screen'],1452)
        self.assertIn('HV-only',self.data['selection']['candidate_count_rule'])
        self.assertIn('83',self.data['selection']['candidate_count_rule'])
        for x in self.data['maps']:
            self.assertEqual(x['sar_series_db']['dates'],['2026-07-18','2026-08-11','2026-08-23','2026-09-04','2026-09-16','2026-09-28'])
            self.assertEqual(len(x['sar_series_db']['HH']),6)
            self.assertEqual(len(x['sar_series_db']['HV']),6)
            self.assertIn('joint3dbflag',x)
            self.assertIn('both HH and HV',x['joint3dbflag_rule'])
            self.assertIsInstance(x['worldcover2021_code'],int)

    def test_new_optical_quality_calibration_and_mask_receipts(self):
        scenes=self.data['new_optical_evidence']['selected_scenes']
        self.assertEqual([s['date'] for s in scenes],['2026-10-03','2026-10-21'])
        self.assertIn('classes 4,5,6 ',scenes[0]['mask'])
        self.assertNotIn('4,5,6,7',scenes[0]['mask'])
        for scene in scenes:
            self.assertTrue(scene['processing_metadata']['earthsearch_boa_offset_applied'])
            self.assertEqual(scene['native_analysis_grid']['resolution_m'],20)
            self.assertIn('B04',scene['indices'])
            p=ROOT/scene['asset_npz']
            self.assertEqual(hashlib.sha256(p.read_bytes()).hexdigest(),scene['asset_npz_sha256'])
            with np.load(p) as a:
                self.assertTrue({'red','nir','swir16','scl','ndvi','ndmi'}<=set(a.files))
        for x in self.data['maps']:
            self.assertEqual([s['date'] for s in x['new_optical']],['2026-10-03','2026-10-21'])
            late=x['new_optical'][1]
            self.assertEqual(late['local_scl_clear_fraction'],1.0)
            early=x['new_optical'][0]
            expected='usable_local_context' if early['local_scl_clear_fraction']>=.8 else 'cloud_limited_context'
            self.assertEqual(early['context_status'],expected)
        c04=next(x for x in self.data['maps'] if x['id']=='candidate-04')
        self.assertAlmostEqual(c04['new_optical'][0]['local_scl_clear_fraction'],.4892)
        self.assertEqual(c04['new_optical'][0]['context_status'],'cloud_limited_context')

    def test_leaflet_overlays_are_reprojected_hashed_rgba_with_scl_alpha(self):
        overlays=self.data['new_optical_overlays']
        self.assertEqual([x['date'] for x in overlays],['2026-10-03','2026-10-21'])
        scenes={x['date']:x for x in self.data['new_optical_evidence']['selected_scenes']}
        for overlay in overlays:
            p=ROOT/overlay['path']
            self.assertEqual(hashlib.sha256(p.read_bytes()).hexdigest(),overlay['sha256'])
            w,s,e,n=overlay['bounds_wgs84']
            self.assertLess(w,e); self.assertLess(s,n)
            scene=scenes[overlay['date']]
            # WGS84 raster bounds must be the projected UTM-window perimeter, not relabelled UTM.
            sb=scene['bounds_m']
            expected=transform_bounds('EPSG:32722','EPSG:4326',*sb,densify_pts=21)
            for actual,want in zip((w,s,e,n),expected): self.assertAlmostEqual(actual,want,places=4)
            with Image.open(p) as im:
                rgba=np.array(im.convert('RGBA'))
                self.assertEqual(list(im.size),overlay['output_dimensions_px'])
            alpha=rgba[:,:,3]
            self.assertTrue(set(np.unique(alpha))<={0,255})
            self.assertGreater(int((alpha==255).sum()),0)
            self.assertGreater(int((alpha==0).sum()),0)
            # Independently nearest-warp source SCL and require exactly classes 4/5/6 opaque.
            source=ROOT/scene['asset_npz']
            with np.load(source) as a: scl=a['scl']
            h,wpx=scl.shape; west,south,east,north=scene['bounds_m']
            src=from_origin(west,north,20,20); dst_transform=rasterio.transform.from_bounds(w,s,e,n,rgba.shape[1],rgba.shape[0])
            mask=np.zeros(alpha.shape,dtype='uint8')
            reproject(scl,mask,src_transform=src,src_crs='EPSG:32722',dst_transform=dst_transform,
              dst_crs='EPSG:4326',src_nodata=0,dst_nodata=0,resampling=Resampling.nearest)
            self.assertTrue(np.array_equal(alpha==255,np.isin(mask,[4,5,6])))
            self.assertEqual(overlay['legend']['reflectance_stretch'],[0,0.3])
            self.assertEqual(overlay['legend']['gamma'],2.2)
            self.assertIn('class 4 vegetation, 5 not-vegetated, or 6 water',overlay['valid_mask_policy'])

if __name__=='__main__': unittest.main()
