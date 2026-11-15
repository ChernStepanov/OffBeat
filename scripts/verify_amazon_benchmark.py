"""Verify the frozen Amazon benchmark without replacing any receipts or outputs."""
import hashlib
import json
from pathlib import Path
from pipeline.amazon_benchmark import rank

ROOT = Path(__file__).resolve().parents[1]
FOLDER = ROOT / 'data/benchmark/amazon-v1'

def load(path):
    return json.loads(path.read_text(encoding='utf-8'))

def verify():
    protocol = load(FOLDER / 'protocol.json')
    results = load(FOLDER / 'results.json')
    for name, expected in protocol['input_sha256'].items():
        if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != expected:
            raise ValueError(f'Frozen input changed: {name}')
    rows = rank(load(ROOT / 'data/amazon.json'), load(ROOT / 'data/analysis/amazon-era5.json'), protocol)
    for name in ('history_drop_db', 'peer_drop_db', 'weather_drop_db'):
        eligible = sorted((r for r in rows if r[name] is not None), key=lambda r: (-r[name], r['id']))
        actual = [r['id'] for r in eligible]
        reference = results['methods'][name]
        flagged = sum(r[name] >= protocol['threshold_db'] for r in eligible)
        if actual != reference['ranking'] or flagged != reference['flagged_at_threshold']:
            raise ValueError(f'Benchmark results differ: {name}')
        print(f'{name}: {len(eligible)} eligible, {flagged} flagged; ranking matches')
    print(f"{len(rows)} samples, {len(set(r['event_group'] for r in rows))} development group; independent accuracy remains unknown")

if __name__ == '__main__':
    verify()
