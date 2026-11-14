"""Offline checks for pipeline.context_amazon: parsers, rasterisation and validate() on synthetic patches."""
import csv
import io

import numpy as np
from pyproj import CRS, Transformer
from rasterio.transform import from_origin

from pipeline.config import Site
from pipeline import context_amazon as ca
from pipeline.grid import Grid

GRID = Grid(CRS.from_epsg(32722), from_origin(600_000, 9_480_000, 100, 100), 60, 50)  # ~ -49.1, -4.7
TO_LL = Transformer.from_crs(GRID.crs, 4326, always_xy=True)
SITE = Site(id="synthetic", name="test", bbox=(-49.5, -5.0, -49.05, -4.55),
            start="2025-11-01", end="2026-11-03", tracks=())


def cell_xy(r, c):
    return GRID.transform @ (c + 0.5, r + 0.5)


def cell_lonlat(r, c):
    return TO_LL.transform(*cell_xy(r, c))


def rect(r0, c0, r1, c1):
    """Lon/lat polygon covering cells rows r0..r1-1, cols c0..c1-1 (edges on cell borders)."""
    pts = [GRID.transform @ (c, r) for c, r in [(c0, r0), (c1, r0), (c1, r1), (c0, r1), (c0, r0)]]
    xs, ys = TO_LL.transform([p[0] for p in pts], [p[1] for p in pts])
    return {"type": "Polygon", "coordinates": [list(zip(xs, ys))]}


def alert(geom, date, source="DETER", cls="DESMATAMENTO_CR"):
    return {"type": "Feature", "geometry": geom,
            "properties": {"date": date, "source": source, "class": cls,
                           "area_ha": ca.geometry_area_ha(geom)}}


def cells(r0, c0, r1, c1):
    return [(r, c) for r in range(r0, r1) for c in range(c0, c1)]


# ----------------------------------------------------------------------------- parsers

def test_firms_rows_filtered_to_bbox_and_dates():
    text = ("latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,satellite,instrument,"
            "confidence,version,bright_ti5,frp,daynight,type\n"
            "-4.80,-49.30,330,0.4,0.4,2025-11-05,0412,N,VIIRS,n,2,290,3.5,N,0\n"   # in
            "-4.80,-49.30,330,0.4,0.4,2025-10-31,0412,N,VIIRS,h,2,290,3.5,N,0\n"   # too early
            "-6.00,-49.30,330,0.4,0.4,2025-11-05,0412,N,VIIRS,l,2,290,3.5,N,0\n")  # outside
    rows = ca.parse_firms_rows(csv.DictReader(io.StringIO(text)), "VIIRS_SNPP", SITE.bbox,
                               ca._date(SITE.start), ca._date(SITE.end))
    assert len(rows) == 1
    f = rows[0]
    assert f["date"] == "2025-11-05" and f["source"] == "VIIRS_SNPP" and f["confidence"] == "n"
    assert f["frp"] == 3.5 and f["lat"] == -4.8 and f["lon"] == -49.3


def test_modis_confidence_is_int():
    rows = [{"latitude": "-4.7", "longitude": "-49.2", "acq_date": "2026-08-01",
             "confidence": "77", "frp": "8.8", "acq_time": "124"}]
    f = ca.parse_firms_rows(rows, "MODIS", SITE.bbox, ca._date(SITE.start), ca._date(SITE.end))[0]
    assert f["confidence"] == 77 and f["time"] == "0124"


def test_inpe_rows_keep_viirs_modis_only():
    rows = [
        {"lat": " -4.70", "lon": " -49.20", "data_hora_gmt": "2026-09-01 16:40:00", "satelite": "NOAA-21", "frp": "12"},
        {"lat": " -4.70", "lon": " -49.20", "data_hora_gmt": "2026-09-01 16:40:00", "satelite": "GOES-19", "frp": "99"},
        {"lat": " -4.70", "lon": " -49.20", "data_hora_gmt": "2026-09-01 13:30:00", "satelite": "AQUA_M-T", "frp": ""},
    ]
    got = ca.parse_inpe_rows(rows, SITE.bbox, ca._date(SITE.start), ca._date(SITE.end))
    assert [f["source"] for f in got] == ["VIIRS_NOAA21", "MODIS"]
    assert got[0]["time"] == "1640" and got[1]["frp"] is None
    only21 = ca.parse_inpe_rows(rows, SITE.bbox, ca._date(SITE.start), ca._date(SITE.end), ("VIIRS_NOAA21",))
    assert len(only21) == 1


