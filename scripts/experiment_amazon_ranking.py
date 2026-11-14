"""Offline Amazon event-window ranking experiment (issue #33 follow-up).

Only 2026-08-23 and 2026-09-04 are used to rank pixels. Later dates are
reported solely as follow-up at fixed checkpoints and cannot affect ranks.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]

SERIES = ROOT / "data/subsets/amazon-series"
COVER_PATH = ROOT / "data/subsets/amazon/worldcover.npz"
BEFORE, AFTER = "2026-08-23", "2026-09-04"
TARGET = (5, 15)
# Fixed spatial checkpoints (target and four immediate axial neighbors).
CHECKPOINT_OFFSETS = {"candidate": (0, 0), "north": (-1, 0), "east": (0, 1),
                      "south": (1, 0), "west": (0, -1)}
RADII = (1, 2, 4)  # half-widths: 3x3, 5x5, 9x9
MIN_PEERS = 3


def valid_observations(mask, hh, hv):
    """Use the existing EDA validity contract without changing its file."""
    mask, hh, hv = np.asarray(mask), np.asarray(hh), np.asarray(hv)
    return ((mask != 0) & (mask != 255) & np.isfinite(mask) & np.isfinite(hh) &
            np.isfinite(hv) & (hh > 0) & (hv > 0))


def require_aligned(reference, candidate, date):
    """Require exact coordinate arrays, as in scripts/eda_amazon_sar.py."""
    for key in ("lat", "lon"):
        if candidate[key].shape != reference[key].shape:
            raise ValueError(f"Coordinate shape mismatch on {date}")
        if not np.array_equal(candidate[key], reference[key]):
            raise ValueError(f"Coordinate values are shifted on {date}")


def sar_signature(meta):
    source_id = meta.get("source", {}).get("id", "")
    match = re.search(r"_\d+_(\d+)_([AD])_(\d+)_\d+_([A-Z]{4})_([A-Z])_", source_id)
    return match.groups() if match else None


def require_compatible_metadata(reference, candidate, date):
    grid = lambda meta: {k: v for k, v in meta.get("grid", {}).items() if k != "date"}
    ref_sig, cand_sig = sar_signature(reference), sar_signature(candidate)
    if grid(reference) != grid(candidate) or ref_sig is None or ref_sig != cand_sig:
        raise ValueError(f"Incompatible SAR/grid metadata on {date}")


def relative_residuals(delta, paired_class, radius, min_peers=MIN_PEERS):
    """Per-pixel change minus same-class local median; self is always excluded."""
    corrected = np.full(delta.shape, np.nan)
    support = np.zeros(delta.shape, dtype=int)
    medians = np.full(delta.shape, np.nan)
    for r, c in zip(*np.where(paired_class)):
        rlo, rhi = max(0, r-radius), min(delta.shape[0], r+radius+1)
        clo, chi = max(0, c-radius), min(delta.shape[1], c+radius+1)
        local = paired_class[rlo:rhi, clo:chi].copy()
        local[r-rlo, c-clo] = False
        vals = delta[rlo:rhi, clo:chi][local]
        support[r, c] = vals.size
        if vals.size >= min_peers:
            medians[r, c] = np.median(vals)
            corrected[r, c] = delta[r, c] - medians[r, c]
    return corrected, support, medians


def load_data():
    dates, signals, valid, grids, metas = [], {}, [], [], []
    for p in sorted(SERIES.glob("*.json")):
        meta = json.loads(p.read_text())
        date = meta["date"]
        with np.load(SERIES / f"{date}.npz") as a:
            grids.append({key: a[key].copy() for key in ("lat", "lon")})
            dates.append(date)
            valid.append(valid_observations(a["mask"], a["hh"], a["hv"]))
            for pol in ("hh", "hv"):
                power = a[pol].astype(float)
                signals.setdefault(pol, []).append(np.where(power > 0, 10*np.log10(np.where(power > 0, power, 1)), np.nan))
        metas.append(meta)
    if not grids:
        raise RuntimeError(f"No Amazon time-series NPZ files in {SERIES}")
    for date, meta, grid in zip(dates[1:], metas[1:], grids[1:]):
        require_compatible_metadata(metas[0], meta, date)
        require_aligned(grids[0], grid, date)
    with np.load(COVER_PATH) as a:
        cover = a["cover"].copy()
    if cover.shape != grids[0]["lat"].shape:
        raise ValueError(f"WorldCover shape {cover.shape} != SAR shape {grids[0]['lat'].shape}")
    return dates, {k: np.stack(v) for k, v in signals.items()}, np.stack(valid), cover


def window_indices(dates):
    if BEFORE not in dates or AFTER not in dates:
        raise RuntimeError(f"Required event window {BEFORE} -> {AFTER} missing")
    return dates.index(BEFORE), dates.index(AFTER)


def run():
    dates, stacks, valid, cover = load_data()
    i, j = window_indices(dates)
    r0, c0 = TARGET
    cls = int(cover[TARGET])
    class_mask = (cover == cls) & (cover != 0)
    result = {
        "experiment": "Amazon event-window relative-change ranking",
        "event_window": [BEFORE, AFTER], "ranking_uses_only_event_window": True,
        "followup_dates_excluded_from_ranking": [d for d in dates if d > AFTER],
        "target": {"row": r0, "col": c0, "worldcover_code": cls},
        "ranking_population": "valid paired pixels in target WorldCover class; sampled cells, not independent events",
        "minimum_local_peers": MIN_PEERS, "sensitivities": {}, "checkpoints": {},
        "correlations": {"status": "withheld", "reason": "only four acquisition dates; below n=10 threshold; repeated dates at one location are not independent events"},
    }
    observation_pair_valid = valid[i] & valid[j]
    pair_valid = observation_pair_valid & class_mask
    point_rows = []
    lat_grid = lon_grid = None
    with np.load(SERIES / f"{BEFORE}.npz") as coordinates:
        lat_grid, lon_grid = coordinates["lat"].copy(), coordinates["lon"].copy()
    # Point-only display payload. Null values stay null; no interpolation or polygons.
    for r, c in np.ndindex(pair_valid.shape):
        point_rows.append({"row": int(r), "col": int(c), "lat": float(lat_grid[r, c]),
                           "lon": float(lon_grid[r, c]), "worldcover_code": int(cover[r, c]),
                           "valid_pair": bool(observation_pair_valid[r, c]), "signals": {}})
    for pol, stack in stacks.items():
        delta = stack[j] - stack[i]
        for radius in RADII:
            corrected, support, neighbor_median = relative_residuals(delta, pair_valid, radius)
            radius_key = f"{2*radius+1}x{2*radius+1}"
            for idx, (r, c) in enumerate(np.ndindex(pair_valid.shape)):
                point = point_rows[idx]
                record = point["signals"].setdefault(pol, {})
                record[radius_key] = {
                    "raw_change_db": float(delta[r, c]) if observation_pair_valid[r, c] else None,
                    "neighbor_median_db": float(neighbor_median[r, c]) if pair_valid[r, c] and np.isfinite(neighbor_median[r, c]) else None,
                    "residual_db": float(corrected[r, c]) if np.isfinite(corrected[r, c]) else None,
                    "paired_neighbors": int(support[r, c]) if pair_valid[r, c] else None,
                    "valid_class_pair": bool(pair_valid[r, c]),
                }
            eligible = pair_valid & np.isfinite(corrected)
            vals = corrected[eligible]
            # Negative residual ranks first (largest relative decrease).
            order = np.argsort(vals, kind="stable")
            coords = np.argwhere(eligible)
            for rank, value_index in enumerate(order, start=1):
                rr, cc = coords[value_index]
                point_rows[np.ravel_multi_index((rr, cc), pair_valid.shape)]["signals"][pol][radius_key]["rank"] = int(rank)
                point_rows[np.ravel_multi_index((rr, cc), pair_valid.shape)]["signals"][pol][radius_key]["rank_population"] = int(order.size)
            ranks = np.empty(order.size, dtype=int)
            ranks[order] = np.arange(1, order.size + 1)
            target_value = corrected[TARGET]
            target_rank = None
            if eligible[TARGET]:
                target_rank = int(np.flatnonzero((coords == TARGET).all(axis=1))[0])
                target_rank = int(ranks[target_rank])
            key = f"{2*radius+1}x{2*radius+1}"
            result["sensitivities"].setdefault(pol, {})[key] = {
                "eligible_class_pixels": int(eligible.sum()),
                "target_raw_change_db": float(delta[TARGET]) if pair_valid[TARGET] else None,
                "target_neighbor_median_db": float(neighbor_median[TARGET]) if eligible[TARGET] else None,
                "target_residual_db": float(target_value) if eligible[TARGET] else None,
                "target_rank_most_negative_first": target_rank,
                "target_rank_fraction": (target_rank / int(eligible.sum())) if target_rank else None,
                "target_paired_neighbor_count": int(support[TARGET]),
                "top_5": [{"row": int(coords[k, 0]), "col": int(coords[k, 1]), "residual_db": float(vals[k])}
                          for k in order[:5]],
            }
            if radius == 2:
                for name, (dr, dc) in CHECKPOINT_OFFSETS.items():
                    r, c = r0+dr, c0+dc
                    cp = result["checkpoints"].setdefault(name, {"row": r, "col": c, "worldcover_code": int(cover[r,c]), "event_window": {}})
                    observable = bool(observation_pair_valid[r,c])
                    class_match = bool(class_mask[r,c])
                    local_eligible = bool(pair_valid[r,c] and np.isfinite(corrected[r,c]))
                    cp["event_window"].setdefault(pol, {})[key] = {
                        "valid_observation_pair": observable,
                        "matches_target_worldcover_class": class_match,
                        "valid_class_pair": bool(observable and class_match),
                        "paired_neighbors": int(support[r,c]) if class_match else None,
                        "raw_change_db": float(delta[r,c]) if observable else None,
                        "neighbor_median_db": float(neighbor_median[r,c]) if local_eligible else None,
                        "residual_db": float(corrected[r,c]) if local_eligible else None,
                    }
    # Fixed checkpoint follow-up: descriptive only and never fed into rankings.
    for name, cp in result["checkpoints"].items():
        r, c = cp["row"], cp["col"]
        cp["followup"] = {}
        for pol, stack in stacks.items():
            cp["followup"][pol] = {d: (float(stack[k,r,c]) if valid[k,r,c] else None)
                                   for k, d in enumerate(dates) if d > AFTER}
    result["data_dates"] = dates
    result["points"] = point_rows
    result["mask_policy"] = "shared validity helper: mask 0/255, non-finite and non-positive HH/HV invalid; WorldCover class 0 excluded"
    result["spatial_caveat"] = "neighboring sampled pixels are spatially dependent observations, not independent events; WorldCover transform is unverified"
    return result


if __name__ == "__main__":
    print(json.dumps(run(), indent=2, allow_nan=False))
