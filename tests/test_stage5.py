"""Stage 5 verification: copy + export .md.

Run: python tests/test_stage5.py
Covers requirements 1-9, and runs Stage 2/3/4 suites as a regression gate.
"""

import os
import subprocess
import sys
import tempfile
from itertools import count
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication
from src import main_window
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


class _FakeClip:
    def __init__(self):
        self._t = ""
    def setText(self, text, mode=None):
        self._t = text
    def text(self, mode=None):
        return self._t


def test_copy_content():
    app = QApplication.instance() or QApplication([])
    w = MainWindow()
    md = "# 标题\n\n正文 **粗** `码`\n"
    row = _add(w, markdown=md)
    w._table.selectRow(row)
    clip = _FakeClip()
    with patch.object(main_window.QApplication, "clipboard", return_value=clip):
        w._on_copy()
    ok = _check("1. 复制内容完全等于 markdown", clip._t == md, repr(clip._t))
    w.close()
    return ok


def test_non_done_disabled():
    app = QApplication.instance() or QApplication([])
    w = MainWindow()
    rw = _add(w, status=FileStatus.WAITING)
    w._table.selectRow(rw)
    off_wait = not w._act_copy.isEnabled() and not w._act_export.isEnabled()
    re_ = _add(w, status=FileStatus.ERROR, error="x")
    w._table.selectRow(re_)
    off_err = not w._act_copy.isEnabled()
    rd = _add(w, markdown="# ok")
    w._table.selectRow(rd)
    on_done = w._act_copy.isEnabled() and w._act_export.isEnabled()
    ok = _check("2. 非 DONE 按钮禁用 / DONE 启用", off_wait and off_err and on_done,
                f"wait={off_wait} err={off_err} done={on_done}")
    w.close()
    return ok


def test_default_export_name():
    app = QApplication.instance() or QApplication([])
    w = MainWindow()
    row = _add(w, markdown="# x")
    w._table.selectRow(row)
    entry = w._model.entry_at(row)
    expected = Path(entry.filename).stem + ".md"
    captured = {}
    def fake_save(*args, **kwargs):
        captured["args"] = args
        return (str(Path(tempfile.mkdtemp()) / "out.md"), "")
    with patch.object(main_window.QFileDialog, "getSaveFileName", side_effect=fake_save):
        w._on_export()
    got = captured.get("args", [None, None, None])[2]
    ok = "args" in captured and got == expected
    ok = _check("3. 默认导出名 = 原名去扩展+.md", ok, f"default={got!r} expected={expected!r}")
    w.close()
    return ok


def test_utf8_export():
    app = QApplication.instance() or QApplication([])
    w = MainWindow()
    md = "# 中文标题\n\n正文 with emoji 🚀 and 表格 | a | b |\n"
    row = _add(w, markdown=md)
    w._table.selectRow(row)
    target = Path(tempfile.mkdtemp()) / "导出.md"
    with patch.object(main_window.QFileDialog, "getSaveFileName", return_value=(str(target), "")):
        w._on_export()
    ok = target.exists() and target.read_text(encoding="utf-8") == md
    ok = _check("4. UTF-8 导出正确", ok, f"exists={target.exists()}")
    w.close()
    return ok


def test_cancel_no_file():
    app = QApplication.instance() or QApplication([])
    w = MainWindow()
    row = _add(w, markdown="# x")
    w._table.selectRow(row)
    target = Path(tempfile.mkdtemp()) / "should_not_exist.md"
    with patch.object(main_window.QFileDialog, "getSaveFileName", return_value=("", "")):
        w._on_export()
    ok = _check("5. 用户取消不生成文件", not target.exists(), f"exists={target.exists()}")
    w.close()
    return ok


def test_write_error_handled():
    app = QApplication.instance() or QApplication([])
    w = MainWindow()
    row = _add(w, markdown="# x")
    w._table.selectRow(row)
    target = Path(tempfile.mkdtemp()) / "fail.md"
    criticals = []
    with patch.object(main_window.QFileDialog, "getSaveFileName", return_value=(str(target), "")), \
         patch.object(Path, "write_text", side_effect=OSError("disk full")), \
         patch.object(main_window.QMessageBox, "critical", side_effect=lambda *a, **k: criticals.append(a)):
        w._on_export()
    ok = len(criticals) >= 1 and not target.exists()
    ok = _check("6. 写入异常被捕获并提示", ok, f"criticals={len(criticals)} exists={target.exists()}")
    w.close()
    return ok


def test_no_overwrite_source():
    app = QApplication.instance() or QApplication([])
    w = MainWindow()
    # entry.path is a real temp file; exporting to that same path must be refused.
    row = _add(w, markdown="# new content")
    w._table.selectRow(row)
    entry = w._model.entry_at(row)
    with patch.object(main_window.QFileDialog, "getSaveFileName", return_value=(entry.path, "")):
        w._on_export()
    ok = "不能覆盖源文件" in w.statusBar().currentMessage()
    ok = _check("6b. 不覆盖源文件", ok, w.statusBar().currentMessage())
    w.close()
    return ok


def test_switch_state():
    app = QApplication.instance() or QApplication([])
    w = MainWindow()
    rw = _add(w, status=FileStatus.WAITING)
    rd = _add(w, markdown="# done")
    w._table.selectRow(rw)
    off = not w._act_copy.isEnabled()
    w._table.selectRow(rd)
    on = w._act_copy.isEnabled()
    ok = _check("7. 切换文件按钮状态正确", off and on, f"off={off} on={on}")
    w.close()
    return ok


def test_auto_enable_after_conversion():
    app = QApplication.instance() or QApplication([])
    w = MainWindow()
    r = _add(w, status=FileStatus.WAITING)
    w._table.selectRow(r)  # disabled while WAITING
    assert not w._act_copy.isEnabled()
    w._on_file_done(r, "# now done")
    ok = w._act_copy.isEnabled()
    ok = _check("8. 转换完成按钮自动启用", ok, f"enabled={w._act_copy.isEnabled()}")
    w.close()
    return ok


def test_regression():
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    suites = ["test_file_model.py", "test_converter.py", "test_worker.py",
              "test_stage3_integration.py", "test_stage4.py"]
    ok = True
    for name in suites:
        r = subprocess.run([sys.executable, str(ROOT / "tests" / name)],
                           capture_output=True, text=True, env=env)
        last = (r.stdout.strip().splitlines() or [""])[-1]
        ok &= _check(f"9. 回归 {name}", r.returncode == 0, last if r.returncode == 0 else r.stderr[-200:])
    return ok


def main():
    results = [
        test_copy_content(),
        test_non_done_disabled(),
        test_default_export_name(),
        test_utf8_export(),
        test_cancel_no_file(),
        test_write_error_handled(),
        test_no_overwrite_source(),
        test_switch_state(),
        test_auto_enable_after_conversion(),
        test_regression(),
    ]
    ok = all(results)
    print()
    print("ALL STAGE 5 CHECKS PASSED" if ok else "SOME STAGE 5 CHECKS FAILED")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
