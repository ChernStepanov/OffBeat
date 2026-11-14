"""Inspect consecutive Mexico GUNW windows for one NISAR track, preserving raw quality layers."""
import argparse,hashlib,json,os,re
from pathlib import Path
import earthaccess,h5py,numpy as np,requests
import subset_nisar as sub
ROOT=Path(__file__).resolve().parents[1]

def main():
    parser=argparse.ArgumentParser();parser.add_argument('direction',choices=['ascending','descending']);parser.add_argument('--limit',type=int,default=3);args=parser.parse_args()
    spec={'ascending':(19,11,'A','Ascending'),'descending':(113,79,'D','Descending')}[args.direction]
    track,frame,letter,word=spec;sub.configure('mexico','Mexico City',dict(w=-99.09,s=19.415,e=-99.065,n=19.44),track,frame)
    params={'short_name':'NISAR_L2_GUNW_PROVISIONAL_V1','bounding_box':'-99.09,19.415,-99.065,19.44','page_size':2000,'sort_key':'start_date'}
    resp=requests.get('https://cmr.earthdata.nasa.gov/search/granules.json',params=params,timeout=90);resp.raise_for_status()
    if int(resp.headers.get('CMR-Hits',0))>2000:raise RuntimeError('CMR pagination required')
    gs=[g for g in resp.json()['feed']['entry'] if re.search(rf'_GUNW_\d+_{track:03}_{letter}_{frame:03}_',g['producer_granule_id'])]
    gs.sort(key=lambda g:g['time_start']);gs=gs[:args.limit]
    if len(gs)<args.limit:raise ValueError('Too few granules')
    os.environ['EARTHDATA_TOKEN']=(ROOT/'.earthdata_token').read_text().strip()
    if not earthaccess.login(strategy='environment',persist=False).authenticated:raise RuntimeError('Authentication failed')
    fs=earthaccess.get_fsspec_https_session();lat,lon=sub.coordinates();target=ROOT/'data/subsets/mexico-gunw-series'/args.direction;target.mkdir(parents=True,exist_ok=True)
    prev=None
    for g in gs:
        url=next(l['href'] for l in g['links'] if l['href'].startswith('https://nisar.asf.earthdatacloud.nasa.gov/') and l['href'].endswith('.h5') and l.get('rel','').endswith('/data#'))
        with fs.open(url,block_size=1024*1024,cache_type='blockcache') as f,h5py.File(f,'r') as h:
            ident=h['science/LSAR/identification']; observed=(int(ident['trackNumber'][()]),int(ident['frameNumber'][()]),sub.scalar(ident['orbitPassDirection']))
            if observed!=(track,frame,word):raise ValueError('Track/direction mismatch')
            ref=sub.scalar(ident['referenceZeroDopplerStartTime'])[:10];sec=sub.scalar(ident['secondaryZeroDopplerStartTime'])[:10]
            if prev and ref!=prev:raise ValueError('Consecutive pairs do not connect')
            prev=sec;base=h['science/LSAR/GUNW/grids/frequencyA'];grp=base['unwrappedInterferogram'];
            names={'phase':'HH/unwrappedPhase','coherence':'HH/coherenceMagnitude','component':'HH/connectedComponents','iono':'HH/ionospherePhaseScreen','iono_sd':'HH/ionospherePhaseScreenUncertainty','mask':'mask'}
            a,grid=sub.grid_samples(grp,names,lat,lon);mask=a['mask'].astype(np.uint32);sw=mask&255
            valid=(np.isfinite(a['phase'])&np.isfinite(a['iono'])&np.isfinite(a['coherence'])&(a['coherence']>=.7)&(a['component']>0)&(a['component']<65535)&(sw<100)&((sw//10)>0)&((sw%10)>0)&(((mask>>8)&65535)==0)&((mask&0xFE000000)==0)&np.isfinite(a['iono_sd'])&(a['iono_sd']<=1))
            path=target/f'{ref}_{sec}.npz';np.savez_compressed(path,lat=lat,lon=lon,**a)
            r={'source':{'id':g['producer_granule_id'],'concept_id':g['id'],'collection':g['collection_concept_id'],'url':url},'catalogue_query':resp.url,'reference_date':ref,'secondary_date':sec,'identification':{'track':track,'frame':frame,'direction':word,'look_direction':sub.scalar(ident['lookDirection'])},'center_frequency_hz':float(base['centerFrequency'][()]),'grid':grid,'subset_path':path.relative_to(ROOT).as_posix(),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'sample_count':int(valid.size),'quality_valid_count':int(valid.sum()),'steps':['Sample native GUNW HH phase, coherence, components, ionosphere and uncertainty at 32x32 existing points','Use previous quality mask coherence >=0.7, valid nonwater subswaths, valid connected component, no anomaly flags and ionosphere uncertainty <=1 rad','No displacement rate or stable reference claimed']}
            path.with_suffix('.json').write_text(json.dumps(r,indent=2)+'\n');print(word,ref,sec,'quality valid',valid.sum(),flush=True)

if __name__=='__main__':main()
