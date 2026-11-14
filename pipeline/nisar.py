"""NISAR L2 GCOV / GUNW: CMR search, remote HDF5 reads, resampling onto the site grid, npz cache.

Search uses the public CMR API (no login). Reading the .h5 files needs Earthdata Login
(~/.netrc or EARTHDATA_USERNAME / EARTHDATA_PASSWORD); files are streamed over HTTPS with
fsspec so only the HDF5 chunks covering the site are fetched.

HDF5 layout sources (checked 2026-11-14):
  [GCOV-XML]  isce3 product spec XML, python/packages/nisar/products/XML/L2/nisar_L2_GCOV.xml
              https://github.com/isce-framework/isce3/blob/develop/python/packages/nisar/products/XML/L2/nisar_L2_GCOV.xml
  [GCOV-DOC]  https://nisar-docs.asf.alaska.edu/  -> Data Products / GCOV (gamma0 power, mask layer)
  [GUNW-SPEC] JPL D-102272 Rev E, L2 GUNW product specification (Nov 2024), tables 3-11, 5-3,
              section 3.3 (radarGrid cubes, LOS definition, paged HDF5)
              https://nisar.asf.earthdatacloud.nasa.gov/NISAR-SAMPLE-DATA/DOCS/NISAR_D-102272_RevE_NASA_SDS_Product_Specification_L2_GUNW_Nov8_2024_w-sigs.pdf
  [GUNW-W]    isce3 GUNW writer (current develop): python/packages/nisar/products/insar/GUNW_writer.py,
              InSAR_L2_writer.py, and nisar/workflows/h5_prep.py (set_get_geo_info,
              add_radar_grid_cubes_to_hdf5)  https://github.com/isce-framework/isce3
  [MINTPY]    MintPy NISAR reader, src/mintpy/prep_nisar.py (same GUNW paths, phase used unflipped)
              https://github.com/insarlab/MintPy/blob/main/src/mintpy/prep_nisar.py
  [CMR]       live CMR UMM-G records of NISAR_L2_{GCOV,GUNW}_{BETA_V1,PROVISIONAL_V1,V1}
"""
from __future__ import annotations

import math
import os
import pathlib
import re
from dataclasses import dataclass

import h5py
import numpy as np
import requests
from pyproj import CRS, Transformer
from rasterio.transform import Affine
from rasterio.warp import Resampling, reproject, transform_bounds
from scipy.interpolate import RegularGridInterpolator

from .config import GCOV, GLOBAL_GAP, GUNW, Site, Track
from .grid import Grid, site_grid

# --------------------------------------------------------------------------------------------
# HDF5 paths
# --------------------------------------------------------------------------------------------
IDENT = "/science/LSAR/identification"                       # [GCOV-XML] [GUNW-SPEC 5.2]
ID_START = f"{IDENT}/zeroDopplerStartTime"                   # GCOV only [GCOV-XML]
ID_REF_START = f"{IDENT}/referenceZeroDopplerStartTime"      # GUNW [GUNW-SPEC] [MINTPY]
ID_SEC_START = f"{IDENT}/secondaryZeroDopplerStartTime"      # GUNW [GUNW-SPEC]
ID_TRACK = f"{IDENT}/trackNumber"                            # both
ID_FRAME = f"{IDENT}/frameNumber"                            # both
ID_PASS = f"{IDENT}/orbitPassDirection"                      # both ("Ascending"/"Descending")

# GCOV [GCOV-XML]: float32 real diagonal terms (gamma0, linear power, _FillValue nan, units 1),
# xCoordinates/yCoordinates are float64 pixel CENTRES (pixel_coordinate_convention="center"),
# projection is a scalar uint32 holding the EPSG code (also attr "epsg_code").
# mask: uint8, 0 = partially focused / invalid, 255 = outside the acquisition, else subswath number.
GCOV_GRID = "/science/LSAR/GCOV/grids/frequency{freq}"
GCOV_X = "xCoordinates"
GCOV_Y = "yCoordinates"
GCOV_PROJ = "projection"
GCOV_MASK = "mask"

