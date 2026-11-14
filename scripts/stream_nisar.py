"""Read genuine NISAR HDF5 subsets through authenticated HTTP range requests."""
import json
from pathlib import Path
import earthaccess
import h5py

ROOT = Path(__file__).resolve().parents[1]

def main():
    auth = earthaccess.login(strategy='interactive', persist=False)
    if not auth.authenticated:
        raise SystemExit('Earthdata login failed')
    manifest = json.loads((ROOT/'data/mexico-manifest.json').read_text())
    selected = manifest['products']['gcov'][:2] + manifest['products']['gunw'][:1]
    fs = earthaccess.get_fsspec_https_session()
    inspections = []
    for record in selected:
        print('Inspecting', record['id'], flush=True)
        with fs.open(record['url'], block_size=1024*1024, cache_type='blockcache') as remote:
            with h5py.File(remote, 'r') as hdf:
                datasets = []
                def visit(name, obj):
                    if isinstance(obj, h5py.Dataset):
                        entry = dict(path=name, shape=list(obj.shape), dtype=str(obj.dtype),
                            attrs={k:str(v) for k,v in obj.attrs.items()})
                        if obj.size < 10:
                            entry['value'] = str(obj[()])
                        datasets.append(entry)
                hdf.visititems(visit)
                inspections.append(dict(granule=record, datasets=datasets))
                (ROOT/'data/mexico-inspection.json').write_text(json.dumps(inspections,indent=2)+'\n')
                for d in datasets:
                    if any(k in d['path'] for k in ['HHHH','HVHV','unwrappedPhase','connectedComponents','coherenceMagnitude','ionospherePhaseScreen','centerFrequency','radarCenterFrequency','zeroDopplerStartTime','trackNumber','frameNumber','orbitPassDirection','mask']):
                        print(json.dumps(d),flush=True)

if __name__=='__main__':
    main()
