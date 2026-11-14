"""Audit quality continuity of sampled Mexico GUNW pairs; do not infer velocity."""
import hashlib,json
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1]

def main():
    report={'source':'NISAR PROVISIONAL GUNW / ASF DAAC','sample_grid':'32x32 existing Mexico coordinates, nearest native 80 m samples',
      'method':'Per pair require finite phase and ionosphere, coherence >=0.7, valid component and nonwater subswaths, no RSLC anomaly flags and ionosphere uncertainty <=1 rad. Then intersect pointwise masks across consecutive pairs. Connected components, stable reference, atmospheric residuals and viewing geometry require separate assessment.',
      'limitations':'Short initial segments only; quality overlap is necessary but not sufficient for a displacement chain. A zero count is a result of this conservative mask, not proof of no motion. No velocity or vertical/east decomposition is estimated.',
      'directions':{}}
    for direction in ('ascending','descending'):
        files=sorted((ROOT/'data/subsets/mexico-gunw-series'/direction).glob('*.json'))
        if len(files)!=3:raise ValueError(f'{direction}: expected three receipts')
        rows=[];masks=[];lat=lon=None;previous=None
        for path in files:
            r=json.loads(path.read_text());p=ROOT/r['subset_path'];
            if hashlib.sha256(p.read_bytes()).hexdigest()!=r['sha256']:raise ValueError('Subset hash mismatch')
            a=np.load(p)
            if lat is None:lat,lon=a['lat'],a['lon']
            if not(np.array_equal(lat,a['lat']) and np.array_equal(lon,a['lon'])):raise ValueError('Coordinates differ')
            if previous and r['reference_date']!=previous:raise ValueError('Non-consecutive pairs')
            previous=r['secondary_date'];mask=a['mask'].astype(np.uint32);sw=mask&255
            checks={'phase_finite':np.isfinite(a['phase']),'ionosphere_finite':np.isfinite(a['iono']),
              'coherence_at_least_0_7':np.isfinite(a['coherence'])&(a['coherence']>=.7),
              'component_valid':(a['component']>0)&(a['component']<65535),
              'nonwater_valid_subswaths':(sw<100)&((sw//10)>0)&((sw%10)>0),
              'no_anomaly_flags':(((mask>>8)&65535)==0)&((mask&0xFE000000)==0),
              'ionosphere_uncertainty_at_most_1_rad':np.isfinite(a['iono_sd'])&(a['iono_sd']<=1)}
            valid=np.logical_and.reduce(list(checks.values()));masks.append(valid)
            if int(valid.sum())!=r['quality_valid_count']:raise ValueError('Quality count mismatch')
            rows.append({'reference_date':r['reference_date'],'secondary_date':r['secondary_date'],'granule_id':r['source']['id'],'concept_id':r['source']['concept_id'],'subset_receipt':path.relative_to(ROOT).as_posix(),'valid_count':int(valid.sum()),'individual_check_counts':{k:int(v.sum()) for k,v in checks.items()},'flag_bits_set_counts':{str(i):int(((mask>>i)&1).sum()) for i in range(8,32) if ((mask>>i)&1).any()}})
        report['directions'][direction]={'pairs':rows,'quality_valid_in_all_pairs':int(np.logical_and.reduce(masks).sum())}
    dest=ROOT/'data/analysis/mexico-gunw-quality.json';dest.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print('Common quality-valid samples:',{k:v['quality_valid_in_all_pairs'] for k,v in report['directions'].items()})

if __name__=='__main__':main()
