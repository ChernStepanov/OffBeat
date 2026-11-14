"""Extract genuine GCOV samples and inspect GUNW; never invent missing channels."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import h5py
import numpy as np
from pyproj import Transformer

ROOT = Path(__file__).resolve().parents[1]

def sample(group, dataset, lat, lon):
    """Nearest native cell; no interpolation across nodata or outside footprint."""
    ds = group[dataset]
    xs, ys = group['xCoordinates'][:], group['yCoordinates'][:]
    epsg = int(group['projection'][()])
    xx, yy = Transformer.from_crs(4326, epsg, always_xy=True).transform(lon, lat)
    dx, dy = float(xs[1] - xs[0]), float(ys[1] - ys[0])
    col, row = int(np.floor((xx - xs[0]) / dx + .5)), int(np.floor((yy - ys[0]) / dy + .5))
    if not (0 <= col < len(xs) and 0 <= row < len(ys)):
        return None
    value = float(ds[row, col])
    fill = ds.attrs.get('_FillValue')
    if not np.isfinite(value) or (fill is not None and value == fill):
        return None
    return value

def db(value):
    return round(float(10 * np.log10(value)), 4) if value is not None and value > 0 else None

def main():
    raw = ROOT / 'data/raw'
    receipt = json.loads((raw / 'download-receipt.json').read_text())
    for record in receipt:
        digest = hashlib.sha256()
        with (raw / record['file']).open('rb') as stream:
            for block in iter(lambda: stream.read(8 * 1024 * 1024), b''):
                digest.update(block)
        if digest.hexdigest() != record['sha256']:
            raise ValueError('Input changed since download: ' + record['file'])
    gcov = sorted([r for r in receipt if '_GCOV_' in r['id']], key=lambda r:r['start'])
    if len(gcov) < 2:
        raise ValueError('Need two GCOV acquisitions')
    dates = [r['start'][:10] for r in gcov]
    n = 24
    bbox = dict(w=-99.25, s=19.25, e=-98.9, n=19.6)
    pixels = []
    for y in range(n):
        for x in range(n):
            pixels.append(dict(id=f'MEX r{y} c{x}', lat=bbox['n']-(y+.5)/n*(bbox['n']-bbox['s']),
                lon=bbox['w']+(x+.5)/n*(bbox['e']-bbox['w']), cover=None, peers=None, z=None,
                style=None, since=None, hh=[], hv=[], disp=None, peer_disp=None,
                peer={k:[None]*len(dates) for k in ['hh_med','hh_sd','hv_med','hv_sd']}))
    inspections = []
    for record in receipt:
        with h5py.File(raw / record['file'], 'r') as hdf:
            datasets = []
            hdf.visititems(lambda name, obj: datasets.append(dict(path=name, shape=list(obj.shape), dtype=str(obj.dtype))) if isinstance(obj, h5py.Dataset) else None)
            inspections.append(dict(granule=record['id'], datasets=datasets))
            if record not in gcov:
                continue
            group = hdf['science/LSAR/GCOV/grids/frequencyA']
            # Fail loudly on an incompatible product; do not relabel other polarizations.
            if not all(k in group for k in ['HHHH','HVHV','projection','xCoordinates','yCoordinates']):
                raise ValueError('GCOV frequency A HH/HV grid unavailable')
            for p in pixels:
                p['hh'].append(db(sample(group, 'HHHH', p['lat'], p['lon'])))
                p['hv'].append(db(sample(group, 'HVHV', p['lat'], p['lon'])))
    result = dict(schema_version=2, id='mexico', name='Mexico City', region='Measured GCOV · GUNW validation pending',
        center=[19.425,-99.075], zoom=11, source='NISAR PROVISIONAL GCOV (frequency A)', event=None,
        status='partial', message='Real GCOV samples. GUNW displacement, WorldCover and peer statistics not yet validated.',
        dates=dates, displacement_dates=[], grid=dict(n=n,bbox=bbox,cellM=None), pixels=pixels,
        provenance=dict(created_at=datetime.now(timezone.utc).isoformat(),inputs=receipt,
          steps=['Verify SHA-256 of downloaded HDF5 products','Inspect every input dataset path, shape and dtype',
          'Sample native frequencyA HHHH/HVHV cells at 24x24 WGS84 preview locations using product EPSG',
          'Reject nonfinite, fill and nonpositive power; convert gamma0 power with 10*log10',
          'No synthetic land cover, peers, z-score, classifier or displacement'],
          limitations=['Sparse preview samples, not area aggregates or a native-resolution raster',
          'GUNW not yet converted: phase sign, corrections and spatial reference require validation',
          'No WorldCover input: same-class comparisons unavailable']))
    (ROOT / 'data/mexico-inspection.json').write_text(json.dumps(inspections, indent=2)+'\n')
    output = ROOT / 'data/mexico.json'
    temporary = output.with_suffix('.tmp')
    temporary.write_text(json.dumps(result, allow_nan=False, separators=(',', ':'))+'\n')
    temporary.replace(output)
    print('Wrote real GCOV preview; GUNW remains explicitly unavailable pending validation.')

if __name__ == '__main__':
    main()
