"""Safe remote-URL fetch service for MdDesk (Stage 2).

This module owns ALL network access for remote URLs. It replaces the
unsafe built-in ``MarkItDown.convert_uri()`` entirely (we never call it).

Security posture (mandated by MdDesk-v0.2-Plan.md Stage 2 / Security Model):
  * scheme whitelist: only http/https (file:/data:/ftp:/... are refused)
  * DNS resolution -> per-IP validation (loopback 127/8, ::1, RFC1918,
    link-local, metadata 169.254.169.254, IPv6 ULA/site-local, multicast,
    reserved, unspecified, non-global are all refused)
  * DNS-rebinding mitigation: the hostname is resolved ONCE, every resolved
    IP is validated, and the connection is PINNED to one validated IP
    (http.client connects to the literal IP; the real hostname is sent only
    as the SNI/Host header). No second DNS lookup occurs at connect time, so
    a rebind cannot redirect us to an unvalidated address.
  * manual redirect handling: every hop is re-resolved and re-validated
  * redirect-count cap
  * connect timeout + read timeout
  * max download size, enforced while streaming (Content-Length pre-check +
    chunked read cap); gzip transparently decompressed
  * friendly, user-facing error categories (no raw tracebacks to users)

The service returns a ``FetchResult`` carrying a ``BytesIO`` plus a
correctly-built ``StreamInfo`` (url / filename / extension / mimetype /
charset), which the caller hands to ``MarkItDown().convert_stream(...)``.

Pure standard library only (socket / ssl / http.client / ipaddress / gzip /
urllib.parse) -> no new third-party dependency.
"""

from __future__ import annotations

import enum
import gzip
import http.client
import io
import ipaddress
import os
import re
import socket
import ssl
import urllib.parse
from dataclasses import dataclass

from markitdown import StreamInfo

from .version import user_agent


# ---- tunables ---------------------------------------------------------------
DEFAULT_MAX_REDIRECTS = 5
DEFAULT_CONNECT_TIMEOUT = 10.0   # seconds
DEFAULT_READ_TIMEOUT = 30.0      # seconds
DEFAULT_MAX_SIZE = 50 * 1024 * 1024  # 50 MiB
# Derived from the single version source (src/version.py) so the User-Agent
# can never drift to a stale version string again.
DEFAULT_USER_AGENT = user_agent()


class FetchErrorCategory(str, enum.Enum):
    """Why a fetch failed, mapped to a friendly user message."""

    SCHEME = "SCHEME"       # unsupported / missing scheme
    BLOCKED = "BLOCKED"     # SSRF / target not allowed
    TIMEOUT = "TIMEOUT"     # connect or read timeout
    TOO_LARGE = "TOO_LARGE" # exceeded max download size
    REDIRECT = "REDIRECT"   # redirect loop / cap exceeded / missing Location
    SSL_ERROR = "SSL_ERROR" # TLS certificate / hostname verification failure
    NETWORK = "NETWORK"     # DNS / connection / HTTP protocol error


class FetchError(Exception):
    """Raised on any fetch failure. Carries a ``category`` and ``message``."""

    def __init__(self, category: FetchErrorCategory, message: str) -> None:
        super().__init__(message)
        self.category = category
        self.message = message


@dataclass
class FetchResult:
    """Outcome of a successful fetch, ready to feed ``convert_stream``."""

    content: io.BytesIO
    stream_info: StreamInfo
    final_url: str
    status_code: int


# ---- IP / target validation -------------------------------------------------
def is_safe_ip(ip_str: str) -> bool:
    """Return True only for a globally-routable, safe unicast IP.

    Refuses loopback, link-local (incl. 169.254.169.254 metadata), private
    (RFC1918 + CGNAT 100.64/10), reserved, multicast, unspecified, and IPv6
    ULA/site-local. The authoritative gate is ``ip.is_global``; the extra
    explicit denials are defense-in-depth and aid auditing.
    """
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return False
    if not ip.is_global:
        return False
    if (
        ip.is_loopback
        or ip.is_link_local
        or ip.is_private
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
        or (ip.version == 6 and ip.is_site_local)
    ):
        return False
    return True


