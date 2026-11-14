"""Context layers for the Amazon site: active fires and deforestation alerts.

They explain and validate the HV-drop patches found in NISAR GCOV:

* fires  -> data/amazon/fires.json      [{date, lat, lon, source, confidence, frp, provider}]
* alerts -> data/amazon/alerts.geojson  polygons with {date, source, class, area_ha}

Fires
  1. NASA FIRMS area API, when the env var FIRMS_MAP_KEY is set
     (https://firms.modaps.eosdis.nasa.gov/api/area/csv/<KEY>/<SOURCE>/<bbox>/<days>/<date>,
     <= 10 days per call, standard-processing (SP) and NRT sources, deduplicated).
  2. Without a key: FIRMS yearly country CSVs (no key; only published for finished years,
     https://firms.modaps.eosdis.nasa.gov/data/country/<sensor>/<year>/<sensor>_<year>_Brazil.csv)
     for the sensors/years that exist, and INPE BDQueimadas monthly CSVs (no key; same VIIRS and
     MODIS satellites, processed by INPE) for the rest:
     https://dataserver-coids.inpe.br/queimadas/queimadas/focos/csv/mensal/Brasil/focos_mensal_br_YYYYMM.csv

Alerts
  * INPE DETER Amazonia, TerraBrasilis GeoServer WFS, layer deter-amz:deter_amz (no key).
  * UMD GLAD-L (Landsat) alerts, public GCS bucket earthenginepartners-hansen/GLADalert/C2 (no key),
    confirmed pixels (value 3), vectorised by alert day.
  * RADD and the GFW integrated alerts are only served by the Global Forest Watch data API, which
    needs an API key -> skipped.

Run:  .venv/bin/python -m pipeline.context_amazon
"""
from __future__ import annotations

import csv
import datetime as dt
import io
import json
import os
import sys
import time
from collections import Counter
from pathlib import Path

import math

import numpy as np
import requests
from pyproj import Geod, Transformer

from .config import SITES, Site
from .grid import Grid, site_grid

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
UA = {"User-Agent": "offbeat-pipeline/0.1"}

FIRMS_API = "https://firms.modaps.eosdis.nasa.gov/api/area/csv/{key}/{source}/{bbox}/{days}/{date}"
FIRMS_API_SOURCES = {  # FIRMS API source -> our label
    "VIIRS_SNPP_SP": "VIIRS_SNPP", "VIIRS_SNPP_NRT": "VIIRS_SNPP",
    "VIIRS_NOAA20_SP": "VIIRS_NOAA20", "VIIRS_NOAA20_NRT": "VIIRS_NOAA20",
    "VIIRS_NOAA21_NRT": "VIIRS_NOAA21",
    "MODIS_SP": "MODIS", "MODIS_NRT": "MODIS",
}
FIRMS_COUNTRY = "https://firms.modaps.eosdis.nasa.gov/data/country/{s}/{y}/{s}_{y}_Brazil.csv"
FIRMS_COUNTRY_SENSORS = {  # yearly-file sensor name -> our label
    "viirs-snpp": "VIIRS_SNPP", "viirs-jpss1": "VIIRS_NOAA20",
    "viirs-jpss2": "VIIRS_NOAA21", "modis": "MODIS",
}
INPE_MONTHLY = ("https://dataserver-coids.inpe.br/queimadas/queimadas/focos/csv/mensal/Brasil/"
                "focos_mensal_br_{ym}.csv")
INPE_SATELLITES = {  # INPE satellite -> our label (GOES, METOP, MSG, ... are dropped)
    "NPP-375": "VIIRS_SNPP", "NPP-375D": "VIIRS_SNPP",
    "NOAA-20": "VIIRS_NOAA20", "NOAA-21": "VIIRS_NOAA21",
    "AQUA_M-T": "MODIS", "AQUA_M-M": "MODIS", "TERRA_M-T": "MODIS", "TERRA_M-M": "MODIS",
}
FIRE_SOURCES = ("VIIRS_SNPP", "VIIRS_NOAA20", "VIIRS_NOAA21", "MODIS")