# GUNW [GUNW-SPEC table 3-11, 5-3] [GUNW-W] [MINTPY]
GUNW_GRID = "/science/LSAR/GUNW/grids/frequency{freq}"
GUNW_CENTER_FREQ = "centerFrequency"                         # Hz, scalar, in GUNW_GRID [GUNW-SPEC] [GUNW-W]
GUNW_UNW = GUNW_GRID + "/unwrappedInterferogram"
GUNW_UNW_PHASE = "unwrappedPhase"                            # float32 radians, fill nan, in UNW/<pol>
GUNW_UNW_COH = "coherenceMagnitude"                          # float32, fill nan, in UNW/<pol>
GUNW_UNW_CC = "connectedComponents"                          # uint16, fill 65535, 0 = not unwrapped
GUNW_UNW_MASK = "mask"                                       # in UNW (group level); low byte = 3 decimal
#   digits water*100 + refSubswath*10 + secSubswath (0 subswath = invalid), fill 255.
#   Rev E spec says uint8; current isce3 writer says uint32 with anomaly bits 8-31 -> we use low byte.
# xCoordinates / yCoordinates / projection are written both in UNW and in UNW/<pol>
# (set_get_geo_info is called for both groups in [GUNW-W]); MintPy reads the <pol> copies.
GUNW_RADARGRID = "/science/LSAR/GUNW/metadata/radarGrid"     # [GUNW-SPEC 3.3] [GUNW-W] [MINTPY]
RG_LOS_X = "losUnitVectorX"     # east  component, target -> sensor, ENU, cube [height, y, x]
RG_LOS_Y = "losUnitVectorY"     # north component; up = sqrt(1 - x^2 - y^2)  [GUNW-SPEC 3.3]
RG_X, RG_Y, RG_Z, RG_PROJ = "xCoordinates", "yCoordinates", "heightAboveEllipsoid", "projection"

SPEED_OF_LIGHT = 299_792_458.0

CMR_URL = "https://cmr.earthdata.nasa.gov/search/granules.umm_json"
MATURITY_RANK = {"BETA": 0, "PROVISIONAL": 1, "VALIDATED": 2}
RAW_DIR = pathlib.Path(__file__).resolve().parents[1] / "data" / "raw"


# --------------------------------------------------------------------------------------------
# Search
# --------------------------------------------------------------------------------------------
@dataclass
class Granule:
    id: str
    url: str            # https data URL of the .h5
    product: str        # "GCOV" | "GUNW"
    maturity: str       # "BETA" | "PROVISIONAL" | "VALIDATED"
    track: int
    direction: str      # "A"/"D"
    frame: int
    start: str          # ISO date of the acquisition (GCOV) or the secondary/later date (GUNW)
    ref: str | None     # GUNW reference (earlier) date, else None
    pols: str           # e.g. "DHDH", "SH"
    size_mb: float | None


def _iso(t: str) -> str:
    """'20251030T120539' or '2025-10-30T12:05:39Z' -> '2025-10-30'."""
    t = t.strip()
    if re.match(r"^\d{8}T", t):
        return f"{t[0:4]}-{t[4:6]}-{t[6:8]}"
    return t[:10]


def parse_name(name: str) -> dict:
    """Fields from a NISAR L2 granule name (checked against live CMR, see [CMR]).

    GCOV: NISAR_L2_PR_GCOV_<cycle>_<track>_<A|D>_<frame>_<mode>_<pol>_<orbit>_<start>_<end>_<CRID>_...
          e.g. NISAR_L2_PR_GCOV_004_019_A_011_4005_DHDH_A_20251030T120539_20251030T120613_P05023_N_F_J_001
    GUNW: NISAR_L2_PR_GUNW_<cyc1>_<track>_<A|D>_<frame>_<cyc2>_<mode>_<pol>_<t1>_<t1e>_<t2>_<t2e>_<CRID>_...
          e.g. NISAR_L2_PR_GUNW_004_054_D_083_005_4000_SH_20251101T230233_20251101T230307_
               20251113T230233_20251113T230308_P05023_N_F_J_001
    """
    p = name.removesuffix(".h5").split("_")
    product = p[3]
    out = {"product": product, "track": int(p[5]), "direction": p[6], "frame": int(p[7])}
    if product == "GCOV":
        out.update(pols=p[9], start=_iso(p[11]), ref=None, crid=p[13], counter=p[-1])
    elif product == "GUNW":
        out.update(pols=p[10], ref=_iso(p[11]), start=_iso(p[13]), crid=p[15], counter=p[-1])
    else:
        raise ValueError(f"not a GCOV/GUNW name: {name}")
    return out


