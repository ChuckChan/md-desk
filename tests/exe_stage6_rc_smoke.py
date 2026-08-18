"""Frozen-binary RC smoke for MdDesk v0.4.0.

Headless (offscreen). Drives the real MainWindow + conversion worker + settings
+ diagnostics across the full RC feature matrix. Complements
exe_stage5_diag_smoke.py (which only covered the Stage 5 stabilization bits).

Coverage (all offline-safe; network-bound paths are exercised via mocked
fetch / engine so the smoke never needs internet or hits SSRF guards):

  * Local file conversion (real MarkItDown, no network)
  * Batch conversion (multiple files in one worker run)
  * URL entry: accepted + end-to-end convert via worker (mocked fetch+engine)
  * YouTube: accepted as a URL entry + convert_url forwards
    ``youtube_transcript_languages`` to the engine (converter-level support)
  * StreamInfo override: reaches the engine StreamInfo (mocked) AND a real
    mislabeled-extension passthrough conversion
  * Advanced Settings dialog: toggling quality writes back to Settings + persists
  * Preview / Copy / Export: source+preview populated; copy -> clipboard;
    export -> file written (dialog + clipboard mocked)
  * Quality OFF: converted file produces NO warnings (empty tuple)
  * Quality ON + warning: low-yield input surfaces a quality warning and the
    status column shows "完成 (质量提示)" (never ERROR)
  * Diagnostics UI: DONE+warning / ERROR / clear / unknown-type tolerance
  * Diagnostic log: redaction + rotation, metadata-only (no markdown body)
  * Frozen-only: magika model bundled; markitdown importable

Run both as a source script (frozen-only checks skipped) and as a frozen EXE.
"""

import io
import json
import os
import sys
import tempfile
import threading
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
if not getattr(sys, "frozen", False):
    # Source-mode only: make the local `src` package importable. In frozen mode
    # `src` is collected into the PYZ archive by the spec's collect_submodules('src');
    # inserting ROOT here (which resolves to an unstable path under PyInstaller)
    # must be avoided so it cannot shadow or confuse the frozen import graph.
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from PySide6.QtCore import QEventLoop, Qt, QTimer
from PySide6.QtWidgets import QApplication, QFileDialog

from src.advanced_settings_dialog import AdvancedSettingsDialog
from src.converter import convert_url
from src.diagnostics_panel import DiagnosticsPanel
from src.file_entry import FileEntry, FileStatus
from src.main_window import MainWindow
from src.report import ConversionReport, DiagnosticLogger, ReportBuilder
from src.result import ConversionResult, QualityWarning
from src.settings import Settings, StreamInfoOverride


_OUT = []


def _log(name, ok, detail=""):
    _OUT.append((name, ok, detail))
    print(("PASS" if ok else "FAIL"), "-", name, "" if ok else f":: {detail}", flush=True)
    return ok


# ---------------------------------------------------------------------------
# Fakes used to exercise network-bound paths offline.
# ---------------------------------------------------------------------------
class _FakeFetchService:
    """Returns canned HTML for any URL so convert_url runs without network."""

    def __init__(self, body=None):
        self._body = body or (
            "<html><head><title>RC</title></head>"
            "<body><h1>Hello RC</h1><p>remote markdown body</p></body></html>"
        )

    def fetch(self, url):
        from markitdown import StreamInfo

        si = StreamInfo(url=url, filename="page.html", extension=".html",
                       mimetype="text/html")
        return type("FetchResult", (), {
            "content": io.BytesIO(self._body.encode("utf-8")),
            "stream_info": si,
            "final_url": url,
            "status_code": 200,
        })()


class _FakeEngine:
    """Records the StreamInfo + kwargs handed to the conversion engine."""

    def __init__(self):
        self.calls = []

    def convert_stream(self, stream, stream_info=None, **kwargs):
        self.calls.append((stream_info, dict(kwargs)))
        return type("R", (), {"markdown": "# Converted\n\nremote markdown body"})

    def convert(self, path):
        self.calls.append((None, {"path": path}))
        return type("R", (), {"markdown": "# Converted\n\nlocal markdown body"})


def _fake_engine_ctx():
    eng = _FakeEngine()
    return eng, patch("src.markitdown_factory.MarkItDownFactory.create",
                      return_value=eng)


