"""Frozen-binary smoke for v0.4 Stage 4 diagnostics UI.

Headless (offscreen). Builds a MainWindow, drives synthetic terminal results
through the real ``_on_file_finished`` path, and asserts the DiagnosticsPanel
renders correctly in the frozen binary:
  * DONE + warning  -> "转换成功，但有质量提示" banner + warning text shown;
    the file-list status column shows "完成 (质量提示)" (never ERROR).
  * ERROR            -> failure banner + error text shown; report still viewable.
  * Report lifecycle -> the ConversionReport is attached to the entry.

This complements exe_s3_smoke.py (which does a real conversion + report/log
write). Together they prove the Stage 4 build config (with correct ``magika``)
freezes into a working EXE.

Run under PyInstaller: Analysis on this file, console=True, with the same
collect_data_files('magika') / hiddenimports as md-desk.spec.
"""

import io
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Force headless before any Qt widget is created.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
from src.main_window import MainWindow
from src.file_entry import FileStatus
from src.result import ConversionResult, QualityWarning

_OUT = []


def _log(name, ok, detail=""):
    _OUT.append((name, ok, detail))
    print(("PASS" if ok else "FAIL"), "-", name, "" if ok else f":: {detail}", flush=True)


def _warn_blob(panel):
    return "\n".join(f"{m.text()}|{c.text()}" for _, m, c in panel._warn_rows if m.text())


def main():
    app = QApplication.instance() or QApplication([])
    w = MainWindow()

    # ---- DONE + warning ------------------------------------------------
    d = tempfile.mkdtemp()
    p0 = Path(d) / "a.md"
    p0.write_text("# A\n\nsome text", encoding="utf-8")
    w._model.add_paths([str(p0)])
    r0 = w._model.rowCount() - 1
    warn = QualityWarning("LOW_TEXT_YIELD", "输出文字偏少，可能未完整提取")
    w._table.selectRow(r0)
    w._current_row = r0
    w._on_file_finished(ConversionResult.success(r0, "# A\n\nsome text", duration_ms=7, warnings=(warn,)))

    panel = w._diag_panel
    _log("S4.1 DONE+warning banner", panel._banner.text() == "转换成功，但有质量提示", panel._banner.text())
    _log("S4.2 warning text shown", "输出文字偏少" in _warn_blob(panel), _warn_blob(panel))
    _log("S4.3 status column=完成 (质量提示)",
         w._model.data(w._model.index(r0, 3), Qt.ItemDataRole.DisplayRole) == "完成 (质量提示)",
         w._model.data(w._model.index(r0, 3), Qt.ItemDataRole.DisplayRole))
    _log("S4.4 report attached to entry",
         w._model.entry_at(r0) is not None and w._model.entry_at(r0).report is not None
         and w._model.entry_at(r0).report.ok is True)
    _log("S4.5 not labelled ERROR", "失败" not in panel._banner.text(), panel._banner.text())

    # ---- ERROR ----------------------------------------------------------
    p1 = Path(d) / "b.md"
    p1.write_text("broken", encoding="utf-8")
    w._model.add_paths([str(p1)])
    r1 = w._model.rowCount() - 1
    w._table.selectRow(r1)
    w._current_row = r1
    w._on_file_finished(ConversionResult.failure(r1, FileStatus.ERROR, "boom detail", duration_ms=3))
    _log("S4.6 ERROR banner", "转换失败" in panel._banner.text(), panel._banner.text())
    _log("S4.7 error text shown", "boom detail" in panel._error_label.text(), panel._error_label.text())
    _log("S4.8 failed report still viewable",
         w._model.entry_at(r1) is not None and w._model.entry_at(r1).report is not None
         and w._model.entry_at(r1).report.ok is False)

    # ---- lifecycle: clear wipes report --------------------------------
    w._on_clear()
    w._show_entry(None)
    _log("S4.9 clear -> placeholder", panel._banner.text() == "暂无诊断信息", panel._banner.text())

    # ---- diagnostic log written ---------------------------------------
    _log("S4.10 diagnostic log exists", os.path.exists(w._diag_logger.log_path),
         w._diag_logger.log_path)

    w.close()
    ok = all(ok_ for _, ok_, _ in _OUT)
    print("S4_FROZEN_PASS" if ok else "S4_FROZEN_FAIL", flush=True)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
