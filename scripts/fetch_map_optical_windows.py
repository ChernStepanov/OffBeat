"""Fetch bounded dated Sentinel-2 COG windows for independent Amazon map review."""
import hashlib, json, math
from pathlib import Path
from datetime import datetime, timezone
import numpy as np
import requests, rasterio
from rasterio.windows import from_bounds
from rasterio.transform import from_origin
from rasterio.warp import reproject, Resampling
from PIL import Image, ImageDraw
from pyproj import Transformer

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'data/investigation/maps'
STAC='https://earth-search.aws.element84.com/v1/search'
DATE_RANGE='2026-09-20T00:00:00Z/2026-11-15T23:59:59Z'
QUERY={'collections':['sentinel-2-l2a'],'bbox':[-49.2875,-4.7875,-49.2625,-4.7625],
       'datetime':DATE_RANGE,'limit':100}
TARGET_DATES={'2026-09-23','2026-10-03','2026-10-13','2026-10-21','2026-11-05'}
OUT_RES=20

def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()

def read_to_grid(href, bounds, transform, shape, resampling):
    with rasterio.open(href) as src:
        src_bounds=Transformer.from_crs('EPSG:32722',src.crs,always_xy=True)
        b=src_bounds.transform_bounds(*bounds,densify_pts=21)
        win=from_bounds(*b,transform=src.transform).round_offsets().round_lengths()
        data=src.read(1,window=win,boundless=True,masked=True).astype('float32').filled(np.nan)
        dst=np.full(shape,np.nan,dtype='float32')
        reproject(data,dst,src_transform=src.window_transform(win),src_crs=src.crs,
          dst_transform=transform,dst_crs='EPSG:32722',src_nodata=np.nan,dst_nodata=np.nan,
          resampling=resampling)
        band=(src.tags(1) or {})
        return dst, {'href':href,'crs':str(src.crs),'native_resolution':list(src.res),'dtype':str(src.dtypes[0]),
          'scale':float(src.scales[0]),'offset':float(src.offsets[0]),'nodata':src.nodata,
          'raster_band_tags':band,'source_window':list(win.flatten()) if hasattr(win,'flatten') else [win.col_off,win.row_off,win.width,win.height]}

