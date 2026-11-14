"""Serve only the local site preview and static assets on loopback."""
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]


class PreviewHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        requested = unquote(urlsplit(self.path).path)
        target = (ROOT / requested.lstrip('/')).resolve()
        if requested in ('/', '/index.html') or (target.is_relative_to(ROOT / 'assets') and target.is_file()):
            return super().do_GET()
        self.send_error(404, 'Not part of the static preview')


if __name__ == '__main__':
    print('Preview: http://127.0.0.1:8767/#competitor', flush=True)
    ThreadingHTTPServer(('127.0.0.1', 8767), partial(PreviewHandler, directory=str(ROOT))).serve_forever()
