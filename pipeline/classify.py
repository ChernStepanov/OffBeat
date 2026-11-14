"""Name the shape of a pixel's departure from its peers.

Each channel is a z-series against peers (HH, HV, and, where GUNW exists,
displacement relative to peers). We find one change point per pixel and read
the jump on each channel:

  drop  - HV falls sharply (canopy gone: clearing, fire)
  flood - HH jumps up while HV barely moves (double bounce off water under plants)
  step  - displacement jumps between two dates (earthquake)
  drift - displacement departs steadily, no single jump (subsidence)
"""
from __future__ import annotations

import numpy as np

STYLES = {0: None, 1: "drop", 2: "flood", 3: "drift", 4: "step"}
CODE = {v: k for k, v in STYLES.items() if v}


def change_point(z: np.ndarray, min_seg: int = 2):
    """Best single mean-shift for every pixel.

    z: float[T, H, W] with NaN gaps. Returns (index int16[H,W], jump float32[H,W]):
    index is the first date after the change, jump = mean(after) - mean(before).
    """
    T = z.shape[0]
    ok = ~np.isnan(z)
    v = np.where(ok, z, 0.0)
    cs, cn = np.cumsum(v, 0), np.cumsum(ok, 0)
    tot, ntot = cs[-1], cn[-1]
    best = np.zeros(z.shape[1:], np.float32)
    idx = np.zeros(z.shape[1:], np.int16)
    jump = np.zeros(z.shape[1:], np.float32)
    for k in range(min_seg, T - min_seg + 1):
        nb, sb = cn[k - 1], cs[k - 1]
        na, sa = ntot - nb, tot - sb
        with np.errstate(invalid="ignore", divide="ignore"):
            d = sa / na - sb / nb
            score = np.abs(d) * np.sqrt(nb * na / np.maximum(ntot, 1))  # t-like statistic
        score = np.where((nb >= min_seg) & (na >= min_seg), score, 0)
        better = score > best
        best = np.where(better, score, best)
        idx = np.where(better, k, idx).astype(np.int16)
        jump = np.where(better, d, jump).astype(np.float32)
    return idx, jump


def jump_at(z: np.ndarray, idx: np.ndarray) -> np.ndarray:
    """mean(after) - mean(before) of z split at a given index per pixel."""
    T = z.shape[0]
    after = np.arange(T)[:, None, None] >= idx[None]
    ok = ~np.isnan(z)
    v = np.where(ok, z, 0)
    with np.errstate(invalid="ignore", divide="ignore"):
        a = (v * after).sum(0) / (ok & after).sum(0)
        b = (v * ~after).sum(0) / (ok & ~after).sum(0)
    return np.nan_to_num(a - b).astype(np.float32)


def drift_strength(dz: np.ndarray):
    """Linear trend of a relative-displacement z-series and how much a single step explains instead.

    Returns (slope_per_step float32[H,W], linearity float32[H,W] in 0..1).
    """
    T = dz.shape[0]
    t = np.arange(T, dtype=np.float32)[:, None, None]
    ok = ~np.isnan(dz)
    n = ok.sum(0)
    tm = np.where(ok, t, 0).sum(0) / np.maximum(n, 1)
    ym = np.where(ok, dz, 0).sum(0) / np.maximum(n, 1)
    tt = np.where(ok, t - tm, 0)
    yy = np.where(ok, dz - ym, 0)
    sxx, sxy, syy = (tt * tt).sum(0), (tt * yy).sum(0), (yy * yy).sum(0)
    with np.errstate(invalid="ignore", divide="ignore"):
        slope = sxy / sxx
        r2 = sxy * sxy / (sxx * syy)
    return slope.astype(np.float32), np.nan_to_num(r2).astype(np.float32)


def classify(z_hh: np.ndarray, z_hv: np.ndarray, z_disp: np.ndarray | None = None,
             k: float = 2.5, flood_hv_max: float = 1.5):
    """Style code, change index and signed z in the style's own channel.

    Returns dict: style uint8[H,W] (codes in STYLES), since int16[H,W] (-1 none),
    z float32[H,W] (last-date z in the style channel; HV last z for unstyled pixels).
    """
    H, W = z_hh.shape[1:]
    style = np.zeros((H, W), np.uint8)
    since = np.full((H, W), -1, np.int16)
    zout = np.nan_to_num(z_hv[-1]).astype(np.float32)

    i_hv, j_hv = change_point(z_hv)
    i_hh, j_hh = change_point(z_hh)

    drop = j_hv <= -k
    # HV measured across the same split as the HH jump, not at HV's own (noise-chosen) best split
    flood = (j_hh >= k) & (np.abs(jump_at(z_hv, i_hh)) < flood_hv_max) & ~drop
    style[drop], since[drop] = CODE["drop"], i_hv[drop]
    style[flood], since[flood] = CODE["flood"], i_hh[flood]
    zout[flood] = np.nan_to_num(z_hh[-1])[flood]

    if z_disp is not None:
        i_d, j_d = change_point(z_disp)
        slope, lin = drift_strength(z_disp)
        # share of variance a single step explains, to compare with the straight line's r^2
        ok = ~np.isnan(z_disp)
        n = ok.sum(0)
        nb = np.take_along_axis(np.cumsum(ok, 0), np.maximum(i_d - 1, 0)[None].astype(np.intp), 0)[0]
        mean = np.where(ok, z_disp, 0).sum(0) / np.maximum(n, 1)
        syy = np.where(ok, (z_disp - mean) ** 2, 0).sum(0)
        with np.errstate(invalid="ignore", divide="ignore"):
            r2_step = np.nan_to_num(j_d ** 2 * nb * (n - nb) / np.maximum(n, 1) / syy)
        last = np.nan_to_num(z_disp[-1])
        moved = (np.abs(last) >= k) | (np.abs(j_d) >= k)
        step = moved & (np.abs(j_d) >= k) & (r2_step > lin)
        drift = moved & ~step & (lin >= 0.6)
        first = np.argmax(np.abs(np.nan_to_num(z_disp)) >= 2, axis=0).astype(np.int16)  # drift: first date past 2 sigma
        for m, name, i in ((step, "step", i_d), (drift, "drift", first)):
            m = m & (style == 0)
            style[m] = CODE[name]
            since[m] = i[m]
            zout[m] = last[m]
    return {"style": style, "since": since, "z": zout}