def test_lat_prefilter_never_drops_aoi_lines():
    pre = ca._lat_prefixes(SITE.bbox)
    for lat in (-5.0, -4.99, -4.7, -4.55):
        assert any(t in f"x, {lat:.6f}, -49.2" for t in pre)


def test_deter_class_filter_and_area():
    g = rect(0, 0, 10, 10)                       # 1 km x 1 km = 100 ha
    fc = {"features": [
        {"geometry": g, "properties": {"classname": "DESMATAMENTO_CR", "view_date": "2026-05-10", "gid": "1"}},
        {"geometry": g, "properties": {"classname": "CS_DESORDENADO", "view_date": "2026-05-10", "gid": "2"}},
        {"geometry": g, "properties": {"classname": "CICATRIZ_DE_QUEIMADA", "view_date": "2026-09-01", "gid": "3"}},
        {"geometry": g, "properties": {"classname": "DESMATAMENTO_CR", "view_date": "2024-01-01", "gid": "4"}},
    ]}
    out = ca.parse_deter(fc, ca._date(SITE.start), ca._date(SITE.end))
    assert [f["properties"]["class"] for f in out] == ["DESMATAMENTO_CR", "CICATRIZ_DE_QUEIMADA"]
    assert abs(out[0]["properties"]["area_ha"] - 100) < 2      # UTM scale factor ~0.9996-1.0004


def test_glad_polygons_group_and_earliest_day():
    from rasterio.transform import from_origin as fo
    alert_a = np.zeros((20, 20), np.uint8)
    day = np.zeros((20, 20), np.uint16)
    alert_a[2:8, 2:8] = 3; day[2:8, 2:8] = 150; day[2, 2] = 140       # one clearing, earliest day 140
    alert_a[15, 15] = 3; day[15, 15] = 160                             # speck -> dropped by min_ha
    alert_a[12:18, 2:8] = 2; day[12:18, 2:8] = 170                     # probable only -> dropped
    tr = fo(-49.3, -4.7, 0.00025, 0.00025)
    feats = ca.glad_polygons(alert_a, day, tr, 2026, ca._date("2025-11-01"), ca._date("2026-11-03"))
    assert len(feats) == 1
    assert feats[0]["properties"]["date"] == "2026-05-20"              # DOY 140 of 2026
    assert 0.5 < feats[0]["properties"]["area_ha"] < 4


def test_glad_tile_name():
    assert ca.glad_tile(-49.3, -4.8) == "050W_10S_040W_00N"
    assert ca.glad_tile(12.0, 3.0) == "010E_00N_020E_10N"


# ----------------------------------------------------------------------------- rasterise + validate

def test_rasterize_alerts_earliest_date_wins():
    a = [alert(rect(5, 5, 15, 15), "2026-07-01"), alert(rect(10, 10, 20, 20), "2026-06-01")]
    mask, first = ca.rasterize_alerts(SITE, GRID, a)
    assert mask.dtype == np.uint8 and mask.shape == GRID.shape
    assert mask.sum() == 100 + 100 - 25
    assert ca.day_to_iso(first[12, 12]) == "2026-06-01"   # overlap -> earlier
    assert ca.day_to_iso(first[6, 6]) == "2026-07-01"
    assert first[0, 0] == 0 and first[30, 30] == 0


def test_rasterize_alerts_empty():
    mask, first = ca.rasterize_alerts(SITE, GRID, {"type": "FeatureCollection", "features": []})
    assert mask.sum() == 0 and first.sum() == 0


