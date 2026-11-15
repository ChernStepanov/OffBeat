"""Local-only static UI + API server for testing shared-review integration."""
import argparse
import os
import tempfile
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit, unquote
from api.server import Handler

ROOT = Path(__file__).resolve().parent.parent


class DevHandler(Handler, SimpleHTTPRequestHandler):
    def do_POST(self):
        host = urlsplit('//'+self.headers.get('Host', '')).hostname
        if host not in ('127.0.0.1', 'localhost', '::1'):
            self.respond(403, {'error': 'Local host required'}); return
        return Handler.do_POST(self)

    def do_GET(self):
        if any(part.startswith('.') for part in unquote(urlsplit(self.path).path).split('/') if part):
            self.send_error(404); return
        if urlsplit(self.path).path.startswith('/api/'):
            return Handler.do_GET(self)
        return SimpleHTTPRequestHandler.do_GET(self)

    def do_HEAD(self):
        if any(part.startswith('.') for part in unquote(urlsplit(self.path).path).split('/') if part):
            self.send_error(404); return
        return SimpleHTTPRequestHandler.do_HEAD(self)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8873)
    parser.add_argument('--database', default=str(Path(tempfile.gettempdir()) / 'offbeat-dev-reviews.sqlite3'))
    args = parser.parse_args()
    Path(args.database).resolve().parent.mkdir(parents=True, exist_ok=True)
    os.environ['OFFBEAT_REVIEWS_DB'] = args.database
    os.chdir(ROOT)
    server = ThreadingHTTPServer(('127.0.0.1', args.port), DevHandler)
    print(f'Local test: http://127.0.0.1:{args.port}/', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
