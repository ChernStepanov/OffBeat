"""Совпадение по геометрии и времени, маски облаков и актуальность визуального разбора."""
import json
from pathlib import Path

import numpy as np
from shapely.geometry import box, mapping

import validate_amazon as audit


def feature(lon,lat,stamp,confidence=3):
    return dict(type='Feature',geometry=mapping(box(lon-.00005,lat-.00005,lon+.00005,lat+.00005)),
                properties=dict(source='GLAD-L',date=stamp,confidence=confidence))


def test_overlap_needs_matching_time_and_confirmed_confidence():
    pixel=dict(lon=-49.28,lat=-4.78,since='2026-09-16')
    features=[feature(-49.28,-4.78,'2026-01-01'),feature(-49.28,-4.78,'2026-09-17',2)]
    assert audit.match_alerts(pixel,features)[0]==[]
    features.append(feature(-49.28,-4.78,'2026-09-17'))
    matches,_=audit.match_alerts(pixel,features)
    assert len(matches)==1 and matches[0]['point_overlap']
    assert matches[0]['delta_days']==1


def test_nearby_polygon_is_not_point_confirmation():
    pixel=dict(lon=-49.28,lat=-4.78,since='2026-09-16')
    matches,nearest=audit.match_alerts(pixel,[feature(-49.279,-4.78,'2026-09-17')])
    assert not matches and nearest['GLAD-L']['distance_m']>30


def test_polygon_hole_is_not_overlap():
    pixel=dict(lon=-49.28,lat=-4.78,since='2026-09-16')
    outer=box(-49.29,-4.79,-49.27,-4.77)
    hole=box(-49.281,-4.781,-49.279,-4.779)
    shape=outer.difference(hole)
    f=dict(type='Feature',geometry=mapping(shape),properties=dict(source='DETER',date='2026-09-17'))
    assert not audit.match_alerts(pixel,[f])[0]


def test_stale_review_does_not_carry_over_verdict():
    output={'input_sha256':{'site':'new'},'candidates':[{'id':'p','alert_matches':[]}]}
    reviews={'input_sha256':{'site':'old'},'candidates':{'p':{'verdict':'confirmed_forest_loss'}}}
    audit.attach_reviews(output,reviews)
    assert output['review_status']=='needs_review'
    assert output['candidates'][0]['review']['verdict']=='unreviewed'


def test_scl_shadow_is_not_clear_rgb():
    root=Path(__file__).resolve().parents[1]
    site=json.loads((root/'data/amazon.json').read_text())
    result=json.loads((root/'data/amazon/validation.json').read_text())
    row=next(r for r in result['candidates'] if r['id']=='AMA r21 c0')
    last=next(r for r in row['rgb'] if r['date']=='2026-09-21')
    assert last['scl']==3 and not last['clear_land']
    assert row['clear_after']=='2026-09-03'


def test_saved_audit_covers_all_candidates_and_verified_inputs():
    root=Path(__file__).resolve().parents[1]
    site=json.loads((root/'data/amazon.json').read_text())
    result=json.loads((root/'data/amazon/validation.json').read_text())
    assert {p['id'] for p in site['pixels'] if p['style']=='drop'}=={r['id'] for r in result['candidates']}
    assert result['summary']['n_candidates']==6
    assert result['review_status']=='current'
    for key,path in [('site','data/amazon.json'),('optical','data/amazon/optical/index.json'),('sources','data/amazon/validation/sources.json')]:
        assert result['input_sha256'][key]==audit.digest(root/path)
    sources=json.loads((root/'data/amazon/validation/sources.json').read_text())
    for item in [sources['deter'],sources['glad'],*sources['scl'].values()]:
        assert item['sha256']==audit.digest(audit.DIRECTORY/item['path'])
    features=json.loads((audit.DIRECTORY/'alerts.geojson').read_text())['features']
    optical=json.loads((root/'data/amazon/optical/index.json').read_text())
    scenes={row['scene']['scene_id']:row['scene'] for row in optical['entries']}
    pixels={pixel['id']:pixel for pixel in site['pixels']}
    for candidate in result['candidates']:
        matches,_=audit.match_alerts(candidate,features)
        assert matches==candidate['alert_matches']
        for rgb in candidate['rgb']:
            assert rgb['png_sha256']==audit.digest(root/'data/amazon/optical'/rgb['file'])
            assert rgb==audit.pixel_rgb(pixels[candidate['id']],scenes[rgb['scene_id']],sources['scl'][rgb['scene_id']])


def test_zero_glad_and_invalid_codes_are_not_alerts(monkeypatch,tmp_path):
    monkeypatch.setattr(audit,'DIRECTORY',tmp_path)
    (tmp_path/'deter.json').write_text(json.dumps(dict(type='FeatureCollection',features=[])))
    np.savez_compressed(tmp_path/'glad.npz',alert=np.array([[0,1,255,2,3]],np.uint8),alertDate=np.array([[1,1,1,260,260]]))
    receipts=dict(as_of='2026-11-14',deter=dict(path='deter.json'),glad=dict(path='glad.npz',year=2026,bands={'alert':{'transform':[.00025,0,-49.28,0,-.00025,-4.78]}}))
    features=audit.alert_features(receipts)
    assert [f['properties']['confidence'] for f in features]==[2,3]
