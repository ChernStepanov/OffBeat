"""Проверка неизменённого детектора на подтверждённых GLAD-пикселях.

python scripts/evaluate_amazon.py --refresh-optical
Повтор без флага использует сохранённые RGB/SCL и радарные ряды.
"""
import argparse
from collections import Counter
from datetime import date
import json
from pathlib import Path
import sys

import numpy as np
import rasterio
from rasterio.warp import reproject, Resampling
import requests
from shapely.geometry import shape, Point

from crop_optical import render_scene
from optical import scene_record, fetch_scenes
import validate_amazon as audit

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'data/amazon/positive-eval'
sys.path.insert(0,str(ROOT))
from pipeline.classify import classify, change_point


def selected_samples(site,features):
    """Все точные пересечения в период радара, без отбора по выходу детектора."""
    candidates={};excluded=Counter()
    start,end=site['dates'][0],site['dates'][-1]
    for feature in features:
        prop=feature['properties']
        if prop.get('confidence')!=3:continue
        if not start<=prop['date']<=end:
            excluded['alert_outside_radar_period']+=1;continue
        polygon=shape(feature['geometry']);found=False
        for pixel in site['pixels']:
            if polygon.covers(Point(pixel['lon'],pixel['lat'])):
                found=True
                candidates.setdefault(pixel['id'],dict(pixel=pixel,alert_dates=set()))['alert_dates'].add(prop['date'])
        if not found:excluded['no_exact_preview_sample']+=1
    result=[]
    for item in candidates.values():
        item['alert_dates']=sorted(item['alert_dates']);result.append(item)
    return sorted(result,key=lambda row:row['pixel']['id']),dict(excluded)


def acquire_optical(site):
    bbox=[site['grid']['bbox'][k] for k in ('w','s','e','n')];session=requests.Session()
    items,query,pages=fetch_scenes(session,bbox,[date(2026,7,3),date(2026,7,24)],0)
    wanted={'2026-07-05','2026-07-13','2026-07-18','2026-07-23'}
    scenes=[];receipts={}
    with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN='EMPTY_DIR',CPL_VSIL_CURL_ALLOWED_EXTENSIONS='.tif',GDAL_HTTP_TIMEOUT='45',GDAL_HTTP_MAX_RETRY='2'):
        for item in items:
            scene=scene_record(item,bbox)
            if not scene or scene['date'] not in wanted:continue
            scene['render']=render_scene(scene,bbox,OUT,session)
            source,affine,crs,window=audit.window_read(scene['scl_url'],bbox)
            r=scene['render'];target=np.zeros((r['height'],r['width']),np.uint8)
            reproject(source,target,src_transform=affine,src_crs=crs,src_nodata=0,dst_transform=rasterio.transform.from_bounds(*bbox,r['width'],r['height']),dst_crs=4326,dst_nodata=0,resampling=Resampling.nearest)
            path=OUT/f"scl-{scene['date']}.npz";np.savez_compressed(path,scl=target)
            receipts[scene['scene_id']]=dict(path=path.name,sha256=audit.digest(path),url=scene['scl_url'],window=window)
            scenes.append(scene);print('extra RGB/SCL',scene['date'],flush=True)
    if {s['date'] for s in scenes}!=wanted:raise ValueError('Получены не все дополнительные оптические даты')
    audit.save(OUT/'optical.json',dict(query=query,pages=pages,scenes=scenes,scl=receipts))


def score(pixel,dates):
    z={key:((np.array(pixel[key],float)-np.array(pixel['peer'][key+'_med'],float))/np.array(pixel['peer'][key+'_sd'],float)).reshape(-1,1,1) for key in ('hh','hv')}
    result=classify(z['hh'],z['hv'],k=2.5);index,jump=change_point(z['hv'],min_seg=2)
    return dict(style_code=int(result['style'][0,0]),detected_drop=int(result['style'][0,0])==1,
                hv_jump=float(jump[0,0]),best_split=dates[int(index[0,0])],hv_z=z['hv'][:,0,0].round(5).tolist(),
                stored_style=pixel['style'],latest_z=pixel['z'])


def baseline(dates,last_forest,first_clear):
    """Заведомо до/после события: дата GLAD не заменяет интервал по RGB."""
    before=[d for d in dates if last_forest and d<=last_forest]
    after=[d for d in dates if first_clear and d>=first_clear]
    possible_before=[d for d in dates if first_clear and d<first_clear]
    return dict(before=before,after=after,max_possible_before=possible_before,eligible=len(before)>=2 and len(after)>=2,
                note='Минимум 2 наблюдения с каждой стороны требуется неизменённым классификатором')


