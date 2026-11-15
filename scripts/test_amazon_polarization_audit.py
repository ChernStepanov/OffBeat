import json
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]


class PolarizationAuditTest(unittest.TestCase):
    def test_cell_and_neighbourhood_from_native_arrays(self):
        report = json.loads((ROOT / 'data/analysis/amazon-dense-polarizations-2026-11-15.json').read_text(encoding='utf-8'))
        before, after = [np.load(ROOT / x['subset_path']) for x in report['inputs']]
        self.assertEqual(len(report['items']), 5)
        for item in report['items']:
            row, col = item['row'], item['col']
            for channel in ('hh', 'hv'):
                expected = 10 * np.log10(float(after[channel][row, col]) / float(before[channel][row, col]))
                self.assertAlmostEqual(expected, item[channel]['cell_delta_db'], places=2)
                values = []
                for r in range(max(row-1, 0), min(row+2, before[channel].shape[0])):
                    for c in range(max(col-1, 0), min(col+2, before[channel].shape[1])):
                        a, b = float(before[channel][r, c]), float(after[channel][r, c])
                        if all(0 < int(x['mask'][r, c]) < 255 for x in (before, after)) and np.isfinite(a) and np.isfinite(b) and a > 0 and b > 0:
                            values.append(10 * np.log10(b/a))
                self.assertEqual(len(values), item[channel]['near_3x3']['count'])
                self.assertAlmostEqual(float(np.median(values)), item[channel]['near_3x3']['median_db'], places=2)


if __name__ == '__main__':
    unittest.main()
