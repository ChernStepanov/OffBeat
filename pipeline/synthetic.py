"""Synthetic NISAR inputs on the real site grid and real WorldCover, shaped exactly like
nisar.read_gcov / read_gunw output. Lets the whole chain (analysis -> export -> web) run
before Earthdata access exists. Every value here is invented; the export marks it so.
"""
from __future__ import annotations

from datetime import date, timedelta

import numpy as np
from scipy.ndimage import gaussian_filter, binary_dilation

from .config import GLOBAL_GAP, Site

# L-band gamma0 in dB per WorldCover class: HH, HV, seasonal amplitude
BASE = {10: (-7.0, -12.5, 0.4), 20: (-9.0, -15.0, 0.8), 30: (-10.5, -18.0, 1.2), 40: (-9.5, -16.5, 1.8),
        50: (-3.0, -11.0, 0.2), 60: (-12.0, -21.0, 0.6), 80: (-20.0, -27.0, 0.5), 90: (-8.5, -15.0, 1.0),
        95: (-7.5, -13.0, 0.5), 0: (-15.0, -22.0, 0.0)}


def acquisition_dates(site: Site, offset_days: int = 0) -> list[str]:
    gaps = [GLOBAL_GAP, *site.gaps]
    d, end, out = date.fromisoformat(site.start) + timedelta(offset_days), date.fromisoformat(site.end), []
    while d <= end:
        s = d.isoformat()
        if not any(a <= s <= b for a, b in gaps):
            out.append(s)
        d += timedelta(12)
    return out


def _field(rng, shape, sigma):
    f = gaussian_filter(rng.standard_normal(shape), sigma)
    return (f - f.mean()) / (f.std() + 1e-9)


def _enu(shape, direction):
    """Typical NISAR geometry: right-looking, ~37 deg incidence. Ascending looks east, descending west."""
    inc, east = np.deg2rad(37), (-1 if direction == "A" else 1)
    v = np.array([east * np.sin(inc) * 0.98, -0.17 * np.sin(inc), np.cos(inc)], np.float32)
    return np.broadcast_to(v[:, None, None], (3, *shape)).astype(np.float32)