def main():
    report={'source':'Copernicus Sentinel-2 L2A COGs via Earth Search','stac_url':STAC,
      'query':QUERY,'requested_target_dates':sorted(TARGET_DATES),'requested_at_utc':datetime.now(timezone.utc).isoformat(),
      'bounded_access':'Per-asset rasterio COG range reads for only a projected bounding window enclosing eight reviewed point crops; no full scene downloads.',
      'catalogue_status':None,'candidate_catalogue_items':[],'attempts':[],'selected_scenes':[],'point_summaries':[],
      'limitations':[]}
    try:
      response=requests.post(STAC,json=QUERY,timeout=90); report['catalogue_status']=response.status_code
      response.raise_for_status(); payload=response.json()
      features=payload.get('features',[])
      report['catalogue_feature_count']=len(features)
      report['catalogue_candidate_pages']=len(payload.get('links',[]))
    except Exception as e:
      report['catalogue_failure']={'error_type':type(e).__name__,'message':str(e)[:500]}
      write_report(report); return
    bydate={f['properties']['datetime'][:10]:f for f in features if f['properties']['datetime'][:10] in TARGET_DATES}
    for day in sorted(TARGET_DATES):
      f=bydate.get(day)
      if f:
        report['candidate_catalogue_items'].append({'date':day,'id':f['id'],'datetime':f['properties'].get('datetime'),
          'cloud_percent':f['properties'].get('eo:cloud_cover'),'item_url':next((x['href'] for x in f.get('links',[]) if x.get('rel')=='self'),None),
          'assets':{k:f.get('assets',{}).get(k,{}).get('href') for k in ['red','green','blue','nir','swir16','scl']}})
      else: report['attempts'].append({'date':day,'status':'not_returned_by_catalogue'})
    # Prefer dates after Sep 28 by local clear fraction, then include one pre-date only if usable.
    maps=json.loads((ROOT/'data/investigation/map-candidates.json').read_text())['maps']
    coords=[(x['id'],x['role'],x['lat'],x['lon']) for x in maps]
    xy=[Transformer.from_crs(4326,32722,always_xy=True).transform(lon,lat) for _,_,lat,lon in coords]
    pad=550; bounds=(min(x for x,y in xy)-pad,min(y for x,y in xy)-pad,max(x for x,y in xy)+pad,max(y for x,y in xy)+pad)
    width=math.ceil((bounds[2]-bounds[0])/OUT_RES); height=math.ceil((bounds[3]-bounds[1])/OUT_RES)
    bounds=(bounds[0],bounds[3]-height*OUT_RES,bounds[0]+width*OUT_RES,bounds[3])
    affine=from_origin(bounds[0],bounds[3],OUT_RES,OUT_RES); shape=(height,width)
    # Probe SCL locally first; retain at most three good, distinct dates, favoring late follow-up.
    ordered=sorted((f for d,f in bydate.items()),key=lambda f:(f['properties'].get('eo:cloud_cover',100),f['properties']['datetime']))
    probed=[]
    for f in ordered:
      day=f['properties']['datetime'][:10]
      try:
        scl,rec=read_to_grid(f['assets']['scl']['href'],bounds,affine,shape,Resampling.nearest)
        clear=np.isin(scl,[4,5,6])
        windows=[]
        for (ident,role,lat,lon),(x,y) in zip(coords,xy):
          r=int((bounds[3]-y)/OUT_RES); c=int((x-bounds[0])/OUT_RES); rad=25
          cut=scl[max(0,r-rad):min(height,r+rad),max(0,c-rad):min(width,c+rad)]
          frac=float(np.isin(cut,[4,5,6]).mean()) if cut.size else 0
          windows.append({'id':ident,'role':role,'clear_fraction':frac})
        usable=sum(w['clear_fraction']>=.8 for w in windows)
        probed.append((f,scl,rec,windows,usable))
        report['attempts'].append({'date':day,'scene_id':f['id'],'cloud_percent_scene':f['properties'].get('eo:cloud_cover'),
          'status':'scl_probe_ok','per_point_1km_clear_fractions':windows,'points_ge_80pct_clear':usable,
          'scl_asset':rec,'clear_fraction_bounded_region':float(clear.mean())})
      except Exception as e:
        report['attempts'].append({'date':day,'scene_id':f['id'],'cloud_percent_scene':f['properties'].get('eo:cloud_cover'),
          'status':'scl_probe_failed','error_type':type(e).__name__,'message':str(e)[:500]})
    # Pick latest clear post scene first, plus prior post scene and one pre scene where viable.
    # Keep scenes with useful clear coverage across >=4 of the eight points; other point windows
    # remain explicitly masked in summaries rather than hiding a useful partial scene.
    good=[p for p in probed if p[4]>=4]
    post=[p for p in good if p[0]['properties']['datetime'][:10]>'2026-09-28']
    pre=[p for p in good if p[0]['properties']['datetime'][:10]<='2026-09-28']
    chosen=[]
    for pool in (sorted(post,key=lambda p:p[0]['properties']['datetime'][:10],reverse=True),
                 sorted(pre,key=lambda p:p[0]['properties']['datetime'][:10],reverse=True)):
      for p in pool:
        if len(chosen)>=3: break
        if all(p[0]['id']!=q[0]['id'] for q in chosen): chosen.append(p)
      if len(chosen)>=3: break
    chosen.sort(key=lambda p:p[0]['properties']['datetime'])
    for f,scl,sclrec,quality,usable in chosen:
      day=f['properties']['datetime'][:10]; bands={}; band_receipts={}
      try:
        for key,resamp in [('red',Resampling.bilinear),('green',Resampling.bilinear),('blue',Resampling.bilinear),('nir',Resampling.bilinear),('swir16',Resampling.bilinear)]:
          bands[key],band_receipts[key]=read_to_grid(f['assets'][key]['href'],bounds,affine,shape,resamp)
        sclrec['resampling']='nearest'
        # Apply STAC per-band scale/offset; Earth Search reflectance bands are encoded as integers.
        assets=f['assets']; cal={}
        for k in bands:
          rb=(assets[k].get('raster:bands') or [{}])[0]
          scale=rb.get('scale',.0001); offset=rb.get('offset',0)
          if f['properties'].get('earthsearch:boa_offset_applied',False): offset=0
          elif 'offset' not in rb and float(f['properties'].get('s2:processing_baseline','0'))>=4: offset=-.1
          bands[k]=bands[k]*scale+offset
          cal[k]={'scale':scale,'offset':offset,'unit':'surface reflectance','catalogue_raster_band':rb}
        clear=np.isin(scl,[4,5,6])
        denominator=bands['nir']+bands['red']; ndvi=np.divide(bands['nir']-bands['red'],denominator,out=np.full(shape,np.nan,dtype='float32'),where=np.isfinite(denominator)&(denominator!=0))
        denominator=bands['nir']+bands['swir16']; ndmi=np.divide(bands['nir']-bands['swir16'],denominator,out=np.full(shape,np.nan,dtype='float32'),where=np.isfinite(denominator)&(denominator!=0))
        ndvi[~clear]=np.nan; ndmi[~clear]=np.nan
        # Persist small bounded arrays and exact source/processing metadata.
        npz=BASE/f'new-{day}-windows.npz'; np.savez_compressed(npz,**bands,scl=scl,ndvi=ndvi,ndmi=ndmi)
        scene={'date':day,'datetime':f['properties'].get('datetime'),'scene_id':f['id'],
          'item_url':next((x['href'] for x in f.get('links',[]) if x.get('rel')=='self'),None),
          'scene_cloud_percent':f['properties'].get('eo:cloud_cover'),'scl_clear_by_point':quality,
          'points_ge_80pct_clear':usable,'bounded_region_crs':'EPSG:32722','bounds_m':list(bounds),
          'processing_metadata':{'s2_processing_baseline':f['properties'].get('s2:processing_baseline'),
            'earthsearch_boa_offset_applied':f['properties'].get('earthsearch:boa_offset_applied')},
          'native_analysis_grid':{'resolution_m':OUT_RES,'shape':[height,width],'pixel_support':'20 m square; B04/B08 bilinear resampled from native 10 m; B11/SCL native 20 m; all metrics on common 20 m grid'},
          'assets':{k:{'href':assets[k]['href'],'local_read':band_receipts[k]} for k in ['red','green','blue','nir','swir16']},
          'scl':sclrec,'calibration':cal,'mask':'SCL classes 4,5,6 (vegetation, bare soil, water) retained; unclassified, cloud shadow, clouds, cirrus, snow, saturation, dark pixels and no-data excluded from NDVI/NDMI',
          'indices':'NDVI=(B08-B04)/(B08+B04); NDMI=(B08-B11)/(B08+B11), after scale/offset; no RGB-derived indices',
          'asset_npz':f'data/investigation/maps/{npz.name}','asset_npz_sha256':sha(npz)}
        # Per-location cropped RGB, NDVI, NDMI; transparent/hatched cloud pixels remain blank.
        for ident,role,lat,lon in coords:
          x,y=Transformer.from_crs(4326,32722,always_xy=True).transform(lon,lat); r=int((bounds[3]-y)/OUT_RES); c=int((x-bounds[0])/OUT_RES); rad=25
          sl=(slice(max(0,r-rad),min(height,r+rad)),slice(max(0,c-rad),min(width,c+rad)))
          rgb=np.stack([bands[k][sl] for k in ('red','green','blue')],axis=-1); mask=clear[sl]&np.isfinite(rgb).all(axis=2)
          # Shared fixed reflectance stretch, for display only.
          vis=np.clip(rgb/.3,0,1)**(1/2.2); vis=np.uint8(vis*255); vis[~mask]=0
          im=Image.fromarray(vis,'RGB').resize((200,200)); d=ImageDraw.Draw(im); d.line((94,100,106,100),fill='red',width=2);d.line((100,94,100,106),fill='red',width=2)
          p=BASE/f'new-{ident}-{day}-rgb.png'; im.save(p,optimize=True)
          sheets=scene.setdefault('point_crops',[]); sheets.append({'id':ident,'role':role,'lat':lat,'lon':lon,'rgb_path':f'data/investigation/maps/{p.name}','rgb_sha256':sha(p)})
          for key,arr,lim in [('ndvi',ndvi,(-.2,.9)),('ndmi',ndmi,(-.5,.8))]:
            a=arr[sl]; finite=np.isfinite(a); frac=float(finite.mean())
            if finite.any(): stats={'valid_fraction':frac,'median':float(np.nanmedian(a)),'p10':float(np.nanpercentile(a,10)),'p90':float(np.nanpercentile(a,90))}
            else: stats={'valid_fraction':frac,'median':None,'p10':None,'p90':None}
            sheets[-1][key]=stats
            norm=np.clip((np.nan_to_num(a,nan=lim[0])-lim[0])/(lim[1]-lim[0]),0,1)
            color=np.stack([norm*255,(1-np.abs(norm-.5)*2)*180,(1-norm)*255],axis=-1).astype('uint8');color[~finite]=0
            oi=Image.fromarray(color,'RGB').resize((200,200)); od=ImageDraw.Draw(oi);od.line((94,100,106,100),fill='white',width=2);od.line((100,94,100,106),fill='white',width=2)
            ip=BASE/f'new-{ident}-{day}-{key}.png';oi.save(ip,optimize=True);sheets[-1][key+'_map']={'path':f'data/investigation/maps/{ip.name}','sha256':sha(ip)}
        report['selected_scenes'].append(scene)
      except Exception as e:
        report['attempts'].append({'date':day,'scene_id':f['id'],'status':'asset_fetch_failed','error_type':type(e).__name__,'message':str(e)[:500]})
    # Dated visual contact sheets from the new, actually-read COG windows only.
    if report['selected_scenes']:
      first=report['selected_scenes'][0]
      for point in first['point_crops']:
        tiles=[]
        for scene in report['selected_scenes']:
          p=next((x for x in scene['point_crops'] if x['id']==point['id']),None)
          if not p: continue
          with Image.open(ROOT/p['rgb_path']) as src: im=src.convert('RGB').copy()
          tiles.append((im,scene['date'],p['rgb_sha256']))
        if not tiles: continue
        sheet=Image.new('RGB',(220*len(tiles),230),'white'); draw=ImageDraw.Draw(sheet)
        for i,(im,day,_) in enumerate(tiles):
          sheet.paste(im.resize((220,200)),(220*i,25)); draw.text((220*i+5,5),day,fill='black')
        path=BASE/f"new-{point['id']}-contact.png";sheet.save(path,optimize=True)
        report.setdefault('new_contact_sheets',[]).append({'id':point['id'],'path':f'data/investigation/maps/{path.name}',
          'sha256':sha(path),'dates':[x[1] for x in tiles],'source_rgb_sha256':[x[2] for x in tiles]})
    if not report['selected_scenes']:
      report['limitations'].append('No selected scene produced the required bounded COG reads; late optical rebound remains unexamined.')
    write_report(report)

def write_report(report):
    path=BASE/'new-optical-receipts.json'; path.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'selected':[(x['date'],x['scene_id']) for x in report.get('selected_scenes',[])],
      'attempts':[(x.get('date'),x.get('status')) for x in report.get('attempts',[])],
      'receipt':str(path.relative_to(ROOT))},indent=2))

if __name__=='__main__': main()
