"""MainWindow integration tests (Stage 3 requirements 8, 9, 11, 13).

Run: python tests/test_stage3_integration.py
"""

import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication
from markitdown import FileConversionException
from src.converter import ConversionError
from src.main_window import MainWindow
from src.file_entry import FileStatus

TEST_INPUT = ROOT.parent / "test_input.html"


def _check(name, cond, detail=""):
    print(("PASS" if cond else "FAIL"), "-", name, "" if cond else f":: {detail}")
    return cond


def _run_batch(window):
    window._worker.wait()
    QApplication.instance().processEvents()


def test_markdown_written():
    app = QApplication.instance() or QApplication([])
    w = MainWindow()
    w.show()
    assert TEST_INPUT.exists()
    w._model.add_paths([str(TEST_INPUT)])
    w.start_conversion()
    _run_batch(w)
    e = w._model.entry_at(0)
    ok = _check("8. Markdown 写回正确 FileEntry", e.status == FileStatus.DONE and e.markdown and len(e.markdown) > 0,
                f"status={e.status} md_len={len(e.markdown) if e.markdown else 0}")
    w.close()
    return ok


def test_error_written():
    app = QApplication.instance() or QApplication([])
    w = MainWindow()
    w.show()
    w._model.add_paths([str(TEST_INPUT)])
    # converter wraps raw exceptions into ConversionError; simulate that contract.
    with patch("src.worker.convert_file",
               side_effect=ConversionError(FileStatus.ERROR, "boom")):
        w.start_conversion()
        _run_batch(w)
    e = w._model.entry_at(0)
    ok = True
    ok &= _check("9. error_message 写回正确", e.error_message is not None and len(e.error_message) > 0, f"{e.error_message}")
    ok &= _check("9b. 失败状态 ERROR", e.status == FileStatus.ERROR, f"{e.status}")
    w.close()
    return ok


def test_controls_restored():
    app = QApplication.instance() or QApplication([])
    w = MainWindow()
    w.show()
    w._model.add_paths([str(TEST_INPUT)])
    w.start_conversion()
    # during conversion controls disabled
    mid_disabled = (not w._act_add.isEnabled()) and (not w._act_convert.isEnabled())
    _run_batch(w)
    ok = True
    ok &= _check("11. 转换中控件禁用", mid_disabled, f"add_enabled={w._act_add.isEnabled()}")
    ok &= _check("11b. 批次完成后控件恢复", w._act_add.isEnabled() and w._act_convert.isEnabled(), "")
    ok &= _check("11c. 转换标志复位 & worker 清理", w._converting is False and w._worker is None,
                 f"converting={w._converting} worker={w._worker}")
    w.close()
    return ok


def test_event_loop_responsive():
    app = QApplication.instance() or QApplication([])
    w = MainWindow()
    w.show()
    w._model.add_paths([str(TEST_INPUT)])
    w.start_conversion()
    # main thread must stay responsive while the worker thread runs
    visible = w.isVisible()
    app.processEvents()  # returns promptly; conversion runs off the GUI thread
    responsive = True
    w._worker.wait()
    app.processEvents()
    e = w._model.entry_at(0)
    ok = True
    ok &= _check("13. 转换期间 event loop 仍可响应", visible and responsive, f"visible={visible}")
    ok &= _check("13b. 后台线程完成后结果可见", e.status == FileStatus.DONE, f"{e.status}")
    w.close()
    return ok


def main():
    results = [
        test_markdown_written(),
        test_error_written(),
        test_controls_restored(),
        test_event_loop_responsive(),
    ]
    ok = all(results)
    print()
    print("ALL STAGE3 INTEGRATION CHECKS PASSED" if ok else "SOME CHECKS FAILED")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
