"""Frozen-binary smoke for v0.4 Stage 5 (stabilization).

Headless (offscreen). Builds a MainWindow and drives synthetic terminal
results through the real ``_on_file_finished`` path, then exercises the
Stage 5 hardening directly:
  * DiagnosticsPanel renders DONE+warning / ERROR correctly (never ERROR for
    warnings; report attached to the entry; clear wipes it).
  * DiagnosticLogger rotates at a size cap (stdlib-only), keeps only metadata
    (no markdown body, no secrets) across rotations, and respects backup_count.
  * DiagnosticsPanel tolerates NEW warning codes / unknown source types and
    non-QualityWarning warning objects without crashing.
  * In a frozen build, magika's model data is correctly bundled.

Complements exe_stage4_diag_smoke.py / exe_s3_smoke.py. Proves the Stage 5
build config (correct ``magika`` collection) freezes into a working EXE.
"""

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
from src.main_window import MainWindow
from src.diagnostics_panel import DiagnosticsPanel
from src.file_entry import FileStatus
from src.report import ConversionReport, DiagnosticLogger, ReportBuilder
from src.result import ConversionResult, QualityWarning

_OUT = []


def _log(name, ok, detail=""):
    _OUT.append((name, ok, detail))
    print(("PASS" if ok else "FAIL"), "-", name, "" if ok else f":: {detail}", flush=True)


def _warn_blob(panel):
    return "\n".join(f"{m.text()}|{c.text()}" for _, m, c in panel._warn_rows if m.text())


def _stage4_panel_checks(w):
    panel = w._diag_panel
    d = tempfile.mkdtemp()
    p0 = Path(d) / "a.md"
    p0.write_text("# A\n\nsome text", encoding="utf-8")
    w._model.add_paths([str(p0)])
    r0 = w._model.rowCount() - 1
    warn = QualityWarning("LOW_TEXT_YIELD", "输出文字偏少，可能未完整提取")
    w._table.selectRow(r0)
    w._current_row = r0
    w._on_file_finished(ConversionResult.success(r0, "# A\n\nsome text", duration_ms=7, warnings=(warn,)))
    _log("S5.1 DONE+warning banner", panel._banner.text() == "转换成功，但有质量提示", panel._banner.text())
    _log("S5.2 warning text shown", "输出文字偏少" in _warn_blob(panel), _warn_blob(panel))
    _log("S5.3 status column=完成 (质量提示)",
         w._model.data(w._model.index(r0, 3), Qt.ItemDataRole.DisplayRole) == "完成 (质量提示)",
         w._model.data(w._model.index(r0, 3), Qt.ItemDataRole.DisplayRole))
    _log("S5.4 report attached to entry",
         w._model.entry_at(r0) is not None and w._model.entry_at(r0).report is not None
         and w._model.entry_at(r0).report.ok is True)
    _log("S5.5 not labelled ERROR", "失败" not in panel._banner.text(), panel._banner.text())

    p1 = Path(d) / "b.md"
    p1.write_text("broken", encoding="utf-8")
    w._model.add_paths([str(p1)])
    r1 = w._model.rowCount() - 1
    w._table.selectRow(r1)
    w._current_row = r1
    w._on_file_finished(ConversionResult.failure(r1, FileStatus.ERROR, "boom detail", duration_ms=3))
    _log("S5.6 ERROR banner", "转换失败" in panel._banner.text(), panel._banner.text())
    _log("S5.7 error text shown", "boom detail" in panel._error_label.text(), panel._error_label.text())

    w._on_clear()
    w._show_entry(None)
    _log("S5.8 clear -> placeholder", panel._banner.text() == "暂无诊断信息", panel._banner.text())
    _log("S5.9 diagnostic log exists", os.path.exists(w._diag_logger.log_path), w._diag_logger.log_path)


def _rotation_checks():
    # Rotation at a tiny cap, with secret redaction preserved across generations.
    log_dir = tempfile.mkdtemp()
    logger = DiagnosticLogger(log_dir=log_dir, max_bytes=200, backup_count=2)
    from src.file_entry import FileEntry
    fe = FileEntry(path="/x/secret.txt", filename="secret.txt", extension=".txt", size=10)
    res = ConversionResult.failure(0, FileStatus.ERROR, "token=SUPERSECRET api_key=abc123")
    rep = ReportBuilder.build(res, fe)
    for _ in range(20):
        assert logger.record(rep) is True
    cur = logger.log_path
    _log("S5.10 rotation .1 exists", os.path.exists(cur + ".1"), cur + ".1")
    _log("S5.11 rotation caps at backup_count (.3 absent)",
         not os.path.exists(cur + ".3"), cur + ".3")
    # Every generation is valid JSON metadata, no markdown body.
    import json
    clean = True
    for gen in ("", ".1", ".2"):
        p = cur + gen
        if not os.path.exists(p):
            continue
        with open(p, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                obj = json.loads(line)
                if "markdown" in obj:
                    clean = False
    _log("S5.12 no markdown body in any generation", clean)
    # Redaction preserved in the rotated generation.
    rot = Path(cur + ".1").read_text(encoding="utf-8")
    _log("S5.13 redaction preserved in rotation",
         "SUPERSECRET" not in rot and "abc123" not in rot and "<REDACTED>" in rot)


def _unknown_type_checks():
    # A NEW warning code + unknown source type + non-QualityWarning object must
    # render without crashing.
    app = QApplication.instance() or QApplication([])
    panel = DiagnosticsPanel()

    class _FakeWarn:
        def __init__(self, code, message):
            self.code = code
            self.message = message

    rep = ConversionReport(
        row=0, source="weird://src", source_type="stream",
        status=FileStatus.DONE, duration_ms=5, output_chars=10,
        warnings=(_FakeWarn("NEW_CODE", "未来新增的提示"),),
        error=None, timestamp="2026-01-01T00:00:00Z",
    )
    panel.show_report(rep)
    _log("S5.14 unknown source_type shown", panel._ov_type.text() == "stream", panel._ov_type.text())
    _log("S5.15 unknown warning code shown",
         any("NEW_CODE" in c.text() for _, _, c in panel._warn_rows),
         str([c.text() for _, _, c in panel._warn_rows]))
    _log("S5.16 unknown warning message shown",
         any("未来新增的提示" in m.text() for _, m, _ in panel._warn_rows),
         str([m.text() for _, m, _ in panel._warn_rows]))

    # None source_type + bare-string warning object -> no crash.
    rep2 = ConversionReport(
        row=1, source="x", source_type=None, status=FileStatus.DONE,
        duration_ms=1, output_chars=3, warnings=("bare string warning",),
        error=None, timestamp="2026-01-01T00:00:00Z",
    )
    panel.show_report(rep2)
    _log("S5.17 None source_type -> 占位符", panel._ov_type.text() == "—", panel._ov_type.text())
    panel.deleteLater()
    app.processEvents()


def _magika_bundled():
    if not getattr(sys, "frozen", False):
        _log("S5.18 magika bundled (skip: not frozen)", True, "source run")
        return
    model = os.path.join(os.path.dirname(sys.executable), "_internal", "magika",
                         "models", "standard_v3_3", "model.onnx")
    _log("S5.18 magika model bundled", os.path.exists(model), model)


def main():
    app = QApplication.instance() or QApplication([])
    w = MainWindow()
    _stage4_panel_checks(w)
    w.close()
    _rotation_checks()
    _unknown_type_checks()
    _magika_bundled()
    ok = all(ok_ for _, ok_, _ in _OUT)
    print("S5_FROZEN_PASS" if ok else "S5_FROZEN_FAIL", flush=True)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
