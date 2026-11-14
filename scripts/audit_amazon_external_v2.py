"""Fetch dated Sentinel-2 SCL pixels and independent INPE DETER/local alert context.

Network-dependent; deterministic windows and selection rule. Requires rasterio and
shapely in addition to numpy. Run from repository root and save JSON stdout.
"""
from __future__ import annotations

import json
import hashlib
import math
import re
import urllib.parse
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
import rasterio
from rasterio.warp import transform
from shapely.geometry import Point, shape
from shapely import make_valid, transform as shapely_transform

ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "data/amazon-spatial-sar-eda-v2.json"
STAC = "https://earth-search.aws.element84.com/v1/search"
DETER = "https://terrabrasilis.dpi.inpe.br/geoserver/ows"
PRE_START, PRE_END = "2026-07-24T09:04:09Z", "2026-08-23T09:04:09Z"
POST_START, POST_END = "2026-09-04T09:04:43Z", "2026-10-04T09:04:43Z"
MAX_DISTANCE_M = 2000
RAW_DIR = ROOT / "data/amazon-external-audit-v3-raw"
SCL_LABELS = {0: "no_data", 1: "saturated_or_defective", 2: "dark_area_pixels",
              3: "cloud_shadow", 4: "vegetation", 5: "not_vegetated",
              6: "water", 7: "unclassified", 8: "cloud_medium_probability",
              9: "cloud_high_probability", 10: "thin_cirrus", 11: "snow_or_ice"}


def get_json(url, body=None, raw_name=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=90) as response:
        raw = response.read()
        parsed = json.loads(raw)
        metadata = {"requested_url": url, "method": "POST" if data else "GET",
                    "fetched_at_utc": datetime.now(timezone.utc).isoformat(),
                    "http_status": response.status,
                    "headers": {k: response.headers.get(k) for k in ("Date", "ETag", "Last-Modified", "Content-Length")},
                    "sha256": hashlib.sha256(raw).hexdigest()}
    if raw_name:
        RAW_DIR.mkdir(parents=True, exist_ok=True)
        p = RAW_DIR / raw_name
        p.write_bytes(raw)
        metadata["raw_response_path"] = str(p.relative_to(ROOT))
    return parsed, metadata


def scenes_for(point, start, end, key, side):
    body = {"collections": ["sentinel-2-c1-l2a", "sentinel-2-pre-c1-l2a"],
            "intersects": {"type": "Point", "coordinates": [point["lon"], point["lat"]]},
            "datetime": f"{start}/{end}", "limit": 100}
    url, method_body = STAC, body
    items, pages, page_no = [], [], 0
    while url:
        page_no += 1
        result, page_meta = get_json(url, method_body, f"stac_{key}_{side}_{page_no}.json")
        items.extend(result.get("features", []))
        pages.append(page_meta)
        nxt = next((x for x in result.get("links", []) if x.get("rel") == "next"), None)
        if nxt:
            url = nxt["href"]
            method_body = nxt.get("body") if nxt.get("method", "GET").upper() == "POST" else None
        else:
            url, method_body = None, None
    dedup = {x["id"]: x for x in items}
    return sorted(dedup.values(), key=lambda x: (x["properties"]["datetime"], x["id"])), pages


def sample_scl(item, point):
    if not item or "scl" not in item.get("assets", {}):
        return None
    href = item["assets"]["scl"]["href"]
    with rasterio.open(href) as ds:
        x, y = transform("EPSG:4326", ds.crs, [point["lon"]], [point["lat"]])
        value = int(next(ds.sample([(x[0], y[0])], indexes=1))[0])
        return {"item_id": item["id"], "collection": item["collection"],
                "datetime": item["properties"]["datetime"],
                "scene_cloud_cover_percent": item["properties"].get("eo:cloud_cover"),
                "asset": href, "asset_crs": str(ds.crs), "asset_resolution_m": list(ds.res),
                "pixel_value": value, "class": SCL_LABELS.get(value, "unknown"),
                "coordinate_transform": "candidate EPSG:4326 lon/lat transformed to asset CRS; nearest containing raster pixel"}


