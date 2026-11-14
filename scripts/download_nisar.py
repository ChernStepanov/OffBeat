"""Download the first compatible Mexico GCOV pair and GUNW, using local EDL login."""
import argparse
import hashlib
import json
from pathlib import Path
import earthaccess

ROOT = Path(__file__).resolve().parents[1]

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--login-only', action='store_true')
    args = parser.parse_args()
    # Interactive password is hidden by earthaccess; no secrets in repo or arguments.
    auth = earthaccess.login(strategy='interactive', persist=False)
    if not auth.authenticated:
        raise SystemExit('Earthdata authentication failed')
    if args.login_only:
        return
    manifest = json.loads((ROOT / 'data/mexico-manifest.json').read_text())
    gcov = manifest['products']['gcov'][:2]
    gunw = manifest['products']['gunw'][:1]
    selected = gcov + gunw
    output = ROOT / 'data/raw'
    output.mkdir(parents=True, exist_ok=True)
    records = []
    for granule in selected:
        results = earthaccess.search_data(concept_id=granule['concept_id'])
        if len(results) != 1:
            raise RuntimeError(f"Expected one CMR result: {granule['id']}")
        files = earthaccess.download(results, local_path=str(output))
        hdf = [Path(f) for f in files if str(f).endswith('.h5')]
        if len(hdf) != 1:
            raise RuntimeError('Expected one HDF5 product')
        path = hdf[0]
        digest = hashlib.sha256()
        with path.open('rb') as stream:
            if stream.read(8) != b'\x89HDF\r\n\x1a\n':
                raise RuntimeError('Not HDF5 (possibly an authentication page)')
            stream.seek(0)
            for block in iter(lambda: stream.read(8 * 1024 * 1024), b''):
                digest.update(block)
        records.append({**granule, 'file': path.name, 'sha256': digest.hexdigest()})
    (output / 'download-receipt.json').write_text(json.dumps(records, indent=2) + '\n')
    print('Downloaded and checked 2 GCOV + 1 GUNW. Run scripts/prepare_nisar.py next.')

if __name__ == '__main__':
    main()
