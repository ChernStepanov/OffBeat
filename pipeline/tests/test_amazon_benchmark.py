import copy
import json
import pytest
from pipeline.amazon_benchmark import ROOT, metrics, rank, validate_protocol


def test_unknown_is_not_negative():
    result = metrics([{'label': 'confirmed'}, {'label': 'unknown'}, {'label': 'refuted'}], 3)
    assert result['precision_at_k'] is None
    assert result['precision_bounds'] == [1 / 3, 2 / 3]
    assert result['false_discoveries'] == 1


def test_empty_test_is_not_zero_precision():
    assert metrics([], 10)['precision_at_k'] is None
    assert metrics([], 10)['precision_bounds'] is None


def test_group_leakage_rejected():
    site = {'pixels': [{'id': 'a'}, {'id': 'b'}]}
    p = {'ids': ['a', 'b'], 'assignments': [
        {'id': 'a', 'event_group': 'same', 'split': 'development'},
        {'id': 'b', 'event_group': 'same', 'split': 'test'}]}
    with pytest.raises(ValueError, match='Event group'):
        validate_protocol(p, site)


def test_future_signal_does_not_change_weather_fit():
    folder = ROOT / 'data/benchmark/amazon-v1'
    protocol = json.loads((folder / 'protocol.json').read_text())
    site = json.loads((ROOT / 'data/amazon.json').read_text())
    weather = json.loads((ROOT / 'data/analysis/amazon-era5.json').read_text())
    original = rank(site, weather, protocol)
    changed = copy.deepcopy(site)
    for p in changed['pixels']:
        p['hv'][3:] = [v + 20 if v is not None else None for v in p['hv'][3:]]
    later = rank(changed, weather, protocol)
    assert [r['rain_slope_db_per_10mm'] for r in original] == [r['rain_slope_db_per_10mm'] for r in later]
