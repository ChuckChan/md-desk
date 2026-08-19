"""v0.5.0 source-mode GUI smoke.

Drives a real MainWindow (offscreen QApplication) end-to-end with REAL
markitdown conversions (plain-text files only, no network). All file dialogs
are replaced via ``patch.object(QFileDialog, "getExistingDirectory", ...)``.

Flow covered:
  * folder ingest (model-level add_folder + toolbar _on_add_folder)
  * convert-selected (only the chosen row; neighbours stay WAITING)
  * full batch + retry-failed (ERROR/UNSUPPORTED rows re-run; DONE rows kept)
  * cooperative cancel (after the first file_finished) + batch summary
  * batch export (DONE rows only, content matches, sources untouched)

The batch-wait helper mirrors exe_stage6_rc_smoke.py::_run_batch: a
QEventLoop + QTimer.singleShot timeout + worker.batch_finished/batch_cancelled
connections + processEvents/sendPostedEvents flush. The worker is owned by
MainWindow and must NOT be deleteLater()-ed by the test.
"""

import os
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication, QFileDialog

from src.batch_summary import summary_message
from src.file_entry import FileStatus
from src.main_window import MainWindow


def _check(name, cond, detail=""):
    print(("PASS" if cond else "FAIL"), "-", name, "" if cond else f":: {detail}")
    assert cond, f"{name} :: {detail}"


def _run_batch(window, timeout_ms=90000):
    """Start the batch already running on ``window`` and wait for its end.

    Returns {"ok": bool, "cancelled": bool}. Completion is detected through
    the worker's own signals AND a watchdog on ``window._worker`` becoming
    None (the window's internal handler fires either way, so we never miss a
    batch that ended before we connected).
    """
    worker = window._worker
    assert worker is not None, "no batch was started"
    loop = QEventLoop()
    done = {"ok": False, "cancelled": False}

    def _on_finished(s, f):
        done["ok"] = True
        loop.quit()

    def _on_cancelled(s, f):
        done["ok"] = True
        done["cancelled"] = True
        loop.quit()

    worker.batch_finished.connect(_on_finished)
    worker.batch_cancelled.connect(_on_cancelled)

    watch = QTimer()

    def _watch():
        if window._worker is None:  # window._finish_batch already ran
            loop.quit()

    watch.timeout.connect(_watch)
    watch.start(20)
    QTimer.singleShot(timeout_ms, loop.quit)
    loop.exec()
    watch.stop()
    if not done["ok"] and window._worker is not None:
        raise AssertionError("batch did not finish within the timeout")
    # Flush any remaining queued signals (file_finished -> model updates).
    # NOTE: no worker.deleteLater() here — the worker is owned by MainWindow.
    app = QApplication.instance()
    app.processEvents()
    app.sendPostedEvents()
    return done


def _row_status(window, row):
    entry = window._model.entry_at(row)
    return entry.status if entry else None


