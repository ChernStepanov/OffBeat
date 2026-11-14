#!/usr/bin/env python3
"""Access-only CMR and granule-header audit for Amazon IMERG.

This script does not authenticate, download/extract precipitation, or infer
rainfall. It checks catalogue entries, anonymous GET status, and HDF5 signature.
Only full 30-minute bins contained in [SAR start - N days, SAR start) count.
"""
from __future__ import annotations

import datetime as dt
import json
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CMR = "https://cmr.earthdata.nasa.gov/search"
POINT = (-49.275390625, -4.766796875)  # longitude, latitude
STREAMS = {
    "early": "GPM_3IMERGHHE",
    "late": "GPM_3IMERGHHL",
    "final": "GPM_3IMERGHH",
}
UTC = dt.timezone.utc
BIN = dt.timedelta(minutes=30)
PROBE_DATE = "2026-09-04"  # representative real granules from both NRT streams


def read_acquisitions():
    paths = sorted((ROOT / "data/subsets/amazon-series").glob("*.json"))
    paths += [ROOT / "data/subsets/amazon/nisar-0.json", ROOT / "data/subsets/amazon/nisar-1.json"]
    # Additional July/August pair is audited separately as supplementary data.
    supplement = ROOT / "data/subsets/amazon/2026-07-18_2026-08-11"
    paths += [supplement / "nisar-0.json", supplement / "nisar-1.json"]
    acquisitions = []
    for path in paths:
        meta = json.loads(path.read_text())
        source = meta["source"]
        start = dt.datetime.fromisoformat(source["start"].replace("Z", "+00:00"))
        acquisitions.append({
            "date": meta.get("date", meta.get("grid", {}).get("date", start.date().isoformat())),
            "time": start.astimezone(UTC), "source_id": source["id"],
            "sidecar": str(path.relative_to(ROOT)), "source_url": source.get("url"),
            "identification": meta.get("identification"),
            "identification_provenance": ("sidecar.identification" if "identification" in meta
                                           else "absent_from_sidecar; not inferred"),
            "track": meta.get("identification", {}).get("trackNumber"),
            "frame": meta.get("identification", {}).get("frameNumber"),
            "pass": meta.get("identification", {}).get("orbitPassDirection"),
            "grid": meta.get("grid", {}),
            "supplemental": "2026-07-18_2026-08-11" in str(path),
        })
    return sorted(acquisitions, key=lambda row: row["time"])


def request_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "amazon-imerg-repro/1.0"})
    with urllib.request.urlopen(req, timeout=60) as response:
        return json.load(response)


def utc_parse(value):
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def collection_metadata():
    result = {}
    for stream, short_name in STREAMS.items():
        url = f"{CMR}/collections.json?" + urllib.parse.urlencode({"short_name": short_name, "page_size": 100})
        feed = request_json(url).get("feed", {}).get("entry", [])
        result[stream] = [{"entry_id": c.get("entry_id"), "version": c.get("version_id"),
                           "title": c.get("dataset_id"), "start": c.get("time_start"),
                           "end": c.get("time_end")} for c in feed]
    return result


def granule_search(short_name, start, end):
    bbox = f"{POINT[0]-0.0001},{POINT[1]-0.0001},{POINT[0]+0.0001},{POINT[1]+0.0001}"
    params = {"short_name": short_name, "version": "07",
              "temporal": f"{start.isoformat().replace('+00:00','Z')},{end.isoformat().replace('+00:00','Z')}",
              "bounding_box": bbox, "page_size": 2000, "sort_key": "start_date"}
    url = f"{CMR}/granules.json?" + urllib.parse.urlencode(params)
    data = request_json(url)
    output = []
    for entry in data.get("feed", {}).get("entry", []):
        links = entry.get("links", [])
        data_url = next((x.get("href") for x in links if x.get("href", "").endswith(".HDF5")), None)
        output.append({"granule_id": entry.get("id"), "start": entry.get("time_start"),
                       "end": entry.get("time_end"), "url": data_url})
    return output, url


def assess_window(granules, start, sar_start):
    # Treat every source bin as [granule start, start + 30 min). Do not count
    # overlapping bins at either boundary, even if most of the bin is inside.
    by_start = {}
    overlapping = []
    for g in granules:
        if not g.get("start"):
            continue
        bin_start = utc_parse(g["start"])
        bin_end = bin_start + BIN
        if bin_start < sar_start and bin_end > start:
            overlapping.append(g)
        if bin_start >= start and bin_end <= sar_start:
            by_start.setdefault(bin_start, {**g, "bin_start": bin_start.isoformat(),
                                             "bin_end_exclusive": bin_end.isoformat()})
    expected_starts = []
    step = int(BIN.total_seconds())
    quotient, remainder = divmod(int(start.timestamp()), step)
    cursor = (quotient + (1 if remainder else 0)) * step
    while dt.datetime.fromtimestamp(cursor, UTC) + BIN <= sar_start:
        expected_starts.append(dt.datetime.fromtimestamp(cursor, UTC))
        cursor += int(BIN.total_seconds())
    full = [by_start[t] for t in expected_starts if t in by_start]
    missing = [t.isoformat() for t in expected_starts if t not in by_start]
    covered_seconds = len(full) * BIN.total_seconds()
    requested_seconds = (sar_start - start).total_seconds()
    return {"expected_duration_seconds": requested_seconds,
            "intersecting_granule_count_including_partial_edges": len(overlapping),
            "full_bin_count": len(full), "covered_full_bin_seconds": covered_seconds,
            "possible_full_bin_count": len(expected_starts), "missing_full_bin_count": len(missing),
            "excluded_partial_edge_granule_count": len(overlapping) - len(full),
            "missing_full_bin_starts": missing,
            "coverage_fraction": covered_seconds / requested_seconds,
            "coverage_percent": round(100 * covered_seconds / requested_seconds, 4),
            "coverage_policy": "conservative: only complete 30-minute bins wholly inside the half-open SAR window",
            "partial_edge_bins_excluded": True, "precipitation_mm": None,
            "precipitation_status": "not_extracted",
            "granules": full}


