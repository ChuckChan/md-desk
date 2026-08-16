#!/usr/bin/env python
"""Frozen-binary URL runtime smoke (Stage 2).

Frozen with the SAME collection flags as the real md-desk build, this entry
proves the URL pipeline works inside a PyInstaller bundle:
    UrlFetchService.fetch -> BytesIO + StreamInfo -> MarkItDown.convert_stream()

It starts a LOCAL mock HTTP server (bound to 127.0.0.1) and fetches a tiny
HTML page through the frozen modules. The local host is allow-listed on the
validator purely so the test can reach the loopback mock; the production
validator uses an empty allow-list (loopback always blocked).

Run (frozen) from the markitdown-gui dir:
    ./dist/urltest/urltest.exe
"""

import io
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from src.url_fetch_service import FetchError, StrictTargetValidator, UrlFetchService
from src.converter import convert_url


HTML = b"<html><head><title>Smoke</title></head><body><h1>Frozen</h1><p>UrlOk</p></body></html>"


class _H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(HTML)))
        self.end_headers()
        self.wfile.write(HTML)


def main():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    host, port = srv.server_address
    url = f"http://127.0.0.1:{port}/page.html"

    validator = StrictTargetValidator(allow_hosts=("127.0.0.1",))
    svc = UrlFetchService(validator=validator, connect_timeout=5, read_timeout=5)

    try:
        res = svc.fetch(url)
        print("FETCH_OK final_url=%s ext=%s mime=%s" % (
            res.final_url, res.stream_info.extension, res.stream_info.mimetype))
        md = convert_url(url, service=svc)
        print("CONVERT_OK len=%d" % len(md))
        assert "Frozen" in md and "UrlOk" in md, "unexpected markdown: %r" % md
        print("MARKDOWN_CONTAINS_EXPECTED_TEXT")

        # Security in the frozen binary: the strict (empty allow-list) validator
        # must refuse a loopback target (same address the mock listens on).
        strict = UrlFetchService(validator=StrictTargetValidator(),
                                 connect_timeout=5, read_timeout=5)
        try:
            strict.fetch("http://127.0.0.1:%d/page.html" % port)
            print("FROZEN_SECURITY_FAIL: loopback not blocked")
            srv.shutdown(); srv.server_close()
            return 1
        except FetchError as e:
            print("FROZEN_SECURITY_OK blocked_category=%s" % e.category.value)

        print("ALL_FROZEN_URL_CHECKS_PASSED")
        srv.shutdown()
        srv.server_close()
        return 0
    except Exception as exc:  # noqa: BLE001
        print("FROZEN_URL_FAILED:", type(exc).__name__, exc)
        srv.shutdown()
        srv.server_close()
        return 1


if __name__ == "__main__":
    sys.exit(main())
