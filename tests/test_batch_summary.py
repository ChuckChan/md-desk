"""v0.5.0 batch_summary unit tests.

Pure-function suite: mixed-status counting, the quality-hints criterion (must
agree with FileModel.data's "完成 (质量提示)" display), duration_ms pass-through,
and summary_message contents in both normal and cancelled forms.
"""

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import Qt

from src.batch_summary import BatchSummary, summarize, summary_message
from src.file_entry import FileEntry, FileStatus
from src.file_model import FileModel


def _check(name, cond, detail=""):
    print(("PASS" if cond else "FAIL"), "-", name, "" if cond else f":: {detail}")
    assert cond, f"{name} :: {detail}"


class _WarnReport:
    """Minimal report stand-in: summarize only reads ``warnings``."""

    def __init__(self, warnings):
        self.warnings = warnings


def _entry(status, markdown=None, report=None):
    return FileEntry(
        path="/x.txt", filename="x.txt", extension=".txt", size=1,
        status=status, markdown=markdown, report=report,
    )


def test_mixed_counts():
    entries = [
        _entry(FileStatus.DONE, markdown="# ok"),
        _entry(FileStatus.DONE, markdown="# ok", report=_WarnReport(("w",))),
        _entry(FileStatus.ERROR),
        _entry(FileStatus.UNSUPPORTED),
        _entry(FileStatus.WAITING),
    ]
    s = summarize(entries, 1234)
    _check("1. 混合状态计数",
           (s.total, s.success, s.quality_hints, s.failed, s.unexecuted)
           == (5, 2, 1, 2, 1),
           f"total={s.total} success={s.success} hints={s.quality_hints} "
           f"failed={s.failed} unexecuted={s.unexecuted}")
    _check("2. duration_ms 原样", s.duration_ms == 1234, f"{s.duration_ms}")


def test_quality_hints_matches_model_display():
    """A DONE entry with non-empty report.warnings must count as a quality hint
    AND display as "完成 (质量提示)" in the model's status column — the two
    criteria must never drift apart."""
    entry = _entry(FileStatus.DONE, markdown="# x", report=_WarnReport(("w",)))
    s = summarize([entry], 0)
    _check("3. quality_hints == 1", s.quality_hints == 1 and s.success == 1,
           f"hints={s.quality_hints} success={s.success}")

    m = FileModel()
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "x.txt"
        p.write_text("x", encoding="utf-8")
        m.add_paths([str(p)])
        m.set_status(0, FileStatus.DONE)
        m.set_result(0, markdown="# x")
        m.set_report(0, _WarnReport(("w",)))
        shown = m.data(m.index(0, 3), Qt.ItemDataRole.DisplayRole)
        _check("3b. 模型状态列显示「完成 (质量提示)」", shown == "完成 (质量提示)", repr(shown))

    # A DONE entry with empty warnings must NOT be a quality hint.
    plain = _entry(FileStatus.DONE, markdown="# x", report=_WarnReport(()))
    s2 = summarize([plain], 0)
    _check("4. 无警告不计为质量提示", s2.quality_hints == 0, f"hints={s2.quality_hints}")


def test_done_but_no_markdown_not_quality_hint():
    # A DONE entry with report.warnings but empty markdown is still a success
    # and still a quality hint: summarize only checks status + warnings.
    entry = _entry(FileStatus.DONE, markdown=None, report=_WarnReport(("w",)))
    s = summarize([entry], 5)
    _check("5. 语义口径与模型一致(状态优先)",
           (s.success, s.quality_hints) == (1, 1),
           f"success={s.success} hints={s.quality_hints}")


def test_summary_message_contains_all_numbers():
    s = BatchSummary(total=5, success=2, quality_hints=1, failed=2,
                     unexecuted=1, duration_ms=1234)
    normal = summary_message(s)
    _check("6. 正常消息含头与全部数字",
           "转换完成" in normal and "共 5" in normal and "成功 2" in normal
           and "质量提示 1" in normal and "失败 2" in normal
           and "未执行 1" in normal and "1234" in normal,
           normal)
    cancelled = summary_message(s, cancelled=True)
    _check("7. 取消消息含头与全部数字",
           "已取消" in cancelled and "共 5" in cancelled and "成功 2" in cancelled
           and "质量提示 1" in cancelled and "失败 2" in cancelled
           and "未执行 1" in cancelled and "1234" in cancelled,
           cancelled)


def main():
    test_mixed_counts()
    test_quality_hints_matches_model_display()
    test_done_but_no_markdown_not_quality_hint()
    test_summary_message_contains_all_numbers()
    print()
    print("ALL BATCH SUMMARY CHECKS PASSED")
    sys.exit(0)


if __name__ == "__main__":
    main()
