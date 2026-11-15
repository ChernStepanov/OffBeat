import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.operations import inventory, probe


class OperationsTest(unittest.TestCase):
    def test_inventory_detects_missing_and_invalid_datasets(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'data').mkdir()
            (root / 'data' / 'mexico.json').write_text(json.dumps({'id': 'wrong'}))
            result = inventory(root)
            self.assertEqual(len(result["errors"]), 7)
            self.assertEqual(result['sites'], [])

    def test_inventory_indexes_real_datasets(self):
        result = inventory()
        self.assertEqual(result['errors'], [])
        self.assertEqual(len(result["sites"]), 7)
        self.assertTrue(all(len(site['sha256']) == 64 for site in result['sites']))

    def test_probe_reports_network_failure(self):
        with patch('scripts.operations.urlopen', side_effect=OSError('offline')):
            self.assertFalse(probe('https://example.invalid/')['ok'])


if __name__ == '__main__':
    unittest.main()
