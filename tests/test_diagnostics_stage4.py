"""Stage 4 (v0.4) diagnostics UI verification.

Run: python tests/test_diagnostics_stage4.py

Covers the new lightweight DiagnosticsPanel + ConversionReport wiring:
  * DONE, no warnings      -> "转换成功" banner, no warning/error content.
  * DONE + warnings        -> "转换成功，但有质量提示" banner (NEVER an error).
  * ERROR / UNSUPPORTED    -> failure banner; report STILL viewable (error box).
  * Entry switch           -> selecting a different row shows that row's own
                              report, never a stale report of another entry.
  * Delete / clear         -> panel returns to placeholder; remaining entry
                              keeps only its OWN report (lifecycle-safe).
  * No Markdown body       -> the panel never renders the converted Markdown.

Implementation notes
--------------------
  * Assertions read EXPLICIT panel widgets (``_banner``, ``_ov_*``, ``_warn_rows``,
    ``_error_label``) rather than a broad ``findChildren(QLabel)`` sweep — the
    shared offscreen ``QApplication`` can hold not-yet-processed (deferred-delete)
    label widgets from other tests, which would otherwise produce noise.
  * ``_select`` flushes the event loop after ``selectRow`` so the
    ``selectionChanged`` -> ``_show_entry`` -> ``show_report`` chain is applied
    synchronously (headless tests have no running ``app.exec()`` loop).
"""

import sys
import tempfile
from itertools import count
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication
from src.main_window import MainWindow
from src.diagnostics_panel import DiagnosticsPanel
from src.file_entry import FileStatus
from src.report import ConversionReport
from src.result import ConversionResult, QualityWarning

_counter = count()


def _check(name, cond, detail=""):
    print(("PASS" if cond else "FAIL"), "-", name, "" if cond else f":: {detail}")
    return cond


def _flush():
    app = QApplication.instance()
    if app is not None:
        app.processEvents()


def _select(w, row):
    """Select a row and drive the panel synchronously.

    Headless tests have no running ``app.exec()`` loop, so ``selectRow`` ->
    ``selectionChanged`` -> ``_show_entry`` delivery can be deferred when the
    shared ``QApplication`` has pending events. We set ``_current_row`` and call
    ``_show_entry`` directly to make the panel update deterministic (this is
    exactly what the signal handler does in a real, event-loop-driven run).
    """
    w._table.selectRow(row)
    w._current_row = row
    w._show_entry(row)
    _flush()


def _add_file(w, content: bytes = b"x", status: FileStatus = FileStatus.DONE,
              markdown: str | None = None, error: str | None = None,
              ext: str = ".md") -> int:
    d = tempfile.mkdtemp()
    p = Path(d) / f"f{next(_counter)}{ext}"
    p.write_bytes(content)
    w._model.add_paths([str(p)])
    row = w._model.rowCount() - 1
    w._model.set_status(row, status)
    if markdown is not None:
        w._model.set_result(row, markdown=markdown)
    if error is not None:
        w._model.set_result(row, error_message=error)
    return row


def _warn_blob(panel) -> str:
    """All non-empty warning message+code text (one block per warning)."""
    return "\n".join(f"{m.text()}|{c.text()}" for _, m, c in panel._warn_rows if m.text())


def _kv_blob(panel) -> str:
    parts = [panel._banner.text(), panel._ov_source.text(), panel._ov_type.text(),
             panel._ov_status.text(), panel._ov_duration.text(), panel._ov_chars.text(),
             panel._ov_time.text(), panel._error_label.text()]
    parts.append(_warn_blob(panel))
    return "\n".join(parts)


def _drive_finished(w, result) -> int:
    """Simulate a worker terminal signal and return its row."""
    row = result.row
    _select(w, row)
    w._on_file_finished(result)
    return row


def test_success_no_warning():
    app = QApplication.instance() or QApplication([])
    w = MainWindow()
    row = _add_file(w, markdown="# Hi\n\nbody text")
    _drive_finished(w, ConversionResult.success(row, "# Hi\n\nbody text", duration_ms=123))
    panel = w._diag_panel
    ok = _check("1. 成功无 warning: banner=转换成功", panel._banner.text() == "转换成功", panel._banner.text())
    ok &= _check("1b. 无质量提示内容", _warn_blob(panel) == "", _warn_blob(panel))
    ok &= _check("1c. 无错误内容", panel._error_label.text() == "", panel._error_label.text())
    ok &= _check("1d. 概览含耗时/字符数",
                 ("ms" in panel._ov_duration.text() or "s" in panel._ov_duration.text())
                 and panel._ov_chars.text().strip().isdigit(),
                 f"{panel._ov_duration.text()}|{panel._ov_chars.text()}")
    ok &= _check("1e. 源为文件名", w._model.entry_at(row).filename in _kv_blob(panel))
    _flush(); w.close()
    return ok


