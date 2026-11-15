"""Reproject cached calibrated Sentinel-2 windows into Leaflet-ready RGBA PNG overlays."""
import hashlib, json
from pathlib import Path
import numpy as np
import rasterio
from rasterio.transform import from_origin
from rasterio.warp import calculate_default_transform, reproject, Resampling
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'data/investigation/maps'

def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()

def overlay(entry):
    source=ROOT/entry['asset_npz']
    if sha(source)!=entry['asset_npz_sha256']: raise ValueError(f'NPZ hash mismatch: {source}')
    with np.load(source) as data:
        bands=[data[k].astype('float32') for k in ('red','green','blue')]
        scl=data['scl'].astype('uint8')
    h,w=scl.shape
    west,south,east,north=entry['bounds_m']
    src_transform=from_origin(west,north,entry['native_analysis_grid']['resolution_m'],entry['native_analysis_grid']['resolution_m'])
    dst_transform,dst_w,dst_h=calculate_default_transform('EPSG:32722','EPSG:4326',w,h,west,south,east,north)
    if dst_w<=0 or dst_h<=0: raise ValueError('Invalid reprojected output dimensions')
    warped=[]
    for band in bands:
        out=np.full((dst_h,dst_w),np.nan,dtype='float32')
        reproject(band,out,src_transform=src_transform,src_crs='EPSG:32722',dst_transform=dst_transform,
          dst_crs='EPSG:4326',src_nodata=np.nan,dst_nodata=np.nan,resampling=Resampling.bilinear)
        warped.append(out)
    # Nearest-neighbor categorical reprojection preserves source SCL classes, not blended codes.
    scl_out=np.zeros((dst_h,dst_w),dtype='uint8')
    reproject(scl,scl_out,src_transform=src_transform,src_crs='EPSG:32722',dst_transform=dst_transform,
      dst_crs='EPSG:4326',src_nodata=0,dst_nodata=0,resampling=Resampling.nearest)
    valid=np.isin(scl_out,[4,5,6]) & np.isfinite(np.stack(warped)).all(axis=0)
    rgb=np.stack(warped,axis=-1)
    # Same reflectance stretch as established previews; no per-image histogram fit.
    rgb=np.clip(rgb/0.3,0,1)**(1/2.2)
    rgb=np.nan_to_num(rgb,nan=0.0,posinf=0.0,neginf=0.0)
    rgba=np.zeros((dst_h,dst_w,4),dtype='uint8')
    rgba[:,:,:3]=np.uint8(np.clip(rgb,0,1)*255)
    rgba[:,:,3]=valid.astype('uint8')*255
    outpath=BASE/f"new-{entry['date']}-leaflet-rgb.png"
    Image.fromarray(rgba,'RGBA').save(outpath,optimize=True)
    bounds_wgs84=[float(dst_transform.c),float(dst_transform.f+dst_transform.e*dst_h),
      float(dst_transform.c+dst_transform.a*dst_w),float(dst_transform.f)]
    return {'date':entry['date'],'source_scene':entry['scene_id'],'source_item_url':entry['item_url'],
      'path':f'data/investigation/maps/{outpath.name}','sha256':sha(outpath),
      'bounds_wgs84':bounds_wgs84,'crs':'EPSG:4326','pixel_registration':'north-up affine raster; bounds are outer pixel edges; source grid pixels interpreted at pixel centers by affine transform',
      'output_dimensions_px':[dst_w,dst_h],'source_grid':{'crs':'EPSG:32722','bounds_m':entry['bounds_m'],
        'shape_px':[h,w],'resolution_m':entry['native_analysis_grid']['resolution_m'],'pixel_support':entry['native_analysis_grid']['pixel_support']},
      'reprojection':'Rasterio/GDAL warp EPSG:32722 -> EPSG:4326 north-up; RGB bilinear; SCL nearest-neighbor. Source native grid transform is from pixel outer bounds, so samples are located at native pixel centers.',
      'legend':{'type':'true_color_rgb','bands':['B04 red','B03 green','B02 blue'],'reflectance_stretch':[0,0.3],
        'gamma':2.2,'display':'fixed RGB stretch; qualitative true-color appearance only; not an index'},
      'valid_mask_policy':'PNG alpha=255 only where nearest-reprojected SCL is class 4 vegetation, 5 not-vegetated, or 6 water AND all calibrated RGB bands are finite; otherwise alpha=0. Cloud/shadow/unclassified/snow/no-data and other SCL classes are transparent.',
      'resolution_qualification':'Source optical composites are on a common 20 m grid; B04/B03/B02 were bilinear-resampled from native 10 m before this geographic warp. Output is a display overlay, not native 10 m imagery or an area/condition measurement.',
      'alpha':{'valid_fraction':float(valid.mean()),'transparent_fraction':float((~valid).mean()),'nonzero_values':[0,255]}}

def main():
    receipt=json.loads((BASE/'new-optical-receipts.json').read_text())
    overlays=[overlay(x) for x in receipt.get('selected_scenes',[])]
    if not overlays: raise RuntimeError('No cached COG windows available')
    path=ROOT/'data/investigation/map-candidates.json'
    data=json.loads(path.read_text())
    data['new_optical_overlays']=overlays
    data['new_optical_evidence']['overlays']=overlays
    bydate={x['date']:x for x in overlays}
    for m in data['maps']:
        for obs in m.get('new_optical',[]):
            obs['overlay']=bydate.get(obs['date'])
    path.write_text(json.dumps(data,indent=2)+'\n')
    print(json.dumps([{'date':x['date'],'path':x['path'],'sha256':x['sha256'],
      'bounds_wgs84':x['bounds_wgs84'],'dimensions':x['output_dimensions_px'],'alpha':x['alpha']} for x in overlays],indent=2))

if __name__=='__main__': main()
