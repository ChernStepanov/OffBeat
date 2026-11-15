"""Read-only HTTP API for the prepared OffBeat datasets (Python standard library)."""
import argparse
import json
import math
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / 'data'
SITES = ('mexico', 'amazon', 'venezuela', 'delhi', 'tokyo', 'khimki', 'nairobi', 'sydney')
CONTEXT = {'fires': 'amazon/fires.json', 'alerts': 'amazon/alerts.geojson',
           'ranking': 'amazon-ranking-experiment.json'}


class APIError(Exception):
    def __init__(self, status, message):
        self.status, self.message = status, message


def load(path):
    try:
        with path.open(encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError) as exc:
        raise APIError(503, 'Dataset unavailable or invalid') from exc


def site_data(site_id):
    if site_id not in SITES:
        raise APIError(404, 'Unknown site')
    site = load(DATA / (site_id + '.json'))
    if (site.get('id') != site_id or site.get('schema_version') != 2
            or not site.get('provenance', {}).get('inputs')
            or any(word in site.get('source', '').lower() for word in ('synthetic', 'mock'))):
        raise APIError(503, 'Dataset does not meet measured data contract')
    return site


def number(params, key, default, minimum=None, maximum=None, integer=False):
    value = params.get(key, [str(default)])[0]
    try:
        result = int(value) if integer else float(value)
        if not math.isfinite(result) or (minimum is not None and result < minimum) or (maximum is not None and result > maximum):
            raise ValueError()
        return result
    except ValueError:
        raise APIError(400, f'Invalid {key}')


def page(items, params):
    limit = number(params, 'limit', 100, 1, 1000, True)
    offset = number(params, 'offset', 0, 0, integer=True)
    return {'total': len(items), 'limit': limit, 'offset': offset, 'items': items[offset:offset + limit]}


def summary(site):
    return {k: v for k, v in site.items() if k not in ('pixels', 'provenance')}


def patches(site, threshold):
    pixels, n = site['pixels'], site['grid']['n']
    if site.get('analysis_status') == 'exploratory_sparse_samples':
        result = [{'style': p['style'], 'cells': 1, 'peak_index': i,
                   'peak_pixel_id': p['id'], 'peak_z': p['z'], 'since': p.get('since'),
                   'mean_abs_z': abs(p['z'])}
                  for i, p in enumerate(pixels)
                  if p.get('style') and p.get('z') is not None and abs(p['z']) >= threshold]
        return sorted(result, key=lambda p: -p['mean_abs_z'])
    seen, result = set(), []
    for i, p in enumerate(pixels):
        if i in seen or not p.get('style') or p.get('z') is None or abs(p['z']) < threshold:
            continue
        stack, group = [i], []
        seen.add(i)
        while stack:
            current = stack.pop()
            group.append(current)
            x, y = current % n, current // n
            for nx, ny in ((x+1,y),(x-1,y),(x,y+1),(x,y-1)):
                j = ny*n+nx
                if 0 <= nx < n and 0 <= ny < n and j not in seen:
                    q = pixels[j]
                    if q.get('style') == p['style'] and q.get('z') is not None and abs(q['z']) >= threshold:
                        seen.add(j)
                        stack.append(j)
        if len(group) >= 3:
            peak = max(group, key=lambda j: abs(pixels[j]['z']))
            result.append({'style': p['style'], 'cells': len(group), 'peak_index': peak,
                           'peak_pixel_id': pixels[peak]['id'], 'peak_z': pixels[peak]['z'],
                           'since': pixels[peak].get('since'),
                           'mean_abs_z': sum(abs(pixels[j]['z']) for j in group)/len(group)})
    return sorted(result, key=lambda p: -p['cells'] * p['mean_abs_z'])


