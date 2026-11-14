"""Record public HLS candidates for missing optical dates; no authenticated image is invented."""
import json
from pathlib import Path
from datetime import date, timedelta
import requests

ROOT=Path(__file__).resolve().parents[1]

if __name__=='__main__':
    for identifier in ['mexico','amazon','venezuela']:
        path=ROOT/f'data/{identifier}/optical/index.json';index=json.loads(path.read_text())
        for entry in index['entries']:
            if entry['status']=='ready':continue
            day=date.fromisoformat(entry['nisar_date']);bbox=index['bbox'];checks=[]
            for short_name in ['HLSS30','HLSL30']:
                response=requests.get('https://cmr.earthdata.nasa.gov/search/granules.json',params={
                    'short_name':short_name,'bounding_box':','.join(str(bbox[k]) for k in ['w','s','e','n']),
                    'temporal':f'{day-timedelta(days=15)}T00:00:00Z,{day+timedelta(days=15)}T23:59:59Z',
                    'page_size':20,'sort_key':'start_date'},timeout=90)
                response.raise_for_status()
                checks.append({'source':short_name,'query':response.url,'hits':int(response.headers.get('CMR-Hits',0)),
                    'granules':[{'id':g['id'],'producer_id':g.get('producer_granule_id'),'date':g.get('time_start'),
                        'links':g.get('links')} for g in response.json()['feed']['entry']]})
            entry['hls_catalogue']=checks
            entry['hls_status']='catalogue_only: Earthdata required to inspect quality and render'
            print(identifier,entry['nisar_date'],[(c['source'],c['hits']) for c in checks],flush=True)
        path.write_text(json.dumps(index,indent=2)+'\n')
