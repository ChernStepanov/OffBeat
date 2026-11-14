"""Reproject ESA WorldCover 2021 to the native Amazon GCOV grid, nearest-neighbour."""
import hashlib,json
from pathlib import Path
import numpy as np,rasterio
from rasterio.transform import Affine
from rasterio.warp import reproject,Resampling

ROOT=Path(__file__).resolve().parents[1]
URL='https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map/ESA_WorldCover_10m_2021_v200_S06W051_Map.tif'

def main():
    p=ROOT/'data/subsets/amazon-dense/2026-08-23.json';g=json.loads(p.read_text())['grid']; h,w=g['shape']
    t=Affine(g['x_step'],0,g['x_first']-g['x_step']/2,0,g['y_step'],g['y_first']-g['y_step']/2)
    arr=np.zeros((h,w),dtype=np.uint8)
    with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN='EMPTY_DIR',CPL_VSIL_CURL_ALLOWED_EXTENSIONS='.tif',GDAL_HTTP_TIMEOUT='60'):
      with rasterio.open('/vsicurl/'+URL) as src:
        reproject(source=rasterio.band(src,1),destination=arr,src_transform=src.transform,src_crs=src.crs,src_nodata=src.nodata,dst_transform=t,dst_crs=f"EPSG:{g['epsg']}",dst_nodata=0,resampling=Resampling.nearest)
    target=ROOT/'data/subsets/amazon-dense/worldcover-2021.npz';np.savez_compressed(target,cover=arr)
    receipt={'source':URL,'source_year':2021,'grid':g,'subset_path':target.relative_to(ROOT).as_posix(),'sha256':hashlib.sha256(target.read_bytes()).hexdigest(),'method':'Nearest-neighbour WorldCover 2021 to native GCOV 20 m grid; zero means unavailable. Classes predate radar observations.'}
    target.with_suffix('.json').write_text(json.dumps(receipt,indent=2)+'\n');print('classes and counts:',dict(zip(*np.unique(arr,return_counts=True))),flush=True)

if __name__=='__main__':main()