DETER_WFS = "https://terrabrasilis.dpi.inpe.br/geoserver/deter-amz/ows"
DETER_LAYER = "deter-amz:deter_amz"
# Kept: clear-cut, clearing with residual vegetation, mining (all = vegetation removed) and burn scars.
# Dropped: DEGRADACAO, CS_DESORDENADO / CS_GEOMETRICO (selective logging) - canopy stays.
DETER_CLASSES = {"DESMATAMENTO_CR", "DESMATAMENTO_VEG", "MINERACAO", "CICATRIZ_DE_QUEIMADA"}

GLAD_BUCKET = "earthenginepartners-hansen"
GLAD_PREFIX = "GLADalert/C2"
GCS_LIST = "https://storage.googleapis.com/storage/v1/b/{b}/o"
GCS_FILE = "https://storage.googleapis.com/{b}/{name}"

GEOD = Geod(ellps="WGS84")
EPOCH = dt.date(1970, 1, 1)


# ----------------------------------------------------------------------------- helpers

def _date(s) -> dt.date:
    return s if isinstance(s, dt.date) else dt.date.fromisoformat(str(s)[:10])


def day_number(s) -> int:
    """Days since 1970-01-01 (the int form used in rasters)."""
    return (_date(s) - EPOCH).days


def day_to_iso(n: int) -> str:
    return (EPOCH + dt.timedelta(days=int(n))).isoformat()


def _in_aoi(lat, lon, d, bbox, start, end) -> bool:
    w, s, e, n = bbox
    return w <= lon <= e and s <= lat <= n and start <= d <= end


def _get(url, *, params=None, stream=False, timeout=180, tries=4, ok404=False):
    for i in range(tries):
        try:
            r = requests.get(url, params=params, headers=UA, stream=stream, timeout=timeout)
            if r.status_code == 404 and ok404:
                return None
            if r.status_code in (429, 500, 502, 503, 504):
                raise requests.HTTPError(f"{r.status_code} from {url}")
            r.raise_for_status()
            return r
        except (requests.ConnectionError, requests.Timeout, requests.HTTPError) as exc:
            if i == tries - 1:
                raise
            print(f"  retry {i + 1} ({exc})", file=sys.stderr)
            time.sleep(10 * (i + 1))


def _exists(url) -> bool:
    try:
        return requests.head(url, headers=UA, timeout=60, allow_redirects=True).status_code == 200
    except requests.RequestException:
        return False


def _months(start: dt.date, end: dt.date):
    y, m = start.year, start.month
    while (y, m) <= (end.year, end.month):
        yield y, m
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


# ----------------------------------------------------------------------------- fires

def parse_firms_rows(rows, label, bbox, start, end, provider="FIRMS"):
    """FIRMS CSV dict rows (API or yearly country file) -> fire dicts inside the AOI."""
    out = []
    for r in rows:
        try:
            lat, lon, d = float(r["latitude"]), float(r["longitude"]), _date(r["acq_date"])
        except (KeyError, ValueError, TypeError):
            continue
        if not _in_aoi(lat, lon, d, bbox, start, end):
            continue
        conf = r.get("confidence")
        conf = int(conf) if conf and conf.isdigit() else (conf or None)
        out.append({"date": d.isoformat(), "lat": lat, "lon": lon, "source": label,
                    "confidence": conf, "frp": _num(r.get("frp")), "provider": provider,
                    "time": (r.get("acq_time") or "").zfill(4) or None})
    return out


def parse_inpe_rows(rows, bbox, start, end, sources=FIRE_SOURCES):
    """INPE BDQueimadas CSV dict rows -> fire dicts (VIIRS/MODIS only)."""
    out = []
    for r in rows:
        label = INPE_SATELLITES.get((r.get("satelite") or "").strip())
        if label is None or label not in sources:
            continue
        try:
            lat, lon = float(r["lat"]), float(r["lon"])
            stamp = r["data_hora_gmt"].strip()
            d = _date(stamp)
        except (KeyError, ValueError, TypeError, AttributeError):
            continue
        if not _in_aoi(lat, lon, d, bbox, start, end):
            continue
        hhmm = stamp[11:16].replace(":", "") if len(stamp) >= 16 else None
        out.append({"date": d.isoformat(), "lat": lat, "lon": lon, "source": label,
                    "confidence": None, "frp": _num(r.get("frp")), "provider": "INPE",
                    "time": hhmm})
    return out


