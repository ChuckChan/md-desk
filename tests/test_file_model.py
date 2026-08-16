"""Stage 2 verification: file ingest closed loop.

Run:  python tests/test_file_model.py   (offscreen on headless hosts)
All 12 required checks are asserted; non-zero exit on any failure.
"""

import ast
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QPointF, QUrl, QMimeData, Qt
from PySide6.QtGui import QDropEvent
from PySide6.QtWidgets import QApplication, QSplitter

from src.file_entry import FileEntry, FileStatus
from src.file_model import FileModel
from src.main_window import FileTableView, MainWindow


def _make_file(directory: str, name: str, content: bytes = b"hello") -> str:
    p = Path(directory) / name
    p.write_bytes(content)
    return str(p)


results: list[tuple[str, bool, str]] = []


def check(name: str, cond, detail: str = "") -> None:
    ok = bool(cond)
    results.append((name, ok, detail))
    print(("PASS" if ok else "FAIL"), "-", name, "" if ok else f":: {detail}")


def test_add_single() -> None:
    m = FileModel()
    with tempfile.TemporaryDirectory() as d:
        f = _make_file(d, "a.txt")
        added, skipped = m.add_paths([f])
        check("1. 单文件添加", added == 1 and m.rowCount() == 1, f"added={added} count={m.rowCount()}")


def test_add_multi() -> None:
    m = FileModel()
    with tempfile.TemporaryDirectory() as d:
        added, _ = m.add_paths([_make_file(d, "a.txt"), _make_file(d, "b.pdf")])
        check("2. 多文件添加", added == 2 and m.rowCount() == 2, f"count={m.rowCount()}")


def test_dedup() -> None:
    m = FileModel()
    with tempfile.TemporaryDirectory() as d:
        f = _make_file(d, "a.txt")
        added, skipped = m.add_paths([f, f])
        check("3. 重复路径去重", added == 1 and skipped == 1 and m.rowCount() == 1,
              f"added={added} skip={skipped}")


def test_same_name_diff_path() -> None:
    m = FileModel()
    with tempfile.TemporaryDirectory() as d:
        d1, d2 = Path(d) / "x", Path(d) / "y"
        d1.mkdir(); d2.mkdir()
        added, _ = m.add_paths([_make_file(str(d1), "same.txt"), _make_file(str(d2), "same.txt")])
        check("4. 同名不同路径共存", added == 2 and m.rowCount() == 2, f"count={m.rowCount()}")


def test_metadata() -> None:
    m = FileModel()
    with tempfile.TemporaryDirectory() as d:
        m.add_paths([_make_file(d, "doc.PDF", b"12345")])
        e = m.entry_at(0)
        ok = (e.filename == "doc.PDF" and e.extension == ".pdf"
              and e.size == 5 and e.status == FileStatus.WAITING)
        check("5. 元数据正确", ok, f"name={e.filename} ext={e.extension} size={e.size} status={e.status}")


def test_remove() -> None:
    m = FileModel()
    with tempfile.TemporaryDirectory() as d:
        m.add_paths([_make_file(d, "a.txt"), _make_file(d, "b.txt")])
        m.removeRows(0, 1)
        e = m.entry_at(0)
        check("6. 删除选中项", m.rowCount() == 1 and e.filename == "b.txt",
              f"count={m.rowCount()} name={e.filename if e else None}")


def test_clear() -> None:
    m = FileModel()
    with tempfile.TemporaryDirectory() as d:
        m.add_paths([_make_file(d, "a.txt"), _make_file(d, "b.txt")])
        m.clear()
        check("7. 清空列表", m.rowCount() == 0 and len(m._paths) == 0, f"count={m.rowCount()}")


def test_invalid_and_dir() -> None:
    m = FileModel()
    with tempfile.TemporaryDirectory() as d:
        real = _make_file(d, "a.txt")
        added, skipped = m.add_paths([real, "C:/__no_such_file_xyz123.txt", d])
        check("8/9. 无效路径+文件夹忽略", added == 1 and skipped == 2 and m.rowCount() == 1,
              f"added={added} skip={skipped}")


def test_mime_drag() -> None:
    with tempfile.TemporaryDirectory() as d:
        f = _make_file(d, "dropped.txt")
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(f), QUrl.fromLocalFile(d)])  # file + dir
        extracted = FileTableView.extract_local_files(mime)
        norm = lambda x: os.path.normcase(os.path.abspath(x))
        check("10a. QMimeData+QUrl 提取(忽略文件夹)", extracted == [f] or [norm(x) for x in extracted] == [norm(f)],
              f"extracted={extracted} expected={f}")

        table = FileTableView()
        model = FileModel()
        table.setModel(model)
        table.files_dropped.connect(lambda paths: model.add_paths(paths))
        ev = QDropEvent(QPointF(0, 0), Qt.DropAction.CopyAction, mime,
                       Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
        table.dropEvent(ev)
        check("10b. 拖拽事件写入模型", model.rowCount() == 1 and model.entry_at(0).filename == "dropped.txt",
              f"count={model.rowCount()}")


def test_mainwindow_offscreen() -> None:
    app = QApplication.instance()
    w = MainWindow()
    w.show()
    app.processEvents()
    ok = (w.windowTitle() == "MdDesk"
          and isinstance(w.centralWidget(), QSplitter)
          and w._table.model() is w._model
          and "共 0 个文件" in w.statusBar().currentMessage())
    w.close()
    app.processEvents()
    check("11. MainWindow offscreen 正常", ok, f"status='{w.statusBar().currentMessage()}'")


def test_no_markitdown() -> None:
    from src import file_entry, file_model, main_window
    bad = []
    for mod in (file_entry, file_model, main_window):
        tree = ast.parse(Path(mod.__file__).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "markitdown" or alias.name.startswith("markitdown."):
                        bad.append(mod.__name__)
            elif isinstance(node, ast.ImportFrom):
                if node.module and (node.module == "markitdown" or node.module.startswith("markitdown.")):
                    bad.append(mod.__name__)
    check("12. 无 MarkItDown 调用", not bad, f"violations={bad}")


def main() -> None:
    QApplication.instance() or QApplication([])
    test_add_single()
    test_add_multi()
    test_dedup()
    test_same_name_diff_path()
    test_metadata()
    test_remove()
    test_clear()
    test_invalid_and_dir()
    test_mime_drag()
    test_mainwindow_offscreen()
    test_no_markitdown()

    failed = [r for r in results if not r[1]]
    print()
    print(f"TOTAL {len(results)} | PASS {len(results) - len(failed)} | FAIL {len(failed)}")
    if failed:
        print("FAILED:", [r[0] for r in failed])
        sys.exit(1)
    print("ALL STAGE 2 CHECKS PASSED")
    sys.exit(0)


if __name__ == "__main__":
    main()
