"""Validate HLS QA logic and authenticated mosaic inspection receipt."""
import json
from pathlib import Path
import numpy as np
from inspect_hls_mosaic_quality import clear_qa
ROOT=Path(__file__).resolve().parents[1]
# Isolated QA-bit behaviour; these test arrays are not application data.
qa=np.ma.array([0,2,4,8,16,32,255,0],mask=[False,False,False,False,False,False,False,True],dtype=np.uint8)
assert clear_qa(qa).tolist()==[True,False,False,False,False,True,False,False]
x=json.loads((ROOT/'data/subsets/venezuela-hls/2025-11-21-mosaic-quality.json').read_text())
assert len(x['candidates'])==20 and len({c['acquisition'] for c in x['candidates']})==20
assert all('error' not in c for c in x['candidates'])
for c in x['candidates']:
 assert len(c['granules'])==2 and {g['id'].split('.')[2] for g in c['granules']}=={'T19PGM','T19PFM'}
 assert len(c['assets'])==2 and all('? ' not in url and '?' not in url for url in c['assets'])
 assert c['total_pixels']>0 and 0<=c['clear_pixels']<=c['total_pixels']
 assert abs(c['clear_fraction']-c['clear_pixels']/c['total_pixels'])<0.000001
assert max(c['clear_fraction'] for c in x['candidates'])<x['threshold']==0.8
print('PASS: HLS QA bits, 20 aligned acquisition mosaics, fractions and no passing scene')
