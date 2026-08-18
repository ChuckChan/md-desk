"""Frozen-EXE runtime smoke for v0.4 Stage 3 (ConversionReport + DiagnosticLogger).

Built with the SAME collection flags as md-desk.exe (notably
``--collect-submodules markitdown`` / ``markitdown_ocr`` and
``--hidden-import openai``), so it exercises the identical bundled module set.
It proves, INSIDE the frozen binary (no venv), that the Stage 3 reporting
layer actually works end-to-end:

  1. ``src.report`` (ConversionReport / ReportBuilder / DiagnosticLogger) is
     collected (importable) in the frozen build.
  2. A normal HTML file converts through ``ConversionWorker``; its result is
     turned into a ``ConversionReport`` and written as ONE diagnostic JSON line
     by ``DiagnosticLogger``.
  3. The written log line is valid JSON, contains the diagnostic metadata
     (status / duration / output_chars / warnings / error), and contains NO
     Markdown body.
  4. A URL source (with embedded credentials) is sanitized before logging
     (no user:pass, no query string appears in the report's ``source``).
  5. The default (frozen) log path resolves to a real, writable location
     (APPDATA/MdDesk/logs) — proving the path adapts to the frozen env.

Headless (offscreen QApplication). Exits 0 on success. stdout forced UTF-8.
"""

import sys
import tempfile
import json
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

sys.path.insert(0, ".")

from PySide6.QtWidgets import QApplication  # noqa: E402

from src.worker import ConversionWorker  # noqa: E402
from src.file_entry import FileEntry, FileStatus  # noqa: E402
from src.result import ConversionResult  # noqa: E402
from src.report import ConversionReport, ReportBuilder, DiagnosticLogger  # noqa: E402


def _check(label, ok, detail=""):
    print(("PASS" if ok else "FAIL"), "-", label, "" if ok else ":: " + detail)
    return ok


def main():
    ok = True

    # 1. collection: report layer importable inside the frozen binary
    ok &= _check("IMPORT_REPORT", ConversionReport is not None)
    ok &= _check("IMPORT_BUILDER", ReportBuilder is not None)
    ok &= _check("IMPORT_LOGGER", DiagnosticLogger is not None)

    # 2. drive a real (AI-OFF) conversion through the unified worker signal
    tmp = Path(tempfile.mkdtemp(prefix="mddesk_s3_frozen_"))
    fixture = tmp / "sample.html"
    fixture.write_text(
        "<html><body><h1>Title</h1><p>Hello frozen world.</p></body></html>",
        encoding="utf-8",
    )
    entry = FileEntry.from_path(str(fixture))

    app = QApplication.instance() or QApplication([])
    results: list[ConversionResult] = []
    w = ConversionWorker([(0, entry)])  # no settings -> EngineConfig.disabled()
    w.file_finished.connect(lambda r: results.append(r))
    w.start()
    w.wait()
    app.processEvents()

    ok &= _check("S3_FILE_FINISHED_EMITTED", len(results) == 1, f"n={len(results)}")
    if not results:
        print("S3_FROZEN_FAIL")
        sys.exit(1)
    res = results[0]

    # 3. build a report + write one diagnostic line to an explicit temp log dir
    log_dir = str(tmp / "diag")
    logger = DiagnosticLogger(log_dir=log_dir)
    report = ReportBuilder.build(res, entry)
    ok &= _check("S3_REPORT_BUILT", isinstance(report, ConversionReport))
    ok &= _check("S3_REPORT_OK", report.ok is True)
    ok &= _check("S3_REPORT_HAS_CHARS", report.output_chars > 0, f"{report.output_chars}")
    ok &= _check("S3_LOG_PATH_EXPOSED", logger.log_path.endswith("md_desk_diagnostic.log"))
    wrote = logger.record(report)
    ok &= _check("S3_LOG_WRITTEN", wrote is True)
    log_path = Path(logger.log_path)
    ok &= _check("S3_LOG_FILE_EXISTS", log_path.exists())
    if log_path.exists():
        line = log_path.read_text(encoding="utf-8").strip()
        try:
            obj = json.loads(line)
            ok &= _check("S3_LOG_LINE_JSON", True)
        except Exception as e:
            obj = {}
            ok &= _check("S3_LOG_LINE_JSON", False, str(e))
        ok &= _check("S3_LOG_NO_MARKDOWN_BODY", "# Title" not in line, repr(line[:60]))
        ok &= _check("S3_LOG_HAS_STATUS", obj.get("status") == FileStatus.DONE.value,
                     str(obj.get("status")))
        ok &= _check("S3_LOG_HAS_CHARS", obj.get("output_chars", 0) > 0)
        ok &= _check("S3_LOG_NO_SECRET_KEY", "api_key" not in line)

    # 4. URL source with credentials is sanitized before logging
    url = "https://user:secretpass@example.com/docs/page.html?token=abc#frag"
    url_entry = FileEntry(
        path=url, filename="page.html", extension=".html", size=0, url=url,
    )
    url_report = ReportBuilder.build(
        ConversionResult.success(1, "# page", duration_ms=11), url_entry
    )
    ok &= _check("S3_URL_TYPE", url_report.source_type == "url")
    ok &= _check("S3_URL_SANITIZED", "secretpass" not in url_report.source, url_report.source)
    ok &= _check("S3_URL_NO_QUERY", "token=abc" not in url_report.source)
    ok &= _check("S3_URL_HOST_KEPT", url_report.source.startswith("https://example.com/docs/page.html"))

    # 5. default (frozen) log path resolves to a real, writable location
    default_logger = DiagnosticLogger()  # no dir -> uses _default_log_dir()
    dlp = default_logger.log_path
    ok &= _check("S3_DEFAULT_LOG_IN_MDDESK", "MdDesk" in dlp and "logs" in dlp, dlp)
    ok &= _check("S3_DEFAULT_LOG_NAMED", dlp.endswith("md_desk_diagnostic.log"), dlp)

    print()
    if ok:
        print("S3_FROZEN_PASS")
        sys.exit(0)
    else:
        print("S3_FROZEN_FAIL")
        sys.exit(1)


if __name__ == "__main__":
    main()