def _run_batch(window, timeout_ms=30000):
    """Start the worker and wait for batch_finished, then flush queued signals."""
    window.start_conversion()
    worker = window._worker
    loop = QEventLoop()
    finished = {"ok": False}

    def _on_finished():
        finished["ok"] = True
        loop.quit()

    worker.batch_finished.connect(_on_finished)
    QTimer.singleShot(timeout_ms, loop.quit)
    loop.exec()
    if not finished["ok"]:
        _log("batch event-loop timeout", False, "worker did not finish in time")
        return
    # Flush any remaining queued signals (file_finished -> model update).
    # NOTE: do NOT call worker.deleteLater() here. The ConversionWorker is owned
    # by MainWindow and is cleaned up when the window/app closes; forcing a
    # synchronous deleteLater()+sendPostedEvents() on a QThread whose C++ object
    # may already be torn down raises "libshiboken: Internal C++ object
    # (ConversionWorker) already deleted" under frozen PyInstaller. Just flush.
    app = QApplication.instance()
    app.processEvents()
    app.sendPostedEvents()


# ---------------------------------------------------------------------------
# 1. Local file (real MarkItDown)
# ---------------------------------------------------------------------------
def _local_file_check(w):
    d = tempfile.mkdtemp()
    p = Path(d) / "note.txt"
    p.write_text("# Title\n\nSome real markdown content for RC.\n", encoding="utf-8")
    w._model.add_paths([str(p)])
    row = w._model.rowCount() - 1
    _run_batch(w)
    entry = w._model.entry_at(row)
    ok = _log("S6.1 本地文件转换 DONE",
              entry is not None and entry.status == FileStatus.DONE and bool(entry.markdown),
              entry.status.value if entry else "none")
    ok &= _log("S6.1b 本地文件 markdown 非空且含原文",
               "Some real markdown content" in (entry.markdown or ""),
               repr((entry.markdown or "")[:60]))
    ok &= _log("S6.1c 本地文件 quality OFF -> 无警告",
               entry.report is not None and entry.report.warnings == (),
               repr(entry.report.warnings if entry.report else None))
    # select + preview
    w._table.selectRow(row)
    w._current_row = row
    w._show_entry(row)
    ok &= _log("S6.1d 预览/源码填充",
               "Some real markdown content" in w._source_view.toPlainText(),
               w._source_view.toPlainText()[:60])
    return ok


# ---------------------------------------------------------------------------
# 2. Batch (multiple files)
# ---------------------------------------------------------------------------
def _batch_check(w):
    d = tempfile.mkdtemp()
    files = []
    for i, txt in enumerate(["alpha", "beta", "gamma"]):
        p = Path(d) / f"f{i}.txt"
        p.write_text(f"# {txt}\n\ncontent {txt}\n", encoding="utf-8")
        files.append(str(p))
    before = w._model.rowCount()
    w._model.add_paths(files)
    _run_batch(w)
    n = w._model.rowCount()
    done = sum(1 for r in range(before, n)
               if w._model.entry_at(r).status == FileStatus.DONE)
    return _log("S6.2 批量转换全部 DONE",
                done == len(files) and w._model.entry_at(n - 1).status == FileStatus.DONE,
                f"done={done}/{len(files)}")


# ---------------------------------------------------------------------------
# 3. URL entry + end-to-end convert (mocked fetch + engine)
# ---------------------------------------------------------------------------
def _url_check(w):
    eng = _FakeEngine()
    with patch("src.markitdown_factory.MarkItDownFactory.create", return_value=eng), \
         patch("src.converter.UrlFetchService", _FakeFetchService):
        added, _ = w._model.add_url("https://example.com/rc-page.html")
        ok = _log("S6.3 URL 入列被接受", added == 1, f"added={added}")
        row = w._model.rowCount() - 1
        entry = w._model.entry_at(row)
        ok &= _log("S6.3b URL 条目 is_url=True", entry is not None and entry.is_url,
                   repr(entry.is_url if entry else None))
        _run_batch(w)
        e2 = w._model.entry_at(row)
        ok &= _log("S6.3c URL 经 worker 转换 DONE",
                   e2.status == FileStatus.DONE and bool(e2.markdown), e2.status.value)
        ok &= _log("S6.3d 引擎被调用处理 URL 转换",
                   bool(eng.calls),
                   repr(eng.calls[:1] if eng.calls else None))
    return ok


