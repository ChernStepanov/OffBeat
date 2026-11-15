#!/usr/bin/env python3
"""Build the bilingual research-page payload from the checked-in analysis receipts."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUT = Path("data/research/results.json")


def bi(ru: str, en: str) -> dict[str, str]:
    return {"ru": ru, "en": en}


def fmt_int(value: int, *, ru: bool = False) -> str:
    return f"{value:,}".replace(",", "\u202f" if ru else ",")


def fmt_float(value: float, digits: int, *, ru: bool = False) -> str:
    result = f"{value:.{digits}f}"
    return result.replace(".", ",") if ru else result


def column(key: str, ru: str, en: str, **formatting: Any) -> dict[str, Any]:
    return {"key": key, "label": bi(ru, en), **formatting}


def table(columns: list[dict[str, Any]], rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {"columns": columns, "rows": rows}


def source(path: str, label_ru: str, label_en: str, *, download: bool = False) -> dict[str, Any]:
    result: dict[str, Any] = {"label": bi(label_ru, label_en), "href": path}
    if download:
        result["download"] = True
    return result


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json(root: Path, rel: str) -> dict[str, Any]:
    with (root / rel).open(encoding="utf-8") as stream:
        return json.load(stream)


def build_report(root: Path = ROOT) -> dict[str, Any]:
    cross_path = Path("data/research/cross-sensor.json")
    spatial_path = Path("data/research/spatial-robustness.json")
    cross = load_json(root, str(cross_path))
    spatial = load_json(root, str(spatial_path))

    forest = spatial["persistence_reversion"]
    trajectory_dates = ["2026-09-04", "2026-09-16", "2026-09-28"]
    trajectory_series = []
    for band in ("HH", "HV"):
        trajectory_series.append({
            "label": band,
            "values": [
                {"label": date[5:], "value": forest[date][band]["median"]}
                for date in trajectory_dates
            ],
        })
    trajectory_rows = [
        {"date": date, "HH": forest[date]["HH"]["median"], "HV": forest[date]["HV"]["median"]}
        for date in trajectory_dates
    ]

    hv = cross["analyses"]["HV_vs_VH"]
    hh = cross["analyses"]["HH_vs_VV"]
    correlation_values = [
        hv["pooled_level_correlation"],
        hv["within_class_and_date_centered_correlation"],
        hv["consecutive_matched_change_correlation"],
    ]
    estimator = spatial["scale_and_nonlinearity_ablation"]["per_band"]["HV"]
    dB_median = estimator["median_of_date_dB_difference"]
    linear_ratio = estimator["dB_of_linear_mean_ratio"]

    scale_rows = []
    scale_points = []
    for item in spatial["scale_and_nonlinearity_ablation"]["spatial_median_windows"]:
        scale_rows.append({
            "scale": item["window_m"],
            "HH": item["HH_delta"]["median"],
            "HV": item["HV_delta"]["median"],
            "joint_fraction": item["both_bands_le_minus_3db_fraction"] * 100,
        })
        scale_points.append({"label": str(item["window_m"]), "value": item["both_bands_le_minus_3db_fraction"] * 100})

    threshold_rows = [
        {
            "threshold": item["threshold_db"],
            "soft_count": item["forest_cells_both_bands_at_least_2_of_3_post_dates"],
            "soft_percent": item["forest_fraction"] * 100,
            "late_count": item["forest_cells_both_bands_below_threshold_on_both_2026_09_16_and_2026_09_28"],
        }
        for item in spatial["threshold_sweep"]
    ]

    pair_entries = cross["matching"]["by_tolerance_days"]["6"]
    timestamp_entries = cross["matching"]["nearest_12d_class_series"]["HV_vs_VH"]["per_date_nearest_12d"]
    hourly_ranges = [
        value
        for entry in timestamp_entries
        for value in entry["catalogue_granule_utc_lag_hours_range"]
    ]
    lag_low, lag_high = min(hourly_ranges), max(hourly_ranges)
    pair_rows = []
    for entry in pair_entries:
        date_record = next(x for x in timestamp_entries if x["nisar_date"] == entry["nisar_date"])
        date_low, date_high = date_record["catalogue_granule_utc_lag_hours_range"]
        pair_rows.append({
            "nisar": entry["nisar_date"],
            "rtc": entry["rtc_date"],
            "lag": entry["lag_days_calendar"],
            "utc_range": bi(
                f"{fmt_float(date_low,3,ru=True)}…{fmt_float(date_high,3,ru=True)} ч · гранулы",
                f"{fmt_float(date_low,3)}…{fmt_float(date_high,3)} h · granules",
            ),
        })

    tolerances = cross["matching"]["by_tolerance_days"]
    threshold_three = next(item for item in spatial["threshold_sweep"] if item["threshold_db"] == 3)
    sample_counts = {
        "sparse": cross["metadata"]["coordinates"]["count"],
        "dense": spatial["matching"]["valid_cells"],
        "forest": spatial["quality"]["worldcover_forest_cells_class10"],
        "matched_dates": cross["summary"]["matched_unique_pairs_at_6d"],
    }

    cards = [
        {
            "label": bi("Лесная сетка · собственная база · 16 → 28 сентября", "Forest grid · own baseline · 16 → 28 September"),
            "values": [
                {"label": "HH · 16 Sep", "value": forest["2026-09-16"]["HH"]["median"]},
                {"label": "HV · 16 Sep", "value": forest["2026-09-16"]["HV"]["median"]},
                {"label": "HH · 28 Sep", "value": forest["2026-09-28"]["HH"]["median"]},
                {"label": "HV · 28 Sep", "value": forest["2026-09-28"]["HV"]["median"]},
            ],
            "unit": "dB",
            "note": bi("Медианы по всем ячейкам лесного класса, не по экстремально выбранным точкам.", "Medians across all forest-class cells, not extreme-value-selected points."),
        },
        {
            "label": bi("HV · выбор временной сводки меняет знак", "HV · temporal summary choice changes the sign"),
            "values": [
                {"label": bi("разность медиан дат", "difference of date medians"), "value": dB_median["median"]},
                {"label": bi("ratio средних power → dB", "ratio of mean power → dB"), "value": linear_ratio["median"]},
            ],
            "unit": "dB",
            "note": bi("Обе оценки по всей dense-сетке; это разные estimands, не выбор между «ложью» и истиной.", "Both estimates use the full dense grid; they are different estimands, not a choice between ‘wrong’ and truth."),
        },
        {
            "label": bi("Связь уровней сильнее связи изменений", "Levels associate more than changes"),
            "values": [
                {"label": bi("уровни", "levels"), "value": correlation_values[0]},
                {"label": bi("после центрирования", "after centering"), "value": correlation_values[1]},
                {"label": bi("последовательные изменения", "consecutive changes"), "value": correlation_values[2]},
            ],
            "unit": "r",
            "signed": False,
            "note": bi("NISAR HV / OPERA VH; описательная корреляция, не причинная связь.", "NISAR HV / OPERA VH; descriptive correlation, not a causal relationship."),
        },
    ]

    headline = bi(
        "Что выдерживает проверку: сопоставление радаров и устойчивость аномалий",
        "What withstands scrutiny: radar matching and anomaly robustness",
    )
    intro = bi(
        "По всей лесной части dense-сетки медианы HH и HV меняют знак между 16 и 28 сентября. Межсенсорные уровни связаны умеренно, а последовательные изменения — слабее. Способ сводки тоже меняет знак общей оценки HV. Это наблюдаемые ограничения кандидатов, не подтверждённые события.",
        "Across the dense-grid forest cells, HH and HV medians change sign between 16 and 28 September. Cross-sensor levels are moderately associated, while consecutive changes are less so. The aggregation choice also changes the sign of the overall HV estimate. These are observed limits on candidate interpretation, not confirmed events.",
    )

    return {
        "schema_version": 1,
        "headline": headline,
        "intro": intro,
        "summary": bi(
            "Один участок Амазонии, шесть дат NISAR; исследовательские результаты проверены, но не являются метками событий.",
            "One Amazon site and six NISAR dates; these are research findings, not event labels.",
        ),
        "dashboard_link": {"label": bi("Открыть участок Амазонии в dashboard", "Open Amazon in the dashboard"), "href": "index.html?site=amazon"},
        "cards": cards,
        "finding": {
            "summary": intro,
            "charts": [
                {
                    "title": bi("Лес: HH/HV относительно медианы первых трёх дат", "Forest: HH/HV relative to the first-three-date median"),
                    "series": trajectory_series,
                },
                {
                    "type": "bar",
                    "title": bi("NISAR L-band / Sentinel-1 C-band: корреляция уровней и изменений", "NISAR L-band / Sentinel-1 C-band: correlation of levels and changes"),
                    "labels": [bi("уровни", "levels"), bi("центрированные уровни", "centered levels"), bi("изменения", "changes")],
                    "series": [
                        {"label": "HV / VH", "values": [hv["pooled_level_correlation"], hv["within_class_and_date_centered_correlation"], hv["consecutive_matched_change_correlation"]]},
                        {"label": "HH / VV", "values": [cross["analyses"]["HH_vs_VV"]["pooled_level_correlation"], cross["analyses"]["HH_vs_VV"]["within_class_and_date_centered_correlation"], cross["analyses"]["HH_vs_VV"]["consecutive_matched_change_correlation"]]},
                    ],
                },
            ],
            "tables": [
                {"title": bi("Траектория по всем ячейкам WorldCover forest", "Trajectory across all WorldCover forest cells"),
                 "table": table([column("date","Дата","Date"),column("HH","HH · dB","HH · dB"),column("HV","HV · dB","HV · dB")],trajectory_rows),
                 "note": bi("База каждого пикселя — собственная медиана 18 июля, 11 и 23 августа; сетка 141×141, 20 м.", "Each pixel uses its own median from 18 July, 11 and 23 August; 141×141 grid at 20 m.")},
                {"title": bi("Корреляции HV/VH и HH/VV", "HV/VH and HH/VV correlations"),
                  "table": table([column("pair","Каналы","Channels"),column("levels","Уровни r","Levels r"),column("centered","Центрированные уровни r","Centered levels r"),column("changes","Изменения r","Changes r"),column("centered_changes","Центрированные изменения r","Centered changes r")],[
                      {"pair":"HV / VH","levels":hv["pooled_level_correlation"],"centered":hv["within_class_and_date_centered_correlation"],"changes":hv["consecutive_matched_change_correlation"],"centered_changes":hv["class_and_interval_centered_change_correlation"]},
                      {"pair":"HH / VV","levels":hh["pooled_level_correlation"],"centered":hh["within_class_and_date_centered_correlation"],"changes":hh["consecutive_matched_change_correlation"],"centered_changes":hh["class_and_interval_centered_change_correlation"]},
                  ]),
                  "note": bi("Центрирование уровней — по классу WorldCover и дате; центрирование изменений — по классу и интервалу. 6 144 point-date строки уровней и 5 120 парных точек-интервалов изменений — зависимые записи, не независимые события.", "Level centering is by WorldCover class and date; change centering is by class and interval. 6,144 level point-date rows and 5,120 paired point-interval change rows are dependent observations, not independent events.")},
                {"title": bi("Выбор временной сводки меняет знак HV по всей сетке", "Temporal summary choice changes the all-grid HV sign"),
                  "table": table([column("band","Поляризация","Polarization"),column("dB_median","Разность медиан дат, dB","Difference of date medians, dB",digits=4,signed=True),column("linear_ratio","dB отношения средних power","dB of mean-power ratio",digits=4,signed=True)],[
                      {"band":"HH","dB_median":spatial["scale_and_nonlinearity_ablation"]["per_band"]["HH"]["median_of_date_dB_difference"]["median"],"linear_ratio":spatial["scale_and_nonlinearity_ablation"]["per_band"]["HH"]["dB_of_linear_mean_ratio"]["median"]},
                      {"band":"HV","dB_median":dB_median["median"],"linear_ratio":linear_ratio["median"]},
                  ]),
                  "note": bi(f"Сначала для каждой ячейки: медиана трёх post-дат минус медиана трёх pre-дат в dB; затем пространственная медиана по n={fmt_int(dB_median['n'],ru=True)} dense-ячейкам. Это не медиана отдельных парных разностей. Оценки отвечают на разные вопросы.", f"First, per cell: median of three post dates minus median of three pre dates in dB; then the spatial median over n={fmt_int(dB_median['n'])} dense cells. This is not the median of paired date differences. The estimates answer different questions.")},
            ],
            "details":[
                {"title":bi("Контраст r уровней − r изменений и block-bootstrap CI", "Contrast r levels − r changes and block-bootstrap CI"),
                 "text":bi("Для HV/VH разность корреляций рассчитана в парном spatial block bootstrap: в каждом повторе уровни и изменения используют одни и те же spatial blocks. Интервал условен на данном участке и шести датах.", "For HV/VH, the correlation difference is estimated with paired spatial block bootstrap: each replicate uses the same spatial blocks for levels and changes. The interval is conditional on this site and six dates."),
                 "table":table([column("block","Блок, cells/side","Block, cells/side"),column("contrast","r уровни − изменения","r levels − changes",digits=3),column("lower","95% CI · нижняя","95% CI · lower",digits=3),column("upper","95% CI · верхняя","95% CI · upper",digits=3),column("blocks","Spatial blocks","Spatial blocks"),column("replicates","Валидных повторов","Valid replicates")],[
                     {"block":int(k),"contrast":v["point_estimates"]["contrast_r_levels_minus_r_changes"],"lower":v["ci95"]["contrast_r_levels_minus_r_changes"][0],"upper":v["ci95"]["contrast_r_levels_minus_r_changes"][1],"blocks":v["spatial_blocks"],"replicates":v["replicates_valid"]}
                     for k,v in sorted(hv["level_change_contrast_spatial_bootstrap"].items(),key=lambda item:int(item[0]))
                 ]),
                 "note":bi("Это пространственная неопределённость при фиксированных датах/участке, не временная или event-level репликация.", "This is spatial uncertainty conditional on dates/site, not temporal or event-level replication.")},
            ],
        },
        "evidence": {
            "strength": bi(
                f"Траектория рассчитана для всех {fmt_int(sample_counts['forest'],ru=True)} forest-ячеек dense-grid, а не для точек, выбранных по экстремуму. Cross-sensor корреляции используют проверенный общий порядок {fmt_int(sample_counts['sparse'],ru=True)} sparse sample-координат; matching и допуски дат приведены явно.",
                f"The trajectory uses all {fmt_int(sample_counts['forest'])} dense-grid forest cells, not points selected for an extreme value. Cross-sensor correlations use the checked common order of {fmt_int(sample_counts['sparse'])} sparse sample coordinates; matching and date tolerances are explicit.",
            ),
            "limitations": [
                bi("Один участок и шесть дат NISAR; соседние ячейки и point-date строки зависимы.", "One site and six NISAR dates; neighboring cells and point-date rows are dependent."),
                bi("NISAR GCOV provisional. WorldCover 2021 — историческая стратификация, а не актуальная наземная метка.", "NISAR GCOV is provisional. WorldCover 2021 is historical stratification, not a current ground label."),
                bi("NISAR — ascending, OPERA гранулы — descending; различаются геометрия, каналы и время съёмки. Это не изолированный эффект длины волны.", "NISAR is ascending and OPERA granules are descending; geometry, channels and acquisition time differ. This does not isolate wavelength effects."),
                bi("Нет source-granule, geometry и quality mask на уровне точки для OPERA RTC. Полнота маски NISAR 100% означает только прохождение заданного фильтра, не достоверность измерений.", "OPERA RTC has no per-point source-granule, geometry or quality mask. A 100% NISAR mask pass rate means only that the stated filter passed, not that measurements are trustworthy."),
                bi("Нет независимых меток событий: причинность, accuracy/recall и площадь подтверждённых событий не оценивались.", "There are no independent event labels: causation, accuracy/recall and confirmed event area were not evaluated."),
                bi("Падение числа кандидатов при сглаживании не означает, что удалились только false positives: фильтр может стереть небольшие реальные объекты.", "Fewer candidates after smoothing does not mean only false positives were removed: filtering can erase small real features."),
            ],
            "details": [
                {"title": bi("Что именно означает 100% валидных dense-ячеек", "What 100% valid dense cells means"), "text": bi(
                    f"Источник сообщает {fmt_int(spatial['quality']['valid_all_six_both_bands'],ru=True)}/{fmt_int(spatial['quality']['total_cells'],ru=True)} ячеек после применения сохранённых масок, конечности и положительной мощности на шести датах. Это покрытие данного фильтра в этом clipped subset; оно не подтверждает калибровку, геометрическую сопоставимость или отсутствие ошибок.",
                    f"The source reports {fmt_int(spatial['quality']['valid_all_six_both_bands'])}/{fmt_int(spatial['quality']['total_cells'])} cells passing the saved-mask, finite-value and positive-power checks on all six dates. This is coverage under that filter in this clipped subset; it does not verify calibration, geometric comparability or absence of errors.",
                )},
            ],
        },
        "matching": {
            "summary": bi(
                f"При допуске {cross['method']['primary_tolerance_days']} дней найдены {fmt_int(len(pair_entries),ru=True)} уникальных пар; все OPERA даты на один календарный день раньше NISAR. Каталожные burst-времена дают общий диапазон примерно {fmt_float(lag_low,1,ru=True)}…{fmt_float(lag_high,1,ru=True)} часа (около −24,1 ч), но это не время вклада каждого пикселя.",
                f"At a {cross['method']['primary_tolerance_days']}-day tolerance, {fmt_int(len(pair_entries))} unique pairs were found; every OPERA date is one calendar day before NISAR. Catalogue burst times span about {fmt_float(lag_low,1)} to {fmt_float(lag_high,1)} hours (about −24.1 h), but do not identify each pixel’s contributing acquisition time.",
            ),
            "table": table([column("nisar","Дата NISAR","NISAR date"),column("rtc","Дата OPERA","OPERA date"),column("lag","Календарный лаг, дни","Calendar lag, days"),column("utc_range","Каталожный UTC lag, ч","Catalogue UTC lag range, h")],pair_rows),
            "details": [
                {"title": bi("Разные выборки и support — counts не складывать", "Different samples and support — do not combine counts"),
                 "text": bi("Cross-sensor matching использует sparse sample points. Spatial robustness анализирует отдельную dense-сетку. Sparse и dense геометрии не соединялись и не задают общий знаменатель.", "Cross-sensor matching uses sparse sample points. Spatial robustness analyzes a separate dense grid. Sparse and dense geometries were not joined and do not share a denominator."),
                 "table": table([column("design","Дизайн","Design"),column("support","Поддержка","Support"),column("count","Размер","Count")],[
                     {"design":bi("Cross-sensor NISAR/OPERA","Cross-sensor NISAR/OPERA"),"support":bi("sparse, общий ordered-coordinate hash","sparse, shared ordered-coordinate hash"),"count":sample_counts["sparse"]},
                     {"design":bi("NISAR temporal robustness","NISAR temporal robustness"),"support":bi("dense 141×141 native grid, 20 м","dense 141×141 native grid, 20 m"),"count":sample_counts["dense"]},
                 ])},
                {"title": bi("Чувствительность числа matched dates к допуску", "Matched-date count by temporal tolerance"),
                 "table": table([column("tolerance","Допуск, дни","Tolerance, days"),column("count","Уникальных пар","Unique pairs")],[{"tolerance":int(k),"count":len(v)} for k,v in sorted(tolerances.items(),key=lambda x:int(x[0]))]),
                 "text": bi("Ноль пар при нулевом допуске — отсутствие календарного совпадения, а не отрицательный результат sensor comparison.", "Zero pairs at zero-day tolerance means no calendar-date match, not a negative sensor-comparison result.")},
                {"title": bi("Точность сопоставления и геометрия", "Matching precision and geometry"),
                 "items": [
                     bi("NISAR track 146 ascending; matched OPERA burst IDs относятся к descending Sentinel-1. Поляризации HV/VH и HH/VV не считаются эквивалентными.", "NISAR track 146 is ascending; matched OPERA burst IDs are descending Sentinel-1. HV/VH and HH/VV are not treated as equivalent."),
                     bi("UTC lag рассчитан по гранулам каталога; неизвестно, какой burst заполнил конкретную точку.", "UTC lag comes from catalogue granules; the burst contributing to each point is unknown."),
                     bi("RTC JSON не содержит per-point source granule или quality/geometry mask; finite value не равен quality-checked observation.", "RTC JSON contains no per-point source granule or quality/geometry mask; a finite value is not a quality-checked observation."),
                 ]},
            ],
        },
        "ablations": {
            "summary": bi(
                f"При пороге 3 dB: {threshold_three['forest_cells_both_bands_at_least_2_of_3_post_dates']} ячейки по правилу ≥2/3 для каждой поляризации отдельно против {threshold_three['forest_cells_both_bands_below_threshold_on_both_2026_09_16_and_2026_09_28']} при требовании обеих поздних дат. При сглаживании кандидатов меньше, но малые реальные объекты тоже могут исчезнуть.",
                f"At a 3 dB threshold: {threshold_three['forest_cells_both_bands_at_least_2_of_3_post_dates']} cells under ≥2/3 for each polarization independently versus {threshold_three['forest_cells_both_bands_below_threshold_on_both_2026_09_16_and_2026_09_28']} requiring both late dates. Smoothing reduces candidates, but can also erase small real features.",
            ),
            "charts": [{
                "type":"bar",
                "title":bi("Совместная доля лесных ячеек с HH и HV ≤ −3 dB по окну сглаживания", "Joint forest fraction with HH and HV ≤ −3 dB by smoothing window"),
                "labels":[str(x["window_m"]) for x in spatial["scale_and_nonlinearity_ablation"]["spatial_median_windows"]],
                "series":[{"label":bi("Доля forest, %","Forest fraction, %"),"values":scale_points}],
            }],
            "tables": [{
                "title":bi("Пространственный масштаб: медианные сдвиги и доля совместного −3 dB критерия", "Spatial scale: median shifts and joint −3 dB criterion fraction"),
                "table":table([column("scale","Окно, м","Window, m"),column("HH","HH медиана, dB","HH median, dB"),column("HV","HV медиана, dB","HV median, dB"),column("joint_fraction","HH и HV ≤ −3 dB, % forest","HH and HV ≤ −3 dB, % forest")],scale_rows),
                "note":bi("Падение частоты кандидатов при сглаживании не доказывает удаление ложных срабатываний: малые реальные объекты тоже могут исчезать.", "Fewer candidates after smoothing does not prove false positives were removed: small real features can also disappear."),
            }],
            "details":[
                {"title":bi("Порог и persistence — два разных правила подсчёта", "Threshold and persistence are two different counting rules"),
                  "text":bi("Мягкое правило: каждая поляризация отдельно ниже собственной pre-period базы на заданный порог минимум в 2 из 3 дат 4/16/28 сентября; HH и HV не обязаны проходить критерий в одни и те же даты. Строгое late persistence требует выполнения критерия и 16, и 28 сентября. Это retrospective candidates, не false/true event labels.", "Soft rule: each polarization independently falls below its own pre-period baseline by the threshold on at least 2 of 3 dates (4/16/28 September); HH and HV need not pass on the same dates. Strict late persistence requires the condition on both 16 and 28 September. These are retrospective candidates, not false/true event labels."),
                 "table":table([column("threshold","Порог, dB","Threshold, dB"),column("soft_count","≥2 из 3: ячеек","≥2 of 3: cells"),column("soft_percent","≥2 из 3: % forest","≥2 of 3: % forest"),column("late_count","16 и 28 Sep: ячеек","16 and 28 Sep: cells")],threshold_rows),
                 "note":bi(f"При 3 dB: {threshold_three['forest_cells_both_bands_at_least_2_of_3_post_dates']} ячейки по мягкому правилу против {threshold_three['forest_cells_both_bands_below_threshold_on_both_2026_09_16_and_2026_09_28']} по late persistence. Счётчики используют те же post-даты, независимого temporal holdout нет.", f"At 3 dB: {threshold_three['forest_cells_both_bands_at_least_2_of_3_post_dates']} cells under the soft rule versus {threshold_three['forest_cells_both_bands_below_threshold_on_both_2026_09_16_and_2026_09_28']} under late persistence. Counts use the same post dates; there is no independent temporal holdout.")},
                {"title":bi("Выбор временной сводки и знак all-grid HV", "Temporal summary choice and the all-grid HV sign"),
                  "text":bi("Первая оценка: для каждой ячейки медиана трёх post-дат минус медиана трёх pre-дат в dB, затем пространственная медиана этих ячеечных значений. Это не медиана отдельных парных разностей. Вторая оценка — dB отношения средних линейных мощностей. Это разные estimands; ни один не выбран как ground truth.", "First estimate: for each cell, median of three post dates minus median of three pre dates in dB, followed by the spatial median across cells. This is not the median of paired date differences. The second estimate is dB of the ratio of mean linear powers. These are distinct estimands; neither is selected as ground truth."),
                   "table":table([column("band","Поляризация","Polarization"),column("dB_median","Разность медиан дат, dB","Difference of date medians, dB",digits=4,signed=True),column("linear_ratio","dB отношения средних power","dB of mean-power ratio",digits=4,signed=True),column("n","Dense cells","Dense cells")],[
                      {"band":"HH","dB_median":spatial["scale_and_nonlinearity_ablation"]["per_band"]["HH"]["median_of_date_dB_difference"]["median"],"linear_ratio":spatial["scale_and_nonlinearity_ablation"]["per_band"]["HH"]["dB_of_linear_mean_ratio"]["median"],"n":dB_median["n"]},
                      {"band":"HV","dB_median":dB_median["median"],"linear_ratio":linear_ratio["median"],"n":linear_ratio["n"]},
                  ])},
            ],
        },
        "sources": [
            source("docs/research-cross-sensor.md","Отчёт: cross-sensor matching","Report: cross-sensor matching"),
            source("docs/research-spatial-robustness.md","Отчёт: spatial robustness","Report: spatial robustness"),
            source("docs/research-protocol.md","Протокол исследования","Research protocol"),
            source("docs/research-summary.md","Сводный синтез","Research synthesis"),
            source(str(cross_path),"Исходный JSON: cross-sensor","Raw JSON: cross-sensor",download=True),
            source(str(spatial_path),"Исходный JSON: spatial robustness","Raw JSON: spatial robustness",download=True),
            source("index.html?site=amazon","Dashboard: участок Амазонии","Dashboard: Amazon site"),
        ],
        "reproducibility": {
            "summary":bi("Генератор offline: читает два сохранённых результата анализа, извлекает метрики/пары, вычисляет сводные проценты и SHA-256 входных JSON. Числа на странице не поддерживаются отдельной ручной копией.", "The generator is offline: it reads the two saved analysis outputs, extracts metrics/pairs, computes summary percentages and SHA-256 hashes of the input JSON. Page values are not maintained as a separate hand-copied set."),
            "commands":[
                {"label":bi("Собрать страницу","Build page data"),"command":"python3 scripts/build_research_page.py"},
                {"label":bi("Проверить generator","Test generator"),"command":"python3 -m pytest scripts/test_build_research_page.py -q"},
                {"label":bi("Повторить cross-sensor анализ","Re-run cross-sensor analysis"),"command":"python scripts/research_cross_sensor.py"},
                {"label":bi("Повторить spatial robustness","Re-run spatial robustness"),"command":"python scripts/research_spatial_robustness.py"},
            ],
            "details":[{"title":bi("Входные JSON и SHA-256","Input JSON files and SHA-256"),"table":table([column("path","Файл","File"),column("sha256","SHA-256","SHA-256")],[
                {"path":str(cross_path),"sha256":sha256(root/cross_path)},
                {"path":str(spatial_path),"sha256":sha256(root/spatial_path)},
            ])}],
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default=str(OUT), help="Output path relative to repository root")
    args = parser.parse_args()
    target = ROOT / args.output
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(build_report(ROOT), ensure_ascii=False, indent=2) + "\n"
    target.write_text(payload, encoding="utf-8")
    print(f"Wrote {target.relative_to(ROOT)} ({len(payload)} bytes)")


if __name__ == "__main__":
    main()
