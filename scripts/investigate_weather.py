"""Exploratory matching of NISAR scene/class summaries to coarse ERA5 context.

Weather is an AOI-scale covariate, never a 20 m pixel measurement. Dates, not
pixels, are the independent units in temporal associations.
"""
from __future__ import annotations

import hashlib
import json
import argparse
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import requests
from scipy.stats import pearsonr, spearmanr

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data/investigation/weather-raw"
ARCHIVE = "https://archive-api.open-meteo.com/v1/archive"
HOURLY = ["soil_moisture_0_to_7cm", "soil_temperature_0_to_7cm",
          "soil_temperature_7_to_28cm", "temperature_2m", "wind_speed_10m"]
DAILY = ["precipitation_sum", "temperature_2m_mean", "wind_speed_10m_max"]
ARGS = argparse.Namespace(refresh=False)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def request_site(site: str, model: str, center: list[float], start: str, end: str):
    params = {"latitude": center[0], "longitude": center[1], "start_date": start,
              "end_date": end, "models": model, "timezone": "GMT",
              "daily": ",".join(DAILY)}
    if model == "era5_land":
        params["hourly"] = ",".join(HOURLY)
    name = f"{site}-{model}.json"
    RAW.mkdir(parents=True, exist_ok=True)
    rawpath = RAW / name
    prior_path = ROOT / "data/investigation/weather.json"
    if rawpath.exists() and prior_path.exists() and not ARGS.refresh:
        prior = json.loads(prior_path.read_text())
        provenance = next((p for p in prior.get("provenance", []) if p.get("raw_file") == str(rawpath.relative_to(ROOT))), None)
        if provenance and provenance.get("raw_sha256") == sha256(rawpath):
            return json.loads(rawpath.read_text()), provenance
    response = requests.get(ARCHIVE, params=params, timeout=90)
    rawpath.write_bytes(response.content)
    response.raise_for_status()
    data = response.json()
    return data, {"source": "Open-Meteo Historical Weather API; ECMWF " + model.upper(),
                  "endpoint": ARCHIVE, "query_url": response.url,
                  "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
                  "http_status": response.status_code, "raw_file": str(rawpath.relative_to(ROOT)),
                  "raw_sha256": sha256(rawpath), "requested_center_lat_lon": center,
                  "returned_grid_lat_lon": [data.get("latitude"), data.get("longitude")],
                  "nominal_resolution_degrees": 0.25 if model == "era5" else 0.1,
                  "elevation_m": data.get("elevation"), "timezone": data.get("timezone"),
                  "daily_units": data.get("daily_units"), "hourly_units": data.get("hourly_units")}


def windows(daily, stamp):
    byday = dict(zip(daily.get("time", []), daily.get("precipitation_sum", [])))
    day = date.fromisoformat(stamp)
    out = {}
    for n in (1, 3, 7, 14):
        vals = [byday.get((day - timedelta(days=i)).isoformat()) for i in range(1, n + 1)]
        out[f"rain_prev_{n}d_mm"] = round(float(sum(vals)), 2) if vals and all(v is not None for v in vals) else None
    future = [byday.get((day + timedelta(days=i)).isoformat()) for i in range(1, 4)]
    out["rain_future_3d_negative_control_mm"] = round(float(sum(future)), 2) if all(v is not None for v in future) else None
    temp_byday = dict(zip(daily.get("time", []), daily.get("temperature_2m_mean", [])))
    future_temp = [temp_byday.get((day + timedelta(days=i)).isoformat()) for i in range(1, 4)]
    out["temperature_future_3d_mean_c_negative_control"] = round(float(np.mean(future_temp)), 2) if all(v is not None for v in future_temp) else None
    return out


