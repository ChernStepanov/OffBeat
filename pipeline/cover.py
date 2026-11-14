"""ESA WorldCover 2021 (v200, 10 m) on the site grid, read straight from the public COGs on AWS."""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.warp import reproject

from .config import Site
from .grid import Grid, site_grid

BASE = "https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map"
CACHE = Path(__file__).resolve().parent.parent / "data" / "raw"


def tile_names(bbox) -> list[str]:
    """WorldCover tiles are 3 x 3 degrees, named by their south-west corner."""
    w, s, e, n = bbox
    out = []
    for lat in range(math.floor(s / 3) * 3, math.ceil(n / 3) * 3, 3):
        for lon in range(math.floor(w / 3) * 3, math.ceil(e / 3) * 3, 3):
            ns = f"N{lat:02d}" if lat >= 0 else f"S{-lat:02d}"
            ew = f"E{lon:03d}" if lon >= 0 else f"W{-lon:03d}"
            out.append(f"ESA_WorldCover_10m_2021_v200_{ns}{ew}_Map.tif")
    return out


def read_cover(site: Site, grid: Grid | None = None) -> np.ndarray:
    """Class codes uint8[H, W] on the site grid (mode of the 10 m classes in each pixel). 0 = no data."""
    grid = grid or site_grid(site)
    cache = CACHE / site.id / f"worldcover_{site.pixel_m}m.npy"
    if cache.exists():
        return np.load(cache)
    out = np.zeros(grid.shape, np.uint8)
    with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif"):
        for name in tile_names(site.bbox):
            with rasterio.open(f"/vsicurl/{BASE}/{name}") as src:
                w, s, e, n = site.bbox
                win = src.window(w - 0.01, s - 0.01, e + 0.01, n + 0.01).round_offsets().round_lengths()
                win = win.intersection(rasterio.windows.Window(0, 0, src.width, src.height))
                data = src.read(1, window=win)
                part = np.zeros(grid.shape, np.uint8)
                reproject(data, part, src_transform=src.window_transform(win), src_crs=src.crs,
                          dst_transform=grid.transform, dst_crs=grid.crs,
                          src_nodata=0, dst_nodata=0, resampling=Resampling.mode)
                out = np.where(out == 0, part, out)
    cache.parent.mkdir(parents=True, exist_ok=True)
    np.save(cache, out)
    return out


if __name__ == "__main__":
    from .config import SITES
    for s in SITES.values():
        c = read_cover(s)
        vals, counts = np.unique(c, return_counts=True)
        print(s.id, c.shape, {int(v): round(100 * k / c.size, 1) for v, k in zip(vals, counts)})
