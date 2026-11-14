"""Tests for the standalone Amazon SAR EDA; does not alter production pipeline."""
import numpy as np

from scripts.eda_amazon_sar import MIN_CORRELATION_N, neighbour_control, pearson, require_aligned, require_compatible_metadata, run, valid_observations


def test_correlation_requires_minimum_pairwise_sample():
    assert pearson(range(6), range(6)) is None
    assert abs(pearson(range(MIN_CORRELATION_N), range(MIN_CORRELATION_N)) - 1.0) < 1e-12


def test_amazon_target_and_paired_neighbour_controls():
    result = run()
    assert result["target"]["row"] == 5 and result["target"]["col"] == 15
    assert result["target"]["worldcover_code"] == 10
    event = result["event_comparison"]
    assert event["hv"]["raw_target_change_db"] < -7
    for pol in ("hh", "hv"):
        assert event[pol]["dates"] == ["2026-08-23", "2026-09-04"]
        for radius in ("same_class_3x3", "same_class_5x5", "same_class_9x9"):
            control = event[pol]["neighbour_controls"][radius]
            assert control["n_paired"] > 0
            assert control["median_corrected_target_change_db"] is not None
    # Exercise paired_median through the same function used by run(), against
    # the real event stack and its target-excluded neighborhood.
    assert abs(event["hv"]["neighbour_controls"]["same_class_3x3"]["median_individual_change_db"] - -4.0) < 0.001


def test_validity_excludes_zero_255_and_missing_for_every_channel():
    mask = np.array([1, 0, 255, 1, 1])
    hh = np.array([2., 2., 2., np.nan, 2.])
    hv = np.array([3., 3., 3., 3., 0.])
    assert valid_observations(mask, hh, hv).tolist() == [True, False, False, False, False]


def test_exact_median_pairing_and_candidate_exclusion():
    before = np.array([[0., 10.], [20., 30.]])
    after = before + np.array([[100., 1.], [3., 5.]])
    ok = np.ones((2, 2), bool)
    candidates = np.ones((2, 2), bool)
    candidates[0, 0] = False  # target excluded, despite its extreme change
    stack = np.stack([before, after])
    valid = np.stack([ok, ok])
    assert neighbour_control(stack, valid, 0, 1, candidates)["median_individual_change_db"] == 3.
    ok_after = ok.copy()
    ok_after[1, 1] = False
    valid[1] = ok_after
    assert neighbour_control(stack, valid, 0, 1, candidates)["median_individual_change_db"] == 2.


def test_shifted_coordinates_are_not_exactly_aligned():
    reference = {"lat": np.array([[1., 2.], [3., 4.]]), "lon": np.zeros((2, 2))}
    shifted = {"lat": reference["lat"].copy(), "lon": reference["lon"].copy()}
    shifted["lat"][0, 0] += 1e-6
    import pytest
    with pytest.raises(ValueError, match="shifted on 2026-09-04"):
        require_aligned(reference, shifted, "2026-09-04")


def test_incompatible_grid_metadata_is_rejected_for_every_series_date():
    import json
    from pathlib import Path
    import pytest
    series = Path(__file__).resolve().parents[1] / "data/subsets/amazon-series"
    sidecars = sorted(series.glob("*.json"))
    reference = json.loads(sidecars[0].read_text())
    for sidecar in sidecars[1:]:
        actual = json.loads(sidecar.read_text())
        incompatible = json.loads(json.dumps(actual))
        incompatible["grid"]["epsg"] += 1
        with pytest.raises(ValueError, match=f"Incompatible SAR/grid metadata on {actual['date']}"):
            require_compatible_metadata(reference, incompatible, actual["date"])
