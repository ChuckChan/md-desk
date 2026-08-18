"""Worker unit tests (Stage 3 requirements 6, 7, 10, 12).

Run: python tests/test_worker.py
"""

import ast
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication

from markitdown import UnsupportedFormatException, FileConversionException
from src.converter import ConversionError
from src.worker import ConversionWorker
from src.result import ConversionResult, QualityWarning
from src.file_entry import FileStatus


def _check(name, cond, detail=""):
    print(("PASS" if cond else "FAIL"), "-", name, "" if cond else f":: {detail}")
    return cond


class _DummyEntry:
    """Stand-in for a FileEntry: the worker only forwards it to
    ``convert_entry``, which is fully mocked in these tests."""

    def __init__(self, path: str, size: int = 0) -> None:
        self.path = path
        self.url = None
        self.size = size


def _run(tasks, fake, quality_enabled: bool = False):
    """Run a worker to completion, flush queued signals, return collectors.

    The worker dispatches via ``src.converter.convert_entry`` (Stage 3+ API),
    so that is what we mock here. ``quality_enabled`` drives the Stage 2
    QualityInspector path.
    """
    app = QApplication.instance() or QApplication([])
    started, finished, progress = [], [], []
    w = ConversionWorker(tasks, quality_enabled=quality_enabled)
    w.file_started.connect(lambda r: started.append(r))
    w.file_finished.connect(lambda res: finished.append(res))
    w.progress.connect(lambda d, t: progress.append((d, t)))
    with patch("src.worker.convert_entry", side_effect=fake):
        w.start()
        w.wait()
    # Stage 5: fully destroy the worker object so its QThread / OS thread
    # handle does not linger in the parent pytest process (root cause of the
    # Windows subprocess pipe-EOF deadlock when later tests spawn children).
    w.deleteLater()
    app.processEvents()
    app.sendPostedEvents()
    return started, finished, progress


def test_sequential():
    tasks = [(0, _DummyEntry("a.html")), (1, _DummyEntry("b.html")), (2, _DummyEntry("c.html"))]

    def fake(entry, settings=None, **kwargs):
        return f"# {entry.path}"

    started, finished, progress = _run(tasks, fake)
    done = [res for res in finished if res.ok]
    failed = [res for res in finished if not res.ok]
    ok = True
    ok &= _check("6. 按顺序处理 (started 顺序)", started == [0, 1, 2], f"{started}")
    ok &= _check("6b. 全部成功完成", len(done) == 3 and len(failed) == 0, f"done={len(done)} failed={len(failed)}")
    return ok


def test_status_mapping():
    tasks = [(0, _DummyEntry("ok.html")), (1, _DummyEntry("bad.unknown")), (2, _DummyEntry("err.pdf"))]

    def fake(entry, settings=None, **kwargs):
        # Mimic converter.convert_entry's contract: raise ConversionError
        # (the real converter wraps raw markitdown exceptions itself).
        if entry.path.endswith("unknown"):
            raise ConversionError(FileStatus.UNSUPPORTED, "不支持")
        if entry.path.endswith("err.pdf"):
            raise ConversionError(FileStatus.ERROR, "bad")
        return "# ok"

    started, finished, progress = _run(tasks, fake)
    ok = True
    done_map = {res.row: res.status for res in finished if res.ok}
    fail_map = {res.row: (res.status, res.error_message) for res in finished if not res.ok}
    ok &= _check("7. 状态 WAITING->PROCESSING->DONE", 0 in done_map and done_map[0] == FileStatus.DONE, f"{done_map}")
    ok &= _check("7b. UNSUPPORTED 映射", 1 in fail_map and fail_map[1][0] == FileStatus.UNSUPPORTED, f"{fail_map.get(1)}")
    ok &= _check("7c. ERROR 映射", 2 in fail_map and fail_map[2][0] == FileStatus.ERROR, f"{fail_map.get(2)}")
    return ok


