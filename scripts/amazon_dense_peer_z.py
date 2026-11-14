"""Dense latest-date peer z on real GCOV; preserve full 1 km context or mark unavailable."""
import hashlib,json
from pathlib import Path
import numpy as np
from PIL import Image
from scipy.spatial import cKDTree
from rasterio.transform import Affine,from_bounds
from rasterio.warp import calculate_default_transform,reproject,Resampling,transform_bounds
ROOT=Path(__file__).resolve().parents[1]

def main():
    site=json.loads((ROOT/'data/amazon.json').read_text());folder=ROOT/'data/subsets/amazon-dense';dates=site['dates']
    receipts=[json.loads((folder/f'{d}.json').read_text()) for d in dates]
    g=receipts[0]['grid']
    if any(r['grid']!=g for r in receipts):raise ValueError('Incompatible native grids')
    cover_receipt=json.loads((folder/'worldcover-2021.json').read_text());cover=np.load(ROOT/cover_receipt['subset_path'])['cover'];h,w=cover.shape
    for r in [*receipts,cover_receipt]:
        if hashlib.sha256((ROOT/r['subset_path']).read_bytes()).hexdigest()!=r['sha256']:raise ValueError('Source hash mismatch')
    row,col=np.indices((h,w)); coords=np.column_stack((col.ravel()*abs(g['x_step']),row.ravel()*abs(g['y_step'])))
    radius=1000.0;margin=int(np.ceil(radius/min(abs(g['x_step']),abs(g['y_step']))))
    interior=(row>=margin)&(row<h-margin)&(col>=margin)&(col<w-margin)
    out=[]; counts=[]
    for d,r in zip(dates,receipts):
        a=np.load(ROOT/r['subset_path']);hv=a['hv'];mask=a['mask'];valid=(mask>0)&(mask<255)&np.isfinite(hv)&(hv>0)&(cover!=0)&(cover!=80)
        values=np.full((h,w),np.nan);values[valid]=10*np.log10(hv[valid]);z=np.full((h,w),np.nan,dtype=np.float32);n=np.zeros((h,w),dtype=np.uint16)
        for code in np.unique(cover[valid]):
            members=np.flatnonzero((valid&(cover==code)).ravel()); tree=cKDTree(coords[members]);
            for point in np.flatnonzero((valid&interior&(cover==code)).ravel()):
                neighbours=members[tree.query_ball_point(coords[point],radius)];neighbours=neighbours[neighbours!=point]
                if neighbours.size<10:continue
                data=values.ravel()[neighbours];med=np.median(data);sigma=1.4826*np.median(np.abs(data-med))
                if not np.isfinite(sigma) or sigma<=0:continue
                z.ravel()[point]=(values.ravel()[point]-med)/sigma;n.ravel()[point]=len(data)
        out.append(z);counts.append(n);print(d,'valid z:',int(np.isfinite(z).sum()),flush=True)
    out=np.stack(out);counts=np.stack(counts)
    dest=folder/'peer-z.npz';np.savez_compressed(dest,z=out,peer_counts=counts,dates=np.array(dates))
    # Reproject the last actual z raster to a geographic grid without interpolating values.
    src_transform=Affine(g['x_step'],0,g['x_first']-g['x_step']/2,0,g['y_step'],g['y_first']-g['y_step']/2)
    left=src_transform.c;top=src_transform.f;right=left+w*g['x_step'];bottom=top+h*g['y_step']
    west,south,east,north=transform_bounds(f"EPSG:{g['epsg']}",'EPSG:4326',left,bottom,right,top,densify_pts=21)
    dst_transform=from_bounds(west,south,east,north,w,h); dst=np.full((h,w),np.nan,dtype=np.float32)
    reproject(out[-1],dst,src_transform=src_transform,src_crs=f"EPSG:{g['epsg']}",src_nodata=np.nan,dst_transform=dst_transform,dst_crs='EPSG:4326',dst_nodata=np.nan,resampling=Resampling.nearest)
    rgba=np.zeros((h,w,4),dtype=np.uint8);ok=np.isfinite(dst);magnitude=np.minimum(np.abs(np.nan_to_num(dst))/4,1);neg=ok&(dst<0);pos=ok&(dst>=0)
    rgba[neg,0]=(235*(1-magnitude[neg])+24*magnitude[neg]).astype('uint8');rgba[neg,1]=(235*(1-magnitude[neg])+70*magnitude[neg]).astype('uint8');rgba[neg,2]=(235*(1-magnitude[neg])+210*magnitude[neg]).astype('uint8')
    rgba[pos,0]=(235*(1-magnitude[pos])+210*magnitude[pos]).astype('uint8');rgba[pos,1]=(235*(1-magnitude[pos])+40*magnitude[pos]).astype('uint8');rgba[pos,2]=(235*(1-magnitude[pos])+35*magnitude[pos]).astype('uint8');rgba[ok,3]=200
    image=ROOT/'data/amazon/dense-peer-z.png';image.parent.mkdir(parents=True,exist_ok=True);Image.fromarray(rgba,'RGBA').save(image,optimize=True)
    meta={'site':'amazon','dates':dates,'layer_date':dates[-1],'source':'NISAR PROVISIONAL GCOV HV gamma0; ESA WorldCover 2021',
      'inputs':[{'path':r['subset_path'],'sha256':r['sha256'],'granule_id':r.get('source',{}).get('id')} for r in receipts],
      'worldcover':{'path':cover_receipt['subset_path'],'sha256':cover_receipt['sha256'],'source':cover_receipt['source']},
      'method':'Per date and native 20 m pixel: finite positive HV, mask 1..254, same 2021 WorldCover class within 1 km; exclude target pixel, water and no-data, require at least 10 peers and non-zero 1.4826 MAD. z=(HV dB - peer median)/MAD. Full 1 km neighbourhood required within extracted window; boundaries lacking full coverage remain unavailable.',
      'limits':'Exploratory same-class deviation, not a change, event, or probability. WorldCover is from 2021. Values reflect provisional products; weather and speckle remain. Dated to last radar observation, independent of time slider. Geographic rendering uses nearest-neighbour reprojection; no missing values are filled.',
      'grid':g,'valid_per_date':[int(np.isfinite(v).sum()) for v in out],'bounds':{'w':west,'s':south,'e':east,'n':north},
      'data_path':dest.relative_to(ROOT).as_posix(),'sha256':hashlib.sha256(dest.read_bytes()).hexdigest(),'image_path':image.relative_to(ROOT).as_posix(),'image_sha256':hashlib.sha256(image.read_bytes()).hexdigest()}
    (ROOT/'data/amazon/dense-peer-z.json').write_text(json.dumps(meta,indent=2)+'\n');print('wrote raster and metadata',flush=True)

if __name__=='__main__':main()
