"""Reproducible, local-only exploratory analysis of the prepared Amazon NISAR subset.

Run from the repository root: python scripts/eda_amazon_sar.py
Requires NumPy. Reads only data/subsets/amazon-series, its JSON sidecars,
WorldCover subset, and the checked-in Amazon alert GeoJSON. No network access.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
SERIES = DATA / "subsets/amazon-series"
TARGET = (5, 15)
MIN_CORRELATION_N = 10


def pearson(x, y, minimum=MIN_CORRELATION_N):
    """Pairwise-finite Pearson r, withheld unless sample count is adequate."""
    x, y = np.asarray(x, float), np.asarray(y, float)
    ok = np.isfinite(x) & np.isfinite(y)
    if ok.sum() < minimum or np.std(x[ok]) == 0 or np.std(y[ok]) == 0:
        return None
    return float(np.corrcoef(x[ok], y[ok])[0, 1])


def valid_observations(mask, hh, hv):
    """Shared validity across all calculations; zero and 255 are fill/invalid."""
    mask, hh, hv = np.asarray(mask), np.asarray(hh), np.asarray(hv)
    return ((mask != 0) & (mask != 255) & np.isfinite(mask) & np.isfinite(hh) &
            np.isfinite(hv) & (hh > 0) & (hv > 0))


def paired_median(values_a, values_b, valid_a, valid_b, candidate_mask):
    paired = candidate_mask & valid_a & valid_b
    paired = paired.copy()
    vals = np.asarray(values_b)[paired] - np.asarray(values_a)[paired]
    return int(vals.size), float(np.median(vals)) if vals.size else None


def require_aligned(reference, candidate, date):
    """Reject a SAR acquisition unless its coordinates exactly match the grid."""
    lat, lon = reference["lat"], reference["lon"]
    if candidate["lat"].shape != lat.shape or candidate["lon"].shape != lon.shape:
        raise ValueError(f"Coordinate shape mismatch on {date}")
    if not np.array_equal(candidate["lat"], lat) or not np.array_equal(candidate["lon"], lon):
        raise ValueError(f"Coordinate values are shifted on {date}")


def require_compatible_metadata(reference, candidate, date):
    def grid(meta):
        return {k: v for k, v in meta.get("grid", {}).items() if k != "date"}
    def signature(meta):
        match = re.search(r"_\d+_(\d+)_([AD])_(\d+)_\d+_([A-Z]{4})_([A-Z])_",
                          meta.get("source", {}).get("id", ""))
        return match.groups() if match else None
    if grid(reference) != grid(candidate) or signature(reference) is None or signature(reference) != signature(candidate):
        raise ValueError(f"Incompatible SAR/grid metadata on {date}")


def sar_signature(value):
    match = re.search(r"_\d+_(\d+)_([AD])_(\d+)_\d+_([A-Z]{4})_([A-Z])_", value)
    return match.groups() if match else None


def neighbour_control(stack, valid, a, b, local):
    """Calculate the same paired median control used in the reported EDA."""
    n, median = paired_median(stack[a], stack[b], valid[a], valid[b], local)
    paired = local & valid[a] & valid[b]
    vals = (stack[b] - stack[a])[paired]
    return {"n_paired": n, "median_individual_change_db": median,
            "median_corrected_target_change_db": None,
            "control_iqr_db": [float(x) for x in np.percentile(vals, [25, 75])] if n else None}


def run():
    sidecars = sorted(SERIES.glob("*.json"))
    dates, grids, metas = [], [], []
    for sidecar in sidecars:
        meta = json.loads(sidecar.read_text())
        date = meta["date"]
        with np.load(SERIES / f"{date}.npz") as a:
            grids.append({k: a[k].copy() for k in ("lat", "lon", "hh", "hv", "mask")})
        dates.append(date)
        metas.append(meta)
    if not grids:
        raise RuntimeError(f"No Amazon time-series NPZ files in {SERIES}")
    for date, meta in zip(dates[1:], metas[1:]):
        require_compatible_metadata(metas[0], meta, date)
    lat, lon = grids[0]["lat"], grids[0]["lon"]
    for date, grid in zip(dates[1:], grids[1:]):
        require_aligned(grids[0], grid, date)
    cover_path = DATA / "subsets/amazon/worldcover.npz"
    with np.load(cover_path) as a:
        cover = a["cover"].copy()
    if cover.shape != lat.shape:
        raise ValueError(f"WorldCover shape {cover.shape} != SAR shape {lat.shape}")
    alignment = {"worldcover_shape_matches": bool(cover.shape == lat.shape),
                 "worldcover_coordinate_transform_verified": False,
                 "unverified": ["WorldCover geotransform/CRS (subset NPZ has no coordinate arrays)",
                                "mask bit semantics beyond explicit 0/255 invalid codes"]}
    prior_compatibility = []
    for idx in (0, 1):
        mp, ap = DATA / f"subsets/amazon/nisar-{idx}.json", DATA / f"subsets/amazon/nisar-{idx}.npz"
        if mp.exists() and ap.exists():
            m = json.loads(mp.read_text())
            with np.load(ap) as z:
                same_shape = all(z[k].shape == grids[0][k].shape for k in ("lat", "lon", "hh", "hv", "mask"))
                same_coords = same_shape and np.array_equal(z["lat"], lat) and np.array_equal(z["lon"], lon)
            current_grid = {k: v for k, v in metas[0].get("grid", {}).items() if k != "date"}
            prior_grid = {k: v for k, v in m.get("grid", {}).items() if k != "date"}
            prior_id = m.get("identification") or {}
            current_id = metas[0].get("identification") or {}
            # Series sidecars omit identification fields; verify track/frame,
            # pass, polarization and band from the granule naming convention.
            source_id = m.get("source", {}).get("id", "")
            current_source_id = metas[0].get("source", {}).get("id", "")
            signatures_match = (sar_signature(source_id) is not None and
                                sar_signature(source_id) == sar_signature(current_source_id))
            explicit_match = bool(prior_id and current_id and prior_id == current_id)
            same_metadata = prior_grid == current_grid and (signatures_match or explicit_match)
            prior_compatibility.append({"date": m.get("grid", {}).get("date"),
                "compatible": bool(same_shape and same_coords and same_metadata),
                "shape_match": bool(same_shape), "coordinates_match": bool(same_coords),
                "grid_and_sar_metadata_match": bool(same_metadata)})
            if same_shape and same_coords and same_metadata:
                with np.load(ap) as z:
                    grids.append({k: z[k].copy() for k in ("lat", "lon", "hh", "hv", "mask")})
                dates.append(m["grid"]["date"])
                metas.append(m)
    ordered = sorted(zip(dates, grids, metas), key=lambda item: item[0])
    dates, grids, metas = map(list, zip(*ordered))
    # NPZ stores linear gamma0 power, not dB. Zero/non-positive values are nodata.
    hh_power = np.stack([g["hh"] for g in grids])
    hv_power = np.stack([g["hv"] for g in grids])
    valid = np.stack([valid_observations(g["mask"], g["hh"], g["hv"]) for g in grids])
    hh = np.where(valid, 10 * np.log10(np.where(valid, hh_power, 1)), np.nan)
    hv = np.where(valid, 10 * np.log10(np.where(valid, hv_power, 1)), np.nan)
    r, c = TARGET
    cls = int(cover[r, c])
    peers = (cover == cls) & (cover != 0)
    # Baseline: the event's raw target change. Relative change subtracts the
    # median paired change of same-class neighbours, excluding the target.
    target_ok = valid[:, r, c]
    first = int(np.flatnonzero(target_ok)[0]) if target_ok.any() else None
    out = {
        "study": "Amazon (Itupiranga, Para), NISAR GCOV SAR; not Sarov",
        "dates": dates,
        "prior_acquisition_compatibility": prior_compatibility,
        "alignment_checks": alignment,
        "granules": [m["source"]["id"] for m in metas],
        "shape": list(lat.shape),
        "grid": {"epsg": metas[0]["grid"]["epsg"], "spacing_m": metas[0]["grid"]["spacing"], "window": metas[0]["grid"]["window"]},
        "target": {"row": r, "col": c, "lat": float(lat[r,c]), "lon": float(lon[r,c]), "worldcover_code": cls,
                   "valid_dates": [d for d, ok in zip(dates, target_ok) if ok]},
        "availability": {"pixels": int(valid.shape[1]*valid.shape[2]),
                         "valid_hh_hv_by_date": {d: int(v.sum()) for d,v in zip(dates, valid)},
                         "cover_classes": {str(int(k)): int(n) for k,n in zip(*np.unique(cover, return_counts=True))}},
        "target_series": {}, "correlations": {},
    }
    event_pair = (dates.index("2026-08-23"), dates.index("2026-09-04")) if "2026-08-23" in dates and "2026-09-04" in dates else None
    for pol, stack in (("hh", hh), ("hv", hv)):
        series = stack[:, r, c].astype(float)
        out["target_series"][pol] = [float(x) if np.isfinite(x) else None for x in series]
        if first is not None:
            change = series - series[first]
            out["target_series"][pol + "_change_from_first_db"] = [float(x) if np.isfinite(x) else None for x in change]
            if event_pair:
                a, b = event_pair
                raw = float(series[b] - series[a]) if target_ok[a] and target_ok[b] else None
                out.setdefault("event_comparison", {})[pol] = {"dates": [dates[a], dates[b]], "raw_target_change_db": raw, "neighbour_controls": {}}
                for width in (3, 5, 9):
                    rr, cc = width // 2, width // 2
                    local = np.zeros_like(peers)
                    local[max(0,r-rr):r+rr+1, max(0,c-cc):c+cc+1] = True
                    local &= peers
                    local[r,c] = False
                    control = neighbour_control(stack, valid, a, b, local)
                    median = control["median_individual_change_db"]
                    control["median_corrected_target_change_db"] = raw - median if raw is not None and median is not None else None
                    out["event_comparison"][pol]["neighbour_controls"][f"same_class_{width}x{width}"] = {
                        **control}
    # Alert intersection is a point-in-polygon test not implied by proximity; report
    # local feature metadata only, never treat an alert as ground-truth confirmation.
    alerts = json.loads((DATA / "amazon/alerts.geojson").read_text())
    cutoff = dates[-1]
    alert_rows = []
    for f in alerts.get("features", []):
        p = f.get("properties", {})
        if p.get("date", "")[:10] <= cutoff:
            alert_rows.append({k: p.get(k) for k in ("date", "source", "class", "area_ha")})
    out["available_alert_records_through_last_sar_date"] = alert_rows
    out["correlation_policy"] = f"Pearson reported only at n >= {MIN_CORRELATION_N}; only {len(dates)} local acquisition dates are available"
    out["correlations"]["hh_hv_across_dates_target"] = pearson(hh[:, r, c], hv[:, r, c])
    return out


if __name__ == "__main__":
    print(json.dumps(run(), indent=2, allow_nan=False))
