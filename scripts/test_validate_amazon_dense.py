"""Check dense candidate rules and provenance without treating fixtures as measurements."""
import hashlib,json
from pathlib import Path
import numpy as np
from validate_amazon_dense import candidate_labels
ROOT=Path(__file__).resolve().parents[1]
hv=np.ones((6,3,3),float);valid=np.ones_like(hv,dtype=bool);cover=np.full((3,3),10);z=np.zeros_like(hv)
for row,col in [(0,0),(0,1),(1,0),(1,1)]:hv[3:,row,col]=0.1
good,flags,labels,change,keep=candidate_labels(hv,valid,cover,z)
assert len(keep)==1 and flags.sum()==4 and (labels==keep[0]).sum()==4
valid[4,0,0]=False
assert len(candidate_labels(hv,valid,cover,z)[-1])==0
valid[4,0,0]=True;cover[0,0]=80
assert len(candidate_labels(hv,valid,cover,z)[-1])==0
x=json.loads((ROOT/'data/amazon/dense-validation.json').read_text())
for r in x['inputs']+x['context_inputs']+[x['worldcover']]:assert hashlib.sha256((ROOT/r['path']).read_bytes()).hexdigest()==r['sha256']
assert hashlib.sha256((ROOT/x['peer_z_path']).read_bytes()).hexdigest()==x['peer_z_sha256']
assert x['quality']['eligible_forest_cells']==590 and x['quality']['candidate_count']==1
assert x['candidates'][0]['cells']==4 and not x['candidates'][0]['alert_matches'] and not x['candidates'][0]['fire_matches']
print('PASS: dense candidate validity, class mask, connectivity, provenance and context')