def corr(x, y):
    pairs = [(float(a), float(b)) for a, b in zip(x, y) if a is not None and b is not None and np.isfinite(a) and np.isfinite(b)]
    if len(pairs) < 4:
        return {"n_dates": len(pairs), "pearson_r": None, "spearman_rho": None, "loo_pearson_range": None}
    xx, yy = np.asarray(pairs).T
    if np.ptp(xx) == 0 or np.ptp(yy) == 0:
        return {"n_dates": len(xx), "pearson_r": None, "spearman_rho": None, "loo_pearson_range": None}
    loo = [pearsonr(np.delete(xx, i), np.delete(yy, i)).statistic
           for i in range(len(xx)) if np.ptp(np.delete(xx, i)) and np.ptp(np.delete(yy, i))] if len(xx) > 4 else []
    return {"n_dates": len(xx), "pearson_r": round(float(pearsonr(xx, yy).statistic), 4),
            "spearman_rho": round(float(spearmanr(xx, yy).statistic), 4),
            "loo_pearson_range": [round(float(min(loo)), 4), round(float(max(loo)), 4)] if loo else None}


def seasonal_residual_corr(x, y, stamps):
    """Partial correlation after linear trend and one annual sin/cos cycle."""
    valid = [(i, a, b) for i, (a, b) in enumerate(zip(x, y))
             if a is not None and b is not None and np.isfinite(a) and np.isfinite(b)]
    if len(valid) < 6:
        return {**corr([], []), "model": "intercept + linear time trend + annual sin/cos day-of-year"}
    ix = np.array([v[0] for v in valid])
    xx = np.array([v[1] for v in valid], dtype=float)
    yy = np.array([v[2] for v in valid], dtype=float)
    ds = [date.fromisoformat(stamps[i]) for i in ix]
    t = np.array([(d - ds[0]).days for d in ds], dtype=float)
    doy = np.array([d.timetuple().tm_yday for d in ds], dtype=float)
    period = 365.2425
    design = np.column_stack([np.ones(len(ds)), t / period,
                              np.sin(2 * np.pi * doy / period),
                              np.cos(2 * np.pi * doy / period)])
    rx = xx - design @ np.linalg.lstsq(design, xx, rcond=None)[0]
    ry = yy - design @ np.linalg.lstsq(design, yy, rcond=None)[0]
    out = corr(rx.tolist(), ry.tolist())
    loo = []
    for i in range(len(ds)):
        keep = np.arange(len(ds)) != i
        dx, dy = design[keep], design[keep]
        ex = xx[keep] - dx @ np.linalg.lstsq(dx, xx[keep], rcond=None)[0]
        ey = yy[keep] - dy @ np.linalg.lstsq(dy, yy[keep], rcond=None)[0]
        if len(ex) >= 4 and np.ptp(ex) and np.ptp(ey):
            loo.append(float(pearsonr(ex, ey).statistic))
    out["loo_pearson_range"] = [round(min(loo), 4), round(max(loo), 4)] if loo else None
    out.update({"model": "intercept + linear time trend + annual sin/cos day-of-year",
                "residual_df_approx": max(0, len(ds) - design.shape[1]),
                "warning": "exploratory one-cycle adjustment; low effective degrees of freedom and serial dependence; not causal"})
    return out


def common_mode_decompose(values):
    """Return point-own-baseline d_it, scene common mode g_t, and local r_it."""
    x = np.asarray(values, dtype=float)
    d = x - np.nanmedian(x, axis=1, keepdims=True)
    g = np.nanmedian(d, axis=0)
    return d, g, d - g[None, :]


