"""Date-matched Sentinel-2 previews. Read only AOI COG windows; never invent missing images.

Usage: python scripts/optical.py [--site amazon] [--search-only]
"""
import argparse
import hashlib
import json
from datetime import date, timedelta, datetime, timezone
from pathlib import Path
import numpy as np
import requests
import rasterio
from rasterio.enums import Resampling
from rasterio.warp import transform_bounds, reproject
from rasterio.windows import from_bounds
from rasterio.transform import from_bounds as output_transform
from PIL import Image
from shapely.geometry import shape, box

ROOT = Path(__file__).resolve().parents[1]
STAC = 'https://earth-search.aws.element84.com/v1/search'
SIZE = 256


def calibration_for(asset, props):
    band=(asset.get('raster:bands') or [{}])[0]
    scale=band.get('scale',.0001)
    offset=band.get('offset',0)
    if props.get('earthsearch:boa_offset_applied',False): offset=0
    elif 'offset' not in band and float(props.get('s2:processing_baseline','0'))>=4: offset=-.1
    return scale,offset


def read_window(href, bbox, nearest=False):
    """Bounded remote read and reprojection; nodata never becomes a valid zero."""
    bounds = [bbox[k] for k in ['w','s','e','n']]
    with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN='EMPTY_DIR', GDAL_HTTP_TIMEOUT=30):
        with rasterio.open(href) as source:
            native = transform_bounds('EPSG:4326',source.crs,*bounds,densify_pts=21)
            window = from_bounds(*native,transform=source.transform).round_offsets().round_lengths()
            values = source.read(1,window=window,boundless=True,masked=True).astype('float32').filled(np.nan)
            result = np.full((SIZE,SIZE),np.nan,dtype='float32')
            reproject(values,result,src_transform=source.window_transform(window),src_crs=source.crs,
                dst_transform=output_transform(*bounds,SIZE,SIZE),dst_crs='EPSG:4326',
                src_nodata=np.nan,dst_nodata=np.nan,
                resampling=Resampling.nearest if nearest else Resampling.bilinear)
    return result


def search(site):
    dates = [date.fromisoformat(d) for d in site['dates']]
    b = site['grid']['bbox']
    payload = {'collections':['sentinel-2-l2a'], 'bbox':[b[k] for k in ['w','s','e','n']],
        'datetime':f'{min(dates)-timedelta(days=15)}T00:00:00Z/{max(dates)+timedelta(days=15)}T23:59:59Z',
        'limit':100}
    items = []
    response = requests.post(STAC,json=payload,timeout=90)
    response.raise_for_status()
    while True:
        page = response.json(); items.extend(page.get('features',[]))
        link = next((l for l in page.get('links',[]) if l.get('rel')=='next'),None)
        if not link: break
        response = requests.post(link['href'],json=link.get('body',{}),timeout=90) if link.get('method')=='POST' else requests.get(link['href'],timeout=90)
        response.raise_for_status()
    aoi = box(*[b[k] for k in ['w','s','e','n']])
    items = [i for i in items if shape(i['geometry']).covers(aoi) and all(k in i['assets'] for k in ['red','green','blue','scl'])]
    return payload, items


def select_candidates(items, target):
    return sorted([i for i in items if abs((date.fromisoformat(i['properties']['datetime'][:10])-date.fromisoformat(target)).days)<=15],
        key=lambda i:(i['properties'].get('eo:cloud_cover',100),abs((date.fromisoformat(i['properties']['datetime'][:10])-date.fromisoformat(target)).days),i['id']))


def make_preview(item,bbox,folder):
    assets = item['assets']; props = item['properties']
    scl = read_window(assets['scl']['href'],bbox,nearest=True)
    clear = np.isin(scl,[4,5,6,7])
    cloud = np.isin(scl,[3,8,9,10,11])
    quality = {'aoi_cloud_shadow_snow_fraction':float(cloud.mean()), 'aoi_clear_fraction':float(clear.mean())}
    if clear.mean()<.8:
        return {'status':'rejected_cloud_or_nodata', **quality}
    rgb = []; calibration = {}
    for name in ['red','green','blue']:
        asset = assets[name]
        raw = read_window(asset['href'],bbox)
        scale,offset=calibration_for(asset,props)
        reflectance = raw*scale + offset
        calibration[name] = {'scale':scale,'offset':offset,'provider_boa_offset_applied':props.get('earthsearch:boa_offset_applied')}
        rgb.append(np.uint8(np.nan_to_num(np.clip(reflectance/0.3,0,1))**(1/2.2)*255))
        clear &= np.isfinite(raw)
    rgba = np.dstack(rgb+[np.uint8(clear)*255])
    name = item['id']+'.png'
    path = folder/name
    Image.fromarray(rgba).save(path,optimize=True)
    return {'status':'ready', **quality, 'path':path.relative_to(ROOT).as_posix(),
        'sha256':hashlib.sha256(path.read_bytes()).hexdigest(), 'bounds':bbox,
        'calibration':calibration,
        'processing':'AOI-only reads; EPSG:4326, 256x256; fixed reflectance stretch 0..0.3 and gamma 2.2 for every date; cloud/shadow/snow/nodata transparent'}


def run(site_id, search_only=False):
    site = json.loads((ROOT/f'data/{site_id}.json').read_text())
    folder = ROOT/f'data/{site_id}/optical'; folder.mkdir(parents=True,exist_ok=True)
    query, items = search(site)
    cached, entries = {}, []
    for target in site['dates']:
        chosen = None; rejected = []
        for item in select_candidates(items,target):
            identifier = item['id']
            if identifier not in cached:
                try:
                    cached[identifier] = {'status':'catalogue_only'} if search_only else make_preview(item,site['grid']['bbox'],folder)
                except Exception as error:
                    cached[identifier] = {'status':'read_failed','reason':str(error)[:300]}
            result = cached[identifier]
            if result['status'] not in ['ready','catalogue_only']:
                rejected.append({'scene_id':identifier,**result}); continue
            chosen = {'nisar_date':target,'source':'Copernicus Sentinel-2 L2A / Earth Search',
                'scene_id':identifier,'date':item['properties']['datetime'][:10],
                'scene_cloud_percent':item['properties'].get('eo:cloud_cover'),
                'item_url':next((l['href'] for l in item.get('links',[]) if l.get('rel')=='self'),None),
                'assets':{k:item['assets'][k]['href'] for k in ['red','green','blue','scl']},**result}
            break
        entries.append(chosen or {'nisar_date':target,'status':'unavailable','reason':'No readable scene with >=80% clear AOI in +/-15 days','rejected':rejected})
        print(site_id,target,entries[-1]['status'],flush=True)
    output = {'schema_version':1,'site':site_id,'bbox':site['grid']['bbox'],
        'checked_at':datetime.now(timezone.utc).isoformat(),'catalogue':STAC,'query':query,
        'selection':'lowest scene cloud fraction among scenes with >=80% locally clear AOI, then nearest date; +/-15 days',
        'entries':entries}
    (folder/'index.json').write_text(json.dumps(output,indent=2)+'\n')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--site',choices=['mexico','amazon','venezuela'])
    parser.add_argument('--search-only',action='store_true')
    args=parser.parse_args()
    for identifier in [args.site] if args.site else ['mexico','amazon','venezuela']:
        run(identifier,args.search_only)
