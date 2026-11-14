"""Peer statistics: how a pixel's same-land-cover neighbours behave on each date.

For each WorldCover class and date we take the median and a robust spread
(1.4826 x MAD) inside 1 km blocks, then average those block values over a
radius (3 km by default) so every pixel gets a smooth local reference. With a
few months of NISAR history this replaces the pixel's own past.
"""
from __future__ import annotations

import numpy as np
from scipy.ndimage import uniform_filter

MAD_K = 1.4826


def _block_stats(values: np.ndarray, mask: np.ndarray, b: int, min_n: int):
    """Median and robust sd of values[mask] in b x b blocks. NaN where fewer than min_n samples."""
    h, w = values.shape
    bh, bw = -(-h // b), -(-w // b)
    pad = ((0, bh * b - h), (0, bw * b - w))
    v = np.pad(np.where(mask, values, np.nan), pad, constant_values=np.nan)
    v = v.reshape(bh, b, bw, b).transpose(0, 2, 1, 3).reshape(bh, bw, b * b)
    n = np.sum(~np.isnan(v), axis=2)
    with np.errstate(all="ignore"), _quiet():
        med = np.nanmedian(v, axis=2)
        sd = MAD_K * np.nanmedian(np.abs(v - med[..., None]), axis=2)
    med[n < min_n] = np.nan
    sd[n < min_n] = np.nan
    return med, sd, n


class _quiet:
    def __enter__(self):
        import warnings
        self._w = warnings.catch_warnings()
        self._w.__enter__()
        warnings.simplefilter("ignore", RuntimeWarning)

    def __exit__(self, *a):
        self._w.__exit__(*a)


def _nan_smooth(a: np.ndarray, size: int) -> np.ndarray:
    """Mean of the non-NaN values in a size x size window."""
    ok = ~np.isnan(a)
    num = uniform_filter(np.where(ok, a, 0.0), size, mode="constant")
    den = uniform_filter(ok.astype(float), size, mode="constant")
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(den > 0, num / den, np.nan)


def peer_stats(stack: np.ndarray, cover: np.ndarray, pixel_m: float,
               block_m: float = 1000, radius_m: float = 3000, min_n: int = 8,
               sd_floor: float = 0.5, skip_classes=(0, 70, 80)):
    """Peer median and robust sd for every pixel and date.

    stack: float[T, H, W] (e.g. gamma0 in dB, or displacement in cm), NaN = no data.
    cover: int[H, W] WorldCover class codes.
    Returns (med, sd), both float32[T, H, W]; NaN where a class has too few peers
    or the class is skipped (no data, snow, permanent water).
    """
    med, sd, _ = peer_stats_blocks(stack, cover, pixel_m, block_m, radius_m, min_n, sd_floor, skip_classes)
    return med, sd


def peer_stats_blocks(stack, cover, pixel_m, block_m=1000, radius_m=3000, min_n=8,
                      sd_floor=0.5, skip_classes=(0, 70, 80)):
    """Same as peer_stats, also returning the smoothed block values the web uses:
    blocks = {"size": b, "classes": {code: (med float32[T,bh,bw], sd float32[T,bh,bw])}}."""
    T, H, W = stack.shape
    b = max(1, int(round(block_m / pixel_m)))
    blocks = {"size": b, "classes": {}}
    win = 2 * int(round(radius_m / block_m)) + 1
    med = np.full(stack.shape, np.nan, np.float32)
    sd = np.full(stack.shape, np.nan, np.float32)
    rows, cols = np.indices((H, W))
    br, bc = rows // b, cols // b
    for c in np.unique(cover):
        if c in skip_classes:
            continue
        m = cover == c
        cm, cs = [], []
        for t in range(T):
            bm, bs, _ = _block_stats(stack[t], m & ~np.isnan(stack[t]), b, min_n)
            sm, ss = _nan_smooth(bm, win), np.maximum(_nan_smooth(bs, win), sd_floor)
            med[t][m] = sm[br[m], bc[m]]
            sd[t][m] = ss[br[m], bc[m]]
            cm.append(sm); cs.append(ss)
        blocks["classes"][int(c)] = (np.array(cm, np.float32), np.array(cs, np.float32))
    return med, sd, blocks


def zscore(stack: np.ndarray, med: np.ndarray, sd: np.ndarray) -> np.ndarray:
    with np.errstate(invalid="ignore", divide="ignore"):
        return ((stack - med) / sd).astype(np.float32)


def to_db(power: np.ndarray) -> np.ndarray:
    """Positive measured power only; zero, negative and nonfinite values are missing."""
    values=np.asarray(power,dtype=np.float64)
    out=np.full(values.shape,np.nan,dtype=np.float32)
    valid=np.isfinite(values)&(values>0)
    out[valid]=10*np.log10(values[valid])
    return out
