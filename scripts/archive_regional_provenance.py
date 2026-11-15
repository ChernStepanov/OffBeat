"""Archive original bounded WFS and STAC payloads, then verify derived selection provenance."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "data/investigation/regional-events.json"
RAW = ROOT / "data/investigation/regional-raw"


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    report = json.loads(REPORT.read_text())
    receipts = {"retrieval_started_at_utc": now(), "tls_verification": "requests default certificate verification enabled",
                "wfs": None, "stac_unique_items": [], "scene_uses": [], "failures": []}

    wfs_url = report["source"]["source_receipt"]["url"]
    started = now()
    try:
        response = requests.get(wfs_url, timeout=90)  # exact prior URL; certificate verification remains enabled
        response.raise_for_status()
        raw_path = RAW / "wfs-refetched-response.json"
        raw_path.write_bytes(response.content)
        original = response.json()
        receipts["wfs"] = {"method": "GET", "request_url": wfs_url, "request_body": None,
            "retrieval_started_at_utc": started, "retrieval_completed_at_utc": now(),
            "http_status": response.status_code, "content_type": response.headers.get("Content-Type"),
            "path": raw_path.relative_to(ROOT).as_posix(), "sha256": sha(response.content),
            "bytes": len(response.content), "feature_count": len(original.get("features", [])),
            "number_matched": original.get("numberMatched"),
            "source_time_utc": now(),
            "payload_role": "unaltered HTTP response body bytes from this bounded re-fetch; not reconstructed from selected derived features",
            "prior_response_body_available": False,
            "version_drift_from_initial_response": "unverifiable: the initial response body was not cached; current raw selected IDs/properties/geometries are compared to the derived selected GeoJSON"}
        raw_by_id = {f.get("id"): f for f in original.get("features", [])}
        derived_path = ROOT / report["selected_geometry"]["path"]
        derived = {f.get("id"): f for f in json.loads(derived_path.read_text()).get("features", [])}
        checks = []
        for ident, feature in derived.items():
            source = raw_by_id.get(ident)
            if source is None:
                checks.append({"id": ident, "status": "not_found_in_refetched_wfs"})
                continue
            prop_keys = list(source.get("properties", {}).keys())
            same_props = all(source["properties"].get(k) == feature["properties"].get(k) for k in prop_keys)
            same_geometry = source.get("geometry") == feature.get("geometry")
            checks.append({"id": ident, "status": "exact_geometry_and_source_properties_match" if same_props and same_geometry else "mismatch",
                "source_property_keys_compared": prop_keys, "properties_match": same_props,
                "geometry_match": same_geometry})
        receipts["wfs"]["selected_geometry_comparison"] = {
            "derived_geojson_path": report["selected_geometry"]["path"],
            "derived_geojson_sha256": report["selected_geometry"]["sha256"],
            "selected_ids_count": len(derived), "checks": checks,
            "all_selected_features_match": len(checks) == len(derived) and all(c["status"] == "exact_geometry_and_source_properties_match" for c in checks)}
        report["source"]["raw_original_response"] = receipts["wfs"]
    except Exception as exc:
        receipts["failures"].append({"source": "bounded WFS", "request_url": wfs_url,
            "retrieval_started_at_utc": started, "error_type": type(exc).__name__,
            "error": str(exc)[:500], "raw_status": "unverified; no raw response asserted"})
        report["source"]["raw_original_response"] = {"status": "unverified_not_archived",
            "request_url": wfs_url, "retrieval_started_at_utc": started,
            "error_type": type(exc).__name__, "error": str(exc)[:500]}

    uses = []
    for event in report["optical_catalogue_checks"]:
        for product in event.get("products", []):
            uses.append({"event_id": event["event_id"], "phase": product["phase"],
                         "scene_id": product["scene_id"], "item_url": product["item_url"]})
    unique = {}
    for use in uses:
        unique.setdefault(use["scene_id"], use["item_url"])
    scene_receipts = {}
    for scene_id, url in unique.items():
        started = now()
        try:
            response = requests.get(url, timeout=60)  # no auth, no TLS bypass
            response.raise_for_status()
            body = response.content
            raw_item = response.json()
            if raw_item.get("id") != scene_id:
                raise ValueError(f"Item ID mismatch: requested {scene_id}, returned {raw_item.get('id')}")
            path = RAW / f"stac-item-{scene_id}.json"
            path.write_bytes(body)
            props = raw_item.get("properties", {})
            typed_flag = props.get("earthsearch:boa_offset_applied")
            flag_is_bool = type(typed_flag) is bool
            calib = {}
            # Earth Search's item-level STAC assets use canonical names; their hrefs point to B04/B03/etc.
            asset_keys = {"red": "red", "green": "green", "blue": "blue", "nir": "nir", "swir16": "swir16"}
            baseline = props.get("s2:processing_baseline")
            for band, asset_key in asset_keys.items():
                asset = raw_item.get("assets", {}).get(asset_key, {})
                band_info = (asset.get("raster:bands") or [{}])[0]
                source_scale = band_info.get("scale")
                source_offset_present = "offset" in band_info
                source_offset = band_info.get("offset")
                scale = source_scale if source_scale is not None else .0001
                if typed_flag is True:
                    offset, branch = 0, "boa_offset_applied_true_effective_offset_zero"
                elif source_offset_present:
                    offset, branch = source_offset, "asset_band_offset"
                elif baseline is not None and float(baseline) >= 4:
                    offset, branch = -.1, "processing_baseline_ge_4_inferred_offset"
                else:
                    offset, branch = 0, "default_zero_offset"
                calib[band] = {"asset_key": asset_key, "original_band_scale": source_scale,
                    "original_band_offset_present": source_offset_present, "original_band_offset": source_offset,
                    "effective_scale": scale, "effective_offset": offset, "calibration_branch": branch}
            scene_receipts[scene_id] = {"status": "archived_original_stac_item",
                "method": "GET", "request_url": url, "request_body": None,
                "retrieval_started_at_utc": started, "retrieval_completed_at_utc": now(),
                "source_time_utc": now(), "prior_raw_item_available": False,
                "version_drift_from_initial_catalogue_feature": "unverifiable: initial POST search feature body was not cached; raw current GET Item response archived",
                "http_status": response.status_code, "content_type": response.headers.get("Content-Type"),
                "path": path.relative_to(ROOT).as_posix(), "sha256": sha(body), "bytes": len(body),
                "payload_role": "unaltered HTTP STAC Item response body bytes",
                "stac_id": raw_item.get("id"), "properties": {"datetime": props.get("datetime"),
                    "created": props.get("created"), "updated": props.get("updated"),
                    "earthsearch:boa_offset_applied": typed_flag,
                    "earthsearch:boa_offset_applied_type": type(typed_flag).__name__ if "earthsearch:boa_offset_applied" in props else "missing",
                    "s2:processing_baseline": baseline},
                "asset_calibration": calib}
        except Exception as exc:
            scene_receipts[scene_id] = {"status": "unverified_not_archived", "method": "GET",
                "request_url": url, "request_body": None, "retrieval_started_at_utc": started,
                "error_type": type(exc).__name__, "error": str(exc)[:500],
                "raw_status": "unverified; no raw payload fabricated"}
            receipts["failures"].append({"source": "STAC item", "scene_id": scene_id,
                "request_url": url, "retrieval_started_at_utc": started,
                "error_type": type(exc).__name__, "error": str(exc)[:500]})

    for use in uses:
        use_receipt = scene_receipts[use["scene_id"]]
        use["raw_stac_status"] = use_receipt["status"]
        if use_receipt["status"] == "archived_original_stac_item":
            use["raw_stac_path"] = use_receipt["path"]
            use["raw_stac_sha256"] = use_receipt["sha256"]
            use["earthsearch_boa_offset_applied"] = use_receipt["properties"]["earthsearch:boa_offset_applied"]
            use["earthsearch_boa_offset_applied_type"] = use_receipt["properties"]["earthsearch:boa_offset_applied_type"]
            use["asset_calibration"] = use_receipt["asset_calibration"]
            product = next(p for e in report["optical_catalogue_checks"] if e["event_id"] == use["event_id"]
                           for p in e["products"] if p["phase"] == use["phase"] and p["scene_id"] == use["scene_id"])
            product["raw_stac_path"] = use_receipt["path"]
            product["raw_stac_sha256"] = use_receipt["sha256"]
            product["raw_stac_properties"] = use_receipt["properties"]
            product["raw_stac_asset_calibration"] = use_receipt["asset_calibration"]
            product["calibration_provenance_status"] = "verified_against_archived_raw_stac_item"
            # Compare new typed source behavior with already-recorded effective calibration; never silently alter indices.
            old = product.get("calibration", {})
            band_checks = {}
            for band, new in use_receipt["asset_calibration"].items():
                prior = old.get(band, {})
                band_checks[band] = {"prior_effective_scale": prior.get("scale"),
                    "prior_effective_offset": prior.get("offset"),
                    "verified_effective_scale": new["effective_scale"],
                    "verified_effective_offset": new["effective_offset"],
                    "matches_prior": prior.get("scale") == new["effective_scale"] and prior.get("offset") == new["effective_offset"]}
            product["calibration_provenance_comparison"] = band_checks
            product["prior_calibration_matches_verified_source"] = all(x["matches_prior"] for x in band_checks.values())
    receipts["stac_unique_items"] = list(scene_receipts.values())
    receipts["scene_uses"] = uses
    receipts["retrieval_completed_at_utc"] = now()
    manifest_path = RAW / "manifest.json"
    manifest_path.write_text(json.dumps(receipts, indent=2) + "\n")
    report["raw_provenance_archive"] = {"manifest_path": manifest_path.relative_to(ROOT).as_posix(),
        "manifest_sha256": sha(manifest_path.read_bytes()), "status": "complete" if not receipts["failures"] else "partial_or_unverified",
        "wfs_raw_archived": receipts["wfs"] is not None,
        "stac_scene_uses": len(uses), "stac_unique_items_archived": sum(x.get("status") == "archived_original_stac_item" for x in scene_receipts.values()),
        "failures": receipts["failures"]}
    REPORT.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report["raw_provenance_archive"], indent=2))


if __name__ == "__main__":
    main()
