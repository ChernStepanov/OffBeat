"""Opt-in shared candidate reviews; deploy only behind a protected same-origin proxy."""
import hashlib
import json
import os
import re
import sqlite3
from contextlib import closing
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / 'data'

class ReviewError(Exception):
    def __init__(self, status, message):
        self.status, self.message = status, message

def load(path):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        raise ReviewError(503, 'Dataset unavailable') from exc

CATALOG = DATA / 'change-candidates' / 'catalog-9b22c7d45ddb.json'
VERDICTS = ('visible_change', 'no_visible_change', 'uncertain')
BASES = ('optical', 'radar', 'both')


def database():
    name = os.environ.get('OFFBEAT_REVIEWS_DB')
    if not name:
        raise ReviewError(503, 'Shared reviews are not configured')
    conn = sqlite3.connect(name, timeout=5)
    conn.execute('CREATE TABLE IF NOT EXISTS reviews (dataset TEXT NOT NULL, site TEXT NOT NULL, marker TEXT NOT NULL, voter TEXT NOT NULL, verdict TEXT NOT NULL, basis TEXT NOT NULL, updated TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY(dataset, site, marker, voter))')
    return conn


def validate(site, marker, dataset):
    catalog = load(CATALOG)
    entry = next((s for s in catalog['sites'] if s['id'] == site), None)
    if not entry:
        raise ReviewError(404, 'Unknown site')
    root = DATA.parent.resolve()
    path = (root / entry['path']).resolve()
    if root not in path.parents:
        raise ReviewError(503, 'Invalid catalogue')
    data = load(path)
    expected = '.'.join(i['sha256'][:16] for i in data['inputs'] + data.get('optical_images', []))
    if dataset != expected or not any(m['id'] == marker for m in data['markers']):
        raise ReviewError(404, 'Unknown candidate or dataset')
    return data


def counts(site, marker, dataset):
    validate(site, marker, dataset)
    with closing(database()) as db:
        rows = db.execute('SELECT verdict, COUNT(*) FROM reviews WHERE dataset=? AND site=? AND marker=? GROUP BY verdict', (dataset, site, marker)).fetchall()
    return {'counts': {name: dict(rows).get(name, 0) for name in VERDICTS}, 'note': 'Unverified anonymous reviews; not independent validation.'}


def save(payload):
    if not isinstance(payload, dict):
        raise ReviewError(400, 'Invalid review')
    site, marker, dataset = (payload.get(k, '') for k in ('site', 'marker', 'dataset'))
    if not all(isinstance(v, str) for v in (site, marker, dataset)):
        raise ReviewError(400, 'Invalid candidate')
    data = validate(site, marker, dataset)
    token, verdict, basis = (payload.get(k, '') for k in ('token', 'verdict', 'basis'))
    if not isinstance(token, str) or not re.fullmatch(r'[a-f0-9]{64}', token):
        raise ReviewError(400, 'Invalid review token')
    if verdict not in VERDICTS + ('clear',) or (verdict != 'clear' and basis not in BASES):
        raise ReviewError(400, 'Invalid review')
    if verdict != 'clear' and basis in ('optical', 'both'):
        point = next(m for m in data['markers'] if m['id'] == marker)
        covered = {i.get('date') for i in data.get('optical_images', []) if i.get('bounds')
                   and i['bounds']['w'] <= point['lon'] <= i['bounds']['e']
                   and i['bounds']['s'] <= point['lat'] <= i['bounds']['n']}
        if not covered or (len(covered) < 2 and verdict != 'uncertain'):
            raise ReviewError(400, 'Insufficient optical coverage')
    voter = hashlib.sha256(token.encode('ascii')).hexdigest()
    with closing(database()) as db, db:
        if verdict == 'clear':
            db.execute('DELETE FROM reviews WHERE dataset=? AND site=? AND marker=? AND voter=?', (dataset, site, marker, voter))
        else:
            db.execute('INSERT INTO reviews(dataset,site,marker,voter,verdict,basis) VALUES(?,?,?,?,?,?) ON CONFLICT(dataset,site,marker,voter) DO UPDATE SET verdict=excluded.verdict,basis=excluded.basis,updated=CURRENT_TIMESTAMP', (dataset, site, marker, voter, verdict, basis))
    return counts(site, marker, dataset)
