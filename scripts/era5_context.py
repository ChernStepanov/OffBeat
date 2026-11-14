"""Reproduce coarse ERA5 precipitation context before each Amazon NISAR date.

ERA5 is a reanalysis, not a local rain gauge; no claim of independent validation
or causal weather correction is made. Full UTC days before acquisition are used,
so no part of the acquisition day or later observations enters the windows.
"""
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import requests

ROOT=Path(__file__).resolve().parents[1]
URL='https://archive-api.open-meteo.com/v1/archive'


def summarize(dates, daily):
    by_day=dict(zip(daily['time'],daily['precipitation_sum']))
    output=[]
    for stamp in dates:
        day=date.fromisoformat(stamp);windows={}
        for length in (1,3,7):
            selected=[by_day.get((day-timedelta(days=i)).isoformat()) for i in range(1,length+1)]
            windows[f'previous_{length}_utc_days_mm']=round(sum(selected),2) if all(v is not None for v in selected) else None
        output.append({'nisar_date':stamp,**windows})
    return output


def run():
    site=json.loads((ROOT/'data/amazon.json').read_text())
    b=site['grid']['bbox'];dates=site['dates']
    params={'latitude':(b['s']+b['n'])/2,'longitude':(b['w']+b['e'])/2,
        'start_date':str(date.fromisoformat(dates[0])-timedelta(days=7)),
        'end_date':str(date.fromisoformat(dates[-1])-timedelta(days=1)),
        'daily':'precipitation_sum','models':'era5','timezone':'GMT'}
    response=requests.get(URL,params=params,timeout=90);response.raise_for_status();data=response.json()
    if 'daily' not in data or data.get('daily_units',{}).get('precipitation_sum')!='mm':
        raise ValueError('ERA5 response lacks millimetre daily precipitation')
    result={'source':'ECMWF ERA5 reanalysis via Open-Meteo historical weather API',
        'query':response.url,'retrieved_at':datetime.now(timezone.utc).isoformat(),
        'requested_location':[params['latitude'],params['longitude']],
        'returned_grid_location':[data.get('latitude'),data.get('longitude')],
        'nominal_resolution_degrees':0.25,'time_zone':'UTC','units':'mm',
        'windows':'full days immediately before the UTC acquisition date; acquisition day excluded',
        'availability':'retrospective ERA5 reanalysis; original availability date per daily value not established',
        'limitations':['coarse reanalysis estimate; not a pixel-scale rain observation',
          'not NASA GPM IMERG; not independent event confirmation',
          'not used for weather correction or a forecast model',
          'retrospective access can introduce availability leakage if used in a historical operational forecast'],
        'daily':data['daily'],'acquisitions':summarize(dates,data['daily'])}
    path=ROOT/'data/analysis/amazon-era5.json';path.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result['acquisitions'],indent=2))


if __name__=='__main__':run()
