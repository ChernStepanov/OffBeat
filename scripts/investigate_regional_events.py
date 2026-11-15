"""Bounded read-only discovery of nearby dated INPE DETER alerts and optical context."""
from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path

import requests
import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.transform import from_origin
from rasterio.warp import transform_bounds, reproject
from rasterio.windows import from_bounds
from rasterio.features import geometry_mask
from PIL import Image
from shapely.geometry import shape, mapping, box
from shapely.ops import transform
from pyproj import Transformer

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/investigation/regional"
REPORT = ROOT / "data/investigation/regional-events.json"
DETER = "https://terrabrasilis.dpi.inpe.br/geoserver/ows"
STAC = "https://earth-search.aws.element84.com/v1/search"
CENTER = (-49.275, -4.775)
RADIUS_M = 25_000


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def area_m2(geom) -> float:
    project = Transformer.from_crs(4326, 32722, always_xy=True).transform
    return transform(project, geom).area


def bounded_deter() -> tuple[dict, list[dict]]:
    # This bounding rectangle encloses a 25 km radius around the exact study center.
    dx = RADIUS_M / (111_320 * math.cos(math.radians(CENTER[1])))
    dy = RADIUS_M / 110_574
    bbox = [CENTER[0] - dx, CENTER[1] - dy, CENTER[0] + dx, CENTER[1] + dy]
    cql = ("view_date >= '2025-01-01' AND view_date <= '2026-12-31' AND "
           f"BBOX(geom,{bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]},'CRS:84')")
    params = {"service": "WFS", "version": "2.0.0", "request": "GetFeature",
              "typeNames": "deter-amz:deter_amz", "CQL_FILTER": cql, "count": 500,
              "outputFormat": "application/json",
              "propertyName": "gid,classname,view_date,publish_month,areamunkm,municipality,uf,geom"}
    r = requests.get(DETER, params=params, timeout=90)
    r.raise_for_status()
    payload = r.json()
    records = []
    circle_project = Transformer.from_crs(4326, 32722, always_xy=True).transform
    center_x, center_y = circle_project(*CENTER)
    from shapely.geometry import Point
    center = Point(center_x, center_y)
    for f in payload.get("features", []):
        g = shape(f["geometry"])
        projected = transform(circle_project, g)
        dist = center.distance(projected)
        if dist > RADIUS_M:
            continue
        p = f["properties"]
        records.append({"id": f["id"], "geometry": f["geometry"], "properties": p,
                        "distance_center_m": round(dist, 1), "area_geometry_ha": round(area_m2(g) / 10_000, 3),
                        "bbox_wgs84": [round(x, 7) for x in g.bounds]})
    receipt = {"url": r.url, "status": r.status_code, "response_bytes": len(r.content),
               "feature_count_returned": len(payload.get("features", [])),
               "number_matched": payload.get("numberMatched"), "in_radius_count": len(records),
               "bbox_wgs84": bbox, "filter": cql,
               "queried_at_utc": datetime.now(timezone.utc).isoformat(),
               "crs": "OGC CRS:84 (WGS84 lon/lat)"}
    return receipt, records


