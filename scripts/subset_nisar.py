"""Reproducible small Mexico case: real HH/HV and a spatially referenced GUNW pair."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import earthaccess
import h5py
import numpy as np
from pyproj import Transformer
import rasterio
from analyze_preview import analyze_site

ROOT=Path(__file__).resolve().parents[1]
N=32
BBOX=dict(w=-99.09,s=19.415,e=-99.065,n=19.44)
WORLD='https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map/ESA_WorldCover_10m_2021_v200_N18W102_Map.tif'
CASE=dict(id='mexico',name='Mexico City',track=19,frame=11)
TARGET=ROOT/'data/subsets'

def configure(site_id,name,bbox,track,frame):
    global CASE,BBOX,WORLD,TARGET
    CASE=dict(id=site_id,name=name,track=track,frame=frame)
    BBOX=bbox
    TARGET=ROOT/'data/subsets'/site_id if site_id!='mexico' else ROOT/'data/subsets'
    lat=int(np.floor(bbox['s']/3)*3);lon=int(np.floor(bbox['w']/3)*3)
    tile=f"{'N' if lat>=0 else 'S'}{abs(lat):02}{'E' if lon>=0 else 'W'}{abs(lon):03}"
    WORLD=f'https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map/ESA_WorldCover_10m_2021_v200_{tile}_Map.tif'

def scalar(ds):
    value=ds[()]
    return value.decode() if isinstance(value,bytes) else value.item() if isinstance(value,np.generic) else value

def coordinates():
    lat,lon=np.meshgrid(BBOX['n']-(np.arange(N)+.5)/N*(BBOX['n']-BBOX['s']),BBOX['w']+(np.arange(N)+.5)/N*(BBOX['e']-BBOX['w']),indexing='ij')
    return lat,lon

def grid_samples(group,names,lat,lon):
    xs,ys=group['xCoordinates'][:],group['yCoordinates'][:]
    epsg=int(group['projection'][()])
    xx,yy=Transformer.from_crs(4326,epsg,always_xy=True).transform(lon,lat)
    cols=np.floor((xx-xs[0])/(xs[1]-xs[0])+.5).astype(int)
    rows=np.floor((yy-ys[0])/(ys[1]-ys[0])+.5).astype(int)
    if np.any((cols<0)|(cols>=len(xs))|(rows<0)|(rows>=len(ys))):
        raise ValueError('AOI outside product grid')
    r0,r1,c0,c1=int(rows.min()),int(rows.max()+1),int(cols.min()),int(cols.max()+1)
    result={}
    for key,path in names.items():
        ds=group[path]
        print('Read',ds.name,[r0,r1,c0,c1],flush=True)
        values=np.asarray(ds[r0:r1,c0:c1])[rows-r0,cols-c0]
        fill=ds.attrs.get('_FillValue')
        if np.issubdtype(values.dtype,np.floating):
            values=values.astype(float)
            if fill is not None: values[values==fill]=np.nan
        result[key]=values
    meta=dict(epsg=epsg,spacing=[float(xs[1]-xs[0]),float(ys[1]-ys[0])],window=[r0,r1,c0,c1],paths={k:group[v].name for k,v in names.items()})
    return result,meta

def extract(manifest,fs):
    lat,lon=coordinates()
    target=TARGET
    target.mkdir(parents=True,exist_ok=True)
    records=manifest['products']['gcov'][:2]+manifest['products']['gunw'][:1]
    receipts=[]
    for i,record in enumerate(records):
        output=target/f'nisar-{i}.npz'
        metadata=output.with_suffix('.json')
        if output.exists() and metadata.exists():
            print('Reusing',output.name,flush=True)
            cached=json.loads(metadata.read_text())
            with np.load(output) as arrays:
                if cached['source']['id']!=record['id'] or not np.array_equal(arrays['lat'],lat) or not np.array_equal(arrays['lon'],lon):
                    raise ValueError('Cached subset belongs to a different product or AOI; choose a fresh cache directory')
            if hashlib.sha256(output.read_bytes()).hexdigest()!=cached['sha256']:
                raise ValueError('Cached subset checksum mismatch')
            receipts.append(cached)
            continue
        with fs.open(record['url'],block_size=1024*1024,cache_type='blockcache') as remote:
            with h5py.File(remote,'r') as hdf:
                ident=hdf['science/LSAR/identification']
                identification={k:scalar(ident[k]) for k in ['trackNumber','frameNumber','orbitPassDirection','productVersion','lookDirection','radarBand']}
                if (identification['trackNumber'],identification['frameNumber'],identification['orbitPassDirection'])!=(CASE['track'],CASE['frame'],'Ascending'):
                    raise ValueError('Incompatible acquisition geometry')
                if i<2:
                    group=hdf['science/LSAR/GCOV/grids/frequencyA']
                    values,meta=grid_samples(group,{'hh':'HHHH','hv':'HVHV','mask':'mask'},lat,lon)
                    meta['date']=scalar(ident['zeroDopplerStartTime'])[:10]
                else:
                    base=hdf['science/LSAR/GUNW/grids/frequencyA']
                    group=base['unwrappedInterferogram']
                    names={'phase':'HH/unwrappedPhase','coherence':'HH/coherenceMagnitude','component':'HH/connectedComponents','iono':'HH/ionospherePhaseScreen','iono_sd':'HH/ionospherePhaseScreenUncertainty','mask':'mask'}
                    values,meta=grid_samples(group,names,lat,lon)
                    meta['center_frequency_hz']=float(base['centerFrequency'][()])
                    meta['reference_date']=scalar(ident['referenceZeroDopplerStartTime'])[:10]
                    meta['secondary_date']=scalar(ident['secondaryZeroDopplerStartTime'])[:10]
                    params=hdf['science/LSAR/GUNW/metadata/processingInformation/parameters/unwrappedInterferogram/frequencyA']
                    meta['flattening']={k:scalar(params[k]) for k in ['ellipsoidalFlatteningApplied','topographicFlatteningApplied']}
                    if any(v!='True' for v in meta['flattening'].values()): raise ValueError('Unflattened phase cannot be used')
                np.savez_compressed(output,lat=lat,lon=lon,**values)
                receipt=dict(source=record,identification=identification,grid=meta,subset_file=output.name,sha256=hashlib.sha256(output.read_bytes()).hexdigest())
                metadata.write_text(json.dumps(receipt,indent=2)+'\n')
                receipts.append(receipt)
    # WorldCover is a real 2021 classification, not a measurement of 2025 land cover.
    coverpath=target/'worldcover.npz'
    if not coverpath.exists():
        with rasterio.open(WORLD) as src:
            samples=np.array([v[0] for v in src.sample(zip(lon.ravel(),lat.ravel()))],dtype=np.uint8).reshape(N,N)
            np.savez_compressed(coverpath,cover=samples)
    cover=np.load(coverpath)['cover']
    export(receipts,cover,lat,lon)

def export(receipts,cover,lat,lon):
    target=TARGET
    arrays=[dict(np.load(target/r['subset_file'])) for r in receipts]
    for r in receipts:
        if hashlib.sha256((target/r['subset_file']).read_bytes()).hexdigest()!=r['sha256']: raise ValueError('Subset checksum mismatch')
        r['subset_path']=(target/r['subset_file']).relative_to(ROOT).as_posix()
    dates=[r['grid']['date'] for r in receipts[:2]]
    days=int((np.datetime64(dates[1])-np.datetime64(dates[0]))/np.timedelta64(1,'D'))
    gunw=receipts[2]['grid']
    if dates!=[gunw['reference_date'],gunw['secondary_date']]: raise ValueError('Pair dates do not match GCOV')
    hh,hv=[],[]
    for a in arrays[:2]:
        for key,collection in [('hh',hh),('hv',hv)]:
            raw=a[key].astype(float)
            valid=np.isfinite(raw)&(raw>0)&(a['mask']>0)&(a['mask']<255)
            db=np.full(raw.shape,np.nan)
            db[valid]=10*np.log10(raw[valid])
            collection.append(db)
    a=arrays[2]
    mask=a['mask'].astype(np.uint32)
    subs=mask&255
    valid=(np.isfinite(a['phase'])&np.isfinite(a['iono'])&np.isfinite(a['coherence'])&
        (a['coherence']>=.7)&(a['component']>0)&(a['component']<65535)&
        (subs<100)&((subs//10)>0)&((subs%10)>0)&(((mask>>8)&65535)==0)&
        ((mask&0xFE000000)==0)&np.isfinite(a['iono_sd'])&(a['iono_sd']<=1.0))
    corrected=a['phase']-a['iono']
    # Reference is explicit, selected by coherence; it is NOT asserted geologically stable.
    reference=int(np.argmax(np.where(valid,a['coherence'],-1))) if valid.any() else None
    component=int(a['component'].ravel()[reference]) if reference is not None else None
    valid &= a['component']==component if reference is not None else False
    factor=-299792458/gunw['center_frequency_hz']/(4*np.pi)*100
    displacement=np.where(valid,(corrected-corrected.ravel()[reference])*factor,np.nan) if reference is not None else np.full(corrected.shape,np.nan)
    pixels=[]
    clean=lambda v:round(float(v),5) if np.isfinite(v) else None
    for i in range(N*N):
        bs_h=[clean(x.ravel()[i]) for x in hh]; bs_v=[clean(x.ravel()[i]) for x in hv]
        d=clean(displacement.ravel()[i])
        pixels.append(dict(id=f"{CASE['id'][:3].upper()} r{i//N} c{i%N}",lat=float(lat.ravel()[i]),lon=float(lon.ravel()[i]),cover=int(cover.ravel()[i]) or None,
            peers=None,z=None,style=None,since=None,hh=bs_h,hv=bs_v,peer={k:[None]*2 for k in ['hh_med','hh_sd','hv_med','hv_sd']},
            disp=[0,d] if d is not None else None,peer_disp=None,coherence=clean(a['coherence'].ravel()[i]),component=int(a['component'].ravel()[i]),
            ionosphere_interpolated=bool(mask.ravel()[i]&(1<<24)),ionosphere_sd_rad=clean(a['iono_sd'].ravel()[i])))
    limitations=[f'One {days}-day pair: no deformation trend, subsidence rate or event attribution',
        'Apparent relative LOS change, positive toward sensor; spatial reference selected by coherence, stability not established',
        'Ionosphere screen subtracted; troposphere and solid Earth tides not corrected, residual phase may not be ground motion',
        'Product-interpolated ionosphere screen retained where bit 24 is set, flagged per sample; require screen uncertainty <=1 rad',
        'WorldCover 2021 v200 is historical context, not contemporaneous land cover',
        'Sparse nearest-native samples, no area aggregation, no anomaly classification or patch area']
    # Compare only actual sampled same-class locations within 1 km, excluding self.
    east,north=Transformer.from_crs(4326,receipts[0]['grid']['epsg'],always_xy=True).transform(lon.ravel(),lat.ravel())
    for i,p in enumerate(pixels):
        eligible=((east-east[i])**2+(north-north[i])**2<=1000**2)&(cover.ravel()==p['cover'])
        eligible[i]=False
        p['peer_counts']={'hh':[],'hv':[]}
        for key,series in [('hh',hh),('hv',hv)]:
            for t,values in enumerate(series):
                candidates=values.ravel()[eligible&np.isfinite(values.ravel())]
                p['peer_counts'][key].append(len(candidates))
                if len(candidates)>=10:
                    median=float(np.median(candidates))
                    spread=1.4826*float(np.median(np.abs(candidates-median)))
                    p['peer'][key+'_med'][t]=clean(median)
                    p['peer'][key+'_sd'][t]=clean(spread) if spread>0 else None
        p['peers']=p['peer_counts']['hv'][-1]
    limitations.append('Peers use sparse preview locations within 1 km, minimum 10 valid samples; median and 1.4826*MAD; no deformation peer band')
    provenance=dict(created_at=datetime.now(timezone.utc).isoformat(),inputs=receipts,
        worldcover=dict(url=WORLD,year=2021,version='v200',subset_path=(target/'worldcover.npz').relative_to(ROOT).as_posix(),sha256=hashlib.sha256((target/'worldcover.npz').read_bytes()).hexdigest(),attribution='© ESA WorldCover project 2021 / Contains modified Copernicus Sentinel data (2021) processed by ESA WorldCover consortium'),
        reference=dict(index=reference,lat=float(lat.ravel()[reference]),lon=float(lon.ravel()[reference]),component=component,coherence=clean(a['coherence'].ravel()[reference])) if reference is not None else None,
        steps=['Authenticated HTTP Range read of HDF5 native windows; subset arrays saved with SHA-256',
        f"Check track {CASE['track']} ascending frame {CASE['frame']}, frequency A, GCOV HH/HV, exact GUNW reference/secondary date match",
        f"Transform WGS84 preview locations to EPSG:{receipts[0]['grid']['epsg']}, nearest native samples; reject GCOV mask 0/255, nonfinite/nonpositive power; 10log10 gamma0",
        'GUNW HH 80m: coherence >=0.7, valid nonwater subswaths, no RSLC anomaly flags, ionosphere screen uncertainty <=1 rad; bit24 interpolation flagged, retain only reference connected component',
        'Subtract ionosphere screen, then spatial reference phase; convert with -c/(4*pi*f)*100 cm, positive toward sensor; epoch zero is a reference definition',
        'Sample ESA WorldCover 2021 v200 at preview coordinates',
        'Per channel/date same-class preview peers within 1 km, exclude self, minimum 10; median and 1.4826*MAD'],limitations=limitations,
        sign_source='https://github.com/isce-framework/isce3/blob/develop/cxx/isce3/signal/Crossmul.cpp',
        counts=dict(gcov_hh=[int(np.isfinite(x).sum()) for x in hh],gcov_hv=[int(np.isfinite(x).sum()) for x in hv],gunw_valid=int(valid.sum())))
    site=dict(schema_version=2,id=CASE['id'],name=CASE['name'],region=f'Real GCOV + GUNW · {dates[0]} – {dates[-1]}',center=[float(lat.mean()),float(lon.mean())],zoom=15,
        source='NISAR PROVISIONAL GCOV + GUNW · ESA WorldCover 2021',status='measured_pair',message=f'Measured HH/HV for {dates[0]} – {dates[1]} ({days} days). GUNW accepted: {int(valid.sum())}/{N*N} samples. Atmospheric residuals remain; no trend or anomaly classification.',
        event=None,dates=dates,displacement_dates=dates,grid=dict(n=N,bbox=BBOX,cellM=None),pixels=pixels,provenance=provenance)
    output=ROOT/'data'/f"{CASE['id']}.json"
    analyze_site(site)
    temporary=output.with_suffix('.tmp')
    temporary.write_text(json.dumps(site,allow_nan=False,separators=(',',':'))+'\n')
    temporary.replace(output)
    print(json.dumps(provenance['counts']),flush=True)

def main():
    auth=earthaccess.login(strategy='interactive',persist=False)
    if not auth.authenticated: raise SystemExit('Login failed')
    extract(json.loads((ROOT/'data/mexico-manifest.json').read_text()),earthaccess.get_fsspec_https_session())

if __name__=='__main__': main()