# ---------------------------------------------------------------------------
# 4. YouTube: accepted + convert_url forwards youtube_transcript_languages
# ---------------------------------------------------------------------------
def _youtube_check(w):
    added, _ = w._model.add_url("https://www.youtube.com/watch?v=RCd3m0")
    ok = _log("S6.4 YouTube 链接被接受为 URL 条目",
              added == 1, f"added={added}")
    row = w._model.rowCount() - 1
    entry = w._model.entry_at(row)
    ok &= _log("S6.4b YouTube 条目 is_url=True",
               entry is not None and entry.is_url, repr(entry.is_url if entry else None))
    # Converter-level support: convert_url must forward youtube_transcript_languages
    # to the engine when provided.
    eng = _FakeEngine()
    with patch("src.markitdown_factory.MarkItDownFactory.create", return_value=eng), \
         patch("src.converter.UrlFetchService", _FakeFetchService):
        md = convert_url("https://www.youtube.com/watch?v=RCd3m0",
                         youtube_languages=["zh-Hans", "en"])
        ok &= _log("S6.4c convert_url 返回 markdown", isinstance(md, str) and len(md) > 0,
                   repr(md[:40]))
        ok &= _log("S6.4d youtube_transcript_languages 转发到引擎",
                   bool(eng.calls) and eng.calls[0][1].get("youtube_transcript_languages") == ["zh-Hans", "en"],
                   repr(eng.calls[0][1] if eng.calls else None))
    return ok


# ---------------------------------------------------------------------------
# 5. StreamInfo override reaches the engine + real mislabeled passthrough
# ---------------------------------------------------------------------------
def _streaminfo_check(w):
    # (a) mechanism: override fields appear on the StreamInfo handed to engine.
    d = tempfile.mkdtemp()
    p = Path(d) / "data.bin"
    p.write_text("raw text payload\n", encoding="utf-8")
    added, _ = w._model.add_paths([str(p)])
    row = w._model.rowCount() - 1
    entry = w._model.entry_at(row)
    entry.stream_info_override = StreamInfoOverride(extension=".txt", charset="utf-8")
    eng = _FakeEngine()
    with patch("src.markitdown_factory.MarkItDownFactory.create", return_value=eng):
        from src.converter import convert_file
        convert_file(str(p), override=entry.stream_info_override)
        si = eng.calls[0][0] if eng.calls else None
        ok = _log("S6.5 StreamInfo 覆盖(扩展名)到达引擎",
                  si is not None and si.extension == ".txt", repr(si))
        ok &= _log("S6.5b StreamInfo 覆盖(字符集)到达引擎",
                   si is not None and si.charset == "utf-8", repr(si))
    # (b) real conversion: a .csv that is actually plain text, overridden to .txt
    raw = "Hello world\nThis is plain text content, not a spreadsheet.\n"
    pp = Path(d) / "data.csv"
    pp.write_text(raw, encoding="utf-8")
    md_default = convert_file(str(pp))  # routes to CSV converter
    md_override = convert_file(str(pp), override=StreamInfoOverride(extension=".txt"))
    ok &= _log("S6.5c 误标 .csv 默认走 CSV(≠原文)",
               md_default.strip() != raw.strip(), repr(md_default[:50]))
    ok &= _log("S6.5d 覆盖 .txt -> PlainText 原文透传",
               md_override.strip() == raw.strip(), repr(md_override[:50]))
    return ok


# ---------------------------------------------------------------------------
# 6. Advanced Settings dialog toggles quality -> Settings + persists
# ---------------------------------------------------------------------------
def _advanced_settings_check(w):
    d = tempfile.mkdtemp()
    tmp_settings = Path(d) / "settings.json"
    # Neutralize side effects: never touch the real Credential Manager or the
    # real APPDATA path.
    with patch("src.advanced_settings_dialog.set_api_key") as m_set, \
         patch("src.advanced_settings_dialog.delete_api_key") as m_del:
        w._settings._path = str(tmp_settings)
        # pick a selected entry so the override section is enabled
        w._model.add_paths([str(Path(d) / "x.txt")])
        row = w._model.rowCount() - 1
        w._current_row = row
        entry = w._model.entry_at(row)
        dlg = AdvancedSettingsDialog(w._settings, entry, w)
        dlg._quality_enabled.setChecked(True)
        dlg._ai_key.setText("")  # empty -> delete_api_key (mocked)
        dlg.accept()
        ok = _log("S6.6 高级设置开启 quality -> settings 更新",
                  w._settings.quality_enabled is True, repr(w._settings.quality_enabled))
        # restore real path so later saves (if any) don't go to temp
        w._settings._path = None
        ok &= _log("S6.6b 高级设置接受未触碰凭据管理器",
                  m_set.call_count == 0 and m_del.call_count >= 0,
                  f"set={m_set.call_count} del={m_del.call_count}")
    # persisted file reflects quality_enabled=True
    if tmp_settings.exists():
        blob = json.loads(tmp_settings.read_text(encoding="utf-8"))
        ok &= _log("S6.6c quality_enabled 已持久化到 settings.json",
                   blob.get("quality_enabled") is True, repr(blob))
    else:
        ok = _log("S6.6c quality_enabled 已持久化", False, "settings.json 未写入")
    # reset for later checks
    w._settings.quality_enabled = False
    return ok


