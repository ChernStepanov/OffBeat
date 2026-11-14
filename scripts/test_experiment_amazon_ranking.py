"""Regression checks for event-window ranks, masks, and grid safeguards."""
import json

import numpy as np
import pytest

from scripts import experiment_amazon_ranking as experiment


def test_real_amazon_exact_rank_medians_residuals_and_shared_population():
    result = experiment.run()
    expected = {
        "hh": [(1, -2.584113644159677, -7.763805203965466),
               (1, -2.6260723652132807, -7.721846482911863),
               (1, -1.3878964494193617, -8.960022398705782)],
        "hv": [(36, -3.999547859245185, -3.420514325523982),
               (5, -2.2753470084085876, -5.144715176360579),
               (3, -1.1132413651665845, -6.306820819602582)],
    }
    populations = []
    for pol, rows in expected.items():
        for radius, (rank, median, residual) in zip(("3x3", "5x5", "9x9"), rows):
            record = result["sensitivities"][pol][radius]
            assert record["target_rank_most_negative_first"] == rank
            assert record["target_paired_neighbor_count"] == {"3x3": 5, "5x5": 12, "9x9": 30}[radius]
            assert record["target_neighbor_median_db"] == pytest.approx(median, abs=1e-12)
            assert record["target_residual_db"] == pytest.approx(residual, abs=1e-12)
            populations.append(record["eligible_class_pixels"])
    assert populations == [543, 570, 575, 543, 570, 575]
    assert [result["sensitivities"]["hv"][r]["target_rank_most_negative_first"]
            for r in ("3x3", "5x5", "9x9")] == [36, 5, 3]


def test_north_checkpoint_separates_observation_validity_from_class_eligibility():
    north = experiment.run()["checkpoints"]["north"]
    assert north["worldcover_code"] == 30
    for pol, expected_change in (("hh", 2.9478), ("hv", -2.3930)):
        row = north["event_window"][pol]["5x5"]
        assert row["valid_observation_pair"] is True
        assert row["matches_target_worldcover_class"] is False
        assert row["valid_class_pair"] is False
        assert row["raw_change_db"] == pytest.approx(expected_change, abs=0.0001)
        assert row["paired_neighbors"] is None
        assert row["neighbor_median_db"] is None
        assert row["residual_db"] is None


def test_self_exclusion_and_minimum_peer_threshold_on_synthetic_values():
    delta = np.array([[100., 1.], [3., 5.]])
    paired = np.ones((2, 2), dtype=bool)
    residual, count, median = experiment.relative_residuals(delta, paired, radius=1, min_peers=3)
    assert count[0, 0] == 3
    assert median[0, 0] == 3.0  # target's 100 is excluded
    assert residual[0, 0] == 97.0
    paired[1, 1] = False
    residual, count, median = experiment.relative_residuals(delta, paired, radius=1, min_peers=3)
    assert count[0, 0] == 2
    assert np.isnan(residual[0, 0]) and np.isnan(median[0, 0])


def test_masks_and_future_values_cannot_change_event_ranks(monkeypatch):
    mask = np.array([1, 0, 255, 1, 1])
    hh = np.array([2., 2., 2., np.nan, 2.])
    hv = np.array([3., 3., 3., 3., 0.])
    assert experiment.valid_observations(mask, hh, hv).tolist() == [True, False, False, False, False]

    original = experiment.load_data()
    baseline = experiment.run()
    dates, stacks, valid, cover = original
    altered = {pol: stack.copy() for pol, stack in stacks.items()}
    for pol in altered:
        altered[pol][dates.index("2026-09-16"):] += 1000
    monkeypatch.setattr(experiment, "load_data", lambda: (dates, altered, valid, cover))
    changed = experiment.run()
    assert changed["sensitivities"] == baseline["sensitivities"]
    for name in baseline["checkpoints"]:
        assert changed["checkpoints"][name]["event_window"] == baseline["checkpoints"][name]["event_window"]
    assert changed["checkpoints"]["candidate"]["followup"] != baseline["checkpoints"]["candidate"]["followup"]


def test_exact_grid_alignment_and_sar_metadata_are_required():
    ref = {"lat": np.array([[1., 2.]]), "lon": np.array([[3., 4.]])}
    shifted = {"lat": ref["lat"].copy(), "lon": ref["lon"].copy()}
    shifted["lat"][0, 0] += 1e-6
    with pytest.raises(ValueError, match="shifted on 2026-09-04"):
        experiment.require_aligned(ref, shifted, "2026-09-04")
    with pytest.raises(ValueError, match="shape mismatch"):
        experiment.require_aligned(ref, {"lat": np.zeros((2, 1)), "lon": np.zeros((2, 1))}, "2026-09-04")

    meta = json.loads((experiment.SERIES / "2026-08-23.json").read_text())
    same = json.loads(json.dumps(meta))
    experiment.require_compatible_metadata(meta, same, "2026-09-04")
    incompatible = json.loads(json.dumps(same))
    incompatible["grid"]["epsg"] += 1
    with pytest.raises(ValueError, match="Incompatible SAR/grid metadata"):
        experiment.require_compatible_metadata(meta, incompatible, "2026-09-04")


def test_captured_json_matches_current_reproducible_result():
    path = experiment.ROOT / "data/amazon-ranking-experiment.json"
    assert json.loads(path.read_text()) == experiment.run()


def test_fixed_event_window_and_followup_are_distinct():
    result = experiment.run()
    assert result["event_window"] == [experiment.BEFORE, experiment.AFTER]
    assert result["ranking_uses_only_event_window"] is True
    assert result["followup_dates_excluded_from_ranking"] == ["2026-09-16", "2026-09-28"]
    assert experiment.window_indices(["2026-08-23", "2026-09-04", "2026-09-16"]) == (0, 1)


def test_point_payload_is_sampled_only_and_has_ranked_corrected_signals():
    result = experiment.run()
    points = result["points"]
    assert len(points) == 32 * 32
    target = next(p for p in points if (p["row"], p["col"]) == experiment.TARGET)
    signal = target["signals"]["hh"]["5x5"]
    assert signal["raw_change_db"] == pytest.approx(-10.347918848125143)
    assert signal["neighbor_median_db"] == pytest.approx(-2.6260723652132807)
    assert signal["residual_db"] == pytest.approx(-7.721846482911863)
    assert signal["rank"] == 1 and signal["rank_population"] == 570
    north = next(p for p in points if (p["row"], p["col"]) == (4, 15))
    assert north["valid_pair"] is True and north["worldcover_code"] == 30
    assert north["signals"]["hh"]["5x5"]["raw_change_db"] is not None
    assert north["signals"]["hh"]["5x5"]["residual_db"] is None
