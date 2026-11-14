"""Проверки пропусков, исключения себя и воспроизводимости демо-анализа."""
import copy
import json
from pathlib import Path

import numpy as np
import pytest

from pipeline.classify import classify, CODE
from pipeline.peers import sparse_peer_stats, zscore
from pipeline.preview import analyze_site


def test_sparse_peers_exclude_self_other_classes_and_distant_samples():
    values = np.array([[100, 1, 2, 3, 4, 5, 200, 300]], dtype=float)
    cover = np.array([10, 10, 10, 10, 10, 10, 30, 10])
    east = np.array([0, 1, 2, 3, 4, 5, 6, 2000])
    med, sd, counts = sparse_peer_stats(values, cover, east, np.zeros(8), min_n=5)
    assert counts[0, 0] == 5
    assert med[0, 0] == 3
    assert sd[0, 0] == pytest.approx(1.4826)
    assert np.isnan(med[0, 6:]).all()
    values[0, 1] = np.nan
    med, sd, counts = sparse_peer_stats(values, cover, east, np.zeros(8), min_n=5)
    assert counts[0, 0] == 4
    assert np.isnan(med[0, 0])


def test_zero_spread_and_missing_latest_score_stay_unavailable():
    stack = np.ones((6, 12))
    med, sd, _ = sparse_peer_stats(stack, np.full(12, 10), np.arange(12), np.zeros(12))
    assert np.isfinite(med).all()
    assert np.isnan(sd).all()
    assert np.isnan(zscore(stack, med, sd)).all()
    z = np.zeros((6, 1, 1)); z[-1] = np.nan
    result = classify(z, z)
    assert np.isnan(result['z']).all()
    assert not result['style'].any()


def test_hh_jump_requires_measured_hv_on_both_sides():
    hh = np.array([0, 0, 5, 5, 5, 5], dtype=float).reshape(6, 1, 1)
    missing = np.full_like(hh, np.nan)
    assert not classify(hh, missing)['style'].any()
    hv = np.zeros_like(hh); hv[:2] = np.nan
    assert not classify(hh, hv)['style'].any()
    result = classify(hh, np.zeros_like(hh))
    assert result['style'][0, 0] == CODE['flood']
    assert result['since'][0, 0] == 2


@pytest.mark.parametrize('name', ['mexico', 'amazon', 'venezuela'])
def test_real_analysis_reproduces_export_and_preserves_measurements(name):
    path = Path(__file__).resolve().parents[2] / 'data' / f'{name}.json'
    site = json.loads(path.read_text())
    before = copy.deepcopy(site)
    analyze_site(site)
    assert site == before
    for pixel in site['pixels']:
        if pixel['z'] is not None:
            channel = 'hh' if pixel['style'] == 'flood' else 'hv'
            assert pixel['peer_counts'][channel][-1] >= 10
    # Повторный запуск после изменения реального ряда не должен оставлять старые оценки.
    pixel = site['pixels'][0]
    pixel['hv'] = [None] * len(site['dates'])
    pixel['hh'] = [None] * len(site['dates'])
    analyze_site(site)
    assert pixel['z'] is None and pixel['style'] is None and pixel['since'] is None