def make(site: Site, cover: np.ndarray, seed: int = 1):
    """Returns (gcov list[dict], gunw dict[track -> list[pair dict]], truth dict)."""
    rng = np.random.default_rng(seed)
    H, W = cover.shape
    land = cover != 80
    yy, xx = np.indices((H, W))
    dates = acquisition_dates(site)
    T = len(dates)
    ev = next((i for i, d in enumerate(dates) if site.event and d >= site.event), None)

    hh_add = np.zeros((T, H, W), np.float32)
    hv_add = np.zeros((T, H, W), np.float32)
    up_rate = np.zeros((H, W), np.float32)          # cm/yr
    east_rate = np.zeros((H, W), np.float32)
    coseis = np.zeros((H, W), np.float32)           # cm, vertical
    damage = np.zeros((H, W), bool)

    if site.id == "amazon":
        # fishbone clearings in forest, opening between July and October 2026
        forest = cover == 10
        later = [i for i, d in enumerate(dates) if "2026-07-01" <= d <= "2026-10-20"]
        for _ in range(55):
            r, c = rng.integers(20, H - 20), rng.integers(20, W - 20)
            if not forest[r, c]:
                continue
            h, w = rng.integers(3, 9), rng.integers(4, 16)
            m = np.zeros((H, W), bool); m[r:r + h, c:c + w] = True
            m &= forest
            t0 = later[rng.integers(len(later))]
            hv_add[t0:, m] -= rng.uniform(4.5, 7.5)
            hh_add[t0:, m] -= 2.0
        # vegetation along the reservoir shore goes under water as the rains return in late September
        shore = binary_dilation(cover == 80, iterations=2) & ~(cover == 80) & np.isin(cover, (10, 30, 90))
        shore &= _field(rng, (H, W), 6) > 0.3
        wet = [i for i, d in enumerate(dates) if d >= "2026-09-20"][0]
        hh_add[wet:, shore] += 5.5

    if site.id == "mexico":
        built = np.isin(cover, (50, 30, 60))
        for r0, c0, s0, a in ((0.45, 0.72, 0.16, 32), (0.62, 0.55, 0.12, 24), (0.80, 0.42, 0.09, 18), (0.30, 0.64, 0.07, 14)):
            r0, c0, s0 = r0 * H, c0 * W, s0 * H
            up_rate -= a * np.exp(-((yy - r0) ** 2 + (xx - c0) ** 2) / (2 * s0 ** 2))
        up_rate *= (0.75 + 0.25 * _field(rng, (H, W), 12)) * built
        east_rate = 0.08 * np.gradient(gaussian_filter(up_rate, 8), axis=1) * 100

    if site.id == "venezuela":
        # coseismic: uplift lobe on the coast decaying inland, from an offshore fault
        from scipy.ndimage import distance_transform_edt
        coast = cover == 80
        inland = distance_transform_edt(~coast)                    # pixels from the shore (the fault runs offshore)
        coseis = (-12 * np.exp(-inland / 70) * (0.85 + 0.15 * _field(rng, (H, W), 15))).astype(np.float32)
        coseis[coast] = 0
        dist = np.exp(-inland / 70)                                # 1 at the shore, used for damage odds below
        built = cover == 50
        seeds = built & (_field(rng, (H, W), 3) > 2.0) & (dist > 0.15 * dist.max())
        damage = binary_dilation(seeds, iterations=1) & built
        # landslides on forested slopes near the coast
        slides = (cover == 10) & (_field(rng, (H, W), 2) > 2.3) & (dist > 0.1 * dist.max())
        hv_add[ev:, slides] -= 6
        hh_add[ev:, slides] -= 2

    # ---------- GCOV ----------
    gcov = []
    hh0 = np.vectorize(lambda c: BASE.get(int(c), BASE[0])[0])(cover).astype(np.float32)
    hv0 = np.vectorize(lambda c: BASE.get(int(c), BASE[0])[1])(cover).astype(np.float32)
    amp = np.vectorize(lambda c: BASE.get(int(c), BASE[0])[2])(cover).astype(np.float32)
    speckle_hh, speckle_hv = _field(rng, (H, W), 1) * 0.6, _field(rng, (H, W), 1) * 0.6
    for t, d in enumerate(dates):
        season = amp * np.sin(2 * np.pi * (date.fromisoformat(d).timetuple().tm_yday / 365.0 - 0.1))
        hh = hh0 + season + speckle_hh + rng.normal(0, 0.55, (H, W)) + hh_add[t]
        hv = hv0 + 0.8 * season + speckle_hv + rng.normal(0, 0.6, (H, W)) + hv_add[t]
        if site.id == "amazon" and t < 6:          # the uncalibrated BETA months sit 0.7 dB off
            hh += 0.7; hv += 0.7
        gcov.append({"date": d, "HHHH": (10 ** (hh / 10)).astype(np.float32),
                     "HVHV": (10 ** (hv / 10)).astype(np.float32), "valid": np.ones((H, W), bool)})

    # ---------- GUNW, one chain per track ----------
    gunw = {}
    for k, tr in enumerate(site.tracks[:2]):
        tdates = acquisition_dates(site, offset_days=0 if k == 0 else 5)
        enu = _enu((H, W), tr.direction)
        # atmosphere is one delay screen per acquisition; a pair sees the difference of two screens
        screens = {d: _field(rng, (H, W), 40) * 0.006 for d in tdates}
        pairs = []
        for d0, d1 in zip(tdates, tdates[1:]):
            dt = (date.fromisoformat(d1) - date.fromisoformat(d0)).days / 365.25
            disp = (up_rate * enu[2] + east_rate * enu[0]) * dt / 100   # m
            spans_event = site.event and d0 < site.event <= d1
            if spans_event:
                disp = disp + coseis * enu[2] / 100
            atmo = screens[d1] - screens[d0] + rng.normal(0, 0.002, (H, W))
            coh = np.clip(np.where(cover == 50, 0.85, np.where(cover == 10, 0.35, 0.6))
                          + rng.normal(0, 0.05, (H, W)), 0, 1)
            if spans_event:
                coh[damage] = rng.uniform(0.1, 0.3, damage.sum())
            coh[~land] = 0.05
            pairs.append({"ref": d0, "sec": d1, "track": tr.track, "direction": tr.direction,
                          "los_m": np.where(land, disp + atmo, np.nan).astype(np.float32),
                          "coherence": coh.astype(np.float32),
                          "conncomp": land.astype(np.int32), "los_enu": enu})
        gunw[tr.track] = pairs

    truth = {"up_rate": up_rate, "east_rate": east_rate, "coseismic_cm": coseis, "damage": damage}
    return gcov, gunw, truth