def _maturity(short_name: str) -> str:
    if "_BETA_" in short_name:
        return "BETA"
    if "_PROVISIONAL_" in short_name:
        return "PROVISIONAL"
    return "VALIDATED"


def _attrs(umm: dict) -> dict:
    return {a["Name"]: a.get("Values", []) for a in umm.get("AdditionalAttributes", [])}


def _granule_from_umm(umm: dict) -> tuple[Granule, dict]:
    name = umm["GranuleUR"]
    f = parse_name(name)
    at = _attrs(umm)
    # prefer the explicit CMR attributes, fall back to the name
    track = int(at.get("TRACK_NUMBER", [f["track"]])[0])
    frame = int(at.get("FRAME_NUMBER", [f["frame"]])[0])
    direction = (at.get("ASCENDING_DESCENDING", [f["direction"]])[0] or f["direction"])[0].upper()
    start, ref = f["start"], f["ref"]
    if f["product"] == "GUNW":
        if "REFERENCE_ZERO_DOPPLER_START_TIME" in at:
            ref = _iso(at["REFERENCE_ZERO_DOPPLER_START_TIME"][0])
        if "SECONDARY_ZERO_DOPPLER_START_TIME" in at:
            start = _iso(at["SECONDARY_ZERO_DOPPLER_START_TIME"][0])
    else:
        rng = umm.get("TemporalExtent", {}).get("RangeDateTime", {})
        if rng.get("BeginningDateTime"):
            start = _iso(rng["BeginningDateTime"])
    url = next(
        (u["URL"] for u in umm.get("RelatedUrls", [])
         if u.get("Type") == "GET DATA" and u["URL"].startswith("https") and u["URL"].endswith(".h5")),
        None,
    )
    size = None
    for a in umm.get("DataGranule", {}).get("ArchiveAndDistributionInformation", []):
        if a.get("Name", "").endswith(".h5") and not a["Name"].endswith("_QA_STATS.h5"):
            if "SizeInBytes" in a:
                size = a["SizeInBytes"] / 1e6
            elif "Size" in a:
                size = float(a["Size"])
            break
    g = Granule(
        id=name, url=url, product=f["product"],
        maturity=_maturity(umm.get("CollectionReference", {}).get("ShortName", "")),
        track=track, direction=direction, frame=frame, start=start, ref=ref,
        pols=f["pols"], size_mb=size,
    )
    extra = {"crid": f["crid"], "counter": f["counter"],
             "production": umm.get("DataGranule", {}).get("ProductionDateTime", "")}
    return g, extra


def _cmr_items(short_name: str, bbox, start: str, end: str) -> list[dict]:
    params = {
        "short_name": short_name,
        "bounding_box": ",".join(str(v) for v in bbox),
        "temporal": f"{start}T00:00:00Z,{end}T23:59:59Z",
        "page_size": 2000,
    }
    items, headers = [], {}
    while True:
        r = requests.get(CMR_URL, params=params, headers=headers, timeout=60)
        r.raise_for_status()
        page = r.json().get("items", [])
        items += page
        after = r.headers.get("CMR-Search-After")
        if not after or len(page) < params["page_size"]:
            return items
        headers = {"CMR-Search-After": after}


def _in(d: str, gap: tuple[str, str]) -> bool:
    return gap[0] <= d <= gap[1]


def _keep_dates(site: Site, g: Granule) -> bool:
    dates = [g.start] + ([g.ref] if g.ref else [])
    if not all(site.start <= d <= site.end for d in dates):
        return False
    gaps = (GLOBAL_GAP,) + tuple(site.gaps)
    if any(_in(d, gap) for d in dates for gap in gaps):
        return False
    # a pair that straddles a site gap compares two different processing states
    if g.ref and any(g.ref < gap[0] and g.start > gap[1] for gap in site.gaps):
        return False
    return True


