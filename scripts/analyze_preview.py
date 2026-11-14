"""Пересчитать соседей, z-score и формы изменения без сети и Earthdata."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline.preview import analyze_site


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--site', choices=['all', 'mexico', 'amazon', 'venezuela'], default='all')
    args = parser.parse_args()
    for name in ('mexico', 'amazon', 'venezuela') if args.site == 'all' else [args.site]:
        path = ROOT / 'data' / f'{name}.json'
        site = json.loads(path.read_text())
        summary = analyze_site(site)
        temporary = path.with_suffix('.tmp')
        temporary.write_text(json.dumps(site, allow_nan=False, separators=(',', ':')) + '\n')
        temporary.replace(path)
        print(name, json.dumps(summary, ensure_ascii=False))


if __name__ == '__main__':
    main()
