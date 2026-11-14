"""Deterministic spatial/date audit of local Amazon NISAR candidates (offline)."""
from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path

import numpy as np
from shapely import is_valid_reason, make_valid
from shapely.geometry import Point, shape

ROOT = Path(__file__).resolve().parents[1]
SERIES = ROOT / "data/subsets/amazon-series"
ALERTS = ROOT / "data/amazon/alerts.geojson"
FIRES = ROOT / "data/amazon/fires.json"
BEFORE, AFTER = "2026-08-23", "2026-09-04"
SEED = 33017
MAX_CANDIDATES = 8
MIN_CELL_GAP = 3  # deterministic grid separation; not an independence claim


def point_in_geometry(lon, lat, geometry):
    """Shapely covers test on repaired GeoJSON geometry; boundary counts as covered."""
    if not geometry:
        return False
    geom = shape(geometry)
    if not geom.is_valid:
        geom = make_valid(geom)
    return bool(geom.covers(Point(lon, lat)))


def prepare_alert_geometries(features):
    prepared, invalid_reasons, repaired_types = [], [], Counter()
    for index, feature in enumerate(features):
        geom = shape(feature["geometry"])
        original_valid = geom.is_valid
        if not original_valid:
            invalid_reasons.append({"feature_index": index, "reason": is_valid_reason(geom)})
            geom = make_valid(geom)
            repaired_types[geom.geom_type] += 1
        prepared.append((feature, geom, original_valid))
    return prepared, {"feature_count": len(features), "invalid_geometry_count": len(invalid_reasons),
                      "invalid_geometry_reasons": invalid_reasons,
                      "make_valid_output_types": dict(repaired_types),
                      "all_repaired_geometries_valid": all(g.is_valid for _, g, _ in prepared),
                      "predicate": "Shapely covers(Point), including polygon boundaries; invalid input repaired with make_valid"}


