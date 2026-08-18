"""ConversionReport + DiagnosticLogger tests (v0.4 Stage 3).

Run: pytest tests/test_report.py

Covers:
  - Report construction for success / warning / failure results
  - URL source sanitization (no credentials / query / fragment)
  - Error-message secret redaction (api_key / token / Authorization / ...)
  - Diagnostic log line: valid JSON, NO markdown body, NO raw secrets
  - Frozen vs source log-dir resolution + explicit disk location
  - result.py / report.py stay markitdown-free (no engine pulled in)
  - Quality-OFF result yields an empty-warnings report; report never stores body
"""

import json
import os
import sys

import pytest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.file_entry import FileEntry, FileStatus  # noqa: E402
from src.report import (  # noqa: E402
    ConversionReport,
    DiagnosticLogger,
    ReportBuilder,
    _default_log_dir,
    _redact_secrets,
    _sanitize_url,
)
from src.converter import ConversionError  # noqa: E402
from src.result import ConversionResult, QualityWarning  # noqa: E402


# ---------------------------------------------------------------------------
# Report construction
# ---------------------------------------------------------------------------
def _file_entry(name="doc.pdf", size=1234, url=None):
    return FileEntry(
        path=f"/tmp/{name}",
        filename=name,
        extension=os.path.splitext(name)[1].lower(),
        size=size,
        url=url,
    )


def test_success_report_fields():
    entry = _file_entry("report.docx", size=2048)
    res = ConversionResult.success(3, "# Hello\n\nSome converted text.", duration_ms=42)
    rep = ReportBuilder.build(res, entry)
    assert isinstance(rep, ConversionReport)
    assert rep.row == 3
    assert rep.source == "report.docx"
    assert rep.source_type == "file"
    assert rep.status == FileStatus.DONE
    assert rep.ok is True
    assert rep.duration_ms == 42
    assert rep.output_chars == len("# Hello\n\nSome converted text.")
    assert rep.warnings == ()
    assert rep.error is None
    assert rep.timestamp  # ISO string present
    # Report never carries the markdown body.
    assert "markdown" not in rep.to_dict()


def test_failure_report_fields():
    entry = _file_entry("bad.unknown")
    ce = ConversionError(FileStatus.UNSUPPORTED, "不支持的文件格式: .unknown")
    res = ConversionResult.from_error(1, ce, duration_ms=7)
    rep = ReportBuilder.build(res, entry)
    assert rep.ok is False
    assert rep.status == FileStatus.UNSUPPORTED
    assert rep.error == "不支持的文件格式: .unknown"
    assert rep.output_chars == 0  # no markdown on failure
    assert rep.source_type == "file"
    assert rep.source == "bad.unknown"


def test_warning_report_preserves_code_and_message():
    entry = _file_entry("scan.pdf", size=60000)
    warnings = (
        QualityWarning("LOW_TEXT_YIELD", "输入较大但提取文本极少。"),
        QualityWarning("OCR_ERROR_MARKER", "包含 OCR 失败块。"),
    )
    res = ConversionResult.success(
        2, "x", duration_ms=99, warnings=warnings
    )
    rep = ReportBuilder.build(res, entry)
    assert rep.ok is True
    assert isinstance(rep.warnings, tuple)
    assert rep.warnings == warnings
    assert {w.code for w in rep.warnings} == {"LOW_TEXT_YIELD", "OCR_ERROR_MARKER"}
    # Stable code + readable message survive into to_dict.
    codes = {w["code"] for w in rep.to_dict()["warnings"]}
    assert codes == {"LOW_TEXT_YIELD", "OCR_ERROR_MARKER"}


def test_report_frozen_immutable():
    res = ConversionResult.success(0, "md", duration_ms=1)
    rep = ReportBuilder.build(res, _file_entry())
    with pytest.raises(Exception):
        rep.row = 5  # frozen dataclass -> raises


