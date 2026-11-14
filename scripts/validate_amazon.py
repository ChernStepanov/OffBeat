"""Сверить все HV drop Амазонии с DETER, GLAD-L и RGB без подмены отсутствия данных нулём.

python scripts/validate_amazon.py --refresh --as-of 2026-11-14
Повтор без --refresh использует сохранённые квитанции и окна источников.
"""
import argparse
from collections import Counter
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
from PIL import Image, ImageDraw
import rasterio
from rasterio.transform import Affine
from rasterio.warp import reproject, transform_bounds, Resampling
from rasterio.windows import from_bounds, Window
from pyproj import Transformer
import requests
from shapely import geometry, transform as transform_geometry

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline.classify import classify

DIRECTORY = ROOT / 'data/amazon/validation'
WFS = 'https://terrabrasilis.dpi.inpe.br/geoserver/deter-amz/ows'
BUCKET = 'https://storage.googleapis.com/earthenginepartners-hansen/'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, allow_nan=False, indent=2) + '\n')


def window_read(url, bbox):
    with rasterio.open(url) as src:
        bounds = transform_bounds(4326, src.crs, *bbox, densify_pts=21)
        w = from_bounds(*bounds, src.transform)
        left, top = int(np.floor(w.col_off)), int(np.floor(w.row_off))
        right, bottom = int(np.ceil(w.col_off+w.width)), int(np.ceil(w.row_off+w.height))
        win = Window(left, top, right-left, bottom-top).intersection(Window(0, 0, src.width, src.height))
        if win.width * win.height > 2_000_000:
            raise ValueError('Слишком большое окно')
        return src.read(1, window=win), src.window_transform(win), src.crs, list(map(int, [win.col_off, win.row_off, win.width, win.height]))


def acquire(site, scenes, as_of):
    candidates = [p for p in site['pixels'] if p['style'] == 'drop']
    start = min(date.fromisoformat(p['since']) for p in candidates) - timedelta(days=60)
    b = site['grid']['bbox']
    # Окно поиска включает 500 м контекста по всем сторонам, а не весь старый AOI 50 км.
    bbox = [b['w']-.005, b['s']-.005, b['e']+.005, b['n']+.005]
    session = requests.Session()
    params = dict(service='WFS', version='1.0.0', request='GetFeature', typeName='deter-amz:deter_amz',
                  outputFormat='application/json', CQL_FILTER=f"BBOX(geom,{','.join(map(str,bbox))}) AND view_date BETWEEN '{start}' AND '{as_of}'")
    response = session.get(WFS, params=params, timeout=(10, 60)); response.raise_for_status()
    deter = response.json()
    if deter.get('type') != 'FeatureCollection' or len(deter['features']) != deter.get('numberMatched', deter.get('totalFeatures')):
        raise ValueError('Ответ DETER неполный или неверного формата')
    save(DIRECTORY/'deter-raw.geojson', deter)
    receipts = dict(as_of=as_of.isoformat(), fetched_at=datetime.now(timezone.utc).isoformat(),
                    bbox=bbox, start=start.isoformat(),
                    deter=dict(url=response.url, path='deter-raw.geojson', sha256=digest(DIRECTORY/'deter-raw.geojson'), count=len(deter['features'])), scl={})
    prefixes, token = [], None
    while True:
        params = dict(prefix=f'GLADalert/C2/{as_of.year}/', delimiter='/', fields='prefixes,nextPageToken', maxResults=1000)
        if token: params['pageToken'] = token
        response = session.get('https://storage.googleapis.com/storage/v1/b/earthenginepartners-hansen/o',params=params,timeout=(10,60));response.raise_for_status()
        result = response.json(); prefixes.extend(result.get('prefixes', []));token=result.get('nextPageToken')
        if not token:break
    dated = []
    for prefix in prefixes:
        try:stamp=date.fromisoformat(f"{as_of.year}-{prefix.rstrip('/').split('/')[-1].replace('_','-')}")
        except ValueError:continue
        if stamp<=as_of:dated.append((stamp,prefix))
    if not dated:raise ValueError('Нет датированных выпусков GLAD')
    skipped=[]
    for stamp,prefix in sorted(dated,reverse=True):
        urls=[f'{BUCKET}{prefix}{key}{as_of.year%100:02d}_050W_10S_040W_00N.tif' for key in ('alert','alertDate')]
        statuses=[session.head(url,timeout=(10,30)).status_code for url in urls]
        if statuses==[200,200]:break
        if any(code not in (200,404) for code in statuses):raise ValueError('Не удалось проверить выпуск GLAD')
        skipped.append(dict(release=stamp.isoformat(),reason='Нет обоих растров для выбранного тайла'))
    else:raise ValueError('Нет доступного выпуска GLAD для тайла')
    arrays, windows = {}, {}
    with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN='EMPTY_DIR', CPL_VSIL_CURL_ALLOWED_EXTENSIONS='.tif', GDAL_HTTP_TIMEOUT='45', GDAL_HTTP_MAX_RETRY='2'):
        for key in ('alert', 'alertDate'):
            url=f'{BUCKET}{prefix}{key}{as_of.year%100:02d}_050W_10S_040W_00N.tif'
            values, affine, crs, win=window_read(url,bbox)
            if crs.to_epsg()!=4326:raise ValueError('Неожиданная проекция GLAD')
            arrays[key]=values; windows[key]=dict(url=url,window=win,transform=list(affine)[:6])
            print('GLAD',key,values.shape,flush=True)
        if windows['alert']['transform']!=windows['alertDate']['transform'] or arrays['alert'].shape!=arrays['alertDate'].shape:
            raise ValueError('Сетки GLAD не совпадают')
        np.savez_compressed(DIRECTORY/'glad.npz',**arrays)
        receipts['glad']=dict(release=stamp.isoformat(),year=as_of.year,path='glad.npz',sha256=digest(DIRECTORY/'glad.npz'),bands=windows,skipped_releases=skipped)
        for scene in scenes:
            values,affine,crs,win=window_read(scene['scl_url'],[b[k] for k in ('w','s','e','n')])
            target=np.zeros((scene['render']['height'],scene['render']['width']),np.uint8)
            reproject(values,target,src_transform=affine,src_crs=crs,src_nodata=0,
                      dst_transform=rasterio.transform.from_bounds(*scene['render']['bbox'],target.shape[1],target.shape[0]),dst_crs=4326,dst_nodata=0,resampling=Resampling.nearest)
            filename=f"scl-{scene['date']}.npz";np.savez_compressed(DIRECTORY/filename,scl=target)
            receipts['scl'][scene['scene_id']]=dict(path=filename,url=scene['scl_url'],window=win,sha256=digest(DIRECTORY/filename))
            print('SCL',scene['date'],flush=True)
    save(DIRECTORY/'sources.json',receipts)


