#!/usr/bin/env python
"""Stage 2 — Safe Remote URL verification.

Uses a LOCAL mock HTTP server (no public internet) to exercise:

  SECURITY (StrictTargetValidator, empty allow-list):
    - file:// rejected (SCHEME)
    - localhost rejected (BLOCKED)
    - private IP (10.0.0.5) rejected (BLOCKED)
    - 169.254.169.254 (metadata) rejected (BLOCKED)
    - public -> private redirect rejected (BLOCKED on 2nd hop)
    - redirect loop rejected (REDIRECT cap)
    - timeout -> TIMEOUT error
    - oversize download -> TOO_LARGE error

  FUNCTIONAL (StrictTargetValidator with the mock host allow-listed so we can
  reach the local server; production uses an empty allow-list):
    - HTML URL   -> non-empty markdown + expected text
    - TXT  URL   -> non-empty markdown + expected text
    - PDF  URL   -> non-empty markdown + expected text
    - fetch() returns StreamInfo with correct url/extension/mimetype

  EVIDENCE:
    - is_safe_ip table (loopback / private / link-local / global / v6)
    - convert_uri NOT referenced anywhere in src/ (we never call MarkItDown.convert_uri)

Run from project root:
    python tests/test_url_stage2.py
"""

import io
import socket
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.url_fetch_service import (
    FetchError,
    FetchErrorCategory,
    StrictTargetValidator,
    UrlFetchService,
    is_safe_ip,
)
from src.converter import convert_url


def _check(name, cond, detail=""):
    print(("PASS" if cond else "FAIL"), "-", name, "" if cond else f":: {detail}")
    return cond


# ---- mock server ------------------------------------------------------------
HTML_BODY = b"<html><head><title>Hi</title></head><body><h1>Hello</h1><p>World</p></body></html>"
TXT_BODY = b"Plain text content line one.\nSecond line here."


def _make_pdf() -> bytes:
    from fpdf import FPDF

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=20)
    pdf.cell(0, 10, "Pdf Title")
    pdf.set_font("Helvetica", size=12)
    pdf.ln(15)
    pdf.multi_cell(0, 8, "Pdf Body Text from remote URL.")
    out = io.BytesIO()
    pdf.output(out)
    return out.getvalue()


