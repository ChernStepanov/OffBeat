"""Догрузка исходных окон оставшихся GUNW с проверкой кэша и возобновлением.

python -m scripts.download_mexico_remaining --inventory
python -m scripts.download_mexico_remaining --workers 2
Полные многогигабайтные HDF5 не копируются: читаются native окна AOI и метаданные.
"""
import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import contextlib
from datetime import datetime, timezone
import io
import json
import os
from pathlib import Path
import re

import earthaccess
import h5py
import numpy as np
from pyproj import Transformer

from scripts import mexico_displacement as M
from scripts import subset_nisar as S

TARGET = M.ROOT/'data/subsets/mexico-gunw-remaining'
RECEIPT = 'data/analysis/mexico-gunw-download.json'
_WORKER_FS = None


def verify_cached(path, granule):
    r = json.loads(path.read_text())
    p = M.ROOT/r['subset_path']
    if r['source']['id'] != granule['id'] or M.digest(p) != r['sha256']:
        raise ValueError('Кэш не соответствует исходной грануле')
    return r


def inventory():
    catalogue = json.loads((M.ROOT/M.CATALOGUE).read_text())
    existing = {}
    for path in (M.ROOT/'data/subsets/mexico-gunw-series').glob('*/*.json'):
        r = json.loads(path.read_text())
        verify_cached(path, r['source'])
        existing[r['source']['id']] = path.relative_to(M.ROOT).as_posix()
    remaining = [g for g in catalogue['granules'] if g['id'] not in existing]
    if len({g['id'] for g in catalogue['granules']}) != len(catalogue['granules']):
        raise ValueError('Повторные гранулы каталога')
    return catalogue, existing, remaining


def geometry_cube(hdf, lat, lon):
    path = 'science/LSAR/GUNW/metadata/radarGrid'
    names = ['xCoordinates','yCoordinates','heightAboveEllipsoid','projection','losUnitVectorX','losUnitVectorY']
    if path not in hdf or not all(n in hdf[path] for n in names):
        return {}, {'available': False}
    g = hdf[path]; x,y,z = [g[n][:] for n in names[:3]]; epsg=int(g['projection'][()])
    xx,yy=Transformer.from_crs(4326,epsg,always_xy=True).transform(lon,lat)
    def window(axis,values):
        if np.min(values)<min(axis) or np.max(values)>max(axis):
            raise ValueError('Координаты за пределами геометрического куба')
        indices=np.flatnonzero((axis>=np.min(values))&(axis<=np.max(values)))
        if indices.size:
            return slice(max(0,int(indices.min())-1),min(len(axis),int(indices.max())+2))
        nearest=int(np.argmin(abs(axis-np.mean(values))))
        return slice(max(0,nearest-1),min(len(axis),nearest+2))
    rows,cols=window(y,yy),window(x,xx)
    a={'geometry_x':x[cols], 'geometry_y':y[rows], 'geometry_height':z,
       'geometry_los_e':g['losUnitVectorX'][:,rows,cols],
       'geometry_los_n':g['losUnitVectorY'][:,rows,cols]}
    return a, {'available':True,'epsg':epsg,'path':path,
               'window':[rows.start,rows.stop,cols.start,cols.stop],
               'method':'Сохранены исходные ENU east/north кубы для всех высот; высота местности не подменена средним уровнем.'}


def samples(group,names,lat,lon):
    """Native nearest-neighbour без глобального перенаправления stdout в потоках."""
    x,y=group['xCoordinates'][:],group['yCoordinates'][:]
    epsg=int(group['projection'][()])
    xx,yy=Transformer.from_crs(4326,epsg,always_xy=True).transform(lon,lat)
    cols=np.floor((xx-x[0])/(x[1]-x[0])+.5).astype(int)
    rows=np.floor((yy-y[0])/(y[1]-y[0])+.5).astype(int)
    if np.any((cols<0)|(cols>=len(x))|(rows<0)|(rows>=len(y))):
        raise ValueError('AOI за пределами продукта')
    r0,r1,c0,c1=int(rows.min()),int(rows.max()+1),int(cols.min()),int(cols.max()+1)
    result={}
    for key,name in names.items():
        ds=group[name]; values=np.asarray(ds[r0:r1,c0:c1])[rows-r0,cols-c0]
        if np.issubdtype(values.dtype,np.floating):
            values=values.astype(float); fill=ds.attrs.get('_FillValue')
            if fill is not None:values[values==fill]=np.nan
        result[key]=values
    return result,{'epsg':epsg,'spacing':[float(x[1]-x[0]),float(y[1]-y[0])],
                   'window':[r0,r1,c0,c1],'paths':{k:group[v].name for k,v in names.items()}}


