"""Conversion reporting & diagnostic logging (v0.4 Stage 3).

A small, **Qt-free, MarkItDown-free** data layer that turns a single
``ConversionResult`` (plus the ``FileEntry`` it came from) into a stable,
immutable ``ConversionReport`` for the future Stage 4 UI, and writes a
lightweight diagnostic log line.

Why this module lives OUTSIDE the worker
----------------------------------------
  * The worker owns *conversion only*. Building a report and writing a
    diagnostic log are a separate concern (Separation of Concerns), so this
    module is imported by the UI signal handler (``MainWindow._on_file_finished``)
    — never by ``src.worker``. The worker is therefore completely untouched by
    Stage 3 and its conversion logic is unchanged.
  * Staying free of Qt / converter / markitdown means it can be unit-tested in
    isolation (no display server, no heavy engine).

Import graph (must stay clean)
------------------------------
  ``result``  ->  ``file_entry`` (FileStatus)  ->  ``settings`` (StreamInfoOverride)
  None of those import markitdown, so importing this module does NOT pull
  markitdown in. We import ``QualityWarning`` from ``result`` (defined there,
  not in ``quality``) and the ``FileEntry``/``FileStatus`` vocabulary — never
  ``quality`` or ``converter``. ``result.py``'s ``QualityWarning`` is defined
  locally and only references ``file_entry.FileStatus``, so it is already
  decoupled from markitdown (verified: ``import src.result`` leaves markitdown
  out of ``sys.modules``).

What the report stores (diagnostic metadata ONLY)
-------------------------------------------------
  row, source (sanitized), source_type, status, duration_ms, output_chars,
  warnings (stable code + message), error (sanitized), timestamp.
  It deliberately does NOT contain the full Markdown body.

What the diagnostic log stores (one JSON line per conversion)
-------------------------------------------------------------
  ts, row, source, source_type, status, duration_ms, output_chars,
  warnings (code+message), error. No Markdown, no secrets.

Desensitization guarantees
---------------------------
  * The Markdown body is never written (period).
  * URLs are stripped of userinfo / query / fragment before being logged as
    ``source``.
  * ``error`` text and any field that could carry a credential are run through
    a secret-redaction pass that blanks api_key / token / secret / password /
    Authorization / Cookie / Bearer / client_secret / access_key values.
"""

from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass
from typing import Optional, Tuple
from urllib.parse import urlparse, urlunparse
from datetime import datetime, timezone

from .file_entry import FileEntry, FileStatus
from .result import ConversionResult, QualityWarning


# ---------------------------------------------------------------------------
# Secret / credential redaction
# ---------------------------------------------------------------------------
# Matches ``key=value`` / ``key: value`` for known secret-ish keys. The value
# is a non-space run (quotes optional). e.g. ``api_key=abc123``,
# ``password="s3cret"``, ``client_secret: xyz``.
_KV_RE = re.compile(
    r"(?i)\b("
    r"api[_-]?key|apikey|secret|token|password|passwd|"
    r"access[_-]?key|client[_-]?secret"
    r")\b(\s*[:=]\s*)\S+"
)

# Matches ``Authorization`` / ``Cookie`` / ``Bearer`` followed by its value
# (the value is the immediately following non-space token; quotes optional).
# e.g. ``Bearer eyJ...`` -> ``Bearer <REDACTED>``, ``Authorization: Basic abc==``
# -> ``Authorization <REDACTED>``, ``Cookie: sess=xyz`` -> ``Cookie <REDACTED>``.
_AUTH_RE = re.compile(
    r"(?i)\b(authorization|cookie|bearer)\b(\s*[:=]?\s*)(\S+)"
)

# JSON Web Token shape (header.payload.signature, base64url). A JWT IS the
# credential even when it appears without a "Bearer" prefix, so redact it
# wherever it shows up in a logged string.
_JWT_RE = re.compile(r"[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}")


def _redact_secrets(text: str) -> str:
    """Blank known credential patterns in ``text`` (defense-in-depth).

    Returns a copy with api_key / token / secret / password / Authorization /
    Cookie / Bearer / client_secret / access_key values and JWTs replaced by
    ``<REDACTED>``. Non-matching text is returned unchanged.

    Order matters: JWT-shaped tokens are redacted first (so a bare JWT is
    caught), then key=value forms, then the Authorization/Cookie/Bearer
    prefixes (which may wrap a JWT already blanked to ``<REDACTED>``).
    """
    text = _JWT_RE.sub("<REDACTED>", text)
    text = _KV_RE.sub(lambda m: f"{m.group(1)}=<REDACTED>", text)
    text = _AUTH_RE.sub(lambda m: f"{m.group(1)} <REDACTED>", text)
    return text


