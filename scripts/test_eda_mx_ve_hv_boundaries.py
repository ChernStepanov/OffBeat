import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("eda", ROOT / "scripts/eda_mx_ve_hv_boundaries.py")
eda = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(eda)


def test_median_ignores_non_numeric_and_nan():
    assert eda.med([1, "2", None, "bad", float("nan"), float("inf"), 3]) == 2
    assert eda.med([None, "bad", float("nan")]) is None


def test_exact_three_plus_three_and_peer_adjustment(tmp_path):
    dates = [f"d{i}" for i in range(7)]
    # Boundary d3: raw median change = 4; peer-relative change = 2.
    pix = {"hv": [0, 1, 2, 4, 5, 6, 999],
           "peer": {"hv_med": [0, 0, 0, 2, 2, 2, -999]}}
    pix2 = {"hv": [10, 11, 12, 14, 15, 16, -999],
            "peer": {"hv_med": [10, 10, 10, 12, 12, 12, 999]}}
    path = tmp_path / "fixture.json"
    path.write_text(json.dumps({"id": "fixture", "dates": dates, "pixels": [pix, pix2]}))
    result = eda.analyze_site(path, np.random.default_rng(33))
    assert len(result["boundaries"]) == 2
    b = next(x for x in result["boundaries"] if x["boundary"] == "d3")
    assert b["before_dates"] == ["d0", "d1", "d2"]
    assert b["after_dates"] == ["d3", "d4", "d5"]
    assert b["raw_change_median_db"] == 4
    assert b["peer_adjusted_change_median_db"] == 2
    assert b["peer_adjusted_abs_change_median_db"] == 2


def test_raw_rows_kept_when_peer_series_missing(tmp_path):
    dates = [f"d{i}" for i in range(6)]
    points = [{"hv": [0, 1, 2, 3, 4, 5], "peer": {"hv_med": [0, 0, 0, 0, 0, 0]}},
              {"hv": [10, 11, 12, 13, 14, 15]}]
    path = tmp_path / "missing-peer.json"
    path.write_text(json.dumps({"id": "fixture", "dates": dates, "pixels": points}))
    b = eda.analyze_site(path, np.random.default_rng(33))["boundaries"][0]
    assert b["n_raw"] == 2
    assert b["n_peer_adjusted"] == 1


def test_seeded_controls_and_current_expected_metrics():
    a, b = eda.run(), eda.run()
    assert a == b
    assert a["seed"] == 33 and a["training"] is False
    assert [s["id"] for s in a["sites"]] == ["mexico", "venezuela"]
    mexico = next(x for x in a["sites"][0]["boundaries"] if x["boundary"] == "2026-01-22")
    venezuela = a["sites"][1]["boundaries"][0]
    assert mexico["raw_change_median_db"] == pytest.approx(-3.805605)
    assert mexico["peer_adjusted_abs_change_median_db"] == pytest.approx(1.754, abs=0.001)
    assert mexico["site_median_contrast_after_minus_before_db"] == pytest.approx(-3.494355)
    assert venezuela["raw_change_median_db"] == pytest.approx(-5.03975)
    assert venezuela["peer_adjusted_abs_change_median_db"] == pytest.approx(1.505, abs=0.001)
    assert venezuela["site_median_contrast_after_minus_before_db"] == pytest.approx(-5.871735)
    assert 0 < mexico["low_change_control_n"] <= mexico["n_raw"]
    assert mexico["random_control_abs_change_median_db"] > 0


def test_saved_json_matches_recomputed_result_and_event_warning():
    saved = json.loads((ROOT / "data/mexico-venezuela-hv-boundary-eda.json").read_text())
    assert saved == eda.run()
    warnings = " ".join(saved["warnings"])
    assert "us6000t7zp" in warnings and "No event match" in warnings
    assert "not directly comparable" in warnings
