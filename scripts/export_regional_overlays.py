"""Export Leaflet-ready geographic RGB overlays from cached regional NPZs only."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image
import rasterio
from rasterio.transform import from_origin
from rasterio.warp import calculate_default_transform, reproject, Resampling, transform_bounds

ROOT = Path(__file__).resolve().parents[1]
REPORT_PATH = ROOT / "data/investigation/regional-events.json"
OUT = ROOT / "data/investigation/regional"
MASK_POLICY = "strict SCL classes [4,5,6]; nodata/non-finite RGB alpha=0; SCL nearest-neighbor"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def export(product: dict, event_id: str) -> dict:
    source = ROOT / product["npz"]
    if sha(source) != product["sha256"]:
        raise ValueError(f"Cached NPZ hash mismatch: {source}")
    with np.load(source) as cached:
        rgb = cached["rgb"].astype("float32")
        scl = cached["scl"].astype("float32")
    if rgb.ndim != 3 or rgb.shape[2] != 3 or rgb.shape[:2] != scl.shape:
        raise ValueError(f"Unexpected cached RGB/SCL dimensions: {source}")
    h, w = scl.shape
    west, south, east, north = product["bounds_m"]
    src_transform = from_origin(west, north, 20.0, 20.0)  # pixel-edge transform, 20 m cells
    dst_transform, dst_width, dst_height = calculate_default_transform(
        "EPSG:32722", "EPSG:4326", w, h, west, south, east, north)
    if dst_width <= 0 or dst_height <= 0:
        raise ValueError("Invalid EPSG:4326 destination grid")

    warped_rgb = []
    for index in range(3):
        band = rgb[:, :, index]
        dest = np.full((dst_height, dst_width), np.nan, dtype="float32")
        reproject(band, dest, src_transform=src_transform, src_crs="EPSG:32722",
            dst_transform=dst_transform, dst_crs="EPSG:4326", src_nodata=np.nan,
            dst_nodata=np.nan, resampling=Resampling.bilinear)
        warped_rgb.append(dest)
    warped_rgb = np.stack(warped_rgb, axis=-1)

    # Reproject categorical SCL with nearest-neighbour; never blend class numbers.
    source_scl = np.where(np.isfinite(scl), scl, 0).astype("uint8")
    dest_scl = np.zeros((dst_height, dst_width), dtype="uint8")
    reproject(source_scl, dest_scl, src_transform=src_transform, src_crs="EPSG:32722",
        dst_transform=dst_transform, dst_crs="EPSG:4326", src_nodata=0, dst_nodata=0,
        resampling=Resampling.nearest)
    valid = np.isin(dest_scl, [4,5,6]) & np.isfinite(warped_rgb).all(axis=2)
    stretched = np.clip(warped_rgb / .3, 0, 1) ** (1/2.2)
    stretched = np.nan_to_num(stretched, nan=0.0, posinf=0.0, neginf=0.0)
    rgba = np.zeros((dst_height, dst_width, 4), dtype="uint8")
    rgba[:, :, :3] = np.uint8(np.clip(stretched, 0, 1) * 255)
    rgba[:, :, 3] = valid.astype("uint8") * 255

    date = product["datetime"][:10]
    scene = product["scene_id"]
    out_path = OUT / f"{event_id}-{product['phase']}-{date}-leaflet-rgb.png"
    Image.fromarray(rgba, "RGBA").save(out_path, optimize=True)
    bounds_wgs84 = [float(dst_transform.c), float(dst_transform.f + dst_transform.e*dst_height),
        float(dst_transform.c + dst_transform.a*dst_width), float(dst_transform.f)]
    projected_bounds = transform_bounds("EPSG:32722", "EPSG:4326", west, south, east, north, densify_pts=21)
    grid_tolerance = max(abs(dst_transform.a), abs(dst_transform.e)) * 1.1 + 1e-9
    if any(abs(a-b) > grid_tolerance for a,b in zip(bounds_wgs84, projected_bounds)):
        raise ValueError(f"Warped raster edge bounds disagree by more than one destination pixel: {bounds_wgs84} vs {projected_bounds}")
    return {"path": out_path.relative_to(ROOT).as_posix(), "sha256": sha(out_path),
        "bounds_wgs84": bounds_wgs84, "date": date, "source_scene": scene,
        "mask_policy": MASK_POLICY,
        "resolution_qualification": "Cached source RGB is a 20 m EPSG:32722 grid (B04/B03/B02 bilinear-resampled from native 10 m); exported to a north-up EPSG:4326 display grid with bilinear RGB reprojection. This is a geographic display overlay, not native 10 m imagery or a measurement grid.",
        "crs": "EPSG:4326", "pixel_registration": "north-up affine raster; bounds are outer pixel edges; source 20 m pixel centers mapped from EPSG:32722 affine",
        "wgs84_affine": [float(dst_transform.a), float(dst_transform.b), float(dst_transform.c),
            float(dst_transform.d), float(dst_transform.e), float(dst_transform.f)],
        "dimensions_px": [dst_width, dst_height], "projected_source_bounds_wgs84": [float(x) for x in projected_bounds],
        "source_grid": {"crs": "EPSG:32722",
            "bounds_m": product["bounds_m"], "shape_px": [h,w], "resolution_m": 20.0},
        "alpha": {"valid_pixels": int(valid.sum()), "transparent_pixels": int((~valid).sum()),
            "nonzero_values": [0,255], "valid_fraction": float(valid.mean())}}


def main() -> None:
    report = json.loads(REPORT_PATH.read_text())
    outputs = []
    for event in report["optical_catalogue_checks"]:
        for product in event.get("products", []):
            overlay = export(product, event["event_id"])
            product["map_overlay"] = overlay
            outputs.append({"event_id": event["event_id"], "phase": product["phase"], **overlay})
    if len(outputs) != 6:
        raise RuntimeError(f"Expected six existing cached scenes, exported {len(outputs)}")
    report["regional_map_overlays"] = {"source": "existing calibrated regional NPZ RGB/SCL arrays",
        "network_requests": 0, "scene_count": len(outputs), "mask_policy": MASK_POLICY,
        "outputs": [{k: entry[k] for k in ("event_id","phase","path","sha256","bounds_wgs84","date","source_scene")} for entry in outputs]}
    REPORT_PATH.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report["regional_map_overlays"], indent=2))


if __name__ == "__main__":
    main()
