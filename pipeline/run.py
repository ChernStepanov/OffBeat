"""Run the analysis for a site and write what the web reads.

    .venv/bin/python -m pipeline.run mexico              # real NISAR (needs Earthdata login)
    .venv/bin/python -m pipeline.run mexico --synthetic  # invented inputs on the real grid and land cover

Output in data/<site>/ (format described in export.py).
"""
from __future__ import annotations

import argparse

import numpy as np

from .config import SITES, Site
from .cover import read_cover
from .grid import site_grid
from .peers import peer_stats_blocks, zscore, to_db
from .classify import classify
from .insar import chain_pairs, rate_cm_per_year, decompose, damage_proxy
from . import export


def _nan_mean3(a):
    from scipy.ndimage import uniform_filter
    ok = ~np.isnan(a)
    num, den = uniform_filter(np.where(ok, a, 0.0), 3), uniform_filter(ok.astype(float), 3)
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(ok & (den > 0), num / den, np.nan).astype(np.float32)


def load_real(site: Site, grid):
    from . import nisar  # imported here so synthetic runs work without the reader
    tracks = site.tracks
    primary = tracks[0]
    gcov = [nisar.load_or_read(g, site, "gcov") for g in nisar.search(site, "GCOV", primary)]
    gunw = {}
    for tr in tracks[:2]:
        pairs = [nisar.load_or_read(g, site, "gunw") for g in nisar.search(site, "GUNW", tr)]
        if pairs:
            gunw[tr.track] = pairs
    return gcov, gunw


def analyze(site: Site, cover, gcov: list[dict], gunw: dict[int, list[dict]]):
    gcov = sorted(gcov, key=lambda g: g["date"])
    dates = [g["date"] for g in gcov]
    hh = np.stack([np.where(g["valid"], to_db(g["HHHH"]), np.nan) for g in gcov])
    hv = np.stack([np.where(g["valid"], to_db(g["HVHV"]), np.nan) for g in gcov])

    out = {"dates": dates, "hh": hh, "hv": hv}
    out["hh_med"], out["hh_sd"], out["hh_blocks"] = peer_stats_blocks(hh, cover, site.pixel_m)
    out["hv_med"], out["hv_sd"], out["hv_blocks"] = peer_stats_blocks(hv, cover, site.pixel_m)
    z_hh, z_hv = zscore(hh, out["hh_med"], out["hh_sd"]), zscore(hv, out["hv_med"], out["hv_sd"])

    z_disp = None
    tracks = list(gunw)
    if tracks:
        # displacement of the primary track, put on the GCOV dates
        land = cover != 80
        # reference: stable ground (forest, shrub, bare hills) when there is enough of it, else all land
        stable = np.isin(cover, (10, 20, 60))
        ref = stable if stable.mean() > 0.05 else land
        ddates, dcm = chain_pairs(gunw[tracks[0]], ref_mask=ref)
        disp = np.full(hh.shape, np.nan, np.float32)
        for i, d in enumerate(dates):
            j = int(np.argmin([abs((np.datetime64(d) - np.datetime64(x)).astype(int)) for x in ddates]))
            if abs((np.datetime64(d) - np.datetime64(ddates[j])).astype(int)) <= 6:
                disp[i] = dcm[j]
        out["disp"] = disp
        out["disp_med"], out["disp_sd"], out["disp_blocks"] = peer_stats_blocks(disp, cover, site.pixel_m, sd_floor=1.5)
        # deformation is spatially coherent, single-pixel phase noise is not: smooth z over 3 x 3
        z_disp = np.stack([_nan_mean3(z) for z in zscore(disp, out["disp_med"], out["disp_sd"])])

        if len(tracks) >= 2 and {p[0]["direction"] for p in (gunw[tracks[0]], gunw[tracks[1]])} == {"A", "D"}:
            rates, enus = {}, {}
            for t in tracks[:2]:
                ds, cm = chain_pairs(gunw[t], ref_mask=ref)
                rates[gunw[t][0]["direction"]] = rate_cm_per_year(ds, cm)
                enus[gunw[t][0]["direction"]] = gunw[t][0]["los_enu"]
            out["east"], out["up"] = decompose(rates["A"], enus["A"], rates["D"], enus["D"])

        if site.event:
            pairs = gunw[tracks[0]]
            co = next((p for p in pairs if p["ref"] < site.event <= p["sec"]), None)
            pre = [p for p in pairs if p["sec"] < site.event][-3:]
            if co and pre:
                out["damage"] = damage_proxy(pre, co, cover)
                out["damage_pair"] = (co["ref"], co["sec"])
                # the whole-scene picture: line-of-sight motion across the event, in cm
                good = (co["coherence"] >= 0.3) & (co["conncomp"] > 0) & land
                off = np.nanmedian(co["los_m"][good & (cover != 50)]) if good.any() else 0.0
                out["coseismic"] = np.where(good, (co["los_m"] - off) * 100, np.nan).astype(np.float32)

    out.update(classify(z_hh, z_hv, z_disp))
    return out


def check_clearings(site, grid, res, path, k=2.5, min_cells=3):
    """Score HV-drop patches against INPE DETER / UMD GLAD alerts and FIRMS fires (data/amazon/)."""
    import json
    from scipy.ndimage import label
    from .context_amazon import validate
    folder = path.parent
    if not (folder / "alerts.geojson").exists():
        print("no alerts.geojson: run python -m pipeline.context_amazon first"); return
    fires = json.loads((folder / "fires.json").read_text()) if (folder / "fires.json").exists() else []
    drop = (res["style"] == 1) & (np.abs(res["z"]) >= k)
    lab, n = label(drop)
    patches = []
    for i in range(1, n + 1):
        m = lab == i
        if m.sum() < min_cells:
            continue
        since = int(np.median(res["since"][m]))
        patches.append({"id": i, "cells": m, "since": res["dates"][since], "style": "drop"})
    out = validate(patches, folder / "alerts.geojson", fires, grid=grid)
    summary = dict(out["summary"], alert_recall=out["summary"]["recall_area"],
                   source="INPE DETER and UMD GLAD alerts, NASA FIRMS / INPE fires")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary, indent=1))
    print("validation:", {k: summary[k] for k in ("n_patches", "share_confirmed", "median_lag_days", "share_with_fire", "alert_recall")})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("site", choices=sorted(SITES))
    ap.add_argument("--synthetic", action="store_true")
    a = ap.parse_args()
    site = SITES[a.site]
    grid = site_grid(site)
    cover = read_cover(site, grid)
    if a.synthetic:
        from .synthetic import make
        gcov, gunw, _ = make(site, cover)
        source = "synthetic"
    else:
        gcov, gunw = load_real(site, grid)
        source = "NISAR L2 GCOV + GUNW (ASF DAAC)"
    res = analyze(site, cover, gcov, gunw)
    validation = export.ROOT / site.id / "validation.json"
    if site.id == "amazon" and not a.synthetic:
        check_clearings(site, grid, res, validation)
    elif validation.exists():
        validation.unlink()            # scores from real data never sit next to synthetic layers
    path = export.write(site, grid, cover, res, source)
    styled = int((res["style"] > 0).sum())
    print(f"{site.id}: {len(res['dates'])} dates, {styled} styled px, layers: "
          f"{', '.join(k for k in ('disp', 'up', 'damage') if k in res)} -> {path}")


if __name__ == "__main__":
    main()
