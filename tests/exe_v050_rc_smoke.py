"""Frozen-binary RC smoke for MdDesk v0.5.0 (batch productivity).

Headless (offscreen). Drives the real MainWindow + worker + v0.5 batch
features. Complements tests/test_v05_gui_smoke.py (source-mode pytest) by
running the SAME v0.5 feature matrix inside the PyInstaller-frozen EXE.

Coverage (all offline-safe; network paths not exercised):

  * Boot MainWindow offscreen (frozen + source)
  * Folder import: model.add_folder recursive (+ non-recursive), dedup,
    invalid path; FileTableView.extract_local_files now keeps directories
  * Convert-selected: only selected rows convert; others untouched
  * Retry-failed: ERROR/UNSUPPORTED rows reset + re-run; DONE rows untouched
  * Cooperative cancel: current file finishes, remaining stay WAITING,
    batch_cancelled fired, _last_summary counts consistent
  * Batch export: export_batch via _on_export_batch (dialog mocked) writes
    .md files, never overwrites source files
  * Batch summary: summary_message contains all real counts
  * Regression: local file real MarkItDown -> DONE; quality OFF (default)
    -> no warnings
  * Frozen-only: markitdown importable from the frozen PYZ

Run both as a source script (frozen-only checks skipped) and as a frozen EXE.
"""

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
if not getattr(sys, "frozen", False):
    # Source-mode only: make the local `src` package importable. In frozen mode
    # `src` is collected into the PYZ archive by the spec; inserting ROOT here
    # must be avoided so it cannot shadow the frozen import graph.
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from PySide6.QtCore import QEventLoop, QMimeData, QTimer, QUrl  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from src.batch_summary import summarize, summary_message  # noqa: E402
from src.export_service import export_batch  # noqa: E402
from src.file_entry import FileStatus  # noqa: E402
from src.file_model import FileModel  # noqa: E402
from src.main_window import FileTableView, MainWindow  # noqa: E402
from src.worker import ConversionWorker  # noqa: E402

_OUT = []


def _log(name, ok, detail=""):
    _OUT.append((name, ok, detail))
    print(("PASS" if ok else "FAIL"), "-", name, "" if ok else f":: {detail}", flush=True)
    return ok


def _wait_batch_done(window, timeout_ms=60000):
    """Wait until MainWindow's worker has been torn down (batch finished OR
    cancelled). Returns True if it ended in time."""
    app = QApplication.instance()
    loop = QEventLoop()

    def _poll():
        if window._worker is None:
            loop.quit()

    timer = QTimer()
    timer.timeout.connect(_poll)
    timer.start(50)
    QTimer.singleShot(timeout_ms, loop.quit)
    loop.exec()
    timer.stop()
    app.processEvents()
    app.sendPostedEvents()
    return window._worker is None


def _wait_first_finished(window, timeout_ms=60000):
    """Wait for the worker's first file_finished. Returns the ConversionResult
    or None on timeout."""
    worker = window._worker
    if worker is None:
        return None
    got = {"res": None}
    loop = QEventLoop()

    def _on(res):
        if got["res"] is None:
            got["res"] = res
        loop.quit()

    worker.file_finished.connect(_on)
    QTimer.singleShot(timeout_ms, loop.quit)
    loop.exec()
    return got["res"]


# ---------------------------------------------------------------------------
# 1. Folder import
# ---------------------------------------------------------------------------
def _folder_import_check(w):
    d = tempfile.mkdtemp()
    (Path(d) / "a.txt").write_text("# A\n\ncontent a\n", encoding="utf-8")
    (Path(d) / "b.txt").write_text("# B\n\ncontent b\n", encoding="utf-8")
    sub = Path(d) / "sub"
    sub.mkdir()
    (sub / "c.txt").write_text("# C\n\ncontent c\n", encoding="utf-8")

    ok = _log("V5.1 递归 add_folder 收集嵌套文件",
              w._model.add_folder(d) == (3, 0),
              f"{w._model.rowCount()}")
    # dedup: adding the same folder again adds nothing
    ok &= _log("V5.1b 同文件夹重复添加去重",
               w._model.add_folder(d) == (0, 3), f"{w._model.rowCount()}")
    # non-recursive: a fresh dir with a top file + a nested file
    d2 = tempfile.mkdtemp()
    (Path(d2) / "top.txt").write_text("t", encoding="utf-8")
    (Path(d2) / "nest").mkdir()
    (Path(d2) / "nest" / "deep.txt").write_text("x", encoding="utf-8")
    ok &= _log("V5.1c 非递归只取直接子文件",
               w._model.add_folder(d2, recursive=False) == (1, 0),
               f"{w._model.rowCount()}")
    ok &= _log("V5.1d 无效路径 -> (0,1)",
               w._model.add_folder(str(Path(d) / "nope")) == (0, 1))
    ok &= _log("V5.1e 空目录 -> (0,0)",
               w._model.add_folder(tempfile.mkdtemp()) == (0, 0))
    # drag-drop extraction keeps directories (v0.5 behavior change)
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(d), QUrl.fromLocalFile(str(Path(d) / "a.txt"))])
    extracted = FileTableView.extract_local_files(mime)
    ok &= _log("V5.1f extract_local_files 保留目录+文件",
               any(os.path.isdir(p) for p in extracted) and any(os.path.isfile(p) for p in extracted),
               repr(extracted))
    w._model.clear()
    return ok


