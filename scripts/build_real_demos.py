"""Select actual compatible CMR pairs, then extract small real Amazon/Venezuela cases."""
import argparse
import json
import re
from datetime import datetime,timezone
import requests
import earthaccess
import subset_nisar as subset

CASES=[('amazon','Itupiranga, Pará',dict(w=-49.2875,s=-4.7875,e=-49.2625,n=-4.7625),146,175),
       ('venezuela','Caracas and Catia La Mar',dict(w=-67.0925,s=10.4575,e=-67.0675,n=10.4825),162,7),
       ('delhi','New Delhi, India',dict(w=77.1975,s=28.5975,e=77.2225,n=28.6225),156,16),
       ('tokyo','Tokyo, Japan',dict(w=139.6775,s=35.6775,e=139.7025,n=35.7025),38,20)]

def discover(site,bbox,track,frame,pair_index=0):
    products={}
    queries=[]
    for kind in ['gcov','gunw']:
        params=dict(short_name=f'NISAR_L2_{kind.upper()}_PROVISIONAL_V1',bounding_box=','.join(str(bbox[k]) for k in ['w','s','e','n']),page_size=2000,sort_key='start_date')
        response=requests.get('https://cmr.earthdata.nasa.gov/search/granules.json',params=params,timeout=90)
        response.raise_for_status();queries.append(response.url)
        if int(response.headers.get('CMR-Hits',0))>2000: raise ValueError('CMR pagination required')
        products[kind]=[]
        for g in response.json()['feed']['entry']:
            name=g['producer_granule_id']
            if not re.search(f'_{kind.upper()}_\\d+_{track:03}_A_{frame:03}_',name):continue
            if kind=='gcov' and '_DHDH_' not in name:continue
            url=next((l['href'] for l in g['links'] if l['href'].startswith('https:') and l['href'].endswith('.h5') and l.get('rel','').endswith('/data#')),None)
            if url:products[kind].append(dict(id=name,concept_id=g['id'],collection=g['collection_concept_id'],start=g['time_start'],end=g['time_end'],url=url))
    bydate={g['start'][:10]:g for g in products['gcov']}
    compatible=[]
    for pair in products['gunw']:
        times=re.findall(r'\d{8}T\d{6}',pair['id'])
        dates=[f'{t[:4]}-{t[4:6]}-{t[6:8]}' for t in [times[0],times[2]]]
        if all(d in bydate for d in dates):
            compatible.append(dict(gcov=[bydate[d] for d in dates],gunw=[pair]))
    if len(compatible)<=pair_index:raise ValueError(f'No compatible real pair at index {pair_index} for {site}')
    selected=compatible[pair_index]
    dates=[g['start'][:10] for g in selected['gcov']]
    manifest=dict(site=site,checked_at=datetime.now(timezone.utc).isoformat(),queries=queries,products=selected,track=track,frame=frame,maturity='PROVISIONAL',bbox=bbox)
    (subset.ROOT/'data'/f'{site}-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(site,'selected',dates,flush=True)
    return manifest

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--site',choices=['all']+[c[0] for c in CASES],default='all')
    parser.add_argument('--pair-index',type=int,default=None)
    args=parser.parse_args()
    cases=[c for c in CASES if args.site=='all' or c[0]==args.site]
    indices=[args.pair_index if args.pair_index is not None else (2 if c[0]=='amazon' else 0) for c in cases]
    manifests=[discover(site,bbox,track,frame,index) for (site,_,bbox,track,frame),index in zip(cases,indices)]
    auth=earthaccess.login(strategy='interactive',persist=False)
    if not auth.authenticated:raise SystemExit('Earthdata login failed')
    fs=earthaccess.get_fsspec_https_session()
    for (site,name,bbox,track,frame),manifest,index in zip(cases,manifests,indices):
        subset.configure(site,name,bbox,track,frame)
        if index:
            dates=[g['start'][:10] for g in manifest['products']['gcov']]
            subset.TARGET=subset.TARGET/('_'.join(dates))
        subset.extract(manifest,fs)

if __name__=='__main__':main()
