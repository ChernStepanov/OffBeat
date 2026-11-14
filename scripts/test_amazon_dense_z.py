"""Independent spot checks for dense peer-z coverage, values, and source hashes."""
import hashlib,json
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
m=json.loads((ROOT/'data/amazon/dense-peer-z.json').read_text());a=np.load(ROOT/m['data_path']);z=a['z'];n=a['peer_counts'];cover=np.load(ROOT/m['worldcover']['path'])['cover']
assert z.shape==(6,141,141) and np.array_equal(a['dates'],m['dates'])
assert np.isnan(z[:,:50,:]).all() and np.isnan(z[:,-50:,:]).all() and np.isnan(z[:,:,:50]).all() and np.isnan(z[:,:,-50:]).all()
assert hashlib.sha256((ROOT/m['data_path']).read_bytes()).hexdigest()==m['sha256']
assert hashlib.sha256((ROOT/m['image_path']).read_bytes()).hexdigest()==m['image_sha256']
for item in m['inputs']+[m['worldcover']]:assert hashlib.sha256((ROOT/item['path']).read_bytes()).hexdigest()==item['sha256']
y,x=np.indices(cover.shape)
for di,row,col in [(0,50,50),(2,70,70),(5,90,90)]:
    v=np.load(ROOT/m['inputs'][di]['path']);valid=(v['mask']>0)&(v['mask']<255)&np.isfinite(v['hv'])&(v['hv']>0)&(cover==cover[row,col]);valid[row,col]=False
    valid &= ((x-col)*20)**2+((y-row)*20)**2<=1000**2
    vals=10*np.log10(v['hv'][valid]);med=np.median(vals);sigma=1.4826*np.median(np.abs(vals-med));expected=(10*np.log10(v['hv'][row,col])-med)/sigma
    assert n[di,row,col]==valid.sum() and abs(float(z[di,row,col])-expected)<1e-5
print('PASS: dense GCOV hashes, no-data edges, peer counts and independent z-score checks')