def extract(g, fs):
    parts=re.findall(r'\d{8}T\d{6}',g['id'])
    dates=[f'{v[:4]}-{v[4:6]}-{v[6:8]}' for v in [parts[0],parts[2]]]
    target=TARGET/g['direction']; target.mkdir(parents=True,exist_ok=True)
    output=target/('_'.join(dates)+'.npz'); receipt=output.with_suffix('.json')
    if receipt.exists():
        return verify_cached(receipt,g)
    track,frame,word,_=M.SPECS[g['direction']]
    lat,lon=S.coordinates()
    with fs.open(g['url'],block_size=1024*1024,cache_type='blockcache') as stream, h5py.File(stream,'r') as h:
        ident=h['science/LSAR/identification']
        observed=(int(ident['trackNumber'][()]),int(ident['frameNumber'][()]),S.scalar(ident['orbitPassDirection']))
        if observed!=(track,frame,word) or S.scalar(ident['lookDirection'])!='Left':
            raise ValueError('Несовместимая геометрия')
        ref,sec=[S.scalar(ident[n])[:10] for n in ['referenceZeroDopplerStartTime','secondaryZeroDopplerStartTime']]
        if dates!=[ref,sec]:raise ValueError('Даты не соответствуют ID')
        base=h['science/LSAR/GUNW/grids/frequencyA']; group=base['unwrappedInterferogram']
        names={'phase':'HH/unwrappedPhase','coherence':'HH/coherenceMagnitude','component':'HH/connectedComponents',
               'iono':'HH/ionospherePhaseScreen','iono_sd':'HH/ionospherePhaseScreenUncertainty','mask':'mask'}
        a,grid=samples(group,names,lat,lon)
        valid=M.quality(a)
        p='science/LSAR/GUNW/metadata/processingInformation/parameters/unwrappedInterferogram/frequencyA'
        grid['flattening']={n:S.scalar(h[p+'/'+n]) if p+'/'+n in h else None for n in
                            ['ellipsoidalFlatteningApplied','topographicFlatteningApplied']}
        geo,geometry=geometry_cube(h,lat,lon)
        grid['geometry']=geometry
        optional=[n for n in h['science/LSAR/GUNW/metadata/radarGrid'].keys()
                  if any(k in n.lower() for k in ['troposphere','tide'])] if 'science/LSAR/GUNW/metadata/radarGrid' in h else []
        grid['external_correction_layer_names']=optional
        temporary=output.with_suffix('.part.npz')
        np.savez_compressed(temporary,lat=lat,lon=lon,**a,**geo)
        r={'source':{k:g[k] for k in ['id','concept_id','url']},
           'catalogue_query':json.loads((M.ROOT/M.CATALOGUE).read_text())['query'],
           'retrieved_utc':datetime.now(timezone.utc).isoformat(),
           'reference_date':ref,'secondary_date':sec,
           'identification':{'track':track,'frame':frame,'direction':word,'look_direction':'Left',
                             'product_version':S.scalar(ident['productVersion'])},
           'center_frequency_hz':float(base['centerFrequency'][()]),'grid':grid,
           'subset_path':output.relative_to(M.ROOT).as_posix(),'sha256':M.digest(temporary),
           'sample_count':int(valid.size),'quality_valid_count':int(valid.sum()),
           'steps':['Authenticated HTTP Range чтение native окон 32×32 прежних координат.',
                    'Сохранены исходные phase/coherence/components/ionosphere/uncertainty/mask без заполнения.',
                    'Проверены реальные даты/track/frame/look direction; сохранены flattening flags и доступные LOS кубы.',
                    'Строгая маска прежнего расчёта, без изменения порогов; атмосфера не исправлялась.']}
        temporary.replace(output)
        temp_receipt=receipt.with_suffix('.part.json'); temp_receipt.write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n')
        temp_receipt.replace(receipt)
        return r


def worker_init():
    global _WORKER_FS
    with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
        auth=earthaccess.login(strategy='environment',persist=False)
    if not auth.authenticated:raise RuntimeError('Earthdata authentication failed')
    _WORKER_FS=earthaccess.get_fsspec_https_session()


def worker_extract(g):
    return extract(g,_WORKER_FS)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inventory',action='store_true'); parser.add_argument('--workers',type=int,default=2)
    parser.add_argument('--limit',type=int)
    args=parser.parse_args()
    catalogue,existing,remaining=inventory()
    if args.inventory:
        print(json.dumps({'catalogue':len(catalogue['granules']),'previously_sampled':len(existing),
                          'remaining':len(remaining),'by_direction':{d:sum(g['direction']==d for g in remaining) for d in M.SPECS}}));return
    if args.workers<1 or args.workers>4:raise ValueError('workers: 1…4')
    token_file=M.ROOT/'.earthdata_token'
    if not os.environ.get('EARTHDATA_TOKEN') and token_file.is_file():
        os.environ['EARTHDATA_TOKEN']=token_file.read_text().strip()
    with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
        auth=earthaccess.login(strategy='environment',persist=False)
    if not auth.authenticated:raise RuntimeError('Earthdata authentication failed')
    selected=remaining[:args.limit] if args.limit is not None else remaining
    errors=[];done={}
    # HDF5 сериализует потоки глобальной блокировкой; процессы независимо читают HTTP Range.
    with ProcessPoolExecutor(max_workers=args.workers,initializer=worker_init) as pool:
        jobs={pool.submit(worker_extract,g):g for g in selected}
        for future in as_completed(jobs):
            g=jobs[future]
            try:
                r=future.result(); done[g['id']]={'receipt':r['subset_path'].replace('.npz','.json'),'valid':r['quality_valid_count']}
                print(g['direction'],r['reference_date'],r['secondary_date'],'valid',r['quality_valid_count'],flush=True)
            except Exception as exc:
                errors.append({'id':g['id'],'error_type':type(exc).__name__})
                print(g['direction'],'failed',type(exc).__name__,flush=True)
            M.save(RECEIPT,{'catalogue_sha256':M.digest(M.ROOT/M.CATALOGUE),'catalogue_granules':len(catalogue['granules']),
                            'previous_receipts':existing,'expected_remaining':len(remaining),'completed':done,
                            'errors':errors,'selected_count':len(selected),'complete':len(done)==len(remaining) and not errors,
                            'mode':'native_aoi_windows_not_full_hdf5'})
    if errors:raise SystemExit(1)


if __name__=='__main__':
    try:main()
    except Exception as exc:
        print('Загрузка остановлена:',type(exc).__name__)
        raise SystemExit(1)