def test_progress():
    tasks = [(i, _DummyEntry(f"f{i}.html")) for i in range(4)]

    def fake(entry, settings=None, **kwargs):
        return "# x"

    started, finished, progress = _run(tasks, fake)
    ok = True
    ok &= _check("10. 进度信号数量正确", len(progress) == 4, f"{len(progress)}")
    ok &= _check("10b. 末次进度 (总数,总数)", progress[-1] == (4, 4), f"{progress[-1]}")
    ok &= _check("10c. 进度单调递增", progress == [(1, 4), (2, 4), (3, 4), (4, 4)], f"{progress}")
    return ok


def test_duration_ms_nonneg():
    """Stage 1: every emitted ConversionResult carries a real, non-negative
    duration_ms computed from perf_counter() (see src/worker._elapsed_ms)."""
    tasks = [(i, _DummyEntry(f"f{i}.html")) for i in range(3)]

    def fake(entry, settings=None, **kwargs):
        return "# x"

    started, finished, progress = _run(tasks, fake)
    ok = True
    ok &= _check("11. 收到 3 个终态结果", len(finished) == 3, f"{len(finished)}")
    for i, res in enumerate(finished):
        ok &= _check(f"11b. 结果[{i}] duration_ms >= 0", res.duration_ms >= 0, f"{res.duration_ms}")
    return ok


def test_no_model_or_widget_access():
    src = Path(ROOT / "src" / "worker.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    bad = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for n in node.names:
                if n.name.split(".")[0] in ("file_model", "main_window"):
                    bad.append(n.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.module.split(".")[-1] in ("file_model", "main_window"):
                bad.append(node.module)
    ok = _check("12. Worker 不 import FileModel/Widget", not bad, f"{bad}")
    # also must not reference the FileModel class or call set_status
    # (docstring mentions are ignored by scanning AST nodes only).
    refs = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id == "FileModel":
            refs.append("FileModel")
        if isinstance(node, ast.Attribute) and node.attr == "set_status":
            refs.append("set_status")
    ok &= _check("12b. Worker 不引用 FileModel/set_status", not refs, f"{refs}")
    return ok


def test_quality_off_no_warnings():
    """Stage 2 (default OFF): even a large input producing tiny output must
    yield NO warnings, so a v0.3 / S1 conversion is byte-for-byte unchanged."""
    tasks = [(i, _DummyEntry(f"big{i}.pdf", size=60000)) for i in range(3)]

    def fake(entry, settings=None, **kwargs):
        return "x"  # tiny output, would trigger LOW_TEXT_YIELD if quality ON

    started, finished, progress = _run(tasks, fake)  # quality_enabled default False
    ok = True
    ok &= _check("QOFF. 发出 3 个结果", len(finished) == 3, f"{len(finished)}")
    for i, res in enumerate(finished):
        ok &= _check(f"QOFF[{i}] 默认关闭时无 warnings", res.warnings == (), repr(res.warnings))
    return ok


def test_quality_on_detects():
    """Stage 2 (ON): a large input with tiny output must be flagged with
    LOW_TEXT_YIELD; the status stays DONE and markdown is untouched."""
    tasks = [(0, _DummyEntry("big.pdf", size=60000))]

    def fake(entry, settings=None, **kwargs):
        return "x"

    started, finished, progress = _run(tasks, fake, quality_enabled=True)
    ok = True
    ok &= _check("QON. 发出 1 个结果", len(finished) == 1, f"{len(finished)}")
    if finished:
        res = finished[0]
        codes = {w.code for w in res.warnings}
        ok &= _check("QON. 大输入+极少文本 -> LOW_TEXT_YIELD", "LOW_TEXT_YIELD" in codes, repr(codes))
        # Quality is advisory: success state + markdown preserved.
        ok &= _check("QON. 状态仍为 DONE", res.ok is True)
        ok &= _check("QON. Markdown 未被修改", res.markdown == "x")
        ok &= _check("QON. warnings 为 QualityWarning 元组",
                     isinstance(res.warnings, tuple)
                     and all(isinstance(w, QualityWarning) for w in res.warnings))
    return ok


def main():
    results = [test_sequential(), test_status_mapping(), test_progress(),
               test_duration_ms_nonneg(), test_no_model_or_widget_access(),
               test_quality_off_no_warnings(), test_quality_on_detects()]
    ok = all(results)
    print()
    print("ALL WORKER CHECKS PASSED" if ok else "SOME WORKER CHECKS FAILED")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
