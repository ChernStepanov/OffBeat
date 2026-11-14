import hashlib
import json
from pathlib import Path
from datetime import date
from shapely import make_valid
from shapely.geometry import Point, Polygon

from scripts.audit_amazon_external_v2 import ROOT, SCL_LABELS, nearest_clear_scl_4_or_5, relation


def test_scl_distinguishes_cloud_shadow_not_vegetated_from_vegetation():
    assert SCL_LABELS[4] == "vegetation"
    assert SCL_LABELS[5] == "not_vegetated"
    assert SCL_LABELS[3] == "cloud_shadow"
    assert SCL_LABELS[8].startswith("cloud_") and SCL_LABELS[9].startswith("cloud_")


def test_fixed_date_window_relations_are_not_relabelled_as_confirmation():
    assert relation(date(2026, 7, 23)) == "before_fixed_window"
    assert relation(date(2026, 7, 24)) == "window_or_sar_boundary_calendar_day_time_ambiguous"
    assert relation(date(2026, 8, 23)) == "window_or_sar_boundary_calendar_day_time_ambiguous"
    assert relation(date(2026, 8, 24)) == "between_sar_dates"
    assert relation(date(2026, 9, 4)) == "window_or_sar_boundary_calendar_day_time_ambiguous"
    assert relation(date(2026, 9, 5)) == "post_pair_window"
    assert relation(date(2026, 10, 4)) == "window_or_sar_boundary_calendar_day_time_ambiguous"
    assert relation(date(2026, 10, 5)) == "after_fixed_window"


def test_make_valid_and_covers_includes_polygon_boundary():
    bowtie = Polygon([(0, 0), (2, 2), (0, 2), (2, 0), (0, 0)])
    assert not bowtie.is_valid
    fixed = make_valid(bowtie)
    assert fixed.is_valid
    assert fixed.covers(Point(1, 0))  # boundary belongs to geometry under covers


def test_quality_tie_breaks_scl_4_and_5_equally_by_time_then_stable_fields():
    inventory = [
        {"pixel_value": 5, "seconds_from_sar_reference": -3600,
         "datetime": "2026-09-04T08:04:00Z", "item_id": "earlier-class-5"},
        {"pixel_value": 4, "seconds_from_sar_reference": 3600,
         "datetime": "2026-09-04T10:04:00Z", "item_id": "later-class-4"},
        {"pixel_value": 8, "seconds_from_sar_reference": 10,
         "datetime": "2026-09-04T09:04:10Z", "item_id": "cloud"},
    ]
    assert nearest_clear_scl_4_or_5(inventory)["item_id"] == "earlier-class-5"


def test_saved_full_inventory_hashes_geometry_repairs_and_revised_points():
    path = ROOT / "data/amazon-spatial-external-audit-v2.json"
    out = json.loads(path.read_text())
    s2 = out["sentinel2"]
    assert s2["catalog_search"]["point_queries"] == 20
    assert s2["catalog_search"]["pagination_followed"]
    assert len(s2["results_by_row_col"]) == 10
    for row in s2["results_by_row_col"].values():
        assert len(row["inventory"]["pre"]) == 9
        assert len(row["inventory"]["post"]) == 9
    assert s2["broad_2026-08-14_to_2026-09-21_comparison"]["interpretation"].startswith("explicitly wider")
    p173 = s2["results_by_row_col"]["17,3"]
    assert [x["pixel_value"] for x in p173["inventory"]["post"]] == [8, 9, 8, 8, 5, 10, 4, 9, 8]
    assert p173["posthoc_nearest_clear_scl_4_or_5"]["post"]["pixel_value"] == 5
    assert p173["posthoc_nearest_clear_scl_4_or_5"]["post"]["datetime"].startswith("2026-09-21")
    old = s2["previous_selection_broad_pair_crosscheck"]["results_by_row_col"]
    assert [old[k]["post"]["pixel_value"] for k in
            ("5,15", "12,20", "11,10", "13,7", "19,13", "26,16", "26,26", "15,28", "0,6", "17,21")] == [5, 5, 4, 4, 4, 4, 4, 4, 5, 5]
    for c in old.values():
        assert [c["scl_by_scene_date"][day]["pixel_value"] for day in
                ("2026-08-02", "2026-08-04", "2026-08-14")] == [4, 4, 4]
    assert out["local_glad_deter_alerts"]["feature_count"] == 373
    assert out["local_glad_deter_alerts"]["invalid_geometry_count"] == 200
    repairs = out["local_glad_deter_alerts"]["invalid_geometry_repairs"]
    assert len(repairs) == 200 and all(r["repair_valid"] for r in repairs)
    assert not any(r["feature_geometry_covers_point_including_boundary"]
                   for r in out["local_glad_deter_alerts"]["records_within_2km"])
    assert out["inpe_deter"]["pagination_complete_by_number_matched"]
    for page in s2["catalog_search"]["pages"] + out["inpe_deter"]["pagination_pages"]:
        raw = ROOT / page["raw_response_path"]
        assert raw.exists()
        assert hashlib.sha256(raw.read_bytes()).hexdigest() == page["sha256"]
