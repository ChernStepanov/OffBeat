"""Synthetic checks for peers, classify and insar: each planted change must come back with its style and date."""
import numpy as np

from pipeline.peers import peer_stats, zscore
from pipeline.classify import classify, CODE
from pipeline.insar import chain_pairs, rate_cm_per_year, decompose, damage_proxy

rng = np.random.default_rng(0)
T, H, W = 20, 60, 60


def scene():
    cover = np.full((H, W), 10, np.int16)
    cover[:, 40:] = 40                     # cropland on the right
    season = np.sin(np.linspace(0, 2 * np.pi, T))[:, None, None]
    hh = np.where(cover == 10, -7.0, -9.5) + 1.5 * season + rng.normal(0, 0.5, (T, H, W))
    hv = np.where(cover == 10, -12.5, -16.5) + 1.2 * season + rng.normal(0, 0.5, (T, H, W))
    return cover, hh.astype(np.float32), hv.astype(np.float32)


def test_peers_remove_season_and_class():
    cover, hh, hv = scene()
    med, sd = peer_stats(hv, cover, pixel_m=100)
    z = zscore(hv, med, sd)
    assert np.nanstd(z) < 1.6                      # the shared season is gone
    assert abs(np.nanmean(z[:, :, :40]) - np.nanmean(z[:, :, 40:])) < 0.3   # so is the class offset


def test_drop_and_flood_are_found_with_their_dates():
    cover, hh, hv = scene()
    hv[12:, 10:14, 10:14] -= 6                     # clearing from date 12
    hh[8:, 30:33, 50:53] += 6                      # flooding in cropland from date 8
    mh, sh = peer_stats(hh, cover, 100)
    mv, sv = peer_stats(hv, cover, 100)
    r = classify(zscore(hh, mh, sh), zscore(hv, mv, sv))
    assert (r["style"][10:14, 10:14] == CODE["drop"]).all()
    assert (r["since"][10:14, 10:14] == 12).all()
    assert (r["style"][30:33, 50:53] == CODE["flood"]).all()
    assert (r["since"][30:33, 50:53] == 8).all()
    assert (r["style"] != 0).mean() < 0.02         # few false alarms elsewhere


def test_step_and_drift_from_displacement():
    cover, hh, hv = scene()
    zd = rng.normal(0, 0.6, (T, H, W)).astype(np.float32)
    zd[10:, 0:5, 0:5] += 6                          # step at date 10
    zd[:, 50:55, 0:5] += np.linspace(0, 7, T)[:, None, None]   # steady drift
    mh, sh = peer_stats(hh, cover, 100)
    mv, sv = peer_stats(hv, cover, 100)
    r = classify(zscore(hh, mh, sh), zscore(hv, mv, sv), zd)
    assert (r["style"][0:5, 0:5] == CODE["step"]).mean() > 0.9
    assert (r["since"][0:5, 0:5] == 10).mean() > 0.9
    assert (r["style"][50:55, 0:5] == CODE["drift"]).mean() > 0.9


def pair(ref, sec, los, coh=0.8):
    return {"ref": ref, "sec": sec, "los_m": los.astype(np.float32),
            "coherence": np.full(los.shape, coh, np.float32), "conncomp": np.ones(los.shape, np.int32)}


def test_chain_rate_and_decompose():
    dates = [f"2026-{m:02d}-01" for m in range(1, 13)]
    true_up, true_east = -0.30, 0.02                # m/yr: sinking 30 cm/yr, 2 cm/yr east
    enu_a = np.stack([np.full((H, W), v) for v in (-0.6, -0.1, 0.79)])   # looking east from the west
    enu_d = np.stack([np.full((H, W), v) for v in (0.6, -0.1, 0.79)])
    out = {}
    for name, enu in (("a", enu_a), ("d", enu_d)):
        pairs = []
        for d0, d1 in zip(dates, dates[1:]):
            dt = (np.datetime64(d1) - np.datetime64(d0)).astype(int) / 365.25
            los = (true_east * enu[0] + true_up * enu[2]) * dt * np.ones((H, W))
            los[:5, :5] = 0                         # a stable reference corner
            pairs.append(pair(d0, d1, los))
        ref = np.zeros((H, W), bool); ref[:5, :5] = True
        ds, cm = chain_pairs(pairs, ref_mask=ref)
        out[name] = rate_cm_per_year(ds, cm)
    east, up = decompose(out["a"], enu_a, out["d"], enu_d)
    assert abs(np.nanmedian(up[10:, 10:]) - true_up * 100) < 1.0
    assert abs(np.nanmedian(east[10:, 10:]) - true_east * 100) < 1.0


def test_damage_proxy_flags_only_damaged_buildings():
    cover = np.full((H, W), 50, np.int16)
    cover[:, :10] = 10                              # forest strip, decorrelates on its own
    pre = [pair("a", "b", np.zeros((H, W)), 0.85), pair("b", "c", np.zeros((H, W)), 0.83)]
    for p in pre:
        p["coherence"] = (p["coherence"] + rng.normal(0, 0.03, (H, W))).astype(np.float32)
        p["coherence"][:, :10] = 0.3
    co = pair("c", "d", np.zeros((H, W)), 0.8)
    co["coherence"] = (co["coherence"] + rng.normal(0, 0.03, (H, W))).astype(np.float32)
    co["coherence"][30:36, 30:36] = 0.25           # collapsed block
    z = damage_proxy(pre, co, cover)
    assert np.isnan(z[:, :10]).all()
    assert (z[30:36, 30:36] > 5).all()
    assert (np.nan_to_num(z) > 3).mean() < 0.02