def search(site: Site, product: str, track: Track | None = None) -> list[Granule]:
    """CMR search over site.bbox and site.start..site.end in every maturity collection of
    config.GCOV / config.GUNW, filtered to the site's tracks/frames (or only `track`),
    skipping GLOBAL_GAP and site.gaps, one granule per acquisition (GCOV) or pair (GUNW)
    preferring VALIDATED > PROVISIONAL > BETA, then the newer CRID / product counter.
    Sorted by (start, track)."""
    product = product.upper()
    collections = {"GCOV": GCOV, "GUNW": GUNW}[product]
    tracks = (track,) if track is not None else site.tracks
    wanted = {(t.track, t.direction): set(t.frames) for t in tracks}
    best: dict[tuple, tuple[tuple, Granule]] = {}
    for short_name in collections:
        for item in _cmr_items(short_name, site.bbox, site.start, site.end):
            try:
                g, extra = _granule_from_umm(item["umm"])
            except (KeyError, ValueError, IndexError):
                continue
            if g.product != product or g.url is None:
                continue
            frames = wanted.get((g.track, g.direction))
            if frames is None or g.frame not in frames or not _keep_dates(site, g):
                continue
            key = (g.track, g.direction, g.frame, g.ref, g.start)
            rank = (MATURITY_RANK[g.maturity], extra["crid"], extra["counter"], extra["production"])
            if key not in best or rank > best[key][0]:
                best[key] = (rank, g)
    return sorted((g for _, g in best.values()), key=lambda g: (g.start, g.ref or "", g.track, g.frame))


# --------------------------------------------------------------------------------------------
# Remote open
# --------------------------------------------------------------------------------------------
_FS = None


def _https_fs():
    global _FS
    if _FS is None:
        import earthaccess

        auth = None
        for strategy in ("netrc", "environment"):
            try:
                auth = earthaccess.login(strategy=strategy)
            except Exception:
                auth = None
            if auth is not None and getattr(auth, "authenticated", False):
                break
        else:
            raise RuntimeError(
                "NISAR data needs Earthdata Login: add to ~/.netrc (chmod 600)\n"
                "  machine urs.earthdata.nasa.gov login <user> password <password>\n"
                "or set EARTHDATA_USERNAME / EARTHDATA_PASSWORD. Accounts: https://urs.earthdata.nasa.gov/"
            )
        _FS = earthaccess.get_fsspec_https_session()
    return _FS


def open_h5(granule: Granule) -> h5py.File:
    """Read-only h5py.File over an fsspec HTTPS file object (chunks fetched on demand).
    NISAR files use the paged file-space strategy [GUNW-SPEC 3.3], so a page buffer is enabled
    when the file allows it."""
    if os.path.exists(granule.url):                      # local copy (tests, manual downloads)
        return h5py.File(granule.url, "r")
    fs = _https_fs()
    fobj = fs.open(granule.url, mode="rb", cache_type="blockcache", block_size=8 * 1024 * 1024)
    try:
        return h5py.File(fobj, "r", page_buf_size=64 * 1024 * 1024, rdcc_nbytes=64 * 1024 * 1024)
    except (OSError, ValueError):
        fobj.seek(0)
        return h5py.File(fobj, "r", rdcc_nbytes=64 * 1024 * 1024)


# --------------------------------------------------------------------------------------------
# Helpers for reading
# --------------------------------------------------------------------------------------------
def _str(f: h5py.File, path: str, default=None):
    if path not in f:
        return default
    v = f[path][()]
    if isinstance(v, np.ndarray):
        v = v.flat[0] if v.size else default
    return v.decode() if isinstance(v, bytes) else str(v)


def _epsg(ds: h5py.Dataset) -> int:
    if "epsg_code" in ds.attrs:
        return int(np.asarray(ds.attrs["epsg_code"]).flat[0])
    return int(np.asarray(ds[()]).flat[0])


def _find(f: h5py.File, groups: list[str], name: str) -> h5py.Dataset:
    for g in groups:
        if f"{g}/{name}" in f:
            return f[f"{g}/{name}"]
    raise KeyError(f"{name} not found in {groups}")


def _grid_bounds(grid: Grid) -> tuple[float, float, float, float]:
    t = grid.transform
    x0, y0 = t.c, t.f
    x1, y1 = t.c + t.a * grid.width + t.b * grid.height, t.f + t.d * grid.width + t.e * grid.height
    return min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)


