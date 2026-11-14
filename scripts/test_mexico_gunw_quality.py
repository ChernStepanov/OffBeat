"""Check reproducibility, pair continuity and reported quality counts."""
import hashlib,json
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
report=json.loads((ROOT/'data/analysis/mexico-gunw-quality.json').read_text())
for direction,expected in [('ascending',[357,208,0]),('descending',[54,210,0])]:
 pairs=report['directions'][direction]['pairs'];assert len(pairs)==3
 assert [x['valid_count'] for x in pairs]==expected
 assert report['directions'][direction]['quality_valid_in_all_pairs']==0
 for idx,p in enumerate(pairs):
  if idx:assert p['reference_date']==pairs[idx-1]['secondary_date']
  r=json.loads((ROOT/p['subset_receipt']).read_text()); path=ROOT/r['subset_path']
  assert hashlib.sha256(path.read_bytes()).hexdigest()==r['sha256']
  a=np.load(path); assert a['phase'].shape==(32,32) and a['mask'].shape==(32,32)
  assert r['source']['id']==p['granule_id'] and r['quality_valid_count']==p['valid_count']
print('PASS: six authentic GUNW subset hashes, dates and reported quality continuity')
