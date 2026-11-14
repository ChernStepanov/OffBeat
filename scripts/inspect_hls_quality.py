"""Inspect HLS v2 Fmask quality for the first recorded CMR page at the Caracas AOI.

Requires a locally supplied Earthdata token. Writes a receipt, never credentials or signed URLs.
"""
import datetime as dt
import json
import os
from pathlib import Path

import numpy as np
import rasterio
import requests
from rasterio.warp import transform_bounds
from rasterio.windows import from_bounds

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / 'data/venezuela/optical/index.json'
OUTPUT = ROOT / 'data/subsets/venezuela-hls/2025-11-21-quality.json'
TOKEN_FILE = ROOT / '.earthdata_token'


def main():
    token = os.environ.get('EARTHDATA_TOKEN') or TOKEN_FILE.read_text().strip()
    index = json.loads(INDEX.read_text(encoding='utf-8'))
    entry = next(e for e in index['entries'] if e['nisar_date'] == '2025-11-21')
    b = index['bbox']
    candidates = []
    for collection in entry['hls_catalogue']:
        for granule in collection['granules']:
            ident = granule['producer_id']
            if '.T19PGM.' not in ident:
                continue
            links = [link['href'] for link in granule['links'] if link.get('href', '').startswith('https://data.lpdaac.earthdatacloud.nasa.gov/') and link['href'].endswith('.Fmask.tif')]
            if not links:
                continue
            try:
                response = requests.get(links[0], headers={'Authorization': 'Bearer ' + token, 'Range': 'bytes=0-0'}, allow_redirects=False, timeout=30)
                if response.status_code != 303:
                    candidates.append({'producer_id': ident, 'error': f'HTTP {response.status_code}'})
                    continue
                with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN='EMPTY_DIR', GDAL_HTTP_TIMEOUT='20', CPL_VSIL_CURL_ALLOWED_EXTENSIONS='.tif'):
                    with rasterio.open('/vsicurl/' + response.headers['Location']) as src:
                        bounds = transform_bounds('EPSG:4326', src.crs, b['w'], b['s'], b['e'], b['n'])
                        window = from_bounds(*bounds, src.transform).round_offsets().round_lengths()
                        mask = src.read(1, window=window, masked=True)
                        clear = (~np.ma.getmaskarray(mask)) & ((mask.filled(255) & 30) == 0)
                        candidates.append({'producer_id': ident, 'clear_fraction': round(float(clear.mean()), 3)})
            except Exception as exc:
                # Do not print the exception: GDAL messages can contain signed URLs.
                candidates.append({'producer_id': ident, 'error': type(exc).__name__})
            print(ident, candidates[-1].get('clear_fraction', candidates[-1].get('error')), flush=True)
    receipt = {
        'source': 'NASA LP DAAC HLS v2.0', 'source_catalogue': str(INDEX.relative_to(ROOT)),
        'nisar_date': entry['nisar_date'], 'inspected_at': dt.datetime.now(dt.timezone.utc).isoformat(),
        'scope': 'First page of recorded CMR HLS candidates for tile T19PGM; not an exhaustive search',
        'mask': 'Fmask: exclude fill and bits 1 cloud, 2 adjacent cloud/shadow, 3 cloud shadow, 4 snow/ice; transform AOI bounds to source CRS and read nearest whole-pixel window',
        'threshold': 0.8,
        'limitations': 'Fractions rounded to 3 decimal places; HLS 30m and five-pixel cloud adjacency are more conservative than the Sentinel-2 SCL mask. No image generated.',
        'candidates': candidates,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
