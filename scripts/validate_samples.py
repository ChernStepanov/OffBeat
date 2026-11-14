"""Match sparse HV-drop candidates to dated alerts/fires without raster area claims."""
import json
from pathlib import Path
from shapely.geometry import Point, shape
from pyproj import Geod
from datetime import date

ROOT=Path(__file__).resolve().parents[1]


def validate(site, alerts, fires, days=60, radius_m=1000):
    geod=Geod(ellps='WGS84');rows=[]
    for p in site['pixels']:
        if p['style']!='drop' or not p['since']: continue
        since=date.fromisoformat(p['since']);point=Point(p['lon'],p['lat'])
        matched=[]
        for f in alerts['features']:
            stamp=f['properties'].get('date')
            if not stamp: continue
            lag=(since-date.fromisoformat(stamp[:10])).days
            if abs(lag)<=days and shape(f['geometry']).covers(point):
                matched.append({'source':f['properties'].get('source'),'date':stamp,'lag_days':lag})
        near=[]
        for fire in fires:
            lag=(since-date.fromisoformat(fire['date'][:10])).days
            if abs(lag)>days:continue
            distance=geod.inv(p['lon'],p['lat'],fire['lon'],fire['lat'])[2]
            if distance<=radius_m:near.append({'source':fire.get('source'),'date':fire['date'],'distance_m':round(distance,1)})
        rows.append({'id':p['id'],'lat':p['lat'],'lon':p['lon'],'cover':p['cover'],'since':p['since'],
            'alerts':matched,'fires':near,'status':'supporting context only' if matched else 'unknown: no matched alert'})
    return {'schema_version':1,'kind':'sparse_sample_validation','n_candidates':len(rows),
        'n_alert_matches':sum(bool(r['alerts']) for r in rows),'n_fire_matches':sum(bool(r['fires']) for r in rows),
        'max_days':days,'fire_radius_m':radius_m,'candidates':rows,'area_ha':None,'recall':None,
        'limitations':['Sparse points, no event area or recall estimate','Absence of an alert does not establish absence of change',
            'Alert match is supporting evidence, not independent confirmation of the cause',
            'No negative labels, no precision or accuracy estimate']}


if __name__=='__main__':
    site=json.loads((ROOT/'data/amazon.json').read_text())
    report=validate(site,json.loads((ROOT/'data/amazon/alerts.geojson').read_text()),json.loads((ROOT/'data/amazon/fires.json').read_text()))
    report['sources']={'alerts':'data/amazon/alerts.geojson','fires':'data/amazon/fires.json','analysis':'data/analysis/amazon.json'}
    (ROOT/'data/amazon/validation.json').write_text(json.dumps(report,indent=2)+'\n')
    print({k:report[k] for k in ['n_candidates','n_alert_matches','n_fire_matches']})
