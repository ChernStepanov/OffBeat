import math
"""Численные регрессии, маски и запрет подмены одиночной пары скоростью."""
import copy
import json

import numpy as np
import pytest

from scripts import mexico_displacement as M


def pair(phase, component=None, ref='2026-01-01', sec='2026-01-13'):
    phase = np.asarray(phase, dtype=float)
    shape = phase.shape
    return {'receipt': {'reference_date': ref, 'secondary_date': sec,
                        'center_frequency_hz': 299792458/(4*np.pi)},
            'arrays': {'phase': phase, 'iono': np.zeros(shape), 'coherence': np.ones(shape),
                       'component': np.ones(shape, np.uint16) if component is None else np.array(component),
                       'mask': np.full(shape,11,np.uint32), 'iono_sd': np.zeros(shape)}}


def test_mask_rejects_invalid_values_and_preserves_interpolation_flag():
    a = pair(np.zeros((1,7)))['arrays']
    a['phase'][0,0] = np.inf
    a['component'][0,1] = 65535
    a['mask'][0,2] |= 1 << 8
    a['mask'][0,3] = 111  # водная маска
    a['iono_sd'][0,4] = -1
    a['coherence'][0,5] = 1.1
    a['mask'][0,6] |= 1 << 24
    np.testing.assert_array_equal(M.quality(a), [[False]*6+[True]])


def test_component_labels_may_change_but_independent_components_do_not_join():
    a = pair([[1,2,3]], [[1,1,2]])
    b = pair([[3,4,5]], [[7,7,8]])
    common, labels = M.connected_intersection([a,b])
    assert labels == [1,7]
    np.testing.assert_array_equal(common, [[True,True,False]])
    b['arrays']['coherence'][:] = .1
    common, labels = M.connected_intersection([a,b])
    assert not common.any() and labels == []


def test_chain_sign_units_fixed_reference_and_arbitrary_phase_offset():
    a = pair([[1.,3.]])
    b = pair([[5.,6.]], ref='2026-01-13',sec='2026-01-25')
    target = np.ones((1,2),bool); reference = np.array([[True,False]])
    values,_ = M.chain([a,b],target,reference)
    np.testing.assert_allclose(values[:,0], [[0,0],[0,-200],[0,-300]])
    shifted = copy.deepcopy([a,b]); shifted[0]['arrays']['phase'] += 100
    shifted[1]['arrays']['phase'] -= 60
    other,_ = M.chain(shifted,target,reference)
    np.testing.assert_allclose(other,values,atol=1e-10)


def test_chain_refuses_gaps_missing_reference_and_invalid_target():
    a = pair([[1.,3.]])
    target = np.ones((1,2),bool)
    with pytest.raises(ValueError, match='Опора'):
        M.chain([a],target,np.zeros((1,2),bool))
    b = pair([[1.,3.]],ref='2026-01-14',sec='2026-01-26')
    with pytest.raises(ValueError, match='Разрыв'):
        M.chain([a,b],target,target)
    a['arrays']['coherence'][0,1] = .5
    with pytest.raises(ValueError, match='маску'):
        M.chain([a],target,np.array([[True,False]]))


def test_single_pair_has_two_epochs_and_no_rate():
    values,_ = M.chain([pair([[1.,3.]])],np.ones((1,2),bool),np.ones((1,2),bool))
    assert len(values)==2
    from pipeline.insar import rate_cm_per_year
    assert np.isnan(rate_cm_per_year(['2026-01-01','2026-01-13'],values)).all()


def test_opera_does_not_extrapolate_or_reuse_one_observation_for_both_endpoints():
    dates=['2025-12-31','2026-01-06','2026-01-12']
    assert M.nearest_interval(dates,'2025-12-17','2025-12-29') == ([0,0],[14,2],False)
    assert M.nearest_interval(dates,'2026-01-05','2026-01-11') == ([1,2],[1,1],True)


@pytest.fixture(scope='module')
def actual():
    return M.calculate()


def test_saved_result_reproduces_all_values_and_input_hashes(actual):
    saved=json.loads((M.ROOT/M.OUT).read_text())
    assert _same(actual, saved)
    for path,digest in actual['input_sha256'].items():
        assert M.digest(M.ROOT/path)==digest


def test_measured_counts_and_decomposition_blockers(actual):
    a,d = [actual['directions'][k] for k in ['ascending','descending']]
    assert [p['valid'] for p in a['sampled_pairs']] == [357,208,0,0,438,465,431,340]
    assert [p['valid'] for p in d['sampled_pairs']] == [54,210,0,0,0,93,190,249]
    assert (a['selected_connected_points'],d['selected_connected_points'])==(275,68)
    assert a['all_pairs_common_points']==d['all_pairs_common_points']==0
    assert sum(len(v['all_contiguous_windows_at_least_3_pairs']) for v in [a,d])==42
    assert actual['shared_connected_points']==39
    assert actual['reference']['count']==38
    assert actual['decomposition']['overlap_days']==29
    assert actual['decomposition']['exact_common_epochs']==0
    assert not actual['decomposition']['available']
    assert not actual['ui']['velocity_available'] and not actual['ui']['vertical_east_available']
    assert not actual['reference']['stability_verified']
    assert actual['gnss']['selected_pairs_accepted']=={'ascending':2,'descending':0}


def test_reference_shift_independent_scalar_computation(actual):
    r=actual['directions']['ascending']
    # Восстановление одной точки напрямую из NPZ: не используем chain().
    index = actual['reference']['indices'][0]
    expected = 0.
    ref=np.array(actual['reference']['indices'])
    for p in r['sampled_pairs'][-4:]:
        receipt=json.loads((M.ROOT/p['receipt']).read_text())
        with np.load(M.ROOT/receipt['subset_path']) as a:
            phase=(a['phase']-a['iono']).ravel()
            scale=-299792458/receipt['center_frequency_hz']/(4*np.pi)*100
            expected += (phase[index]-np.median(phase[ref]))*scale
    assert r['diagnostic_los_cm'][-1][index] == pytest.approx(expected)
    assert r['endpoint_reference_shift_range_cm']==pytest.approx(.2574803347)
    assert actual['directions']['descending']['endpoint_reference_shift_range_cm']==pytest.approx(.3462077515)


def test_opera_check_has_only_actual_dates_and_no_physical_agreement_claim(actual):
    assert len(actual['opera']['dates'])==15
    assert actual['opera']['all_dates_finite_points']==1018
    assert not actual['opera']['independent_validation']
    assert not actual['opera']['raw_masks_components_geometry_saved']
    a,d = [actual['directions'][k]['opera_interval_check'] for k in ['ascending','descending']]
    assert not a[0]['within_3_days']
    assert [p['common_points'] for p in a[1:]]==[273]*3
    assert [p['common_points'] for p in d]==[67]*3
    assert all(p['offset_days']==[2,2] for p in a[1:])
    assert all(p['offset_days']==[1,1] for p in d)

def _same(a, b):
    """Equal up to float noise between numpy/Python builds; recorded tool versions are not results."""
    if isinstance(a, dict) and isinstance(b, dict):
        keys = (set(a) | set(b)) - {'software'}
        return all(k in a and k in b and _same(a[k], b[k]) for k in keys)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(_same(x, y) for x, y in zip(a, b))
    if isinstance(a, float) or isinstance(b, float):
        return isinstance(a, (int, float)) and isinstance(b, (int, float)) and math.isclose(a, b, rel_tol=1e-6, abs_tol=1e-9)
    return a == b