def test_validate_synthetic_patches():
    alerts = {"type": "FeatureCollection", "features": [
        alert(rect(10, 10, 20, 20), "2026-07-20"),                       # 100 cells
        alert(rect(40, 40, 45, 45), "2026-08-10", source="GLAD-L"),     # 25 cells, missed by us
    ]}
    lon_near, lat_near = TO_LL.transform(*(GRID.transform @ (25, 15)))  # 500 m east of patch A's edge
    lon_far, lat_far = cell_lonlat(45, 5)
    fires = [
        {"date": "2026-07-25", "lat": lat_near, "lon": lon_near, "source": "VIIRS_NOAA20"},
        {"date": "2026-01-01", "lat": lat_near, "lon": lon_near, "source": "MODIS"},     # too old
        {"date": "2026-07-01", "lat": lat_far, "lon": lon_far, "source": "VIIRS_SNPP"},  # far
    ]
    mask_b = np.zeros(GRID.shape, bool)
    mask_b[30:33, 50:53] = True
    patches = [
        {"id": "A", "cells": cells(12, 12, 20, 20), "since": "2026-07-10", "style": "drop"},  # 64 cells in alert
        {"id": "B", "cells": mask_b, "since": "2026-07-01", "style": "drop"},                 # nothing there
        {"id": "C", "cells": cells(10, 10, 12, 20), "since": "2026-08-05", "style": "drop"},  # 20 cells, late
    ]
    res = ca.validate(patches, alerts, fires, max_days=60, grid=GRID)
    p = {r["id"]: r for r in res["patches"]}

    assert p["A"]["alert"] and p["A"]["lag_days"] == -10 and p["A"]["alert_date"] == "2026-07-20"
    assert p["A"]["alert_sources"] == ["DETER"]
    assert p["A"]["fire"] and p["A"]["fire_date"] == "2026-07-25"
    assert 400 < p["A"]["fire_dist_m"] < 600 and p["A"]["fire_source"] == "VIIRS_NOAA20"

    assert not p["B"]["alert"] and p["B"]["lag_days"] is None and not p["B"]["fire"]
    assert p["B"]["n_cells"] == 9

    assert p["C"]["alert"] and p["C"]["lag_days"] == 16
    assert p["C"]["fire"]                                   # same fire, 2026-07-25 within 60 days

    s = res["summary"]
    assert s["n_patches"] == 3
    assert abs(s["share_confirmed"] - 2 / 3) < 1e-9
    assert s["median_lag_days"] == 3.0                     # median of -10, 16
    assert abs(s["share_with_fire"] - 2 / 3) < 1e-9
    assert s["alert_area_ha"] == 125 and s["caught_alert_area_ha"] == 84
    assert abs(s["recall_area"] - 84 / 125) < 1e-9
    assert s["recall_by_source"] == {"DETER": 0.84, "GLAD-L": 0.0}


def test_validate_fire_window_and_radius():
    lon, lat = TO_LL.transform(*(GRID.transform @ (5 + 12, 5)))    # 1.2 km east of cell (4,4)'s right edge
    patches = [{"id": "x", "cells": [(4, 4)], "since": "2026-06-01", "style": "drop"}]
    fires = [{"date": "2026-06-02", "lat": lat, "lon": lon}]
    r = ca.validate(patches, [], fires, grid=GRID)
    assert not r["patches"][0]["fire"]
    assert r["summary"]["recall_area"] is None and r["summary"]["share_confirmed"] == 0
    r = ca.validate(patches, [], fires, grid=GRID, fire_km=1.5)
    assert r["patches"][0]["fire"]
    near_lon, near_lat = cell_lonlat(4, 6)
    late = [{"date": "2026-08-15", "lat": near_lat, "lon": near_lon}]   # 75 days after
    assert not ca.validate(patches, [], late, grid=GRID, max_days=60)["patches"][0]["fire"]
    assert ca.validate(patches, [], late, grid=GRID, max_days=90)["patches"][0]["fire"]


def test_validate_empty_inputs():
    r = ca.validate([], [], [], grid=GRID)
    assert r["summary"]["n_patches"] == 0 and r["summary"]["share_confirmed"] is None
