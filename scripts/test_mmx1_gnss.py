"""Validate GNSS provenance, original observations and nearest radar quality."""
import datetime as dt,hashlib,json
from pathlib import Path
import numpy as np
from pyproj import Geod
from inspect_mmx1_gnss import accepted
ROOT=Path(__file__).resolve().parents[1]
x=json.loads((ROOT/'data/analysis/mexico-mmx1-gnss.json').read_text());raw=ROOT/x['subset_path'];assert hashlib.sha256(raw.read_bytes()).hexdigest()==x['subset_sha256']
lines=raw.read_text().splitlines();assert len(lines)-1==len(x['records'])==56
for line,r in zip(lines[1:],x['records']):
 p=line.split();assert dt.datetime.strptime(p[1],'%y%b%d').date().isoformat()==r['date'];assert abs(float(p[11])+float(p[12])-r['up_m'])<1e-9;assert float(p[16])==r['sigma_up_m']
site=json.loads((ROOT/'data/mexico.json').read_text());near=x['nearest_nisar_sample'];assert site['pixels'][near['index']]['id']==near['id']
lat=x['station_coordinates']['lat'];lon=x['station_coordinates']['lon'];_,_,distance=Geod(ellps='WGS84').inv(lon,lat,near['lon'],near['lat']);assert abs(distance-near['distance_m'])<.02
quality=json.loads((ROOT/'data/analysis/mexico-gunw-postgap-quality.json').read_text());row,col=divmod(near['index'],site['grid']['n'])
for direction in ('ascending','descending'):
 for entry,reported in zip(quality['directions'][direction]['pairs'],x['gunw_quality_at_nearest_sample'][direction]):
  receipt=json.loads((ROOT/entry['subset_receipt']).read_text());a=np.load(ROOT/receipt['subset_path']);assert accepted(a,row,col)==reported['quality_accepted']
assert sum(p['quality_accepted'] for p in x['gunw_quality_at_nearest_sample']['ascending'])==2
assert sum(p['quality_accepted'] for p in x['gunw_quality_at_nearest_sample']['descending'])==0
print('PASS: MMX1 raw subset hash, daily coordinates and nearest-sample GUNW quality')