def _stream_csv(url, prefilter: tuple[str, ...] = ()):
    """Stream a big CSV; yields dict rows. prefilter: line must contain one of these substrings."""
    r = _get(url, stream=True, timeout=600)
    lines = (ln.decode("utf-8", "replace") for ln in r.iter_lines() if ln)
    header = next(csv.reader([next(lines)]))
    for ln in lines:
        if prefilter and not any(t in ln for t in prefilter):
            continue
        vals = next(csv.reader([ln]))
        if len(vals) == len(header):
            yield dict(zip(header, (v.strip() for v in vals)))


def _lat_prefixes(bbox) -> tuple[str, ...]:
    """Substrings one of which every in-bbox line contains (cheap prefilter for 100 MB files)."""
    import math
    s, n = bbox[1], bbox[3]
    lo, hi = math.floor(s), math.floor(n)
    return tuple(f"-{abs(k + 1)}." if k < 0 else f"{k}." for k in range(lo, hi + 1)) + \
        ((f"-{abs(math.ceil(s))}.",) if s < 0 else ())


def fetch_fires_api(key, bbox, start, end):
    out = []
    bb = ",".join(f"{v:g}" for v in bbox)
    for src, label in FIRMS_API_SOURCES.items():
        d = start
        n_src = 0
        while d <= end:
            days = min(10, (end - d).days + 1)
            url = FIRMS_API.format(key=key, source=src, bbox=bb, days=days, date=d.isoformat())
            r = _get(url, timeout=120)
            text = r.text
            if text.lstrip().lower().startswith(("invalid", "error")):
                raise RuntimeError(f"FIRMS API: {text[:200]}")
            rows = parse_firms_rows(csv.DictReader(io.StringIO(text)), label, bbox, start, end)
            out += rows
            n_src += len(rows)
            d += dt.timedelta(days=days)
            time.sleep(0.5)
        print(f"  FIRMS API {src}: {n_src}")
    return out


def fetch_fires_public(bbox, start, end):
    """No key: FIRMS yearly country CSVs where published, INPE monthly CSVs for the rest."""
    out = []
    covered: dict[int, set[str]] = {}
    for y in range(start.year, end.year + 1):
        covered[y] = set()
        for s, label in FIRMS_COUNTRY_SENSORS.items():
            url = FIRMS_COUNTRY.format(s=s, y=y)
            if not _exists(url):
                continue
            rows = parse_firms_rows(_stream_csv(url), label, bbox, start, end)
            print(f"  FIRMS yearly {s} {y}: {len(rows)}  ({url})")
            out += rows
            covered[y].add(label)
    for y, m in _months(start, end):
        need = tuple(s for s in FIRE_SOURCES if s not in covered[y])
        if not need:
            continue
        url = INPE_MONTHLY.format(ym=f"{y}{m:02d}")
        if not _exists(url):
            print(f"  INPE {y}-{m:02d}: missing ({url})")
            continue
        rows = parse_inpe_rows(_stream_csv(url, _lat_prefixes(bbox)), bbox, start, end, need)
        print(f"  INPE monthly {y}-{m:02d} {','.join(need)}: {len(rows)}")
        out += rows
    return out


def dedupe_fires(fires):
    seen, out = set(), []
    for f in sorted(fires, key=lambda f: (f["date"], f.get("time") or "", f["source"])):
        k = (f["date"], f.get("time"), f["source"], round(f["lat"], 3), round(f["lon"], 3))
        if k not in seen:
            seen.add(k)
            out.append(f)
    return out


def fetch_fires(site: Site):
    start, end = _date(site.start), _date(site.end)
    key = os.environ.get("FIRMS_MAP_KEY", "").strip()
    if key:
        print("fires: FIRMS area API (FIRMS_MAP_KEY)")
        fires = fetch_fires_api(key, site.bbox, start, end)
    else:
        print("fires: no FIRMS_MAP_KEY -> FIRMS yearly country CSV + INPE BDQueimadas monthly CSV")
        fires = fetch_fires_public(site.bbox, start, end)
    return dedupe_fires(fires)


# ----------------------------------------------------------------------------- alerts

