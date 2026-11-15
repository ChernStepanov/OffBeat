"""Discover possible new GCOV granules; does not download or publish measurements."""
import argparse
import json
from datetime import datetime, timezone
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from scripts.operations import ROOT, SITES


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('site', choices=SITES)
    args = parser.parse_args()
    site = json.loads((ROOT / 'data' / (args.site + '.json')).read_text(encoding='utf-8'))
    bbox = site['grid']['bbox']
    params = {'short_name': 'NISAR_L2_GCOV_PROVISIONAL_V1',
              'bounding_box': ','.join(str(bbox[k]) for k in ('w', 's', 'e', 'n')),
              'temporal': site['dates'][-1] + 'T00:00:00Z,', 'page_size': '100',
              'sort_key': '-start_date'}
    url = 'https://cmr.earthdata.nasa.gov/search/granules.json?' + urlencode(params)
    with urlopen(Request(url, headers={'User-Agent': 'OffBeat-update-discovery/1.0'}), timeout=60) as response:
        hits = int(response.headers.get('CMR-Hits', '0'))
        entries = json.load(response)['feed']['entry']
    report = {'site': args.site, 'checked_at': datetime.now(timezone.utc).isoformat(),
              'query': url, 'hits': hits, 'truncated': hits > len(entries),
              'last_prepared_date': site['dates'][-1],
              'candidates': [{'concept_id': e['id'], 'producer_id': e.get('producer_granule_id'),
                              'start': e.get('time_start'), 'end': e.get('time_end')}
                             for e in entries],
              'limitations': ['Catalogue overlap is not valid-pixel coverage.',
                              'Track, polarizations, masks and measurement compatibility require verification.',
                              'No files were downloaded, processed, or published.']}
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