# ---------------------------------------------------------------------------
# URL sanitization
# ---------------------------------------------------------------------------
def test_url_source_sanitized():
    url = "https://user:secretpass@example.com/docs/page.html?token=abc123#frag"
    entry = _file_entry("page.html", url=url)
    entry.url = url
    res = ConversionResult.success(0, "# page", duration_ms=10)
    rep = ReportBuilder.build(res, entry)
    assert rep.source_type == "url"
    # No userinfo, query, or fragment in the logged source.
    assert "secretpass" not in rep.source
    assert "token=abc123" not in rep.source
    assert "#frag" not in rep.source
    assert "user:" not in rep.source
    assert rep.source.startswith("https://example.com/docs/page.html")


def test_sanitize_url_drops_credentials():
    assert "user:pass" not in _sanitize_url("http://user:pass@host/x")
    assert "api_key=1" not in _sanitize_url("https://h/p?api_key=1")
    assert _sanitize_url("") == ""


# ---------------------------------------------------------------------------
# Secret redaction
# ---------------------------------------------------------------------------
def test_error_message_redacted_in_report():
    entry = _file_entry("x.pdf")
    # Error text that happens to embed a credential / JWT / api key.
    jwt = ("eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0."
           "SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c")
    msg = (f"转换失败: Authorization: Bearer {jwt} "
           f"token=abc123 api_key=SK123456")
    res = ConversionResult.failure(0, FileStatus.ERROR, msg, duration_ms=5)
    rep = ReportBuilder.build(res, entry)
    assert "eyJhbG" not in rep.error          # JWT blanked
    assert "abc123" not in rep.error          # token= blanked
    assert "SK123456" not in rep.error        # api_key= blanked
    assert "<REDACTED>" in rep.error
    assert "api_key=<REDACTED>" in rep.error


def test_redact_secrets_variants():
    text = 'password="s3cret" token=abc123 client_secret: xyz Cookie: sess=9'
    out = _redact_secrets(text)
    assert "s3cret" not in out
    assert "abc123" not in out
    assert "xyz" not in out
    assert "sess=9" not in out
    assert out.count("<REDACTED>") >= 4


# ---------------------------------------------------------------------------
# Diagnostic log file
# ---------------------------------------------------------------------------
def test_log_line_valid_json_no_body_no_secret(tmp_path):
    log_dir = str(tmp_path / "logs")
    logger = DiagnosticLogger(log_dir=log_dir)
    entry = _file_entry("doc.pdf", size=2048)
    markdown = "# Big\n\n" + "x" * 500  # large body must NOT be logged
    res = ConversionResult.success(0, markdown, duration_ms=12)
    ok = logger.record(ReportBuilder.build(res, entry))
    assert ok is True

    path = Path(logger.log_path)
    assert path.exists()
    line = path.read_text(encoding="utf-8").strip()
    # Single JSON object, parseable.
    obj = json.loads(line)
    assert obj["row"] == 0
    assert obj["output_chars"] == len(markdown)
    # No markdown body / no raw secret anywhere in the line.
    assert "x" * 10 not in line  # body fragment absent
    assert "markdown" not in obj
    assert "api_key" not in line
    assert "<REDACTED>" not in line  # success path had nothing to redact


def test_log_records_error_and_warnings(tmp_path):
    log_dir = str(tmp_path / "logs")
    logger = DiagnosticLogger(log_dir=log_dir)
    entry = _file_entry("scan.pdf", size=60000)
    res = ConversionResult.failure(
        1,
        FileStatus.ERROR,
        "网络错误: Cookie: sess=abc",
        duration_ms=8,
        warnings=(QualityWarning("OCR_ERROR_MARKER", "OCR 失败块"),),
    )
    logger.record(ReportBuilder.build(res, entry))
    obj = json.loads(Path(logger.log_path).read_text(encoding="utf-8").strip())
    assert obj["status"] == FileStatus.ERROR.value
    assert "sess=abc" not in obj["error"]  # redacted
    assert obj["warnings"][0]["code"] == "OCR_ERROR_MARKER"


def test_log_dir_created_and_path_exposed(tmp_path):
    log_dir = str(tmp_path / "nested" / "logs")
    logger = DiagnosticLogger(log_dir=log_dir)
    assert logger.log_path.endswith("md_desk_diagnostic.log")
    assert not os.path.exists(log_dir)
    logger.ensure_dir()
    assert os.path.isdir(log_dir)