def ring_area_ha(ring) -> float:
    a, _ = GEOD.polygon_area_perimeter([p[0] for p in ring], [p[1] for p in ring])
    return abs(a) / 1e4


def geometry_area_ha(geom) -> float:
    polys = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
    return sum(ring_area_ha(p[0]) - sum(ring_area_ha(h) for h in p[1:]) for p in polys)


def parse_deter(fc, start, end, classes=DETER_CLASSES):
    out = []
    for f in fc.get("features", []):
        p = f.get("properties") or {}
        if p.get("classname") not in classes or not f.get("geometry") or not p.get("view_date"):
            continue
        d = _date(p["view_date"])
        if not start <= d <= end:
            continue
        out.append({"type": "Feature", "geometry": f["geometry"], "properties": {
            "date": d.isoformat(), "source": "DETER", "class": p["classname"],
            "area_ha": round(geometry_area_ha(f["geometry"]), 2),
            "id": str(p.get("gid") or f.get("id")), "satellite": p.get("satellite"),
            "sensor": p.get("sensor")}})
    return out


def fetch_deter(site: Site):
    w, s, e, n = site.bbox
    cql = f"BBOX(geom,{w},{s},{e},{n}) AND view_date BETWEEN '{site.start}' AND '{site.end}'"
    params = {"service": "WFS", "version": "1.0.0", "request": "GetFeature",
              "typeName": DETER_LAYER, "outputFormat": "application/json", "CQL_FILTER": cql}
    fc = _get(DETER_WFS, params=params, timeout=180, tries=6).json()
    raw = Counter(f["properties"]["classname"] for f in fc.get("features", []))
    print(f"  DETER raw classes in AOI: {dict(raw)}")
    return parse_deter(fc, _date(site.start), _date(site.end))


def _gcs_prefixes(prefix):
    out, tok = [], None
    while True:
        params = {"prefix": prefix, "delimiter": "/", "fields": "prefixes,nextPageToken"}
        if tok:
            params["pageToken"] = tok
        j = _get(GCS_LIST.format(b=GLAD_BUCKET), params=params, timeout=60).json()
        out += j.get("prefixes", [])
        tok = j.get("nextPageToken")
        if not tok:
            return out


def glad_tile(lon, lat) -> str:
    """GLAD 10x10 degree tile name, e.g. 050W_10S_040W_00N."""
    import math
    x0 = math.floor(lon / 10) * 10
    y0 = math.floor(lat / 10) * 10

    def ew(v):
        return f"{abs(v):03d}{'W' if v < 0 else 'E'}"

    def ns(v):
        return f"{abs(v):02d}{'S' if v < 0 else 'N'}"
    return f"{ew(x0)}_{ns(y0)}_{ew(x0 + 10)}_{ns(y0 + 10)}"


def _glad_latest(year: int, tile: str):
    """Newest GLAD folder holding alertYY/alertDateYY for that tile (folders live under the next year too)."""
    yy = f"{year % 100:02d}"
    folders = []
    for y in (year + 1, year):
        # dated folders look like GLADalert/C2/2026/11_13/ ; "final" holds the year-end release
        folders += sorted((p for p in _gcs_prefixes(f"{GLAD_PREFIX}/{y}/")
                           if p.rstrip("/").split("/")[-1].replace("_", "").isdigit()), reverse=True)
    for f in folders:
        a = GCS_FILE.format(b=GLAD_BUCKET, name=f"{f}alert{yy}_{tile}.tif")
        d = GCS_FILE.format(b=GLAD_BUCKET, name=f"{f}alertDate{yy}_{tile}.tif")
        if _exists(a) and _exists(d):
            return a, d
    return None


GLAD_MIN_HA = 0.5   # drop specks below half a 100 m output pixel


