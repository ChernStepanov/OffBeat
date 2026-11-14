"""Расчёт соседей и предварительных форм изменения в измеренном JSON демо."""
from collections import Counter

import numpy as np
from pyproj import Transformer

from .classify import classify, STYLES
from .peers import sparse_peer_stats, zscore


def analyze_site(site):
    """Обновить производные поля, сохранив исходные измерения и ось GUNW."""
    pixels = site['pixels']
    n = site['grid']['n']
    dates = site['dates']
    if len(pixels) != n * n or not dates or dates != sorted(set(dates)):
        raise ValueError('Некорректная сетка или даты')
    epsg = site['provenance']['inputs'][0]['grid']['epsg']
    east, north = Transformer.from_crs(4326, epsg, always_xy=True).transform(
        [p['lon'] for p in pixels], [p['lat'] for p in pixels])
    cover = np.array([p['cover'] or 0 for p in pixels])
    scores = {}
    for channel in ('hh', 'hv'):
        stack = np.array([p[channel] for p in pixels], dtype=float).T
        if stack.shape != (len(dates), len(pixels)):
            raise ValueError('Длина измерений не совпадает с датами')
        med, sd, counts = sparse_peer_stats(stack, cover, np.array(east), np.array(north))
        scores[channel] = zscore(stack, med, sd).reshape(len(dates), n, n)
        for i, pixel in enumerate(pixels):
            pixel.setdefault('peer', {})[channel + '_med'] = [_number(v) for v in med[:, i]]
            pixel['peer'][channel + '_sd'] = [_number(v) for v in sd[:, i]]
            pixel.setdefault('peer_counts', {})[channel] = counts[:, i].tolist()
    result = classify(scores['hh'], scores['hv'])
    for i, pixel in enumerate(pixels):
        code = int(result['style'].ravel()[i])
        since = int(result['since'].ravel()[i])
        pixel['z'] = _number(result['z'].ravel()[i])
        pixel['style'] = STYLES[code]
        pixel['since'] = dates[since] if since >= 0 else None
        pixel['peers'] = pixel['peer_counts']['hv'][-1] if pixel['cover'] else None
    summary = dict(
        version=1, radius_m=1000, min_peers=10, spread='1.4826*MAD; no floor',
        exclude_self=True, skip_classes=[0, 70, 80], threshold=2.5, min_segment_samples=2,
        latest_scores=sum(p['z'] is not None for p in pixels),
        styles=dict(Counter(p['style'] for p in pixels if p['style'])),
        interpretation='Preliminary backscatter shapes, not verified clearing, flooding or ground motion',
    )
    site['provenance']['analysis'] = summary
    site['provenance']['limitations'] = [
        'Sparse nearest-native samples, no area aggregation; preliminary backscatter shapes, no verified causes or patch area'
        if note == 'Sparse nearest-native samples, no area aggregation, no anomaly classification or patch area'
        else note for note in site['provenance'].get('limitations', [])
    ]
    site['status'] = 'measured_analysis'
    site['message'] = (
        f"Measured HH/HV on {len(dates)} dates; preliminary same-class peer scores and change shapes. "
        "Change causes are unverified; GUNW remains the original pair. Sparse samples do not measure patch area."
    )
    return summary


def _number(value):
    return round(float(value), 5) if np.isfinite(value) else None