def dispatch(path, params):
    parts = [unquote(p) for p in path.strip('/').split('/')]
    if parts == ['api', 'v1', 'health']:
        errors = []
        for name in SITES:
            try:
                site_data(name)
            except APIError:
                errors.append(name)
        if errors:
            raise APIError(503, 'Prepared datasets unavailable: ' + ', '.join(errors))
        return {'status': 'ok', 'datasets': len(SITES)}
    if parts == ['api', 'v1']:
        return {'name': 'OffBeat API', 'version': 1, 'documentation': '/api/v1/help', 'sites': '/api/v1/sites'}
    if parts == ['api', 'v1', 'help']:
        return {'documentation': 'See docs/api.md', 'endpoints': ['/api/v1/sites', '/api/v1/sites/{site}', '/api/v1/sites/{site}/pixels', '/api/v1/sites/{site}/pixels/{index}', '/api/v1/sites/{site}/signals', '/api/v1/sites/{site}/patches', '/api/v1/sites/{site}/acquisitions', '/api/v1/sites/{site}/provenance', '/api/v1/sites/amazon/context/{fires|alerts|ranking}']}
    if parts == ['api', 'v1', 'sites']:
        items, errors = [], []
        for name in SITES:
            try:
                items.append(summary(site_data(name)))
            except APIError as exc:
                errors.append({'site': name, 'error': exc.message})
        return {'items': items, 'errors': errors}
    if len(parts) < 4 or parts[:3] != ['api', 'v1', 'sites']:
        raise APIError(404, 'Unknown endpoint')
    site = site_data(parts[3])
    if len(parts) == 4:
        return summary(site)
    resource = parts[4]
    if len(parts) == 5 and resource == 'provenance':
        return site['provenance']
    if len(parts) == 5 and resource == 'acquisitions':
        return {'dates': site['dates'], 'displacement_dates': site['displacement_dates'],
                'hv_available': [sum(p['hv'][i] is not None for p in site['pixels']) for i in range(len(site['dates']))]}
    if len(parts) == 5 and resource == 'patches':
        threshold = number(params, 'min_abs_z', 2, 0)
        return {'min_abs_z': threshold, **page(patches(site, threshold), params)}
    if len(parts) == 6 and resource == 'context' and parts[3] == 'amazon' and parts[5] in CONTEXT:
        return load(DATA / CONTEXT[parts[5]])
    if resource == 'pixels' and len(parts) == 6:
        try:
            i = int(parts[5])
            if i < 0 or i >= len(site['pixels']):
                raise ValueError()
        except ValueError:
            raise APIError(404, 'Unknown pixel index')
        return {'index': i, 'row': i // site['grid']['n'], 'col': i % site['grid']['n'], 'pixel': site['pixels'][i],
                'dates': site['dates'], 'displacement_dates': site['displacement_dates']}
    if len(parts) == 5 and resource in ('pixels', 'signals'):
        items = []
        style = params.get('style', [None])[0]
        if style is not None and style not in ('drop', 'flood', 'drift', 'step'):
            raise APIError(400, 'Invalid style')
        threshold = number(params, 'min_abs_z', 0, 0) if 'min_abs_z' in params else None
        date = params.get('date', [None])[0]
        if date is not None and date not in site['dates']:
            raise APIError(400, 'Unknown acquisition date')
        di = site['dates'].index(date) if date is not None else None
        for i, p in enumerate(site['pixels']):
            if resource == 'signals' and (p.get('style') is None or p.get('z') is None):
                continue
            if style is not None and p.get('style') != style:
                continue
            if threshold is not None and (p.get('z') is None or abs(p['z']) < threshold):
                continue
            item = {'index': i, 'row': i // site['grid']['n'], 'col': i % site['grid']['n'],
                    **{k: p.get(k) for k in ('id', 'lat', 'lon', 'cover', 'peers', 'z', 'style', 'since')}}
            if di is not None:
                item.update({'date': date, 'hh': p['hh'][di], 'hv': p['hv'][di]})
            items.append(item)
        if resource == 'signals':
            items.sort(key=lambda p: -abs(p['z']))
        return page(items, params)
    raise APIError(404, 'Unknown endpoint')


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        url = urlsplit(self.path)
        try:
            result = dispatch(url.path, parse_qs(url.query, keep_blank_values=True))
            status = 200
        except APIError as exc:
            status, result = exc.status, {'error': {'status': exc.status, 'message': exc.message}}
        body = json.dumps(result, ensure_ascii=False, allow_nan=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers()
        self.wfile.write(body)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8766)
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f'OffBeat API listening on http://{args.host}:{args.port}/api/v1', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