def glad_polygons(alert, adate, transform, year, start, end, min_level=3, min_ha=GLAD_MIN_HA):
    """GLAD confidence + day-of-year arrays -> one polygon per 8-connected clearing.

    min_level 3 = confirmed. Each clearing gets the earliest alert day among its pixels.
    """
    from rasterio.features import shapes
    from scipy import ndimage
    base = dt.date(year, 1, 1)
    lo, hi = (start - base).days + 1, (end - base).days + 1
    ok = (alert >= min_level) & (adate >= max(lo, 1)) & (adate <= hi)
    lab, n = ndimage.label(ok, structure=np.ones((3, 3), bool))
    if not n:
        return []
    first = ndimage.minimum(adate, lab, index=np.arange(1, n + 1))
    out = []
    for geom, v in shapes(lab.astype(np.int32), mask=ok, transform=transform, connectivity=8):
        area = geometry_area_ha(geom)
        if area < min_ha:
            continue
        d = base + dt.timedelta(days=int(first[int(v) - 1]) - 1)
        out.append({"type": "Feature", "geometry": geom, "properties": {
            "date": d.isoformat(), "source": "GLAD-L", "class": "glad_confirmed",
            "area_ha": round(area, 2)}})
    return out


def fetch_glad(site: Site):
    import rasterio
    from rasterio.windows import from_bounds
    w, s, e, n = site.bbox
    start, end = _date(site.start), _date(site.end)
    tile = glad_tile((w + e) / 2, (s + n) / 2)
    if glad_tile(w, s) != glad_tile(e, n):
        print("  GLAD: AOI spans several tiles, only the centre tile is read", file=sys.stderr)
    out = []
    for year in range(start.year, end.year + 1):
        urls = _glad_latest(year, tile)
        if urls is None:
            print(f"  GLAD {year}: no file")
            continue
        arrs = []
        for u in urls:
            with rasterio.open("/vsicurl/" + u) as ds:
                win = from_bounds(w, s, e, n, ds.transform).round_offsets().round_lengths()
                arrs.append(ds.read(1, window=win))
                tr = ds.window_transform(win)
        feats = glad_polygons(arrs[0], arrs[1], tr, year, start, end)
        print(f"  GLAD-L {year}: {len(feats)} polygons  ({urls[1]})")
        out += feats
    return out


def fetch_alerts(site: Site, glad=True):
    print("alerts: INPE DETER (TerraBrasilis WFS)")
    feats = fetch_deter(site)
    if glad:
        print("alerts: UMD GLAD-L (public GCS)")
        try:
            feats += fetch_glad(site)
        except Exception as exc:  # GLAD is optional
            print(f"  GLAD failed: {exc}", file=sys.stderr)
    print("alerts: RADD / GFW integrated alerts skipped (GFW data API needs an API key)")
    feats.sort(key=lambda f: (f["properties"]["date"], f["properties"]["source"]))
    return {"type": "FeatureCollection", "features": feats}


# ----------------------------------------------------------------------------- rasterise + validate

def _features(alerts):
    if alerts is None:
        return []
    if isinstance(alerts, (str, Path)):
        alerts = json.loads(Path(alerts).read_text())
    return alerts["features"] if isinstance(alerts, dict) else list(alerts)


def _to_grid_geom(geom, tr: Transformer):
    def ring(r):
        xs, ys = tr.transform([p[0] for p in r], [p[1] for p in r])
        return list(zip(xs, ys))
    if geom["type"] == "Polygon":
        return {"type": "Polygon", "coordinates": [ring(r) for r in geom["coordinates"]]}
    return {"type": "MultiPolygon", "coordinates": [[ring(r) for r in p] for p in geom["coordinates"]]}


def rasterize_alerts(site: Site, grid: Grid, alerts=None, all_touched=False):
    """Alert polygons -> (mask uint8[H,W], first_date int32[H,W]).

    first_date = earliest alert date per cell as days since 1970-01-01, 0 where there is no alert
    (day_to_iso() converts back). `alerts` defaults to data/<site>/alerts.geojson.
    """
    from rasterio.features import rasterize
    if alerts is None:
        alerts = DATA / site.id / "alerts.geojson"
    feats = _features(alerts)
    first = np.zeros(grid.shape, np.int32)
    if feats:
        tr = Transformer.from_crs(4326, grid.crs, always_xy=True)
        # later shapes overwrite earlier ones: burn newest first so the earliest date wins
        feats = sorted(feats, key=lambda f: f["properties"]["date"], reverse=True)
        pairs = [(_to_grid_geom(f["geometry"], tr), day_number(f["properties"]["date"])) for f in feats]
        first = rasterize(pairs, out_shape=grid.shape, transform=grid.transform, fill=0,
                          dtype="int32", all_touched=all_touched)
    return (first > 0).astype(np.uint8), first


