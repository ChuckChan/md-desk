"""Stage 2 final: HTTPS/TLS acceptance for MdDesk UrlFetchService.

Local TLS fixtures only (NO public network). Generates a CA + server certs
with ``cryptography``, runs a local HTTPS server, and verifies:

  1. valid cert   (signed by trusted CA, SAN matches host)  -> fetch succeeds
  2. hostname mismatch (cert SAN != connected host)         -> SSL_ERROR
  3. untrusted / self-signed (different CA)                 -> SSL_ERROR
  4. DNS pinning:
       - TCP connects to the RESOLVED/VALIDATED IP (no rebind)
       - TLS server_hostname == ORIGINAL hostname (not the IP)
       - hostname verification is ON (not bypassed)
  5. allow_hosts is TEST-ONLY:
       - production path (convert_url default) blocks loopback
       - no env var / settings hook can enable it

Run:  python tests/test_tls_stage2.py   (from the project root)
"""
from __future__ import annotations

import datetime
import http.server
import ipaddress
import ssl
import socket
import threading
from pathlib import Path

# --- crypto (test-only fixture generation) ---------------------------------
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.url_fetch_service import (
    StrictTargetValidator,
    UrlFetchService,
    FetchErrorCategory,
)
from src.converter import convert_url, ConversionError

ROOT = Path(__file__).resolve().parent.parent
NOW = datetime.datetime.now(datetime.timezone.utc)
LATER = NOW + datetime.timedelta(days=2)

_PASSED = 0
_FAILED = 0


def _check(name: str, ok: bool, detail: str = "") -> bool:
    global _PASSED, _FAILED
    if ok:
        _PASSED += 1
        print(f"  [PASS] {name}")
    else:
        _FAILED += 1
        print(f"  [FAIL] {name}  {detail}")
    return ok


def _gen_ca():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subj = issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "MdDesk Test CA")])
    cert = (
        x509.CertificateBuilder()
        .subject_name(subj)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(NOW)
        .not_valid_after(LATER)
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .add_extension(
            x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False
        )
        .add_extension(
            x509.KeyUsage(
                digital_signature=False,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=True,
                crl_sign=True,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .sign(key, hashes.SHA256())
    )
    return key, cert


def _gen_server_cert(ca_key, ca_cert, cn: str, san_dns: list[str]):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subj = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])
    san = [x509.DNSName(d) for d in san_dns]
    san.append(x509.IPAddress(ipaddress.ip_address("127.0.0.1")))
    cert = (
        x509.CertificateBuilder()
        .subject_name(subj)
        .issuer_name(ca_cert.subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(NOW)
        .not_valid_after(LATER)
        .add_extension(x509.SubjectAlternativeName(san), critical=False)
        .add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()),
            critical=False,
        )
        .sign(ca_key, hashes.SHA256())
    )
    return key, cert


def _write_pem(key, cert, key_path: Path, cert_path: Path):
    key_path.write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))


class _Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):  # silence
        pass

    def do_GET(self):
        body = b"<html><body><h1>TLS OK</h1><p>pinned</p></body></html>"
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def _start_https(cert_path: Path, key_path: Path):
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(certfile=str(cert_path), keyfile=str(key_path))
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    httpd.socket = ctx.wrap_socket(httpd.socket, server_side=True)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    host, port = httpd.server_address
    return httpd, f"https://localhost:{port}/page.html"


def _trusting_context_factory(ca_pem_path: str):
    """Monkeypatch ssl.create_default_context to trust OUR test CA only.

    This mirrors the production code path (which calls
    ssl.create_default_context()) while letting us control trust WITHOUT
    polluting the system trust store or modifying production code.
    """
    orig = ssl.create_default_context

    def _fake(purpose=ssl.Purpose.SERVER_AUTH, *, cafile=None, capath=None, cadata=None):
        return orig(purpose=purpose, cafile=ca_pem_path, capath=capath, cadata=cadata)

    ssl.create_default_context = _fake
    return orig


def _patch_resolve(ip: str, hostname: str = "localhost"):
    """Force ``hostname`` to resolve to a single literal IP (IPv4).

    Avoids platform-dependent ::1/127.0.0.1 ordering; the server binds IPv4.
    """
    orig = socket.getaddrinfo

    def fake(host, port, *a, **k):
        if host == hostname:
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, port or 0))]
        return orig(host, port, *a, **k)

    socket.getaddrinfo = fake
    return orig


