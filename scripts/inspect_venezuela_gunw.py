"""Read the earthquake-spanning GUNW subset and report quality, without creating a displacement product."""
import hashlib,json,re
from pathlib import Path
import earthaccess,h5py,numpy as np,requests
import subset_nisar as sub
from build_real_demos import CASES

def main():
    site,name,bbox,track,frame=CASES[1];sub.configure(site,name,bbox,track,frame)
    params=dict(short_name='NISAR_L2_GUNW_PROVISIONAL_V1',bounding_box=','.join(str(bbox[k]) for k in ['w','s','e','n']),page_size=2000)
    response=requests.get('https://cmr.earthdata.nasa.gov/search/granules.json',params=params,timeout=90);response.raise_for_status()
    matches=[g for g in response.json()['feed']['entry'] if re.search(r'_GUNW_\d+_162_A_007_',g['producer_granule_id']) and '_20260613T' in g['producer_granule_id'] and '_20260625T' in g['producer_granule_id']]
    if len(matches)!=1:raise ValueError(f'Expected one pair, found {len(matches)}')
    g=matches[0];url=next(l['href'] for l in g['links'] if l['href'].startswith('https:') and l['href'].endswith('.h5') and l.get('rel','').endswith('/data#'))
    auth=earthaccess.login(strategy='interactive',persist=False)
    if not auth.authenticated:raise SystemExit('Earthdata login failed')
    fs=earthaccess.get_fsspec_https_session();lat,lon=sub.coordinates()
    with fs.open(url,block_size=1024*1024,cache_type='blockcache') as f,h5py.File(f,'r') as h:
        ident=h['science/LSAR/identification'];base=h['science/LSAR/GUNW/grids/frequencyA'];group=base['unwrappedInterferogram']
        if (int(ident['trackNumber'][()]),int(ident['frameNumber'][()]),sub.scalar(ident['orbitPassDirection']))!=(162,7,'Ascending'):raise ValueError('Wrong track')
        names={'phase':'HH/unwrappedPhase','coherence':'HH/coherenceMagnitude','component':'HH/connectedComponents','iono':'HH/ionospherePhaseScreen','iono_sd':'HH/ionospherePhaseScreenUncertainty','mask':'mask'}
        a,grid=sub.grid_samples(group,names,lat,lon)
        ref=sub.scalar(ident['referenceZeroDopplerStartTime'])[:10];sec=sub.scalar(ident['secondaryZeroDopplerStartTime'])[:10]
        if (ref,sec)!=('2026-06-13','2026-06-25'):raise ValueError('Wrong pair dates')
        freq=float(base['centerFrequency'][()]);mask=a['mask'].astype(np.uint32);subs=mask&255
        valid=(np.isfinite(a['phase'])&np.isfinite(a['iono'])&np.isfinite(a['coherence'])&(a['coherence']>=.7)&(a['component']>0)&(a['component']<65535)&(subs<100)&((subs//10)>0)&((subs%10)>0)&(((mask>>8)&65535)==0)&((mask&0xFE000000)==0)&np.isfinite(a['iono_sd'])&(a['iono_sd']<=1.0))
        target=sub.ROOT/'data/subsets/venezuela-gunw';target.mkdir(parents=True,exist_ok=True)
        output=target/'2026-06-13_2026-06-25.npz';np.savez_compressed(output,lat=lat,lon=lon,**a)
        report=dict(source={'id':g['producer_granule_id'],'concept_id':g['id'],'collection':g['collection_concept_id'],'url':url},catalogue_query=response.url,reference_date=ref,secondary_date=sec,center_frequency_hz=freq,grid=grid,subset_path=output.relative_to(sub.ROOT).as_posix(),sha256=hashlib.sha256(output.read_bytes()).hexdigest(),valid_samples=int(valid.sum()),sample_count=int(valid.size),quality_counts={'coherence_at_least_0_7':int((a['coherence']>=.7).sum()),'ionosphere_uncertainty_at_most_1_rad':int((a['iono_sd']<=1).sum())},steps=['Sample original phase, coherence, components, ionosphere, uncertainty and mask at native locations','Quality: coherence >=0.7, ionosphere uncertainty <=1 rad, valid nonwater subswaths, valid component and no anomaly flags','No spatial reference or displacement estimated in this exploratory quality check'])
        output.with_suffix('.json').write_text(json.dumps(report,indent=2)+'\n')
        print('GUNW valid samples:',report['valid_samples'],'/',report['sample_count'],flush=True)

if __name__=='__main__':main()