def test_v05_gui_smoke(tmp):
    app = QApplication.instance() or QApplication([])

    window = MainWindow()
    # Keep the run offline & silent: no AI (avoids the OCR-plugin QMessageBox
    # in _start_batch), quality off (no warnings).
    window._settings.ai.enabled = False
    window._settings.quality_enabled = False

    # ---- fixture tree ---------------------------------------------------
    d = Path(tmp) / "src"
    (d / "sub").mkdir(parents=True)
    (d / "a.txt").write_text("content a", encoding="utf-8")
    (d / "b.txt").write_text("content b", encoding="utf-8")
    # Binary payload + unknown extension reliably maps to UNSUPPORTED in
    # markitdown 0.1.7 (text content in an unknown extension would instead
    # fall through to the plain-text converter and become DONE).
    (d / "bad.unknownext").write_bytes(b"\x00\x01\x02\x03\xff" * 40)
    (d / "sub" / "c.txt").write_text("content c", encoding="utf-8")
    d2 = Path(tmp) / "src2"
    d2.mkdir()
    (d2 / "d.txt").write_text("content d", encoding="utf-8")

    try:
        # ---- 1. folder ingest -------------------------------------------
        added, skipped = window._model.add_folder(str(d))
        _check("S1. add_folder 递归添加 4 个条目(含子目录文件)",
               added == 4 and skipped == 0 and window._model.rowCount() == 4,
               f"added={added} skipped={skipped} count={window._model.rowCount()}")
        names = [window._model.entry_at(r).filename for r in range(4)]
        _check("S1b. 条目为 a/b/bad/c(子目录)", names == ["a.txt", "b.txt", "bad.unknownext", "c.txt"],
               repr(names))

        with patch.object(QFileDialog, "getExistingDirectory",
                          staticmethod(lambda *a, **k: str(d2))):
            before = window._model.rowCount()
            window._on_add_folder()
            _check("S2. _on_add_folder 行数增加",
                   window._model.rowCount() == before + 1, f"{before} -> {window._model.rowCount()}")
            _check("S2b. 状态栏消息含新增/跳过",
                   "已添加文件夹" in window.statusBar().currentMessage()
                   and "新增 1 个文件" in window.statusBar().currentMessage(),
                   window.statusBar().currentMessage())

        # ---- 2. convert selected (row 0 only) ----------------------------
        window._table.selectRow(0)
        window._on_convert_selected()
        done = _run_batch(window)
        _check("S3. 转换选中批次正常结束", done["ok"] and not done["cancelled"], repr(done))
        _check("S3b. row0 DONE", _row_status(window, 0) == FileStatus.DONE,
               str(_row_status(window, 0)))
        _check("S3c. row1 仍 WAITING(未波及)", _row_status(window, 1) == FileStatus.WAITING,
               str(_row_status(window, 1)))
        _check("S3d. 转换选中摘要只统计批次行(total==1)",
               window._last_summary is not None and window._last_summary.total == 1
               and window._last_summary.success == 1,
               repr(window._last_summary))

        # ---- 3. full conversion + retry failed ---------------------------
        window.start_conversion()
        done = _run_batch(window)
        _check("S4. 全量转换结束", done["ok"] and not done["cancelled"], repr(done))
        _check("S4b. a/b/c/d DONE", all(_row_status(window, r) == FileStatus.DONE
                                        for r in (0, 1, 3, 4)),
               repr([str(_row_status(window, r)) for r in range(5)]))
        _check("S4c. bad UNSUPPORTED", _row_status(window, 2) == FileStatus.UNSUPPORTED,
               str(_row_status(window, 2)))

        window._on_retry_failed()
        done = _run_batch(window)
        _check("S5. 重试失败结束", done["ok"] and not done["cancelled"], repr(done))
        _check("S5b. bad 重置后重跑仍 UNSUPPORTED",
               _row_status(window, 2) == FileStatus.UNSUPPORTED,
               str(_row_status(window, 2)))
        _check("S5c. a/b/c/d 仍 DONE 未被重置",
               all(_row_status(window, r) == FileStatus.DONE for r in (0, 1, 3, 4)),
               repr([str(_row_status(window, r)) for r in range(5)]))

        # ---- 4. cooperative cancel + summary -----------------------------
        for i in range(5):
            p = Path(tmp) / f"new{i}.txt"
            p.write_text(f"new content {i}", encoding="utf-8")
            window._model.add_paths([str(p)])
        total = window._model.rowCount()
        _check("S6. 加 5 个文件后共 10 行", total == 10, f"total={total}")

        window.start_conversion()
        worker = window._worker
        loop = QEventLoop()
        cancelled = {"ok": False}
        first = {"seen": False}

        def _on_first_finished(result):
            first["seen"] = True
            window._on_cancel()  # cooperative: current file finishes, rest skipped

        worker.file_finished.connect(_on_first_finished)

        def _on_cancelled(s, f):
            cancelled["ok"] = True
            loop.quit()

        worker.batch_cancelled.connect(_on_cancelled)
        worker.batch_finished.connect(lambda s, f: loop.quit())  # safety net
        QTimer.singleShot(90000, loop.quit)
        loop.exec()
        app.processEvents()
        app.sendPostedEvents()

        _check("S7. 收到 batch_cancelled", cancelled["ok"] and first["seen"],
               f"cancelled={cancelled['ok']} first={first['seen']}")
        _check("S7b. 已完成者 DONE、其余 WAITING",
               _row_status(window, 0) == FileStatus.DONE
               and _row_status(window, 4) == FileStatus.DONE
               and all(_row_status(window, r) == FileStatus.WAITING for r in range(5, 10)),
               repr([str(_row_status(window, r)) for r in range(total)]))
        _check("S7c. 未执行批次 bad 仍 UNSUPPORTED",
               _row_status(window, 2) == FileStatus.UNSUPPORTED,
               str(_row_status(window, 2)))

        summary = window._last_summary
        _check("S8. _last_summary 非空且 total==rowCount",
               summary is not None and summary.total == window._model.rowCount(),
               f"total={summary.total if summary else None} rows={window._model.rowCount()}")
        waiting = sum(1 for r in range(window._model.rowCount())
                      if _row_status(window, r) == FileStatus.WAITING)
        _check("S8b. success+failed+unexecuted==total",
               summary.success + summary.failed + summary.unexecuted == summary.total,
               f"success={summary.success} failed={summary.failed} "
               f"unexecuted={summary.unexecuted} total={summary.total}")
        _check("S8c. unexecuted==WAITING 计数", summary.unexecuted == waiting,
               f"unexecuted={summary.unexecuted} waiting={waiting}")
        msg = summary_message(summary, cancelled=True)
        _check("S8d. summary_message 含全部数字",
               all(str(x) in msg for x in (summary.total, summary.success,
                                           summary.failed, summary.unexecuted,
                                           summary.duration_ms)),
               msg)

        # ---- 5. batch export --------------------------------------------
        out = Path(tmp) / "export"
        out.mkdir()
        source_before = {}
        for name in ("a.txt", "b.txt"):
            source_before[name] = (d / name).read_bytes()
        source_before["c.txt"] = (d / "sub" / "c.txt").read_bytes()
        source_before["d.txt"] = (d2 / "d.txt").read_bytes()

        done_rows = window._model.done_rows()
        _check("S9. 有 DONE 行可导出", len(done_rows) >= 4, repr(done_rows))
        with patch.object(QFileDialog, "getExistingDirectory",
                          staticmethod(lambda *a, **k: str(out))):
            window._on_export_batch()
        md_files = list(out.glob("*.md"))
        _check("S9b. 导出 .md 数量 == DONE 条目数",
               len(md_files) == len(done_rows),
               f"files={len(md_files)} done={len(done_rows)}")
        for row in done_rows:
            e = window._model.entry_at(row)
            target = out / (Path(e.filename).stem + ".md")
            _check(f"S9c. {e.filename} 导出内容与 markdown 一致",
                   target.exists() and target.read_text(encoding="utf-8") == e.markdown,
                   str(target))
        _check("S9d. 源文件未被覆盖",
               (d / "a.txt").read_bytes() == source_before["a.txt"]
               and (d / "b.txt").read_bytes() == source_before["b.txt"]
               and (d / "sub" / "c.txt").read_bytes() == source_before["c.txt"]
               and (d2 / "d.txt").read_bytes() == source_before["d.txt"])

        _check("S10. 状态栏含批量导出结果",
               "批量导出完成" in window.statusBar().currentMessage(),
               window.statusBar().currentMessage())
    finally:
        window.close()
        app.processEvents()


def main():
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        test_v05_gui_smoke(Path(d))
    print()
    print("ALL V0.5 GUI SMOKE CHECKS PASSED")
    sys.exit(0)


if __name__ == "__main__":
    main()