# ===========================================================================
def test_valid_cert(tmp):
    ca_key, ca_cert = _gen_ca()
    skey, scert = _gen_server_cert(ca_key, ca_cert, "localhost", ["localhost"])
    _write_pem(skey, scert, tmp / "valid_key.pem", tmp / "valid_cert.pem")
    _write_pem(ca_key, ca_cert, tmp / "ca_key.pem", tmp / "ca_cert.pem")

    httpd, url = _start_https(tmp / "valid_cert.pem", tmp / "valid_key.pem")
    orig = _trusting_context_factory(str(tmp / "ca_cert.pem"))
    orig_ga = _patch_resolve("127.0.0.1")
    try:
        svc = UrlFetchService(
            validator=StrictTargetValidator(allow_hosts=("localhost",)),
            connect_timeout=5, read_timeout=5,
        )
        res = svc.fetch(url)
        md = res.stream_info  # noqa
        # re-run through converter to confirm end-to-end markdown
        from markitdown import MarkItDown
        out = MarkItDown().convert_stream(res.content, stream_info=res.stream_info).markdown
        ok = _check("valid HTTPS cert -> fetch succeeds", "TLS OK" in out)
    except Exception as e:
        ok = _check("valid HTTPS cert -> fetch succeeds", False, f"{type(e).__name__}: {e}")
    finally:
        ssl.create_default_context = orig
        socket.getaddrinfo = orig_ga
        httpd.shutdown(); httpd.server_close()
    return ok


def test_hostname_mismatch(tmp):
    ca_key, ca_cert = _gen_ca()
    # cert is for example.com, but we CONNECT to localhost
    skey, scert = _gen_server_cert(ca_key, ca_cert, "example.com", ["example.com"])
    _write_pem(skey, scert, tmp / "mm_key.pem", tmp / "mm_cert.pem")
    _write_pem(ca_key, ca_cert, tmp / "ca_key.pem", tmp / "ca_cert.pem")

    httpd, url = _start_https(tmp / "mm_cert.pem", tmp / "mm_key.pem")
    orig = _trusting_context_factory(str(tmp / "ca_cert.pem"))
    orig_ga = _patch_resolve("127.0.0.1")
    try:
        svc = UrlFetchService(
            validator=StrictTargetValidator(allow_hosts=("localhost",)),
            connect_timeout=5, read_timeout=5,
        )
        try:
            svc.fetch(url)
            _check("hostname mismatch -> SSL_ERROR", False, "expected FetchError")
            ok = False
        except Exception as e:
            cat = getattr(e, "category", None)
            ok = _check(
                "hostname mismatch -> SSL_ERROR",
                cat == FetchErrorCategory.SSL_ERROR,
                f"got {cat}",
            )
    finally:
        ssl.create_default_context = orig
        socket.getaddrinfo = orig_ga
        httpd.shutdown(); httpd.server_close()
    return ok


def test_untrusted_cert(tmp):
    # A DIFFERENT CA signs the server cert; client only trusts our test CA.
    other_key, other_cert = _gen_ca()
    skey, scert = _gen_server_cert(other_key, other_cert, "localhost", ["localhost"])
    _write_pem(skey, scert, tmp / "bad_key.pem", tmp / "bad_cert.pem")
    # Client's trusted CA is a separate one (ca_cert.pem) that did NOT sign scert
    ca_key, ca_cert = _gen_ca()
    _write_pem(ca_key, ca_cert, tmp / "ca_key.pem", tmp / "ca_cert.pem")

    httpd, url = _start_https(tmp / "bad_cert.pem", tmp / "bad_key.pem")
    orig = _trusting_context_factory(str(tmp / "ca_cert.pem"))
    orig_ga = _patch_resolve("127.0.0.1")
    try:
        svc = UrlFetchService(
            validator=StrictTargetValidator(allow_hosts=("localhost",)),
            connect_timeout=5, read_timeout=5,
        )
        try:
            svc.fetch(url)
            _check("untrusted/self-signed -> SSL_ERROR", False, "expected FetchError")
            ok = False
        except Exception as e:
            cat = getattr(e, "category", None)
            ok = _check(
                "untrusted/self-signed -> SSL_ERROR",
                cat == FetchErrorCategory.SSL_ERROR,
                f"got {cat}",
            )
    finally:
        ssl.create_default_context = orig
        socket.getaddrinfo = orig_ga
        httpd.shutdown(); httpd.server_close()
    return ok


