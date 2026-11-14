"""Add actual same-track GCOV acquisitions to the Mexico preview, keeping GUNW independent."""
import hashlib
import json
from pathlib import Path
import earthaccess
import h5py
import numpy as np
from pyproj import Transformer
import subset_nisar as sub
from analyze_preview import analyze_site

def main():
    root=sub.ROOT
    site=json.loads((root/'data/mexico.json').read_text())
    manifest=json.loads((root/'data/mexico-manifest.json').read_text())
    records=manifest['products']['gcov']
    lat,lon=sub.coordinates()
    if [r['start'][:10] for r in records[:2]] != site['dates'][:2]: raise ValueError('Unexpected existing acquisitions')
    expected=[r['start'][:10] for r in records]
    if site['dates']==expected:
        for item in site['provenance'].get('additional_gcov',[]):
            if hashlib.sha256((root/item['subset_path']).read_bytes()).hexdigest()!=item['sha256']:raise ValueError('Invalid saved subset')
        if len(site['provenance'].get('additional_gcov',[]))!=len(expected)-2:raise ValueError('Incomplete provenance')
        print(f'{len(expected)} acquisitions already exported and verified')
        analyze_site(site)
        temp=root/'data/mexico.tmp'
        temp.write_text(json.dumps(site,allow_nan=False,separators=(',',':'))+'\n')
        temp.replace(root/'data/mexico.json')
        return
    if site['dates']!=expected[:len(site['dates'])]:raise ValueError('Unexpected existing date series')
    auth=earthaccess.login(strategy='interactive',persist=False)
    if not auth.authenticated: raise SystemExit('Earthdata login failed')
    fs=earthaccess.get_fsspec_https_session()
    target=root/'data/subsets/mexico-series'
    target.mkdir(parents=True,exist_ok=True)
    new=[]
    for r in records[len(site['dates']):]:
        path=target/(r['start'][:10]+'.npz'); receipt=path.with_suffix('.json')
        if not receipt.exists():
            with fs.open(r['url'],block_size=1024*1024,cache_type='blockcache') as stream, h5py.File(stream,'r') as hdf:
                ident=hdf['science/LSAR/identification']
                if (int(ident['trackNumber'][()]),int(ident['frameNumber'][()]),sub.scalar(ident['orbitPassDirection']))!=(19,11,'Ascending'): raise ValueError('Incompatible geometry')
                group=hdf['science/LSAR/GCOV/grids/frequencyA']
                values,grid=sub.grid_samples(group,{'hh':'HHHH','hv':'HVHV','mask':'mask'},lat,lon)
                date=sub.scalar(ident['zeroDopplerStartTime'])[:10]
                if date!=r['start'][:10]:raise ValueError('Date mismatch')
                np.savez_compressed(path,lat=lat,lon=lon,**values)
                record=dict(source=r,grid=grid,date=date,subset_path=path.relative_to(root).as_posix(),sha256=hashlib.sha256(path.read_bytes()).hexdigest())
                receipt.write_text(json.dumps(record,indent=2)+'\n')
        record=json.loads(receipt.read_text())
        if record['source']['id']!=r['id'] or hashlib.sha256(path.read_bytes()).hexdigest()!=record['sha256']:raise ValueError('Invalid cached subset')
        a=np.load(path); mask=(a['mask']>0)&(a['mask']<255)
        values={}
        for k in ['hh','hv']:
            power=a[k]; good=mask&np.isfinite(power)&(power>0)
            v=np.full(power.shape,np.nan);v[good]=10*np.log10(power[good]);values[k]=v
        print(record['date'], 'valid HH/HV',*[int(np.isfinite(values[k]).sum()) for k in ['hh','hv']],flush=True)
        new.append((record,values))
    cover=np.array([p['cover'] or 0 for p in site['pixels']]); east,north=Transformer.from_crs(4326,32614,always_xy=True).transform(lon.ravel(),lat.ravel())
    for record,values in new:
        for i,p in enumerate(site['pixels']):
            eligible=((east-east[i])**2+(north-north[i])**2<=1000**2)&(cover==cover[i])&(cover[i]!=0);eligible[i]=False
            for k in ['hh','hv']:
                value=values[k].ravel()[i];p[k].append(round(float(value),5) if np.isfinite(value) else None)
                arr=values[k].ravel(); peers=arr[eligible&np.isfinite(arr)];p['peer_counts'][k].append(len(peers))
                median=float(np.median(peers)) if len(peers)>=10 else None
                spread=1.4826*float(np.median(np.abs(peers-median))) if median is not None else 0
                p['peer'][k+'_med'].append(round(median,5) if median is not None else None)
                p['peer'][k+'_sd'].append(round(spread,5) if spread>0 else None)
            p['peers']=p['peer_counts']['hv'][-1]
        site['dates'].append(record['date'])
    site['provenance'].setdefault('additional_gcov',[]).extend(r for r,_ in new)
    site['provenance']['steps'].append('Additional same-track GCOV: validate grid, mask and acquisition date; sample native HH/HV and recompute same-class 1 km peer medians and MAD independently per date.')
    site['region']=f"Real GCOV {site['dates'][0]} – {site['dates'][-1]} · one GUNW pair"
    site['message']=f"Measured HH/HV on {len(site['dates'])} dates; LOS remains one 12-day pair. Atmospheric residuals remain; no trend or anomaly classification."
    analyze_site(site)
    temp=root/'data/mexico.tmp';temp.write_text(json.dumps(site,allow_nan=False,separators=(',',':'))+'\n');temp.replace(root/'data/mexico.json')
    print('Exported',len(site['dates']),'GCOV dates',flush=True)

if __name__=='__main__':main()
