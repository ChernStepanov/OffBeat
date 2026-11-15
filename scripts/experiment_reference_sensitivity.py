"""Reproduce a retrospective GNSS anchoring sensitivity check; no event detection."""
import hashlib
import json
from pathlib import Path

from scripts.findings import opera_tied, opera_vs_gnss

ROOT = Path(__file__).resolve().parents[1]


def main():
    paths = ('data/mexico.json', 'data/mexico/opera-disp.json',
             'data/analysis/mexico-mmx1-gnss.json')
    results = []
    for radius in (100, 200, 400, 800):
        result = opera_tied(anchor_m=radius)
        results.append({key: result[key] for key in ('anchor_radius_m', 'anchor_samples',
                        'anchor_opera_cm_per_year', 'percentiles_5_50_95', 'sinking_share', 'assumptions')})
    report = {'kind': 'retrospective_sensitivity_not_validation',
              'input_sha256': {path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for path in paths},
              'comparison': opera_vs_gnss(), 'anchor_radius_sensitivity': results,
              'limitations': ['Same GNSS station is used to anchor and evaluate: not independent validation.',
                              'Radius is varied after inspecting data, not a preregistered experiment.',
                              'GNSS and OPERA windows differ; incidence angle and horizontal motion are approximated.',
                              'One anchor cannot verify a regional deformation field or establish reference stability.',
                              'Formal regression errors omit systematic and temporally correlated errors.']}
    print(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == '__main__':
    main()
