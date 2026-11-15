"""Recompute leave-one-out peers and exploratory curve shapes on real sparse samples.

No area estimates, spatial interpolation, weather correction or event attribution.
Run from repository root: python -m scripts.analyze_samples
"""
import hashlib
import json
from pathlib import Path
import numpy as np
from pyproj import Transformer
from scipy.spatial import cKDTree
from pipeline.classify import classify, STYLES

ROOT = Path(__file__).resolve().parents[1]


def finite(value):
    return round(float(value),5) if np.isfinite(value) else None


def analyze(site, radius=1000, minimum=10):
    pixels = site['pixels']; count = len(pixels); dates = site['dates']
    lat=np.array([p['lat'] for p in pixels]); lon=np.array([p['lon'] for p in pixels])
    crs = 32600+int((float(lon.mean())+180)//6)+1 if lat.mean()>=0 else 32700+int((float(lon.mean())+180)//6)+1
    x,y=Transformer.from_crs(4326,crs,always_xy=True).transform(lon,lat)
    nearby=cKDTree(np.column_stack([x,y])).query_ball_point(np.column_stack([x,y]),radius)
    cover=np.array([p['cover'] or 0 for p in pixels])
    signals={k:np.array([[np.nan if v is None else v for v in p[k]] for p in pixels]) for k in ['hh','hv']}
    z={k:np.full((count,len(dates)),np.nan) for k in signals}
    for i,p in enumerate(pixels):
        peers=np.array([j for j in nearby[i] if j!=i and cover[j]==cover[i]],dtype=int)
        if cover[i] in [0,70,80]: peers=np.array([],dtype=int)
        p['peer_counts']={}
        for channel, values in signals.items():
            medians=[]; spreads=[]; counts=[]
            for t in range(len(dates)):
                values_t=values[peers,t]; values_t=values_t[np.isfinite(values_t)]
                counts.append(len(values_t)); median=spread=np.nan
                if len(values_t)>=minimum:
                    median=float(np.median(values_t)); spread=1.4826*float(np.median(np.abs(values_t-median)))
                    if spread>1e-6 and np.isfinite(values[i,t]): z[channel][i,t]=(values[i,t]-median)/spread
                medians.append(finite(median)); spreads.append(finite(spread) if spread>1e-6 else None)
            p['peer'][channel+'_med']=medians; p['peer'][channel+'_sd']=spreads
            p['peer_counts'][channel]=counts; p['z_'+channel]=[finite(v) for v in z[channel][i]]
        p['peers']=p['peer_counts']['hv'][-1]
    result=classify(z['hh'].T[:,None,:],z['hv'].T[:,None,:])
    reviews=[]
    for i,p in enumerate(pixels):
        p['z']=finite(result['z'][0,i]); style=STYLES[int(result['style'][0,i])]
        p['style']=style; idx=int(result['since'][0,i]); p['since']=dates[idx] if style and idx>=0 else None
        p['interpretation']='unverified curve-shape candidate' if style else 'no classified shape'
        # Simple own-history baseline and neighbour-relative change, both on the same dates.
        before=signals['hv'][i,:2]; after=signals['hv'][i,-2:]
        own=float(np.mean(after)-np.mean(before)) if len(dates)>=4 and np.isfinite(before).all() and np.isfinite(after).all() else np.nan
        relative=signals['hv'][i]-np.array([np.nan if v is None else v for v in p['peer']['hv_med']])
        rel=float(relative[-2:].mean()-relative[:2].mean()) if len(dates)>=4 and np.isfinite(relative[:2]).all() and np.isfinite(relative[-2:]).all() else np.nan
        reviews.append({'id':p['id'],'lat':p['lat'],'lon':p['lon'],'cover':p['cover'],'z':p['z'],
            'style':style,'since':p['since'],'hh':p['hh'],'hv':p['hv'],
            'own_history_hv_change_db':finite(own),'peer_relative_hv_change_db':finite(rel),
            'status':'unknown: no independent dated validation', 'valid_peer_count':p['peers']})
    source=json.dumps({'dates':dates,'samples':[{k:p[k] for k in ['id','lat','lon','cover','hh','hv']} for p in pixels]},sort_keys=True).encode()
    site['provenance']['sample_analysis']={'script':'scripts/analyze_samples.py','input_sha256':hashlib.sha256(source).hexdigest(),
        'radius_m':radius,'minimum_valid_peers':minimum,'exclude_self':True,'spread':'1.4826 * MAD; zero spread unavailable',
        'z_definition':'(sample dB - same-class local median dB) / robust spread dB',
        'classifier':'pipeline.classify; >=2 valid samples per segment; shift >=2.5 robust units',
        'limitations':['WorldCover 2021 may be outdated','Sparse samples, no area or continuous raster',
            'Curve shapes are not confirmed clearing, flood, earthquake or subsidence','No weather correction or labelled accuracy estimate']}
    site['analysis_status']='exploratory_sparse_samples'
    if len(dates) < 4:
        displacement = 'GUNW has quality-filtered samples on a separate date axis.' if any(p.get('disp') for p in pixels) else 'No GUNW displacement samples passed quality checks.'
        site['message']=f"Measured HH/HV on {len(dates)} dates; exploratory peer deviations only. Too few dates for curve-shape classification. {displacement}"
    else:
        site['message']=f"Measured HH/HV on {len(dates)} dates; exploratory peer deviations and curve shapes. Event cause unverified; GUNW remains separate."
    medians=[]
    for t,d in enumerate(dates):
        medians.append({'date':d,'classes':{str(c):{'n':int(np.isfinite(signals['hv'][cover==c,t]).sum()),
            'hv_median_db':finite(np.nanmedian(signals['hv'][cover==c,t]))} for c in sorted(set(cover)) if c}})
    ranked=sorted(reviews,key=lambda r:abs(r['peer_relative_hv_change_db'] or 0),reverse=True)
    return {'site':site['id'],'dates':dates,'input_sha256':site['provenance']['sample_analysis']['input_sha256'],
        'valid_latest_z':sum(p['z'] is not None for p in pixels),
        'shape_counts':{name:sum(p['style']==name for p in pixels) for name in ['drop','flood','drift','step']},
        'class_medians':medians,'review_top10':ranked[:10],
        'controls':[reviews[i] for i in np.random.default_rng(20261114).choice(count,10,replace=False)],
        'requested_candidate':next((r for r in reviews if r['id']=='AMA r5 c15'),None),
        'limitations':site['provenance']['sample_analysis']['limitations']}


if __name__=='__main__':
    folder=ROOT/'data/analysis';folder.mkdir(exist_ok=True)
    for identifier in ['mexico','amazon','venezuela','delhi','tokyo','nairobi','sydney']:
        path=ROOT/f'data/{identifier}.json';site=json.loads(path.read_text())
        report=analyze(site)
        path.write_text(json.dumps(site,allow_nan=False,separators=(',',':'))+'\n')
        (folder/f'{identifier}.json').write_text(json.dumps(report,allow_nan=False,indent=2)+'\n')
        print(identifier,report['valid_latest_z'],report['shape_counts'],flush=True)
