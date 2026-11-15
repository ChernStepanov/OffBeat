"""Recompute existing regional optical products from archived raw band windows; no network access."""
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
REPORT_PATH = ROOT / "data/investigation/regional-events.json"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compute(raw: dict, calibration: dict) -> tuple[dict, dict]:
    reflectance = {}
    for band in ("red", "green", "blue", "nir", "swir16"):
        meta = calibration[band]
        reflectance[band] = raw[f"raw_{band}"] * meta["effective_scale"] + meta["effective_offset"]
    ndvi_den = reflectance["nir"] + reflectance["red"]
    ndmi_den = reflectance["nir"] + reflectance["swir16"]
    ndvi = np.divide(reflectance["nir"]-reflectance["red"], ndvi_den,
        out=np.full(ndvi_den.shape, np.nan, dtype="float32"),
        where=np.isfinite(ndvi_den) & (ndvi_den != 0))
    ndmi = np.divide(reflectance["nir"]-reflectance["swir16"], ndmi_den,
        out=np.full(ndmi_den.shape, np.nan, dtype="float32"),
        where=np.isfinite(ndmi_den) & (ndmi_den != 0))
    clear = np.isin(raw["raw_scl"], [4,5,6,7])
    ndvi[~clear] = np.nan; ndmi[~clear] = np.nan
    rgb = np.stack([reflectance[k] for k in ("red","green","blue")], axis=-1)
    rgb[~clear] = np.nan
    return {"scl": raw["raw_scl"], "ndvi": ndvi, "ndmi": ndmi,
            "rgb": rgb, "event_polygon_mask": raw["event_polygon_mask"].astype(bool)}, reflectance


def main() -> None:
    report = json.loads(REPORT_PATH.read_text())
    outputs = []
    for event in report["optical_catalogue_checks"]:
        for product in event.get("products", []):
            receipt = product.get("raw_band_window")
            calibration = product.get("raw_stac_asset_calibration")
            if not receipt or not calibration:
                product["offline_recompute_status"] = "unavailable_missing_archived_raw_window_or_stac_calibration"
                continue
            raw_path = ROOT / receipt["path"]
            if sha(raw_path) != receipt["sha256"]:
                raise ValueError(f"raw window hash mismatch: {raw_path}")
            with np.load(raw_path) as archive:
                raw = {key: archive[key] for key in archive.files}
            result, reflectance = compute(raw, calibration)
            path = ROOT / product["npz"]
            product.setdefault("prior_recorded_calibration", product.get("calibration"))
            product.setdefault("prior_summary_metrics_before_provenance_fix", {key: product.get(key) for key in
                ("event_polygon_ndvi_median", "event_polygon_ndmi_median", "ndvi_median", "ndmi_median")})
            np.savez_compressed(path, **result)
            polygon = result["event_polygon_mask"]
            clear = np.isin(result["scl"], [4,5,6,7])
            vi = polygon & clear & np.isfinite(result["ndvi"])
            mi = polygon & clear & np.isfinite(result["ndmi"])
            product["event_polygon_clear_fraction"] = float(vi.sum()/max(1, polygon.sum()))
            product["event_polygon_clear_pixels"] = int(vi.sum())
            product["valid_fraction"] = float(np.isfinite(result["ndvi"]).mean())
            product["event_polygon_ndvi_median"] = float(np.nanmedian(result["ndvi"][vi])) if vi.any() else None
            product["event_polygon_ndmi_median"] = float(np.nanmedian(result["ndmi"][mi])) if mi.any() else None
            product["ndvi_median"] = float(np.nanmedian(result["ndvi"])) if np.isfinite(result["ndvi"]).any() else None
            product["ndmi_median"] = float(np.nanmedian(result["ndmi"])) if np.isfinite(result["ndmi"]).any() else None
            product["sha256"] = sha(path); product["bytes"] = path.stat().st_size
            product["calibration"] = {band: {"scale": values["effective_scale"], "offset": values["effective_offset"],
                "branch": values["calibration_branch"],
                "earthsearch:boa_offset_applied": product["raw_stac_properties"]["earthsearch:boa_offset_applied"],
                "earthsearch:boa_offset_applied_type": product["raw_stac_properties"]["earthsearch:boa_offset_applied_type"]}
                for band, values in calibration.items()}
            product["calibration_recomputed_from_archived_raw_cogs"] = True
            old = product["prior_summary_metrics_before_provenance_fix"]
            summary_keys = ("event_polygon_ndvi_median", "event_polygon_ndmi_median", "ndvi_median", "ndmi_median")
            product["prior_summary_values_unchanged"] = all(old.get(key) == product.get(key) for key in summary_keys)
            product["numeric_summary_comparison_note"] = "Old and verified-offset recomputed summaries are compared; same scene/date/grid, no new acquisitions."

            rgb = result["rgb"]
            display = np.clip(np.nan_to_num(rgb, nan=0)/.3,0,1)**(1/2.2)
            display = np.uint8(display*255)
            try:
                from scipy.ndimage import binary_erosion
                edge = polygon & ~binary_erosion(polygon)
            except ImportError:
                edge = polygon
            display[edge] = [255,40,220]
            preview = ROOT / product["rgb_preview"]
            display_image = Image.fromarray(display,"RGB").resize((display.shape[1]*4,display.shape[0]*4),Image.Resampling.NEAREST)
            display_image.save(preview,optimize=True)
            product["rgb_preview_sha256"] = sha(preview)
            product["offline_recompute_status"] = "recomputed_from_hash_verified_local_raw_windows"
            outputs.append({"event_id": event["event_id"], "phase": product["phase"],
                "npz_sha256": product["sha256"], "summaries_unchanged": product["prior_summary_values_unchanged"]})
    report["offline_calibration_recompute"] = {"status": "complete" if len(outputs) == 6 else "partial",
        "network_requests": 0, "products_recomputed": len(outputs), "products": outputs,
        "method": "Archived raw reflectance-band digital-number windows plus raw STAC Item effective scale/offset and typed BOA flag; recomputed NDVI/NDMI and RGB on original 20 m grids."}
    REPORT_PATH.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report["offline_calibration_recompute"], indent=2))


if __name__ == "__main__":
    main()
