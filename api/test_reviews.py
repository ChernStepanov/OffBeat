import json
import os
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from unittest.mock import patch

from api.server import Handler
from api import reviews


class SharedReviewsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {'OFFBEAT_REVIEWS_DB': os.path.join(self.temp.name, 'reviews.sqlite')})
        self.env.start()
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = 'http://127.0.0.1:%s/api/v1/reviews' % self.server.server_port
        cat = reviews.load(reviews.CATALOG)
        data = reviews.load(reviews.DATA.parent / cat['sites'][0]['path'])
        self.base = {'site': data['site'], 'marker': data['markers'][0]['id'], 'dataset': '.'.join(i['sha256'][:16] for i in data['inputs'] + data.get('optical_images', []))}

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(); self.env.stop(); self.temp.cleanup()

    def post(self, **changes):
        data = {**self.base, 'token': 'a' * 64, 'verdict': 'visible_change', 'basis': 'radar', **changes}
        req = Request(self.url, json.dumps(data).encode(), {'Content-Type': 'application/json'}, method='POST')
        with urlopen(req) as response:
            return json.load(response)['counts']

    def test_counts_are_shared_and_updates_not_duplicate(self):
        self.assertEqual(self.post()['visible_change'], 1)
        self.assertEqual(self.post(verdict='uncertain')['visible_change'], 0)
        self.assertEqual(self.post(token='b' * 64)['visible_change'], 1)
        with urlopen(self.url + '?' + urlencode(self.base)) as response:
            counts = json.load(response)['counts']
        self.assertEqual(counts['visible_change'], 1)
        self.assertEqual(counts['uncertain'], 1)
        self.assertEqual(self.post(verdict='clear')['uncertain'], 0)

    def test_invalid_candidate_and_token_are_rejected(self):
        for changes in ({'marker': 'fake'}, {'dataset': 'fake'}, {'token': 'short'}):
            with self.subTest(changes=changes), self.assertRaises(HTTPError):
                self.post(**changes)

    def test_shared_queue_moderation(self):
        def current():
            with urlopen(self.url.replace('/reviews', '/review-queue')) as response:
                items = json.load(response)['items']
            self.assertEqual(len(items), 192)
            return next(i for i in items if i['site'] == self.base['site'] and i['marker'] == self.base['marker'])
        self.post(verdict='uncertain')
        self.assertEqual(current()['status'], 'pending')
        self.post(verdict='visible_change')
        self.assertEqual(current()['status'], 'visible')
        self.post(token='b' * 64, verdict='no_visible_change')
        self.assertEqual(current()['status'], 'rejected')
        self.post(token='b' * 64, verdict='clear')
        self.assertEqual(current()['status'], 'visible')

    def test_database_must_be_configured(self):
        with patch.dict(os.environ, {}, clear=True), self.assertRaises(HTTPError) as error:
            urlopen(self.url + '?' + urlencode(self.base))
        self.assertEqual(error.exception.code, 503)


if __name__ == '__main__':
    unittest.main()
