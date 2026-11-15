"""Fetch bounded public elevation context for the Amazon dense native grid."""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import numpy as np
import requests
import rasterio
from scipy.ndimage import distance_transform_edt
from pyproj import Transformer
from rasterio.transform import Affine
from rasterio.warp import Resampling, reproject, transform_bounds
from rasterio.windows import from_bounds

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/investigation"
LAYERS = OUT / "layers"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def web_tile(lon: float, lat: float, zoom: int) -> tuple[int, int]:
    n = 2**zoom
    x = int((lon + 180) / 360 * n)
    y = int((1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n)
    return x, y


def terrain_window(grid: dict, source_path: Path) -> tuple[np.ndarray, np.ndarray]:
    h, w = grid["shape"]
    dst = np.full((h, w), np.nan, dtype=np.float32)
    dst_transform = Affine(grid["x_step"], 0, grid["x_first"] - grid["x_step"] / 2,
                           0, grid["y_step"], grid["y_first"] - grid["y_step"] / 2)
    with rasterio.open(source_path) as src:
        reproject(rasterio.band(src, 1), dst, src_transform=src.transform,
                  src_crs=src.crs, dst_transform=dst_transform, dst_crs=f"EPSG:{grid['epsg']}",
                  resampling=Resampling.bilinear, src_nodata=src.nodata, dst_nodata=np.nan)
    # 20 m central differences; edge cells use one-sided differences via numpy.gradient.
    dy, dx = np.gradient(dst.astype(np.float64), abs(grid["y_step"]), abs(grid["x_step"]))
    slope = np.degrees(np.arctan(np.hypot(dx, dy))).astype(np.float32)
    slope[~np.isfinite(dst)] = np.nan
    return dst, slope


def hansen_window(grid: dict, band: str) -> tuple[np.ndarray, np.ndarray, dict]:
    """Read just the AOI window from Hansen's public, range-capable GeoTIFF."""
    version, tile = "GFC-2024-v1.12", "00N_050W"
    url = f"https://storage.googleapis.com/earthenginepartners-hansen/{version}/Hansen_{version}_{band}_{tile}.tif"
    bounds = transform_bounds(f"EPSG:{grid['epsg']}", "EPSG:4326",
        grid["x_first"] - abs(grid["x_step"]),
        grid["y_first"] + (grid["shape"][0]-1)*grid["y_step"] - abs(grid["y_step"]),
        grid["x_first"] + grid["shape"][1]*grid["x_step"],
        grid["y_first"] + abs(grid["y_step"]), densify_pts=21)
    with rasterio.open(url) as src:
        window = from_bounds(*bounds, transform=src.transform).round_offsets().round_lengths()
        data = src.read(1, window=window)
        # Zero is a real value in both bands (no canopy / no mapped loss), not nodata.
        dst = np.full(tuple(grid["shape"]), 255, dtype=np.uint8)
        dst_transform = Affine(grid["x_step"], 0, grid["x_first"] - grid["x_step"] / 2,
                               0, grid["y_step"], grid["y_first"] - grid["y_step"] / 2)
        reproject(data, dst, src_transform=src.window_transform(window), src_crs=src.crs,
                  dst_transform=dst_transform, dst_crs=f"EPSG:{grid['epsg']}",
                  resampling=Resampling.nearest, src_nodata=255, dst_nodata=255)
        info = {"url": url, "source_window_row_col_height_width": [int(window.row_off), int(window.col_off), int(window.height), int(window.width)],
                "raw_window_shape": list(data.shape), "raw_window_sha256": hashlib.sha256(data.tobytes()).hexdigest(),
                "source_year": 2024, "resolution": "approximately 30 m / 1 arc-second",
                "license": "CC BY 4.0; Hansen/UMD/Google attribution required",
                "access": "GDAL /vsicurl HTTP byte-range read of AOI window; TIFF block layout is striped (1 x 40000), not tiled COG, so actual transferred bytes may exceed decoded window size."}
    return dst, data, info


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    LAYERS.mkdir(parents=True, exist_ok=True)
    receipt = json.loads((ROOT / "data/subsets/amazon-dense/2026-08-23.json").read_text())
    grid = receipt["grid"]
    # Approximate WGS84 center only selects the Web-Mercator source tile.
    inv = Transformer.from_crs(grid["epsg"], 4326, always_xy=True)
    lon, lat = inv.transform(grid["x_first"] + (grid["shape"][1]-1)*grid["x_step"]/2,
                             grid["y_first"] + (grid["shape"][0]-1)*grid["y_step"]/2)
    zoom = 12
    tx, ty = web_tile(lon, lat, zoom)
    url = f"https://elevation-tiles-prod.s3.amazonaws.com/geotiff/{zoom}/{tx}/{ty}.tif"
    raw = LAYERS / f"aws-terrain-z{zoom}-{tx}-{ty}.tif"
    if not raw.exists():
        response = requests.get(url, timeout=60)
        response.raise_for_status()
        if len(response.content) > 10_000_000:
            raise RuntimeError("Unexpectedly large elevation tile; refusing download")
        raw.write_bytes(response.content)
    elevation, slope = terrain_window(grid, raw)
    treecover, tree_raw, tree_info = hansen_window(grid, "treecover2000")
    lossyear, loss_raw, loss_info = hansen_window(grid, "lossyear")
    npz = LAYERS / "amazon-dem-native.npz"
    forest_npz = LAYERS / "amazon-hansen-native.npz"
    coords = json.loads((OUT / "map-candidates.json").read_text()) if (OUT / "map-candidates.json").exists() else {"maps": []}
    cover_path = ROOT / "data/subsets/amazon-dense/worldcover-2021.npz"
    cover = np.load(cover_path)["cover"]
    if cover.shape != tuple(grid["shape"]):
        raise ValueError("WorldCover does not match native AOI grid")
    # Per-class distance to the nearest *different WorldCover class*, in metres.
    boundary_distance = np.zeros(cover.shape, dtype=np.float32)
    for klass in np.unique(cover):
        same = cover == klass
        d = distance_transform_edt(same, sampling=(abs(grid["y_step"]), abs(grid["x_step"])))
        boundary_distance[same] = d[same]
    xx = grid["x_first"] + np.arange(grid["shape"][1], dtype=np.float64) * grid["x_step"]
    yy = grid["y_first"] + np.arange(grid["shape"][0], dtype=np.float64) * grid["y_step"]
    gx, gy = np.meshgrid(xx, yy)
    lon_grid, lat_grid = Transformer.from_crs(grid["epsg"], 4326, always_xy=True).transform(gx, gy)
    np.savez_compressed(forest_npz, treecover2000=treecover, lossyear=lossyear,
                        raw_treecover_window=tree_raw, raw_lossyear_window=loss_raw,
                        longitude=lon_grid.astype(np.float64), latitude=lat_grid.astype(np.float64))
    np.savez_compressed(npz, elevation_m=elevation, slope_deg=slope,
                        worldcover2021=cover, distance_to_other_worldcover_class_m=boundary_distance,
                        longitude=lon_grid.astype(np.float64), latitude=lat_grid.astype(np.float64))
    cells = []
    for point in coords.get("maps", []):
        r, c = int(point["native_row"]), int(point["native_col"])
        cells.append({"id": point["id"], "role": point["role"], "row": r, "col": c,
                      "lat": point["lat"], "lon": point["lon"],
                      "hv_shift_db": point["hv_shift_db"],
                      "elevation_m": round(float(elevation[r, c]), 2) if np.isfinite(elevation[r,c]) else None,
                      "slope_deg": round(float(slope[r, c]), 2) if np.isfinite(slope[r,c]) else None,
                      "treecover2000_pct": int(treecover[r, c]), "lossyear_code": int(lossyear[r, c]),
                      "lossyear_calendar_year": 2000 + int(lossyear[r, c]) if 1 <= int(lossyear[r, c]) <= 24 else None,
                      "worldcover_2021_class": int(cover[r, c]),
                      "distance_to_different_worldcover_class_m": round(float(boundary_distance[r, c]), 1),
                      "neighborhood_3x3": {"treecover2000_pct_median": float(np.median(treecover[max(0,r-1):r+2,max(0,c-1):c+2])),
                          "lossyear_code_counts": {str(int(k)): int((lossyear[max(0,r-1):r+2,max(0,c-1):c+2] == k).sum())
                              for k in np.unique(lossyear[max(0,r-1):r+2,max(0,c-1):c+2])},
                          "worldcover_class_counts": {str(int(k)): int((cover[max(0,r-1):r+2,max(0,c-1):c+2] == k).sum())
                              for k in np.unique(cover[max(0,r-1):r+2,max(0,c-1):c+2])}}})
    selected = {(int(p["native_row"]), int(p["native_col"])) for p in coords.get("maps", [])}
    background = np.ones(cover.shape, dtype=bool)
    for r, c in selected:
        background[r, c] = False

    def summarize(mask: np.ndarray) -> dict:
        t, l, w = treecover[mask], lossyear[mask], cover[mask]
        valid_loss = l > 0
        return {"n_native_cells": int(mask.sum()),
                "treecover2000_pct_median": float(np.median(t)),
                "treecover2000_ge_30pct_n": int((t >= 30).sum()),
                "lossyear_nonzero_n": int(valid_loss.sum()),
                "lossyear_nonzero_pct": round(float(valid_loss.mean() * 100), 2),
                "lossyear_year_counts": {str(2000+i): int((l == i).sum()) for i in range(1,25) if (l == i).any()},
                "worldcover2021_class_counts": {str(int(k)): int((w == k).sum()) for k in np.unique(w)}}
    output = {
         "study": "Amazon dense NISAR GCOV native AOI external map context; exploratory only",
         "generated_on": "2026-11-15",
        "native_grid": grid,
        "source": {"name": "AWS Terrain Tiles / Mapzen terrain; elevation derived from public terrain compilation",
                   "url": url, "zoom": zoom, "tile_xy": [tx, ty], "raw_path": raw.relative_to(ROOT).as_posix(),
                   "raw_sha256": sha256(raw), "raw_bytes": raw.stat().st_size,
                   "access": "one bounded 512x512 GeoTIFF tile; URL supports HTTP byte ranges (verified 206); no credentials",
                   "resolution": "Web-Mercator zoom 12, approximately 19 m/pixel at this latitude",
                   "license": "Mapzen Terrain Tiles, CC BY 4.0 (attribution to Mapzen/OpenStreetMap contributors required); AWS hosts the tiles. The product is a mixed-source terrain compilation.",
                   "limitation": "Not a hydrologically conditioned DEM; cannot infer channel/flood status or event timing."},
        "derived": {"path": npz.relative_to(ROOT).as_posix(), "sha256": sha256(npz),
                    "method": "Bilinear reprojection to all 141x141 EPSG:32722 20 m native cell centers; slope from 20 m central differences; no smoothing or class labels.",
                    "valid_elevation_cells": int(np.isfinite(elevation).sum()),
                    "elevation_range_m": [round(float(np.nanmin(elevation)), 2), round(float(np.nanmax(elevation)), 2)],
                    "slope_range_deg": [round(float(np.nanmin(slope)), 2), round(float(np.nanmax(slope)), 2)]},
         "forest_change": {"product": "Hansen Global Forest Change 2024 v1.12", "path": forest_npz.relative_to(ROOT).as_posix(),
             "sha256": sha256(forest_npz), "treecover2000": tree_info, "lossyear": loss_info,
             "method": "Two AOI-only source windows nearest-neighbor sampled to every 20 m native cell. Treecover2000 is canopy cover percent circa 2000. Lossyear code 0=no mapped loss; 1..24=2001..2024. Both source bands use 0 as a valid value (not nodata); source nodata 255 is retained as 255. Historical layer cannot date 2026 change. Upsampling 30m source to 20m means neighboring native cells can share source samples.",
             "grid_stats": {"canopy_ge_30pct_cells": int((treecover >= 30).sum()), "canopy_ge_50pct_cells": int((treecover >= 50).sum()),
                            "lossyear_nonzero_cells": int((lossyear > 0).sum()),
                            "lossyear_counts": {str(2000+i): int((lossyear == i).sum()) for i in range(1,25) if (lossyear == i).any()}},
             "grid_and_sample_stats_separate": {"all_native_grid": summarize(np.ones(cover.shape, dtype=bool)),
                "background_excluding_the_eight_displayed_points": summarize(background),
                "all_eight_displayed_points": summarize(np.isin(np.arange(cover.size).reshape(cover.shape),
                     [r*cover.shape[1]+c for r,c in selected])),
                "four_visual_candidates_only": summarize(np.isin(np.arange(cover.size).reshape(cover.shape),
                     [int(p["native_row"])*cover.shape[1]+int(p["native_col"]) for p in coords.get("maps",[]) if p["role"]=="candidate"])),
                "four_visual_controls_only": summarize(np.isin(np.arange(cover.size).reshape(cover.shape),
                     [int(p["native_row"])*cover.shape[1]+int(p["native_col"]) for p in coords.get("maps",[]) if p["role"]=="control"]))},
             "class_stratified_all_grid": {str(int(k)): summarize(cover == k) for k in np.unique(cover)},
             "visual_candidate_class_subsets": {str(k): {"n_points": sum(1 for p in cells if p["role"] == "candidate" and p["worldcover_2021_class"] == k),
                 "native_class_background": summarize((cover == k) & background),
                 "warning": "Point values are listed individually; 2 points per class do not support inferential comparison."}
                  for k in sorted({p["worldcover_2021_class"] for p in cells if p["role"] == "candidate"})},
             "group_stats": {role: {"n": sum(1 for p in cells if p["role"] == role),
                 "median_treecover2000_pct": float(np.median([p["treecover2000_pct"] for p in cells if p["role"] == role])),
                 "lossyear_nonzero_n": sum(1 for p in cells if p["role"] == role and p["lossyear_code"] > 0)} for role in ("candidate", "control")}},
         "candidate_matches": cells,
         "not_acquired": [
             {"source": "JRC Global Surface Water occurrence/seasonality", "status": "not downloaded", "reason": "public explorer provides styled map tiles, not verified numeric AOI raster access in this run; styling/color is not treated as measurements. Historical reference only, not event truth."},
             {"source": "OpenStreetMap waterways/roads", "status": "not acquired", "reason": "small Overpass bbox query attempted, but public endpoints returned 406/429 or timed out; no infrastructure geometries are asserted. OSM would be ODbL with attribution and query date; it is not satellite validation."},
            {"source": "Dynamic World", "status": "not downloaded", "reason": "no confirmed credentialless bounded probability-raster endpoint found. It is Sentinel-2-derived and therefore shares optical/cloud/seasonality limitations."},
            {"source": "MapBiomas/PRODES/DETER geometries", "status": "not downloaded", "reason": "no verified dated geometry API matching this AOI obtained; alerts must not be represented as complete coverage."},
        ],
        "interpretation": "Elevation/slope add geomorphic context independent of WorldCover class and NISAR backscatter. They can test whether candidate/control differences track relief, but cannot establish forest clearing, water, inundation, or cause.",
    }
    (OUT / "external-maps.json").write_text(json.dumps(output, indent=2) + "\n")
    print(json.dumps({"tile": [tx, ty], "bytes": raw.stat().st_size,
                      "elevation_range_m": output["derived"]["elevation_range_m"],
                      "matches": cells}, indent=2))


if __name__ == "__main__":
    main()