def _sanitize_url(url: str) -> str:
    """Return a safe, loggable display string for a source URL.

    Drops userinfo (user:pass@), query string, and fragment. Keeps only
    scheme + host + path (path truncated if extremely long). Falls back to a
    generously redacted, truncated raw string if the URL cannot be parsed.
    """
    if not url:
        return ""
    raw = url.strip()
    if not raw:
        return ""
    try:
        p = urlparse(raw)
        if not p.scheme:
            # Not a real URL (e.g. a bare hostname) — just redact + truncate.
            return _redact_secrets(raw)[:120]
        # Rebuild WITHOUT credentials / query / fragment.
        host = p.hostname or p.netloc.split("@")[-1].split(":")[0]
        clean = urlunparse((p.scheme, host, p.path, "", "", ""))
    except Exception:  # noqa: BLE001 - never let sanitization crash logging
        clean = _redact_secrets(raw)
    if len(clean) > 200:
        clean = clean[:197] + "..."
    return clean


def _sanitize_text(text: Optional[str]) -> Optional[str]:
    """Sanitize a free-text field (e.g. an error message) for logging."""
    if not text:
        return text
    return _redact_secrets(text)


def _utc_now() -> str:
    """Current time as a stable, sortable ISO-8601 UTC string."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# Immutable report value object
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class ConversionReport:
    """Immutable diagnostic snapshot of ONE conversion (success or failure).

    Built from a ``ConversionResult`` + the originating ``FileEntry``. It is
    the stable data contract the future Stage 4 UI will consume. It carries
    diagnostic metadata ONLY — never the full Markdown body.
    """

    row: int
    source: str                 # sanitized display string (filename or URL)
    source_type: str            # "file" | "url" | "unknown"
    status: FileStatus
    duration_ms: int
    output_chars: int
    warnings: Tuple[QualityWarning, ...]
    error: Optional[str]        # sanitized error message (None on success)
    timestamp: str              # ISO-8601 UTC

    @property
    def ok(self) -> bool:
        """True when the conversion succeeded (status == DONE)."""
        return self.status == FileStatus.DONE

    def to_dict(self) -> dict:
        """Structured, JSON-serializable form (used by the logger)."""
        return {
            "ts": self.timestamp,
            "row": self.row,
            "source": self.source,
            "source_type": self.source_type,
            "status": self.status.value,
            "duration_ms": self.duration_ms,
            "output_chars": self.output_chars,
            "warnings": [
                {"code": w.code, "message": w.message} for w in self.warnings
            ],
            "error": self.error,
        }


# ---------------------------------------------------------------------------
# Report builder
# ---------------------------------------------------------------------------
class ReportBuilder:
    """Pure builder: ``ConversionResult`` + ``FileEntry`` -> ``ConversionReport``.

    No I/O, no logging side-effect. Keeping build and log separate makes both
    independently testable and keeps the worker free of reporting concerns.
    """

    @staticmethod
    def build(
        result: ConversionResult,
        entry: Optional[FileEntry] = None,
        *,
        now: Optional[str] = None,
    ) -> ConversionReport:
        """Construct a ``ConversionReport`` from a result and its source entry.

        ``entry`` is optional (a report can still be built from the result
        alone — source falls back to the row index). ``now`` lets tests pin the
        timestamp; when omitted the current UTC time is used.
        """
        if entry is not None and getattr(entry, "is_url", False):
            source_type = "url"
            source = _sanitize_url(getattr(entry, "url", None) or entry.filename)
        elif entry is not None:
            source_type = "file"
            source = entry.filename or entry.path
        else:
            source_type = "unknown"
            source = f"row:{result.row}"

        output_chars = len(result.markdown or "")
        return ConversionReport(
            row=result.row,
            source=source,
            source_type=source_type,
            status=result.status,
            duration_ms=result.duration_ms,
            output_chars=output_chars,
            warnings=tuple(result.warnings or ()),
            error=_sanitize_text(result.error_message),
            timestamp=now or _utc_now(),
        )


# ---------------------------------------------------------------------------
# Diagnostic logger
# ---------------------------------------------------------------------------
def _default_log_dir() -> "os.PathLike":
    """Resolve the diagnostic log directory for the current runtime.

    The location is explicit and adapts to how the app is running:

      * Frozen EXE (``sys.frozen``) OR normal dev with ``%APPDATA%`` present
        (Windows, the target platform): ``%APPDATA%/MdDesk/logs``.
        -> User-writable, survives EXE updates, never under the (possibly
           read-only) Program Files install tree.
      * Source/dev without ``%APPDATA`` (e.g. some CI / Linux):
        ``~/.md_desk/logs`` (mirrors ``Settings.default_path`` convention).

    The actual on-disk path is exposed via :attr:`DiagnosticLogger.log_path`
    so the Stage 4 UI can show it to the user.
    """
    appdata = os.environ.get("APPDATA")
    if appdata:
        return os.path.join(appdata, "MdDesk", "logs")
    if getattr(sys, "frozen", False):
        # Frozen but no APPDATA (unusual on Windows) — fall back next to the
        # launcher, where the user normally has write access.
        base = os.path.dirname(sys.executable)
    else:
        base = os.path.join(os.path.expanduser("~"), ".md_desk")
    return os.path.join(base, "logs")


class DiagnosticLogger:
    """Appends one JSON diagnostic line per conversion to a log file.

    It records ONLY the diagnostic metadata from a ``ConversionReport`` — never
    the Markdown body, never credentials. All failures are swallowed (logging
    must NEVER break or slow down conversion).

    Rotation (stdlib-only): when the log would exceed ``max_bytes`` it is
    rotated to ``<name>.1``, ``<name>.2``, ... up to ``backup_count`` old
    generations (oldest dropped). Rotation never writes the Markdown body or
    any secret — only the existing metadata lines are shifted around.
    """

    def __init__(
        self,
        log_dir: Optional[str] = None,
        max_bytes: int = 1_000_000,
        backup_count: int = 5,
    ) -> None:
        self._log_dir = log_dir or _default_log_dir()
        self._log_path = os.path.join(self._log_dir, "md_desk_diagnostic.log")
        # Guard against degenerate config values from callers.
        self._max_bytes = max(1024, int(max_bytes))
        self._backup_count = max(0, int(backup_count))

    @property
    def log_path(self) -> str:
        """Absolute path of the diagnostic log file (for UI display / tests)."""
        return self._log_path

    @property
    def max_bytes(self) -> int:
        """Soft size cap before rotation (bytes)."""
        return self._max_bytes

    @property
    def backup_count(self) -> int:
        """Number of rotated generations kept."""
        return self._backup_count

    def ensure_dir(self) -> None:
        """Create the log directory if missing. Best-effort."""
        os.makedirs(self._log_dir, exist_ok=True)

    def _rotate_if_needed(self, incoming: int) -> None:
        """Rotate the log file if writing ``incoming`` bytes would exceed cap.

        No-op when rotation is disabled (``backup_count == 0``) or the file does
        not yet exist. Any error here is swallowed — rotation must never break
        logging; the append below will simply keep growing the current file.
        """
        if self._backup_count <= 0:
            return
        try:
            if not os.path.exists(self._log_path):
                return
            if os.path.getsize(self._log_path) + incoming <= self._max_bytes:
                return
            # Shift older generations up by one (.{n} -> .{n+1}), then make the
            # current file generation 1. The highest generation kept is
            # .{backup_count}; anything beyond is overwritten/discarded, so the
            # total number of old files never exceeds backup_count.
            for gen in range(self._backup_count - 1, 0, -1):
                src = f"{self._log_path}.{gen}"
                dst = f"{self._log_path}.{gen + 1}"
                if os.path.exists(src):
                    os.replace(src, dst)
            os.replace(self._log_path, f"{self._log_path}.1")
        except Exception:  # noqa: BLE001 - rotation is best-effort
            pass

    def record(self, report: ConversionReport) -> bool:
        """Append one JSON line for ``report``.

        Returns ``True`` on success, ``False`` on any I/O or serialization
        failure. Designed to be called inside a ``try/except`` from the UI so a
        logging problem can never affect conversion.
        """
        try:
            self.ensure_dir()
            # Compact, single-line, UTF-8 JSON. ensure_ascii keeps the file
            # ASCII-safe and avoids any encoding surprises across locales.
            line = json.dumps(report.to_dict(), ensure_ascii=True, separators=(",", ":"))
            self._rotate_if_needed(len(line) + 1)
            with open(self._log_path, "a", encoding="utf-8") as fh:
                fh.write(line + "\n")
            return True
        except Exception:  # noqa: BLE001 - logging must never raise
            return False
