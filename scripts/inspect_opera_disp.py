"""Sample OPERA DISP-S1 common-reference Mexico frame at the existing NISAR points.
Reads metadata and small windows only. Values failing recommended_mask are null.
"""
import datetime as dt
import hashlib
import json
import os
from pathlib import Path

import earthaccess
import h5py
import numpy as np
from pyproj import CRS, Transformer

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'data/mexico/opera-disp.json'


def main():
    token = (ROOT / '.earthdata_token').read_text().strip()
    os.environ['EARTHDATA_TOKEN'] = token
    if not earthaccess.login(strategy='environment', persist=False).authenticated:
        raise RuntimeError('Earthdata login failed')
    site = json.loads((ROOT / 'data/mexico.json').read_text())
    points = site['pixels']
    evidence = json.loads((ROOT / 'data/evidence/mexico-opera-disp.json').read_text())
    granules = [g for g in evidence['collections'][0]['granules'] if '_F01088_VV_20251225T003922Z_' in g['producer_id']]
    if len(granules) < 5:
        raise ValueError('Insufficient common-reference granules')
    granules.sort(key=lambda g: g['producer_id'].split('_')[7])
    fs = earthaccess.get_fsspec_https_session()
    result = {'source':'NASA OPERA L3 DISP-S1 v1 / ASF DAAC', 'collection':'C3294057315-ASF',
              'catalogue_evidence':'data/evidence/mexico-opera-disp.json', 'frame':'F01088',
              'reference_date':'2025-12-25', 'retrieved_utc':dt.datetime.now(dt.timezone.utc).isoformat(),
              'units':'meters, LOS positive toward satellite',
              'method':'Nearest 30 m product-cell centre to each existing NISAR sample coordinate; retain only recommended_mask=1 and finite values. No resampling or gap filling.',
              'limitations':'Observations share a product reference date but may have different unwrapping components. No independently stable reference, atmospheric correction or north/south motion constraint has been assessed. Short-wavelength values are spatially filtered at 30 km. No vertical motion inferred.',
              'points_sha256':hashlib.sha256(json.dumps([(p['lat'],p['lon']) for p in points]).encode()).hexdigest(), 'granules':[]}
    OUT.parent.mkdir(parents=True,exist_ok=True)
    for g in granules:
        url=next(l['href'] for l in g['links'] if l['href'].startswith('https://cumulus.asf.earthdatacloud.nasa.gov/') and l['href'].endswith('.nc'))
        try:
            with fs.open(url,block_size=1048576,cache_type='blockcache') as f,h5py.File(f,'r') as h:
                crs=CRS.from_wkt(h['spatial_ref'].attrs['crs_wkt'])
                tr=Transformer.from_crs(4326,crs,always_xy=True)
                xx,yy=tr.transform([p['lon'] for p in points],[p['lat'] for p in points])
                gx=h['x'][:]; gy=h['y'][:]
                cols=np.rint((np.asarray(xx)-gx[0])/(gx[1]-gx[0])).astype(int)
                rows=np.rint((np.asarray(yy)-gy[0])/(gy[1]-gy[0])).astype(int)
                inside=(cols>=0)&(cols<len(gx))&(rows>=0)&(rows<len(gy))
                if not inside.all(): raise ValueError('AOI outside frame')
                r0,r1=int(rows.min()),int(rows.max())+1;c0,c1=int(cols.min()),int(cols.max())+1
                q=h['recommended_mask'][r0:r1,c0:c1][rows-r0,cols-c0]
                vals={}
                for name in ('displacement','short_wavelength_displacement'):
                    v=h[name][r0:r1,c0:c1][rows-r0,cols-c0]
                    vals[name]=[round(float(x),6) if ok==1 and np.isfinite(x) else None for x,ok in zip(v,q)]
                def scalar(name):
                    v=h['identification'][name][()]
                    return v.decode() if isinstance(v,bytes) else str(v)
                ref=scalar('reference_zero_doppler_start_time')[:10];sec=scalar('secondary_zero_doppler_start_time')[:10]
                if ref != '2025-12-25': raise ValueError('Unexpected reference')
                result['granules'].append({'id':g['producer_id'],'concept_id':g['id'],'url':url,'reference_date':ref,'secondary_date':sec,
                  'valid_samples':sum(v is not None for v in vals['displacement']),'values':vals})
                print(sec,'valid:',result['granules'][-1]['valid_samples'],flush=True)
        except Exception as exc:
            result['granules'].append({'id':g['producer_id'],'concept_id':g['id'],'error':type(exc).__name__})
            print(g['id'],'unavailable:',type(exc).__name__,flush=True)
        OUT.write_text(json.dumps(result,separators=(',',':'))+'\n',encoding='utf-8')


if __name__ == '__main__': main()
