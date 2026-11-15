"""Download bounded native GCOV windows for one existing demo; local files only."""
import argparse
import hashlib
import json
import os
import re
from pathlib import Path

import earthaccess
import h5py
import numpy as np
from pyproj import Transformer

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('site', choices=('mexico','venezuela','delhi','tokyo','nairobi','sydney'))
args = parser.parse_args()
site = json.loads((ROOT / 'data' / (args.site + '.json')).read_text(encoding='utf-8'))
items = site['provenance']['inputs'][:2]
dates = site['dates'][:2]
def signature(record):
    name = record['source']['id']
    match = re.search(r'_GCOV_\d+_(\d{3})_([AD])_(\d{3})_\d+_(DHDH)_', name)
    if not match:
        raise ValueError('Missing same-track HH/HV granule signature')
    return match.groups()
if len(items) != 2 or signature(items[0]) != signature(items[1]):
    raise ValueError('The two GCOV granules have incompatible track/frame/polarization')
token_path = ROOT / '.earthdata_token'
if not token_path.exists():
    raise SystemExit('Earthdata Login token is unavailable')
os.environ['EARTHDATA_TOKEN'] = token_path.read_text(encoding='utf-8').strip()
if not earthaccess.login(strategy='environment', persist=False).authenticated:
    raise SystemExit('Earthdata Login authentication failed')
fs = earthaccess.get_fsspec_https_session()
folder = ROOT / 'data' / 'subsets' / (args.site + '-dense')
folder.mkdir(parents=True,exist_ok=True)
previous_grid = None
for date, item in zip(dates,items):
    output = folder / (date + '.npz')
    receipt = folder / (date + '.json')
    if receipt.exists() and output.exists():
        existing = json.loads(receipt.read_text(encoding='utf-8'))
        if existing['source']['id'] != item['source']['id'] or hashlib.sha256(output.read_bytes()).hexdigest() != existing['sha256']:
            raise ValueError('Existing subset hash or source mismatch')
        grid = existing['grid']
    else:
        with fs.open(item['source']['url'], block_size=1024*1024, cache_type='blockcache') as stream, h5py.File(stream,'r') as h:
            ident = h['science/LSAR/identification']
            scalar = lambda v: v.decode() if isinstance(v,bytes) else v.item() if isinstance(v,np.generic) else v
            actual = (int(ident['trackNumber'][()]), scalar(ident['orbitPassDirection'][()]), int(ident['frameNumber'][()]))
            expected = (int(signature(item)[0]), 'Ascending' if signature(item)[1] == 'A' else 'Descending', int(signature(item)[2]))
            if actual != expected or scalar(ident['zeroDopplerStartTime'][()])[:10] != date:
                raise ValueError('Granule identification does not match source receipt')
            g = h['science/LSAR/GCOV/grids/frequencyA']; xs=g['xCoordinates'][:]; ys=g['yCoordinates'][:]
            epsg=int(g['projection'][()]); tr=Transformer.from_crs(4326,epsg,always_xy=True); b=site['grid']['bbox']
            xx,yy=tr.transform([b['w'],b['e'],b['w'],b['e']],[b['s'],b['s'],b['n'],b['n']])
            cs=(np.asarray(xx)-xs[0])/(xs[1]-xs[0]); rs=(np.asarray(yy)-ys[0])/(ys[1]-ys[0])
            c0,c1=int(np.floor(min(cs))),int(np.ceil(max(cs)))+1; r0,r1=int(np.floor(min(rs))),int(np.ceil(max(rs)))+1
            if r0<0 or c0<0 or r1>len(ys) or c1>len(xs): raise ValueError('AOI outside granule grid')
            grid={'epsg':epsg,'window':[r0,r1,c0,c1],'x_first':float(xs[c0]),'y_first':float(ys[r0]),'x_step':float(xs[1]-xs[0]),'y_step':float(ys[1]-ys[0]),'shape':[r1-r0,c1-c0]}
            if previous_grid is not None and grid != previous_grid: raise ValueError('Native grids do not match')
            values={k:np.asarray(g[v][r0:r1,c0:c1]) for k,v in {'hh':'HHHH','hv':'HVHV','mask':'mask'}.items()}
            np.savez_compressed(output,**values)
        result={'site':args.site,'source':item['source'],'date':date,'grid':grid,
                'subset_path':output.relative_to(ROOT).as_posix(),'sha256':hashlib.sha256(output.read_bytes()).hexdigest(),
                'steps':['Read native frequency A HHHH, HVHV and mask within prepared bbox','No resampling or imputation'],
                'limitation':'Mask and quality checks required; not validated events.'}
        receipt.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    if previous_grid is not None and grid != previous_grid: raise ValueError('Native grids do not match')
    previous_grid=grid
    print(args.site, date, 'window',grid['shape'],'ready',flush=True)
