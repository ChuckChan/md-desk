"""v0.5.0 FileModel.add_folder unit tests.

Model-level folder ingest: recursive add, dedup against existing entries,
within-batch dedup (same folder twice), invalid/empty-directory edge cases,
plus the add_paths-still-skips-directories regression.
"""

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.file_model import FileModel


def _check(name, cond, detail=""):
    print(("PASS" if cond else "FAIL"), "-", name, "" if cond else f":: {detail}")
    assert cond, f"{name} :: {detail}"


def _build_tree(d):
    sub = Path(d) / "sub"
    sub.mkdir()
    (Path(d) / "a.txt").write_text("a", encoding="utf-8")
    (Path(d) / "b.txt").write_text("b", encoding="utf-8")
    (sub / "c.txt").write_text("c", encoding="utf-8")


def test_add_folder_recursive():
    m = FileModel()
    with tempfile.TemporaryDirectory() as d:
        _build_tree(d)
        added, skipped = m.add_folder(d)
        names = sorted(m.entry_at(r).filename for r in range(m.rowCount()))
        _check("1. 递归添加含子目录文件",
               added == 3 and skipped == 0 and m.rowCount() == 3,
               f"added={added} skipped={skipped} count={m.rowCount()}")
        _check("1b. 条目文件名正确", names == ["a.txt", "b.txt", "c.txt"], repr(names))


def test_add_folder_dedup_existing():
    m = FileModel()
    with tempfile.TemporaryDirectory() as d:
        _build_tree(d)
        first, _ = m.add_paths([str(Path(d) / "a.txt")])
        added, skipped = m.add_folder(d)
        _check("2. 与既有条目去重",
               first == 1 and added == 2 and skipped == 1 and m.rowCount() == 3,
               f"added={added} skipped={skipped} count={m.rowCount()}")


def test_add_folder_twice_only_once():
    m = FileModel()
    with tempfile.TemporaryDirectory() as d:
        _build_tree(d)
        a1, s1 = m.add_folder(d)
        a2, s2 = m.add_folder(d)
        _check("3. 同一文件夹两次只加一次",
               (a1, s1) == (3, 0) and (a2, s2) == (0, 3) and m.rowCount() == 3,
               f"(a1,s1)={(a1,s1)} (a2,s2)={(a2,s2)} count={m.rowCount()}")


def test_add_folder_invalid_path():
    m = FileModel()
    _check("4. 无效路径 -> (0,1)", m.add_folder("C:/__no_such_dir_xyz_123") == (0, 1))
    _check("4b. 空字符串 -> (0,1)", m.add_folder("") == (0, 1))
    with tempfile.TemporaryDirectory() as d:
        f = Path(d) / "a.txt"
        f.write_text("x", encoding="utf-8")
        _check("4c. 文件路径(非目录) -> (0,1)", m.add_folder(str(f)) == (0, 1), str(f))
    _check("4d. 无效路径后模型未变", m.rowCount() == 0, f"count={m.rowCount()}")


def test_add_folder_empty_dir():
    m = FileModel()
    with tempfile.TemporaryDirectory() as d:
        empty = Path(d) / "empty"
        empty.mkdir()
        _check("5. 空目录 -> (0,0)", m.add_folder(str(empty)) == (0, 0), str(empty))
        _check("5b. 空目录非递归 -> (0,0)",
               m.add_folder(str(empty), recursive=False) == (0, 0))


def test_add_paths_still_skips_dirs():
    """Regression: the legacy add_paths entry point must keep ignoring
    directories even though add_folder now handles them explicitly."""
    m = FileModel()
    with tempfile.TemporaryDirectory() as d:
        _build_tree(d)
        f = str(Path(d) / "a.txt")
        added, skipped = m.add_paths([f, d, str(Path(d) / "sub")])
        _check("6. add_paths 仍跳过目录(回归)",
               added == 1 and skipped == 2 and m.rowCount() == 1,
               f"added={added} skipped={skipped} count={m.rowCount()}")


def main():
    test_add_folder_recursive()
    test_add_folder_dedup_existing()
    test_add_folder_twice_only_once()
    test_add_folder_invalid_path()
    test_add_folder_empty_dir()
    test_add_paths_still_skips_dirs()
    print()
    print("ALL FILE MODEL FOLDER CHECKS PASSED")
    sys.exit(0)


if __name__ == "__main__":
    main()