def _axis_window(c: np.ndarray, lo: float, hi: float, pad: int) -> slice:
    """Index slice of the coordinate vector c (pixel centres, either order) covering [lo, hi]."""
    inside = np.nonzero((c >= lo) & (c <= hi))[0]
    if inside.size == 0:
        # the window may fall between two centres; take the nearest ones if within range
        if lo > max(c[0], c[-1]) or hi < min(c[0], c[-1]):
            return slice(0, 0)
        i = int(np.argmin(np.abs(c - (lo + hi) / 2)))
        inside = np.array([i])
    return slice(max(int(inside[0]) - pad, 0), min(int(inside[-1]) + pad + 1, c.size))


def window(x: np.ndarray, y: np.ndarray, epsg: int, grid: Grid, pad: int = 3) -> tuple[slice, slice]:
    """(row slice, col slice) of a product raster with centre coordinates x, y (in EPSG `epsg`)
    that covers the output grid plus `pad` product pixels."""
    b = transform_bounds(grid.crs, CRS.from_epsg(epsg), *_grid_bounds(grid), densify_pts=21)
    return _axis_window(y, b[1], b[3], pad), _axis_window(x, b[0], b[2], pad)


def _src_transform(x: np.ndarray, y: np.ndarray) -> Affine:
    dx = float(x[1] - x[0]) if x.size > 1 else 1.0
    dy = float(y[1] - y[0]) if y.size > 1 else -1.0
    return Affine(dx, 0.0, float(x[0]) - dx / 2, 0.0, dy, float(y[0]) - dy / 2)


def _warp(arr: np.ndarray, src_tr: Affine, epsg: int, grid: Grid, resampling, nodata=np.nan,
          dtype=np.float32) -> np.ndarray:
    out = np.full(grid.shape, nodata, dtype)
    if arr.size == 0:
        return out
    reproject(
        source=np.ascontiguousarray(arr.astype(dtype, copy=False)), destination=out,
        src_transform=src_tr, src_crs=CRS.from_epsg(epsg), src_nodata=nodata,
        dst_transform=grid.transform, dst_crs=grid.crs, dst_nodata=nodata,
        resampling=resampling,
    )
    return out


def _read(ds: h5py.Dataset, rows: slice, cols: slice) -> np.ndarray:
    if rows.stop <= rows.start or cols.stop <= cols.start:
        return np.zeros((0, 0), ds.dtype)
    return ds[rows, cols]


# --------------------------------------------------------------------------------------------
# GCOV
# --------------------------------------------------------------------------------------------
def read_gcov(granule: Granule, site: Site, grid: Grid | None = None,
              pols=("HHHH", "HVHV"), freq: str = "A", min_valid: float = 0.5) -> dict:
    """GCOV diagonal terms on the site grid.

    -> {"date": "YYYY-MM-DD", "<pol>": float32[H,W] gamma0 linear power, ..., "valid": bool[H,W]}
    Only the product window covering the site is read. Pixels with mask 0 (partially focused)
    or 255 (outside the swath) are dropped, then the 20 m data are averaged in LINEAR power
    onto the grid (rasterio Resampling.average, nodata-aware). `valid` = at least `min_valid`
    of the output pixel's footprint had valid product samples and every requested pol is finite.
    A pol missing from the product comes back all NaN."""
    grid = grid or site_grid(site)
    with open_h5(granule) as f:
        base = GCOV_GRID.format(freq=freq)
        x = f[f"{base}/{GCOV_X}"][()]
        y = f[f"{base}/{GCOV_Y}"][()]
        epsg = _epsg(f[f"{base}/{GCOV_PROJ}"])
        rows, cols = window(x, y, epsg, grid)
        tr = _src_transform(x[cols], y[rows]) if rows.stop > rows.start and cols.stop > cols.start \
            else _src_transform(x, y)
        if f"{base}/{GCOV_MASK}" in f:
            m = _read(f[f"{base}/{GCOV_MASK}"], rows, cols)
            good = (m != 0) & (m != 255)
        else:
            good = None
        out = {"date": _iso(_str(f, ID_START, granule.start))}
        valid = np.ones(grid.shape, bool)
        for pol in pols:
            path = f"{base}/{pol}"
            if path not in f:
                out[pol] = np.full(grid.shape, np.nan, np.float32)
                valid[:] = False
                continue
            a = _read(f[path], rows, cols).astype(np.float32)
            fill = f[path].attrs.get("_FillValue")
            if fill is not None and np.isfinite(fill):
                a[a == fill] = np.nan
            a[a < 0] = np.nan
            if good is not None:
                a[~good] = np.nan
            out[pol] = _warp(a, tr, epsg, grid, Resampling.average)
            valid &= np.isfinite(out[pol])
        if good is not None:
            frac = _warp(good.astype(np.float32), tr, epsg, grid, Resampling.average)
            valid &= np.nan_to_num(frac) >= min_valid
    for pol in pols:
        out[pol][~valid] = np.nan
    out["valid"] = valid
    return out


