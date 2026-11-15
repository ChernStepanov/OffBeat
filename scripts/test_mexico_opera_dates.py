"""Independent regression checks against the archived OPERA timing audit."""
import json
from pathlib import Path
from audit_mexico_opera_dates import audit

ROOT = Path(__file__).resolve().parents[1]
expected = json.loads((ROOT / 'data/analysis/mexico-opera-date-audit.json').read_text(encoding='utf-8-sig'))
actual = audit()
assert actual == expected, 'Archived OPERA audit is stale'
assert actual['opera_count'] == 15
assert (actual['accepted_min'], actual['accepted_max']) == (1018, 1021)
assert actual['nisar_opera_date_offsets']['ascending'][0][0]['offset_days'] == 14
assert all(item['offset_days'] == 1 for pair in actual['nisar_opera_date_offsets']['descending'] for item in pair)
print('PASS: OPERA source integrity, accepted observations and independent date offsets')
