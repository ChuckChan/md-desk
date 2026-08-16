"""Stage 4 verification: result viewing (source + native preview).

Run: python tests/test_stage4.py
Covers requirements 1-8, and runs Stage 2/3 suites as a regression gate.
"""

import ast
import os
import subprocess
import sys
import tempfile
from itertools import count
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication
from src.main_window import MainWindow
from src.file_entry import FileStatus

_counter = count()


def _check(name, cond, detail=""):
    print(("PASS" if cond else "FAIL"), "-", name, "" if cond else f":: {detail}")
    return cond


def _add(w, content: bytes = b"x", status: FileStatus = FileStatus.DONE,
         markdown: str | None = None, error: str | None = None, ext: str = ".md") -> int:
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


def test_done_source():
    app = QApplication.instance() or QApplication([])
    w = MainWindow()
    row = _add(w, markdown="# Hello\n\nsome text")
    w._table.selectRow(row)
    src = w._source_view.toPlainText().replace("\r\n", "\n")
    prev = w._preview_view.toPlainText()
    ok = _check("1. DONE 源码正确", src == "# Hello\n\nsome text", repr(src))
    ok &= _check("1b. 预览含内容", "Hello" in prev, repr(prev))
    w.close()
    return ok


def test_native_preview():
    app = QApplication.instance() or QApplication([])
    w = MainWindow()
    md = "# Title\n\n- item1\n- item2\n\n**bold** text"
    row = _add(w, markdown=md)
    w._table.selectRow(row)
    html = w._preview_view.toHtml()
    ok = True
    ok &= _check("2. 标题渲染 <h", "<h" in html, "")
    ok &= _check("2b. 列表渲染 <li", "<li" in html, "")
    ok &= _check("2c. 粗体渲染(font-weight 呈现)",
                 "font-weight" in html and "bold" in w._preview_view.toPlainText(),
                 "Qt 以 font-weight span 渲染粗体，而非 <b>/<strong> 标签")
    # Document Qt's native table limitation (GFM tables are NOT rendered as <table>).
    table_md = "# T\n\n| a | b |\n|---|---|\n| 1 | 2 |\n"
    w._model.set_result(row, markdown=table_md)
    w._table.selectRow(row)
    table_html = w._preview_view.toHtml()
    ok &= _check("2d. 记录: GFM 表格未被渲染为 <table>",
                 "<table" not in table_html, "Qt 原生不渲染 GFM 表格（以原文显示）")
    w.close()
    return ok


def test_switch_sync():
    app = QApplication.instance() or QApplication([])
    w = MainWindow()
    r0 = _add(w, markdown="MARKDOWN_ZERO")
    r1 = _add(w, markdown="MARKDOWN_ONE")
    w._table.selectRow(r0)
    s0 = w._source_view.toPlainText()
    w._table.selectRow(r1)
    s1 = w._source_view.toPlainText()
    ok = _check("3. 切换文件内容同步", s0 == "MARKDOWN_ZERO" and s1 == "MARKDOWN_ONE", f"{s0!r}|{s1!r}")
    w.close()
    return ok


def test_error_states():
    app = QApplication.instance() or QApplication([])
    w = MainWindow()
    re_ = _add(w, status=FileStatus.ERROR, error="boom error msg")
    ru = _add(w, status=FileStatus.UNSUPPORTED, error="unsupported msg")
    w._table.selectRow(re_)
    ok = ("boom error msg" in w._source_view.toPlainText()
          and "boom error msg" in w._preview_view.toPlainText())
    w._table.selectRow(ru)
    ok &= ("unsupported msg" in w._source_view.toPlainText()
           and "unsupported msg" in w._preview_view.toPlainText())
    ok = _check("4. ERROR/UNSUPPORTED 显示 error_message", ok,
                f"src={w._source_view.toPlainText()!r}")
    w.close()
    return ok


def test_empty_states():
    app = QApplication.instance() or QApplication([])
    w = MainWindow()
    rw = _add(w, status=FileStatus.WAITING)
    rp = _add(w, status=FileStatus.PROCESSING)
    w._show_entry(rw)
    ok1 = w._source_view.toPlainText() == "等待转换"
    w._show_entry(rp)
    ok2 = w._source_view.toPlainText() == "转换中…"
    w._show_entry(None)
    ok3 = w._source_view.toPlainText() == "未选择文件"
    ok = _check("5. WAITING/PROCESSING/未选 空状态", ok1 and ok2 and ok3,
                f"wait={ok1} proc={ok2} none={ok3}")
    w.close()
    return ok


def test_auto_refresh():
    app = QApplication.instance() or QApplication([])
    w = MainWindow()
    r = _add(w, status=FileStatus.WAITING)
    w._table.selectRow(r)  # current_row = r, shows 等待转换
    assert w._current_row == r
    w._on_file_done(r, "REFRESHED_MD")
    ok = w._source_view.toPlainText() == "REFRESHED_MD"
    # failed variant
    r2 = _add(w, status=FileStatus.WAITING)
    w._table.selectRow(r2)
    w._on_file_failed(r2, FileStatus.ERROR.value, "AUTO_ERR")
    ok &= "AUTO_ERR" in w._source_view.toPlainText()
    ok = _check("6. 转换完成当前预览自动刷新", ok, w._source_view.toPlainText())
    w.close()
    return ok


def test_no_markdown_dep():
    bad = []
    for f in (ROOT / "src").glob("*.py"):
        tree = ast.parse(f.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for n in node.names:
                    if n.name == "markdown":
                        bad.append(f.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module == "markdown":
                    bad.append(f.name)
    ok = _check("7. 无第三方 markdown 依赖", not bad, f"{bad}")
    ok &= _check("7b. 使用 QTextBrowser.setMarkdown 原生渲染",
                 "setMarkdown" in (ROOT / "src" / "main_window.py").read_text(encoding="utf-8"))
    return ok


def test_regression():
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    suites = ["test_file_model.py", "test_converter.py", "test_worker.py", "test_stage3_integration.py"]
    ok = True
    for name in suites:
        r = subprocess.run([sys.executable, str(ROOT / "tests" / name)],
                           capture_output=True, text=True, env=env)
        ok &= _check(f"8. 回归 {name}", r.returncode == 0,
                     r.stdout.strip().splitlines()[-1] if r.stdout.strip() else r.stderr[-200:])
    return ok


def main():
    results = [
        test_done_source(),
        test_native_preview(),
        test_switch_sync(),
        test_error_states(),
        test_empty_states(),
        test_auto_refresh(),
        test_no_markdown_dep(),
        test_regression(),
    ]
    ok = all(results)
    print()
    print("ALL STAGE 4 CHECKS PASSED" if ok else "SOME STAGE 4 CHECKS FAILED")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
