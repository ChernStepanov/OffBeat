"""Feasibility and nearest-date match for public Tucurui reservoir records."""
from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timedelta, timezone
from math import asin, cos, radians, sin, sqrt
from pathlib import Path

import numpy as np
import requests

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data/investigation/hydrology-raw"
LDOPE = "https://landweb.modaps.eosdis.nasa.gov"
GREALM = "https://ipad.fas.usda.gov/cropexplorer/global_reservoir/"
NISAR_DATES = ["2026-07-18", "2026-08-11", "2026-08-23", "2026-09-04", "2026-09-16", "2026-09-28"]


def digest(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def get(url, params, filename, source):
    r = requests.get(url, params=params, timeout=60)
    RAW.mkdir(parents=True, exist_ok=True)
    path = RAW / filename
    path.write_bytes(r.content)
    return r, {"source": source, "requested_url": r.url, "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
               "http_status": r.status_code, "content_type": r.headers.get("content-type"),
               "raw_file": str(path.relative_to(ROOT)), "bytes": len(r.content), "sha256": digest(r.content)}


def parse_plot(text):
    lines = {}
    for line in text.splitlines():
        k, sep, v = line.partition(":")
        if sep:
            lines[k.strip()] = v
    dates = lines.get("Plot 1 date", "").split(",")
    raw_values = lines.get("Plot 1 mean", "").split(",")
    if len(dates) != len(raw_values):
        raise ValueError(f"LDOPE plot date/value length mismatch: {len(dates)} vs {len(raw_values)}")
    values = []
    for d, v in zip(dates, raw_values):
        try:
            val = float(v.strip())
            values.append({"date": d.strip(), "value": val if np.isfinite(val) else None})
        except (ValueError, TypeError):
            values.append({"date": d.strip(), "value": None})
    return values, {"response_fields": sorted(lines), "date_count": len(dates),
                    "valid_value_count": sum(v["value"] is not None for v in values),
                    "missing_value_count": sum(v["value"] is None for v in values),
                    "first_date": dates[0] if dates else None, "last_date": dates[-1] if dates else None}


def nearest(values, target, prior_only=False):
    valid = [v for v in values if v["value"] is not None]
    t = date.fromisoformat(target)
    if prior_only:
        valid = [v for v in valid if date.fromisoformat(v["date"]) <= t]
    if not valid:
        return None
    v = min(valid, key=lambda x: abs((date.fromisoformat(x["date"]) - t).days))
    return {"measurement_date": v["date"], "lag_days_measurement_minus_nisar": (date.fromisoformat(v["date"]) - t).days,
            "value": v["value"], "interpolated": False}


def conservative_composite_prior(values, target, duration_days=8):
    """Latest label whose assumed full N-day support ends by the target date.

    This is deliberately conservative under the explicit assumption that the
    label is the first day of an N-day composite. The provider's label meaning
    remains unknown, so this is a rule-based prior candidate, not a timestamp.
    """
    t = date.fromisoformat(target)
    safe = []
    for v in values:
        if v.get("value") is None or not v.get("date"):
            continue
        try:
            label = date.fromisoformat(v["date"])
        except (TypeError, ValueError):
            continue
        if label + timedelta(days=duration_days) <= t:
            safe.append(v)
    if not safe:
        return None
    v = max(safe, key=lambda x: date.fromisoformat(x["date"]))
    label_date = date.fromisoformat(v["date"])
    return {"composite_label": v["date"],
            "label_plus_assumed_duration": (label_date + timedelta(days=duration_days)).isoformat(),
            "lag_days_label_minus_nisar": (label_date - t).days,
            "value": v["value"], "interpolated": False,
            "rule": f"label + {duration_days} days <= NISAR date",
            "assumption": "Label is treated as composite start; label semantics are not confirmed by provider documentation."}


def variable_source_classification(variable):
    if variable == "area":
        return {"classification": "satellite-derived area classification estimate",
                "observable_basis": "NIR surface-reflectance water classification; not a direct gauge/altimetry observation"}
    if variable in ("elevation", "storage"):
        return {"classification": "provider-derived estimate",
                "derivation": "area applied to pre-established reservoir Area-Volume-Elevation curves",
                "independent_observation": False,
                "not_independent_of": "the product's area estimate"}
    return {"classification": "provider estimate; derivation not verified"}


def haversine_km(a, b):
    lat1, lon1 = map(radians, a); lat2, lon2 = map(radians, b)
    h = sin((lat2-lat1)/2)**2 + cos(lat1)*cos(lat2)*sin((lon2-lon1)/2)**2
    return 6371 * 2 * asin(sqrt(h))


def run():
    provenance = []
    try:
        g, gp = get(GREALM, {}, "grealm-landing-response.html", "USDA FAS G-REALM public landing page")
        provenance.append(gp)
        g_status = {"status": "not_available" if g.status_code != 200 else "landing_page_reachable_data_not_yet_verified",
                    "http_status": g.status_code, "url": g.url, "body_preview": g.text[:500] if g.status_code != 200 else None,
                    "note": "No G-REALM data or current Tucurui endpoint inferred from historical MEASURES id 785."}
    except requests.RequestException as exc:
        RAW.mkdir(parents=True, exist_ok=True)
        body = (type(exc).__name__ + ": " + str(exc)).encode()
        path = RAW / "grealm-landing-response.error.txt"
        path.write_bytes(body)
        provenance.append({"source": "USDA FAS G-REALM public landing page", "requested_url": GREALM,
                           "retrieved_at_utc": datetime.now(timezone.utc).isoformat(), "http_status": None,
                           "connection_error": str(exc), "raw_file": str(path.relative_to(ROOT)),
                           "bytes": len(body), "sha256": digest(body)})
        g_status = {"status": "not_available", "http_status": None, "url": GREALM,
                    "connection_error": str(exc),
                    "web_fetch_check": "OpenCode web fetch separately received HTTP 503 for this URL on 2026-11-15",
                    "note": "No G-REALM data or current Tucurui endpoint inferred from historical MEASURES id 785."}

    page, pp = get(LDOPE + "/lake", {}, "ldope-lake-landing.html", "NASA MODIS LDOPE Water Reservoir Time Series page")
    provenance.append(pp)
    # Public menu metadata establishes current selectable sensor/product IDs.
    menus = [
        ("terra-archivesets", {"s": "Lake TS", "type": "archiveset", "sensor": "TerraAqua"}),
        ("viirs-archivesets", {"s": "Lake TS", "type": "archiveset", "sensor": "SNPPJ1"}),
        ("terra-esdt", {"s": "Lake TS", "type": "esdt", "sensor": "TerraAqua", "archiveset": "7"}),
        ("viirs-esdt", {"s": "Lake TS", "type": "esdt", "sensor": "SNPPJ1", "archiveset": "5200"}),
        ("terra-bandlist", {"s": "Lake TS", "type": "bandlist", "esdt": "9205"}),
        ("viirs-bandlist", {"s": "Lake TS", "type": "bandlist", "esdt": "3485"}),
    ]
    menu_results = {}
    for name, params in menus:
        r, p = get(LDOPE + "/get_db_data", params, f"ldope-{name}.txt", "NASA LDOPE public dataset-selection endpoint")
        provenance.append(p)
        menu_results[name] = {"status": r.status_code, "text": r.text}

    products = [
        {"sensor": "Terra/Aqua MODIS", "sensor_id": "TerraAqua", "archive_set": "AS7", "esdt": "MxD28C2", "esdt_menu_id": "9205", "dset_id": "4535", "archive_start": "2000-02-26"},
        {"sensor": "Suomi-NPP VIIRS", "sensor_id": "SNPPJ1", "archive_set": "AS5200", "esdt": "Vxx28C2", "esdt_menu_id": "3485", "dset_id": "2451", "archive_start": "2012-01-25"},
    ]
    series = {}
    metadata = {}
    for product in products:
        for variable, unit in (("area", "km² per LDOPE product"), ("elevation", "m per LDOPE product")):
            dset = product["dset_id"]
            params = {"site": "13", "dset": f"{dset}:{variable}", "type": "LAKE"}
            r, p = get(LDOPE + "/get_sitets_data", params,
                       f"ldope-site13-{product['sensor_id']}-{variable}.txt",
                       "NASA LDOPE get_sitets_data chart response")
            provenance.append(p)
            if r.status_code != 200:
                metadata[f"{product['sensor_id']}_{variable}"] = {"status": "not_available", "http_status": r.status_code}
                continue
            values, info = parse_plot(r.text)
            key = f"{product['sensor_id']}_{variable}"
            series[key] = values
            metadata[key] = {**info, "unit": unit, "endpoint_status": r.status_code,
                             "dataset": product["esdt"], "archive_set": product["archive_set"]}

    # MODIS LDOPE site 13 metadata is embedded in the fetched public page.
    page_text = page.text
    marker = "TucuruiReservoir"
    name_pos = page_text.find(marker)
    site_snippet = page_text[max(0, name_pos - 450):name_pos + 100] if name_pos >= 0 else None
    study = json.loads((ROOT / "data/amazon.json").read_text())
    reservoir_center = [-3.83, -49.65]
    terrain = json.loads((ROOT / "data/terrain/amazon.json").read_text())
    dem_path = ROOT / "data/investigation/layers/amazon-dem-native.npz"
    dem = np.load(dem_path)["elevation_m"]
    ldope_elev_cap_m = 75.4
    geospatial = {"study_center_lat_lon": study["center"], "study_bbox": study["grid"]["bbox"],
                  "ldope_site_id": 13, "ldope_site_name": "TucuruiReservoir", "ldope_site_center_lat_lon": reservoir_center,
                  "study_to_ldope_site_center_km": round(haversine_km(study["center"], reservoir_center), 1),
                  "ldope_page_site_metadata_snippet": site_snippet,
                  "ldope_page_metadata_elevation_capacity_m": ldope_elev_cap_m,
                  "local_dem_source": "AWS Terrain Tiles / Mapzen mixed-source terrain compilation; source documented in docs/investigation-external-maps.md and data/investigation/external-maps.json",
                  "local_dem_sha256": hashlib.sha256(dem_path.read_bytes()).hexdigest(),
                  "local_dem_source_tile_path": "data/investigation/layers/aws-terrain-z12-1487-2102.tif",
                  "local_dem_source_tile_sha256": "671b6b7107e86f7caf570cfec5b62c827004bb005530bc92fca7d0002b050c2e",
                  "local_dem_derived_path": "data/investigation/layers/amazon-dem-native.npz",
                  "local_dem_grid_shape": list(dem.shape), "local_dem_elevation_m_min_median_max": [round(float(np.nanmin(dem)), 2), round(float(np.nanmedian(dem)), 2), round(float(np.nanmax(dem)), 2)],
                  "local_dem_cells_at_or_below_ldope_capacity_elevation": int(np.sum(dem <= ldope_elev_cap_m)),
                  "local_dem_fraction_at_or_below_ldope_capacity_elevation": round(float(np.mean(dem <= ldope_elev_cap_m)), 5),
                  "terrain_bbox": terrain.get("study_bbox"),
                  "vertical_datum_comparability": "Unknown: terrain provider vertical datum and LDOPE product vertical reference have not been confirmed as compatible.",
                  "shoreline_relation": "Not established: LDOPE provides a reservoir reference point and time series, not a reservoir shoreline polygon. The study is about 113 km from that reference point. The terrain grid minimum is only 0.6 m above the LDOPE page's stated capacity elevation; given terrain uncertainty and unknown vertical-datum compatibility, this does NOT rule out flooding or hydrologic connection. Shore adjacency remains unverified."}
    matches = []
    for stamp in NISAR_DATES:
        matches.append({"nisar_date": stamp,
                        "terra_modis_area": nearest(series.get("TerraAqua_area", []), stamp),
                        "terra_modis_elevation": nearest(series.get("TerraAqua_elevation", []), stamp),
                        "viirs_area": nearest(series.get("SNPPJ1_area", []), stamp),
                        "viirs_elevation": nearest(series.get("SNPPJ1_elevation", []), stamp),
                        "viirs_area_nearest_prior_only": nearest(series.get("SNPPJ1_area", []), stamp, prior_only=True),
                        "viirs_elevation_nearest_prior_only": nearest(series.get("SNPPJ1_elevation", []), stamp, prior_only=True),
                        "viirs_area_conservative_prior_8day": conservative_composite_prior(series.get("SNPPJ1_area", []), stamp),
                        "viirs_elevation_conservative_prior_8day": conservative_composite_prior(series.get("SNPPJ1_elevation", []), stamp)})
    result = {"generated_at_utc": datetime.now(timezone.utc).isoformat(),
              "status": {"grealm": g_status,
                         "ldope": "public area and elevation time series retrieved for 2026 from Suomi-NPP VIIRS; Terra/Aqua MODIS series is available but stops in 2025 for this service response",
                         "dahiti": "not queried; user notes Tucurui 1065 requires registration; no authentication or access controls attempted"},
              "geospatial_feasibility": geospatial,
              "product_metadata": {"ldope_app_version_from_page": "0.40", "site_id": 13,
                                   "site_page_reference_capacity_area_km2": 2606, "site_page_reference_storage_km3": 45.5,
                                   "products": products,
                                    "temporal_support": {"product_resolution_days": 8, "composite_label_semantics": "unknown", "conservative_prior_rule": "label + 8 days <= NISAR date", "rule_assumption": "Treat label as composite start and use full 8-day duration; this is a conservative screening convention, not provider-confirmed timestamp semantics."},
                                    "variable_source_classification": {v: variable_source_classification(v) for v in ("area", "elevation", "storage")},
                                    "methodology_sources": ["https://viirsland.gsfc.nasa.gov/Products/NASA/GWR.html", "https://modis-land.gsfc.nasa.gov/modgwr.html"],
                                    "quality_note": "Chart response supplies date, mean, climatology only; no per-observation QA/quality flag or processing collection/version field exposed in these responses. Missing means retained as null; do not equate a returned mean with QA-passed field gauge. Elevation/storage are curve-derived from area, not independent altimetry/gauge observations."},
              "availability": metadata, "nearest_measurements_to_nisar_dates": matches,
              "series": series, "menu_responses": menu_results, "provenance": provenance,
              "limitations": ["Water observations are coarse reservoir-level/area summaries, not measurements at the 20 m study pixels.",
                              "Nearest-date matches are descriptive; no interpolation was done. Signed lag is measurement date minus NISAR date.",
                              "LDOPE chart dates are labels for an 8-day composite, not exact overpass timestamps; provider documentation checked does not confirm whether chart labels denote interval start, center, or end. Treat label semantics as unknown.",
                              "VIIRS series includes dates after some NISAR acquisitions; retain sign of lag and do not interpret future observations as antecedent water level.",
                              "The series is satellite-derived and site-aggregated; no independent in-situ gauge QA is present in response.",
                              "Area is derived from reflectance water classification; elevation and storage are derived from area through pre-established AVE curves. They are not three independent measurements.",
                              "Distance to the LDOPE marker is not distance to nearest shoreline; no shoreline geometry was returned.",
                              "Historical MEASURES id 785 was not used as a 2026 endpoint or as a substitute for current observations."]}
    out = ROOT / "data/investigation/hydrology.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    print(json.dumps({"status": result["status"], "matches": matches, "availability": metadata,
                      "geospatial": {k: geospatial[k] for k in ("study_to_ldope_site_center_km", "local_dem_elevation_m_min_median_max", "local_dem_cells_at_or_below_ldope_capacity_elevation")}}, indent=2))


if __name__ == "__main__":
    run()
