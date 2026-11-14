"""Preserve a dated MMX1 GNSS window and audit the closest NISAR sample's quality."""
import datetime as dt,hashlib,json
from pathlib import Path
import numpy as np,requests
from pyproj import Geod
ROOT=Path(__file__).resolve().parents[1]
URL='https://geodesy.unr.edu/gps_timeseries/IGS20/tenv3/IGS20/MMX1.tenv3'
START=dt.date(2025,12,17);END=dt.date(2026,2,10)

def accepted(a,i,j):
    m=int(a['mask'][i,j]);sw=m&255
    return bool(np.isfinite(a['phase'][i,j]) and np.isfinite(a['iono'][i,j]) and np.isfinite(a['coherence'][i,j]) and a['coherence'][i,j]>=.7 and 0<a['component'][i,j]<65535 and sw<100 and sw//10>0 and sw%10>0 and ((m>>8)&65535)==0 and (m&0xFE000000)==0 and np.isfinite(a['iono_sd'][i,j]) and a['iono_sd'][i,j]<=1)

def main():
    response=requests.get(URL,timeout=90);response.raise_for_status();raw=response.content;lines=raw.decode('utf-8').splitlines()
    records=[];selected=[]
    for line in lines[1:]:
        fields=line.split()
        if len(fields)<23 or fields[0]!='MMX1':continue
        try: date=dt.datetime.strptime(fields[1],'%y%b%d').date()
        except ValueError:continue
        if not START<=date<=END:continue
        nums=[float(fields[i]) for i in [7,8,9,10,11,12,14,15,16,20,21]]
        if not all(np.isfinite(nums)):raise ValueError('Nonfinite GNSS record')
        selected.append(line)
        records.append({'date':date.isoformat(),'east_m':nums[0]+nums[1],'north_m':nums[2]+nums[3],'up_m':nums[4]+nums[5],'sigma_east_m':nums[6],'sigma_north_m':nums[7],'sigma_up_m':nums[8],'latitude':nums[9],'longitude':nums[10]})
    records.sort(key=lambda p:p['date'])
    if not records or len(records)!=len(set(r['date'] for r in records)):raise ValueError('Missing or duplicate GNSS records')
    target=ROOT/'data/subsets/mmx1-gnss';target.mkdir(parents=True,exist_ok=True);rawpath=target/'2025-12-17_2026-02-10.tenv3';rawpath.write_text(lines[0]+'\n'+'\n'.join(selected)+'\n',encoding='utf-8')
    site=json.loads((ROOT/'data/mexico.json').read_text());pixels=site['pixels'];lat=records[-1]['latitude'];lon=records[-1]['longitude']
    _,_,dist=Geod(ellps='WGS84').inv([lon]*len(pixels),[lat]*len(pixels),[p['lon'] for p in pixels],[p['lat'] for p in pixels]);idx=int(np.argmin(dist));row,col=divmod(idx,site['grid']['n'])
    quality=json.loads((ROOT/'data/analysis/mexico-gunw-postgap-quality.json').read_text());diagnosis={}
    for direction,segment in quality['directions'].items():
        pairs=[]
        for p in segment['pairs']:
            receipt=json.loads((ROOT/p['subset_receipt']).read_text());file=ROOT/receipt['subset_path']
            if hashlib.sha256(file.read_bytes()).hexdigest()!=receipt['sha256']:raise ValueError('GUNW subset hash mismatch')
            a=np.load(file);pairs.append({'reference_date':p['reference_date'],'secondary_date':p['secondary_date'],'granule_id':p['granule_id'],'quality_accepted':accepted(a,row,col),'coherence':round(float(a['coherence'][row,col]),4) if np.isfinite(a['coherence'][row,col]) else None,'ionosphere_uncertainty_rad':round(float(a['iono_sd'][row,col]),4) if np.isfinite(a['iono_sd'][row,col]) else None})
        diagnosis[direction]=pairs
    out={'station':'MMX1','source':'Nevada Geodetic Laboratory, 24-hour final GNSS solutions, IGS20', 'source_url':URL,'station_page':'https://geodesy.unr.edu/NGLStationPages/stations/MMX1.sta','format_reference':'https://geodesy.unr.edu/gps_timeseries/readmes/README_tenv3.txt','processing_citation':'https://eos.org/project-updates/harnessing-the-gps-data-explosion-for-interdisciplinary-science','operator_reference':'https://geodesy.noaa.gov/CORS/sort_sites.shtml',
      'retrieved_utc':dt.datetime.now(dt.timezone.utc).isoformat(),'source_sha256':hashlib.sha256(raw).hexdigest(),'subset_path':rawpath.relative_to(ROOT).as_posix(),'subset_sha256':hashlib.sha256(rawpath.read_bytes()).hexdigest(),
      'window':[START.isoformat(),END.isoformat()],'method':'Select only daily rows in window; combine integer and fractional ENU positions and retain original standard deviations. No interpolation, smoothing, outlier filtering, trend fitting or conversion to radar line of sight.',
      'limitations':'GNSS measures antenna position in IGS20; it is not a stable reference and is not the same measurement footprint or viewing geometry as an 80 m NISAR radar cell. The nearest radar sample does not pass all quality masks. No direct GNSS/InSAR validation, reference stability, vertical radar velocity or deformation decomposition is inferred.',
      'station_coordinates':{'lat':lat,'lon':lon},'nearest_nisar_sample':{'id':pixels[idx]['id'],'index':idx,'lat':pixels[idx]['lat'],'lon':pixels[idx]['lon'],'distance_m':round(float(dist[idx]),2)},'gunw_quality_at_nearest_sample':diagnosis,'records':records}
    dest=ROOT/'data/analysis/mexico-mmx1-gnss.json';dest.write_text(json.dumps(out,indent=2)+'\n',encoding='utf-8')
    print('GNSS records:',len(records),'nearest sample:',pixels[idx]['id'],'distance m:',round(float(dist[idx]),2))
    for direction,pairs in diagnosis.items():print(direction,'quality accepted:',sum(p['quality_accepted'] for p in pairs),'/',len(pairs))

if __name__=='__main__':main()
