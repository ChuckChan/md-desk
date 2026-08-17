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
from src.file_entry import FileStatus


def _check(name, cond, detail=""):
    print(("PASS" if cond else "FAIL"), "-", name, "" if cond else f":: {detail}")
    return cond


class _DummyEntry:
    """Stand-in for a FileEntry: the worker only forwards it to
    ``convert_entry``, which is fully mocked in these tests."""

    def __init__(self, path: str) -> None:
        self.path = path
        self.url = None


def _run(tasks, fake):
    """Run a worker to completion, flush queued signals, return collectors.

    The worker dispatches via ``src.converter.convert_entry`` (Stage 3+ API),
    so that is what we mock here.
    """
    app = QApplication.instance() or QApplication([])
    started, done, failed, progress = [], [], [], []
    w = ConversionWorker(tasks)
    w.file_started.connect(lambda r: started.append(r))
    w.file_done.connect(lambda r, m: done.append((r, m)))
    w.file_failed.connect(lambda r, s, e: failed.append((r, s, e)))
    w.progress.connect(lambda d, t: progress.append((d, t)))
    with patch("src.worker.convert_entry", side_effect=fake):
        w.start()
        w.wait()
    app.processEvents()
    return started, done, failed, progress


def test_sequential():
    tasks = [(0, _DummyEntry("a.html")), (1, _DummyEntry("b.html")), (2, _DummyEntry("c.html"))]

    def fake(entry, settings=None, **kwargs):
        return f"# {entry.path}"

    started, done, failed, progress = _run(tasks, fake)
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

    started, done, failed, progress = _run(tasks, fake)
    ok = True
    done_map = {r: FileStatus.DONE for r, _ in done}
    fail_map = {r: (FileStatus(s), e) for r, s, e in failed}
    ok &= _check("7. 状态 WAITING->PROCESSING->DONE", 0 in done_map and done_map[0] == FileStatus.DONE, f"{done_map}")
    ok &= _check("7b. UNSUPPORTED 映射", 1 in fail_map and fail_map[1][0] == FileStatus.UNSUPPORTED, f"{fail_map.get(1)}")
    ok &= _check("7c. ERROR 映射", 2 in fail_map and fail_map[2][0] == FileStatus.ERROR, f"{fail_map.get(2)}")
    return ok


def test_progress():
    tasks = [(i, _DummyEntry(f"f{i}.html")) for i in range(4)]

    def fake(entry, settings=None, **kwargs):
        return "# x"

    started, done, failed, progress = _run(tasks, fake)
    ok = True
    ok &= _check("10. 进度信号数量正确", len(progress) == 4, f"{len(progress)}")
    ok &= _check("10b. 末次进度 (总数,总数)", progress[-1] == (4, 4), f"{progress[-1]}")
    ok &= _check("10c. 进度单调递增", progress == [(1, 4), (2, 4), (3, 4), (4, 4)], f"{progress}")
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


def main():
    results = [test_sequential(), test_status_mapping(), test_progress(), test_no_model_or_widget_access()]
    ok = all(results)
    print()
    print("ALL WORKER CHECKS PASSED" if ok else "SOME WORKER CHECKS FAILED")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