def summarize(site, data, weather):
    dates = site["dates"]
    pixels = site["pixels"]
    covers = np.asarray([p["cover"] for p in pixels])
    fields = {}
    for pol in ("hh", "hv"):
        vals = np.asarray([p[pol] for p in pixels], dtype=float)
        # Scene common mode is full-AOI median. Class medians are not pixel-level
        # weather samples; they provide descriptive cover-stratified responses.
        fields[pol] = {"scene_median": np.nanmedian(vals, axis=0),
                       "by_cover": {str(c): np.nanmedian(vals[covers == c], axis=0)
                                    for c in sorted(set(covers)) if np.sum(covers == c) >= 10}}
    daily = data["daily"]
    met_daily = dict(zip(daily["time"], zip(daily["temperature_2m_mean"], daily["wind_speed_10m_max"])))
    hourly = data.get("hourly", {})
    hourly_by_day = {}
    if hourly:
        for j, t in enumerate(hourly["time"]):
            d = t[:10]
            row = hourly_by_day.setdefault(d, {})
            for key in HOURLY:
                row.setdefault(key, []).append(hourly.get(key, [None] * len(hourly["time"]))[j])
    records = []
    for i, stamp in enumerate(dates):
        met = met_daily.get(stamp, (None, None))
        hr = hourly_by_day.get(stamp, {})
        def mean(key):
            x = [v for v in hr.get(key, []) if v is not None]
            return round(float(np.mean(x)), 3) if x else None
        records.append({"date": stamp, **windows(daily, stamp),
                        "temperature_mean_c": met[0], "wind_max_kmh": met[1],
                        "era5_land_soil_moisture_0_7cm_daily_mean_m3m3": mean("soil_moisture_0_to_7cm"),
                        "era5_land_soil_temp_0_7cm_daily_mean_c": mean("soil_temperature_0_to_7cm"),
                        "era5_land_soil_temp_7_28cm_daily_mean_c": mean("soil_temperature_7_to_28cm"),
                        "era5_land_wind_speed_10m_hourly_valid_n": sum(v is not None for v in hr.get("wind_speed_10m", []))})
    # Preserve point-own-baseline class summaries, then compute the separate
    # global date mode and actual common-mode-removed local residuals.
    metrics = {}
    for pol, entries in fields.items():
        scene = entries["scene_median"]
        metrics[f"{pol}_scene_common_mode"] = scene.tolist()
        for c, vals in entries["by_cover"].items():
            metrics[f"{pol}_cover_{c}_median"] = vals.tolist()
        arr = np.asarray([p[pol] for p in pixels], dtype=float)
        d, g, r = common_mode_decompose(arr)
        metrics[f"{pol}_g_t_scene_common_mode_of_point_baseline_deviations"] = g.tolist()
        for c in entries["by_cover"]:
            old_summary = np.nanmedian(d[covers == int(c)], axis=0).tolist()
            metrics[f"{pol}_cover_{c}_cell_median_residual"] = old_summary
            metrics[f"{pol}_cover_{c}_point_own_baseline_class_median"] = old_summary
            metrics[f"{pol}_cover_{c}_common_mode_removed_local_residual"] = np.nanmedian(r[covers == int(c)], axis=0).tolist()
    predictors = [f"rain_prev_{n}d_mm" for n in (1, 3, 7, 14)] + ["rain_future_3d_negative_control_mm", "temperature_mean_c", "wind_max_kmh", "era5_land_soil_moisture_0_7cm_daily_mean_m3m3", "era5_land_soil_temp_0_7cm_daily_mean_c"]
    associations = {}
    for predictor in predictors:
        x = [r.get(predictor) for r in records]
        associations[predictor] = {k: corr(x, v) for k, v in metrics.items()}
    local_metrics = {k: v for k, v in metrics.items()
                     if "_g_t_" in k or "_common_mode_removed_local_residual" in k}
    common_mode_removed = {}
    for predictor in predictors:
        x = [r.get(predictor) for r in records]
        common_mode_removed[predictor] = {k: corr(x, v) for k, v in local_metrics.items()}
    temp = [r.get("temperature_mean_c") for r in records]
    future_temp = [r.get("temperature_future_3d_mean_c_negative_control") for r in records]
    hv_scene = metrics["hv_scene_common_mode"]
    hv_g = metrics["hv_g_t_scene_common_mode_of_point_baseline_deviations"]
    temperature_diagnostics = {
        "target": "ERA5 2 m mean temperature versus HV scene median and baseline-deviation common mode",
        "level_temperature_vs_hv_scene_median": corr(temp, hv_scene),
        "temperature_vs_hv_g_t": corr(temp, hv_g),
        "first_differences_temperature_vs_hv_scene_median": corr(np.diff(temp).tolist(), np.diff(hv_scene).tolist()),
        "first_differences_temperature_vs_hv_g_t": corr(np.diff(temp).tolist(), np.diff(hv_g).tolist()),
        "seasonal_trend_adjusted_temperature_vs_hv_scene_median": seasonal_residual_corr(temp, hv_scene, dates),
        "seasonal_trend_adjusted_temperature_vs_hv_g_t": seasonal_residual_corr(temp, hv_g, dates),
        "future_3d_temperature_vs_hv_scene_median_negative_control": corr(future_temp, hv_scene),
        "future_3d_temperature_vs_hv_g_t_negative_control": corr(future_temp, hv_g),
        "first_difference_note": "Adjacent observation differences only; irregular intervals are not treated as equal physical rates.",
        "seasonal_note": "One annual sin/cos cycle plus linear trend; exploratory with low effective degrees of freedom."}
    return {"site": site["id"], "dates": records, "cover_code_counts": {str(c): int(sum(covers == c)) for c in sorted(set(covers))},
            "class_support": {str(c): {"cells": int(sum(covers == c)), "used_for_class_correlations": bool(sum(covers == c) >= 10)} for c in sorted(set(covers))},
            "sar_date_summaries_db": metrics, "exploratory_date_level_correlations": associations,
            "common_mode_removed_weather_correlations": common_mode_removed,
            "temperature_hv_targeted_falsification": temperature_diagnostics,
            "method": "Two-sided date-level exploratory correlations; no best-lag selection. Legacy *_cell_median_residual preserves point-own-temporal-median class summary and does NOT remove scene/date common mode. New point_own_baseline_class_median aliases it. True local residual: d_it=x_it-median_t(x_i), g_t=median_i(d_it), r_it=d_it-g_t; class summaries are median_i(r_it) by WorldCover class. Dates, not pixels, are temporal units; no pixel bootstrap."}