# --------------------------------------------------------------------------------------------
# GUNW
# --------------------------------------------------------------------------------------------
def _gunw_valid(mask: np.ndarray) -> np.ndarray:
    """Valid, non-water samples from the GUNW mask (low byte = water*100 + ref*10 + sec)."""
    low = mask.astype(np.uint32) & 0xFF
    return (low != 255) & ((low // 10) % 10 != 0) & (low % 10 != 0) & (low // 100 == 0)


def _los_on_grid(f: h5py.File, grid: Grid, height_m: float | None) -> np.ndarray:
    """losUnitVector cube -> float32[3,H,W] ENU target->sensor on the grid (bilinear in x/y,
    linear in height at `height_m`, default the middle of the cube's height range)."""
    g = GUNW_RADARGRID
    xc, yc, zc = f[f"{g}/{RG_X}"][()], f[f"{g}/{RG_Y}"][()], f[f"{g}/{RG_Z}"][()]
    epsg = _epsg(f[f"{g}/{RG_PROJ}"])
    rows, cols = window(xc, yc, epsg, grid, pad=2)
    xs, ys = xc[cols], yc[rows]
    h = 0.5 * (zc.min() + zc.max()) if height_m is None else float(height_m)
    k = int(np.clip(np.searchsorted(zc, h) - 1, 0, max(zc.size - 2, 0))) if zc.size > 1 else 0
    w = 0.0 if zc.size < 2 else float(np.clip((h - zc[k]) / (zc[k + 1] - zc[k]), 0, 1))
    planes = []
    for name in (RG_LOS_X, RG_LOS_Y):
        ds = f[f"{g}/{name}"]
        lo = ds[k, rows, cols].astype(np.float64)
        hi = ds[min(k + 1, zc.size - 1), rows, cols].astype(np.float64)
        planes.append((1 - w) * lo + w * hi)
    # grid pixel centres -> cube CRS
    cc, rr = np.meshgrid(np.arange(grid.width) + 0.5, np.arange(grid.height) + 0.5)
    t = grid.transform
    gx, gy = t.a * cc + t.b * rr + t.c, t.d * cc + t.e * rr + t.f
    px, py = Transformer.from_crs(grid.crs, CRS.from_epsg(epsg), always_xy=True).transform(gx, gy)
    yy, xx = ys, xs
    flip_y, flip_x = yy[0] > yy[-1], xx[0] > xx[-1]
    out = np.full((3,) + grid.shape, np.nan, np.float32)
    for i, p in enumerate(planes):
        if flip_y:
            p = p[::-1]
        if flip_x:
            p = p[:, ::-1]
        interp = RegularGridInterpolator(
            (np.sort(yy), np.sort(xx)), p, method="linear", bounds_error=False, fill_value=None)
        out[i] = interp(np.stack([py.ravel(), px.ravel()], -1)).reshape(grid.shape)
    out[2] = np.sqrt(np.clip(1.0 - out[0] ** 2 - out[1] ** 2, 0.0, 1.0))
    return out


def read_gunw(granule: Granule, site: Site, grid: Grid | None = None, pol: str = "HH",
              freq: str = "A", los_height_m: float | None = None) -> dict:
    """GUNW unwrapped pair on the site grid.

    -> {"ref": date, "sec": date, "track": int, "direction": "A"/"D",
        "los_m": float32[H,W], "coherence": float32[H,W], "conncomp": int32[H,W] (0 = unreliable),
        "los_enu": float32[3,H,W] unit vector ground -> satellite (east, north, up)}

    Sign convention: los_m > 0 = the ground moved TOWARD the satellite between ref and sec
    (range decrease), los_m = -wavelength / (4 pi) * unwrappedPhase. isce3 forms the
    interferogram as ref * conj(sec) with SLC phase -4 pi R / lambda, so positive phase is a
    range increase (isce3 crossmul + troposphere.py; MintPy uses the phase unflipped with the
    same -lambda/4pi rule). The spec itself does not state the sign - check it once on real data
    (e.g. Mexico City subsidence must give los_m < 0).
    Wavelength = c / grids/frequencyA/centerFrequency; missing frequency is an error.
    Phase and coherence are averaged onto the grid, connected components take the mode.
    Invalid, water and fill samples (mask, NaN, conncomp 65535) are dropped first; the
    phase still carries the per-component 2 pi ambiguity, so compare within a component."""
    grid = grid or site_grid(site)
    with open_h5(granule) as f:
        base = GUNW_UNW.format(freq=freq)
        pg = f"{base}/{pol}"
        if pg not in f:
            raise KeyError(f"{granule.id}: no {pol} in {base}")
        groups = [pg, base]
        x, y = _find(f, groups, "xCoordinates")[()], _find(f, groups, "yCoordinates")[()]
        epsg = _epsg(_find(f, groups, "projection"))
        rows, cols = window(x, y, epsg, grid)
        tr = _src_transform(x[cols], y[rows]) if rows.stop > rows.start and cols.stop > cols.start \
            else _src_transform(x, y)

        cf_path = f"{GUNW_GRID.format(freq=freq)}/{GUNW_CENTER_FREQ}"
        if cf_path not in f:
            raise ValueError('GUNW centerFrequency is missing; cannot convert phase to displacement')
        center_frequency = float(f[cf_path][()])
        if not np.isfinite(center_frequency) or center_frequency <= 0:
            raise ValueError('GUNW centerFrequency must be finite and positive')
        wavelength = SPEED_OF_LIGHT / center_frequency

        phase = _read(f[f"{pg}/{GUNW_UNW_PHASE}"], rows, cols).astype(np.float32)
        coh = _read(f[f"{pg}/{GUNW_UNW_COH}"], rows, cols).astype(np.float32)
        cc = _read(f[f"{pg}/{GUNW_UNW_CC}"], rows, cols).astype(np.int32)
        cc[cc == 65535] = 0
        bad = ~np.isfinite(phase)
        if f"{base}/{GUNW_UNW_MASK}" in f:
            bad |= ~_gunw_valid(_read(f[f"{base}/{GUNW_UNW_MASK}"], rows, cols))
        phase[bad] = np.nan
        coh[bad | ~np.isfinite(coh)] = np.nan
        cc[bad] = 0

        los_m = _warp(phase * np.float32(-wavelength / (4 * math.pi)), tr, epsg, grid, Resampling.average)
        coherence = _warp(coh, tr, epsg, grid, Resampling.average)
        # mode over all samples, 0 (unreliable) included; -1 only marks "no product here"
        conncomp = _warp(cc, tr, epsg, grid, Resampling.mode, nodata=-1, dtype=np.int32)
        conncomp[(conncomp < 0) | ~np.isfinite(los_m)] = 0
        los_enu = _los_on_grid(f, grid, los_height_m)

        direction = _str(f, ID_PASS, granule.direction) or granule.direction
        track = _str(f, ID_TRACK, None)
        out = {
            "ref": _iso(_str(f, ID_REF_START, granule.ref or "")),
            "sec": _iso(_str(f, ID_SEC_START, granule.start)),
            "track": int(track) if track not in (None, "") else granule.track,
            "direction": direction[0].upper(),
            "los_m": los_m,
            "coherence": coherence,
            "conncomp": conncomp,
            "los_enu": los_enu,
        }
    return out


# --------------------------------------------------------------------------------------------
# Cache
# --------------------------------------------------------------------------------------------
def cache_path(site: Site, granule: Granule, kind: str) -> pathlib.Path:
    return RAW_DIR / site.id / f"{granule.id}.{kind}.npz"


def load_or_read(granule: Granule, site: Site, kind: str) -> dict:
    """npz cache in data/raw/<site>/ (gitignored); reads the granule on a miss."""
    path = cache_path(site, granule, kind)
    if path.exists():
        with np.load(path, allow_pickle=False) as z:
            return {k: (z[k].item() if z[k].ndim == 0 else z[k]) for k in z.files}
    reader = {"gcov": read_gcov, "gunw": read_gunw}[kind]
    data = reader(granule, site)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name.removesuffix(".npz") + ".partial.npz")
    np.savez_compressed(tmp, **{k: np.asarray(v) for k, v in data.items()})
    tmp.replace(path)
    return data
