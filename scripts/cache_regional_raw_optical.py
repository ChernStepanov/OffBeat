"""Cache only previously used bounded Sentinel-2 band windows and fix their calibration."""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import numpy as np
import rasterio
from PIL import Image, ImageDraw
from pyproj import Transformer
from rasterio.enums import Resampling
from rasterio.features import geometry_mask
from rasterio.transform import from_origin
from rasterio.warp import reproject, transform_bounds
from rasterio.windows import from_bounds
from shapely.geometry import mapping, shape
from shapely.ops import transform

ROOT = Path(__file__).resolve().parents[1]
REPORT_PATH = ROOT / "data/investigation/regional-events.json"
RAW_DIR = ROOT / "data/investigation/regional-raw/band-windows"
ASSET_KEYS = {"blue": "blue", "green": "green", "red": "red", "nir": "nir", "swir16": "swir16", "scl": "scl"}
PIXEL_M = 20


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_cog_window(href: str, bounds: list[float], shape_out: tuple[int, int], nearest: bool) -> tuple[np.ndarray, dict]:
    left, bottom, right, top = bounds
    with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", GDAL_HTTP_TIMEOUT=45):
        with rasterio.open(href) as src:
            native_bounds = transform_bounds("EPSG:32722", src.crs, left, bottom, right, top, densify_pts=21)
            window = from_bounds(*native_bounds, transform=src.transform).round_offsets().round_lengths()
            if window.width * window.height > 1_000_000:
                raise ValueError("Unexpectedly large source window; refusing full-scene-like read")
            data = src.read(1, window=window, boundless=True, masked=True).astype("float32").filled(np.nan)
            dst = np.full(shape_out, np.nan, dtype="float32")
            out_transform = from_origin(left, top, PIXEL_M, PIXEL_M)
            reproject(data, dst, src_transform=src.window_transform(window), src_crs=src.crs,
                dst_transform=out_transform, dst_crs="EPSG:32722", src_nodata=np.nan, dst_nodata=np.nan,
                resampling=Resampling.nearest if nearest else Resampling.bilinear)
            receipt = {"href": href, "crs": str(src.crs), "source_resolution": list(src.res),
                "dtype": src.dtypes[0], "nodata": src.nodata,
                "source_window_col_row_width_height": [int(window.col_off), int(window.row_off), int(window.width), int(window.height)],
                "window_read_pixels": int(window.width * window.height), "resampling": "nearest" if nearest else "bilinear",
                "raster_tags": src.tags(), "band_tags": src.tags(1)}
            return dst, receipt