def _patch_mask(cells, shape):
    a = np.asarray(cells)
    if a.dtype == bool and a.shape == shape:
        return a
    m = np.zeros(shape, bool)
    if a.size:
        a = a.reshape(-1, 2).astype(int)
        m[a[:, 0], a[:, 1]] = True
    return m


def validate(patches, alerts, fires, max_days=60, grid: Grid | None = None, fire_km=1.0):
    """Compare our HV-drop patches with alerts and fires.

    patches: [{id, cells: [(row, col), ...] or bool mask[H,W], since: ISO date, style: "drop"}]
    alerts:  GeoJSON FeatureCollection / feature list / path (properties date, source)
    fires:   [{date, lat, lon, ...}]
    grid:    the site grid the patches live on (default: amazon site grid).
    lag_days = since - alert date (negative: we saw it before the alert).
    """
    from scipy.spatial import cKDTree
    if max_days < 0 or fire_km < 0:
        raise ValueError('Time window and fire radius must be non-negative')
    patches = list(patches)
    grid = grid or site_grid(SITES["amazon"])
    shape = grid.shape
    # distances and areas in metres even when the grid is in degrees (site grids are EPSG:4326)
    from .grid import utm_crs
    w0, s0, e0, n0 = grid.lonlat_bounds()
    metric = utm_crs((w0 + e0) / 2, (s0 + n0) / 2) if grid.crs.is_geographic else grid.crs
    to_m = Transformer.from_crs(grid.crs, metric, always_xy=True)
    if grid.crs.is_geographic:
        lat0 = math.radians((s0 + n0) / 2)
        px_ha = abs(grid.transform.a * grid.transform.e) * 111320.0 ** 2 * math.cos(lat0) / 1e4
    else:
        px_ha = abs(grid.transform.a * grid.transform.e) / 1e4
    feats = _features(alerts)
    _, first = rasterize_alerts(None, grid, feats) if feats else (None, np.zeros(shape, np.int32))
    by_src = {}
    for src in sorted({f["properties"].get("source", "?") for f in feats}):
        by_src[src] = rasterize_alerts(None, grid, [f for f in feats
                                                    if f["properties"].get("source", "?") == src])[0] > 0

    # fires -> grid xy
    fires = list(fires or [])
    if fires:
        tr = Transformer.from_crs(4326, metric, always_xy=True)
        fx, fy = tr.transform([f["lon"] for f in fires], [f["lat"] for f in fires])
        fxy = np.column_stack([fx, fy])
        fday = np.array([day_number(f["date"]) for f in fires])

    union = np.zeros(shape, bool)
    matched_cells = np.zeros(shape, bool)
    matched_by_src = {src: np.zeros(shape, bool) for src in by_src}
    rows = []
    for p in patches:
        m = _patch_mask(p["cells"], shape)
        union |= m
        since = day_number(p["since"])
        # Filter BEFORE rasterising: an old overlapping alert must not hide a recent one.
        eligible = [f for f in feats if abs(day_number(f['properties']['date']) - since) <= max_days]
        _, nearby_dates = rasterize_alerts(None, grid, eligible) if eligible else (None, np.zeros(shape, np.int32))
        hit = nearby_dates[m]
        hit = hit[hit > 0]
        matched_cells |= m & (nearby_dates > 0)
        sources = []
        for src in by_src:
            subset = [f for f in eligible if f['properties'].get('source', '?') == src]
            src_mask = rasterize_alerts(None, grid, subset)[0] > 0 if subset else np.zeros(shape, bool)
            matched_by_src[src] |= src_mask & m
            if (src_mask & m).any(): sources.append(src)
        rec = {"id": p.get("id"), "style": p.get("style"), "since": _date(p["since"]).isoformat(),
               "n_cells": int(m.sum()), "area_ha": round(float(m.sum() * px_ha), 2),
               "alert": bool(hit.size), "alert_date": None, "lag_days": None,
               "alert_sources": sources,
               "fire": False, "fire_date": None, "fire_dist_m": None, "fire_source": None}
        if hit.size:
            a = int(hit[np.argmin(np.abs(hit.astype(np.int64) - since))])
            rec["alert_date"] = day_to_iso(a)
            rec["lag_days"] = since - a
        if fires and m.any():
            r, c = np.nonzero(m)
            cx, cy = to_m.transform(*(grid.transform @ (c + 0.5, r + 0.5)))
            tree = cKDTree(np.column_stack([cx, cy]))
            near = np.abs(fday - since) <= max_days
            if near.any():
                idx = np.nonzero(near)[0]
                dist, _ = tree.query(fxy[idx], distance_upper_bound=fire_km * 1000)
                ok = np.isfinite(dist)
                if ok.any():
                    j = idx[ok][np.argmin(dist[ok])]
                    rec.update(fire=True, fire_date=fires[j]["date"],
                               fire_dist_m=round(float(dist[ok].min()), 1),
                               fire_source=fires[j].get("source"))
        rows.append(rec)

    n = len(rows)
    lags = [r["lag_days"] for r in rows if r["lag_days"] is not None]
    alert_cells = first > 0
    caught = matched_cells
    summary = {
        "n_patches": n,
        "share_confirmed": (sum(r["alert"] for r in rows) / n) if n else None,
        "median_lag_days": float(np.median(lags)) if lags else None,
        "share_with_fire": (sum(r["fire"] for r in rows) / n) if n else None,
        "alert_area_ha": round(float(alert_cells.sum() * px_ha), 2),
        "caught_alert_area_ha": round(float(caught.sum() * px_ha), 2),
        "recall_area": (float(caught.sum() / alert_cells.sum())) if alert_cells.any() else None,
        "recall_by_source": {s: (float(matched_by_src[s].sum() / sm.sum()) if sm.any() else None)
                             for s, sm in by_src.items()},
        "max_days": max_days, "fire_km": fire_km,
        "matching": "spatial overlap AND absolute date difference <= max_days; not independent causal confirmation",
    }
    return {"patches": rows, "summary": summary}