def alert_features(receipts):
    deter=json.loads((DIRECTORY/receipts['deter']['path']).read_text())
    features=[]
    for feature in deter['features']:
        prop=feature['properties']
        features.append(dict(type='Feature',geometry=feature['geometry'],properties=dict(source='DETER',date=str(prop['view_date'])[:10],**{'class':prop['classname']})))
    with np.load(DIRECTORY/receipts['glad']['path']) as data:
        alert,days=data['alert'],data['alertDate']
        affine=Affine(*receipts['glad']['bands']['alert']['transform'])
        # Никакого отсева по площади: даже одиночный подтверждённый пиксель учитывается.
        for row,col in np.argwhere(np.isin(alert,[2,3])&(days>0)&(days<=366)):
            stamp=date(receipts['glad']['year'],1,1)+timedelta(days=int(days[row,col])-1)
            if stamp.isoformat()>receipts['as_of']:continue
            x0,y0=affine@(int(col),int(row));x1,y1=affine@(int(col)+1,int(row)+1)
            features.append(dict(type='Feature',geometry=geometry.mapping(geometry.box(x0,y1,x1,y0)),properties=dict(source='GLAD-L',date=stamp.isoformat(),confidence=int(alert[row,col]),**{'class':'confirmed' if alert[row,col]>=3 else 'unconfirmed'})))
    return features


