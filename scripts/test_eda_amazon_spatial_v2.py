import numpy as np

from scripts.eda_amazon_spatial_v2 import (point_in_geometry, relation, haversine_m, pick_candidates, run)


def test_polygon_hole_and_coordinate_order():
    polygon = {"type": "Polygon", "coordinates": [[[0, 0], [4, 0], [4, 4], [0, 4], [0, 0]],
                                                     [[1, 1], [3, 1], [3, 3], [1, 3], [1, 1]]]}
    assert point_in_geometry(0.5, 0.5, polygon)
    assert not point_in_geometry(2, 2, polygon)
    assert not point_in_geometry(5, 2, polygon)
    assert point_in_geometry(0, 2, polygon)  # covers includes boundary


def test_invalid_polygon_is_repaired_and_boundary_covered():
    invalid = {"type": "Polygon", "coordinates": [[[0, 0], [2, 2], [0, 2], [2, 0], [0, 0]]]}
    assert point_in_geometry(1, 0, invalid)
    assert point_in_geometry(0.5, 0.25, invalid)


def test_sar_calendar_day_alert_dates_are_ambiguous_without_time():
    assert relation("2026-08-23") == "same_sar_calendar_day_time_ambiguous"
    assert relation("2026-09-04") == "same_sar_calendar_day_time_ambiguous"
    assert relation("2026-08-24") == "between_sar_dates"


def test_multipolygon_and_geodesic_distance():
    geom = {"type": "MultiPolygon", "coordinates": [[[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]]}
    assert point_in_geometry(.5, .5, geom)
    assert abs(haversine_m(0, 0, 1, 0) - 111195) < 20


def test_sampling_is_reproducible_and_spatially_spaced():
    ok = np.ones((10, 12), bool)
    delta = np.arange(120, dtype=float).reshape(10, 12) - 60
    lat, lon = np.indices(ok.shape, dtype=float)
    a = pick_candidates(ok, delta, delta, lat, lon)
    b = pick_candidates(ok, delta, delta, lat, lon)
    assert a == b
    assert {x["role"] for x in a} == {"strong", "random_control", "low_change_control"}
    for i, x in enumerate(a):
        for y in a[i + 1:]:
            assert max(abs(x["row"] - y["row"]), abs(x["col"] - y["col"])) >= 3


def test_real_audit_reports_precise_provenance_and_no_scl_claim():
    out = run()
    assert out["pair"] == ["2026-08-23", "2026-09-04"]
    assert out["provenance"]["paired_valid_cells"] > 0
    assert len(out["sar_acquisitions"]) == 2
    assert out["sar_acquisitions"][0]["start_utc"] == "2026-08-23T09:04:09Z"
    strong = [c for c in out["candidate_results"] if c["role"] == "strong"]
    assert len(strong) == 4
    assert all(c["delta_hh_db"] < 0 and c["delta_hv_db"] < 0 for c in strong)
    assert out["selection_comparison"]["revised_candidates_same_cell_as_previous"]
    geometry = out["local_alert_geometry_validation"]
    assert geometry["feature_count"] == 373
    assert geometry["invalid_geometry_count"] == 200
    assert geometry["all_repaired_geometries_valid"]
    assert geometry["make_valid_output_types"] == {"MultiPolygon": 198, "GeometryCollection": 2}
    assert out["sentinel2_scl"]["status"].startswith("not_locally_available")
    assert all("alert_polygon_intersections" in c and "firms_in_500m" in c
               for c in out["candidate_results"])
