"""Exploratory dense SAR candidates and bounded independent context; not confirmed deforestation."""
import hashlib,json
from datetime import date,timedelta
from pathlib import Path
import numpy as np
from pyproj import Transformer
from rasterio.features import shapes
from rasterio.transform import Affine
from scipy.ndimage import label
from shapely.geometry import Point,shape,mapping
from shapely.ops import transform,unary_union
ROOT=Path(__file__).resolve().parents[1]


def candidate_labels(hv,valid,cover,z,threshold_db=3.0,min_pixels=4):
    """Fixed retrospective 3-before/3-after rule; unavailable data cannot form candidates."""
    if hv.shape[0]!=6 or valid.shape!=hv.shape:raise ValueError('Expected six matching observations')
    good=valid.all(axis=0)&(cover==10)&np.isfinite(z).all(axis=0)
    v=np.full(hv.shape,np.nan);v[valid]=10*np.log10(hv[valid])
    pre=np.median(v[:3],axis=0);post=v[3:];change=np.median(post,axis=0)-pre
    flags=good&(change<=-threshold_db)&((post<=pre-threshold_db).sum(axis=0)>=2)
    labels,count=label(flags,structure=np.ones((3,3),dtype=np.uint8));sizes=np.bincount(labels.ravel())
    keep=[int(k) for k in range(1,count+1) if sizes[k]>=min_pixels]
    return good,flags,labels,change,keep


def main():
    meta=json.loads((ROOT/'data/amazon/dense-peer-z.json').read_text());dates=meta['dates']
    if dates!=['2026-07-18','2026-08-11','2026-08-23','2026-09-04','2026-09-16','2026-09-28']:raise ValueError('Unexpected acquisition dates')
    g=meta['grid'];hv=[];valid=[];inputs=[]
    for entry in meta['inputs']:
        p=ROOT/entry['path'];digest=hashlib.sha256(p.read_bytes()).hexdigest()
        if digest!=entry['sha256']:raise ValueError('GCOV input hash mismatch')
        a=np.load(p);h=a['hv'];hv.append(h);valid.append((a['mask']>0)&(a['mask']<255)&np.isfinite(h)&(h>0));inputs.append(entry)
    coverpath=ROOT/meta['worldcover']['path'];zpath=ROOT/meta['data_path']
    if hashlib.sha256(coverpath.read_bytes()).hexdigest()!=meta['worldcover']['sha256'] or hashlib.sha256(zpath.read_bytes()).hexdigest()!=meta['sha256']:raise ValueError('Context hash mismatch')
    cover=np.load(coverpath)['cover'];z=np.load(zpath)['z'];good,flags,labels,change,keep=candidate_labels(np.stack(hv),np.stack(valid),cover,z)
    transform_grid=Affine(g['x_step'],0,g['x_first']-g['x_step']/2,0,g['y_step'],g['y_first']-g['y_step']/2)
    to_grid=Transformer.from_crs(4326,g['epsg'],always_xy=True).transform;to_geo=Transformer.from_crs(g['epsg'],4326,always_xy=True).transform
    alert_path=ROOT/'data/amazon/alerts.geojson';fire_path=ROOT/'data/amazon/fires.json';alerts=json.loads(alert_path.read_text())['features'];fires=json.loads(fire_path.read_text())
    anchor=date.fromisoformat(dates[3]);start=anchor-timedelta(days=60);end=anchor+timedelta(days=60)
    candidates=[]
    for k in keep:
        mask=labels==k;polygons=[shape(geom) for geom,value in shapes(mask.astype('uint8'),mask=mask,transform=transform_grid) if value==1];geom=unary_union(polygons)
        alert_matches=[];fire_matches=[]
        for f in alerts:
            props=f.get('properties') or {}
            try:day=date.fromisoformat(str(props.get('date',''))[:10])
            except ValueError:continue
            if start<=day<=end and f.get('geometry') and transform(to_grid,shape(f['geometry'])).intersects(geom):alert_matches.append({'date':day.isoformat(),'source':props.get('source'),'class':props.get('class')})
        for f in fires:
            try:day=date.fromisoformat(str(f.get('date',''))[:10]);point=Point(*to_grid(float(f['lon']),float(f['lat'])))
            except (KeyError,TypeError,ValueError):continue
            distance=geom.distance(point)
            if start<=day<=end and distance<=1000:fire_matches.append({'date':day.isoformat(),'source':f.get('source'),'provider':f.get('provider'),'distance_m':round(float(distance),1)})
        rows,cols=np.where(mask);edge=bool((rows==50).any() or (rows==labels.shape[0]-51).any() or (cols==50).any() or (cols==labels.shape[1]-51).any())
        candidates.append({'id':f'EXP-{k:03}','cells':int(mask.sum()),'flagged_grid_footprint_ha':round(float(mask.sum()*abs(g['x_step']*g['y_step'])/10000),3),'touches_analysis_boundary':edge,
          'median_hv_shift_db':round(float(np.median(change[mask])),3),'geometry_wgs84':mapping(transform(to_geo,geom)),
          'alert_matches':alert_matches,'fire_matches':fire_matches,'interpretation':'candidate; cause and event status unknown'})
    out={'kind':'experimental_dense_candidate_validation','source':'NISAR PROVISIONAL GCOV, ESA WorldCover 2021, locally archived GLAD-L/DETER and FIRMS/INPE context',
      'radar_dates':dates,'inputs':inputs,'worldcover':meta['worldcover'],'peer_z_path':meta['data_path'],'peer_z_sha256':meta['sha256'],
      'context_inputs':[{'path':p.relative_to(ROOT).as_posix(),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in (alert_path,fire_path)],
      'method':'Retrospective exploratory rule, not preregistered: 2021 forest class, six valid native 20 m HV observations, full 1 km peer-neighbourhood coverage, median of 3 post minus median of 3 pre <= -3 dB, at least 2 of 3 post observations <= pre median -3 dB, then 8-connected groups of at least 4 cells. Fixed 60-day window around first post date for alert polygon intersection and fire point within 1 km of candidate footprint.',
      'limitations':'Flagged footprint is the nominal area of selected radar grid cells, not validated event area. Results depend on post-hoc thresholds, 2021 land classes, weather, speckle and provisional data; missing data and analysis boundaries are not absence of change. Alert and fire archives are incomplete local subsets, date precision may be day-only, fire proximity is not proof of cause. No independent confirmed-event labels, precision, recall, or causal attribution are calculated.',
      'quality':{'eligible_forest_cells':int(good.sum()),'thresholded_cells':int(flags.sum()),'minimum_component_cells':4,'candidate_count':len(candidates)},
      'context_window':[start.isoformat(),end.isoformat()],'candidates':candidates}
    path=ROOT/'data/amazon/dense-validation.json';path.write_text(json.dumps(out,indent=2)+'\n',encoding='utf-8');print('eligible',good.sum(),'thresholded',flags.sum(),'candidates',len(candidates),flush=True)
    for c in candidates:print(c['id'],'cells',c['cells'],'alerts',len(c['alert_matches']),'fire records',len(c['fire_matches']),flush=True)

if __name__=='__main__':main()
