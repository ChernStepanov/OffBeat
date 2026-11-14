"""NISAR reader checks.

Offline: synthetic GCOV / GUNW files with the verified HDF5 layout (see pipeline/nisar.py).
Online (marker `network`, CMR only, no login): search returns granules for every demo site.
Run only offline ones with:  pytest pipeline/tests -m "not network"
"""
import math

import h5py
import numpy as np
import pytest
from pyproj import Transformer

from pipeline import nisar
from pipeline.config import SITES
from pipeline.grid import site_grid

SITE = SITES["mexico"]
EPSG = 32614                       # UTM 14N, what NISAR uses over Mexico City
CF = 1.2575e9                      # Hz
WAVELENGTH = nisar.SPEED_OF_LIGHT / CF


# ------------------------------------------------------------------------------- name parsing
def test_parse_names():
    g = nisar.parse_name("NISAR_L2_PR_GCOV_004_019_A_011_4005_DHDH_A_20251030T120539_"
                         "20251030T120613_P05023_N_F_J_001")
    assert (g["track"], g["direction"], g["frame"], g["pols"], g["start"], g["ref"]) == \
        (19, "A", 11, "DHDH", "2025-10-30", None)
    u = nisar.parse_name("NISAR_L2_PR_GUNW_004_054_D_083_005_4000_SH_20251101T230233_20251101T230307_"
                         "20251113T230233_20251113T230308_P05023_N_F_J_001.h5")
    assert (u["track"], u["direction"], u["frame"], u["pols"], u["ref"], u["start"], u["crid"]) == \
        (54, "D", 83, "SH", "2025-11-01", "2025-11-13", "P05023")


# ------------------------------------------------------------------------------- synthetic files
def _site_utm_box(margin=3000.0):
    w, s, e, n = SITE.bbox
    t = Transformer.from_crs(4326, EPSG, always_xy=True)
    xs, ys = t.transform([w, e, w, e], [s, s, n, n])
    return min(xs) - margin, min(ys) - margin, max(xs) + margin, max(ys) + margin


def _coords(step, margin=3000.0):
    x0, y0, x1, y1 = _site_utm_box(margin)
    x0, y1 = math.floor(x0 / step) * step, math.ceil(y1 / step) * step
    nx, ny = int((x1 - x0) / step) + 1, int((y1 - y0) / step) + 1
    x = x0 + step * (np.arange(nx) + 0.5)          # pixel centres
    y = y1 - step * (np.arange(ny) + 0.5)          # north-up -> decreasing
    return x, y


def _proj(group, name="projection"):
    d = group.create_dataset(name, data=np.uint32(EPSG))
    d.attrs["epsg_code"] = np.int32(EPSG)


