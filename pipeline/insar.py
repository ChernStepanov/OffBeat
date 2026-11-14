"""Interferometry on GUNW pairs: displacement series, ascending + descending decomposition,
and a damage proxy from coherence loss.

Inputs are dicts from nisar.read_gunw on the site grid:
  {"ref", "sec", "track", "direction", "los_m", "coherence", "conncomp", "los_enu"}
"""
from __future__ import annotations

from datetime import date

import numpy as np


def _d(s: str) -> date:
    return date.fromisoformat(s[:10])


# ---------- displacement series from consecutive pairs ----------

def chain_pairs(pairs: list[dict], min_coh: float = 0.3, ref_mask: np.ndarray | None = None):
    """Sum consecutive 12/24-day pairs of one track into cumulative LOS displacement.

    Each pair is re-referenced to the median of reliable pixels (or of ref_mask), so
    orbit and atmosphere offsets common to the scene drop out. A pixel that is unreliable
    in one pair (low coherence or conncomp 0) gets NaN from that date on.
    Returns (dates list[str], disp_cm float32[T, H, W]) with T = len(pairs) + 1, first date = 0.
    """
    if not pairs:
        raise ValueError('At least one GUNW pair is required')
    pairs = sorted(pairs, key=lambda p: p["sec"])
    if len({(p.get('track'), p.get('direction')) for p in pairs}) > 1:
        raise ValueError('Cannot chain different tracks or viewing directions')
    H, W = pairs[0]["los_m"].shape
    dates = [pairs[0]["ref"]] + [p["sec"] for p in pairs]
    out = np.zeros((len(dates), H, W), np.float32)
    alive = np.ones((H, W), bool)
    for i, p in enumerate(pairs, start=1):
        if p["ref"] != dates[i - 1]:
            raise ValueError(f"pairs are not consecutive: {dates[i - 1]} -> {p['ref']}")
        good = (p["coherence"] >= min_coh) & (p["conncomp"] > 0) & ~np.isnan(p["los_m"])
        ref = good if ref_mask is None else good & ref_mask
        if not ref.any():
            alive[:] = False
            if i == 1: out[0] = np.nan
            out[i:] = np.nan
            break
        components, counts = np.unique(p['conncomp'][ref], return_counts=True)
        component = components[np.argmax(counts)]
        ref &= p['conncomp'] == component
        good &= p['conncomp'] == component
        offset = np.nanmedian(p["los_m"][ref])
        if i == 1: out[0] = np.where(good,0,np.nan)
        alive &= good
        out[i] = out[i - 1] + np.where(alive, (p["los_m"] - offset) * 100, np.nan)
    return dates, out


def rate_cm_per_year(dates: list[str], disp_cm: np.ndarray) -> np.ndarray:
    """Least-squares linear rate per pixel, NaN-aware."""
    t = np.array([(_d(d) - _d(dates[0])).days / 365.25 for d in dates], np.float32)[:, None, None]
    ok = ~np.isnan(disp_cm)
    n = ok.sum(0)
    tm = np.where(ok, t, 0).sum(0) / np.maximum(n, 1)
    ym = np.where(ok, disp_cm, 0).sum(0) / np.maximum(n, 1)
    tt, yy = np.where(ok, t - tm, 0), np.where(ok, disp_cm - ym, 0)
    with np.errstate(invalid="ignore", divide="ignore"):
        r = (tt * yy).sum(0) / (tt * tt).sum(0)
    r[n < 4] = np.nan
    return r.astype(np.float32)


# ---------- ascending + descending -> vertical and east ----------

def decompose(rate_a: np.ndarray, enu_a: np.ndarray, rate_d: np.ndarray, enu_d: np.ndarray):
    """Solve two LOS rates for east and up per pixel.

    NISAR's near-polar orbit makes LOS almost blind to north-south motion, so north is
    assumed zero and the 2 x 2 system [e_a u_a; e_d u_d] [E U]^T = [r_a r_d]^T is solved.
    enu_*: float[3, H, W] unit vectors ground -> satellite. Returns (east, up) float32[H, W].
    """
    a11, a12 = enu_a[0], enu_a[2]
    a21, a22 = enu_d[0], enu_d[2]
    det = a11 * a22 - a12 * a21
    with np.errstate(invalid="ignore", divide="ignore"):
        east = (rate_a * a22 - a12 * rate_d) / det
        up = (a11 * rate_d - rate_a * a21) / det
    bad = np.abs(det) < 0.1
    east[bad] = np.nan
    up[bad] = np.nan
    return east.astype(np.float32), up.astype(np.float32)


# ---------- damage proxy from coherence loss ----------

def damage_proxy(pre: list[dict], co: dict, cover: np.ndarray, classes=(50,),
                 min_pre_coh: float = 0.5, sd_floor: float = 0.03):
    """Coherence loss across the event, scored against the scene's own loss.

    pre: pairs entirely before the event (their mean coherence is the 'normal' level).
    co:  the pair that spans the event.
    Only pixels of the given WorldCover classes (default built-up) with stable pre-event
    coherence are scored; vegetation decorrelates on its own and would drown the signal.
    Returns float32[H, W] z: how much more coherence this pixel lost than its class did
    (positive = lost more = likely damage). NaN elsewhere.
    """
    coh_pre = np.nanmean(np.stack([p["coherence"] for p in pre]), axis=0)
    loss = coh_pre - co["coherence"]
    m = np.isin(cover, classes) & (coh_pre >= min_pre_coh) & ~np.isnan(loss)
    out = np.full(loss.shape, np.nan, np.float32)
    if m.sum() < 30:
        return out
    med = np.nanmedian(loss[m])
    sd = max(1.4826 * np.nanmedian(np.abs(loss[m] - med)), sd_floor)
    out[m] = (loss[m] - med) / sd
    return out
