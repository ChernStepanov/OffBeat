#!/usr/bin/env python3
"""Reproducible, offline spatial/temporal NISAR–OPERA comparison for the Amazon site."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/research/cross-sensor.json"
BLOCK = 4
BOOTSTRAPS = 2000
CONTRAST_BOOTSTRAPS = 1000
SEED = 20261115


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def utc_stamp(value):
    return dt.datetime.strptime(value, "%Y%m%dT%H%M%S").replace(tzinfo=dt.timezone.utc)


def corr(x, y):
    x, y = np.asarray(x, float), np.asarray(y, float)
    ok = np.isfinite(x) & np.isfinite(y)
    if ok.sum() < 3 or np.std(x[ok]) == 0 or np.std(y[ok]) == 0:
        return None
    return float(np.corrcoef(x[ok], y[ok])[0, 1])


def date_pairs(l_dates, c_dates, tolerance, unique=True):
    """Nearest date per L acquisition; optionally prohibit reuse of a C acquisition."""
    candidates = []
    for li, ld in enumerate(l_dates):
        for ci, cd in enumerate(c_dates):
            lag = (dt.date.fromisoformat(cd) - dt.date.fromisoformat(ld)).days
            if abs(lag) <= tolerance:
                candidates.append((abs(lag), li, ci, lag))
    if unique:
        chosen = {}
        used_c = set()
        for _, li, ci, lag in sorted(candidates):
            if li not in chosen and ci not in used_c:
                chosen[li] = (ci, lag)
        return [(li, ci, lag) for li, (ci, lag) in sorted(chosen.items())]
    by_l = {}
    for _, li, ci, lag in candidates:
        if li not in by_l or (abs(lag), ci) < (abs(by_l[li][1]), by_l[li][0]):
            by_l[li] = (ci, lag)
    return [(li, ci, lag) for li, (ci, lag) in sorted(by_l.items())]


def block_bootstrap(x, y, cls, rows, cols, n=BOOTSTRAPS, seed=SEED):
    """Resample 4x4 spatial blocks; retain paired sensor/date observations within blocks."""
    x, y, cls = np.asarray(x), np.asarray(y), np.asarray(cls)
    block_ids = (np.asarray(rows) // BLOCK) * 8 + np.asarray(cols) // BLOCK
    blocks = np.unique(block_ids)
    rng = np.random.default_rng(seed)
    vals = []
    for _ in range(n):
        sampled = rng.choice(blocks, len(blocks), replace=True)
        idx = np.concatenate([np.flatnonzero(block_ids == b) for b in sampled])
        vals.append(corr(x[idx], y[idx]))
    vals = np.asarray([v for v in vals if v is not None])
    if not len(vals):
        return {"unit": f"{BLOCK}x{BLOCK} neighboring sample-cell blocks", "blocks": int(len(blocks)), "ci95": None}
    return {"unit": f"{BLOCK}x{BLOCK} neighboring sample-cell blocks; all dates and channels paired within block",
            "blocks": int(len(blocks)), "replicates": n,
            "ci95": [float(np.quantile(vals, .025)), float(np.quantile(vals, .975))],
            "note": "Descriptive spatial uncertainty conditional on these dates/site; not event-level or temporal replication."}


def paired_level_change_bootstrap(level_x, level_y, level_rows, level_cols,
                                  change_x, change_y, change_rows, change_cols,
                                  block_size, n=CONTRAST_BOOTSTRAPS, seed=SEED):
    """Paired spatial bootstrap; identical sampled blocks feed both correlation estimates."""
    nblocks = int(np.ceil(32 / block_size))
    def block_ids(rows, cols):
        return (np.asarray(rows)//block_size)*nblocks + np.asarray(cols)//block_size
    lb, cb = block_ids(level_rows, level_cols), block_ids(change_rows, change_cols)
    blocks = np.arange(nblocks*nblocks)
    rng = np.random.default_rng(seed)
    r_levels, r_changes, contrasts = [], [], []
    for _ in range(n):
        draw = rng.choice(blocks, len(blocks), replace=True)
        li = np.concatenate([np.flatnonzero(lb == b) for b in draw])
        ci = np.concatenate([np.flatnonzero(cb == b) for b in draw])
        rl = corr(np.asarray(level_x)[li], np.asarray(level_y)[li])
        rc = corr(np.asarray(change_x)[ci], np.asarray(change_y)[ci])
        if rl is not None and rc is not None:
            r_levels.append(rl); r_changes.append(rc); contrasts.append(rl-rc)
    return {"block_cells_per_side":block_size,"approx_sample_spacing_m":87,
            "approx_block_width_m":round(block_size*87),"spatial_blocks":int(len(blocks)),
            "replicates_requested":n,"replicates_valid":len(contrasts),"seed":seed,
            "paired_same_block_draw_for_level_and_change":True,
            "resampling_unit":"spatial blocks; all dates and intervals for each point retained together",
            "point_estimates":{"r_levels":corr(level_x,level_y),"r_changes":corr(change_x,change_y),
                               "contrast_r_levels_minus_r_changes":corr(level_x,level_y)-corr(change_x,change_y)},
            "ci95":{"r_levels":np.quantile(r_levels,[.025,.975]).tolist() if r_levels else None,
                    "r_changes":np.quantile(r_changes,[.025,.975]).tolist() if r_changes else None,
                    "contrast_r_levels_minus_r_changes":np.quantile(contrasts,[.025,.975]).tolist() if contrasts else None},
            "interpretation":"Spatial-sampling interval conditional on this site and six NISAR acquisitions; not temporal/event uncertainty or an iid-pixel interval."}


def build():
    site_path = ROOT / "data/amazon.json"
    rtc_path = ROOT / "data/amazon/sentinel1.json"
    manifest_path = ROOT / "data/amazon-manifest.json"
    sidecar_paths = [ROOT / "data/subsets/amazon-dense" / f"{d}.json" for d in
                     ("2026-07-18", "2026-08-11", "2026-08-23", "2026-09-04", "2026-09-16", "2026-09-28")]
    site, rtc, manifest = [json.loads(p.read_text()) for p in (site_path, rtc_path, manifest_path)]
    sidecars = {x["date"]: x for x in (json.loads(p.read_text()) for p in sidecar_paths)}
    pixels = site["pixels"]
    coords = [(p["lat"], p["lon"]) for p in pixels]
    coords_hash = hashlib.sha256(json.dumps(coords).encode()).hexdigest()
    # Validate both IDs and geographic positions against the declared regular 32x32 sample grid.
    n = site["grid"]["n"]
    bbox = site["grid"]["bbox"]
    step_lat, step_lon = (bbox["n"]-bbox["s"])/n, (bbox["e"]-bbox["w"])/n
    for index, pixel in enumerate(pixels):
        row, col = divmod(index, n)
        expected_id = f"AMA r{row} c{col}"
        expected_lat = bbox["n"] - (row + .5) * step_lat
        expected_lon = bbox["w"] + (col + .5) * step_lon
        if pixel["id"] != expected_id or abs(pixel["lat"]-expected_lat) > 1e-10 or abs(pixel["lon"]-expected_lon) > 1e-10:
            raise ValueError(f"NISAR sample ID/coordinate/grid mismatch at ordered index {index}")
    # RTC stores no coordinate or ID array. Its documented extraction order plus this hash
    # binds values to these IDs/coordinates; this is not per-cell geolocation validation.
    if rtc["provenance"]["points_sha256"] != coords_hash:
        raise ValueError("OPERA sample coordinate hash does not match NISAR coordinate order")
    if len(pixels) != 1024 or any(len(r) != len(pixels) for b in ("vv", "vh") for r in rtc["points"][b]):
        raise ValueError("Unexpected point-array shape")
    classes = np.array([p["cover"] if p["cover"] in (10, 30) else -1 for p in pixels])
    if np.any(classes < 0):
        raise ValueError("Unexpected/unknown WorldCover class in selected sample")
    rows = np.repeat(np.arange(32), 32)
    cols = np.tile(np.arange(32), 32)
    ldates, cdates = site["dates"], rtc["dates"]
    granules_by_date = {}
    for g in rtc["provenance"]["granules"]:
        granules_by_date.setdefault(g["date"], []).append(g["id"])
    rtc_times_by_date = {}
    for date, granules in granules_by_date.items():
        times=[]
        for granule in granules:
            match=re.search(r"_(\d{8}T\d{6})Z_", granule)
            if match:
                times.append({"granule_id":granule,"acquisition_utc":utc_stamp(match.group(1)).isoformat().replace("+00:00","Z")})
        rtc_times_by_date[date]=times
    nisar_times={d:sc["source"]["start"] for d,sc in sidecars.items()}
    # Per-date/per-class medians over shared valid coordinates. Daily values stay sensor-specific.
    series = {}
    for lname, lkey, ckey in (("HV_vs_VH", "hv", "vh"), ("HH_vs_VV", "hh", "vv")):
        larr = np.array([[np.nan if v is None else v for v in p[lkey]] for p in pixels], float)
        carr = np.array(rtc["points"][ckey], float).T
        if not np.isfinite(carr).all():
            carr[~np.isfinite(carr)] = np.nan
        perdate = []
        for li, ld in enumerate(ldates):
            # Retain each nearest RTC date within 12d (including ties) for transparent descriptive matching.
            nearest = min(range(len(cdates)), key=lambda j: (abs((dt.date.fromisoformat(cdates[j])-dt.date.fromisoformat(ld)).days), cdates[j]))
            lag = (dt.date.fromisoformat(cdates[nearest])-dt.date.fromisoformat(ld)).days
            valid = np.isfinite(larr[:, li]) & np.isfinite(carr[:, nearest])
            entry = {"nisar_date": ld, "rtc_date": cdates[nearest], "lag_days_rtc_minus_nisar": lag,
                     "rtc_granules": granules_by_date.get(cdates[nearest], []), "valid_shared_points": int(valid.sum()),
                     "class_medians": {}}
            entry["nisar_acquisition_start_utc"] = nisar_times.get(ld)
            entry["rtc_acquisition_times_utc"] = rtc_times_by_date.get(cdates[nearest], [])
            if entry["nisar_acquisition_start_utc"] and entry["rtc_acquisition_times_utc"]:
                nis_start=dt.datetime.fromisoformat(entry["nisar_acquisition_start_utc"].replace("Z","+00:00"))
                exact_lags=[(dt.datetime.fromisoformat(t["acquisition_utc"].replace("Z","+00:00"))-nis_start).total_seconds()/3600 for t in entry["rtc_acquisition_times_utc"]]
                entry["catalogue_granule_utc_lag_hours_range"]=[min(exact_lags),max(exact_lags)]
            entry["utc_lag_scope"]="Granule-level range only; actual contributing OPERA burst per point is not recorded."
            for code, label in ((10, "tree_cover"), (30, "grassland")):
                m = valid & (classes == code)
                entry["class_medians"][label] = {"n": int(m.sum()), "nisar_db": float(np.median(larr[m, li])) if m.any() else None,
                                                  "opera_db": float(np.median(carr[m, nearest])) if m.any() else None}
            perdate.append(entry)
        series[lname] = {"nisar_band": lkey.upper(), "opera_band": ckey.upper(), "per_date_nearest_12d": perdate}

    # Matched pairs: unique C date per L date avoids silently reusing a C observation.
    pairing = {}
    match_by_tolerance = {}
    for tol in (0, 3, 6, 12):
        pairs = date_pairs(ldates, cdates, tol, unique=True)
        match_by_tolerance[str(tol)] = [{"nisar_date": ldates[i], "rtc_date": cdates[j], "lag_days_calendar": lag,
                                         "nisar_acquisition_start_utc":nisar_times.get(ldates[i]),
                                         "rtc_granules": granules_by_date.get(cdates[j], []),
                                         "rtc_acquisition_times_utc":rtc_times_by_date.get(cdates[j], []),
                                         "utc_lag_scope":"Granule-level only; no per-point source granule."} for i,j,lag in pairs]
    # Primary descriptive comparison uses 6d unique pairs; shared coordinates and class labels.
    primary = date_pairs(ldates, cdates, 6, unique=True)
    analyses = {}
    for label, lkey, ckey in (("HV_vs_VH", "hv", "vh"), ("HH_vs_VV", "hh", "vv")):
        larr = np.array([[np.nan if v is None else v for v in p[lkey]] for p in pixels], float)
        carr = np.array(rtc["points"][ckey], float).T
        xparts=[]; yparts=[]; cparts=[]; rparts=[]; kparts=[]; dtparts=[]
        for li,ci,_ in primary:
            valid=np.isfinite(larr[:,li]) & np.isfinite(carr[:,ci])
            ids=np.flatnonzero(valid)
            xparts.extend(larr[ids,li]); yparts.extend(carr[ids,ci]); cparts.extend(classes[ids]);
            rparts.extend(rows[ids]); kparts.extend(cols[ids]); dtparts.extend([li]*len(ids))
        x=np.asarray(xparts); y=np.asarray(yparts); cl=np.asarray(cparts); rr=np.asarray(rparts); cc=np.asarray(kparts)
        # Within-class centering uses each class-date median independently for each sensor.
        xc=x.copy(); yc=y.copy()
        for t in np.unique(dtparts):
            mask=np.asarray(dtparts)==t
            for code in (10,30):
                m=mask & (cl==code)
                if m.any(): xc[m]-=np.median(x[m]); yc[m]-=np.median(y[m])
        # Contrast within class after removing per-date class medians: correlation is spatial co-variation.
        analyses[label]={"matched_observation_count":int(len(x)), "matched_date_count":len(primary),
                         "pooled_level_correlation":corr(x,y), "within_class_and_date_centered_correlation":corr(xc,yc),
                         "classwise_level_correlations":{name:corr(x[cl==code],y[cl==code]) for code,name in ((10,"tree_cover"),(30,"grassland"))},
                         "spatial_block_bootstrap_pooled":block_bootstrap(x,y,cl,rr,cc),
                         "interpretation": "Sensor polarizations differ (HH/HV vs VV/VH); association is descriptive, not wavelength effect."}
        # Pair-to-pair temporal deltas per coordinate (first differencing consecutive matched L dates).
        dx=[];dy=[];dclass=[];drow=[];dcol=[];dinterval=[]
        for interval,((li0,ci0,_),(li1,ci1,_)) in enumerate(zip(primary,primary[1:])):
            good=np.isfinite(larr[:,li0])&np.isfinite(larr[:,li1])&np.isfinite(carr[:,ci0])&np.isfinite(carr[:,ci1])
            ids=np.flatnonzero(good)
            dx.extend(larr[ids,li1]-larr[ids,li0]); dy.extend(carr[ids,ci1]-carr[ids,ci0]); dclass.extend(classes[ids]); drow.extend(rows[ids]); dcol.extend(cols[ids]); dinterval.extend([interval]*len(ids))
        analyses[label]["consecutive_matched_change_correlation"] = corr(dx,dy)
        analyses[label]["change_observation_count"] = len(dx)
        analyses[label]["change_block_bootstrap"] = block_bootstrap(dx,dy,dclass,drow,dcol,seed=SEED+1) if dx else None
        dx_arr,dy_arr,dc_arr,di_arr=np.asarray(dx),np.asarray(dy),np.asarray(dclass),np.asarray(dinterval)
        dx_centered,dy_centered=dx_arr.copy(),dy_arr.copy()
        for interval in np.unique(di_arr):
            for code in (10,30):
                m=(di_arr==interval)&(dc_arr==code)
                if m.any():
                    dx_centered[m]-=np.median(dx_arr[m]); dy_centered[m]-=np.median(dy_arr[m])
        analyses[label]["class_and_interval_centered_change_correlation"]=corr(dx_centered,dy_centered)
        analyses[label]["level_change_contrast_spatial_bootstrap"]={str(size):paired_level_change_bootstrap(
            x,y,rr,cc,dx,dy,drow,dcol,size,seed=SEED+size) for size in (2,4,8)}

    # Long C-band history: class/date medians and within-class detrended annual phase contrast.
    season = {}
    for code,name in ((10,"tree_cover"),(30,"grassland")):
        ids=np.flatnonzero(classes==code)
        med=[]
        for j,d in enumerate(cdates):
            v=np.asarray(rtc["points"]["vh"][j],float)[ids]
            med.append({"date":d,"median_db":float(np.nanmedian(v)),"n":int(np.isfinite(v).sum())})
        bymonth={m:float(np.median([x["median_db"] for x,d in zip(med,cdates) if dt.date.fromisoformat(d).month==m])) for m in range(1,13)}
        season[name]={"date_count":len(med),"monthly_median_of_date_medians_db":bymonth,
                      "monthly_range_db":max(bymonth.values())-min(bymonth.values()),"per_date":med}

    ablations=[]
    for tol in (0,3,6,12):
        pairs=date_pairs(ldates,cdates,tol,unique=True)
        ablations.append({"name":f"unique_nearest_temporal_tolerance_{tol}d","matched_date_count":len(pairs),
                          "matched_pairs":[{"nisar":ldates[i],"opera":cdates[j],"lag_days":lag} for i,j,lag in pairs],
                          "purpose":"Sensitivity to temporal mismatch; each C acquisition used at most once."})
    ablations.extend([
        {"name":"polarization_channel_pair","result_keys":["HV_vs_VH","HH_vs_VV"],"purpose":"Do not treat cross-pol HV/VH as equivalent to co-pol HH/VV or across sensors."},
        {"name":"absolute_levels_vs_consecutive_changes","result_keys":["pooled_level_correlation","consecutive_matched_change_correlation"],"purpose":"Separate spatially persistent brightness/class association from temporal co-change."},
        {"name":"within_class_and_date_centering","result_keys":["pooled_level_correlation","within_class_and_date_centered_correlation"],"purpose":"Remove class/date location offsets to test class confounding / Simpson-like reversal."},
        {"name":"within_class_and_interval_change_centering","result_keys":["consecutive_matched_change_correlation","class_and_interval_centered_change_correlation"],"purpose":"Remove common class-specific shift in each consecutive interval before correlating pointwise changes."},
        {"name":"paired_spatial_bootstrap_level_minus_change","result_keys":["level_change_contrast_spatial_bootstrap"],"purpose":"For each replicate, use the identical spatial block draw to compute r(levels), r(changes), and their difference."},
        {"name":"shared_valid_coordinates_only","purpose":"Pairwise finite values at same ordered coordinate; reports counts; does not impute missing data."},
        {"name":"spatial_block_bootstrap_4x4","purpose":"Paired spatial blocks, retaining all temporal/channel measurements per block; no pixel-iid inference."},
        {"name":"long_OPERA_history_monthly_class_medians","purpose":"86 dates supply seasonal context but months mix years; descriptive only, not a validated seasonal model."},
    ])
    findings=[]
    for key,a in analyses.items():
        pooled=a["pooled_level_correlation"]; centered=a["within_class_and_date_centered_correlation"]
        if pooled is not None and centered is not None:
            findings.append({"id":key+"_class_confounding_check","pooled_r":pooled,"centered_r":centered,
                             "description":"Pooled association compared with class- and date-centered spatial association; attenuation/reversal indicates composition confounding, not causal mechanism."})
        findings.append({"id":key+"_temporal_change_check","change_r":a["consecutive_matched_change_correlation"],
                         "description":"Correlation of consecutive matched-date changes; only adjacent date intervals in this single site, exploratory."})
    # Short, independently readable matching report.
    output={"study":"Amazon NISAR L-band vs OPERA Sentinel-1 C-band; spatial/temporal association and class confounding",
            "generated_at":"reproducible deterministic computation; no network access",
            "inputs":[{"path":p.relative_to(ROOT).as_posix(),"sha256":sha(p)} for p in (site_path,rtc_path,manifest_path,*sidecar_paths)],
            "metadata":{"nisar_collection":"NISAR L2 GCOV PROVISIONAL; track 146/frame 175 ascending per data/amazon-manifest.json",
                        "nisar_dates":ldates,"nisar_pol":"HH/HV","opera_collection":rtc["collection"],"opera_dates_count":len(cdates),
                        "opera_date_range":[cdates[0],cdates[-1]],"opera_pol":"VV/VH","opera_granules_count":len(rtc["provenance"]["granules"]),
                        "opera_orbit_track_metadata":"per-granule orbit/track not in sidecar; not inferred; granule IDs retained for matched dates",
                        "worldcover":{"version":"2021 v200","class_counts":{"10_tree_cover":int((classes==10).sum()),"30_grassland":int((classes==30).sum())}},
                        "coordinates":{"count":len(coords),"matching":"Validated each NISAR ID and lat/lon against declared 32x32 grid; verified ordered lat/lon SHA-256 equals OPERA points_sha256. OPERA coordinates/IDs are not stored per point; order contract is required.","coordinate_sha256":coords_hash,
                                      "assertions":"AMA row/column ID, grid-derived cell-center lat/lon, 1024 array length, and ordered coordinate hash."},
                        "acquisition_times":{"nisar":"UTC start times from data/subsets/amazon-dense/<date>.json source metadata; these sidecars identify the same acquisition granules in the series.","opera":"UTC acquisition timestamp parsed from each granule ID; all per-date burst granules included","precision":"Granule-level UTC timestamps are available, but actual per-point contributing burst is unknown; exact per-point lag is therefore unavailable."},
                        "radiometry":{"nisar":"GCOV gamma0, HH/HV, positive power to 10log10, source masks 0/255 rejected during extraction; only stored valid/null values consumed here.",
                                      "opera":"RTC-S1 gamma0 VV/VH dB, per scripts/opera_rtc.py uses VV/VH assets and 10log10(linear power); no sigma0 auxiliary used.",
                                      "quality":"No saved per-point RTC quality mask or contributing burst; finite values are not equivalent to verified quality/geometry."},
                        "masks":"Analysis only requires finite, shared point values; no additional per-point geometry/quality mask can be applied from the stored RTC JSON."},
            "method":{"matching":"Nearest calendar date per NISAR acquisition, with unique RTC date assignments for tolerance analyses; ID+lat/lon grid and ordered hash checks; no interpolation; primary tolerance 6 days. UTC granule ranges are reported separately, not assigned to pixels.",
                      "temporal_tolerances_days":[0,3,6,12],"primary_tolerance_days":6,"bootstrap":{"replicates":BOOTSTRAPS,"seed":SEED,"block_cells":[BLOCK,BLOCK],"unit":"spatial blocks; paired coordinates and dates, not independent pixels",
                                  "contrast_replicates":CONTRAST_BOOTSTRAPS,"contrast_block_sizes_cells":[2,4,8],"contrast_seed_rule":"base seed + block size; identical block draw used for level/change correlation within each replicate"},
                      "level_correlation":"pooled point-date observations; centered by WorldCover class AND acquisition-date median within each sensor before spatial correlation.",
                      "change":"per-coordinate consecutive differences over successive matched pairs; changes overlap in coordinates and temporal intervals; temporal sample size is number of dates, not point-date rows."},
            "summary":{"matched_unique_pairs_at_6d":len(primary),"paired_point_date_rows":analyses["HV_vs_VH"]["matched_observation_count"],
                       "primary_HV_VH_pooled_r":analyses["HV_vs_VH"]["pooled_level_correlation"],
                       "primary_HV_VH_centered_r":analyses["HV_vs_VH"]["within_class_and_date_centered_correlation"],
                       "primary_HV_VH_change_r":analyses["HV_vs_VH"]["consecutive_matched_change_correlation"]},
            "findings":findings,"matching":{"by_tolerance_days":match_by_tolerance,"nearest_12d_class_series":series},
            "analyses":analyses,"long_C_band_seasonality":{"band":"VH", "class":season},"ablations":ablations,
            "limitations":["One small study window/site; 1024 spatially autocorrelated sample locations are not independent events.",
                            "NISAR has six acquisitions; C-band dates do not create additional independent NISAR temporal observations.",
                            "L- and C-band polarization channels are not equivalent; frequency effects cannot be isolated from polarization, orbit, incidence geometry, resolution, processor and date.",
                            "RTC points have no per-point contributing-granule receipt or saved per-point quality/geometry mask; a date can combine bursts/versions in first-valid order. Granule-level UTC timestamp ranges cannot establish each point's actual lag or geometry.",
                            "Date matching uses calendar dates; UTC granule timestamps are separately recorded, but no per-point timestamp exists for the selected RTC value.",
                            "Difference between class/date medians is not treated as the median of paired pointwise differences; change correlations are computed from paired pointwise differences.",
                            "WorldCover 2021 is historical; class-30 grassland is not verified pasture.",
                            "No independent event labels; do not infer clearing, event detection accuracy, causation or wavelength superiority.",
                            "Monthly C-band medians pool years and can confound season with trend, orbit/track or acquisition geometry; not a fitted seasonal decomposition."]}
    return output


def main():
    result=build()
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(result,indent=2,sort_keys=True,allow_nan=False)+"\n",encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}; primary pairs={result['summary']['matched_unique_pairs_at_6d']}; "
          f"HV/VH pooled={result['summary']['primary_HV_VH_pooled_r']}, centered={result['summary']['primary_HV_VH_centered_r']}")


if __name__=="__main__": main()