class TargetValidator:
    """Validates whether a resolved target may be contacted.

    Subclass / inject for testing. The production default is
    ``StrictTargetValidator`` with an empty allow-list.
    """

    def check(self, hostname: str, resolved_ips: list[str]) -> None:
        """Raise ``FetchError(BLOCKED)`` if the target must not be contacted."""
        raise NotImplementedError


class StrictTargetValidator(TargetValidator):
    """Refuses any non-global target. Allows an explicit test allow-list.

    ``allow_hosts`` is an escape hatch for local mock-server testing only;
    in production it is left empty, so loopback/private are always blocked.
    """

    def __init__(self, allow_hosts: tuple[str, ...] = ()) -> None:
        self._allow = {h.lower().rstrip(".") for h in allow_hosts}

    def check(self, hostname: str, resolved_ips: list[str]) -> None:
        host = hostname.lower()
        if host in self._allow:
            return  # explicitly permitted (testing / internal allow-list only)
        if host == "localhost" or host == "::1" or host.endswith(".localhost"):
            raise FetchError(FetchErrorCategory.BLOCKED, "禁止访问本地主机（SSRF 防护）")
        if not resolved_ips:
            raise FetchError(FetchErrorCategory.BLOCKED, "无法解析目标主机")
        for ip in resolved_ips:
            if not is_safe_ip(ip):
                raise FetchError(
                    FetchErrorCategory.BLOCKED,
                    f"目标地址 {ip} 不在允许的公开地址范围内（SSRF 防护）",
                )


# ---- pinned TLS connection -------------------------------------------------
class _PinnedTLSHTTPConnection(http.client.HTTPConnection):
    """HTTPConnection that pins the socket to a pre-resolved IP and performs
    the TLS handshake with the ORIGINAL hostname as SNI / verification name.

    Why not ``http.client.HTTPSConnection(server_hostname=...)``? That kwarg is
    not accepted on the installed CPython (3.13), and passing the IP as the
    host would make SNI = IP and break certificate hostname verification. By
    overriding ``connect()`` we keep two guarantees simultaneously:

      * anti-DNS-rebinding: ``socket.create_connection`` is called with the
        literal validated IP, so no second lookup can redirect us;
      * certificate verification intact: ``ssl.wrap_socket(server_hostname=
        real_hostname)`` validates the cert against the original hostname.
    """

    def __init__(
        self,
        ip: str,
        port: int,
        *,
        hostname: str,
        context: ssl.SSLContext | None,
        timeout: float,
    ) -> None:
        super().__init__(ip, port, timeout=timeout)
        self._pin_hostname = hostname
        self._pin_context = context

    def connect(self) -> None:
        sock = socket.create_connection((self.host, self.port), self.timeout)
        if self._pin_context is not None:
            sock = self._pin_context.wrap_socket(sock, server_hostname=self._pin_hostname)
        self.sock = sock


