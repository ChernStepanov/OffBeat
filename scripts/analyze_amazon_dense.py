"""Summarise a pair of registered native Amazon GCOV windows; no event classification."""
import hashlib,json
from pathlib import Path
import numpy as np
from pyproj import Transformer
ROOT=Path(__file__).resolve().parents[1]

def main():
    folder=ROOT/'data/subsets/amazon-dense';dates=('2026-08-23','2026-09-04')
    meta=[json.loads((folder/f'{d}.json').read_text()) for d in dates]
    if meta[0]['grid']!=meta[1]['grid']:raise ValueError('Incompatible native grids')
    for m in meta:
        if hashlib.sha256((ROOT/m['subset_path']).read_bytes()).hexdigest()!=m['sha256']:raise ValueError('Hash mismatch')
    a,b=[np.load(ROOT/m['subset_path']) for m in meta]
    valid=(a['mask']>0)&(a['mask']<255)&(b['mask']>0)&(b['mask']<255)&np.isfinite(a['hv'])&np.isfinite(b['hv'])&(a['hv']>0)&(b['hv']>0)
    delta=np.full(a['hv'].shape,np.nan);delta[valid]=10*np.log10(b['hv'][valid]/a['hv'][valid])
    site=json.loads((ROOT/'data/amazon.json').read_text());p=site['pixels'][5*32+15];grid=meta[0]['grid'];x,y=Transformer.from_crs(4326,grid['epsg'],always_xy=True).transform(p['lon'],p['lat'])
    col=int(np.floor((x-grid['x_first'])/grid['x_step']+.5));row=int(np.floor((y-grid['y_first'])/grid['y_step']+.5))
    if not (1<=row<delta.shape[0]-1 and 1<=col<delta.shape[1]-1):raise ValueError('Candidate outside window')
    window=delta[row-1:row+2,col-1:col+2];finite=window[np.isfinite(window)]
    out={'source':'NASA-ISRO NISAR PROVISIONAL GCOV frequency A HHHH/HVHV, ASF DAAC',
      'dates':list(dates),'source_receipts':[(folder/f'{d}.json').relative_to(ROOT).as_posix() for d in dates],
      'grid':grid,'valid_count':int(valid.sum()),'total_count':int(valid.size),
      'method':'Same native 20 m grid and mask for both dates; require mask 1..254 and finite positive HV linear gamma0; calculate 10*log10(after/before). Candidate is nearest native cell to existing sample AMA r5 c15; neighbourhood is its 3x3 native cells.',
      'limitations':'Exploratory two-date change only; speckle, moisture, viewing geometry and provisional-product issues are not corrected. No event, area, cause, or validation is inferred; bbox window extends slightly beyond the geographic AOI.',
      'window_median_hv_change_db':round(float(np.median(delta[valid])),3),
      'window_hv_change_p10_p90_db':[round(float(v),3) for v in np.percentile(delta[valid],[10,90])],
      'candidate':{'sample':'AMA r5 c15','lat':p['lat'],'lon':p['lon'],'native_row':row,'native_col':col,
        'hv_change_db':round(float(delta[row,col]),3) if np.isfinite(delta[row,col]) else None,
        'local_3x3_valid':int(finite.size),'local_3x3_median_change_db':round(float(np.median(finite)),3) if finite.size else None}}
    outpath=ROOT/'data/analysis/amazon-dense-pair.json';outpath.write_text(json.dumps(out,indent=2)+'\n',encoding='utf-8');print(json.dumps(out['candidate']),flush=True)

if __name__=='__main__':main()