PDF_BODY = _make_pdf()


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # silence
        pass

    def _send(self, code, body, ctype, extra=None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def do_GET(self):
        p = self.path.split("?", 1)[0]
        if p == "/page.html":
            self._send(200, HTML_BODY, "text/html; charset=utf-8")
        elif p == "/doc.txt":
            self._send(200, TXT_BODY, "text/plain; charset=utf-8")
        elif p == "/file.pdf":
            self._send(200, PDF_BODY, "application/pdf")
        elif p == "/named.pdf":
            self._send(200, PDF_BODY, "application/pdf",
                       {"Content-Disposition": 'attachment; filename="report.pdf"'})
        elif p == "/redirect_private":
            self._send(302, b"", "text/plain",
                       {"Location": "http://169.254.169.254/secret"})
        elif p == "/loop":
            self._send(302, b"", "text/plain", {"Location": self._loop_target()})
        elif p == "/slow":
            time.sleep(2.0)  # longer than the test read timeout
            self._send(200, b"too late", "text/plain")
        elif p == "/big":
            chunk = b"X" * 4096
            self._send(200, chunk, "application/octet-stream")
        else:
            self._send(404, b"not found", "text/plain")

    def _loop_target(self):
        host, port = self.server.server_address
        return f"http://127.0.0.1:{port}/loop"

    def do_HEAD(self):
        self.do_GET()


def _start_server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    host, port = server.server_address
    return server, f"127.0.0.1:{port}", f"http://127.0.0.1:{port}"


# ---- tests ------------------------------------------------------------------
def test_is_safe_ip():
    print("\n--- SECURITY: is_safe_ip classification ---")
    ok = True
    safe = [("8.8.8.8", True), ("1.1.1.1", True), ("9.9.9.9", True),
            ("2001:4860:4860::8888", True)]
    blocked = [("127.0.0.1", False), ("10.0.0.5", False), ("192.168.1.1", False),
               ("172.16.5.5", False), ("169.254.169.254", False), ("169.254.1.1", False),
               ("0.0.0.0", False), ("224.0.0.1", False), ("255.255.255.255", False),
               ("::1", False), ("fe80::1", False), ("fc00::1", False),
               ("100.64.0.1", False)]
    for ip, expect in safe + blocked:
        got = is_safe_ip(ip)
        ok &= _check(f"is_safe_ip({ip})=={expect}", got == expect, f"got {got}")
    return ok


def test_scheme_and_target_blocks():
    print("\n--- SECURITY: scheme / SSRF target blocks (no connection) ---")
    ok = True
    svc = UrlFetchService()  # strict, empty allow-list
    cases = [
        ("file:///C:/Windows/notepad.exe", FetchErrorCategory.SCHEME),
        ("file:///etc/passwd", FetchErrorCategory.SCHEME),
        ("ftp://example.com/x", FetchErrorCategory.SCHEME),
        ("http://localhost/secret", FetchErrorCategory.BLOCKED),
        ("http://127.0.0.1/secret", FetchErrorCategory.BLOCKED),
        ("http://[::1]/secret", FetchErrorCategory.BLOCKED),
        ("http://10.0.0.5/secret", FetchErrorCategory.BLOCKED),
        ("http://192.168.1.1/secret", FetchErrorCategory.BLOCKED),
        ("http://169.254.169.254/latest/meta-data", FetchErrorCategory.BLOCKED),
    ]
    for url, cat in cases:
        try:
            svc.fetch(url)
            ok &= _check(f"BLOCK {url}", False, "no exception raised")
        except FetchError as exc:
            ok &= _check(f"BLOCK {url} -> {cat.value}", exc.category == cat,
                         f"got {exc.category.value}: {exc.message}")
        except Exception as exc:  # noqa: BLE001
            ok &= _check(f"BLOCK {url}", False, f"wrong exception {type(exc).__name__}: {exc}")
    return ok


def _allow() -> StrictTargetValidator:
    # Permit the local mock host so functional tests can reach 127.0.0.1.
    return StrictTargetValidator(allow_hosts=("127.0.0.1",))


def test_functional(server_url):
    print("\n--- FUNCTIONAL: HTML / TXT / PDF via safe fetch + convert_stream ---")
    ok = True
    svc = UrlFetchService(validator=_allow(), connect_timeout=5, read_timeout=5)

    # HTML
    try:
        out = convert_url(server_url + "/page.html", service=svc)
    except Exception as exc:  # noqa: BLE001
        return _check("HTML URL convert", False, repr(exc))
    ok &= _check("HTML markdown non-empty", bool(out and out.strip()), f"len={len(out)}")
    ok &= _check("HTML contains Hello/World", "Hello" in out and "World" in out)

    # TXT
    try:
        out = convert_url(server_url + "/doc.txt", service=svc)
    except Exception as exc:  # noqa: BLE001
        return _check("TXT URL convert", False, repr(exc))
    ok &= _check("TXT markdown non-empty", bool(out and out.strip()), f"len={len(out)}")
    ok &= _check("TXT contains plain text", "Plain text content" in out)

    # PDF
    try:
        out = convert_url(server_url + "/file.pdf", service=svc)
    except Exception as exc:  # noqa: BLE001
        return _check("PDF URL convert", False, repr(exc))
    ok &= _check("PDF markdown non-empty", bool(out and out.strip()), f"len={len(out)}")
    ok &= _check("PDF contains body text", "Pdf Body Text" in out)
    return ok


def test_stream_info(server_url):
    print("\n--- EVIDENCE: fetch() StreamInfo fields ---")
    ok = True
    svc = UrlFetchService(validator=_allow(), connect_timeout=5, read_timeout=5)
    try:
        res = svc.fetch(server_url + "/named.pdf")
    except Exception as exc:  # noqa: BLE001
        return _check("fetch StreamInfo", False, repr(exc))
    ok &= _check("stream_info.url == final_url",
                 res.stream_info.url == server_url + "/named.pdf")
    ok &= _check("stream_info.extension == .pdf",
                 (res.stream_info.extension or "").lower() == ".pdf",
                 repr(res.stream_info.extension))
    ok &= _check("stream_info.mimetype == application/pdf",
                 res.stream_info.mimetype == "application/pdf",
                 repr(res.stream_info.mimetype))
    ok &= _check("stream_info.filename == report.pdf",
                 res.stream_info.filename == "report.pdf",
                 repr(res.stream_info.filename))
    return ok


def test_redirect_to_private(server_url):
    print("\n--- SECURITY: public -> private redirect blocked ---")
    svc = UrlFetchService(validator=_allow(), connect_timeout=5, read_timeout=5)
    try:
        svc.fetch(server_url + "/redirect_private")
        return _check("public->private redirect BLOCKED", False, "no exception")
    except FetchError as exc:
        return _check("public->private redirect BLOCKED",
                      exc.category == FetchErrorCategory.BLOCKED,
                      f"got {exc.category.value}: {exc.message}")
    except Exception as exc:  # noqa: BLE001
        return _check("public->private redirect BLOCKED", False, repr(exc))


def test_redirect_loop(server_url):
    print("\n--- SECURITY: redirect loop blocked ---")
    svc = UrlFetchService(validator=_allow(), max_redirects=5,
                          connect_timeout=5, read_timeout=5)
    try:
        svc.fetch(server_url + "/loop")
        return _check("redirect loop BLOCKED", False, "no exception")
    except FetchError as exc:
        return _check("redirect loop BLOCKED",
                      exc.category == FetchErrorCategory.REDIRECT,
                      f"got {exc.category.value}: {exc.message}")
    except Exception as exc:  # noqa: BLE001
        return _check("redirect loop BLOCKED", False, repr(exc))


def test_timeout(server_url):
    print("\n--- SECURITY: read timeout -> TIMEOUT error ---")
    svc = UrlFetchService(validator=_allow(), connect_timeout=5, read_timeout=0.5)
    try:
        svc.fetch(server_url + "/slow")
        return _check("timeout TIMEOUT", False, "no exception")
    except FetchError as exc:
        return _check("timeout -> TIMEOUT", exc.category == FetchErrorCategory.TIMEOUT,
                      f"got {exc.category.value}: {exc.message}")
    except Exception as exc:  # noqa: BLE001
        return _check("timeout -> TIMEOUT", False, repr(exc))


def test_oversize(server_url):
    print("\n--- SECURITY: oversize download blocked ---")
    svc = UrlFetchService(validator=_allow(), connect_timeout=5, read_timeout=5,
                          max_size=1024)
    try:
        svc.fetch(server_url + "/big")
        return _check("oversize TOO_LARGE", False, "no exception")
    except FetchError as exc:
        return _check("oversize -> TOO_LARGE",
                      exc.category == FetchErrorCategory.TOO_LARGE,
                      f"got {exc.category.value}: {exc.message}")
    except Exception as exc:  # noqa: BLE001
        return _check("oversize -> TOO_LARGE", False, repr(exc))


def _strip_docstrings_comments(src: str) -> str:
    import re

    src = re.sub(r'"""[\s\S]*?"""', "", src)
    src = re.sub(r"'''[\s\S]*?'''", "", src)
    src = re.sub(r"#[^\n]*", "", src)
    return src


def test_no_convert_uri():
    print("\n--- EVIDENCE: convert_uri NOT used in src/ ---")
    src_dir = ROOT / "src"
    hits = []
    for f in src_dir.rglob("*.py"):
        code = _strip_docstrings_comments(f.read_text(encoding="utf-8"))
        # Genuine call sites only (prose/docstrings already stripped):
        #   - any 'convert_uri' reference (MarkItDown's unsafe method)
        #   - '.convert_url(' (MarkItDown's convert_uri alias, called as a method)
        if "convert_uri" in code:
            hits.append((f.name, "convert_uri"))
        if ".convert_url(" in code:
            hits.append((f.name, ".convert_url("))
    ok = _check("no convert_uri / MarkItDown.convert_url calls", not hits, str(hits))
    # Positive control: converter must use convert_stream.
    conv = _strip_docstrings_comments((src_dir / "converter.py").read_text(encoding="utf-8"))
    ok &= _check("converter uses convert_stream", "convert_stream(" in conv)
    return ok


def main():
    server, _, server_url = _start_server()
    try:
        results = [
            test_is_safe_ip(),
            test_scheme_and_target_blocks(),
            test_functional(server_url),
            test_stream_info(server_url),
            test_redirect_to_private(server_url),
            test_redirect_loop(server_url),
            test_timeout(server_url),
            test_oversize(server_url),
            test_no_convert_uri(),
        ]
    finally:
        server.shutdown()
        server.server_close()

    ok = all(results)
    print("\n" + ("ALL STAGE 2 URL CHECKS PASSED" if ok else "SOME STAGE 2 CHECKS FAILED"))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