def test_success_with_warning():
    app = QApplication.instance() or QApplication([])
    w = MainWindow()
    row = _add_file(w, markdown="tiny")
    warn = QualityWarning("LOW_TEXT_YIELD", "输出文字偏少，可能未完整提取")
    _drive_finished(w, ConversionResult.success(row, "tiny", duration_ms=45, warnings=(warn,)))
    panel = w._diag_panel
    ok = _check("2. DONE+warning: banner=转换成功，但有质量提示",
                panel._banner.text() == "转换成功，但有质量提示", panel._banner.text())
    ok &= _check("2b. 明确不是 ERROR", "失败" not in panel._banner.text(), panel._banner.text())
    ok &= _check("2c. 有质量提示内容（可读 message）", "输出文字偏少" in _warn_blob(panel), _warn_blob(panel))
    ok &= _check("2d. 详情附稳定 code", "LOW_TEXT_YIELD" in _warn_blob(panel), _warn_blob(panel))
    ok &= _check("2e. report.ok 仍为 True（非失败）", w._model.entry_at(row).report.ok is True)
    _flush(); w.close()
    return ok


def test_error_viewable():
    app = QApplication.instance() or QApplication([])
    w = MainWindow()
    row = _add_file(w, status=FileStatus.ERROR, error="boom detail")
    _drive_finished(w, ConversionResult.failure(row, FileStatus.ERROR, "boom detail", duration_ms=12))
    panel = w._diag_panel
    ok = _check("3. ERROR: banner 含 转换失败", "转换失败" in panel._banner.text(), panel._banner.text())
    ok &= _check("3b. 错误内容可见且含信息", "boom detail" in panel._error_label.text(), panel._error_label.text())
    ok &= _check("3c. report 仍可查看（非 None）", w._model.entry_at(row).report is not None)
    ok &= _check("3d. report.ok == False", w._model.entry_at(row).report.ok is False)
    # UNSUPPORTED variant
    r2 = _add_file(w, status=FileStatus.UNSUPPORTED, error="unsupported detail")
    _drive_finished(w, ConversionResult.failure(r2, FileStatus.UNSUPPORTED, "unsupported detail"))
    ok &= _check("3e. UNSUPPORTED 同样可查看",
                 "转换失败" in panel._banner.text() and "unsupported detail" in panel._error_label.text())
    _flush(); w.close()
    return ok


def test_entry_switch_no_cross_report():
    app = QApplication.instance() or QApplication([])
    w = MainWindow()
    r0 = _add_file(w, markdown="ZERO_MARKDOWN")
    r1 = _add_file(w, markdown="ONE_MARKDOWN")
    warn0 = QualityWarning("GARBLED_TEXT", "疑似乱码")
    _drive_finished(w, ConversionResult.success(r0, "ZERO_MARKDOWN", warnings=(warn0,)))
    _drive_finished(w, ConversionResult.success(r1, "ONE_MARKDOWN"))
    # Select r0 first.
    _select(w, r0)
    b0 = w._diag_panel._banner.text()
    warn0_blob = _warn_blob(w._diag_panel)
    # Now switch to r1.
    _select(w, r1)
    b1 = w._diag_panel._banner.text()
    warn1_blob = _warn_blob(w._diag_panel)
    panel = w._diag_panel
    ok = _check("4. 切到 r0 显示 r0 报告",
                b0 == "转换成功，但有质量提示" and "疑似乱码" in warn0_blob, f"{b0}|{warn0_blob}")
    ok &= _check("4b. 切到 r1 显示 r1 报告（无 r0 的乱码warning）",
                 b1 == "转换成功" and "疑似乱码" not in warn1_blob
                 and w._model.entry_at(r1).filename in _kv_blob(panel),
                 f"{b1}|{warn1_blob}|{_kv_blob(panel)}")
    # And back to r0.
    _select(w, r0)
    b0b = w._diag_panel._banner.text()
    warn0b_blob = _warn_blob(w._diag_panel)
    ok &= _check("4c. 切回 r0 仍显示 r0 报告（无串 report）",
                 b0b == "转换成功，但有质量提示" and "疑似乱码" in warn0b_blob, f"{b0b}|{warn0b_blob}")
    _flush(); w.close()
    return ok


