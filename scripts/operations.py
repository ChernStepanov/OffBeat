"""Offline inventory and public endpoint checks; never reads credentials."""
import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
SITES = ('mexico', 'amazon', 'venezuela', 'delhi', 'tokyo', 'khimki', 'nairobi', 'sydney')


def inventory(root=ROOT):
    result, errors = [], []
    for name in SITES:
        try:
            path = root / 'data' / (name + '.json')
            raw = path.read_bytes()
            data = json.loads(raw)
            grid = data['grid']
            if (data['id'] != name or data['schema_version'] != 2 or
                    not data['provenance']['inputs'] or
                    len(data['pixels']) != grid['n'] ** 2):
                raise ValueError('invalid data contract')
            dates = data['dates']
            if dates != sorted(set(dates)):
                raise ValueError('dates are not strictly increasing')
            result.append({'id': name, 'bbox': grid['bbox'], 'dates': dates,
                           'displacement_dates': data['displacement_dates'],
                           'samples': len(data['pixels']),
                           'sha256': hashlib.sha256(raw).hexdigest(),
                           'path': 'data/' + name + '.json'})
        except (OSError, ValueError, KeyError, TypeError) as exc:
            errors.append({'id': name, 'error': str(exc)})
    return {'schema_version': 1, 'created_utc': datetime.now(timezone.utc).isoformat(),
            'sites': result, 'errors': errors,
            'limitation': 'Bounding boxes describe prepared sparse samples, not complete coverage.'}


def probe(url):
    try:
        with urlopen(Request(url, headers={'User-Agent': 'OffBeat-health-check/1.0'}), timeout=15) as response:
            body = response.read(1024 * 1024)
            if not 200 <= response.status < 300:
                raise ValueError('HTTP ' + str(response.status))
            if '/api/v1/health' in url and json.loads(body).get('status') != 'ok':
                raise ValueError('unhealthy API response')
            if '/api/v1/health' not in url and b'OffBeat' not in body:
                raise ValueError('response does not contain OffBeat')
            return {'url': url, 'ok': True, 'status': response.status}
    except (URLError, OSError, ValueError) as exc:
        return {'url': url, 'ok': False, 'error': str(exc)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('inventory', 'probe'))
    parser.add_argument('urls', nargs='*', help='Explicit URLs to probe; no telemetry is sent elsewhere')
    args = parser.parse_args()
    if args.command == 'inventory':
        result = inventory()
        failed = bool(result['errors'])
    else:
        if not args.urls:
            parser.error('probe requires at least one URL')
        checks = [probe(url) for url in args.urls]
        result, failed = {'checks': checks}, any(not check['ok'] for check in checks)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return int(failed)


if __name__ == '__main__':
    sys.exit(main())
