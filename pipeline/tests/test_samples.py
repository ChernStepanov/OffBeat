import copy
import json
from pathlib import Path
import numpy as np
from pipeline.classify import classify
from pipeline.insar import chain_pairs
from pipeline.peers import to_db
from scripts.analyze_samples import analyze
from scripts.optical import select_candidates, calibration_for

ROOT=Path(__file__).resolve().parents[2]


def test_nonpositive_power_is_missing_not_a_clipped_fake_measurement():
    actual=to_db(np.array([1,.1,0,-1,np.nan,np.inf,1e-8]))
    assert np.allclose(actual[[0,1,6]],[0,-10,-80])
    assert np.isnan(actual[2:6]).all()


def test_missing_latest_measurement_is_not_normal_zero_or_classified():
    values=np.zeros((6,1,1));values[-1]=np.nan
    result=classify(values,values)
    assert np.isnan(result['z'][0,0])
    assert result['style'][0,0]==0


def test_chain_without_reference_stops_instead_of_assuming_zero_offset():
    pair={'ref':'2026-01-01','sec':'2026-01-13','los_m':np.ones((2,2)),
        'coherence':np.ones((2,2)),'conncomp':np.ones((2,2))}
    _,disp=chain_pairs([pair],ref_mask=np.zeros((2,2),bool))
    assert np.isnan(disp[1]).all()


def test_real_sample_recalculation_is_reproducible_and_preserves_raw_measurements():
    site=json.loads((ROOT/'data/amazon.json').read_text())
    original=copy.deepcopy(site)
    report=analyze(site)
    assert report['shape_counts']==json.loads((ROOT/'data/analysis/amazon.json').read_text())['shape_counts']
    for before,after in zip(original['pixels'],site['pixels']):
        for key in ['hh','hv','disp','lat','lon','cover']:
            assert before[key]==after[key]
        assert before['peer']==after['peer']
        assert before['z']==after['z']


def test_optical_date_window_is_inclusive_and_does_not_choose_old_context():
    items=[{'id':d,'properties':{'datetime':d+'T00:00:00Z','eo:cloud_cover':c}}
           for d,c in [('2026-01-01',0),('2026-01-16',5),('2026-01-17',0),('2026-02-01',0)]]
    chosen=select_candidates(items,'2026-01-16')
    assert [i['id'] for i in chosen]==['2026-01-17','2026-01-01','2026-01-16']


def test_sentinel_offset_is_not_applied_twice():
    asset={'raster:bands':[{'scale':.0001,'offset':-.1}]}
    assert calibration_for(asset,{'earthsearch:boa_offset_applied':True})==(.0001,0)
    assert calibration_for(asset,{'earthsearch:boa_offset_applied':False})==(.0001,-.1)
    assert calibration_for({}, {'s2:processing_baseline':'05.12'})==(.0001,-.1)


def test_optical_indexes_have_real_images_matching_bounds_and_hashes():
    import hashlib
    from PIL import Image
    for identifier in ['mexico','amazon','venezuela']:
        site=json.loads((ROOT/f'data/{identifier}.json').read_text())
        index=json.loads((ROOT/f'data/{identifier}/optical/index.json').read_text())
        assert [e['nisar_date'] for e in index['entries']]==site['dates']
        for entry in index['entries']:
            if entry['status']!='ready':
                assert 'path' not in entry
                continue
            assert entry['bounds']==site['grid']['bbox']
            assert abs((__import__('datetime').date.fromisoformat(entry['date'])-__import__('datetime').date.fromisoformat(entry['nisar_date'])).days)<=15
            path=ROOT/entry['path']
            assert hashlib.sha256(path.read_bytes()).hexdigest()==entry['sha256']
            pixels=np.array(Image.open(path))
            assert pixels.shape==(256,256,4)
            assert np.median(pixels[:,:,:3][pixels[:,:,3]>0])>15