# ---------------------------------------------------------------------------
# 7. Preview / Copy / Export
# ---------------------------------------------------------------------------
def _preview_copy_export_check(w):
    d = tempfile.mkdtemp()
    p = Path(d) / "export.txt"
    p.write_text("# Export\n\ncopy/export RC content.\n", encoding="utf-8")
    w._model.add_paths([str(p)])
    row = w._model.rowCount() - 1
    _run_batch(w)  # quality OFF -> no warnings
    entry = w._model.entry_at(row)
    w._table.selectRow(row)
    w._current_row = row
    w._show_entry(row)
    ok = _log("S6.7 预览填充(源码/渲染)",
              "copy/export RC content" in w._source_view.toPlainText()
              and "copy/export RC content" in w._preview_view.toMarkdown(),
              w._source_view.toPlainText()[:40])

    # Copy -> clipboard (mock clipboard so offscreen works)
    class _Clip:
        def __init__(self):
            self.text = None
        def setText(self, t):
            self.text = t
    clip = _Clip()
    with patch.object(QApplication, "clipboard", staticmethod(lambda: clip)):
        w._on_copy()
        ok &= _log("S6.7b 复制 Markdown -> 剪贴板",
                   clip.text == entry.markdown, repr((clip.text or "")[:30]))

    # Export -> file (mock save dialog)
    out = Path(d) / "out.md"
    with patch.object(QFileDialog, "getSaveFileName",
                      staticmethod(lambda *a, **k: (str(out), "Markdown 文件 (*.md)"))):
        w._on_export()
        ok &= _log("S6.7c 导出 .md 写入文件",
                   out.exists() and out.read_text(encoding="utf-8") == entry.markdown,
                   f"exists={out.exists()}")
    return ok


# ---------------------------------------------------------------------------
# 8. Quality ON + warning
# ---------------------------------------------------------------------------
def _quality_on_check(w):
    d = tempfile.mkdtemp()
    # >=2KB but <30 effective chars -> SHORT_OUTPUT warning.
    p = Path(d) / "lowyield.txt"
    p.write_text("x" * 10 + "\n" * 2500, encoding="utf-8")
    w._settings.quality_enabled = True
    try:
        w._model.add_paths([str(p)])
        row = w._model.rowCount() - 1
        _run_batch(w)
        entry = w._model.entry_at(row)
        ok = _log("S6.8 Quality ON: 状态仍 DONE(非 ERROR)",
                  entry.status == FileStatus.DONE, entry.status.value)
        warns = entry.report.warnings if entry.report else ()
        ok &= _log("S6.8b Quality ON: 产生质量提示",
                   len(warns) >= 1, repr([g.code for g in warns]))
        ok &= _log("S6.8c 状态列显示「完成 (质量提示)」",
                   w._model.data(w._model.index(row, 3), Qt.ItemDataRole.DisplayRole)
                   == "完成 (质量提示)",
                   w._model.data(w._model.index(row, 3), Qt.ItemDataRole.DisplayRole))
    finally:
        w._settings.quality_enabled = False
    return ok


