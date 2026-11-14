"""Retrospective, non-training HV boundary EDA for Mexico City and Caracas.

Run: /tmp/opencode/nasa-venv/bin/python scripts/eda_mx_ve_hv_boundaries.py
Inputs are the checked-in demo JSONs; output is a standalone JSON artifact.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/mexico-venezuela-hv-boundary-eda.json"
SEED = 33
WINDOW = 3


def med(values):
    """Median of numeric finite values; ignore nulls, strings and non-finite values."""
    try:
        a = np.asarray(values, dtype=float).reshape(-1)
    except (TypeError, ValueError):
        a = np.asarray([_number(v) for v in values], dtype=float)
    a = a[np.isfinite(a)]
    return float(np.median(a)) if a.size else None


def _number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return np.nan


def _window(values, start, stop):
    return np.asarray([_number(v) for v in values[start:stop]], dtype=float)


def analyze_site(path: Path, controls_rng: np.random.Generator) -> dict:
    data = json.loads(path.read_text())
    dates = data["dates"]
    points = data["pixels"]
    output = {"id": data["id"], "dates": dates, "sampled_points": len(points),
              "boundaries": [], "common_component": None}
    if data["id"] == "venezuela":
        output["common_component"] = (
            "Per-date site-wide median changes can contain a common-mode component ("
            "atmosphere, calibration/geometry, seasonal surface response, or broad signal). "
            "Subtracting same-class peer medians removes much of a spatially shared shift; "
            "it does not identify its physical cause or establish tectonic deformation.")
    for b in range(WINDOW, len(dates) - WINDOW + 1):
        rows = []
        for idx, p in enumerate(points):
            series = p.get("hv", [])
            peer = (p.get("peer") or {}).get("hv_med") or []
            if len(series) != len(dates):
                continue
            before = _window(series, b-WINDOW, b)
            after = _window(series, b, b+WINDOW)
            if not (np.isfinite(before).all() and np.isfinite(after).all()):
                continue
            raw = float(np.median(after) - np.median(before))
            rel = None
            if len(peer) == len(dates):
                pb = _window(peer, b-WINDOW, b)
                pa = _window(peer, b, b+WINDOW)
            else:
                pb = pa = np.array([], dtype=float)
            if pb.size == WINDOW and pa.size == WINDOW and np.isfinite(pb).all() and np.isfinite(pa).all():
                rel = float(np.median(after-pa) - np.median(before-pb))
            rows.append({"point_index": idx, "cover": p.get("cover"), "raw_delta_db": raw,
                         "peer_adjusted_delta_db": rel})
        if not rows:
            continue
        raw_vals = np.array([r["raw_delta_db"] for r in rows])
        rel_rows = [r for r in rows if r["peer_adjusted_delta_db"] is not None]
        rel_vals = np.array([r["peer_adjusted_delta_db"] for r in rel_rows])
        # Seeded random matched-size controls and a low-change decile control.
        n = min(100, len(rows))
        random_idx = controls_rng.choice(len(rows), size=n, replace=False)
        low_cut = np.quantile(np.abs(raw_vals), .1)
        low = np.flatnonzero(np.abs(raw_vals) <= low_cut)
        site_before = med([med([_number(p["hv"][i]) for p in points
                                if len(p.get("hv", [])) == len(dates)])
                           for i in range(b-WINDOW,b)])
        site_after = med([med([_number(p["hv"][i]) for p in points
                               if len(p.get("hv", [])) == len(dates)])
                          for i in range(b,b+WINDOW)])
        output["boundaries"].append({
            "boundary": dates[b], "before_dates": dates[b-WINDOW:b], "after_dates": dates[b:b+WINDOW],
            "n_raw": len(rows), "n_peer_adjusted": len(rel_rows),
            "hv_median_before_db": site_before,
            "hv_median_after_db": site_after,
            "site_median_contrast_after_minus_before_db": (site_after-site_before if site_before is not None and site_after is not None else None),
            "raw_abs_change_median_db": float(np.median(np.abs(raw_vals))),
            "raw_change_median_db": float(np.median(raw_vals)),
            "peer_adjusted_change_median_db": med(rel_vals),
            "peer_adjusted_abs_change_median_db": med(np.abs(rel_vals)),
            "random_control_abs_change_median_db": float(np.median(np.abs(raw_vals[random_idx]))),
            "low_change_control_n": int(len(low)),
            "low_change_control_abs_change_median_db": float(np.median(np.abs(raw_vals[low]))),
            "ranked_abs_change_top10_point_indices": [int(rows[i]["point_index"]) for i in np.argsort(-np.abs(raw_vals), kind="stable")[:10]],
            "ranked_peer_adjusted_abs_change_top10_point_indices": [int(rel_rows[i]["point_index"]) for i in np.argsort(-np.abs(rel_vals), kind="stable")[:10]],
            "spatial_independence": "Even locations separated by ~0.9 km are not independent events; the sampled grid is spatially correlated.",
        })
    return output


def run() -> dict:
    rng = np.random.default_rng(SEED)
    return {"analysis": "retrospective 3-acquisition median HV boundary EDA", "seed": SEED,
            "window_acquisitions": WINDOW, "training": False,
            "units": "HV gamma0 backscatter, dB", "sites": [
                analyze_site(ROOT / "data/mexico.json", rng),
                analyze_site(ROOT / "data/venezuela.json", rng)],
            "warnings": [
                "Retrospective/look-ahead: all currently checked-in acquisitions and all boundaries are analyzed; not a prospective alert test.",
                "Sample selection and retrospective boundary ranking can inflate apparent effects; no multiple-testing correction or causal inference.",
                "Grid locations are spatially correlated; even ~0.9 km separation does not make observations independent events.",
                "Same-class peer correction is an exploratory common-mode adjustment and depends on historical ESA WorldCover classification.",
                "USGS us6000t7zp (2026-06-24) is outside the current Caracas demo dates; the additional 2026-06-13—25 GUNW has zero samples passing the unchanged quality filter. No event match is claimed.",
                "Independent GNSS: UNR IGS20 MMX1 tenv3 https://geodesy.unr.edu/gps_timeseries/IGS20/tenv3/IGS20/MMX1.tenv3 reports Up −10.38 mm from 2025-10-30 to 2025-11-11; this absolute GNSS component is not directly comparable to relative LOS or its spatial reference.",
                "HV backscatter is not displacement. Small sample counts and coverage differ by date/site; unavailable values are excluded, not imputed."]}


if __name__ == "__main__":
    result = run()
    OUT.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    print(f"Wrote {OUT.relative_to(ROOT)}")