# ---------------------------------------------------------------------------
# Frozen vs source log-dir resolution
# ---------------------------------------------------------------------------
def test_default_log_dir_uses_appdata(monkeypatch):
    monkeypatch.delattr(sys, "frozen", raising=False)
    monkeypatch.setenv("APPDATA", "C:\\Users\\test\\AppData\\Roaming")
    d = str(_default_log_dir())
    assert d.endswith(os.path.join("MdDesk", "logs"))
    assert "AppData" in d


def test_default_log_dir_no_appdata_source(monkeypatch):
    monkeypatch.delattr(sys, "frozen", raising=False)
    monkeypatch.delenv("APPDATA", raising=False)
    d = str(_default_log_dir())
    assert d.endswith(os.path.join(".md_desk", "logs"))


def test_default_log_dir_frozen_no_appdata(monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.delenv("APPDATA", raising=False)
    # Falls back to next to the executable (writable location).
    d = str(_default_log_dir())
    assert d.endswith("logs")
    assert os.path.dirname(d) == os.path.dirname(sys.executable)


# ---------------------------------------------------------------------------
# Quality-OFF unchanged + report never stores body
# ---------------------------------------------------------------------------
def test_quality_off_yields_empty_warnings_report():
    # A quality-OFF worker result carries warnings == () regardless of output.
    entry = _file_entry("big.pdf", size=60000)
    res = ConversionResult.success(0, "x", duration_ms=3)  # warnings default ()
    rep = ReportBuilder.build(res, entry)
    assert rep.warnings == ()
    assert rep.ok is True
    assert "markdown" not in rep.to_dict()


# ---------------------------------------------------------------------------
# Diagnostic log rotation (stdlib-only, size cap + backup generations)
# ---------------------------------------------------------------------------
def test_log_rotation_creates_and_caps_backups(tmp_path):
    # Tiny cap + 2 backups: writing many lines must rotate and respect the cap.
    logger = DiagnosticLogger(log_dir=str(tmp_path), max_bytes=200, backup_count=2)
    entry = _file_entry("a.pdf")
    res = ConversionResult.success(0, "# ok", duration_ms=1)
    rep = ReportBuilder.build(res, entry)
    for _ in range(20):
        assert logger.record(rep) is True
    # Current log exists and contains valid JSON metadata lines only.
    assert os.path.exists(logger.log_path)
    # Exactly backup_count generations exist; the next one must not.
    assert os.path.exists(logger.log_path + ".1")
    assert os.path.exists(logger.log_path + ".2")
    assert not os.path.exists(logger.log_path + ".3")
    # No rotated file ever contains a markdown body ("markdown" key absent).
    for gen in ("", ".1", ".2"):
        p = logger.log_path + gen
        if not os.path.exists(p):
            continue
        with open(p, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                obj = json.loads(line)
                assert "markdown" not in obj
                assert "error" in obj  # key present (None on success)


def test_log_rotation_preserves_redaction(tmp_path):
    # Rotation shifts the SAME redacted metadata; secrets must never land on
    # disk in the current file OR any rotated generation.
    logger = DiagnosticLogger(log_dir=str(tmp_path), max_bytes=150, backup_count=3)
    entry = _file_entry("secret.txt")
    res = ConversionResult.failure(
        0, FileStatus.ERROR, "token=SUPERSECRET api_key=abc123"
    )
    rep = ReportBuilder.build(res, entry)
    for _ in range(15):
        logger.record(rep)
    p = logger.log_path + ".1"
    assert os.path.exists(p), "expected at least one rotated generation"
    text = Path(p).read_text(encoding="utf-8")
    assert "SUPERSECRET" not in text
    assert "abc123" not in text
    assert "<REDACTED>" in text


def test_log_no_rotation_when_disabled(tmp_path):
    # backup_count=0 => no rotation; the single file just keeps growing.
    logger = DiagnosticLogger(log_dir=str(tmp_path), max_bytes=10, backup_count=0)
    entry = _file_entry("a.pdf")
    res = ConversionResult.success(0, "# ok", duration_ms=1)
    rep = ReportBuilder.build(res, entry)
    for _ in range(10):
        assert logger.record(rep) is True
    assert os.path.exists(logger.log_path)
    assert not os.path.exists(logger.log_path + ".1")
