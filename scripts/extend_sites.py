"""Extend Amazon/Venezuela GCOV with measured subsets and per-date provenance."""
import hashlib,json,re
from datetime import datetime,timezone
from pathlib import Path
import earthaccess,h5py,numpy as np,requests
from pyproj import Transformer
import subset_nisar as sub
from build_real_demos import CASES

def catalogue(site,bbox,track,frame):
    params={'short_name':'NISAR_L2_GCOV_PROVISIONAL_V1','bounding_box':','.join(str(bbox[k]) for k in ['w','s','e','n']),'page_size':2000,'sort_key':'start_date'}
    response=requests.get('https://cmr.earthdata.nasa.gov/search/granules.json',params=params,timeout=90);response.raise_for_status()
    if int(response.headers.get('CMR-Hits',0))>2000:raise ValueError('CMR pagination required')
    records=[]
    for g in response.json()['feed']['entry']:
        name=g['producer_granule_id']
        if not re.search(f'_GCOV_\\d+_{track:03}_A_{frame:03}_',name) or '_DHDH_' not in name:continue
        url=next((l['href'] for l in g['links'] if l['href'].startswith('https:') and l['href'].endswith('.h5') and l.get('rel','').endswith('/data#')),None)
        if url:records.append(dict(id=name,concept_id=g['id'],collection=g['collection_concept_id'],start=g['time_start'],end=g['time_end'],url=url))
    records.sort(key=lambda r:r['start'])
    return response.url,records

def main():
    candidates=[]
    for site,name,bbox,track,frame in CASES:
        path=sub.ROOT/'data'/f'{site}.json';data=json.loads(path.read_text())
        query,records=catalogue(site,bbox,track,frame)
        pending=[r for r in records if r['start'][:10]>data['dates'][-1]][:4]
        print(site,'catalogue',len(records),'next',[r['start'][:10] for r in pending],flush=True)
        candidates.append((site,name,bbox,track,frame,path,data,query,pending))
    if not any(c[-1] for c in candidates):return
    auth=earthaccess.login(strategy='interactive',persist=False)
    if not auth.authenticated:raise SystemExit('Earthdata login failed')
    fs=earthaccess.get_fsspec_https_session()
    for site,name,bbox,track,frame,path,data,query,records in candidates:
        sub.configure(site,name,bbox,track,frame); lat,lon=sub.coordinates()
        target=sub.ROOT/'data/subsets'/f'{site}-series';target.mkdir(parents=True,exist_ok=True)
        cover=np.array([p['cover'] or 0 for p in data['pixels']]);epsg=data['provenance']['inputs'][0]['grid']['epsg']
        east,north=Transformer.from_crs(4326,epsg,always_xy=True).transform(lon.ravel(),lat.ravel())
        for r in records:
            out=target/(r['start'][:10]+'.npz');receipt=out.with_suffix('.json')
            if not receipt.exists():
                with fs.open(r['url'],block_size=1024*1024,cache_type='blockcache') as stream,h5py.File(stream,'r') as hdf:
                    ident=hdf['science/LSAR/identification']
                    if (int(ident['trackNumber'][()]),int(ident['frameNumber'][()]),sub.scalar(ident['orbitPassDirection']))!=(track,frame,'Ascending'):raise ValueError('Incompatible acquisition')
                    group=hdf['science/LSAR/GCOV/grids/frequencyA']
                    values,grid=sub.grid_samples(group,{'hh':'HHHH','hv':'HVHV','mask':'mask'},lat,lon)
                    date=sub.scalar(ident['zeroDopplerStartTime'])[:10]
                    if date!=r['start'][:10] or grid['epsg']!=epsg:raise ValueError('Date or grid mismatch')
                    np.savez_compressed(out,lat=lat,lon=lon,**values)
                    record=dict(source=r,grid=grid,date=date,subset_path=out.relative_to(sub.ROOT).as_posix(),sha256=hashlib.sha256(out.read_bytes()).hexdigest(),catalogue_query=query)
                    receipt.write_text(json.dumps(record,indent=2)+'\n')
            record=json.loads(receipt.read_text())
            if record['source']['id']!=r['id'] or hashlib.sha256(out.read_bytes()).hexdigest()!=record['sha256']:raise ValueError('Subset hash/source mismatch')
            a=np.load(out)
            if not np.array_equal(a['lat'],lat) or not np.array_equal(a['lon'],lon):raise ValueError('Subset coordinates mismatch')
            mask=(a['mask']>0)&(a['mask']<255);values={}
            for k in ['hh','hv']:
                raw=a[k];valid=mask&np.isfinite(raw)&(raw>0);v=np.full(raw.shape,np.nan);v[valid]=10*np.log10(raw[valid]);values[k]=v
            for i,p in enumerate(data['pixels']):
                eligible=((east-east[i])**2+(north-north[i])**2<=1000**2)&(cover==cover[i])&(cover[i]!=0);eligible[i]=False
                for k in ['hh','hv']:
                    value=values[k].ravel()[i];p[k].append(round(float(value),5) if np.isfinite(value) else None)
                    arr=values[k].ravel();peers=arr[eligible&np.isfinite(arr)];p['peer_counts'][k].append(len(peers))
                    median=float(np.median(peers)) if len(peers)>=10 else None
                    spread=1.4826*float(np.median(np.abs(peers-median))) if median is not None else 0
                    p['peer'][k+'_med'].append(round(median,5) if median is not None else None);p['peer'][k+'_sd'].append(round(spread,5) if spread>0 else None)
                p['peers']=p['peer_counts']['hv'][-1]
            data['dates'].append(record['date']);data['provenance'].setdefault('additional_gcov',[]).append(record)
            data['provenance']['steps'].append('Additional same-track GCOV: native samples, valid mask and power, 10log10, same-class neighbours per date.')
            data['region']=f"Real GCOV {data['dates'][0]} – {data['dates'][-1]} · one GUNW pair"
            data['message']=f"Measured HH/HV on {len(data['dates'])} dates; GUNW remains the original pair. Missing or rejected samples remain unavailable."
            tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(data,allow_nan=False,separators=(',',':'))+'\n');tmp.replace(path)
            print(site,record['date'],'valid HH/HV',*[int(np.isfinite(values[k]).sum()) for k in ['hh','hv']],flush=True)

if __name__=='__main__':main()