# ----------------------------------------------------------------------------- CLI

def monthly_counts(items, key=lambda x: x["date"]):
    return dict(sorted(Counter(key(i)[:7] for i in items).items()))


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--site", default="amazon")
    ap.add_argument("--skip-fires", action="store_true")
    ap.add_argument("--skip-alerts", action="store_true")
    ap.add_argument("--no-glad", action="store_true")
    a = ap.parse_args(argv)
    site = SITES[a.site]
    out = DATA / site.id
    out.mkdir(parents=True, exist_ok=True)

    if not a.skip_fires:
        fires = fetch_fires(site)
        (out / "fires.json").write_text(json.dumps(fires, indent=0))
        print(f"fires: {len(fires)} -> {out / 'fires.json'}")
        for src in FIRE_SOURCES:
            sub = [f for f in fires if f["source"] == src]
            print(f"  {src:13s} {len(sub):5d}  {monthly_counts(sub)}")
        print(f"  by month: {monthly_counts(fires)}")

    if not a.skip_alerts:
        fc = fetch_alerts(site, glad=not a.no_glad)
        (out / "alerts.geojson").write_text(json.dumps(fc))
        feats = fc["features"]
        print(f"alerts: {len(feats)} -> {out / 'alerts.geojson'}")
        for src in sorted({f["properties"]["source"] for f in feats}):
            sub = [f["properties"] for f in feats if f["properties"]["source"] == src]
            ha = Counter()
            for p in sub:
                ha[p["date"][:7]] += p["area_ha"]
            print(f"  {src}: {len(sub)} polygons, {sum(ha.values()):.1f} ha, classes "
                  f"{dict(Counter(p['class'] for p in sub))}")
            print(f"    count by month: {monthly_counts(sub)}")
            print(f"    ha by month:    { {k: round(v, 1) for k, v in sorted(ha.items())} }")
        grid = site_grid(site)
        mask, _ = rasterize_alerts(site, grid, fc)
        print(f"  rasterised on {grid.shape} grid: {int(mask.sum())} cells "
              f"({mask.sum() * site.pixel_m ** 2 / 1e4:.0f} ha)")


if __name__ == "__main__":
    main()
