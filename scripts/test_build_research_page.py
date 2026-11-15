import hashlib
import json

from scripts.build_research_page import ROOT, build_report


def read(relative):
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def test_report_values_are_derived_from_the_checked_in_numeric_results():
    report = build_report(ROOT)
    cross = read("data/research/cross-sensor.json")
    spatial = read("data/research/spatial-robustness.json")

    forest = spatial["persistence_reversion"]
    rebound = report["cards"][0]["values"]
    assert [item["value"] for item in rebound] == [
        forest["2026-09-16"]["HH"]["median"],
        forest["2026-09-16"]["HV"]["median"],
        forest["2026-09-28"]["HH"]["median"],
        forest["2026-09-28"]["HV"]["median"],
    ]
    assert report["cards"][1]["values"][0]["value"] == spatial["scale_and_nonlinearity_ablation"]["per_band"]["HV"]["median_of_date_dB_difference"]["median"]
    assert report["cards"][1]["values"][1]["value"] == spatial["scale_and_nonlinearity_ablation"]["per_band"]["HV"]["dB_of_linear_mean_ratio"]["median"]
    assert report["cards"][2]["values"][0]["value"] == cross["analyses"]["HV_vs_VH"]["pooled_level_correlation"]


def test_sparse_and_dense_sample_designs_stay_separate():
    report = build_report(ROOT)
    details = report["matching"]["details"][0]
    counts = [row["count"] for row in details["table"]["rows"]]
    assert counts == [
        read("data/research/cross-sensor.json")["metadata"]["coordinates"]["count"],
        read("data/research/spatial-robustness.json")["matching"]["valid_cells"],
    ]
    assert counts[0] != counts[1]


def test_all_threshold_rows_and_matching_lags_come_from_sources():
    report = build_report(ROOT)
    spatial = read("data/research/spatial-robustness.json")
    cross = read("data/research/cross-sensor.json")
    threshold_detail = report["ablations"]["details"][0]
    assert [row["soft_count"] for row in threshold_detail["table"]["rows"]] == [
        row["forest_cells_both_bands_at_least_2_of_3_post_dates"]
        for row in spatial["threshold_sweep"]
    ]
    assert [row["lag"] for row in report["matching"]["table"]["rows"]] == [
        row["lag_days_calendar"] for row in cross["matching"]["by_tolerance_days"]["6"]
    ]
    soft_rule = threshold_detail["text"]["en"]
    assert "need not pass on the same dates" in soft_rule


def test_precise_mean_ratio_and_paired_contrast_are_included():
    report = build_report(ROOT)
    spatial = read("data/research/spatial-robustness.json")
    cross = read("data/research/cross-sensor.json")
    estimator_rows = report["finding"]["tables"][2]["table"]["rows"]
    hh = spatial["scale_and_nonlinearity_ablation"]["per_band"]["HH"]
    assert estimator_rows[0]["linear_ratio"] == hh["dB_of_linear_mean_ratio"]["median"]
    assert report["finding"]["tables"][2]["table"]["columns"][2]["digits"] == 4
    assert report["finding"]["tables"][2]["table"]["columns"][1]["label"] == {
        "ru": "Разность медиан дат, dB", "en": "Difference of date medians, dB"
    }
    assert "пространственная медиана" in report["finding"]["tables"][2]["note"]["ru"]
    assert "spatial median" in report["finding"]["tables"][2]["note"]["en"]
    assert "Медиана разностей dB" not in json.dumps(report, ensure_ascii=False)
    matching_columns = report["matching"]["table"]["columns"]
    assert matching_columns[0]["label"] == {"ru": "Дата NISAR", "en": "NISAR date"}
    assert matching_columns[1]["label"] == {"ru": "Дата OPERA", "en": "OPERA date"}
    contrast = report["finding"]["details"][0]["table"]["rows"]
    block4 = cross["analyses"]["HV_vs_VH"]["level_change_contrast_spatial_bootstrap"]["4"]
    assert contrast[1]["lower"] == block4["ci95"]["contrast_r_levels_minus_r_changes"][0]
    assert contrast[1]["upper"] == block4["ci95"]["contrast_r_levels_minus_r_changes"][1]


def test_hashes_and_generated_payload_are_deterministic():
    first = build_report(ROOT)
    second = build_report(ROOT)
    assert json.dumps(first, ensure_ascii=False, sort_keys=True) == json.dumps(second, ensure_ascii=False, sort_keys=True)
    for relative, item in zip(
        ("data/research/cross-sensor.json", "data/research/spatial-robustness.json"),
        first["reproducibility"]["details"][0]["table"]["rows"],
        strict=True,
    ):
        actual = hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()
        assert item["sha256"] == actual