def match_alerts(pixel, features, tolerance_m=30, max_days=60):
    project=Transformer.from_crs(4326,32722,always_xy=True).transform
    point=geometry.Point(*project(pixel['lon'],pixel['lat']))
    matches=[]; nearest={}
    for feature in features:
        prop=feature['properties'];delta=(date.fromisoformat(prop['date'])-date.fromisoformat(pixel['since'])).days
        polygon=transform_geometry(geometry.shape(feature['geometry']),project,interleaved=False)
        distance=float(polygon.distance(point))
        rec=dict(source=prop['source'],date=prop['date'],delta_days=delta,distance_m=round(distance,2),confidence=prop.get('confidence'),point_overlap=bool(polygon.covers(point)))
        if prop['source'] not in nearest or distance<nearest[prop['source']]['distance_m']:
            nearest[prop['source']]=rec
        if abs(delta)<=max_days and distance<=tolerance_m and prop.get('confidence',3)>=3:
            matches.append(rec)
    return matches,nearest


def pixel_rgb(pixel, scene, receipt,image_directory=None,scl_directory=None):
    render=scene['render'];w,s,e,n=render['bbox'];height,width=render['height'],render['width']
    x=min(width-1,max(0,int((pixel['lon']-w)/(e-w)*width)))
    y=min(height-1,max(0,int((n-pixel['lat'])/(n-s)*height)))
    with Image.open((image_directory or ROOT/'data/amazon/optical')/render['file']) as image:rgba=np.array(image)
    with np.load((scl_directory or DIRECTORY)/receipt['path']) as data:scl=data['scl']
    center=int(scl[y,x]);window=scl[max(0,y-3):min(height,y+4),max(0,x-3):min(width,x+4)]
    return dict(date=scene['date'],scene_id=scene['scene_id'],file=render['file'],png_sha256=render['sha256'],scl=center,
                clear_land=center in (4,5) and bool(rgba[y,x,3]),
                nearby_cloud_shadow_fraction=round(float(np.isin(window,[3,8,9,10]).mean()),4),
                rgb=rgba[y,x,:3].tolist())


def stability(pixel):
    zs={key:((np.array(pixel[key],float)-np.array(pixel['peer'][key+'_med'],float))/np.array(pixel['peer'][key+'_sd'],float)).reshape(-1,1,1) for key in ('hh','hv')}
    retained=[]
    for excluded in range(zs['hv'].shape[0]):
        mask=np.arange(zs['hv'].shape[0])!=excluded
        retained.append(bool(classify(zs['hh'][mask],zs['hv'][mask])['style'][0,0]==1))
    return dict(leave_one_date_out_drop_count=sum(retained),trials=len(retained),retained=retained,
                note='Чувствительность формы, не независимая оценка точности')


def attach_reviews(output, reviews):
    current=reviews.get('input_sha256')==output['input_sha256']
    output['review_status']='current' if current else 'needs_review'
    output['review_method']=reviews.get('method') if current else None
    for row in output['candidates']:
        review=reviews.get('candidates',{}).get(row['id']) if current else None
        row['review']=review or dict(verdict='unreviewed',observation='Требуется просмотр RGB для текущих входных данных')
    output['summary']=dict(n_candidates=len(output['candidates']),
                           spatial_temporal_alert_matches=sum(bool(row['alert_matches']) for row in output['candidates']),
                           verdicts=dict(Counter(row['review']['verdict'] for row in output['candidates'])))