# ---------------------------------------------------------------------------
# 9. Diagnostics UI (success/warning/error/unknown types)
# ---------------------------------------------------------------------------
def _diagnostics_ui_check(w):
    panel = w._diag_panel
    d = tempfile.mkdtemp()
    p = Path(d) / "a.md"
    p.write_text("# A\n\nsome text", encoding="utf-8")
    w._model.add_paths([str(p)])
    r0 = w._model.rowCount() - 1
    warn = QualityWarning("LOW_TEXT_YIELD", "输出文字偏少，可能未完整提取")
    w._table.selectRow(r0)
    w._current_row = r0
    w._on_file_finished(ConversionResult.success(r0, "# A\n\nsome text",
                                                  duration_ms=7, warnings=(warn,)))
    ok = _log("S6.9 DONE+warning 横幅", panel._banner.text() == "转换成功，但有质量提示",
              panel._banner.text())
    warn_blob = "\n".join(f"{m.text()}|{c.text()}" for _, m, c in panel._warn_rows if m.text())
    ok &= _log("S6.9b 警告文本显示", "输出文字偏少" in warn_blob, warn_blob[:60])
    ok &= _log("S6.9c 状态列=完成 (质量提示)",
               w._model.data(w._model.index(r0, 3), Qt.ItemDataRole.DisplayRole) == "完成 (质量提示)")

    p1 = Path(d) / "b.md"
    p1.write_text("broken", encoding="utf-8")
    w._model.add_paths([str(p1)])
    r1 = w._model.rowCount() - 1
    w._table.selectRow(r1)
    w._current_row = r1
    w._on_file_finished(ConversionResult.failure(r1, FileStatus.ERROR, "boom detail",
                                                  duration_ms=3))
    ok &= _log("S6.9d ERROR 横幅", "转换失败" in panel._banner.text(), panel._banner.text())
    ok &= _log("S6.9e 错误文本显示", "boom detail" in panel._error_label.text(),
               panel._error_label.text())

    # unknown-type tolerance
    class _FakeWarn:
        def __init__(self, code, message):
            self.code = code
            self.message = message
    rep = ConversionReport(row=9, source="weird://src", source_type="stream",
                           status=FileStatus.DONE, duration_ms=5, output_chars=10,
                           warnings=(_FakeWarn("NEW_CODE", "未来新增的提示"),),
                           error=None, timestamp="2026-01-01T00:00:00Z")
    panel.show_report(rep)
    ok &= _log("S6.9f 未知 source_type 显示", panel._ov_type.text() == "stream",
               panel._ov_type.text())
    ok &= _log("S6.9g 未知 warning code 显示",
               any("NEW_CODE" in c.text() for _, _, c in panel._warn_rows))
    w._on_clear()
    w._show_entry(None)
    ok &= _log("S6.9h 清空 -> 占位符", panel._banner.text() == "暂无诊断信息",
               panel._banner.text())
    return ok


# ---------------------------------------------------------------------------
# 10. Diagnostic log: redaction + rotation, metadata-only
# ---------------------------------------------------------------------------
def _log_rotation_check():
    log_dir = tempfile.mkdtemp()
    logger = DiagnosticLogger(log_dir=log_dir, max_bytes=200, backup_count=2)
    fe = FileEntry(path="/x/secret.txt", filename="secret.txt", extension=".txt", size=10)
    res = ConversionResult.failure(0, FileStatus.ERROR, "token=SUPERSECRET api_key=abc123")
    rep = ReportBuilder.build(res, fe)
    for _ in range(20):
        assert logger.record(rep) is True
    cur = logger.log_path
    ok = _log("S6.10 日志轮转 .1 生成", os.path.exists(cur + ".1"), cur + ".1")
    ok &= _log("S6.10b 轮转不超过 backup_count (.3 不存在)",
               not os.path.exists(cur + ".3"), cur + ".3")
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
    ok &= _log("S6.10c 所有代均无 markdown 正文", clean)
    rot = Path(cur + ".1").read_text(encoding="utf-8")
    ok &= _log("S6.10d 轮转中脱敏保留",
               "SUPERSECRET" not in rot and "abc123" not in rot and "<REDACTED>" in rot)
    return ok


# ---------------------------------------------------------------------------
# 11. Frozen resources
# ---------------------------------------------------------------------------
def _frozen_resources():
    if not getattr(sys, "frozen", False):
        _log("S6.11 magika 模型(源码运行跳过)", True, "source run")
        _log("S6.11b markitdown 可导入(源码运行跳过)", True, "source run")
        return
    model = os.path.join(os.path.dirname(sys.executable), "_internal", "magika",
                         "models", "standard_v3_3", "model.onnx")
    _log("S6.11 magika 模型已打包", os.path.exists(model), model)
    try:
        import markitdown  # noqa: F401
        _log("S6.11b markitdown 可导入(冻结)", True)
    except Exception as exc:  # noqa: BLE001
        _log("S6.11b markitdown 可导入(冻结)", False, str(exc))


def main():
    app = QApplication.instance() or QApplication([])
    w = MainWindow()
    # Ensure AI is off so no credential/MessageBox paths fire during batches.
    w._settings.ai.enabled = False

    ok = True
    ok &= _local_file_check(w)
    ok &= _batch_check(w)
    ok &= _url_check(w)
    ok &= _youtube_check(w)
    ok &= _streaminfo_check(w)
    ok &= _advanced_settings_check(w)
    ok &= _preview_copy_export_check(w)
    ok &= _quality_on_check(w)
    ok &= _diagnostics_ui_check(w)
    ok &= _log_rotation_check()
    _frozen_resources()

    w.close()
    all_ok = ok and all(o for _, o, _ in _OUT)
    print("RC_PASS" if all_ok else "RC_FAIL", flush=True)
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