def hdf5_signature_offset(sample):
    signature = b"\x89HDF\r\n\x1a\n"
    offsets = [0]
    offset = 512
    while offset + len(signature) <= len(sample):
        offsets.append(offset)
        offset *= 2
    return next((offset for offset in offsets if sample[offset:offset + len(signature)] == signature), None)


def classify_hdf5_response(http_status, content_type, sample):
    if http_status not in (200, 206):
        return "http_error", None
    offset = hdf5_signature_offset(sample)
    if offset is not None:
        return "hdf5_signature_verified_access_only", offset
    return "http_success_non_hdf5", None


def probe_real_granule(url):
    if not url:
        return {"url": None, "status": "no_data_link"}
    # Anonymous GET to the actual HDF5 URL, not a directory. This is strictly
    # an access/header audit; even a valid signature does not extract rainfall.
    req = urllib.request.Request(url, headers={"User-Agent": "amazon-imerg-repro/1.0",
                                               "Range": "bytes=0-4095"})
    try:
        with urllib.request.urlopen(req, timeout=45) as response:
            sample = response.read(4096)
            status, signature_offset = classify_hdf5_response(
                response.status, response.headers.get("Content-Type"), sample)
            return {"url": url, "effective_url": response.geturl(), "http_status": response.status,
                    "content_type": response.headers.get("Content-Type"),
                    "bytes_read": len(sample), "hdf5_signature_offset": signature_offset,
                    "hdf5_signature_verified": signature_offset is not None, "status": status,
                    "precipitation_extracted": False}
    except urllib.error.HTTPError as exc:
        return {"url": url, "effective_url": exc.geturl(), "http_status": exc.code,
                "status": "authentication_required" if exc.code == 401 else "http_error",
                "hdf5_signature_offset": None, "hdf5_signature_verified": False,
                "precipitation_extracted": False,
                "reason": str(exc.reason)}
    except Exception as exc:
        return {"url": url, "status": "request_error", "error": f"{type(exc).__name__}: {exc}"}


def build_report(now=None):
    now = now or dt.datetime.now(UTC)
    acquisitions = read_acquisitions()
    collections = collection_metadata()
    windows = []
    searches = []
    probes = []
    for acq in acquisitions:
        t = acq["time"]
        query_start = t - dt.timedelta(days=7)
        for stream, short_name in STREAMS.items():
            requested_at = dt.datetime.now(UTC).isoformat()
            granules, query_url = granule_search(short_name, query_start, t)
            searches.append({"sar_date": acq["date"], "stream": stream, "query_url": query_url,
                             "requested_at_utc": requested_at,
                             "returned_granule_count": len(granules),
                             "granules": granules})
            for days in (1, 3, 7):
                start = t - dt.timedelta(days=days)
                assessment = assess_window(granules, start, t)
                windows.append({"sar_date": acq["date"], "source_id": acq["source_id"],
                                "sidecar": acq["sidecar"], "sar_start_utc": t.isoformat(),
                                "window_start_utc": start.isoformat(),
                                "window_end_exclusive_utc": t.isoformat(), "days": days,
                                "stream": stream, "short_name": short_name,
                                "supplemental_acquisition": acq["supplemental"], **assessment})
            if acq["date"] == PROBE_DATE:
                # Probe the last full granule before SAR time, a real candidate
                # input to the 1/3/7-day windows.
                candidates = [g for g in granules if g.get("start") and
                              utc_parse(g["start"]) + BIN <= t and
                              utc_parse(g["start"]) + BIN > t - dt.timedelta(hours=1)]
                if candidates:
                    probe_requested_at = dt.datetime.now(UTC).isoformat()
                    probes.append({"sar_date": acq["date"], "stream": stream,
                                   "granule_id": candidates[-1]["granule_id"],
                                   "granule_url": candidates[-1]["url"],
                                   "requested_at_utc": probe_requested_at,
                                   "probe": probe_real_granule(candidates[-1]["url"])})
    return {"generated_at_utc": now.isoformat(), "point_lon_lat": list(POINT),
            "collections": collections, "acquisitions": [
                {k: (v.isoformat() if k == "time" else v) for k, v in a.items() if k != "grid"} | {
                    "grid_compatibility": {"epsg": a["grid"].get("epsg"),
                                           "spacing": a["grid"].get("spacing"),
                                           "window": a["grid"].get("window"),
                                           "paths": a["grid"].get("paths")}}
                for a in acquisitions],
            "searches": searches, "windows": windows, "actual_granule_probes": probes,
            "audit_scope": "access_only; no authentication attempted; no precipitation download or extraction",
            "data_values": {"precipitation_mm": None,
                            "meaning": "null means not measured by this access-only audit; it is not zero rainfall"}}


def main():
    report = build_report()
    output = ROOT / "data/amazon-imerg-experiment.json"
    output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"output": str(output.relative_to(ROOT)),
                      "generated_at_utc": report["generated_at_utc"],
                      "acquisitions": len(report["acquisitions"]), "windows": len(report["windows"]),
                      "searches": len(report["searches"]),
                      "probes": report["actual_granule_probes"]}, indent=2))


if __name__ == "__main__":
    main()
