"""Verify post-gap source hashes, strict quality intersections and component diagnostics."""
import hashlib,json
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
x=json.loads((ROOT/'data/analysis/mexico-gunw-postgap-quality.json').read_text());combined=[]
for direction,expected in [('ascending',275),('descending',68)]:
 d=x['directions'][direction]; masks=[];components=[];previous=None
 for pair in d['pairs']:
  r=json.loads((ROOT/pair['subset_receipt']).read_text());p=ROOT/r['subset_path'];assert hashlib.sha256(p.read_bytes()).hexdigest()==r['sha256'];a=np.load(p);m=a['mask'].astype(np.uint32);s=m&255
  if previous:assert previous==pair['reference_date']
  previous=pair['secondary_date']
  ok=np.isfinite(a['phase'])&np.isfinite(a['iono'])&np.isfinite(a['coherence'])&(a['coherence']>=.7)&(a['component']>0)&(a['component']<65535)&(s<100)&((s//10)>0)&((s%10)>0)&(((m>>8)&65535)==0)&((m&0xfe000000)==0)&np.isfinite(a['iono_sd'])&(a['iono_sd']<=1)
  assert int(ok.sum())==pair['valid_count'];masks.append(ok);components.append(a['component'])
 common=np.logical_and.reduce(masks);assert int(common.sum())==expected==d['quality_valid_in_all_pairs'];connected=common.copy()
 for arr,label in zip(components,d['dominant_component_each_pair']):connected &= arr==label
 assert int(connected.sum())==d['common_points_in_dominant_components'];combined.append(common)
assert int((combined[0]&combined[1]).sum())==x['both_directions_quality_overlap']==39
print('PASS: post-gap GUNW hashes, independent quality intersections and components')
