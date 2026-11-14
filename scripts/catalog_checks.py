"""Save public CMR/USGS evidence for issues 21, 35 and 36; no credentials required."""
import json
from datetime import datetime, timezone
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parents[1]
CMR = 'https://cmr.earthdata.nasa.gov/search/'


def get(url, **params):
    response = requests.get(url, params=params, timeout=90, headers={'User-Agent':'OffBeat-science-audit/1.0'})
    response.raise_for_status()
    return response, response.json()


def check(site_id, pattern):
    site = json.loads((ROOT / f'data/{site_id}.json').read_text())
    b = site['grid']['bbox']
    response, data = get(CMR+'collections.json', short_name=pattern,
                         **{'options[short_name][pattern]':'true', 'page_size':100})
    result = {'site':site_id, 'bbox':b, 'collection_query':response.url, 'collections':[]}
    for collection in data['feed']['entry']:
        response, granules = get(CMR+'granules.json', collection_concept_id=collection['id'],
            bounding_box=','.join(str(b[k]) for k in ['w','s','e','n']), page_size=20, sort_key='-start_date')
        result['collections'].append({'id':collection['id'], 'short_name':collection['short_name'],
            'query':response.url, 'hits':int(response.headers.get('CMR-Hits',0)),
            'granules':[{'id':g['id'], 'producer_id':g.get('producer_granule_id'),
                'start':g.get('time_start'), 'end':g.get('time_end'), 'polygons':g.get('polygons'),
                'links':g.get('links')} for g in granules['feed']['entry']]})
    result['coverage'] = 'catalogue_overlap' if any(c['hits'] for c in result['collections']) else 'no_catalogue_overlap'
    result['limitation'] = 'Catalogue footprint overlap does not establish valid pixel coverage; authenticated data inspection required.'
    return result


if __name__ == '__main__':
    output = ROOT / 'data/evidence'; output.mkdir(exist_ok=True)
    for site, pattern, name in [('mexico','OPERA_L3_DISP*','mexico-opera-disp'), ('amazon','OPERA_L2_RTC*','amazon-opera-rtc')]:
        result = check(site,pattern)
        result['checked_at'] = datetime.now(timezone.utc).isoformat()
        (output/f'{name}.json').write_text(json.dumps(result,indent=2)+'\n')
        print(name, result['coverage'], [(c['short_name'],c['hits']) for c in result['collections']],flush=True)
    response, data = get('https://earthquake.usgs.gov/fdsnws/event/1/query',format='geojson',
        starttime='2026-06-24',endtime='2026-06-25',minlatitude=9,maxlatitude=12,
        minlongitude=-70,maxlongitude=-65,minmagnitude=7)
    evidence = {'checked_at':datetime.now(timezone.utc).isoformat(),'query':response.url,'response':data}
    (output/'venezuela-usgs.json').write_text(json.dumps(evidence,indent=2)+'\n')
    print('USGS',[(f['id'],f['properties']['mag']) for f in data['features']],flush=True)
