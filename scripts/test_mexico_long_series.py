"""Полнота догрузки, граф дат и ограничения на опору и скорость."""
import copy
import json
from datetime import date,timedelta

import numpy as np
import pytest

from scripts import mexico_displacement as M
from scripts import mexico_long_series as L
from scripts.test_mexico_displacement import pair


def test_windows_do_not_bridge_an_absent_edge():
    a=pair([[0.,0.,0.]])
    b=pair([[0.,0.,0.]],ref='2026-01-25',sec='2026-02-06')
    rows=L.windows([a,b])
    assert len(rows)==2 and all(w['pairs']==1 for w in rows)
    assert L.longest(rows,4) is None


def test_zero_quality_pair_prevents_a_complete_reference():
    a=pair([[0.,0.,0.]])
    b=pair([[0.,0.,0.]],ref='2026-01-13',sec='2026-01-25')
    b['arrays']['iono_sd'][:]=2
    rows=L.windows([a,b])
    full=next(w for w in rows if w['pairs']==2)
    assert full['common_points']==0
    assert L.longest(rows,1)['pairs']==1


def test_coherence_does_not_establish_external_reference_stability():
    a=pair([[0.,1.,2.]])
    a['receipt']['grid']={}
    w=L.windows([a])[0]
    result=L.diagnose_reference([a],w)
    assert result['available']
    assert not result['stable_reference_verified']
    assert result['external_immobile_control_points']==0
    assert not result['relative_rate_fit']['available']


def test_rate_fit_uses_only_real_secondary_epochs_and_known_time_units():
    pairs=[];start=date(2026,1,1)
    for i in range(9):
        p=pair([[-1.,0.,1.]],ref=(start+timedelta(days=12*i)).isoformat(),
               sec=(start+timedelta(days=12*(i+1))).isoformat())
        p['receipt']['grid']={};pairs.append(p)
    eight=L.diagnose_reference(pairs[:8],L.longest(L.windows(pairs[:8]),1))
    assert not eight['relative_rate_fit']['available']  # восемь вторичных эпох охватывают 84 дня
    nine=L.diagnose_reference(pairs,L.longest(L.windows(pairs),1))
    fit=nine['relative_rate_fit']
    assert fit['real_secondary_epochs']==9 and fit['fit_span_days']==96
    np.testing.assert_allclose(fit['slope_cm_per_year']['p05_p50_p95'],[-2739.375,0.,2739.375])
    assert not fit['validated']


@pytest.fixture(scope='module')
def full():
    return L.calculate()


def test_all_expected_granules_have_hash_verified_windows(full):
    assert full['catalogue_complete']
    assert full['downloaded_additional_pairs']==38
    assert full['directions']['ascending']['count']==28
    assert full['directions']['descending']['count']==26
    assert sum(v['count'] for v in full['directions'].values())==54
    a,d=[full['directions'][k] for k in ['ascending','descending']]
    assert [a['zero_quality_pairs'],d['zero_quality_pairs']]==[5,8]
    assert [a['longest_by_minimum_points']['10']['days'],d['longest_by_minimum_points']['10']['days']]==[168,156]
    assert [a['longest_by_minimum_points']['10']['common_points'],d['longest_by_minimum_points']['10']['common_points']]==[20,20]
    assert full['decomposition']['long_window_combinations_with_90_day_overlap']==190
    assert full['decomposition']['maximum_shared_points_in_any_long_combination']==0
    for path,digest in full['input_sha256'].items():assert M.digest(M.ROOT/path)==digest


def test_missing_expected_granule_stops_the_analysis(monkeypatch):
    original=M.read
    def extra(path,hashes):
        result=original(path,hashes)
        if str(path)==M.CATALOGUE:
            result=copy.deepcopy(result)
            result['granules'].append({'id':'MISSING','direction':'ascending'})
        return result
    monkeypatch.setattr(M,'read',extra)
    with pytest.raises(ValueError,match='Не прочитаны 1'):L.load_all()


def test_reproducible_full_result_and_no_unvalidated_velocity(full):
    assert full==json.loads((M.ROOT/L.OUTPUT).read_text())
    assert not full['ui']['velocity_available'] and not full['ui']['vertical_east_available']
    assert not full['opera']['independent_validation']
    assert full['opera']['latest_catalogue_secondary']=='20260325'
    assert full['opera']['catalogue_latest_secondary_all_frames']=='20260325'
    for v in full['directions'].values():
        assert not v['reference_diagnosis']['stable_reference_verified']
        refs=v['reference_diagnosis']['reference_indices']
        assert len({tuple(indices) for indices in refs.values()})==len(refs)>1
        fit=v['reference_diagnosis']['relative_rate_fit']
        assert fit['available'] and fit['fit_span_days']>=90 and not fit['validated']


def test_local_token_is_ignored_by_git():
    import subprocess
    assert subprocess.run(['git','check-ignore','-q','.earthdata_token'],cwd=M.ROOT).returncode==0