# ---- the service ------------------------------------------------------------
class UrlFetchService:
    def __init__(
        self,
        validator: TargetValidator | None = None,
        *,
        max_redirects: int = DEFAULT_MAX_REDIRECTS,
        connect_timeout: float = DEFAULT_CONNECT_TIMEOUT,
        read_timeout: float = DEFAULT_READ_TIMEOUT,
        max_size: int = DEFAULT_MAX_SIZE,
        verify_ssl: bool = True,
        user_agent: str = DEFAULT_USER_AGENT,
    ) -> None:
        self.validator = validator or StrictTargetValidator()
        self.max_redirects = max_redirects
        self.connect_timeout = connect_timeout
        self.read_timeout = read_timeout
        self.max_size = max_size
        self.verify_ssl = verify_ssl
        self.user_agent = user_agent

    # -- public API --
    def fetch(self, url: str) -> FetchResult:
        """Fetch ``url`` safely and return a ``FetchResult``.

        Raises ``FetchError`` (with a category) on any refusal / failure.
        """
        target = (url or "").strip()
        if not target:
            raise FetchError(FetchErrorCategory.SCHEME, "链接为空")
        parsed = urllib.parse.urlparse(target)
        if parsed.scheme not in ("http", "https"):
            raise FetchError(
                FetchErrorCategory.SCHEME,
                f"仅支持 http/https 链接（收到 {parsed.scheme or '无协议'}）",
            )
        if not parsed.hostname:
            raise FetchError(FetchErrorCategory.SCHEME, "链接缺少主机名")

        current = target
        redirect_count = 0
        while True:
            resp, final_url = self._request(current)
            status = resp.status
            if 300 <= status < 400:
                if redirect_count >= self.max_redirects:
                    # drain and close before raising
                    self._drain(resp)
                    raise FetchError(
                        FetchErrorCategory.REDIRECT,
                        f"重定向次数超过上限（{self.max_redirects}）",
                    )
                loc = resp.getheader("Location")
                if not loc:
                    self._drain(resp)
                    raise FetchError(FetchErrorCategory.REDIRECT, "重定向响应缺少 Location 头")
                redirect_count += 1
                current = urllib.parse.urljoin(current, loc)
                self._drain(resp)
                continue
            if status >= 400:
                self._drain(resp)
                raise FetchError(FetchErrorCategory.NETWORK, f"服务器返回 HTTP {status}")
            # 2xx -> read body
            return self._read_body(resp, final_url)

    # -- internals --
    def _resolve(self, hostname: str) -> list[str]:
        """Resolve ``hostname`` to a de-duplicated list of IP strings."""
        try:
            infos = socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)
        except socket.gaierror as exc:
            raise FetchError(
                FetchErrorCategory.NETWORK, f"无法解析主机名 {hostname}: {exc}"
            ) from exc
        ips: list[str] = []
        for info in infos:
            addr = info[4][0]
            if "%" in addr:  # strip IPv6 zone id
                addr = addr.split("%", 1)[0]
            if addr not in ips:
                ips.append(addr)
        if not ips:
            raise FetchError(FetchErrorCategory.NETWORK, f"主机名 {hostname} 无可用的 IP 地址")
        return ips

    def _request(self, url: str) -> tuple[http.client.HTTPResponse, str]:
        """Resolve + validate + pin-connect to one URL; return (response, url)."""
        parsed = urllib.parse.urlparse(url)
        hostname = parsed.hostname
        assert hostname is not None
        is_https = parsed.scheme == "https"
        port = parsed.port or (443 if is_https else 80)
        path = parsed.path or "/"
        if parsed.query:
            path = f"{path}?{parsed.query}"

        ips = self._resolve(hostname)
        # Validate every resolved IP, then PIN the connection to one of them.
        self.validator.check(hostname, ips)
        ip = ips[0]

        resp = self._connect(ip, port, is_https, hostname, path)
        return resp, url

    def _connect(
        self,
        ip: str,
        port: int,
        is_https: bool,
        hostname: str,
        path: str,
    ) -> http.client.HTTPResponse:
        default_port = (is_https and port == 443) or (not is_https and port == 80)
        host_header = hostname if default_port else f"{hostname}:{port}"
        try:
            if is_https:
                ctx = (
                    ssl.create_default_context()
                    if self.verify_ssl
                    else ssl._create_unverified_context()
                )
                conn = _PinnedTLSHTTPConnection(
                    ip, port, hostname=hostname, context=ctx,
                    timeout=self.connect_timeout,
                )
            else:
                conn = http.client.HTTPConnection(ip, port, timeout=self.connect_timeout)
            # Connect to the pinned IP (no second DNS lookup -> anti-rebind).
            conn.connect()
            # Apply the (separate) read timeout after the connect completes.
            if conn.sock is not None:
                conn.sock.settimeout(self.read_timeout)
            # Send the request ourselves so the Host header carries the real
            # hostname (not the pinned IP) for virtual hosting.
            conn.putrequest("GET", path, skip_host=True)
            conn.putheader("Host", host_header)
            conn.putheader("User-Agent", self.user_agent)
            conn.putheader("Accept", "*/*")
            conn.putheader("Connection", "close")
            conn.endheaders()
            return conn.getresponse()
        except ssl.SSLError as exc:
            raise FetchError(FetchErrorCategory.SSL_ERROR, f"TLS 证书错误: {exc}") from exc
        except socket.timeout:
            raise FetchError(FetchErrorCategory.TIMEOUT, "连接或读取超时")
        except (socket.error, OSError) as exc:
            raise FetchError(FetchErrorCategory.NETWORK, f"网络连接失败: {exc}") from exc
        except http.client.HTTPException as exc:
            raise FetchError(FetchErrorCategory.NETWORK, f"HTTP 协议错误: {exc}") from exc

    @staticmethod
    def _drain(resp: http.client.HTTPResponse) -> None:
        try:
            while resp.read(65536):
                pass
        except Exception:
            pass

    def _read_body(self, resp: http.client.HTTPResponse, final_url: str) -> FetchResult:
        # Pre-check Content-Length to reject oversize responses early.
        cl = resp.getheader("Content-Length")
        if cl and cl.isdigit() and int(cl) > self.max_size:
            self._drain(resp)
            raise FetchError(
                FetchErrorCategory.TOO_LARGE,
                f"响应体积 {int(cl)} 字节超过上限 {self.max_size} 字节",
            )
        buf = bytearray()
        try:
            while True:
                chunk = resp.read(65536)
                if not chunk:
                    break
                buf.extend(chunk)
                if len(buf) > self.max_size:
                    raise FetchError(
                        FetchErrorCategory.TOO_LARGE,
                        f"响应体积超过上限 {self.max_size} 字节",
                    )
        except socket.timeout:
            raise FetchError(FetchErrorCategory.TIMEOUT, "读取响应超时")
        except (socket.error, OSError) as exc:
            raise FetchError(FetchErrorCategory.NETWORK, f"读取响应失败: {exc}") from exc
        finally:
            try:
                resp.close()
            except Exception:
                pass

        body = bytes(buf)
        enc = (resp.getheader("Content-Encoding") or "").lower()
        if "gzip" in enc:
            try:
                body = gzip.decompress(body)
            except OSError:
                pass  # leave as-is; the converter may still handle it

        stream_info = self._build_stream_info(resp, final_url)
        return FetchResult(
            content=io.BytesIO(body),
            stream_info=stream_info,
            final_url=final_url,
            status_code=resp.status,
        )

    @staticmethod
    def _build_stream_info(resp: http.client.HTTPResponse, final_url: str) -> StreamInfo:
        ctype = resp.getheader("Content-Type", "")
        mimetype: str | None = None
        charset: str | None = None
        if ctype:
            parts = [p.strip() for p in ctype.split(";")]
            if parts:
                mimetype = parts[0] or None
            for p in parts[1:]:
                if p.lower().startswith("charset="):
                    charset = p.split("=", 1)[1].strip().strip('"') or None

        filename: str | None = None
        extension: str | None = None

        cd = resp.getheader("Content-Disposition", "")
        m = re.search(r"filename\*?=(?:UTF-8'')?([^;]+)", cd, re.IGNORECASE)
        if m:
            filename = m.group(1).strip().strip('"').strip("'")
        if filename:
            _, ext = os.path.splitext(filename)
            if ext:
                extension = ext

        if not filename:
            p = urllib.parse.urlparse(final_url).path
            if p and p.rstrip("/"):
                filename = os.path.basename(p.rstrip("/"))
                _, ext = os.path.splitext(filename)
                if ext:
                    extension = ext

        return StreamInfo(
            mimetype=mimetype,
            charset=charset,
            filename=filename,
            extension=extension,
            url=final_url,
        )
