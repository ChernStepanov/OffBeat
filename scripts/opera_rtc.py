"""Sentinel-1 backscatter (NASA OPERA RTC-S1, C-band) at the same sample points as a NISAR site.

    .venv/bin/python scripts/opera_rtc.py amazon            # search, then read (asks for Earthdata login)
    .venv/bin/python scripts/opera_rtc.py amazon --dry-run  # search only, no login

Reads only the window around the site from each cloud-optimised GeoTIFF; whole bursts are never
downloaded. Writes data/<site>/sentinel1.json: one VV and one VH value (gamma0, dB) per sample
point and acquisition date, null where the burst does not cover the point or the value is invalid.
Credentials: ~/.netrc, EARTHDATA_USERNAME/EARTHDATA_PASSWORD, or an interactive prompt that is not
saved. Nothing secret is written to disk or to the output.
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import datetime as dt
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import requests

ROOT = Path(__file__).resolve().parent.parent
CMR = "https://cmr.earthdata.nasa.gov/search/granules.json"
COLLECTION = "C2777436413-ASF"          # OPERA_L2_RTC-S1_V1 (ASF DAAC)


def site_points(site_id):
    site = json.loads((ROOT / "data" / f"{site_id}.json").read_text())
    pts = [(p["lat"], p["lon"]) for p in site["pixels"]]
    return site, pts


def search(bbox, start, end):
    w, s, e, n = bbox["w"], bbox["s"], bbox["e"], bbox["n"]
    out, page = [], 1
    while True:
        r = requests.get(CMR, params={
            "collection_concept_id": COLLECTION, "bounding_box": f"{w},{s},{e},{n}",
            "temporal": f"{start}T00:00:00Z,{end}T23:59:59Z", "page_size": 2000, "page_num": page,
            "sort_key": "start_date"}, timeout=60)
        r.raise_for_status()
        entries = r.json()["feed"]["entry"]
        out += entries
        if len(entries) < 2000:
            break
        page += 1
    granules = []
    for g in out:
        links = {l["href"].rsplit("_", 1)[-1][:-4]: l["href"] for l in g["links"]
                 if l["href"].startswith("https://") and l["href"].endswith(".tif")}
        if "VV" in links and "VH" in links:
            granules.append({"id": g["title"], "concept_id": g["id"], "date": g["time_start"][:10],
                             "burst": g["title"].split("_")[3], "vv": links["VV"], "vh": links["VH"]})
    return granules


def login():
    import earthaccess
    for strategy in ("netrc", "environment"):
        try:
            auth = earthaccess.login(strategy=strategy)
            if auth and auth.authenticated:
                return earthaccess
        except Exception:
            pass
    auth = earthaccess.login(strategy="interactive", persist=False)
    if not (auth and auth.authenticated):
        sys.exit("Earthdata login failed")
    return earthaccess


def sample(fs, url, lats, lons):
    """dB values at the points (nearest 30 m cell); NaN outside the burst or where invalid."""
    import rasterio
    from rasterio.windows import from_bounds
    from pyproj import Transformer
    with rasterio.open(url, opener=fs.open) as src:
        tr = Transformer.from_crs(4326, src.crs, always_xy=True)
        xs, ys = tr.transform(lons, lats)
        pad = 2 * abs(src.transform.a)
        try:
            win = from_bounds(min(xs) - pad, min(ys) - pad, max(xs) + pad, max(ys) + pad, src.transform)
            win = win.round_offsets().round_lengths().intersection(rasterio.windows.Window(0, 0, src.width, src.height))
        except Exception:
            return np.full(len(lats), np.nan)
        data = src.read(1, window=win, masked=True).astype("float64").filled(np.nan)
        wt = src.window_transform(win)
        cols = np.floor((np.array(xs) - wt.c) / wt.a).astype(int)
        rows = np.floor((np.array(ys) - wt.f) / wt.e).astype(int)
        ok = (rows >= 0) & (rows < data.shape[0]) & (cols >= 0) & (cols < data.shape[1])
        out = np.full(len(lats), np.nan)
        v = data[rows[ok], cols[ok]]
        with np.errstate(divide="ignore", invalid="ignore"):
            out[ok] = np.where(v > 0, 10 * np.log10(v), np.nan)   # RTC gamma0 is linear power
        return out


def compare(site, dates, vv, vh):
    """Forest vs pasture in C band (Sentinel-1 VH) and L band (NISAR HV) on the same points and weeks.

    C-band dates are those within 12 days of the NISAR dates, so both bands see the same season.
    Medians over points of each class, then over dates. Classes from WorldCover in data/<site>.json.
    """
    nis = site["dates"]
    near = [d for d in dates if min(abs((dt.date.fromisoformat(d) - dt.date.fromisoformat(n)).days) for n in nis) <= 12]
    out = {"c_band_dates": near, "l_band_dates": nis, "classes": {}}
    for cls, name in ((10, "forest"), (30, "pasture/grass")):
        idx = [i for i, p in enumerate(site["pixels"]) if p["cover"] == cls]
        if not idx or not near:
            continue
        c_vh = np.nanmedian([np.nanmedian(vh[d][idx]) for d in near])
        c_vv = np.nanmedian([np.nanmedian(vv[d][idx]) for d in near])
        l_hv = np.nanmedian([np.nanmedian([site["pixels"][i]["hv"][t] if site["pixels"][i]["hv"][t] is not None else np.nan for i in idx]) for t in range(len(nis))])
        out["classes"][name] = {"points": len(idx), "S1_VH_dB": round(float(c_vh), 2), "S1_VV_dB": round(float(c_vv), 2), "NISAR_HV_dB": round(float(l_hv), 2)}
    f, g = out["classes"].get("forest"), out["classes"].get("pasture/grass")
    if f and g:
        out["gap_forest_minus_pasture_dB"] = {"C_VH": round(f["S1_VH_dB"] - g["S1_VH_dB"], 2), "L_HV": round(f["NISAR_HV_dB"] - g["NISAR_HV_dB"], 2)}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("site")
    ap.add_argument("--start", default="2024-01-01")
    ap.add_argument("--end", default=dt.date.today().isoformat())
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    site, pts = site_points(a.site)
    granules = search(site["grid"]["bbox"], a.start, a.end)
    dates = sorted({g["date"] for g in granules})
    print(f"{len(granules)} RTC-S1 granules, {len(dates)} dates, {dates[0]} .. {dates[-1]}, "
          f"bursts {sorted({g['burst'] for g in granules})}")
    if a.dry_run:
        return

    ea = login()
    fs = ea.get_fsspec_https_session()
    lats = [p[0] for p in pts]
    lons = [p[1] for p in pts]

    def work(g):
        try:
            return g, sample(fs, g["vv"], lats, lons), sample(fs, g["vh"], lats, lons)
        except Exception as e:                        # a failed read is a gap, never a value
            print(f"  skip {g['id']}: {e}", file=sys.stderr)
            return g, None, None

    # several bursts can cover a date; per point keep the first valid value of that date
    vv = {d: np.full(len(pts), np.nan) for d in dates}
    vh = {d: np.full(len(pts), np.nan) for d in dates}
    used = []
    with cf.ThreadPoolExecutor(8) as pool:
        for i, (g, a_vv, a_vh) in enumerate(pool.map(work, granules), 1):
            if a_vv is not None:
                d = g["date"]
                vv[d] = np.where(np.isnan(vv[d]), a_vv, vv[d])
                vh[d] = np.where(np.isnan(vh[d]), a_vh, vh[d])
                used.append(g)
            if i % 20 == 0:
                print(f"  {i}/{len(granules)}")

    r1 = lambda a: [None if np.isnan(x) else round(float(x), 2) for x in a]
    out = {
        "schema_version": 1, "site": a.site,
        "source": "NASA OPERA RTC-S1 (Sentinel-1 C-band, gamma0, 30 m) via ASF DAAC",
        "collection": COLLECTION, "polarisations": ["VV", "VH"], "units": "dB",
        "dates": dates,
        "points": {"vv": [r1(vv[d]) for d in dates], "vh": [r1(vh[d]) for d in dates]},   # [date][point], same point order as data/<site>.json
        "provenance": {
            "created_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            "granules": [{"id": g["id"], "concept_id": g["concept_id"], "date": g["date"]} for g in used],
            "sampling": "nearest 30 m RTC cell to each NISAR sample point; linear gamma0 -> 10*log10",
            "points_sha256": hashlib.sha256(json.dumps(pts).encode()).hexdigest(),
        },
    }
    out["summary"] = compare(site, dates, vv, vh)
    print(json.dumps(out["summary"], indent=1))
    path = ROOT / "data" / a.site / "sentinel1.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, separators=(",", ":")))
    print(f"wrote {path} ({path.stat().st_size // 1024} KB, {len(used)}/{len(granules)} granules read)")


if __name__ == "__main__":
    main()