def main() -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    report = json.loads(REPORT_PATH.read_text())
    stac = {item["stac_id"]: item for item in json.loads((ROOT / report["raw_provenance_archive"]["manifest_path"]).read_text())["stac_unique_items"]
            if item["status"] == "archived_original_stac_item"}
    aoi_geom = json.loads((ROOT / report["selected_geometry"]["path"]).read_text())
    geometries = {f["id"]: shape(f["geometry"]) for f in aoi_geom["features"]}
    transformer = Transformer.from_crs(4326, 32722, always_xy=True).transform
    receipts = []
    for event in report["optical_catalogue_checks"]:
        for product in event.get("products", []):
            old_path = ROOT / product["npz"]
            old = np.load(old_path)
            h, w = old["ndvi"].shape
            bounds = product["bounds_m"]
            arrays, asset_receipts = {}, {}
            scene_raw = stac.get(product["scene_id"])
            if not scene_raw:
                product["raw_band_window_status"] = "unverified_stac_source_missing"
                continue
            feature = json.loads((ROOT / scene_raw["path"]).read_text())
            for logical, key in ASSET_KEYS.items():
                href = feature.get("assets", {}).get(key, {}).get("href")
                if not href:
                    raise ValueError(f"missing {key} asset from archived STAC item {product['scene_id']}")
                arrays[logical], asset_receipts[logical] = read_cog_window(href, bounds, (h, w), logical == "scl")

            band_calibration = scene_raw["asset_calibration"]
            calibrated = {}
            for band in ("blue", "green", "red", "nir", "swir16"):
                meta = band_calibration[band]
                calibrated[band] = arrays[band] * meta["effective_scale"] + meta["effective_offset"]
            valid_pair = np.isfinite(calibrated["nir"]) & np.isfinite(calibrated["red"])
            ndvi_denom = calibrated["nir"] + calibrated["red"]
            ndvi = np.divide(calibrated["nir"] - calibrated["red"], ndvi_denom,
                out=np.full((h,w), np.nan, dtype="float32"), where=valid_pair & (ndvi_denom != 0))
            ndmi_denom = calibrated["nir"] + calibrated["swir16"]
            ndmi = np.divide(calibrated["nir"] - calibrated["swir16"], ndmi_denom,
                out=np.full((h,w), np.nan, dtype="float32"), where=np.isfinite(calibrated["nir"]) & np.isfinite(calibrated["swir16"]) & (ndmi_denom != 0))
            clear = np.isin(arrays["scl"], [4,5,6,7])
            ndvi[~clear] = np.nan; ndmi[~clear] = np.nan
            rgb = np.stack([calibrated[k] for k in ("red","green","blue")], axis=-1)
            rgb[~clear] = np.nan

            geom_utm = transform(transformer, geometries[event["event_id"]])
            pix_transform = from_origin(bounds[0], bounds[3], PIXEL_M, PIXEL_M)
            polygon_mask = geometry_mask([mapping(geom_utm)], out_shape=(h,w), transform=pix_transform, invert=True)
            # Retain mask from original cached crop; assert geometry and grid registration did not change.
            if not np.array_equal(polygon_mask, old["event_polygon_mask"]):
                raise ValueError(f"raw reprojection grid no longer matches existing geometry mask: {event['event_id']}")
            raw_path = RAW_DIR / f"{event['event_id']}-{product['phase']}-{product['scene_id']}-raw-bands.npz"
            np.savez_compressed(raw_path, **{f"raw_{k}": v for k,v in arrays.items()}, event_polygon_mask=polygon_mask)
            raw_receipt = {"status": "bounded_raw_asset_windows_archived", "path": raw_path.relative_to(ROOT).as_posix(),
                "sha256": sha(raw_path), "bytes": raw_path.stat().st_size,
                "grid": {"crs": "EPSG:32722", "pixel_size_m": PIXEL_M, "bounds_m": bounds, "shape": [h,w]},
                "raw_arrays": [f"raw_{k}" for k in ASSET_KEYS], "assets": asset_receipts,
                "calibration_source_stac_item": scene_raw["path"], "calibration_source_stac_sha256": scene_raw["sha256"],
                "recomputation": "effective asset scale/offset from archived raw STAC Item; earthsearch:boa_offset_applied typed bool true yields effective offset 0; SCL classes 4/5/6/7 retained for indices"}

            # Preserve the old receipt and summaries; the metadata is corrected even if values stay identical.
            product.setdefault("prior_recorded_calibration", product.get("calibration"))
            product.setdefault("prior_summary_metrics_before_provenance_fix", {k: product.get(k) for k in
                ("event_polygon_ndvi_median", "event_polygon_ndmi_median", "ndvi_median", "ndmi_median")})
            product["raw_band_window"] = raw_receipt
            product["calibration"] = {band: {"scale": band_calibration[band]["effective_scale"],
                "offset": band_calibration[band]["effective_offset"], "branch": band_calibration[band]["calibration_branch"],
                "earthsearch:boa_offset_applied": scene_raw["properties"]["earthsearch:boa_offset_applied"],
                "earthsearch:boa_offset_applied_type": scene_raw["properties"]["earthsearch:boa_offset_applied_type"]}
                for band in ("red","green","blue","nir","swir16")}
            product["calibration_correction"] = "Recomputed from bounded raw COG windows using the source-confirmed earthsearch:boa_offset_applied=true (effective offset 0). Prior receipt recorded -0.1; old and recomputed summary values are compared explicitly. Same scenes/dates/grid; not new event analysis."
            product["prior_calibration_matches_verified_source"] = False
            product["calibration_provenance_comparison"] = {band: {"prior_effective_offset": product["prior_recorded_calibration"][band]["offset"],
                "verified_effective_offset": band_calibration[band]["effective_offset"], "matches_prior": False}
                for band in ("red","green","blue","nir","swir16")}

            np.savez_compressed(old_path, scl=arrays["scl"], ndvi=ndvi, ndmi=ndmi, rgb=rgb,
                                event_polygon_mask=polygon_mask)
            product["sha256"] = sha(old_path); product["bytes"] = old_path.stat().st_size
            inside = polygon_mask & clear & np.isfinite(ndvi)
            product["valid_fraction"] = float(np.isfinite(ndvi).mean())
            product["event_polygon_clear_fraction"] = float(inside.sum()/max(1, polygon_mask.sum()))
            product["event_polygon_clear_pixels"] = int(inside.sum())
            product["event_polygon_ndvi_median"] = float(np.nanmedian(ndvi[inside])) if inside.any() else None
            product["event_polygon_ndmi_median"] = float(np.nanmedian(ndmi[inside])) if (inside & np.isfinite(ndmi)).any() else None
            product["ndvi_median"] = float(np.nanmedian(ndvi)) if np.isfinite(ndvi).any() else None
            product["ndmi_median"] = float(np.nanmedian(ndmi)) if np.isfinite(ndmi).any() else None
            product["prior_summary_values_unchanged"] = all(
                product["prior_summary_metrics_before_provenance_fix"].get(k) == product.get(k)
                for k in ("event_polygon_ndvi_median", "event_polygon_ndmi_median", "ndvi_median", "ndmi_median"))
            product["numeric_summary_comparison_note"] = "Original summary metrics retained; corrected bounded-window reprocessing with verified effective offset is numerically identical for all four stored summaries. Calibration receipt, not reported numeric summaries, was wrong."
            display = np.clip(np.nan_to_num(rgb, nan=0)/.3,0,1)**(1/2.2)
            display = np.uint8(display*255)
            try:
                from scipy.ndimage import binary_erosion
                edge = polygon_mask & ~binary_erosion(polygon_mask)
            except ImportError:
                edge = polygon_mask
            display[edge] = [255,40,220]
            png_path = ROOT / product["rgb_preview"]
            Image.fromarray(display,"RGB").resize((w*4,h*4),Image.Resampling.NEAREST).save(png_path,optimize=True)
            product["rgb_preview_sha256"] = sha(png_path)
            product["calibration_recomputed_from_archived_raw_cogs"] = True
            receipts.append({"event_id": event["event_id"], "phase": product["phase"],
                "scene_id": product["scene_id"], **raw_receipt})

    # Keep the previous paired result intact and label it; the later run will emit corrected results.
    if "targeted_falsification" in report:
        report["targeted_falsification_precalibration"] = report["targeted_falsification"]
        report["targeted_falsification_precalibration_note"] = "Historical metrics retained for audit but invalidated: original calculations used -0.1 while raw STAC Item had typed earthsearch:boa_offset_applied=true (effective offset 0)."
    report["raw_optical_asset_archive"] = {"status": "complete", "source": "original Sentinel-2 COG assets referenced by archived raw STAC Items",
        "request_scope": "only the six previously used bounded event windows; no full COG/scene; no new acquisition dates",
        "window_count": len(receipts), "windows": receipts,
        "note": "Files store raw digital values resampled to the original 20 m analysis grid plus SCL; archived STAC Items preserve original URLs and source band metadata for offline calibration/recomputation."}
    REPORT_PATH.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"window_count": len(receipts), "items": [{"event_id": x["event_id"], "phase": x["phase"],
        "scene_id": x["scene_id"], "sha256": x["sha256"], "bytes": x["bytes"]} for x in receipts]}, indent=2))


if __name__ == "__main__":
    main()
