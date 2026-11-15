"""Tests for bounded external-map processing."""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("external_maps", ROOT / "scripts/investigate_external_maps.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_web_tile_is_deterministic_for_amazon_center():
    assert module.web_tile(-49.275, -4.775, 12) == (1487, 2102)


def test_generated_layer_matches_full_native_grid_and_has_candidate_join():
    import json
    import numpy as np
    result = json.loads((ROOT / "data/investigation/external-maps.json").read_text())
    grid = result["native_grid"]
    arrays = np.load(ROOT / result["derived"]["path"])
    assert arrays["elevation_m"].shape == tuple(grid["shape"]) == (141, 141)
    assert arrays["slope_deg"].shape == (141, 141)
    assert arrays["longitude"].shape == arrays["latitude"].shape == tuple(grid["shape"])
    assert result["derived"]["valid_elevation_cells"] == 141 * 141
    assert {p["id"] for p in result["candidate_matches"]} >= {"candidate-01", "control-04"}
    assert all(p["elevation_m"] is not None for p in result["candidate_matches"])
    points = {p["id"]: p for p in result["candidate_matches"]}
    assert [points[f"candidate-0{i}"]["worldcover_2021_class"] for i in range(1, 5)] == [10, 30, 30, 10]
    assert all(points[f"control-0{i}"]["worldcover_2021_class"] == 10 for i in range(1, 5))
    # Lossyear code 0 is a valid value, not source nodata.
    assert points["candidate-02"]["lossyear_code"] == 0
    assert points["candidate-03"]["lossyear_code"] == 0
    assert result["forest_change"]["grid_and_sample_stats_separate"]["all_native_grid"]["n_native_cells"] == 19881
    forest = np.load(ROOT / result["forest_change"]["path"])
    assert not np.any(forest["lossyear"] == 255)
    assert forest["longitude"].shape == forest["latitude"].shape == tuple(grid["shape"])