# ---------------------------------------------------------------------------
# 2. Convert-selected
# ---------------------------------------------------------------------------
def _convert_selected_check(w):
    d = tempfile.mkdtemp()
    p1 = Path(d) / "sel1.txt"
    p2 = Path(d) / "sel2.txt"
    p3 = Path(d) / "skip.txt"
    p1.write_text("# S1\n\nbody\n", encoding="utf-8")
    p2.write_text("# S2\n\nbody\n", encoding="utf-8")
    p3.write_text("# SK\n\nbody\n", encoding="utf-8")
    w._model.add_paths([str(p1), str(p2), str(p3)])
    w._table.selectRow(0)
    w._on_convert_selected()
    if not _wait_batch_done(w):
        return _log("V5.2 转换选中批次结束", False, "timeout")
    e0 = w._model.entry_at(0)
    e2 = w._model.entry_at(2)
    ok = _log("V5.2a 选中行0 转换 DONE",
              e0 is not None and e0.status == FileStatus.DONE and bool(e0.markdown),
              e0.status.value if e0 else "none")
    ok &= _log("V5.2b 未选中行2 保持 WAITING",
               e2 is not None and e2.status == FileStatus.WAITING,
               e2.status.value if e2 else "none")
    ok &= _log("V5.2c 选中行1 保持 WAITING",
               w._model.entry_at(1).status == FileStatus.WAITING)
    w._model.clear()
    return ok


# ---------------------------------------------------------------------------
# 3. Retry-failed
# ---------------------------------------------------------------------------
def _retry_failed_check(w):
    d = tempfile.mkdtemp()
    good = Path(d) / "ok.txt"
    good.write_text("# OK\n\nbody\n", encoding="utf-8")
    bad = Path(d) / "bad.unknownext"
    bad.write_bytes(b"\x00\x01\x02\xff\xfe\x00\x01")  # binary -> UNSUPPORTED
    w._model.add_paths([str(good), str(bad)])
    w.start_conversion()
    if not _wait_batch_done(w):
        return _log("V5.3 全量批次结束", False, "timeout")
    ok = _log("V5.3a 好文件 DONE / 坏文件 UNSUPPORTED",
              w._model.entry_at(0).status == FileStatus.DONE
              and w._model.entry_at(1).status == FileStatus.UNSUPPORTED,
              f"{w._model.entry_at(0).status.value}/{w._model.entry_at(1).status.value}")
    w._on_retry_failed()
    if not _wait_batch_done(w):
        return _log("V5.3 重试批次结束", False, "timeout")
    ok &= _log("V5.3b 重试只重置 ERROR/UNSUPPORTED 行",
               w._model.entry_at(1).status == FileStatus.UNSUPPORTED
               and w._model.entry_at(0).status == FileStatus.DONE,
               f"{w._model.entry_at(0).status.value}/{w._model.entry_at(1).status.value}")
    ok &= _log("V5.3c 重试后 DONE 行未被重置(仍带 markdown)",
               bool(w._model.entry_at(0).markdown))
    w._model.clear()
    return ok


# ---------------------------------------------------------------------------
# 4. Cooperative cancel + batch summary
# ---------------------------------------------------------------------------
def _cancel_summary_check(w):
    d = tempfile.mkdtemp()
    files = []
    for i in range(6):
        p = Path(d) / f"c{i}.txt"
        p.write_text(f"# C{i}\n\nbody\n", encoding="utf-8")
        files.append(str(p))
    w._model.add_paths(files)
    w.start_conversion()
    first = _wait_first_finished(w)
    if first is None:
        return _log("V5.4 首个文件结束", False, "timeout")
    w._on_cancel()
    if not _wait_batch_done(w):
        return _log("V5.4 取消批次结束", False, "timeout")
    rows = [w._model.entry_at(r) for r in range(w._model.rowCount())]
    done = sum(1 for e in rows if e.status == FileStatus.DONE)
    waiting = sum(1 for e in rows if e.status == FileStatus.WAITING)
    summary = w._last_summary
    ok = _log("V5.4a 取消后存在 DONE 与 WAITING",
              done >= 1 and waiting >= 1, f"done={done} waiting={waiting}")
    ok &= _log("V5.4b batch summary total==rowCount",
               summary is not None and summary.total == w._model.rowCount(),
               repr(summary))
    ok &= _log("V5.4c success+failed+unexecuted==total",
               summary is not None and summary.success + summary.failed + summary.unexecuted == summary.total,
               repr(summary))
    ok &= _log("V5.4d unexecuted==WAITING 计数",
               summary is not None and summary.unexecuted == waiting,
               f"unexecuted={summary.unexecuted} waiting={waiting}")
    ok &= _log("V5.4e 取消消息含全部数字",
               summary is not None and "已取消" in summary_message(summary, cancelled=True)
               and str(summary.total) in summary_message(summary, cancelled=True),
               summary_message(summary, cancelled=True))
    w._model.clear()
    return ok


