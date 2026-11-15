import json
import threading
import unittest
from unittest.mock import patch
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from api.server import APIError, Handler, dispatch, patches


class APITest(unittest.TestCase):
    def test_health_reports_missing_dataset(self):
        with patch('api.server.site_data', side_effect=APIError(503, 'missing')):
            with self.assertRaises(APIError) as error:
                dispatch('/api/v1/health', {})
        self.assertEqual(error.exception.status, 503)

    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = 'http://127.0.0.1:%d/api/v1' % cls.server.server_port

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def get(self, path):
        with urlopen(self.url + path) as response:
            self.assertIn('application/json', response.headers['Content-Type'])
            return json.load(response)

    def test_removed_assistant_endpoint(self):
        request = Request(self.url + '/copilot', data=b'{"messages":[]}',
                          headers={'Content-Type': 'application/json'})
        with self.assertRaises(HTTPError) as error:
            urlopen(request)
        self.assertEqual(error.exception.code, 404)
        self.assertIn('Unknown endpoint', error.exception.read().decode())

    def test_sites_and_pixel_series(self):
        self.assertEqual(self.get('/health')['status'], 'ok')
        sites = self.get('/sites')
        self.assertEqual({s['id'] for s in sites['items']}, {'mexico', 'amazon', 'venezuela', 'delhi', 'tokyo', 'nairobi', 'sydney'})
        pixel = self.get('/sites/mexico/pixels/0')
        self.assertEqual(len(pixel['dates']), len(pixel['pixel']['hv']))
        self.assertEqual(len(pixel['displacement_dates']), len(pixel['pixel']['disp']))
        self.assertIn('inputs', self.get('/sites/mexico/provenance'))

    def test_pagination_date_and_signals(self):
        date = self.get('/sites/mexico/acquisitions')['dates'][0]
        result = self.get('/sites/mexico/pixels?limit=1&offset=1&date=' + date)
        self.assertEqual(result['items'][0]['index'], 1)
        self.assertEqual(result['items'][0]['hv'], self.get('/sites/mexico/pixels/1')['pixel']['hv'][0])
        signals = self.get('/sites/mexico/signals')
        self.assertTrue(all(p['style'] and p['z'] is not None for p in signals['items']))

    def test_context_and_errors(self):
        self.assertIsInstance(self.get('/sites/amazon/context/fires'), list)
        for path, status in [('/sites/nope', 404), ('/sites/mexico/pixels/-1', 404),
                             ('/sites/mexico/pixels?limit=0', 400), ('/sites/mexico/pixels?date=bad', 400),
                             ('/sites/mexico/context/fires', 404)]:
            with self.subTest(path=path), self.assertRaises(HTTPError) as error:
                self.get(path)
            self.assertEqual(error.exception.code, status)

    def test_patches_match_ui_connectivity(self):
        pixels = [{'id': str(i), 'style': 'drop', 'z': z, 'since': None} for i, z in enumerate([3, 4, None, 2, None, None, None, None, None])]
        result = patches({'grid': {'n': 3}, 'pixels': pixels}, 2)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['cells'], 3)
        self.assertEqual(result[0]['peak_index'], 1)

    def test_sparse_samples_are_not_joined_into_areas(self):
        pixels = [{'id': str(i), 'style': 'drop', 'z': z} for i, z in enumerate([3, 4, 2, 1])]
        result = patches({'analysis_status': 'exploratory_sparse_samples', 'grid': {'n': 2}, 'pixels': pixels}, 2)
        self.assertEqual([p['peak_index'] for p in result], [1, 0, 2])
        self.assertTrue(all(p['cells'] == 1 for p in result))


if __name__ == '__main__':
    unittest.main()