def local_alert_audit(points):
    data = json.loads((ROOT / "data/amazon/alerts.geojson").read_text())
    rows, invalid = [], []
    raw = (ROOT / "data/amazon/alerts.geojson").read_bytes()
    prepared = []
    for index, f in enumerate(data.get("features", [])):
        original = shape(f["geometry"])
        was_valid = original.is_valid
        fixed = original if was_valid else make_valid(original)
        prepared.append((f, original, fixed))
        if not was_valid:
            invalid.append({"feature_index": index, "reason": original.is_valid and None or __import__("shapely").is_valid_reason(original),
                            "repaired_type": fixed.geom_type, "repair_valid": fixed.is_valid})
    for c in points:
        p = Point(c["lon"], c["lat"])
        px, py = transform("EPSG:4326", "EPSG:32722", [c["lon"]], [c["lat"]])
        pm = Point(px[0], py[0])
        for f, original, geom in prepared:
            d = date.fromisoformat(str(f.get("properties", {}).get("date", ""))[:10])
            projected = project_to_utm22(geom)
            distance = projected.distance(pm)
            if distance <= MAX_DISTANCE_M:
                prop = f.get("properties", {})
                rows.append({"candidate": [c["row"], c["col"]], "source": prop.get("source"),
                             "class": prop.get("class"), "record_date": str(prop.get("date"))[:10],
                             "relation": relation(d), "distance_m": round(distance, 1),
                             "record_date_precision": "date-only; time/timezone unavailable",
                             "area_ha": prop.get("area_ha"), "original_geometry_valid": original.is_valid,
                             "make_valid_applied": not original.is_valid,
                             "feature_geometry_covers_point_including_boundary": bool(geom.covers(p))})
    return {"file": "data/amazon/alerts.geojson", "sha256": hashlib.sha256(raw).hexdigest(),
            "feature_count": len(prepared), "invalid_geometry_count": len(invalid),
            "invalid_geometry_repairs": invalid,
            "geometry_semantics": "Shapely make_valid for invalid inputs; covers includes boundary points; distance measured after EPSG:4326 to UTM 22S projection",
            "records_within_2km": rows,
            "source_limit": "checked-in local collection; not queried as a complete real-time GLAD archive"}


def relation(d):
    if d in (date(2026, 7, 24), date(2026, 8, 23), date(2026, 9, 4), date(2026, 10, 4)):
        return "window_or_sar_boundary_calendar_day_time_ambiguous"
    if d < date(2026, 7, 24):
        return "before_fixed_window"
    if d < date(2026, 8, 23):
        return "pre_pair_window"
    if d < date(2026, 9, 4):
        return "between_sar_dates"
    if d <= date(2026, 10, 4):
        return "post_pair_window"
    return "after_fixed_window"


def haversine_m(lon1, lat1, lon2, lat2):
    import math
    r = 6371008.8
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def project_to_utm22(geometry):
    """Project a Shapely geometry from WGS84 to the local metric CRS."""
    def coordinates_to_utm(coords):
        xx, yy = transform("EPSG:4326", "EPSG:32722", coords[:, 0].tolist(), coords[:, 1].tolist())
        return np.column_stack((xx, yy))
    return shapely_transform(geometry, coordinates_to_utm)


def nearest_clear_scl_4_or_5(inventory):
    """Choose clear land-class SCL 4/5 equally; only time and deterministic ties rank them."""
    clear = [x for x in inventory if x.get("pixel_value") in (4, 5)]
    clear.sort(key=lambda x: (abs(x["seconds_from_sar_reference"]),
                              x["datetime"], x["item_id"]))
    return clear[0] if clear else None


