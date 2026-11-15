import hashlib
import json

import numpy as np

from scripts import findings as F

ROOT = F.ROOT


def load(site):
    return json.loads((ROOT / 'data' / f'{site}.json').read_text())


def test_join_count_counts_rook_neighbours_only():
    mask = np.array([[1, 1, 0], [0, 0, 0], [0, 1, 1]], dtype=bool)
    assert F.joins(mask) == 2
    assert F.joins(np.eye(3, dtype=bool)) == 0  # diagonal neighbours do not count


def test_repeat_pairs_skip_gaps_longer_than_the_repeat_cycle():
    assert F.repeat_pairs(['2026-07-09', '2026-07-21', '2026-08-14', '2026-08-26']) == [0, 2]


def test_every_published_site_passes_the_plausibility_gate():
    published = json.loads((ROOT / 'data' / 'findings.json').read_text())
    assert all(site['quality']['plausible'] for site in published['sites'].values())


def test_published_findings_match_current_data():
    published = json.loads((ROOT / 'data' / 'findings.json').read_text())
    for site, digest in published['inputs_sha256'].items():
        assert hashlib.sha256((ROOT / 'data' / f'{site}.json').read_bytes()).hexdigest() == digest, f'rerun scripts/findings.py: {site} changed'
    strengths = {f['strength'] for f in published['findings']}
    assert strengths <= {'strong', 'suggestive', 'none', 'issue'}
    for f in published['findings']:
        assert f['en'] and f['ru'] and f['how_en'] and f['how_ru']
        for index in f.get('samples', []):
            assert 0 <= index < len(load(f['site'])['pixels'])


def test_trend_candidates_are_fdr_controlled():
    published = json.loads((ROOT / 'data' / 'findings.json').read_text())
    trends = published['sites']['mexico']['trends']
    assert trends['tests'] > 1000
    assert all(h['q'] < trends['alpha'] for h in trends['strongest'])


def test_opera_rate_is_compared_with_independent_gnss():
    v = F.opera_vs_gnss()
    assert v['station'] == 'MMX1' and v['distance_m'] < 50
    lo, hi = v['gnss_expected_los_cm_per_year']
    assert lo <= hi < 0                      # projected subsidence is away from the satellite
    assert v['gnss_up_se'] < abs(v['gnss_up_cm_per_year']) / 5


def test_gnss_tie_uses_a_neighbourhood_anchor_and_keeps_every_sample_slot():
    tie = F.opera_tied()
    assert tie['anchor_samples'] >= 10
    assert len(tie['tied_los_cm_per_year_mid_incidence']) == 1024
    assert len(tie['fastest']) == 6


def test_findings_answer_the_challenge_questions():
    published = json.loads((ROOT / 'data' / 'findings.json').read_text())
    ids = {f['id'] for f in published['findings']}
    assert 'polarisation' in ids
    for f in published['findings']:
        if f['strength'] in ('strong', 'suggestive'):
            assert f.get('drivers_en') and f.get('drivers_ru'), f['id']
