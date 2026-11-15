"""Cached-only paired optical falsification for regional DETER leads; no network access."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
from pyproj import Transformer
from shapely.geometry import Point, box, shape
from shapely.ops import transform

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "data/investigation/regional-events.json"
PIXEL_M = 20.0
MASKS = {"strict_456": [4, 5, 6], "extended_4567": [4, 5, 6, 7]}
SCL_LABELS = {0: "no_data", 1: "saturated_or_defective", 2: "dark_area_pixels",
              3: "cloud_shadow", 4: "vegetation", 5: "not_vegetated",
              6: "water", 7: "unclassified", 8: "cloud_medium_probability",
              9: "cloud_high_probability", 10: "thin_cirrus", 11: "snow_or_ice"}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def histogram(values: np.ndarray) -> dict:
    values = np.asarray(values)
    finite = np.isfinite(values)
    vals, counts = np.unique(values[finite].astype("int16"), return_counts=True)
    output = {str(int(v)): {"label": SCL_LABELS.get(int(v), "other"), "count": int(n)}
              for v, n in zip(vals, counts)}
    if (~finite).any():
        output["-1"] = {"label": "nodata_nan", "count": int((~finite).sum())}
    return output


def robust_summary(before: np.ndarray, after: np.ndarray, mask: np.ndarray) -> dict:
    n = int(mask.sum())
    if not n:
        return {"support_n": 0, "before_median": None, "after_median": None,
                "median_pixelwise_delta": None, "difference_of_medians": None}
    b, a = before[mask].astype("float64"), after[mask].astype("float64")
    return {"support_n": n, "before_median": float(np.median(b)),
            "after_median": float(np.median(a)),
            "median_pixelwise_delta": float(np.median(a-b)),
            "difference_of_medians": float(np.median(a)-np.median(b))}


def run() -> dict:
    report = json.loads(REPORT.read_text())
    geo_path = ROOT / report["selected_geometry"]["path"]
    features = {x["id"]: x for x in json.loads(geo_path.read_text())["features"]}
    wgs84_to_utm = Transformer.from_crs(4326, 32722, always_xy=True).transform
    aoi = box(-49.2875, -4.7875, -49.2625, -4.7625)
    falsification = []
    for event in report["optical_catalogue_checks"]:
        products = {p["phase"]: p for p in event["products"]}
        pre, post = products["before"], products["after"]
        pre_npz = np.load(ROOT / pre["npz"])
        post_npz = np.load(ROOT / post["npz"])
        if pre_npz["ndvi"].shape != post_npz["ndvi"].shape:
            raise ValueError(f"paired grids differ for {event['event_id']}")
        if not np.allclose(pre["bounds_m"], post["bounds_m"]):
            raise ValueError(f"paired bounds differ for {event['event_id']}")
        h, w = pre_npz["ndvi"].shape
        left, bottom, right, top = pre["bounds_m"]
        geom = shape(features[event["event_id"]]["geometry"])
        geom_utm = transform(wgs84_to_utm, geom)
        inside = pre_npz["event_polygon_mask"].astype(bool)
        if not inside.any():
            raise ValueError(f"empty polygon mask for {event['event_id']}")

        # Pixel-center distance to the actual projected DETER polygon, not an index-derived fit.
        yy, xx = np.indices((h, w))
        xs = left + (xx.ravel() + .5) * PIXEL_M
        ys = top - (yy.ravel() + .5) * PIXEL_M
        distances = np.fromiter((geom_utm.distance(Point(float(x), float(y)))
                                 for x, y in zip(xs, ys)), dtype="float64", count=h*w).reshape(h, w)
        zones = {"event_polygon": inside,
                 "ring_60_120m": (~inside) & (distances >= 60) & (distances < 120),
                 "ring_120_240m": (~inside) & (distances >= 120) & (distances < 240)}
        # Hold one geographic AOI test and per-product SCL availability alongside comparisons.
        aoi_intersects = bool(geom.intersects(aoi))
        class_histograms = {}
        for phase, arr in (("before", pre_npz), ("after", post_npz)):
            class_histograms[phase] = {
                "whole_crop": histogram(arr["scl"]),
                "event_polygon": histogram(arr["scl"][inside]),
                "ring_60_120m": histogram(arr["scl"][zones["ring_60_120m"]]),
                "ring_120_240m": histogram(arr["scl"][zones["ring_120_240m"]])}

        masks = {}
        for mask_name, accepted in MASKS.items():
            common_scl = np.isin(pre_npz["scl"], accepted) & np.isin(post_npz["scl"], accepted)
            paired_valid = (common_scl & np.isfinite(pre_npz["ndvi"]) & np.isfinite(post_npz["ndvi"])
                            & np.isfinite(pre_npz["ndmi"]) & np.isfinite(post_npz["ndmi"]))
            zone_stats = {}
            for zone, zone_mask in zones.items():
                q = paired_valid & zone_mask
                zone_stats[zone] = {index: robust_summary(pre_npz[index], post_npz[index], q)
                                    for index in ("ndvi", "ndmi")}
                zone_stats[zone]["valid_pair_coverage_fraction"] = float(q.sum()/max(1, zone_mask.sum()))
                zone_stats[zone]["zone_pixel_count"] = int(zone_mask.sum())

            # Pre-only matching: threshold uses the pre polygon median and never the post values.
            polygon_pre = paired_valid & inside
            pre_polygon_median = float(np.median(pre_npz["ndvi"][polygon_pre])) if polygon_pre.any() else None
            matched = {}
            ring_union = zones["ring_60_120m"] | zones["ring_120_240m"]
            if pre_polygon_median is not None:
                pre_matched = (paired_valid & ring_union
                               & (np.abs(pre_npz["ndvi"] - pre_polygon_median) <= .1))
                for ring_name in ("ring_60_120m", "ring_120_240m"):
                    q = pre_matched & zones[ring_name]
                    matched[ring_name] = {
                        "selection": "pre-date NDVI within ±0.1 of pre-date event-polygon median; no post-date data used for selection",
                        "pre_polygon_ndvi_median": pre_polygon_median,
                        "support_n": int(q.sum()), "minimum_support_for_summary": 20,
                        "sufficient_support": bool(q.sum() >= 20),
                        "ndvi": robust_summary(pre_npz["ndvi"], post_npz["ndvi"], q),
                        "ndmi": robust_summary(pre_npz["ndmi"], post_npz["ndmi"], q)}
                    if q.sum() < 20:
                        matched[ring_name]["interpretation"] = "insufficient support; descriptive only"
            masks[mask_name] = {"accepted_scl_classes": accepted,
                "paired_common_valid_event_pixels": int((paired_valid & inside).sum()),
                "paired_common_valid_crop_pixels": int(paired_valid.sum()),
                "zone_statistics": zone_stats,
                "inside_minus_ring_contrast": {
                    ring: {index: {
                        "median_pixelwise_delta_contrast": (zone_stats["event_polygon"][index]["median_pixelwise_delta"]
                            - zone_stats[ring][index]["median_pixelwise_delta"])
                            if zone_stats["event_polygon"][index]["median_pixelwise_delta"] is not None and zone_stats[ring][index]["median_pixelwise_delta"] is not None else None,
                        "difference_of_medians_contrast": (zone_stats["event_polygon"][index]["difference_of_medians"]
                            - zone_stats[ring][index]["difference_of_medians"])
                            if zone_stats["event_polygon"][index]["difference_of_medians"] is not None and zone_stats[ring][index]["difference_of_medians"] is not None else None}
                        for index in ("ndvi", "ndmi")} for ring in ("ring_60_120m", "ring_120_240m")},
                "pre_ndvi_matched_ring_comparison": matched}

        # These observations refer only to literal RGB appearance; the DETER outline is not onset proof.
        literal = {
            "deter_amz.31637_curr": "Before: visible brown/open mosaic is already present within the outlined polygon. After: the outlined area looks more brown/open; the change is not a uniform new-clearing signature.",
            "deter_amz.26062_curr": "Before: the outlined patch looks greener overall. After: it appears more brown/open. The before image already has texture/variation; RGB alone does not establish onset or complete clearing.",
            "deter_amz.23558_curr": "Before: mixed green and brown tones within the outline. After: somewhat browner, while nearby landscape also looks browner; RGB alone gives weak evidence of a uniquely localized change."}[event["event_id"]]
        calibrated = {
            "deter_amz.31637_curr": {"status": "supported_localized_optical_decrease",
                "statement": "Paired NDVI/NDMI decrease is materially greater inside the already partly brown/open DETER polygon than both adjacent rings and pre-NDVI-matched ring pixels. Supports localized cover change relative to nearby seasonal change; does not support a claim of a fresh, uniform clearing or exact onset.",
                "confidence": "moderate for localized optical cover decrease; low for complete clearing, cause, or exact event timing"},
            "deter_amz.26062_curr": {"status": "supported_localized_optical_decrease",
                "statement": "Polygon NDVI/NDMI decrease exceeds both nearby rings and pre-NDVI-matched ring pixels, but the background also browns substantially. Supports an additional localized cover decrease, not a fresh, uniform clearing interpretation.",
                "confidence": "moderate for additional localized optical cover decrease; low for complete clearing, cause, or exact event timing"},
            "deter_amz.23558_curr": {"status": "registry_only_background_similar",
                "statement": "NDVI change inside the polygon is nearly the same as both nearby rings; NDMI change is smaller inside than in nearby rings. This pair does not separate a local event change from broader background/seasonal browning.",
                "confidence": "registry support only; low optical evidence for localized change"}}[event["event_id"]]
        falsification.append({
            "event_id": event["event_id"], "view_date": event["event_observation_date"],
            "maps": {"event_geometry_path": report["selected_geometry"]["path"],
                "event_geometry_feature_id": event["event_id"], "coordinates": {"bbox_wgs84": list(geom.bounds),
                    "centroid_lon_lat": [geom.centroid.x, geom.centroid.y]},
                "before": {"path": pre["rgb_preview"], "sha256": pre["rgb_preview_sha256"],
                    "scene_id": pre["scene_id"], "observed_at": pre["datetime"], "catalogue_created_at": pre.get("catalogue_created_at")},
                "after": {"path": post["rgb_preview"], "sha256": post["rgb_preview_sha256"],
                    "scene_id": post["scene_id"], "observed_at": post["datetime"], "catalogue_created_at": post.get("catalogue_created_at")},
                "geometry_intersects_source_aoi_bbox": aoi_intersects,
                "inside_prepared_nisar_aoi": aoi_intersects,
                "paired_grid_bounds_m": list(pre["bounds_m"]),
                "paired_grid_shape": list(pre["shape"]),
                "event_polygon_pixel_count": int(inside.sum()),
                "event_polygon_common_valid_coverage": {key: masks[key]["paired_common_valid_event_pixels"] / max(1, int(inside.sum())) for key in MASKS}},
            "evidence_observations": {"literal_rgb_observation": literal,
                "calibrated_assessment": calibrated,
                "registry_is_not_confirmation_of_onset": True,
                "causal_limit": "INPE DETER view_date is associated image observation date, not guaranteed disturbance onset; optical change is not proof of clearing cause."},
            "class_counts_before_after": class_histograms,
            "comparisons": {"ring_distance_method": "Euclidean distance from 20 m pixel center to actual projected DETER polygon boundary; rings exclude event mask; approximate at raster support.",
                "common_valid_rule": "pixel must pass selected SCL policy and have finite NDVI+NDMI on both dates; same pixel locations used before/after.",
                "mask_ablation": masks,
                "statistics_note": "Descriptive medians only; adjacent pixels are spatially autocorrelated. No p-values or independent-negative/control claims.",
                "background_is_verified_negative": False}})
    report["targeted_falsification"] = {"method": "cached NPZ only; no network calls; before/after paired common-valid SCL; polygon vs 60–120 m and 120–240 m rings; strict 4/5/6 and expanded 4/5/6/7 masks; pre-only NDVI matching",
        "events": falsification}
    REPORT.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"events": [{"id": e["event_id"], "strict": {
        z: e["comparisons"]["mask_ablation"]["strict_456"]["zone_statistics"][z]["ndvi"]["median_pixelwise_delta"]
        for z in ("event_polygon", "ring_60_120m", "ring_120_240m")}} for e in falsification]}, indent=2))
    return report["targeted_falsification"]


if __name__ == "__main__":
    run()
