"""Recalculate matched-date, matched-point exploratory C/L class medians."""
import datetime as dt
import hashlib
import json
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]

def main():
    paths = [ROOT/'data/amazon.json', ROOT/'data/amazon/sentinel1.json']
    site, rtc = [json.loads(p.read_text(encoding='utf-8')) for p in paths]
    pairs=[]
    for i,date in enumerate(site['dates']):
        radar=dt.date.fromisoformat(date)
        eligible=[(abs((dt.date.fromisoformat(d)-radar).days),j) for j,d in enumerate(rtc['dates']) if abs((dt.date.fromisoformat(d)-radar).days)<=6]
        if eligible: pairs.append((i,min(eligible)[1]))
    out={'source':'NISAR GCOV L-band HV and NASA OPERA RTC-S1 C-band VH; ESA WorldCover 2021 classes',
         'inputs':[{ 'path':p.relative_to(ROOT).as_posix(), 'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in paths],
         'method':'For each NISAR date select nearest RTC date within 6 days, then use same sample points valid in both bands. For each class compute the median dB per date, then the median of those date medians. Forest minus grassland contrasts use these class medians.',
         'limitations':'Exploratory descriptive sample, not a causal or independent validation. WorldCover classes are from 2021; geometry, wavelength, spatial resolution, and sensing time differ. Samples are spatially correlated; no error bars or statistical significance are estimated.',
         'pairs':[], 'classes':{}}
    for i,j in pairs:
        out['pairs'].append({'nisar_date':site['dates'][i], 'rtc_date':rtc['dates'][j],
          'rtc_granules':[g for g in rtc['provenance']['granules'] if g['date']==rtc['dates'][j]]})
    for code,label in ((10,'forest'),(30,'grassland')):
        rows=[]
        for i,j in pairs:
            pts=[k for k,p in enumerate(site['pixels']) if p['cover']==code and p['hv'][i] is not None and rtc['points']['vh'][j][k] is not None]
            if pts:
                rows.append({'nisar_date':site['dates'][i],'rtc_date':rtc['dates'][j],'count':len(pts),
                  'c_vh_db':round(float(np.median([rtc['points']['vh'][j][k] for k in pts])),3),
                  'l_hv_db':round(float(np.median([site['pixels'][k]['hv'][i] for k in pts])),3)})
        out['classes'][label]={'per_date':rows,'c_vh_db':round(float(np.median([r['c_vh_db'] for r in rows])),3) if rows else None,
          'l_hv_db':round(float(np.median([r['l_hv_db'] for r in rows])),3) if rows else None}
    for band in ('c_vh_db','l_hv_db'):
        a,b=(out['classes'][x][band] for x in ('forest','grassland'))
        out.setdefault('forest_minus_grassland_db',{})[band]=round(a-b,3) if a is not None and b is not None else None
    p=ROOT/'data/analysis/amazon-c-l-matched.json';p.write_text(json.dumps(out,indent=2)+'\n',encoding='utf-8')
    print('matched dates:',len(pairs),'contrasts dB:',out['forest_minus_grassland_db'])

if __name__=='__main__': main()
