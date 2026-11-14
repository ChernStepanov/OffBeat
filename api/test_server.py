import json
import threading
import unittest
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import urlopen

from api.server import Handler, dispatch, patches


class APITest(unittest.TestCase):
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

    def test_sites_and_pixel_series(self):
        sites = self.get('/sites')
        self.assertEqual({s['id'] for s in sites['items']}, {'mexico', 'amazon', 'venezuela'})
        pixel = self.get('/sites/mexico/pixels/0')
        self.assertEqual(len(pixel['dates']), len(pixel['pixel']['hv']))
        self.assertEqual(len(pixel['displacement_dates']), len(pixel['pixel']['disp']))
        self.assertIn('inputs', self.get('/sites/mexico/provenance'))

    def test_pagination_date_and_signals(self):
        date = self.get('/sites/mexico/acquisitions')['dates'][0]
        result = self.get('/sites/mexico/pixels?limit=1&offset=1&date=' + date)
        self.assertEqual(result['items'][0]['index'], 1)
        self.assertEqual(result['items'][0]['hv'], self.get('/sites/mexico/pixels/1')['pixel']['hv'][0])
        self.assertEqual(self.get('/sites/mexico/signals')['total'], 0)

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


if __name__ == '__main__':
    unittest.main()