def query_deter(points):
    lons, lats = [p["lon"] for p in points], [p["lat"] for p in points]
    params = {"service": "WFS", "version": "2.0.0", "request": "GetFeature",
              "typeNames": "deter-amz:deter_amz", "outputFormat": "application/json",
              "srsName": "EPSG:4326", "bbox": f"{min(lons)-.03},{min(lats)-.03},{max(lons)+.03},{max(lats)+.03},EPSG:4326",
              "count": "1000", "startIndex": "0"}
    base_url = DETER + "?" + urllib.parse.urlencode(params)
    features, pages, offset = [], [], 0
    matched = None
    while True:
        params["startIndex"] = str(offset)
        url = DETER + "?" + urllib.parse.urlencode(params)
        fc, page_meta = get_json(url, raw_name=f"deter_page_{len(pages)+1}.json")
        page_features = fc.get("features", [])
        features.extend(page_features)
        pages.append(page_meta)
        try:
            matched = int(fc.get("numberMatched"))
        except (TypeError, ValueError):
            matched = None
        returned = len(page_features)
        offset += returned
        if returned == 0 or (matched is not None and offset >= matched) or returned < int(params["count"]):
            break
    unique_features = {f.get("id", json.dumps(f, sort_keys=True)): f for f in features}
    features = list(unique_features.values())
    # Project geometries and candidate points to UTM 22S before metric distance.
    output, date_window, invalid_geom = [], [], []
    for f in features:
        props = f.get("properties", {})
        observed = str(props.get("view_date", ""))[:10]
        if not (PRE_START[:10] <= observed <= POST_END[:10]):
            continue
        original = shape(f["geometry"])
        g = original if original.is_valid else make_valid(original)
        if not original.is_valid:
            invalid_geom.append({"feature_id": f.get("id"), "reason": __import__("shapely").is_valid_reason(original),
                                 "repaired_type": g.geom_type, "repair_valid": g.is_valid})
        gp = project_to_utm22(g)
        distances = []
        for c in points:
            geographic_point = Point(c["lon"], c["lat"])
            px, py = transform("EPSG:4326", "EPSG:32722", [c["lon"]], [c["lat"]])
            metric_point = Point(px[0], py[0])
            dist = gp.distance(metric_point)
            distances.append((dist, c))
            if dist <= MAX_DISTANCE_M:
                output.append({"candidate": [c["row"], c["col"]], "feature_id": f.get("id"),
                               "classname": props.get("classname"), "view_date": observed,
                               "date_precision": "date-only; view time unavailable",
                               "publish_month": props.get("publish_month"),
                               "relation": relation(date.fromisoformat(observed)),
                               "distance_m": round(dist, 1),
                               "repaired_geometry_covers_point_including_boundary": bool(g.covers(geographic_point)),
                               "original_geometry_valid": original.is_valid,
                               "area_km2": props.get("areamunkm"), "sensor": props.get("sensor"),
                               "satellite": props.get("satellite")})
        if PRE_START[:10] <= observed <= POST_END[:10]:
            dist, nearest = min(distances, key=lambda item: item[0])
            date_window.append({"feature_id": f.get("id"), "classname": props.get("classname"),
                                "view_date": observed, "publish_month": props.get("publish_month"),
                                "nearest_candidate": [nearest["row"], nearest["col"]],
                                "date_precision": "date-only; view time unavailable",
                                "nearest_distance_m": round(dist, 1),
                                "sensor": props.get("sensor"), "satellite": props.get("satellite")})
    return {"endpoint": DETER, "type_name": "deter-amz:deter_amz", "bbox": params["bbox"],
            "bbox_feature_count_returned": len(features), "number_matched_reported": matched,
            "pagination_pages": pages, "pagination_complete_by_number_matched": matched is not None and matched <= len(features),
            "invalid_date_window_geometry_repairs": invalid_geom,
            "geometry_semantics": "make_valid applied to invalid feature geometries; covers includes boundary; metric distance after projection to EPSG:32722",
            "features_in_fixed_date_window_in_query_bbox": date_window,
            "features_in_fixed_date_window_within_2km": output,
            "date_semantics": "view_date is date-only observation; same-calendar-day ordering is ambiguous; publish_month is month-only publication metadata, not exact release timestamp",
            "query_url_first_page": base_url}


