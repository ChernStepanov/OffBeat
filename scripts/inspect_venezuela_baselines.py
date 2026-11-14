"""Inspect three same-track pre-event GUNW quality/coherence windows for Caracas."""
import hashlib, json, os, re
from pathlib import Path
import earthaccess, h5py, numpy as np, requests
import subset_nisar as sub
from build_real_demos import CASES

ROOT=Path(__file__).resolve().parents[1]

def main():
    site,name,bbox,track,frame=CASES[1];sub.configure(site,name,bbox,track,frame)
    params={'short_name':'NISAR_L2_GUNW_PROVISIONAL_V1','bounding_box':','.join(str(bbox[k]) for k in ('w','s','e','n')),'page_size':2000,'sort_key':'start_date'}
    response=requests.get('https://cmr.earthdata.nasa.gov/search/granules.json',params=params,timeout=90);response.raise_for_status()
    if int(response.headers.get('CMR-Hits',0))>2000:raise ValueError('Pagination required')
    dates={('20260508','20260520'),('20260520','20260601'),('20260601','20260613')}
    records=[]
    for g in response.json()['feed']['entry']:
        n=g['producer_granule_id']; m=re.search(r'_(2026\d{4})T\d{6}_\d{8}T\d{6}_(2026\d{4})T\d{6}_',n)
        if re.search(r'_GUNW_\d+_162_A_007_',n) and m and tuple(m.groups()) in dates:records.append((m.groups(),g))
    if len(records)!=3:raise ValueError('Expected three baseline granules')
    os.environ['EARTHDATA_TOKEN']=(ROOT/'.earthdata_token').read_text().strip()
    if not earthaccess.login(strategy='environment',persist=False).authenticated:raise RuntimeError('Authentication failed')
    fs=earthaccess.get_fsspec_https_session(); lat,lon=sub.coordinates(); target=ROOT/'data/subsets/venezuela-gunw';target.mkdir(parents=True,exist_ok=True)
    for (ref,sec),g in records:
        url=next(l['href'] for l in g['links'] if l['href'].startswith('https://nisar.asf.earthdatacloud.nasa.gov/') and l['href'].endswith('.h5') and l.get('rel','').endswith('/data#'))
        with fs.open(url,block_size=1024*1024,cache_type='blockcache') as f,h5py.File(f,'r') as h:
            ident=h['science/LSAR/identification']
            if (int(ident['trackNumber'][()]),int(ident['frameNumber'][()]),sub.scalar(ident['orbitPassDirection']))!=(162,7,'Ascending'):raise ValueError('Wrong track')
            actual=(sub.scalar(ident['referenceZeroDopplerStartTime'])[:10].replace('-',''),sub.scalar(ident['secondaryZeroDopplerStartTime'])[:10].replace('-',''))
            if actual!=(ref,sec):raise ValueError('Wrong pair')
            group=h['science/LSAR/GUNW/grids/frequencyA/unwrappedInterferogram']
            names={'coherence':'HH/coherenceMagnitude','component':'HH/connectedComponents','iono_sd':'HH/ionospherePhaseScreenUncertainty','mask':'mask'}
            a,grid=sub.grid_samples(group,names,lat,lon)
            mask=a['mask'].astype(np.uint32);subs=mask&255
            valid=(np.isfinite(a['coherence'])&(a['coherence']>=.7)&(a['component']>0)&(a['component']<65535)&(subs<100)&((subs//10)>0)&((subs%10)>0)&(((mask>>8)&65535)==0)&((mask&0xFE000000)==0)&np.isfinite(a['iono_sd'])&(a['iono_sd']<=1))
            path=target/f'{ref}_{sec}-baseline.npz';np.savez_compressed(path,lat=lat,lon=lon,**a)
            receipt={'source':{'id':g['producer_granule_id'],'concept_id':g['id'],'collection':g['collection_concept_id'],'url':url},'catalogue_query':response.url,'reference_date':ref,'secondary_date':sec,'grid':grid,'subset_path':path.relative_to(ROOT).as_posix(),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'sample_count':int(valid.size),'valid_quality_samples':int(valid.sum()),'quality_counts':{'coherence_at_least_0_7':int((a['coherence']>=.7).sum()),'ionosphere_uncertainty_at_most_1_rad':int((a['iono_sd']<=1).sum())},'method':'Sample native GUNW quality and coherence at original 32x32 points; same geometric and quality thresholds as earthquake-pair receipt. This is not a damage estimate.'}
            path.with_suffix('.json').write_text(json.dumps(receipt,indent=2)+'\n');print(ref,sec,'quality valid',valid.sum(),flush=True)

if __name__=='__main__':main()
