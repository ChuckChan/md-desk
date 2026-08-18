"""Frozen-EXE runtime smoke for v0.4 Stage 1 (unified ConversionResult).

Built with the SAME collection flags as md-desk.exe (notably
``--collect-submodules markitdown_ocr`` and ``--hidden-import openai``), so it
exercises the identical bundled module set. It proves, INSIDE the frozen
binary (no venv), that the Stage 1 pipeline actually works end-to-end:

  1. ``src.result`` and ``src.worker`` are collected (importable) in the
     frozen build.
  2. A normal HTML file converts through ``ConversionWorker`` and its
     unified ``file_finished(ConversionResult)`` signal, not the old
     ``file_done``/``file_failed`` pair.
  3. The emitted ``ConversionResult`` carries ``status == DONE``, non-empty
     Markdown, an immutable ``warnings`` tuple, and ``duration_ms >= 0``
     computed from ``perf_counter``.
  4. The default (AI-OFF) engine path is exercised, preserving v0.2 behavior.

The script is headless (offscreen QApplication, no real window) and exits
explicitly with 0 on success, mirroring the repo's established frozen-smoke
pattern (see tests/exe_v03_smoke.py). stdout is forced to UTF-8; all printed
diagnostics are ASCII.

Run: build the smoke EXE (same flags as md-desk) then execute it.
"""

import sys
import tempfile
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


def _check(label, ok, detail=""):
    print(("PASS" if ok else "FAIL"), "-", label, "" if ok else ":: " + detail)
    return ok


def main():
    ok = True

    # 1. collection: result + worker modules import inside the frozen binary
    ok &= _check("IMPORT_RESULT", ConversionResult is not None)
    ok &= _check("IMPORT_WORKER", ConversionWorker is not None)

    # 2. drive a real (AI-OFF) conversion through the unified worker signal
    tmp = Path(tempfile.mkdtemp(prefix="mddesk_s1_frozen_"))
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

    ok &= _check("S1_FILE_FINISHED_EMITTED", len(results) == 1, f"n={len(results)}")
    if not results:
        print()
        print("S1_FROZEN_FAIL")
        sys.exit(1)

    res = results[0]

    # 3a. row handle is the stable batch-start index
    ok &= _check("S1_ROW_STABLE", res.row == 0, f"row={res.row}")

    # 3b. success state
    ok &= _check("S1_STATUS_DONE", res.status == FileStatus.DONE, f"{res.status}")
    ok &= _check("S1_OK_TRUE", res.ok is True)

    # 3c. Markdown produced and non-empty (AI-OFF == v0.2 content)
    md = res.markdown or ""
    ok &= _check(
        "S1_MARKDOWN_NONEMPTY",
        len(md) > 0 and "# Title" in md,
        repr(md[:80]),
    )

    # 3d. no error message on success
    ok &= _check("S1_NO_ERROR_MSG", res.error_message is None)

    # 3e. warnings is an immutable tuple (Stage 1 -> empty)
    ok &= _check(
        "S1_WARNINGS_TUPLE",
        isinstance(res.warnings, tuple) and res.warnings == (),
        type(res.warnings).__name__,
    )

    # 3f. duration_ms is computed from perf_counter and non-negative
    ok &= _check("S1_DURATION_GE0", res.duration_ms >= 0, f"dur={res.duration_ms}")

    print()
    if ok:
        print("S1_FROZEN_PASS")
        sys.exit(0)
    else:
        print("S1_FROZEN_FAIL")
        sys.exit(1)


if __name__ == "__main__":
    main()
