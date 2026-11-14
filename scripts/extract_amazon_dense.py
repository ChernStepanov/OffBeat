"""Read native GCOV windows before/after the Amazon candidate, retaining masks and source receipts."""
import hashlib,json,os
from pathlib import Path
import earthaccess,h5py,numpy as np
from pyproj import Transformer

ROOT=Path(__file__).resolve().parents[1]

def scalar(ds):
    v=ds[()]; return v.decode() if isinstance(v,bytes) else v.item() if isinstance(v,np.generic) else v

def main():
    site=json.loads((ROOT/'data/amazon.json').read_text()); bbox=site['grid']['bbox']
    dates=('2026-08-23','2026-09-04');source=site['provenance']['additional_gcov']
    recs=[next(r for r in source if r['date']==d) for d in dates]
    os.environ['EARTHDATA_TOKEN']=(ROOT/'.earthdata_token').read_text().strip()
    if not earthaccess.login(strategy='environment',persist=False).authenticated:raise RuntimeError('Earthdata authentication failed')
    fs=earthaccess.get_fsspec_https_session();target=ROOT/'data/subsets/amazon-dense';target.mkdir(parents=True,exist_ok=True);lastgrid=None
    for d,r in zip(dates,recs):
        with fs.open(r['source']['url'],block_size=1024*1024,cache_type='blockcache') as f,h5py.File(f,'r') as h:
            ident=h['science/LSAR/identification'];actual=(int(ident['trackNumber'][()]),int(ident['frameNumber'][()]),scalar(ident['orbitPassDirection']),scalar(ident['zeroDopplerStartTime'])[:10])
            if actual!=(146,175,'Ascending',d):raise ValueError('Acquisition mismatch')
            g=h['science/LSAR/GCOV/grids/frequencyA'];xs=g['xCoordinates'][:];ys=g['yCoordinates'][:];epsg=int(g['projection'][()]);tr=Transformer.from_crs(4326,epsg,always_xy=True)
            lon=[bbox['w'],bbox['e'],bbox['w'],bbox['e']];lat=[bbox['s'],bbox['s'],bbox['n'],bbox['n']];xx,yy=tr.transform(lon,lat)
            cs=(np.asarray(xx)-xs[0])/(xs[1]-xs[0]);rs=(np.asarray(yy)-ys[0])/(ys[1]-ys[0]);c0,c1=int(np.floor(min(cs))),int(np.ceil(max(cs)))+1;r0,r1=int(np.floor(min(rs))),int(np.ceil(max(rs)))+1
            if r0<0 or c0<0 or r1>len(ys) or c1>len(xs):raise ValueError('AOI outside source')
            grid={'epsg':epsg,'window':[r0,r1,c0,c1],'x_first':float(xs[c0]),'y_first':float(ys[r0]),'x_step':float(xs[1]-xs[0]),'y_step':float(ys[1]-ys[0]),'shape':[r1-r0,c1-c0]}
            if lastgrid and grid!=lastgrid:raise ValueError('Source grids differ')
            lastgrid=grid;values={k:np.asarray(g[v][r0:r1,c0:c1]) for k,v in {'hh':'HHHH','hv':'HVHV','mask':'mask'}.items()}
            out=target/f'{d}.npz';np.savez_compressed(out,**values)
            receipt={'source':r['source'],'grid':grid,'date':d,'subset_path':out.relative_to(ROOT).as_posix(),'sha256':hashlib.sha256(out.read_bytes()).hexdigest(), 'steps':['Read native frequency A HHHH, HVHV and mask within bounding window','No resampling, classification, smoothing or imputation'],'warning':'Uncalculated native power; mask is retained and needs interpretation before display or change inference.'}
            out.with_suffix('.json').write_text(json.dumps(receipt,indent=2)+'\n');print(d,'shape',grid['shape'],'saved',flush=True)

if __name__=='__main__':main()