def audit():
    local = json.loads(INPUT.read_text())
    points = local["candidate_results"]
    acqs = local["sar_acquisitions"]
    sar_pre = datetime.fromisoformat(acqs[0]["start_utc"].replace("Z", "+00:00"))
    sar_post = datetime.fromisoformat(acqs[1]["end_utc"].replace("Z", "+00:00"))
    point_items, catalog_pages, query_audit = {}, [], []
    for c in points:
        key = f"{c['row']},{c['col']}"
        pre_items, pre_pages = scenes_for(c, PRE_START, PRE_END, key.replace(',', '_'), "pre")
        post_items, post_pages = scenes_for(c, POST_START, POST_END, key.replace(',', '_'), "post")
        point_items[key] = {"pre": pre_items, "post": post_items}
        catalog_pages.extend(pre_pages + post_pages)
        query_audit.extend([{"point": key, "window": "pre", "scene_count": len(pre_items), "pages": pre_pages},
                            {"point": key, "window": "post", "scene_count": len(post_items), "pages": post_pages}])
    union = {}
    for by_side in point_items.values():
        for side, items in by_side.items():
            for item in items:
                union[item["id"]] = (side, item)
    # Read each unique SCL COG once and sample every selected location.
    pixels_by_scene = {}
    for item_id, (side, item) in union.items():
        href = item.get("assets", {}).get("scl", {}).get("href")
        if not href:
            continue
        samples = {}
        with rasterio.open(href) as ds:
            xs, ys = transform("EPSG:4326", ds.crs, [c["lon"] for c in points], [c["lat"] for c in points])
            vals = list(ds.sample(list(zip(xs, ys)), indexes=1))
            for c, val in zip(points, vals):
                samples[f"{c['row']},{c['col']}"] = int(val[0])
            pixels_by_scene[item_id] = {"samples": samples, "crs": str(ds.crs), "resolution_m": list(ds.res),
                                        "href": href}
    old = json.loads((ROOT / "data/amazon-spatial-sar-eda-v2-original-selection.json").read_text())
    old_points = old["candidates"]
    broad_ids = {}
    broad_dates = (("2026-08-02", "pre"), ("2026-08-04", "pre"),
                   ("2026-08-14", "pre"), ("2026-09-21", "post"))
    for day, side in broad_dates:
        found = [item for _, item in union.values() if item["properties"]["datetime"].startswith(day)]
        if not found:
            raise RuntimeError(f"Expected broad-window Sentinel item missing: {day}")
        broad_ids[day] = sorted(found, key=lambda x: (x["properties"]["datetime"], x["id"]))[0]
    old_broad = {}
    for day, side in broad_dates:
        item = broad_ids[day]
        href = item["assets"]["scl"]["href"]
        with rasterio.open(href) as ds:
            xs, ys = transform("EPSG:4326", ds.crs, [c["lon"] for c in old_points], [c["lat"] for c in old_points])
            vals = list(ds.sample(list(zip(xs, ys)), indexes=1))
            for c, val in zip(old_points, vals):
                key = f"{c['row']},{c['col']}"
                old_broad.setdefault(key, {"role": c["role"], "coordinate_lon_lat": [c["lon"], c["lat"]],
                                           "scl_by_scene_date": {}})
                v = int(val[0])
                record = {"item_id": item["id"], "datetime": item["properties"]["datetime"],
                          "pixel_value": v, "class": SCL_LABELS.get(v, "unknown"), "asset": href}
                old_broad[key]["scl_by_scene_date"][day] = record
                if day in ("2026-08-14", "2026-09-21"):
                    old_broad[key]["pre" if day == "2026-08-14" else "post"] = record
    ss = {}
    for c in points:
        key = f"{c['row']},{c['col']}"
        ss[key] = {"role": c["role"], "coordinate_lon_lat": [c["lon"], c["lat"]], "inventory": {}}
        for side in ("pre", "post"):
            target = sar_pre if side == "pre" else sar_post
            inv = []
            for item in point_items[key][side]:
                pix = pixels_by_scene.get(item["id"])
                if not pix:
                    inv.append({"item_id": item["id"], "datetime": item["properties"]["datetime"],
                                "scl_asset_available": False})
                    continue
                value = pix["samples"][key]
                dt = datetime.fromisoformat(item["properties"]["datetime"].replace("Z", "+00:00"))
                inv.append({"item_id": item["id"], "collection": item["collection"],
                            "datetime": item["properties"]["datetime"],
                            "scene_cloud_cover_percent": item["properties"].get("eo:cloud_cover"),
                            "scl_asset": pix["href"], "asset_crs": pix["crs"],
                            "asset_resolution_m": pix["resolution_m"], "pixel_value": value,
                            "class": SCL_LABELS.get(value, "unknown"),
                            "seconds_from_sar_reference": int((dt-target).total_seconds())})
            inv.sort(key=lambda x: (x.get("datetime", ""), x.get("item_id", "")))
            ss[key]["inventory"][side] = inv
            ss[key].setdefault("posthoc_nearest_clear_scl_4_or_5", {})[side] = nearest_clear_scl_4_or_5(inv)
    fires = json.loads((ROOT / "data/amazon/fires.json").read_text())
    # Report point detections within 2 km and fixed windows; do not call detections independent fires.
    frows = []
    for c in points:
        for f in fires:
            d = date.fromisoformat(str(f["date"])[:10])
            if not (date(2026, 7, 24) <= d <= date(2026, 10, 4)):
                continue
            dist = haversine_m(c["lon"], c["lat"], float(f["lon"]), float(f["lat"]))
            if dist <= MAX_DISTANCE_M:
                frows.append({"candidate": [c["row"], c["col"]], "date": str(f["date"]),
                              "time_raw": f.get("time"), "time_timezone_semantics": "timezone not declared in local JSON; do not infer exact ordering from date-only field",
                              "relation": relation(d), "distance_m": round(dist, 1),
                              "provider": f.get("provider"), "source": f.get("source"),
                              "confidence": f.get("confidence"), "frp": f.get("frp")})
    # Exact broad-window comparison requested in review (not a cause/date estimate).
    broad = {"pre_scene_date": "2026-08-14", "post_scene_date": "2026-09-21", "points": {}}
    for key, row in ss.items():
        def on_date(side, day):
            return [x for x in row["inventory"][side] if x.get("datetime", "").startswith(day)]
        broad["points"][key] = {"role": row["role"],
                                "pre": on_date("pre", broad["pre_scene_date"]),
                                "post": on_date("post", broad["post_scene_date"])}
    return {"retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
            "scope": "selected Amazon candidates and controls; retrospective quality-aware analysis, not preregistered",
            "windows": {"pre": [PRE_START, PRE_END], "post": [POST_START, POST_END],
                        "alert_observation_date_filter": ["2026-07-24", "2026-10-04"],
                        "point_distance_screen_m": MAX_DISTANCE_M,
                         "date_only_sources": "inclusive calendar-date filtering; exact within-day ordering is ambiguous on all timed window bounds (2026-07-24, 2026-08-23, 2026-09-04, 2026-10-04) and SAR dates unless source provides a timestamp",
                        "not_preregistered": True},
            "sentinel2": {"api": STAC, "collection_ids": ["sentinel-2-c1-l2a", "sentinel-2-pre-c1-l2a"],
                           "catalog_search": {"pagination_followed": True, "point_queries": len(points)*2,
                                             "unique_scene_items": len(union), "pages": catalog_pages,
                                             "queries": query_audit,
                                             "raw_responses_saved": True,
                                             "inventory_completeness": "all advertised STAC next links followed for each point/window query until no next link; no total matched count supplied/verified; not a claim of complete Sentinel archive"},
                          "scene_inventory_rule": "all returned scenes in exact SAR-time-anchored 30-day windows; no item filtered by scene cloud metadata",
                          "pixel_method": "read every unique SCL COG via Rasterio; transform each candidate lon/lat to asset CRS (recorded per scene), sample containing pixel",
                          "quality_aware_posthoc_rule": "report full pixel inventory; exclude nodata, defective, cloud, shadow and unclassified categories; SCL 4 and 5 are equally eligible clear land classes, with no class preference; choose nearest in absolute time to exact SAR boundary, tie-break earlier UTC then item ID. This is retrospective, not preregistered.",
                          "results_by_row_col": ss,
                          "broad_2026-08-14_to_2026-09-21_comparison": {"interpretation": "explicitly wider, post-hoc optical bracket; cannot date disturbance or prove clearing", **broad},
                          "previous_selection_broad_pair_crosscheck": {"scene_rule": "sample the same S2 2026-08-02, 2026-08-04, 2026-08-14 and 2026-09-21 SCL assets at all archived prior-selected coordinates; this is a retrospective comparison, not independent ground truth",
                                                                         "results_by_row_col": old_broad},
                          "interpretation": "SCL classes 8/9 cloud probability and 3 shadow invalidate vegetation interpretation; class 5 means not-vegetated classification only, not proof of forest loss/clearing; class 4 vegetation is not proof of stable forest"},
            "inpe_deter": query_deter(points), "local_glad_deter_alerts": local_alert_audit(points),
            "local_firms_screen": {"file": "data/amazon/fires.json", "records_within_2km_in_fixed_windows": frows,
                                   "limitation": "FIRMS/INPE active-fire points, not burn polygons; repeat detections may be one fire"},
             "other_source_access": {"GLAD_live": "No unauthenticated query/download endpoint established in this run; GFW Data API access is documented as authentication-required. Checked-in GeoJSON only was inspected.",
                                     "independent_amazon_event": "No independently confirmed event linked to the revised Amazon SAR candidates/controls was verified in the sources checked; this is insufficient evidence, not evidence of no event.",
                                     "NISAR_outside_Amazon": "No independently published matching event identified in accessible checked-in/public sources during this audit."},
             "local_input_sha256": {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                                    for p in [INPUT, ROOT / "data/amazon/alerts.geojson", ROOT / "data/amazon/fires.json",
                                              *sorted((ROOT / "data/subsets/amazon-series").glob("*.json")),
                                              *sorted((ROOT / "data/subsets/amazon-series").glob("*.npz"))]},
             "remote_asset_hash_policy": "STAC/WFS JSON response bodies are saved and SHA-256 recorded; full SCL COG bytes/range responses are not archived or content-hashed, only item IDs, asset URLs and sampled values are preserved",
             "limitations": ["SCL is a categorical cloud/land-cover classifier, not a deforestation label or independent confirmation.",
                            "Scene cloud-cover percentage is scene-wide metadata, not pixel-level cloudiness; pixel SCL is reported separately.",
                             "DETER view date and publish month do not establish exact public availability on any given day; date-only records on SAR dates have ambiguous ordering.",
                            "The fixed +/-30-day windows are descriptive and do not prove event absence outside them; broad SCL brackets are post-hoc and cannot date a change.",
                            "Candidate/control cells may share a spatially correlated disturbance; no independent event counting."]}


if __name__ == "__main__":
    print(json.dumps(audit(), indent=2, allow_nan=False))