def test_dns_pinning(tmp):
    """Prove: TCP to verified IP, SNI=original host, hostname verification on."""
    ca_key, ca_cert = _gen_ca()
    skey, scert = _gen_server_cert(ca_key, ca_cert, "localhost", ["localhost"])
    _write_pem(skey, scert, tmp / "valid_key.pem", tmp / "valid_cert.pem")
    _write_pem(ca_key, ca_cert, tmp / "ca_cert.pem", tmp / "ca_cert.pem")

    httpd, url = _start_https(tmp / "valid_cert.pem", tmp / "valid_key.pem")
    orig_cdc = _trusting_context_factory(str(tmp / "ca_cert.pem"))
    orig_ga = _patch_resolve("127.0.0.1")

    cap_conn = {}
    cap_wrap = {}
    orig_cc = socket.create_connection
    orig_wrap = ssl.SSLContext.wrap_socket

    def fake_cc(addr, *a, **k):
        cap_conn["addr"] = addr
        return orig_cc(addr, *a, **k)

    def fake_wrap(self, sock, **kwargs):
        # Ignore the SERVER's per-connection TLS wrap (server_side=True); we
        # only care about the CLIENT handshake (server_hostname verification).
        if not kwargs.get("server_side"):
            cap_wrap["server_hostname"] = kwargs.get("server_hostname")
            cap_wrap["check_hostname"] = self.check_hostname
            cap_wrap["verify_mode"] = self.verify_mode
        return orig_wrap(self, sock, **kwargs)

    try:
        socket.create_connection = fake_cc
        ssl.SSLContext.wrap_socket = fake_wrap
        svc = UrlFetchService(
            validator=StrictTargetValidator(allow_hosts=("localhost",)),
            connect_timeout=5, read_timeout=5,
        )
        svc.fetch(url)
    except Exception as e:
        print(f"    (fetch raised during pinning probe: {type(e).__name__}: {e})")
    finally:
        socket.create_connection = orig_cc
        ssl.SSLContext.wrap_socket = orig_wrap
        ssl.create_default_context = orig_cdc
        socket.getaddrinfo = orig_ga
        httpd.shutdown(); httpd.server_close()

    # Evidence assertions
    ok = True
    addr = cap_conn.get("addr")
    ok &= _check(
        "DNS pinning: TCP connects to the resolved/validated IP (127.0.0.1)",
        addr is not None and addr[0] == "127.0.0.1",
        f"addr={addr}",
    )
    ok &= _check(
        "DNS pinning: TLS server_hostname == original hostname (localhost), NOT the IP",
        cap_wrap.get("server_hostname") == "localhost",
        f"server_hostname={cap_wrap.get('server_hostname')}",
    )
    ok &= _check(
        "DNS pinning: hostname verification enabled (check_hostname=True, CERT_REQUIRED)",
        cap_wrap.get("check_hostname") is True
        and cap_wrap.get("verify_mode") == ssl.CERT_REQUIRED,
        f"check_hostname={cap_wrap.get('check_hostname')} verify_mode={cap_wrap.get('verify_mode')}",
    )
    return ok


def test_allow_hosts_test_only():
    """Production cannot enable allow_hosts; loopback stays blocked."""
    # 1) default validator has an EMPTY allow-list
    v = StrictTargetValidator()
    ok = _check("allow_hosts default is empty in production validator",
                getattr(v, "_allow", None) == set() or len(getattr(v, "_allow", set())) == 0)

    # 2) production path (convert_url with NO injected service) blocks loopback
    from src.file_entry import FileStatus
    try:
        convert_url("http://127.0.0.1/")
        ok = _check("production convert_url blocks loopback (no allow_hosts)", False,
                    "expected ConversionError") and ok
    except ConversionError as e:
        # mapped to ERROR with a 安全拦截 (BLOCKED) message
        blocked = e.status == FileStatus.ERROR and "安全拦截" in e.message
        ok = _check("production convert_url blocks loopback (no allow_hosts)", blocked,
                    f"status={e.status} msg={e.message}") and ok
    except Exception as e:
        ok = _check("production convert_url blocks loopback (no allow_hosts)", False,
                    f"{type(e).__name__}: {e}") and ok

    # 3) no env var / settings hook can enable allow_hosts anywhere in src/
    import subprocess
    hits = subprocess.run(
        ["grep", "-rnE", "ALLOW_HOSTS|allow_hosts", "src"],
        cwd=str(ROOT), capture_output=True, text=True,
    ).stdout.splitlines()
    # allow only the url_fetch_service.py constructor (test escape hatch)
    leaks = [h for h in hits if "url_fetch_service.py" not in h and "__pycache__" not in h]
    ok = _check("no env/settings hook enables allow_hosts in production code",
                len(leaks) == 0, str(leaks)) and ok
    return ok


def main():
    import tempfile
    tmp = Path(tempfile.mkdtemp(prefix="tls_stage2_"))
    print("\n=== Stage 2 TLS Acceptance ===")
    results = [
        test_valid_cert(tmp),
        test_hostname_mismatch(tmp),
        test_untrusted_cert(tmp),
        test_dns_pinning(tmp),
        test_allow_hosts_test_only(),
    ]
    print(f"\nTLS CHECKS PASSED={_PASSED} FAILED={_FAILED}")
    all_ok = all(results) and _FAILED == 0
    print("TLS_ALL_PASS" if all_ok else "TLS_NOT_ALL_PASS")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