def run():
    result = {"generated_at_utc": datetime.now(timezone.utc).isoformat(),
              "availability_checks": {"open_meteo_archive": "HTTP 200 on 2026-11-15 for both tested ERA5 and ERA5-Land sample dates; response fields inspected. ERA5-Land precipitation and wind fields were null in Mexico sample, so daily rain/temp/wind use ERA5; soil variables use ERA5-Land. ERA5-Land 10m hourly wind also null. soil_temperature_0cm unit undefined; excluded. 0-7cm and 7-28cm soil temperature, 0-7cm soil moisture returned units and non-null data."}, "sites": {}, "provenance": []}
    for sid in ("mexico", "amazon"):
        site = json.loads((ROOT / f"data/{sid}.json").read_text())
        start = (date.fromisoformat(site["dates"][0]) - timedelta(days=14)).isoformat()
        end = (date.fromisoformat(site["dates"][-1]) + timedelta(days=3)).isoformat()
        center = site["center"]
        era5, p1 = request_site(sid, "era5", center, start, end)
        land, p2 = request_site(sid, "era5_land", center, start, end)
        result["provenance"].extend([p1, p2])
        merged = dict(era5)
        merged["hourly"] = land.get("hourly", {})
        merged["hourly_units"] = land.get("hourly_units", {})
        out = summarize(site, merged, land)
        out["weather_sources"] = {"rain_temperature_wind": "ERA5 (Open-Meteo archive API)", "soil_moisture_temperature": "ERA5-Land (Open-Meteo archive API)"}
        result["sites"][sid] = out
    dest = ROOT / "data/investigation/weather.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    print(json.dumps({s: {"dates": len(v["dates"]), "correlations": v["exploratory_date_level_correlations"].get("rain_prev_7d_mm", {})} for s, v in result["sites"].items()}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--refresh", action="store_true", help="re-fetch API responses; default reuses hash-verified saved responses")
    ARGS = parser.parse_args()
    run()
