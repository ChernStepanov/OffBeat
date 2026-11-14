"""Freeze membership before scoring. Refuses to overwrite a registered protocol."""
import json
from pipeline.amazon_benchmark import ROOT, digest
import numpy as np


def freeze():
    folder = ROOT / 'data/benchmark/amazon-v1'
    if (folder / 'protocol.json').exists():
        raise FileExistsError('Protocol already frozen; use a new version for new data')
    folder.mkdir(parents=True, exist_ok=True)
    site = json.loads((ROOT / 'data/amazon.json').read_text())
    ids = sorted(p['id'] for p in site['pixels'])
    sources = ['data/amazon.json', 'data/analysis/amazon-era5.json']
    protocol = {'version': 1, 'registered_date': '2026-11-14', 'ids': ids,
                'input_sha256': {p: digest(ROOT / p) for p in sources},
                'event_group_rule': 'Entire 2.7 km AOI in one group; no pixel holdout is independent.',
                'assignments': [{'id': i, 'event_group': 'amazon-small-aoi-2026',
                                 'split': 'development'} for i in ids],
                'control_ids': sorted(np.random.default_rng(20261114).choice(ids, 20, replace=False).tolist()),
                'k': [5, 10, 20], 'threshold_db': 2.5,
                'target': 'persistent forest-cover loss; all methods are candidate rankings, not attribution',
                'comparison': 'mean first three versus mean last three HV dates; positive means drop',
                'weather': 'ridge=1; rain7/10; fit first three dates only; retrospective ablation',
                'test_admission': 'New spatially disjoint event groups with dated blind confirmed/refuted/unknown labels; new protocol required.'}
    (folder / 'protocol.json').write_text(json.dumps(protocol, indent=2) + '\n')
    archived = 'archive/preview-2026-11-14/data/amazon/validation/reviews.json'
    reviews = json.loads((ROOT / archived).read_text())
    samples = {i: [{'source': archived, 'source_sha256': digest(ROOT / archived),
                    'independence': 'previously inspected; not blind test label',
                    **review}] for i, review in reviews['candidates'].items()}
    samples['AMA r5 c15'] = [{'status': 'unknown', 'interval': ['2026-08-23', '2026-09-04'],
                             'source': 'data/analysis/amazon-dense-pair.json',
                             'note': 'SAR-only corroboration is not independent forest-loss evidence.'}]
    evidence = {'samples': samples, 'dated_optical': 'data/amazon/optical/index.json',
                'dated_alerts': 'archive/preview-2026-11-14/data/amazon/validation/alerts.geojson',
                'source_manifest': 'archive/preview-2026-11-14/data/amazon/validation/sources.json',
                'positive_control_limit': 'archive/preview-2026-11-14/docs/amazon-positive-eval.md',
                'policy': 'No alert absence or archived interpretation converted to a blind negative.'}
    (folder / 'evidence.json').write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + '\n')


if __name__ == '__main__':
    freeze()
