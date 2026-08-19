"""v0.5.0 model helpers for selected/retry batching.

Coverage:
  * retryable_rows() -> only ERROR / UNSUPPORTED rows, ascending.
  * done_rows() -> only DONE rows that carry non-empty markdown.
  * tasks_for_rows() -> (row, entry) pairs in ascending order, skipping
    invalid rows.
"""

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.file_entry import FileStatus
from src.file_model import FileModel


def _check(name, cond, detail=""):
    print(("PASS" if cond else "FAIL"), "-", name, "" if cond else f":: {detail}")
    assert cond, f"{name} :: {detail}"


def _build(d):
    """Four files whose rows are then manipulated by the tests."""
    names = ["a.txt", "b.txt", "c.txt", "d.txt"]
    for n in names:
        (Path(d) / n).write_text(n, encoding="utf-8")
    return names


def test_retryable_rows():
    m = FileModel()
    with tempfile.TemporaryDirectory() as d:
        _build(d)
        m.add_paths([str(Path(d) / n) for n in ("a.txt", "b.txt", "c.txt", "d.txt")])
        m.set_status(0, FileStatus.ERROR)
        m.set_status(1, FileStatus.UNSUPPORTED)
        m.set_status(2, FileStatus.DONE)
        # row 3 stays WAITING
        rows = m.retryable_rows()
        _check("1. retryable_rows 仅含 ERROR/UNSUPPORTED", rows == [0, 1], repr(rows))


def test_done_rows():
    m = FileModel()
    with tempfile.TemporaryDirectory() as d:
        _build(d)
        m.add_paths([str(Path(d) / n) for n in ("a.txt", "b.txt", "c.txt", "d.txt")])
        m.set_status(0, FileStatus.DONE)
        m.set_result(0, markdown="# a")          # DONE + markdown -> included
        m.set_status(1, FileStatus.DONE)         # DONE but NO markdown -> excluded
        m.set_status(2, FileStatus.ERROR)        # not DONE
        rows = m.done_rows()
        _check("2. done_rows 仅含 DONE 且有 markdown", rows == [0], repr(rows))


def test_tasks_for_rows_ascending_skips_invalid():
    m = FileModel()
    with tempfile.TemporaryDirectory() as d:
        _build(d)
        m.add_paths([str(Path(d) / n) for n in ("a.txt", "b.txt", "c.txt", "d.txt")])
        # Out-of-order input plus invalid rows (negative, out of range).
        tasks = m.tasks_for_rows([3, 0, 99, -1, 2])
        rows = [r for r, _ in tasks]
        _check("3. tasks_for_rows 升序且跳过无效行",
               rows == [0, 2, 3], repr(rows))
        _check("3b. (row, entry) 配对正确",
               all(tasks[i][1] is m.entry_at(tasks[i][0]) for i in range(len(tasks))),
               repr([(r, e.filename) for r, e in tasks]))
        _check("3c. 空输入 -> []", m.tasks_for_rows([]) == [])


def main():
    test_retryable_rows()
    test_done_rows()
    test_tasks_for_rows_ascending_skips_invalid()
    print()
    print("ALL SELECTED/RETRY TASKS CHECKS PASSED")
    sys.exit(0)


if __name__ == "__main__":
    main()
