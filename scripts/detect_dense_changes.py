"""Find candidate regions in two co-registered, measured GCOV HV grids."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image
from rasterio.warp import transform
from scipy import ndimage

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / '.work-audit'
OUT.mkdir(parents=True, exist_ok=True)
parser=argparse.ArgumentParser()
parser.add_argument('--site', default='amazon', choices=('amazon','mexico','venezuela','delhi','tokyo','nairobi','sydney'))
args=parser.parse_args()
site=json.loads((ROOT/'data'/f'{args.site}.json').read_text(encoding='utf-8'))
DATES = ('2026-08-23', '2026-09-04') if args.site == 'amazon' else tuple(site['dates'][:2])
folder = ROOT/'data/subsets/amazon-dense' if args.site == 'amazon' else ROOT/'data/subsets'/f'{args.site}-dense'
meta = [json.loads((folder / f'{d}.json').read_text(encoding='utf-8')) for d in DATES]
if meta[0]['grid'] != meta[1]['grid']:
    raise ValueError('Native grids are not identical')
for item in meta:
    if hashlib.sha256((ROOT/item['subset_path']).read_bytes()).hexdigest() != item['sha256']:
        raise ValueError('Subset hash does not match receipt')
grid = meta[0]['grid']
inputs = [np.load(ROOT/item['subset_path']) for item in meta]
valid = np.ones(grid['shape'], dtype=bool)
for a in inputs:
    valid &= (a['mask'] > 0) & (a['mask'] < 255) & np.isfinite(a['hv']) & (a['hv'] > 0)
delta = np.full(valid.shape, np.nan)
delta[valid] = 10*np.log10(inputs[1]['hv'][valid]/inputs[0]['hv'][valid])
count = ndimage.convolve(valid.astype(int), np.ones((3,3), dtype=int), mode='constant')
filtered = ndimage.generic_filter(delta, np.nanmedian, size=3, mode='constant', cval=np.nan)
usable = valid & (count >= 5) & np.isfinite(filtered)
filled = np.where(usable, filtered, np.nanmedian(filtered[usable]))
local = ndimage.median_filter(filled, size=31, mode='nearest')
residual = filtered - local
median = float(np.median(residual[usable]))
scale = float(1.4826*np.median(np.abs(residual[usable]-median)))
if not np.isfinite(scale) or scale < 0.1:
    raise ValueError('Robust spread is too small or invalid')
score = (residual-median)/scale
markers=[]
for direction in (-1, 1):
    regions, n = ndimage.label(usable & (score*direction >= 2.5), structure=np.ones((3,3), dtype=int))
    for label in range(1,n+1):
        cells = np.argwhere(regions == label)
        if len(cells) < 6: continue
        strengths = np.abs(score[cells[:,0], cells[:,1]])
        row,col = map(int,cells[np.argmax(strengths)])
        x = grid['x_first'] + col*grid['x_step']; y = grid['y_first'] + row*grid['y_step']
        longitude,latitude = transform(f"EPSG:{grid['epsg']}", 'EPSG:4326', [x], [y])
        markers.append({'id':f'r{row}-c{col}','row':row,'col':col,'lat':latitude[0],'lon':longitude[0],
                        'direction':'below' if direction < 0 else 'above',
                        'score':round(float(score[row,col]),2), 'delta_db':round(float(delta[row,col]),2),
                        'local_baseline_db':round(float(local[row,col]),2), 'cells':int(len(cells))})
markers.sort(key=lambda x: -abs(x['score']))
for d,a in zip(DATES,inputs):
    db=np.full(valid.shape,np.nan); db[valid]=10*np.log10(a['hv'][valid])
    grey=np.uint8(np.clip(np.nan_to_num((db+25)/25,nan=0),0,1)*255)
    rgba=np.dstack([grey,grey,grey,valid.astype(np.uint8)*255])
    Image.fromarray(rgba).save(OUT/f'dense-{args.site}-hv-{d}.png')
report={'version':1,'site':args.site,'site_name':site['name'],'bbox':site['grid']['bbox'],'dates':list(DATES),'source':'NASA-ISRO NISAR GCOV provisional / ASF',
        'inputs':[{'date':m['date'],'granule_id':m['source']['id'],'concept_id':m['source']['concept_id'],
                   'url':m['source']['url'],'subset_path':m['subset_path'],'sha256':m['sha256']} for m in meta],
        'grid':grid,'valid_cells':int(valid.sum()),'robust_spread_db':round(scale,3),
        'method':f"Same native UTM grid at {abs(grid['x_step'])} m by {abs(grid['y_step'])} m; finite positive HV and masks 1..254 on both dates; 10 log10(after/before); 3x3 median with at least five valid cells; subtract 31x31 median local background; threshold absolute residual / global 1.4826 MAD >= 2.5; 8-connected groups of at least 6 cells; one marker at strongest native cell per group.",
        'limitations':['Retrospective exploratory rule; threshold and groups are not independently validated.',
                       'Point locations are computed from radar cells, not independently identified events.',
                       'Changes in speckle, moisture, acquisition and calibration may mimic changes.',
                       'The median background suppresses widespread changes; no weather correction.',
                       'Masks 1..254 follow the existing project contract, not a complete product quality assessment.',
                       'Different native pixel sizes mean filter footprints and scores are not directly comparable across sites.',
                       'Connected cell counts are not validated event area.'], 'total_marker_count':len(markers), 'markers':markers[:30]}
(OUT/f'dense-detection-{args.site}.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'valid':report['valid_cells'],'scale':report['robust_spread_db'],'markers':len(markers),'first':markers[:4]},ensure_ascii=False,indent=2))