def optical_window(item: dict, event: dict, phase: str) -> dict | None:
    """Read tiny COG windows and save SCL-masked reflectance/indices, never a full scene."""
    from datetime import date
    d = date.fromisoformat(event["properties"]["view_date"])
    scene_day = date.fromisoformat(item["properties"]["datetime"][:10])
    delta = (scene_day - d).days
    if (phase == "before" and not 10 <= -delta <= 180) or (phase == "after" and not 10 <= delta <= 180):
        return None
    geom = shape(event["geometry"])
    lon0, lat0, lon1, lat1 = geom.bounds
    project = Transformer.from_crs(4326, 32722, always_xy=True).transform
    x0, y0 = project(lon0, lat0); x1, y1 = project(lon1, lat1)
    pad = 300
    left, bottom, right, top = min(x0,x1)-pad, min(y0,y1)-pad, max(x0,x1)+pad, max(y0,y1)+pad
    resolution = 20
    width, height = math.ceil((right-left)/resolution), math.ceil((top-bottom)/resolution)
    right, bottom = left+width*resolution, top-height*resolution
    dst_transform = from_origin(left, top, resolution, resolution)
    shape_out = (height, width)
    assets = item.get("assets", {})
    arrays, asset_receipts = {}, {}
    aliases = {"red": "B04", "green": "B03", "blue": "B02", "nir": "B08", "swir16": "B11", "scl": "SCL"}
    for key in ("red", "green", "blue", "nir", "swir16", "scl"):
        asset = assets.get(key) or assets.get(aliases[key])
        if not asset or not asset.get("href"):
            return None
        with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", GDAL_HTTP_TIMEOUT=45):
            with rasterio.open(asset["href"]) as src:
                b = transform_bounds("EPSG:32722", src.crs, left, bottom, right, top, densify_pts=21)
                win = from_bounds(*b, transform=src.transform).round_offsets().round_lengths()
                raw = src.read(1, window=win, boundless=True, masked=True).astype("float32").filled(np.nan)
                dest = np.full(shape_out, np.nan, dtype="float32")
                reproject(raw, dest, src_transform=src.window_transform(win), src_crs=src.crs,
                    dst_transform=dst_transform, dst_crs="EPSG:32722", src_nodata=np.nan, dst_nodata=np.nan,
                    resampling=Resampling.nearest if key == "scl" else Resampling.bilinear)
                asset_receipts[key] = {"href": asset["href"], "crs": str(src.crs),
                    "native_resolution": list(src.res), "window_pixels": [int(win.width), int(win.height)],
                    "range_read": True}
                arrays[key] = dest
    clear = np.isin(arrays["scl"], [4,5,6,7])
    calibrated = {}
    props = item["properties"]
    for key in ("red", "green", "blue", "nir", "swir16"):
        rb = ((assets.get(key) or assets.get(aliases[key])).get("raster:bands") or [{}])[0]
        scale, offset = rb.get("scale", .0001), rb.get("offset", 0)
        if props.get("earthsearch:boa_offset_applied", False): offset = 0
        elif "offset" not in rb and float(props.get("s2:processing_baseline", 0)) >= 4: offset = -.1
        calibrated[key] = arrays[key] * scale + offset
    ndvi_den = calibrated["nir"] + calibrated["red"]
    ndmi_den = calibrated["nir"] + calibrated["swir16"]
    ndvi = np.divide(calibrated["nir"]-calibrated["red"], ndvi_den,
        out=np.full(shape_out, np.nan, dtype="float32"), where=np.isfinite(ndvi_den)&(ndvi_den != 0))
    ndmi = np.divide(calibrated["nir"]-calibrated["swir16"], ndmi_den,
        out=np.full(shape_out, np.nan, dtype="float32"), where=np.isfinite(ndmi_den)&(ndmi_den != 0))
    ndvi[~clear] = np.nan; ndmi[~clear] = np.nan
    geom_projected = transform(project, geom)
    inside = geometry_mask([mapping(geom_projected)], out_shape=shape_out, transform=dst_transform, invert=True)
    event_valid = inside & clear & np.isfinite(ndvi)
    rgb = np.stack([calibrated[k] for k in ("red", "green", "blue")], axis=-1)
    rgb[~clear] = np.nan
    tag = f"{event['id']}-{phase}-{scene_day.isoformat()}"
    path = OUT / f"{tag}.npz"
    np.savez_compressed(path, scl=arrays["scl"], ndvi=ndvi, ndmi=ndmi, rgb=rgb,
                        event_polygon_mask=inside)
    display = np.clip(np.nan_to_num(rgb, nan=0) / .3, 0, 1) ** (1/2.2)
    display = np.uint8(display * 255)
    try:
        from scipy.ndimage import binary_erosion
        edge = inside & ~binary_erosion(inside)
    except ImportError:
        edge = inside
    display[edge] = [255, 40, 220]
    png_path = OUT / f"{tag}-rgb.png"
    Image.fromarray(display, "RGB").resize((width*4, height*4), Image.Resampling.NEAREST).save(png_path, optimize=True)
    valid = np.isfinite(ndvi)
    return {"phase": phase, "scene_id": item["id"], "datetime": props.get("datetime"),
        "catalogue_created_at": props.get("created"), "catalogue_updated_at": props.get("updated"),
        "timestamp_note": "datetime is acquisition observation time; created/updated are Earth Search catalogue record timestamps, not the satellite processor's processing time",
        "days_from_view_date": delta, "cloud_percent_scene": props.get("eo:cloud_cover"),
        "item_url": next((l["href"] for l in item.get("links", []) if l.get("rel") == "self"), None),
        "assets": asset_receipts, "calibration": {k: {"scale": ((assets.get(k) or assets.get(aliases[k])).get("raster:bands") or [{}])[0].get("scale", .0001),
             "offset": ((assets.get(k) or assets.get(aliases[k])).get("raster:bands") or [{}])[0].get("offset", 0)} for k in ("red","green","blue","nir","swir16")},
        "processing": "20 m EPSG:32722 event bounding window + 300 m; Sentinel-2 L2A SCL classes 4/5/6/7 retained; NDVI/NDMI only on clear pixels; B04/B08 bilinear, B11/SCL nearest; COG window reads only",
        "bounds_m": [left,bottom,right,top], "shape": [height,width], "valid_fraction": float(valid.mean()),
        "event_polygon_clear_fraction": float(event_valid.sum()/max(1, inside.sum())),
        "event_polygon_clear_pixels": int(event_valid.sum()),
        "event_polygon_ndvi_median": float(np.nanmedian(ndvi[event_valid])) if event_valid.any() else None,
        "event_polygon_ndmi_median": float(np.nanmedian(ndmi[event_valid])) if (inside & clear & np.isfinite(ndmi)).any() else None,
        "ndvi_median": float(np.nanmedian(ndvi)) if valid.any() else None,
        "ndmi_median": float(np.nanmedian(ndmi)) if np.isfinite(ndmi).any() else None,
        "npz": path.relative_to(ROOT).as_posix(), "sha256": digest(path), "bytes": path.stat().st_size,
        "rgb_preview": png_path.relative_to(ROOT).as_posix(), "rgb_preview_sha256": digest(png_path)}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    receipt, records = bounded_deter()
    # Spaced, 2026-only leads; these are registry records, not a detector accuracy sample.
    preferred = ["deter_amz.31637_curr", "deter_amz.26062_curr", "deter_amz.23558_curr"]
    by_id = {x["id"]: x for x in records}
    selected = [by_id[x] for x in preferred if x in by_id]
    geo = {"type": "FeatureCollection", "name": "INPE DETER Amazon bounded nearby dated alerts",
           "features": [{"type": "Feature", "id": r["id"], "geometry": r["geometry"],
                         "properties": {**r["properties"], "distance_center_m": r["distance_center_m"],
                                        "area_geometry_ha": r["area_geometry_ha"]}} for r in selected]}
    geo_path = OUT / "deter-selected.geojson"
    geo_path.write_text(json.dumps(geo, separators=(",", ":")) + "\n")
    # Individual event-area Sentinel-2 catalogue checks; preserve dated, independent item provenance.
    optical = []
    for event in selected:
        w, s, e, n = event["bbox_wgs84"]
        pad = 0.004
        bbox = [w-pad, s-pad, e+pad, n+pad]
        day = event["properties"]["view_date"]
        start = "2025-01-01T00:00:00Z"
        q = {"collections": ["sentinel-2-l2a"], "bbox": bbox,
             "datetime": f"{start}/2026-11-15T23:59:59Z", "limit": 100}
        record = {"event_id": event["id"], "event_observation_date": day,
                  "query_bbox_wgs84": bbox, "query": q, "status": None, "items": []}
        try:
            resp = requests.post(STAC, json=q, timeout=90); record["http_status"] = resp.status_code
            resp.raise_for_status()
            payload = resp.json()
            items = payload.get("features", [])
            eligible = [i for i in items if i.get("properties", {}).get("datetime", "")[:10] != day]
            eligible.sort(key=lambda i: (i.get("properties", {}).get("eo:cloud_cover", 100), i["properties"]["datetime"]))
            record["catalogue_count"] = len(items)
            record["items"] = [{"id": i["id"], "datetime": i["properties"].get("datetime"),
                "cloud_percent": i["properties"].get("eo:cloud_cover"),
                "item_url": next((l["href"] for l in i.get("links", []) if l.get("rel") == "self"), None),
                "assets": {k: (i.get("assets", {}).get(k) or i.get("assets", {}).get({"red":"B04","green":"B03","blue":"B02","nir":"B08","swir16":"B11","scl":"SCL"}[k]) or {}).get("href") for k in ["red", "green", "blue", "nir", "swir16", "scl"]}}
                for i in eligible[:30]]
            products = []
            for phase in ("before", "after"):
                candidates = [i for i in eligible if (i["properties"]["datetime"][:10] < day if phase == "before" else i["properties"]["datetime"][:10] > day)]
                candidates.sort(key=lambda i: (i["properties"].get("eo:cloud_cover", 100),
                    abs((datetime.fromisoformat(i["properties"]["datetime"].replace("Z", "+00:00")).date() - datetime.fromisoformat(day).date()).days)))
                for candidate in candidates[:3]:
                    try:
                        product = optical_window(candidate, event, phase)
                        if product and product["valid_fraction"] >= .5:
                            products.append(product); break
                    except Exception as exc:
                        record.setdefault("window_failures", []).append({"scene_id": candidate["id"], "phase": phase,
                            "error": f"{type(exc).__name__}: {str(exc)[:300]}"})
            record["products"] = products
            record["status"] = "dated_windows_ready" if len(products) == 2 else "partial_or_no_clear_pair"
        except Exception as exc:
            record["status"] = "catalogue_request_failed"
            record["error"] = f"{type(exc).__name__}: {str(exc)[:400]}"
        optical.append(record)
    report = {
        "schema_version": 1, "study_center": {"lon": CENTER[0], "lat": CENTER[1], "source": "data/amazon.json center"},
        "search_radius_m": RADIUS_M, "source": {"name": "INPE TerraBrasilis / DETER Amazon WFS",
            "service": DETER, "type_name": "deter-amz:deter_amz", "source_receipt": receipt,
            "license": "TerraBrasilis portal: Creative Commons Attribution-ShareAlike 4.0 International (CC BY-SA 4.0); attribute INPE/TerraBrasilis and retain ShareAlike on redistributed adaptations.",
            "documentation": "https://terrabrasilis.dpi.inpe.br/en/layers-via-geoservices/",
            "dates": {"view_date": "satellite image observation date associated with the alert; not exact disturbance onset", "publish_month": "publication month"}},
        "registry_records_in_radius": [{k: x[k] for k in ["id", "properties", "distance_center_m", "area_geometry_ha", "bbox_wgs84"]} for x in records],
        "selected_leads": [{k: x[k] for k in ["id", "properties", "distance_center_m", "area_geometry_ha", "bbox_wgs84"]} for x in selected],
        "selected_geometry": {"path": geo_path.relative_to(ROOT).as_posix(), "sha256": digest(geo_path), "bytes": geo_path.stat().st_size},
        "optical_catalogue_checks": optical,
        "interpretation": {"support": "Official DETER mapped alert polygons provide external registry support for mapped vegetation disturbance at their observation dates; TerraBrasilis describes these data as experimental and subject to change.",
            "not_accuracy": "These polygons are not independent blind validation of DETER, nor proof of exact clearing onset, cause, or complete coverage.",
            "nisar": "Selected polygons are geographically outside the compact sparse/dense prepared NISAR AOI. They are regional leads only; no NISAR/SAR detection or signal is claimed.",
            "optical_status": "Per-event cached paired optical review is reported in targeted_falsification: relative localized decreases are supported for 31637 and 26062, while 23558 is registry-only because nearby rings change similarly. This is not confirmation of complete clearing or onset."}}
    REPORT.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"in_radius": len(records), "selected": [x["id"] for x in selected],
                      "report": str(REPORT.relative_to(ROOT)), "optical": [(x["event_id"], x["status"], len(x["items"])) for x in optical]}, indent=2))


if __name__ == "__main__":
    main()
