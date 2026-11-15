"""Georeferencing, valid-zero, alpha, range and hash checks for the PNG overlays."""
import importlib.util
import json
from pathlib import Path

import numpy as np
from PIL import Image
from pyproj import Transformer
from rasterio.transform import Affine, array_bounds, rowcol, xy

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("external_overlays", ROOT / "scripts/build_external_map_overlays.py")
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


def test_overlays_hash_bounds_and_pixel_center_georeferencing():
    manifest = json.loads((ROOT / "data/investigation/external-maps.json").read_text())
    grid = manifest["native_grid"]
    overlays = manifest["overlays"]
    native_tr = builder.native_transform(grid)
    to_geo = Transformer.from_crs(grid["epsg"], 4326, always_xy=True)
    to_native = Transformer.from_crs(4326, grid["epsg"], always_xy=True)

    # Native first cell is centered exactly at x_first/y_first (not at the corner).
    x0, y0 = xy(native_tr, 0, 0)
    assert np.isclose(x0, grid["x_first"])
    assert np.isclose(y0, grid["y_first"])
    expected_lon, expected_lat = to_geo.transform(x0, y0)
    native = np.load(ROOT / manifest["derived"]["path"])
    assert np.isclose(native["longitude"][0, 0], expected_lon, atol=1e-8)
    assert np.isclose(native["latitude"][0, 0], expected_lat, atol=1e-8)

    for item in overlays.values():
        path = ROOT / item["path"]
        assert builder.file_hash(path) == item["sha256"]
        image = np.asarray(Image.open(path).convert("RGBA"))
        height, width = image.shape[:2]
        assert (width, height) == (item["width"], item["height"])
        dst_tr = Affine(*item["pixel_transform_wgs84"])
        bounds = array_bounds(height, width, dst_tr)
        assert np.allclose(bounds, item["bounds_wgs84"], atol=1e-10)
        # WGS84 output pixel center maps back inside the native source footprint.
        lon, lat = xy(dst_tr, height // 2, width // 2)
        x, y = to_native.transform(lon, lat)
        r, c = rowcol(native_tr, x, y)
        assert 0 <= r < grid["shape"][0] and 0 <= c < grid["shape"][1]


def test_lossyear_zero_is_visible_and_year_2024_is_not_relabelled():
    manifest = json.loads((ROOT / "data/investigation/external-maps.json").read_text())
    grid = manifest["native_grid"]
    layer = manifest["overlays"]["hansen_lossyear"]
    source = np.load(ROOT / manifest["forest_change"]["path"])["lossyear"]
    dst_tr, width, height, bounds = builder.target_grid(grid)
    warped, valid = builder.warp_native(source, grid, dst_tr, width, height, categorical=True)
    expected = builder.rgba_from_values(warped, valid, "lossyear")
    actual = np.asarray(Image.open(ROOT / layer["path"]).convert("RGBA"))
    assert np.array_equal(actual, expected)

    zero = np.argwhere(valid & (warped == 0))
    year_2024 = np.argwhere(valid & (warped == 24))
    assert len(zero) > 0 and len(year_2024) > 0
    for row, col in (zero[0], year_2024[0]):
        assert actual[row, col, 3] > 0
    assert tuple(actual[zero[0][0], zero[0][1], :3]) == (224, 232, 238)
    assert layer["period"].startswith("2001–2024")
    assert "2026" not in layer["period"]
    assert layer["resampling"] == "nearest"


def test_dem_overlay_uses_bilinear_visual_warp_and_transparent_nodata():
    manifest = json.loads((ROOT / "data/investigation/external-maps.json").read_text())
    layer = manifest["overlays"]["dem_elevation"]
    image = np.asarray(Image.open(ROOT / layer["path"]).convert("RGBA"))
    assert layer["resampling"] == "bilinear"
    assert layer["source_key"] == "derived.elevation_m"
    assert np.any(image[..., 3] > 0)
