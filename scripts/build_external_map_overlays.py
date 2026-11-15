"""Build georeferenced, browser-ready PNG overlays from cached native map arrays.

No network access: this script only reads existing investigation NPZ files.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import rasterio
from PIL import Image
from rasterio.transform import Affine, array_bounds
from rasterio.warp import calculate_default_transform, reproject, Resampling

ROOT = Path(__file__).resolve().parents[1]
LAYER_DIR = ROOT / "data/investigation/layers"
MANIFEST = ROOT / "data/investigation/external-maps.json"
LOSS_STOPS = [(1, (255, 240, 128)), (8, (255, 166, 77)),
              (16, (225, 76, 66)), (24, (112, 25, 55))]
TREE_STOPS = [(0, (191, 164, 122)), (25, (196, 190, 127)),
              (50, (112, 166, 103)), (75, (44, 132, 79)), (100, (10, 83, 57))]


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def native_transform(grid: dict) -> Affine:
    """North-up EPSG:32722 transform; x_first/y_first are native pixel centers."""
    return Affine(grid["x_step"], 0, grid["x_first"] - grid["x_step"] / 2,
                  0, grid["y_step"], grid["y_first"] - grid["y_step"] / 2)


def target_grid(grid: dict) -> tuple[Affine, int, int, list[float]]:
    h, w = grid["shape"]
    src_transform = native_transform(grid)
    bounds = array_bounds(h, w, src_transform)
    dst_transform, width, height = calculate_default_transform(
        f"EPSG:{grid['epsg']}", "EPSG:4326", w, h, *bounds)
    west, south, east, north = array_bounds(height, width, dst_transform)
    return dst_transform, width, height, [float(west), float(south), float(east), float(north)]


def warp_native(values: np.ndarray, grid: dict, dst_transform: Affine,
                width: int, height: int, *, categorical: bool) -> tuple[np.ndarray, np.ndarray]:
    if values.shape != tuple(grid["shape"]):
        raise ValueError("Cached native layer does not match the native grid")
    if categorical:
        # 255 is reserved as NODATA; source 0 remains a fully valid value.
        source = values.astype(np.uint8, copy=False)
        dst = np.full((height, width), 255, dtype=np.uint8)
        reproject(source, dst, src_transform=native_transform(grid), src_crs=f"EPSG:{grid['epsg']}",
                  src_nodata=255, dst_transform=dst_transform, dst_crs="EPSG:4326",
                  dst_nodata=255, resampling=Resampling.nearest, init_dest_nodata=True)
        return dst, dst != 255
    source = values.astype(np.float32, copy=False)
    src_valid = np.isfinite(source)
    dst = np.full((height, width), np.nan, dtype=np.float32)
    reproject(source, dst, src_transform=native_transform(grid), src_crs=f"EPSG:{grid['epsg']}",
              src_nodata=np.nan, dst_transform=dst_transform, dst_crs="EPSG:4326",
              dst_nodata=np.nan, resampling=Resampling.bilinear, init_dest_nodata=True)
    return dst, np.isfinite(dst)


def interpolate_color(value: float, stops: list[tuple[float, tuple[int, int, int]]]) -> tuple[int, int, int]:
    if value <= stops[0][0]:
        return stops[0][1]
    if value >= stops[-1][0]:
        return stops[-1][1]
    for (lo, c0), (hi, c1) in zip(stops, stops[1:]):
        if lo <= value <= hi:
            t = (value - lo) / (hi - lo)
            return tuple(round(a + t * (b - a)) for a, b in zip(c0, c1))
    raise AssertionError("unreachable")


def rgba_from_values(values: np.ndarray, valid: np.ndarray, kind: str) -> np.ndarray:
    out = np.zeros((*values.shape, 4), dtype=np.uint8)
    if kind == "lossyear":
        # Code zero is visible, valid “no mapped loss” (not transparent/nodata).
        out[valid & (values == 0)] = (224, 232, 238, 220)
        for year_code in range(1, 25):
            rgb = interpolate_color(year_code, LOSS_STOPS)
            out[valid & (values == year_code)] = (*rgb, 230)
    elif kind == "treecover":
        for canopy in range(101):
            out[valid & (values == canopy)] = (*interpolate_color(canopy, TREE_STOPS), 220)
    elif kind == "dem":
        lo, hi = float(np.nanmin(values[valid])), float(np.nanmax(values[valid]))
        stops = [(lo, (36, 76, 125)), (lo + .35*(hi-lo), (47, 142, 151)),
                 (lo + .68*(hi-lo), (218, 190, 113)), (hi, (126, 78, 50))]
        for value in np.unique(values[valid]):
            out[valid & (values == value)] = (*interpolate_color(float(value), stops), 220)
    else:
        raise ValueError(kind)
    return out


def save_overlay(name: str, values: np.ndarray, grid: dict, *, kind: str,
                 categorical: bool, legend: dict, period: str, resolution: str,
                 source_key: str) -> dict:
    dst_transform, width, height, bounds = target_grid(grid)
    warped, valid = warp_native(values, grid, dst_transform, width, height, categorical=categorical)
    rgba = rgba_from_values(warped, valid, kind)
    path = LAYER_DIR / name
    Image.fromarray(rgba, mode="RGBA").save(path, format="PNG", optimize=True)
    return {"path": path.relative_to(ROOT).as_posix(), "sha256": file_hash(path),
            "bounds_wgs84": bounds, "legend": legend, "period": period,
            "resolution_qualification": resolution, "source_key": source_key,
            "crs": "EPSG:4326", "width": width, "height": height,
            "pixel_transform_wgs84": list(dst_transform)[:6],
            "resampling": "nearest" if categorical else "bilinear",
            "format": "RGBA PNG; alpha=0 only outside valid warped source coverage"}


def build() -> dict:
    manifest = json.loads(MANIFEST.read_text())
    grid = manifest["native_grid"]
    hansen_path = ROOT / manifest["forest_change"]["path"]
    dem_path = ROOT / manifest["derived"]["path"]
    # Verify actual cached inputs first; never fetch or regenerate source data here.
    if file_hash(hansen_path) != manifest["forest_change"]["sha256"]:
        raise ValueError("Hansen native NPZ hash mismatch; refusing to build overlays")
    if file_hash(dem_path) != manifest["derived"]["sha256"]:
        raise ValueError("DEM native NPZ hash mismatch; refusing to build overlays")
    hansen = np.load(hansen_path)
    dem = np.load(dem_path)
    overlays = {
        "hansen_lossyear": save_overlay(
            "hansen-lossyear-2001-2024.png", hansen["lossyear"], grid, kind="lossyear", categorical=True,
            legend={"title": "Hansen Global Forest Change loss year", "unit": "year code",
                    "items": [{"value": 0, "label": "No mapped loss through 2024", "color": "#e0e8ee"}]
                        + [{"value": code, "label": str(2000 + code),
                            "color": "#%02x%02x%02x" % interpolate_color(code, LOSS_STOPS)}
                           for code in range(1, 25)]
                        + [{"value": 255, "label": "Nodata / transparent", "color": "transparent"}],
                    "year_code_rule": "1..24 = 2000 + code; 0 is valid no mapped loss, not nodata"},
            period="2001–2024; code 0 means no mapped loss through 2024",
            resolution="Hansen Landsat-derived source ~30 m; native 20 m grid sampling; WGS84 output raster is a visualization reprojection, not increased source resolution.",
            source_key="forest_change.lossyear"),
        "hansen_treecover2000": save_overlay(
            "hansen-treecover2000.png", hansen["treecover2000"], grid, kind="treecover", categorical=True,
            legend={"title": "Tree canopy cover circa 2000", "unit": "percent", "min": 0, "max": 100,
                    "palette_stops": [{"value": value, "color": "#%02x%02x%02x" % color} for value, color in TREE_STOPS],
                    "nodata": "transparent"}, period="circa 2000",
            resolution="Hansen Landsat-derived source ~30 m; nearest to native 20 m grid; WGS84 output is visualization-only.",
            source_key="forest_change.treecover2000"),
        "dem_elevation": save_overlay(
            "aws-terrain-elevation.png", dem["elevation_m"], grid, kind="dem", categorical=False,
            legend={"title": "Terrain elevation", "unit": "m", "min": round(float(np.nanmin(dem["elevation_m"])), 2),
                    "max": round(float(np.nanmax(dem["elevation_m"])), 2), "palette": "blue/teal low → ochre/brown high",
                    "nodata": "transparent"}, period="static terrain compilation (vintage varies by underlying source)",
            resolution="AWS Terrain/Mapzen zoom 12 source ~19 m/pixel at AOI; sampled native grid then bilinear WGS84 visualization warp. Not hydrologically conditioned.",
            source_key="derived.elevation_m"),
    }
    # Backwards-compatible additive key only; retain all existing manifest fields.
    manifest["overlays"] = overlays
    MANIFEST.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    return overlays


if __name__ == "__main__":
    print(json.dumps(build(), indent=2, ensure_ascii=False))