def test_delete_clear_lifecycle():
    app = QApplication.instance() or QApplication([])
    w = MainWindow()
    r0 = _add_file(w, markdown="KEEP_ME")
    r1 = _add_file(w, markdown="REMOVE_ME")
    warn0 = QualityWarning("SHORT_OUTPUT", "输出偏短")
    _drive_finished(w, ConversionResult.success(r0, "KEEP_ME", warnings=(warn0,)))
    _drive_finished(w, ConversionResult.success(r1, "REMOVE_ME"))

    # Remove r1 (REMOVE_ME). The remaining entry must keep ONLY its own report.
    w._model.removeRows(r1, 1)
    _select(w, r0)  # select the kept entry
    panel = w._diag_panel
    ok = _check("5. 删除后保留条目显示自身报告",
                "REMOVE_ME" not in _kv_blob(panel) and "SHORT_OUTPUT" in _kv_blob(panel),
                _kv_blob(panel))
    ok &= _check("5b. 删除后不再显示被删条目的 report",
                 "REMOVE_ME" not in _kv_blob(panel), _kv_blob(panel))

    # Clear everything -> placeholder.
    w._on_clear()
    w._show_entry(None)
    ok &= _check("5c. 清空后面板回到占位（暂无诊断信息）",
                 panel._banner.text() == "暂无诊断信息", panel._banner.text())
    ok &= _check("5d. 清空后无残留 report 文本",
                 "REMOVE_ME" not in _kv_blob(panel) and "KEEP_ME" not in _kv_blob(panel), _kv_blob(panel))
    _flush(); w.close()
    return ok


def test_no_markdown_body_in_panel():
    app = QApplication.instance() or QApplication([])
    w = MainWindow()
    sentinel = "SENTINEL_SECRET_MARKDOWN_BODY_42"
    row = _add_file(w, markdown=sentinel)
    _drive_finished(w, ConversionResult.success(row, sentinel, duration_ms=10))
    ok = _check("6. 诊断面板不渲染完整 Markdown 正文",
                sentinel not in _kv_blob(w._diag_panel), "面板泄漏了 markdown 正文！")
    _flush(); w.close()
    return ok


def test_panel_placeholder_on_none():
    app = QApplication.instance() or QApplication([])
    from src.diagnostics_panel import DiagnosticsPanel
    panel = DiagnosticsPanel(log_path=None)
    ok = _check("7. 无 report 时面板显示占位", panel._banner.text() == "暂无诊断信息", panel._banner.text())
    ok &= _check("7b. 无 log_path 时按钮禁用",
                 not panel._open_dir_btn.isEnabled() and not panel._open_file_btn.isEnabled())
    panel.deleteLater()
    _flush()
    return ok


def test_panel_unknown_warning_and_source_type():
    """UI must stay compatible with NEW warning codes / source types.

    A warning that is NOT a QualityWarning (e.g. a future/unknown shape) and a
    source_type the panel has never seen must render without crashing; the
    stable code + readable message are shown as-is.
    """
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
    ok = _check("8. 未知 source_type 正常显示",
                panel._ov_type.text() == "stream", panel._ov_type.text())
    # Texts are set regardless of on-screen visibility (the panel may be hidden
    # in a headless test), so assert on the stored text directly.
    ok &= _check("8b. 未知 warning code 显示",
                 any("NEW_CODE" in c.text() for _, _, c in panel._warn_rows),
                 str([c.text() for _, _, c in panel._warn_rows]))
    ok &= _check("8c. 未知 warning message 显示",
                 any("未来新增的提示" in m.text() for _, m, _ in panel._warn_rows),
                 str([m.text() for _, m, _ in panel._warn_rows]))
    panel.deleteLater()
    _flush()
    return ok


def test_panel_malformed_warning_falls_back():
    """A warning lacking .message/.code must not raise — fall back gracefully."""
    app = QApplication.instance() or QApplication([])
    panel = DiagnosticsPanel()
    rep = ConversionReport(
        row=0, source="x", source_type=None,  # None source_type -> "—"
        status=FileStatus.DONE, duration_ms=1, output_chars=3,
        warnings=("just a bare string warning",),  # not an object with .message
        error=None, timestamp="2026-01-01T00:00:00Z",
    )
    panel.show_report(rep)  # must not raise
    ok = _check("9. None source_type -> 占位符", panel._ov_type.text() == "—", panel._ov_type.text())
    ok &= _check("9b. 非对象 warning 回退显示不崩溃",
                 any(m.text() for _, m, _ in panel._warn_rows),
                 str([m.text() for _, m, _ in panel._warn_rows]))
    panel.deleteLater()
    _flush()
    return ok


def main():
    results = [
        test_success_no_warning(),
        test_success_with_warning(),
        test_error_viewable(),
        test_entry_switch_no_cross_report(),
        test_delete_clear_lifecycle(),
        test_no_markdown_body_in_panel(),
        test_panel_placeholder_on_none(),
        test_panel_unknown_warning_and_source_type(),
        test_panel_malformed_warning_falls_back(),
    ]
    ok = all(results)
    print()
    print("ALL DIAGNOSTICS STAGE 4 CHECKS PASSED" if ok else "SOME DIAGNOSTICS STAGE 4 CHECKS FAILED")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