def make_gcov(path, hv_missing=False):
    x, y = _coords(20.0)
    hh = np.where((np.add.outer(np.arange(y.size), np.arange(x.size)) % 2) == 0, 1.0, 0.01)
    mask = np.ones(hh.shape, np.uint8)
    mask[: y.size // 3, :] = 0                     # partially focused strip in the north
    with h5py.File(path, "w") as f:
        f["/science/LSAR/identification/zeroDopplerStartTime"] = np.bytes_("2025-10-30T12:05:39.000000000")
        g = f.create_group("/science/LSAR/GCOV/grids/frequencyA")
        g["xCoordinates"], g["yCoordinates"] = x, y
        _proj(g)
        g.create_dataset("HHHH", data=hh.astype(np.float32), chunks=(64, 64), fillvalue=np.nan)
        if not hv_missing:
            g.create_dataset("HVHV", data=(hh * 0.1).astype(np.float32), chunks=(64, 64))
        g["mask"] = mask
    return x, y, mask


def make_gunw(path, phase_fn, losx_fn):
    x, y = _coords(80.0)
    X, Y = np.meshgrid(x, y)
    phase = phase_fn(X, Y).astype(np.float32)
    cc = np.ones(phase.shape, np.uint16)
    cc[:, : x.size // 4] = 0                       # west quarter not unwrapped
    mask = np.full(phase.shape, 11, np.uint32)     # ref subswath 1, sec subswath 1, land
    mask[-5:, :] = 255                             # outside the swath at the southern edge
    with h5py.File(path, "w") as f:
        ident = f.create_group("/science/LSAR/identification")
        ident["referenceZeroDopplerStartTime"] = np.bytes_("2025-11-01T23:02:33")
        ident["secondaryZeroDopplerStartTime"] = np.bytes_("2025-11-13T23:02:33")
        ident["trackNumber"] = np.uint32(113)
        ident["orbitPassDirection"] = np.bytes_("Descending")
        gr = f.create_group("/science/LSAR/GUNW/grids/frequencyA")
        gr["centerFrequency"] = np.float64(CF)
        unw = gr.create_group("unwrappedInterferogram")
        unw["xCoordinates"], unw["yCoordinates"] = x, y
        _proj(unw)
        unw["mask"] = mask
        hh = unw.create_group("HH")
        hh["xCoordinates"], hh["yCoordinates"] = x, y
        _proj(hh)
        hh.create_dataset("unwrappedPhase", data=phase, chunks=(64, 64))
        hh["coherenceMagnitude"] = np.full(phase.shape, 0.7, np.float32)
        hh["connectedComponents"] = cc
        # coarse radar-grid cube [height, y, x]
        xc, yc = _coords(1000.0, margin=6000.0)
        z = np.array([-500.0, 0.0, 1000.0, 3000.0, 5000.0, 9000.0])
        rg = f.create_group("/science/LSAR/GUNW/metadata/radarGrid")
        rg["xCoordinates"], rg["yCoordinates"], rg["heightAboveEllipsoid"] = xc, yc, z
        _proj(rg)
        XC, _ = np.meshgrid(xc, yc)
        lx = np.stack([losx_fn(XC) for _ in z]).astype(np.float32)
        rg["losUnitVectorX"] = lx
        rg["losUnitVectorY"] = np.full(lx.shape, -0.12, np.float32)
        rg["incidenceAngle"] = np.full(lx.shape, 37.0, np.float32)
    return x, y


def _granule(path, product):
    return nisar.Granule(id=f"SYN_{product}", url=str(path), product=product, maturity="PROVISIONAL",
                         track=113, direction="D", frame=79, start="2025-11-13",
                         ref="2025-11-01" if product == "GUNW" else None, pols="SH", size_mb=None)


@pytest.fixture
def patched_open(monkeypatch):
    def fake_open(granule):
        return h5py.File(granule.url, "r")
    monkeypatch.setattr(nisar, "open_h5", fake_open)


# ------------------------------------------------------------------------------- GCOV
def test_window_covers_site_and_is_smaller(tmp_path):
    x, y, _ = make_gcov(tmp_path / "g.h5")
    grid = site_grid(SITE)
    rows, cols = nisar.window(x, y, EPSG, grid, pad=3)
    assert 0 < rows.start and rows.stop < y.size and 0 < cols.start and cols.stop < x.size
    x0, y0, x1, y1 = _site_utm_box(0.0)
    assert x[cols.start] < x0 and x[cols.stop - 1] > x1
    assert y[rows.stop - 1] < y0 and y[rows.start] > y1


def test_read_gcov_linear_average_and_mask(tmp_path, patched_open):
    _, _, _ = make_gcov(tmp_path / "g.h5")
    grid = site_grid(SITE)
    out = nisar.read_gcov(_granule(tmp_path / "g.h5", "GCOV"), SITE, grid)
    assert out["date"] == "2025-10-30"
    hh, hv, valid = out["HHHH"], out["HVHV"], out["valid"]
    assert hh.shape == hv.shape == valid.shape == grid.shape and hh.dtype == np.float32
    v = hh[valid]
    # checkerboard 1 / 0.01: linear mean ~0.505; a dB mean would give 0.1
    assert v.size > 0.3 * valid.size
    assert np.all((v > 0.45) & (v < 0.56)), (v.min(), v.max())
    assert np.allclose(hv[valid], hh[valid] * 0.1, rtol=1e-4)
    # the masked northern strip of the product falls in the top rows of the site grid
    assert not valid[0].any() and valid[-1].all()
    assert np.isnan(hh[~valid]).all()


def test_read_gcov_missing_pol(tmp_path, patched_open):
    make_gcov(tmp_path / "g.h5", hv_missing=True)
    out = nisar.read_gcov(_granule(tmp_path / "g.h5", "GCOV"), SITE)
    assert np.isnan(out["HVHV"]).all() and not out["valid"].any()


# ------------------------------------------------------------------------------- GUNW
def test_read_gunw_phase_to_metres_and_los(tmp_path, patched_open):
    xs0 = _site_utm_box()[0]
    ramp = 2e-4                                    # rad per metre east
    x, _ = make_gunw(tmp_path / "u.h5",
              phase_fn=lambda X, Y: 3.0 + ramp * (X - xs0),
              losx_fn=lambda X: 0.60 + 1e-6 * (X - xs0))
    grid = site_grid(SITE)
    out = nisar.read_gunw(_granule(tmp_path / "u.h5", "GUNW"), SITE, grid)
    assert (out["ref"], out["sec"], out["track"], out["direction"]) == ("2025-11-01", "2025-11-13", 113, "D")
    for k in ("los_m", "coherence", "conncomp"):
        assert out[k].shape == grid.shape
    assert out["los_m"].dtype == np.float32 and out["conncomp"].dtype == np.int32
    assert out["los_enu"].shape == (3,) + grid.shape and out["los_enu"].dtype == np.float32

    # expected values at grid pixel centres
    cc, rr = np.meshgrid(np.arange(grid.width) + 0.5, np.arange(grid.height) + 0.5)
    t = grid.transform
    lon, lat = t.a * cc + t.c, t.e * rr + t.f
    px, _ = Transformer.from_crs(4326, EPSG, always_xy=True).transform(lon, lat)
    phase = 3.0 + ramp * (px - xs0)
    expect = -WAVELENGTH / (4 * np.pi) * phase      # positive = toward the satellite
    ok = np.isfinite(out["los_m"])
    assert ok.mean() > 0.95
    assert np.allclose(out["los_m"][ok], expect[ok], atol=2e-4), np.nanmax(abs(out["los_m"] - expect))
    assert np.allclose(out["coherence"][ok], 0.7, atol=1e-5)
    # the product's west quarter has connected component 0
    cut = x[x.size // 4] - 40.0
    assert (out["conncomp"][ok & (px < cut - 100)] == 0).all()
    assert (out["conncomp"][ok & (px > cut + 100)] == 1).all()

    e, n, u = out["los_enu"]
    assert np.allclose(e, 0.60 + 1e-6 * (px - xs0), atol=1e-4)
    assert np.allclose(n, -0.12, atol=1e-6)
    assert np.allclose(e ** 2 + n ** 2 + u ** 2, 1.0, atol=1e-5) and (u > 0).all()


def test_gunw_mask_decoding():
    m = np.array([11, 12, 10, 1, 111, 255, 0x0100 + 11], np.uint32)
    assert nisar._gunw_valid(m).tolist() == [True, True, False, False, False, False, True]


def test_cache_round_trip(tmp_path, monkeypatch, patched_open):
    make_gcov(tmp_path / "g.h5")
    monkeypatch.setattr(nisar, "RAW_DIR", tmp_path / "raw")
    g = _granule(tmp_path / "g.h5", "GCOV")
    a = nisar.load_or_read(g, SITE, "gcov")
    path = nisar.cache_path(SITE, g, "gcov")
    assert path == tmp_path / "raw" / "mexico" / "SYN_GCOV.gcov.npz" and path.exists()

    def boom(*_a, **_k):
        raise AssertionError("cache miss")
    monkeypatch.setattr(nisar, "read_gcov", boom)
    b = nisar.load_or_read(g, SITE, "gcov")
    assert b["date"] == a["date"] == "2025-10-30" and isinstance(b["date"], str)
    for k in ("HHHH", "HVHV", "valid"):
        np.testing.assert_array_equal(a[k], b[k])
    assert b["valid"].dtype == bool


# ------------------------------------------------------------------------------- live CMR
@pytest.mark.network
@pytest.mark.parametrize("product", ["GCOV", "GUNW"])
@pytest.mark.parametrize("site_id", list(SITES))
def test_live_search(site_id, product):
    site = SITES[site_id]
    gs = nisar.search(site, product)
    by_track = {}
    for g in gs:
        k = f"{g.track}{g.direction}/{g.frame}"
        by_track.setdefault(k, {}).setdefault(g.maturity, 0)
        by_track[k][g.maturity] += 1
    print(f"\n{site_id} {product}: {len(gs)} {by_track}")
    assert len(gs) > 0
    assert all(g.url.startswith("https://") and g.url.endswith(".h5") for g in gs)
    assert [g.start for g in gs] == sorted(g.start for g in gs)
    keys = [(g.track, g.frame, g.ref, g.start) for g in gs]
    assert len(keys) == len(set(keys))
    for g in gs:
        assert site.start <= g.start <= site.end
        assert any(t.track == g.track and t.direction == g.direction and g.frame in t.frames
                   for t in site.tracks)
        if product == "GUNW":
            assert g.ref and g.ref < g.start
