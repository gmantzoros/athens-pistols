#!/usr/bin/env python3
"""
Local helper for the website check. Serves this folder on http://127.0.0.1:8766
and saves page snapshots that verify/extract.js posts to /save?name=... into
verify/out/. Only listens on this computer.

Usage:  python verify/collect_server.py
Then open http://127.0.0.1:8766/site/index.html and run verify/extract.js in it.
"""
import http.server
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = Path(__file__).resolve().parent / "out"


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def do_POST(self):
        query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        raw = query.get("name", ["snapshot"])[0]
        name = "".join(c if c.isalnum() or c in "-_." else "_" for c in raw)[:160] or "snapshot"
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        OUT.mkdir(exist_ok=True)
        (OUT / f"{name}.json").write_bytes(body)
        self.send_response(204)
        self.end_headers()

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    print("Serving on http://127.0.0.1:8766/site/index.html")
    http.server.ThreadingHTTPServer(("127.0.0.1", 8766), Handler).serve_forever()