def inspection_sheet(pixels,scenes,output=None,image_directories=None):
    sheet=Image.new('RGB',(max(1100,180+len(scenes)*180),30+len(pixels)*210),'#ddd');draw=ImageDraw.Draw(sheet)
    for j,scene in enumerate(scenes):draw.text((185+j*180,5),scene['date'],fill='black')
    for i,pixel in enumerate(pixels):
        y=30+i*210;draw.text((4,y+20),pixel['id']+'\n'+pixel['since']+'\nclass '+str(pixel['cover']),fill='black')
        for j,scene in enumerate(scenes):
            directory=image_directories[scene['scene_id']] if image_directories else ROOT/'data/amazon/optical'
            with Image.open(directory/scene['render']['file']) as original:im=original.convert('RGB')
            w,s,e,n=scene['render']['bbox'];x=(pixel['lon']-w)/(e-w)*im.width;row=(n-pixel['lat'])/(n-s)*im.height
            pad=Image.new('RGB',(im.width+42,im.height+42),'#888');pad.paste(im,(21,21))
            left,top=int(np.floor(x)),int(np.floor(row))
            crop=pad.crop((left,top,left+43,top+43)).resize((172,172),Image.Resampling.NEAREST)
            marker=ImageDraw.Draw(crop)
            cx,cy=round((x+21-left)*4),round((row+21-top)*4)
            for coords in [(cx-7,cy,cx-3,cy),(cx+3,cy,cx+7,cy),(cx,cy-7,cx,cy-3),(cx,cy+3,cx,cy+7)]:marker.line(coords,fill='white',width=2)
            sheet.paste(crop,(180+j*180,y))
    sheet.save(output or DIRECTORY/'rgb-review.png')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--refresh',action='store_true');parser.add_argument('--as-of',default='2026-11-14')
    args=parser.parse_args();as_of=date.fromisoformat(args.as_of)
    site=json.loads((ROOT/'data/amazon.json').read_text());index=json.loads((ROOT/'data/amazon/optical/index.json').read_text())
    if any(date.fromisoformat(p['since']).year!=as_of.year for p in site['pixels'] if p['style']=='drop'):
        raise ValueError('Этот разбор поддерживает кандидатов и выпуск GLAD одного календарного года')
    scenes=sorted({row['scene']['scene_id']:row['scene'] for row in index['entries'] if row.get('scene',{}).get('render')}.values(),key=lambda s:s['date'])
    DIRECTORY.mkdir(parents=True,exist_ok=True)
    if args.refresh:acquire(site,scenes,as_of)
    receipts=json.loads((DIRECTORY/'sources.json').read_text())
    if receipts['as_of'] != as_of.isoformat():raise ValueError('Дата сохранённых источников отличается от --as-of')
    w,s,e,n=receipts['bbox']
    if not all(w<=p['lon']<=e and s<=p['lat']<=n for p in site['pixels']):raise ValueError('Участок не покрыт окном источников')
    for item in [receipts['deter'],receipts['glad'],*receipts['scl'].values()]:
        if digest(DIRECTORY/item['path'])!=item['sha256']:raise ValueError('Хеш исходных данных не совпал')
    features=alert_features(receipts);save(DIRECTORY/'alerts.geojson',dict(type='FeatureCollection',features=features))
    pixels=[p for p in site['pixels'] if p['style']=='drop'];rows=[]
    for pixel in pixels:
        matches,nearest=match_alerts(pixel,features)
        _,nearest_confirmed=match_alerts(pixel,[f for f in features if f['properties'].get('confidence',3)>=3])
        rgb=[pixel_rgb(pixel,scene,receipts['scl'][scene['scene_id']]) for scene in scenes]
        before=[row for row in rgb if row['clear_land'] and row['date']<pixel['since']]
        after=[row for row in rgb if row['clear_land'] and row['date']>=pixel['since']]
        rows.append(dict(id=pixel['id'],lat=pixel['lat'],lon=pixel['lon'],cover=pixel['cover'],since=pixel['since'],z=pixel['z'],
                         alert_matches=matches,nearest_alerts=nearest,nearest_confirmed_alerts=nearest_confirmed,rgb=rgb,
                         clear_before=before[-1]['date'] if before else None,clear_after=after[0]['date'] if after else None,
                         stability=stability(pixel)))
    output=dict(schema_version=1,kind='candidate_audit',site='amazon',as_of=receipts['as_of'],
                source_receipts='validation/sources.json',input_sha256=dict(site=digest(ROOT/'data/amazon.json'),optical=digest(ROOT/'data/amazon/optical/index.json'),sources=digest(DIRECTORY/'sources.json')),
                limitations=['Отсутствие алерта не доказывает отсутствие изменения; GLAD и DETER имеют разные маски, пороги и задержки',
                             'Нет независимой эталонной разметки: precision, recall, площадь вырубки и опережение алертов не оценены',
                             'SCL проверяет облака и тени, но не доказывает точность визуального вывода; серые зоны листа RGB находятся вне вырезки',
                             'Все шесть HV drop проверены, включая точки ниже текущего порога карты; параметры классификатора не подгонялись'],
                match_rule=dict(tolerance_m=30,max_days=60,glad_min_confidence=3),candidates=rows)
    review_path=DIRECTORY/'reviews.json'
    attach_reviews(output,json.loads(review_path.read_text()) if review_path.exists() else {})
    save(ROOT/'data/amazon/validation.json',output);inspection_sheet(pixels,scenes)
    for row in rows:print(row['id'],'matches',len(row['alert_matches']),'clear',row['clear_before'],row['clear_after'],'LOO',row['stability']['leave_one_date_out_drop_count'],flush=True)


if __name__=='__main__':main()
