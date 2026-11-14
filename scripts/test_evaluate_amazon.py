"""Положительные примеры выбираются без знания ответа детектора и без утечки даты GLAD."""
import json
from pathlib import Path

from shapely.geometry import box,mapping

import evaluate_amazon as evaluation


def test_selection_ignores_detector_output_and_deduplicates_samples():
    site={'dates':['2026-07-18','2026-09-28'],'pixels':[
        {'id':'miss','lon':0.5,'lat':0.5,'style':None},
        {'id':'hit','lon':0.6,'lat':0.6,'style':'drop'}]}
    f={'geometry':mapping(box(0,0,1,1)),'properties':{'date':'2026-08-24','confidence':3}}
    selected,_=evaluation.selected_samples(site,[f,f])
    assert {item['pixel']['id'] for item in selected}=={'hit','miss'}
    assert all(item['alert_dates']==['2026-08-24'] for item in selected)


def test_unconfirmed_or_out_of_period_is_not_positive():
    site={'dates':['2026-07-18','2026-09-28'],'pixels':[{'id':'p','lon':.5,'lat':.5,'style':'drop'}]}
    features=[{'geometry':mapping(box(0,0,1,1)),'properties':{'date':day,'confidence':confidence}}
              for day,confidence in [('2026-08-24',2),('2026-05-20',3)]]
    selected,excluded=evaluation.selected_samples(site,features)
    assert not selected and excluded['alert_outside_radar_period']==1


def test_delayed_alert_does_not_create_a_false_pre_event_baseline():
    dates=['2026-07-18','2026-08-11','2026-08-23','2026-09-04','2026-09-16','2026-09-28']
    real=evaluation.baseline(dates,'2026-07-05','2026-08-04')
    assert real['before']==[] and real['max_possible_before']==['2026-07-18']
    assert not real['eligible']
    # Подмена интервала по RGB датой GLAD дала бы ошибочную пригодность.
    misleading=evaluation.baseline(dates,'2026-08-23','2026-08-24')
    assert misleading['eligible']


def test_real_detections_and_sources_are_reproducible():
    root=Path(__file__).resolve().parents[1]
    result=json.loads((evaluation.OUT/'results.json').read_text())
    site=json.loads((root/'data/amazon.json').read_text())
    features=json.loads((evaluation.audit.DIRECTORY/'alerts.geojson').read_text())['features']
    selected,_=evaluation.selected_samples(site,features)
    assert {r['id'] for r in result['samples']}=={item['pixel']['id'] for item in selected}
    for item in selected:
        row=next(r for r in result['samples'] if r['id']==item['pixel']['id'])
        assert row['detector']==evaluation.score(item['pixel'],site['dates'])
    assert result['summary']['samples']==5
    assert result['summary']['verified_forest_loss_samples']==1
    assert result['summary']['eligible_positive_samples']==0
    assert result['summary']['local_recall'] is None
    assert result['review_current']
    assert result['classifier_sha256']==evaluation.audit.digest(root/'pipeline/classify.py')
    assert result['deter']['sha256']==evaluation.audit.digest(evaluation.OUT/'deter-nearby.geojson')
    for key,path in [('site',root/'data/amazon.json'),('alerts',evaluation.audit.DIRECTORY/'alerts.geojson'),
                     ('optical',root/'data/amazon/optical/index.json'),('extra',evaluation.OUT/'optical.json')]:
        assert result['input_sha256'][key]==evaluation.audit.digest(path)
    extra=json.loads((evaluation.OUT/'optical.json').read_text())
    extra_files={scene['render']['file'] for scene in extra['scenes']}
    for row in result['samples']:
        for rgb in row['rgb']:
            directory=evaluation.OUT if rgb['file'] in extra_files else root/'data/amazon/optical'
            assert rgb['png_sha256']==evaluation.audit.digest(directory/rgb['file'])
    for receipt in extra['scl'].values():
        assert receipt['sha256']==evaluation.audit.digest(evaluation.OUT/receipt['path'])
