"""Dense-grid sensitivity study of the local Amazon NISAR time series (offline)."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import numpy as np
from scipy.ndimage import median_filter

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data/subsets/amazon-dense"
DATES = ["2026-07-18", "2026-08-11", "2026-08-23", "2026-09-04", "2026-09-16", "2026-09-28"]
SEED = 741903


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def valid_power(a):
    return (a["mask"] > 0) & (a["mask"] < 255) & np.isfinite(a["hh"]) & np.isfinite(a["hv"]) & (a["hh"] > 0) & (a["hv"] > 0)


def db(power):
    out = np.full(power.shape, np.nan, dtype=np.float64)
    ok = np.isfinite(power) & (power > 0)
    out[ok] = 10 * np.log10(power[ok])
    return out


def stats(x):
    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x)]
    if not x.size:
        return {"n": 0}
    return {"n": int(x.size), "median": round(float(np.median(x)), 4), "mean": round(float(np.mean(x)), 4),
            "p10": round(float(np.percentile(x, 10)), 4), "p90": round(float(np.percentile(x, 90)), 4),
            "negative_fraction": round(float(np.mean(x < 0)), 5)}


def require_complete_masks(masks, operation):
    if not np.all(masks):
        raise ValueError(f"{operation} requires complete valid masks; use a mask-aware implementation or complete-case input")


def linear_mean_ratio_db(arr_db, masks, pre_indices=(0, 1, 2), post_indices=(3, 4, 5)):
    """Mask-aware log ratio of per-period arithmetic means in linear power."""
    linear = np.power(10.0, arr_db / 10.0)

    def masked_mean(indices):
        valid = masks[list(indices)] & np.isfinite(linear[list(indices)])
        count = valid.sum(axis=0)
        total = np.where(valid, linear[list(indices)], 0.0).sum(axis=0)
        return np.divide(total, count, out=np.full(count.shape, np.nan, dtype=float), where=count > 0)

    before, after = masked_mean(pre_indices), masked_mean(post_indices)
    valid = np.isfinite(before) & np.isfinite(after) & (before > 0) & (after > 0)
    out = np.full(before.shape, np.nan, dtype=float)
    out[valid] = 10 * np.log10(after[valid] / before[valid])
    return out


def validate_peer_grid(z, peer_dates, peer_grid, expected_dates, expected_grid, expected_shape):
    assert peer_dates == expected_dates, f"peer-z dates mismatch: {peer_dates} != {expected_dates}"
    if tuple(z.shape) != (len(expected_dates), *expected_shape):
        raise ValueError(f"peer-z shape mismatch: {z.shape}")
    if peer_grid != expected_grid:
        raise ValueError("peer-z grid metadata mismatch")


def peer_complete_mask(forest, z):
    return forest & np.isfinite(z).all(axis=0)


def spatial_bootstrap(values, valid, block_px, rng, reps=2000):
    """Resample non-overlapping spatial blocks; CI is descriptive for this one clipped grid."""
    h, w = valid.shape
    blocks = []
    for r in range(0, h, block_px):
        for c in range(0, w, block_px):
            m = valid[r:min(r + block_px, h), c:min(c + block_px, w)]
            v = values[r:min(r + block_px, h), c:min(c + block_px, w)]
            v = v[m & np.isfinite(v)]
            if v.size:
                blocks.append(v)
    if len(blocks) < 5:
        return {"block_px": block_px, "block_count": len(blocks), "ci95": None, "warning": "fewer than five spatial blocks"}
    sampled = rng.integers(0, len(blocks), size=(reps, len(blocks)))
    means = np.array([np.concatenate([blocks[i] for i in row]).mean() for row in sampled])
    return {"block_px": block_px, "block_m": block_px * 20, "block_count": len(blocks),
            "mean_ci95": [round(float(x), 4) for x in np.percentile(means, [2.5, 97.5])],
            "resampling": "iid resampling of non-overlapping blocks with replacement; descriptive, block-boundary and finite-window limitations remain"}


def run():
    records, hh, hv, masks, provenance = [], [], [], [], []
    for day in DATES:
        mp = DATA / f"{day}.json"
        meta = json.loads(mp.read_text())
        p = ROOT / meta["subset_path"]
        if sha(p) != meta["sha256"]:
            raise ValueError(f"input hash mismatch: {p}")
        with np.load(p) as archive:
            a = {k: archive[k].copy() for k in ("hh", "hv", "mask")}
        records.append(meta)
        hh.append(db(a["hh"]))
        hv.append(db(a["hv"]))
        masks.append(valid_power(a))
        provenance.extend([{"path": mp.relative_to(ROOT).as_posix(), "sha256": sha(mp)}, {"path": p.relative_to(ROOT).as_posix(), "sha256": sha(p)}])
    hh, hv, masks = np.stack(hh), np.stack(hv), np.stack(masks)
    common = masks.all(axis=0)
    if not all(x["grid"] == records[0]["grid"] for x in records):
        raise ValueError("grid metadata differ")
    g = records[0]["grid"]
    if any(x.shape != (141, 141) for x in [common]):
        raise ValueError("unexpected dense grid shape")

    cp = DATA / "worldcover-2021.json"
    cm = json.loads(cp.read_text()); coverpath = ROOT / cm["subset_path"]
    if sha(coverpath) != cm["sha256"]:
        raise ValueError("WorldCover hash mismatch")
    with np.load(coverpath) as a:
        cover = a["cover"].copy()
    provenance.extend([{"path": cp.relative_to(ROOT).as_posix(), "sha256": sha(cp)}, {"path": coverpath.relative_to(ROOT).as_posix(), "sha256": sha(coverpath)}])
    forest = common & (cover == 10)
    pre = slice(0, 3)
    post = slice(3, 6)
    baseline_hh = np.nanmedian(np.where(masks[:3], hh[:3], np.nan), axis=0)
    baseline_hv = np.nanmedian(np.where(masks[:3], hv[:3], np.nan), axis=0)
    chh = hh - baseline_hh
    chv = hv - baseline_hv
    chh[:, ~common] = np.nan; chv[:, ~common] = np.nan
    combined = np.nanmedian(np.stack([chh, chv]), axis=0)
    post3hh = np.nanmedian(chh[3:], axis=0); post3hv = np.nanmedian(chv[3:], axis=0)
    post3 = np.nanmedian(np.stack([post3hh, post3hv]), axis=0)

    # Median change in dB is not the same estimator as log10 of linear-power means.
    raw = {}
    for band, arr in (("HH", hh), ("HV", hv)):
        med_delta = np.nanmedian(arr[3:], axis=0) - np.nanmedian(arr[:3], axis=0)
        paired_delta = np.nanmedian(np.stack([arr[3]-arr[0], arr[4]-arr[1], arr[5]-arr[2]]), axis=0)
        linear_mean = linear_mean_ratio_db(arr, masks)
        raw[band] = {"median_of_date_dB_difference": stats(med_delta[common]),
                     "median_of_three_paired_post_minus_pre_dB_differences": stats(paired_delta[common]),
                     "paired_dates": [[DATES[0], DATES[3]], [DATES[1], DATES[4]], [DATES[2], DATES[5]]],
                     "dB_of_linear_mean_ratio": stats(linear_mean[common]),
                     "median_minus_linear_mean_pixelwise_db": stats((med_delta-linear_mean)[common])}

    rng = np.random.default_rng(SEED)
    bootstrap = [spatial_bootstrap(post3, forest, n, rng) for n in (10, 20, 40)]
    thresholds = []
    post3_per_date = np.stack([chh[3:], chv[3:]], axis=0)  # band x three dates x grid
    for t in (1, 2, 3, 4, 5):
        hhit = np.sum(chh[3:] <= -t, axis=0)
        hvit = np.sum(chv[3:] <= -t, axis=0)
        both = forest & (hhit >= 2) & (hvit >= 2)
        late_persistent = forest & (chh[4] <= -t) & (chh[5] <= -t) & (chv[4] <= -t) & (chv[5] <= -t)
        thresholds.append({"threshold_db": t, "forest_cells_both_bands_at_least_2_of_3_post_dates": int(both.sum()),
                           "forest_fraction": round(float(both.sum()/forest.sum()), 5) if forest.any() else None,
                           "forest_cells_both_bands_below_threshold_on_both_2026_09_16_and_2026_09_28": int(late_persistent.sum()),
                           "late_persistent_forest_fraction": round(float(late_persistent.sum()/forest.sum()), 5) if forest.any() else None,
                           "area_km2_nominal": round(float(both.sum()*abs(g["x_step"]*g["y_step"])/1e6), 5),
                           "definition": "each HH and HV independently at least 2 of dates 2026-09-04/16/28 <= pre-period (Jul18/Aug11/Aug23 median dB) - threshold; 2021 WorldCover class 10"})

    persistence = {}
    for i in range(3, 6):
        persistence[DATES[i]] = {"HH": stats(chh[i][forest]), "HV": stats(chv[i][forest]),
                                 "both_negative_fraction": round(float(np.mean((chh[i][forest] < 0) & (chv[i][forest] < 0))), 5)}
    agreement = forest & np.isfinite(post3hh) & np.isfinite(post3hv)
    agree_sign = (post3hh[agreement] * post3hv[agreement]) > 0
    pol = {"forest_n": int(agreement.sum()), "same_sign_fraction": round(float(agree_sign.mean()), 5),
           "both_negative_fraction": round(float(np.mean((post3hh[agreement] < 0) & (post3hv[agreement] < 0))), 5),
           "HH_HV_correlation": round(float(np.corrcoef(post3hh[agreement], post3hv[agreement])[0,1]), 5)}

    # Neighborhood median filtering is applied to per-date dB, then temporal contrasts are formed.
    smoothing = []
    require_complete_masks(masks, "spatial median-filter ablation")
    for size in (1, 3, 5, 9):
        if size == 1:
            filtered_hh, filtered_hv = hh.copy(), hv.copy()
        else:
            filtered_hh = np.stack([median_filter(x, size=size, mode="nearest") for x in hh])
            filtered_hv = np.stack([median_filter(x, size=size, mode="nearest") for x in hv])
        dh = np.nanmedian(filtered_hh[3:], axis=0)-np.nanmedian(filtered_hh[:3], axis=0)
        dv = np.nanmedian(filtered_hv[3:], axis=0)-np.nanmedian(filtered_hv[:3], axis=0)
        m = forest & np.isfinite(dh) & np.isfinite(dv)
        smoothing.append({"window_cells": size, "window_m": size*20,
                          "HH_delta": stats(dh[m]), "HV_delta": stats(dv[m]),
                          "both_bands_le_minus_3db_fraction": round(float(np.mean((dh[m] <= -3)&(dv[m] <= -3))), 5),
                          "edge_policy": "scipy median_filter mode=nearest; clipped-window edge values included; not an area-corrected estimate"})

    # Compare against the existing 1-km same-class peer z as an alternate spatial reference, not labels.
    zp = ROOT / "data/subsets/amazon-dense/peer-z.npz"
    zmeta_path = ROOT / "data/amazon/dense-peer-z.json"
    zm = json.loads(zmeta_path.read_text())
    if sha(zp) != zm["sha256"]:
        raise ValueError("peer z hash mismatch")
    with np.load(zp) as zf:
        z = zf["z"].copy(); peer_dates = zf["dates"].tolist()
    validate_peer_grid(z, peer_dates, zm.get("grid"), DATES, g, common.shape)
    provenance.extend([{"path": zp.relative_to(ROOT).as_posix(), "sha256": sha(zp)}, {"path": zmeta_path.relative_to(ROOT).as_posix(), "sha256": sha(zmeta_path)}])
    peer_match = peer_complete_mask(forest, z)
    # Avoid noisy all-NaN warnings on clipped/context-invalid edge cells.
    peer_pre = np.ma.median(np.ma.masked_invalid(z[:3]), axis=0).filled(np.nan)
    peer_post = np.ma.median(np.ma.masked_invalid(z[3:]), axis=0).filled(np.nan)
    peer_change = peer_post-peer_pre
    own_peer = {"n": int(peer_match.sum()), "own_history_post_minus_pre_HV_db": stats(post3hv[peer_match]),
                "same_class_1km_peer_z_post_minus_pre": stats(peer_change[peer_match]),
                "note": "same-class peer-z is a spatial contextual standardization, not ground truth or matched causal control; requires all six peer-z dates"}

    # Boundary/coverage and class support, with no extrapolation from this clipped patch.
    edge = np.zeros(common.shape, bool); edge[[0,-1],:] = True; edge[:,[0,-1]] = True
    class_support = []
    for cls in sorted(int(v) for v in np.unique(cover) if v != 0):
        cmask = common & (cover == cls)
        if cmask.any():
            class_support.append({"worldcover_2021_class": cls, "valid_cells": int(cmask.sum()), "grid_fraction": round(float(cmask.sum()/common.sum()), 5),
                                 "post3_HV_change": stats(post3hv[cmask]), "both_band_negative_fraction": round(float(np.mean((post3hh[cmask]<0)&(post3hv[cmask]<0))),5)})
    quality = {"grid_shape": list(common.shape), "grid_cell_m": [abs(g["x_step"]), abs(g["y_step"])],
               "total_cells": int(common.size), "valid_all_six_both_bands": int(common.sum()),
               "valid_fraction": round(float(common.mean()), 5), "valid_fraction_per_date": [round(float(m.mean()),5) for m in masks],
               "outermost_row_or_column_cells": int((common&edge).sum()), "worldcover_forest_cells_class10": int(forest.sum()),
               "nominal_grid_footprint_km2": round(float(common.sum()*abs(g["x_step"]*g["y_step"])/1e6),5),
               "warning": "bbox sample footprint only; not contiguous AOI coverage and not event area"}
    ids = [r["source"]["id"] for r in records]
    track_frame = [re.search(r"GCOV_\d+_(\d+)_([A-Z])_(\d+)_", x).groups() for x in ids]
    processing_suffix = [re.search(r"_(P\d+_[A-Z]_[A-Z]_[A-Z]_\d+)$", x).group(1) for x in ids]
    if len(set(track_frame)) != 1 or len(set(processing_suffix)) != 1:
        raise ValueError("track/frame or processing-generation suffix differs across dates")
    result = {
        "study": "Amazon dense native-grid temporal robustness, NISAR provisional GCOV",
        "finding": "Dense-grid, retrospective descriptive result; no independent event truth. See report for the robust finding/contradiction, not an event label.",
        "dates": DATES, "acquisition_intervals_utc": [{"date": d, "start": r["source"]["start"], "end": r["source"]["end"], "granule": r["source"]["id"]} for d,r in zip(DATES,records)],
        "matching": {"grid": g, "alignment": "all six metadata-identical native 20m EPSG:32722 grids; date masks and positive finite HH/HV; paired complete-case intersection", "valid_cells": int(common.sum()), "dates": DATES,
                      "sparse_32x32_to_dense_141x141_join": "not performed: different geometries/supports; no index-based join. No sparse cells or candidates enter dense statistics.",
                      "dense_receipt_audit": {"track_orbit_frame_tokens": {"track": track_frame[0][0], "orbit_direction": track_frame[0][1], "frame": track_frame[0][2]},
                                              "common_product_processing_id_suffix": processing_suffix[0],
                                              "acquisition_sequence_tokens": [re.search(r"GCOV_(\d+)_", x).group(1) for x in ids],
                                              "grid_metadata_identical": True,
                                              "qualification": "common ID suffix and track/frame are consistent; local subset receipts do not expose a separate software build/version field, so processing equivalence beyond ID tokens is unverified"}},
        "definitions": {"dB": "10*log10(linear gamma0 power)", "own_history": "per-date dB minus pixelwise median of 2026-07-18, 2026-08-11, 2026-08-23", "post_summary": "per-pixel median across 2026-09-04, 2026-09-16, 2026-09-28", "window_filter": "spatial median in dB independently per date, then temporal median difference", "threshold": "threshold sweep uses each polarization separately; >=2/3 post dates, both HH and HV, WorldCover 2021 class 10", "paired_temporal_ablation": "median of paired dB after-before differences for pairs 2026-07-18→09-04, 08-11→09-16, 08-23→09-28; distinct from median(after)-median(before); date lags 48,36,36 days", "seed": SEED},
        "provenance": {"inputs": provenance, "grid_m": [20,20], "mask_policy": "mask 1..254, positive finite HH/HV; all six dates required for primary complete-case estimates"},
        "quality": quality, "all_grid_change": {"HH_3post_median_minus_3pre_median_db": stats(post3hh[common]), "HV_3post_median_minus_3pre_median_db": stats(post3hv[common]), "band_median_combined_db": stats(post3[common]), "forest_class10_HH": stats(post3hh[forest]), "forest_class10_HV": stats(post3hv[forest]), "forest_class10_band_median_combined": stats(post3[forest]), "worldcover_class_support": class_support},
        "persistence_reversion": persistence, "polarization_agreement": pol,
        "threshold_sweep": thresholds, "spatial_block_bootstrap": bootstrap,
        "scale_and_nonlinearity_ablation": {"per_band": raw, "spatial_median_windows": smoothing, "warning": "dB median and logarithm of linear arithmetic mean are distinct estimands; neither has been selected as a ground-truth optimum"},
        "own_history_vs_same_class": own_peer,
        "context": {"worldcover": "2021 nearest-neighbour sampled to same native grid; class is stale relative to 2026 and only stratification", "alerts_fires_era5": "not used as labels; local archives not complete. ERA5 is coarse single-cell context and cannot identify pixel events; omit from primary inference."},
        "limitations": ["one clipped 141x141 native-grid window, not wall-to-wall area; neighboring cells are spatially dependent", "retrospective thresholds and descriptive analyses; no preregistration", "provisional GCOV; seasonal, moisture, geometry and processing effects remain", "same track/frame and product ID suffix, but no explicit software build/version in subset receipts; processing equivalence beyond those tokens unverified", "sparse 32x32 and dense 141x141 supports differ; no index-based join or coordinate crosswalk was attempted", "WorldCover 2021 classes may be stale", "no independent ground truth; candidates are not deforestation, fire, flood or water labels", "spatial bootstrap describes this finite window only and does not create independent sites/events", "peer-z uses same radar time series and class map; it is an alternate spatial reference, not independent validation", "late-return pattern is observational only; no cause (including speckle/artifact) established", "threshold-based late persistence uses the same post observations as candidate selection; regression-to-mean and lack of independent temporal holdout remain"],
    }
    return result


if __name__ == "__main__":
    out = run()
    path = ROOT / "data/research/spatial-robustness.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"quality": out["quality"], "finding": out["all_grid_change"], "persistence": out["persistence_reversion"], "polarization": out["polarization_agreement"], "thresholds": out["threshold_sweep"], "blocks": out["spatial_block_bootstrap"]}, indent=2))