def acquire_deter():
    params=dict(service='WFS',version='1.0.0',request='GetFeature',typeName='deter-amz:deter_amz',outputFormat='application/json',
                CQL_FILTER="BBOX(geom,-49.3375,-4.8375,-49.2125,-4.7125) AND view_date BETWEEN '2026-07-01' AND '2026-11-14'")
    response=requests.get(audit.WFS,params=params,timeout=(10,60));response.raise_for_status();data=response.json()
    if data.get('type')!='FeatureCollection' or data.get('numberMatched')!=len(data['features']):raise ValueError('Неполный ответ DETER')
    audit.save(OUT/'deter-nearby.geojson',data)
    audit.save(OUT/'deter-source.json',dict(query=response.url,sha256=audit.digest(OUT/'deter-nearby.geojson'),number_matched=len(data['features']),
                                         bbox=[-49.3375,-4.8375,-49.2125,-4.7125],start='2026-07-01',end='2026-11-14'))


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--refresh-optical',action='store_true');parser.add_argument('--refresh-deter',action='store_true');args=parser.parse_args()
    OUT.mkdir(parents=True,exist_ok=True)
    site=json.loads((ROOT/'data/amazon.json').read_text());features=json.loads((ROOT/'data/amazon/validation/alerts.geojson').read_text())['features']
    selected,excluded=selected_samples(site,features)
    if args.refresh_optical:acquire_optical(site)
    if args.refresh_deter:acquire_deter()
    extra=json.loads((OUT/'optical.json').read_text());index=json.loads((ROOT/'data/amazon/optical/index.json').read_text())
    scenes={row['scene']['scene_id']:row['scene'] for row in index['entries']};scenes.update({s['scene_id']:s for s in extra['scenes']});scenes=sorted(scenes.values(),key=lambda s:s['date'])
    source_receipts=json.loads((audit.DIRECTORY/'sources.json').read_text());rows=[]
    for item in selected:
        pixel=item['pixel'];observations=[]
        for scene in scenes:
            is_extra=scene['scene_id'] in extra['scl'];receipt=(extra if is_extra else source_receipts)['scl'][scene['scene_id']]
            directory=OUT if is_extra else audit.DIRECTORY
            if audit.digest(directory/receipt['path'])!=receipt['sha256']:raise ValueError('Хеш SCL не совпал')
            render=scene['render'];image_path=(OUT if is_extra else ROOT/'data/amazon/optical')/render['file']
            if audit.digest(image_path)!=render['sha256']:raise ValueError('Хеш RGB не совпал')
            observations.append(audit.pixel_rgb(pixel,scene,receipt,image_directory=image_path.parent,scl_directory=directory))
        rows.append(dict(id=pixel['id'],lat=pixel['lat'],lon=pixel['lon'],cover=pixel['cover'],alert_dates=item['alert_dates'],rgb=observations,detector=score(pixel,site['dates'])))
    deter=json.loads((OUT/'deter-source.json').read_text())
    if audit.digest(OUT/'deter-nearby.geojson')!=deter['sha256']:raise ValueError('Хеш DETER не совпал')
    inputs=dict(site=audit.digest(ROOT/'data/amazon.json'),alerts=audit.digest(audit.DIRECTORY/'alerts.geojson'),
                optical=audit.digest(ROOT/'data/amazon/optical/index.json'),extra=audit.digest(OUT/'optical.json'))
    review_path=OUT/'reviews.json';reviews=json.loads(review_path.read_text()) if review_path.exists() else {};review_current=reviews.get('input_sha256')==inputs
    for row in rows:
        row['review']=reviews.get('samples',{}).get(row['id'],{'status':'unreviewed'}) if review_current else {'status':'unreviewed'}
        rev=row['review'];row['temporal_support']=baseline(site['dates'],rev.get('last_forest'),rev.get('first_clear'))
    result=dict(schema_version=1,kind='positive_control_audit',source='GLAD-L confirmed code 3; snapshot as of 2026-11-14',
                input_sha256=inputs,selection='Все точные пересечения сетки с подтверждёнными GLAD-пикселями в период NISAR, независимо от результата детектора',
                excluded_alert_pixels=excluded,dates=site['dates'],frozen_parameters=dict(k=2.5,min_segment=2),
                classifier_sha256=audit.digest(ROOT/'pipeline/classify.py'),review_current=review_current,deter=deter,samples=rows)
    result['summary']=dict(samples=len(rows),glad_matched_detections=sum(r['detector']['detected_drop'] for r in rows),
                           verified_forest_loss_samples=sum(r['review']['status']=='forest_loss_visible' for r in rows),
                           eligible_positive_samples=sum(r['review']['status']=='forest_loss_visible' and r['temporal_support']['eligible'] for r in rows),
                           review_statuses=dict(Counter(r['review']['status'] for r in rows)))
    result['summary']['eligible_positive_detections']=sum(r['review']['status']=='forest_loss_visible' and r['temporal_support']['eligible'] and r['detector']['detected_drop'] for r in rows)
    eligible=result['summary']['eligible_positive_samples']
    result['summary']['local_recall']=result['summary']['eligible_positive_detections']/eligible if eligible else None
    result['limitations']=['30-метровый пиксель GLAD не гарантирует потери кроны в каждой 10-метровой точке',
                           'Дата алерта может запаздывать; временная пригодность определяется ясными RGB до/после',
                           'Параметры и радарные ряды не менялись; локальная диагностическая выборка не даёт общей оценки recall']
    audit.save(OUT/'results.json',result)
    audit.inspection_sheet([dict(item['pixel'],since=item['alert_dates'][0]) for item in selected],scenes,output=OUT/'rgb-review.png',
                           image_directories={s['scene_id']:OUT if s['scene_id'] in extra['scl'] else ROOT/'data/amazon/optical' for s in scenes})
    print(json.dumps(result['summary'],ensure_ascii=False),flush=True)


if __name__=='__main__':main()