# ---------------------------------------------------------------------------
# 5. Batch export
# ---------------------------------------------------------------------------
def _batch_export_check(w):
    d = tempfile.mkdtemp()
    out = tempfile.mkdtemp()
    p1 = Path(d) / "doc1.txt"
    p2 = Path(d) / "doc2.txt"
    p1.write_text("# D1\n\nhello one\n", encoding="utf-8")
    p2.write_text("# D2\n\nhello two\n", encoding="utf-8")
    w._model.add_paths([str(p1), str(p2)])
    w.start_conversion()
    if not _wait_batch_done(w):
        return _log("V5.5 导出前批次结束", False, "timeout")
    with patch("src.main_window.QFileDialog.getExistingDirectory", return_value=out):
        w._on_export_batch()
    written = sorted(out_dir_file.name for out_dir_file in Path(out).iterdir())
    ok = _log("V5.5a 批量导出写出 2 个 .md",
              sorted(written) == ["doc1.md", "doc2.md"], repr(written))
    ok &= _log("V5.5b 导出内容与 markdown 一致",
               (Path(out) / "doc1.md").read_text(encoding="utf-8").strip() == "# D1\n\nhello one".strip())
    ok &= _log("V5.5c 源文件未被覆盖",
               p1.read_text(encoding="utf-8") == "# D1\n\nhello one\n"
               and p2.read_text(encoding="utf-8") == "# D2\n\nhello two\n")
    ok &= _log("V5.5d 导出目录非源目录(源文件仍存在)",
               p1.exists() and p2.exists())
    # conflict-skip: a source .md exported into its OWN dir must be skipped
    # (target == source path -> never overwrite an input file).
    raw = Path(d) / "raw.md"
    raw.write_text("# RAW\n\nkeep me\n", encoding="utf-8")
    w._model.add_paths([str(raw)])
    w.start_conversion()
    if not _wait_batch_done(w):
        return _log("V5.5 冲突批次结束", False, "timeout")
    res = export_batch([w._model.entry_at(r) for r in range(w._model.rowCount())], d)
    ok &= _log("V5.5e 目标==源文件 -> skipped_conflict 且不覆盖",
               res.skipped_conflict == 1 and res.exported == 2
               and raw.read_text(encoding="utf-8") == "# RAW\n\nkeep me\n",
               repr(res))
    w._model.clear()
    return ok


# ---------------------------------------------------------------------------
# 6. Regression: local file real MarkItDown + quality OFF default
# ---------------------------------------------------------------------------
def _regression_check(w):
    d = tempfile.mkdtemp()
    p = Path(d) / "note.txt"
    p.write_text("# Title\n\nSome real content.\n", encoding="utf-8")
    w._model.add_paths([str(p)])
    w.start_conversion()
    if not _wait_batch_done(w):
        return _log("V5.6 回归批次结束", False, "timeout")
    entry = w._model.entry_at(0)
    ok = _log("V5.6a 本地文件真实转换 DONE",
              entry is not None and entry.status == FileStatus.DONE and bool(entry.markdown),
              entry.status.value if entry else "none")
    ok &= _log("V5.6b 默认 quality OFF -> 无警告",
               entry is not None and entry.report is not None and entry.report.warnings == (),
               repr(entry.report.warnings if entry and entry.report else None))
    # pure helper regression
    s = summarize([entry], 123)
    ok &= _log("V5.6c summarize 单条计数",
               s.total == 1 and s.success == 1 and s.unexecuted == 0 and s.duration_ms == 123,
               repr(s))
    w._model.clear()
    return ok


# ---------------------------------------------------------------------------
# 7. Frozen-only checks
# ---------------------------------------------------------------------------
def _frozen_check():
    ok = True
    if getattr(sys, "frozen", False):
        try:
            import markitdown  # noqa: F401

            ok = _log("V5.7 冻结 EXE 内 markitdown 可导入", True)
        except Exception as exc:  # noqa: BLE001
            ok = _log("V5.7 冻结 EXE 内 markitdown 可导入", False, repr(exc))
    else:
        _log("V5.7 源码模式跳过 frozen-only 检查", True)
    return ok


def main():
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    results = [
        _folder_import_check(window),
        _convert_selected_check(window),
        _retry_failed_check(window),
        _cancel_summary_check(window),
        _batch_export_check(window),
        _regression_check(window),
        _frozen_check(),
    ]
    ok = all(results)
    print()
    print("ALL V0.5.0 RC CHECKS PASSED" if ok else "SOME V0.5.0 RC CHECKS FAILED")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
