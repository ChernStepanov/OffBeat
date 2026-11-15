"""Offline reconcile calibration metadata from already archived original STAC Item bodies."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT_PATH = ROOT / "data/investigation/regional-events.json"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def resolve(item: dict) -> dict:
    props = item.get("properties", {})
    flag = props.get("earthsearch:boa_offset_applied")
    flag_type = type(flag).__name__ if "earthsearch:boa_offset_applied" in props else "missing"
    baseline = props.get("s2:processing_baseline")
    result = {}
    for logical in ("red", "green", "blue", "nir", "swir16"):
        asset = item.get("assets", {}).get(logical, {})
        band = (asset.get("raster:bands") or [{}])[0]
        original_scale = band.get("scale")
        offset_present = "offset" in band
        original_offset = band.get("offset")
        scale = original_scale if original_scale is not None else .0001
        if flag is True:
            offset, branch = 0, "boa_offset_applied_true_effective_offset_zero"
        elif offset_present:
            offset, branch = original_offset, "asset_band_offset"
        elif baseline is not None and float(baseline) >= 4:
            offset, branch = -.1, "processing_baseline_ge_4_inferred_offset"
        else:
            offset, branch = 0, "default_zero_offset"
        result[logical] = {"asset_key": logical, "asset_href": asset.get("href"),
            "original_band_scale": original_scale, "original_band_offset_present": offset_present,
            "original_band_offset": original_offset, "effective_scale": scale,
            "effective_offset": offset, "calibration_branch": branch}
    return {"flag": flag, "flag_type": flag_type, "baseline": baseline, "bands": result}


def main():
    report = json.loads(REPORT_PATH.read_text())
    manifest_path = ROOT / report["raw_provenance_archive"]["manifest_path"]
    manifest = json.loads(manifest_path.read_text())
    for receipt in manifest["stac_unique_items"]:
        if receipt.get("status") != "archived_original_stac_item":
            continue
        payload_path = ROOT / receipt["path"]
        item = json.loads(payload_path.read_text())
        corrected = resolve(item)
        props = receipt["properties"]
        props["earthsearch:boa_offset_applied"] = corrected["flag"]
        props["earthsearch:boa_offset_applied_type"] = corrected["flag_type"]
        props["s2:processing_baseline"] = corrected["baseline"]
        receipt["asset_calibration"] = corrected["bands"]
        receipt["calibration_source_note"] = "Reconciled offline from archived raw STAC Item body (no network request); Earth Search canonical item asset keys red/green/blue/nir/swir16."
    scene_receipts = {r["stac_id"]: r for r in manifest["stac_unique_items"]}
    for use in manifest["scene_uses"]:
        receipt = scene_receipts.get(use["scene_id"], {})
        if receipt.get("status") != "archived_original_stac_item":
            continue
        use["earthsearch_boa_offset_applied"] = receipt["properties"]["earthsearch:boa_offset_applied"]
        use["earthsearch_boa_offset_applied_type"] = receipt["properties"]["earthsearch:boa_offset_applied_type"]
        use["asset_calibration"] = receipt["asset_calibration"]
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    for event in report["optical_catalogue_checks"]:
        for product in event.get("products", []):
            receipt = scene_receipts.get(product["scene_id"])
            if not receipt or receipt.get("status") != "archived_original_stac_item":
                continue
            payload_path = ROOT / receipt["path"]
            item = json.loads(payload_path.read_text())
            resolved = resolve(item)
            product["raw_stac_sha256"] = receipt["sha256"]
            product["raw_stac_path"] = receipt["path"]
            product["raw_stac_asset_calibration"] = resolved["bands"]
            product["raw_stac_properties"] = {**receipt["properties"]}
            old = product.get("calibration", {})
            product["calibration_provenance_comparison"] = {
                band: {"prior_effective_scale": old.get(band, {}).get("scale"),
                       "prior_effective_offset": old.get(band, {}).get("offset"),
                       "verified_effective_scale": vals["effective_scale"],
                       "verified_effective_offset": vals["effective_offset"],
                       "matches_prior": old.get(band, {}).get("scale") == vals["effective_scale"]
                           and old.get(band, {}).get("offset") == vals["effective_offset"]}
                for band, vals in resolved["bands"].items()}
            product["prior_calibration_matches_verified_source"] = all(
                item["matches_prior"] for item in product["calibration_provenance_comparison"].values())
            product["calibration_provenance_status"] = "verified_against_archived_raw_stac_item"
    report["raw_provenance_archive"]["manifest_sha256"] = sha(manifest_path)
    report["raw_provenance_archive"]["calibration_metadata_reconciled_offline"] = True
    REPORT_PATH.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"manifest_sha256": sha(manifest_path), "items": [
        {"id": r["stac_id"], "flag": r["properties"]["earthsearch:boa_offset_applied"],
         "flag_type": r["properties"]["earthsearch:boa_offset_applied_type"],
         "red_band_original_offset": r["asset_calibration"]["red"]["original_band_offset"],
         "red_band_effective_offset": r["asset_calibration"]["red"]["effective_offset"]}
        for r in manifest["stac_unique_items"] if r.get("status") == "archived_original_stac_item"]}, indent=2))


if __name__ == "__main__":
    main()