def haversine_m(lon1, lat1, lon2, lat2):
    r = 6371008.8
    p1, p2 = np.radians([lat1, lat2])
    dp, dl = p2 - p1, np.radians(lon2 - lon1)
    a = np.sin(dp / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return float(2 * r * np.arcsin(np.sqrt(a)))


def load_pair():
    grids, metas = {}, {}
    for date in (BEFORE, AFTER):
        with np.load(SERIES / f"{date}.npz") as a:
            grids[date] = {k: a[k].copy() for k in ("lat", "lon", "hh", "hv", "mask")}
        metas[date] = json.loads((SERIES / f"{date}.json").read_text())
    for key in ("lat", "lon"):
        if not np.array_equal(grids[BEFORE][key], grids[AFTER][key]):
            raise ValueError(f"Unaligned SAR {key} arrays")
    if metas[BEFORE]["grid"] != metas[AFTER]["grid"]:
        raise ValueError("SAR grid metadata differs")
    valid = []
    for d in (BEFORE, AFTER):
        g = grids[d]
        valid.append((g["mask"] != 0) & (g["mask"] != 255) & np.isfinite(g["hh"]) &
                     np.isfinite(g["hv"]) & (g["hh"] > 0) & (g["hv"] > 0))
    ok = valid[0] & valid[1]
    dhh = 10 * np.log10(grids[AFTER]["hh"] / grids[BEFORE]["hh"])
    dhv = 10 * np.log10(grids[AFTER]["hv"] / grids[BEFORE]["hv"])
    return grids, metas, ok, dhh, dhv


def pick_candidates(ok, dhh, dhv, lat, lon):
    """Pick separated severe, randomly sampled, and low-change controls."""
    rr, cc = np.where(ok & np.isfinite(dhh) & np.isfinite(dhv))
    if not len(rr):
        raise RuntimeError("No paired valid pixels")
    # Strong means both channels decrease. RMS magnitude cannot hide an increase
    # in one channel behind a larger decrease in the other.
    rms = np.sqrt((dhh[rr, cc] ** 2 + dhv[rr, cc] ** 2) / 2)
    both_negative = (dhh[rr, cc] < 0) & (dhv[rr, cc] < 0)
    order = np.lexsort((np.arange(len(rr)), -rms, ~both_negative))
    rng = np.random.default_rng(SEED)
    random_order = rng.permutation(len(rr))
    low_order = np.argsort(rms, kind="stable")
    picked = []

    def add(kind, indexes, count, require_both_negative=False):
        for i in indexes:
            if require_both_negative and not both_negative[i]:
                continue
            r, c = int(rr[i]), int(cc[i])
            if all(max(abs(r - x["row"]), abs(c - x["col"])) >= MIN_CELL_GAP for x in picked):
                picked.append({"role": kind, "row": r, "col": c,
                               "lat": float(lat[r, c]), "lon": float(lon[r, c]),
                               "delta_hh_db": float(dhh[r, c]), "delta_hv_db": float(dhv[r, c]),
                               "rms_delta_db": float(rms[i]),
                               "combined_delta_db": float((dhh[r,c] + dhv[r,c]) / 2)})
                if sum(x["role"] == kind for x in picked) >= count:
                    break

    add("strong", order, 4, require_both_negative=True)
    add("random_control", random_order, 3)
    add("low_change_control", low_order, 3)
    return picked


def audit_sources(candidates):
    feature_collection = json.loads(ALERTS.read_text())
    fires = json.loads(FIRES.read_text())
    prepared, _ = prepare_alert_geometries(feature_collection.get("features", []))
    results = []
    for c in candidates:
        matches = []
        for feature, geom, original_valid in prepared:
            p = feature.get("properties", {})
            if geom.covers(Point(c["lon"], c["lat"])):
                date = str(p.get("date", ""))[:10]
                matches.append({"source": p.get("source"), "class": p.get("class"),
                                "date": date, "date_relation": relation(date),
                                "date_precision": "date-only; time/timezone unavailable",
                                "original_geometry_valid": original_valid,
                                "make_valid_applied": not original_valid,
                                "boundary_inclusive_covers": True,
                                "area_ha": p.get("area_ha")})
        fire_matches = []
        for f in fires:
            dist = haversine_m(c["lon"], c["lat"], float(f["lon"]), float(f["lat"]))
            if dist <= 500:
                date = str(f.get("date", ""))[:10]
                fire_matches.append({"date": date, "date_relation": relation(date),
                                     "date_precision": "date-only; time value/timezone retained separately",
                                     "time_raw": f.get("time"),
                                     "distance_m": round(dist, 1), "provider": f.get("provider"),
                                     "source": f.get("source"), "confidence": f.get("confidence"),
                                     "frp": f.get("frp")})
        results.append({**c, "alert_polygon_intersections": matches,
                        "firms_in_500m": sorted(fire_matches, key=lambda f: (f["distance_m"], f["date"]))})
    return results


def relation(date):
    if not date:
        return "undated"
    if date in (BEFORE, AFTER):
        return "same_sar_calendar_day_time_ambiguous"
    if date < BEFORE:
        return "before_pair"
    if date < AFTER:
        return "between_sar_dates"
    return "after_pair"


def run():
    grids, metas, valid, dhh, dhv = load_pair()
    reference = grids[BEFORE]
    candidates = pick_candidates(valid, dhh, dhv, reference["lat"], reference["lon"])
    alert_data = json.loads(ALERTS.read_text())
    _, geometry_validation = prepare_alert_geometries(alert_data.get("features", []))
    previous = json.loads((ROOT / "data/amazon-spatial-sar-eda-v2-original-selection.json").read_text())
    sar_acquisitions = []
    for d in (BEFORE, AFTER):
        granule = metas[d]["source"]["id"]
        m = re.search(r"_(\d{8}T\d{6})_(\d{8}T\d{6})_", granule)
        sar_acquisitions.append({"date": d, "granule_id": granule,
                                 "start_utc": datetime.strptime(m.group(1), "%Y%m%dT%H%M%S").isoformat() + "Z",
                                 "end_utc": datetime.strptime(m.group(2), "%Y%m%dT%H%M%S").isoformat() + "Z"})
    old_cells = {(c["row"], c["col"]): c["role"] for c in previous["candidates"]}
    new_cells = {(c["row"], c["col"]): c["role"] for c in candidates}
    comparison = {"previous_algorithm": previous["algorithm"],
                  "previous_candidate_roles": previous["candidates"],
                  "revised_candidates_same_cell_as_previous": [
                      {"row": r, "col": c, "previous_role": old_cells[(r,c)], "revised_role": new_cells[(r,c)]}
                      for r,c in sorted(old_cells.keys() & new_cells.keys())],
                  "revised_cells_not_in_previous": [
                      {"row": r, "col": c, "role": role} for (r,c),role in sorted(new_cells.items()) if (r,c) not in old_cells]}
    return {
        "study": "Amazon/Itupiranga, local provisional NISAR GCOV sample",
        "pair": [BEFORE, AFTER], "sar_acquisitions": sar_acquisitions, "random_seed": SEED,
        "sampling": {"strong": "four largest RMS(dHH,dHV), requiring dHH < 0 and dHV < 0",
                     "controls": "three seeded-random and three lowest RMS(dHH,dHV) paired changes",
                     "rms_definition": "sqrt((dHH^2+dHV^2)/2), dB-change magnitudes",
                     "selection_revision": "replaces the prior signed-mean rule; the former selection is retained for comparison, not endorsed",
                     "minimum_grid_cell_gap": MIN_CELL_GAP,
                     "warning": "spatially separated candidates are not independent events",
                     "posthoc_note": "analysis choices are retrospective, not preregistered"},
        "provenance": {"granules": [metas[d]["source"]["id"] for d in (BEFORE, AFTER)],
                       "grid": metas[BEFORE]["grid"], "shape": list(valid.shape),
                       "paired_valid_cells": int(valid.sum()),
                       "power_conversion": "10*log10(after/before); excludes mask 0/255, nonfinite, nonpositive HH/HV",
                        "alerts_file": "data/amazon/alerts.geojson",
                        "fires_file": "data/amazon/fires.json",
                        "date_precision_policy": "SAR granule start/end timestamps are exact UTC; GLAD/DETER date fields without time are date-only and same-calendar-day ordering is ambiguous"},
        "local_alert_geometry_validation": geometry_validation,
        "candidate_results": audit_sources(candidates),
        "selection_comparison": comparison,
        "sentinel2_scl": {"status": "not_locally_available; no dated before/after asset sampled",
                           "limitation": "no network fetch attempted; absent evidence is not a negative observation"},
        "limitations": ["Provisional SAR product; sampled subset is not contiguous mapped coverage.",
                        "Alert match uses repaired geometry and boundary-inclusive covers; alert record date does not establish publication/vintage.",
                        "FIRMS is a 500 m point-distance screen, not pixel intersection or fire confirmation.",
                        "Nearby same-event detections/candidates are not independent; no event counts inferred.",
                        "Controls are descriptive, not matched causal controls; no training or attribution."],
    }


if __name__ == "__main__":
    print(json.dumps(run(), indent=2, allow_nan=False))
