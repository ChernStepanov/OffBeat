import datetime as dt

from scripts.experiment_imerg_amazon import (
    BIN,
    UTC,
    assess_window,
    classify_hdf5_response,
    read_acquisitions,
)


def test_full_bin_only_and_coverage_handles_fractional_edges():
    sar = dt.datetime(2026, 9, 4, 9, 4, 8, tzinfo=UTC)
    start = sar - dt.timedelta(days=1)
    # Build every overlapping half-hour bin; the first/last straddling bins
    # must be excluded, leaving 47 complete bins and 97.9167% coverage.
    cursor = dt.datetime(2026, 9, 3, 9, 0, tzinfo=UTC)
    granules = []
    while cursor < sar:
        granules.append({"granule_id": cursor.isoformat(), "start": cursor.isoformat(), "url": "https://x"})
        cursor += BIN
    result = assess_window(granules, start, sar)
    assert result["full_bin_count"] == 47
    assert result["possible_full_bin_count"] == 47
    assert result["missing_full_bin_count"] == 0
    assert result["coverage_percent"] == 97.9167
    assert result["precipitation_mm"] is None
    assert all(dt.datetime.fromisoformat(g["bin_end_exclusive"]) <= sar for g in result["granules"])
    assert all(dt.datetime.fromisoformat(g["bin_start"]) >= start for g in result["granules"])


def test_missing_source_bin_is_not_reported_as_complete_coverage():
    sar = dt.datetime(2026, 9, 4, 9, 4, tzinfo=UTC)
    start = sar - dt.timedelta(days=1)
    granules = []
    cursor = dt.datetime(2026, 9, 3, 9, 0, tzinfo=UTC)
    while cursor < sar:
        if cursor.hour != 12 or cursor.minute != 0:
            granules.append({"granule_id": cursor.isoformat(), "start": cursor.isoformat(), "url": "https://x"})
        cursor += BIN
    result = assess_window(granules, start, sar)
    assert result["possible_full_bin_count"] == 47
    assert result["full_bin_count"] == 46
    assert result["missing_full_bin_count"] == 1
    assert result["coverage_percent"] < 97.9167


def test_aligned_24_hour_window_includes_first_bin_and_has_48_bins():
    start = dt.datetime(2026, 9, 3, 9, 0, tzinfo=UTC)
    sar = dt.datetime(2026, 9, 4, 9, 0, tzinfo=UTC)
    granules = []
    cursor = start
    while cursor < sar:
        granules.append({"granule_id": cursor.isoformat(), "start": cursor.isoformat(), "url": "https://x"})
        cursor += BIN
    result = assess_window(granules, start, sar)
    assert result["full_bin_count"] == 48
    assert result["possible_full_bin_count"] == 48
    assert result["intersecting_granule_count_including_partial_edges"] == 48
    assert result["coverage_percent"] == 100.0


def test_http_200_html_is_not_misidentified_as_hdf5():
    status, verified = classify_hdf5_response(200, "text/html", b"<!doctype html><html>")
    assert status == "http_success_non_hdf5"
    assert verified is None


def test_hdf5_magic_bytes_are_only_access_verification():
    status, verified = classify_hdf5_response(206, "application/octet-stream", b"\x89HDF\r\n\x1a\nrest")
    assert status == "hdf5_signature_verified_access_only"
    assert verified == 0


def test_hdf5_signature_after_user_block_is_detected():
    sample = b"\0" * 512 + b"\x89HDF\r\n\x1a\n" + b"payload"
    status, offset = classify_hdf5_response(206, "application/octet-stream", sample)
    assert status == "hdf5_signature_verified_access_only"
    assert offset == 512


def test_missing_identification_metadata_is_not_filled_from_defaults():
    acquisitions = read_acquisitions()
    without_identification = [a for a in acquisitions if a["identification"] is None]
    assert len(without_identification) == 4
    for acquisition in without_identification:
        assert acquisition["track"] is None
        assert acquisition["frame"] is None
        assert acquisition["pass"] is None
        assert acquisition["identification_provenance"] == "absent_from_sidecar; not inferred"
