"""v0.5.0 folder_scanner.collect_files unit tests.

Pure-function suite (no Qt, no markitdown): recursive / non-recursive
collection, deterministic ordering, directory exclusion, invalid-path and
empty-directory behavior.
"""

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.folder_scanner import collect_files


def _check(name, cond, detail=""):
    print(("PASS" if cond else "FAIL"), "-", name, "" if cond else f":: {detail}")
    assert cond, f"{name} :: {detail}"


def _rel(files, base):
    """Relative (os path separators normalized) paths under ``base``."""
    return [os.path.relpath(p, base) for p in files]


def _build_tree(d):
    """a.txt + b.txt at top, sub/c.txt nested."""
    sub = Path(d) / "sub"
    sub.mkdir()
    (Path(d) / "a.txt").write_text("a", encoding="utf-8")
    (Path(d) / "b.txt").write_text("b", encoding="utf-8")
    (sub / "c.txt").write_text("c", encoding="utf-8")


def test_recursive_collects_nested():
    with tempfile.TemporaryDirectory() as d:
        _build_tree(d)
        files = collect_files(d)
        rel = _rel(files, d)
        _check("1. 递归收集含子目录文件",
               len(files) == 3 and os.path.join("sub", "c.txt") in rel,
               repr(rel))
        # Every returned path must be an absolute regular file.
        _check("1b. 全部为绝对路径且为普通文件",
               all(os.path.isabs(p) and os.path.isfile(p) for p in files),
               repr(files[:2]))


def test_recursive_skips_dirs():
    with tempfile.TemporaryDirectory() as d:
        # A directory whose name looks like a file must still be excluded.
        fake = Path(d) / "not-really.txt"
        fake.mkdir()
        _build_tree(d)
        files = collect_files(d)
        rel = _rel(files, d)
        _check("2. 目录本身(含伪装文件名目录)不在结果",
               "sub" not in rel and "not-really.txt" not in rel,
               repr(rel))


def test_nonrecursive_only_direct_children():
    with tempfile.TemporaryDirectory() as d:
        _build_tree(d)
        files = collect_files(d, recursive=False)
        rel = _rel(files, d)
        _check("3. 非递归只取直接子文件",
               sorted(rel) == ["a.txt", "b.txt"],
               repr(rel))


def test_deterministic_order():
    with tempfile.TemporaryDirectory() as d:
        _build_tree(d)
        first = collect_files(d)
        second = collect_files(d)
        _check("4. 结果顺序确定可复现", first == second, repr(first))
        rel = _rel(first, d)
        # os.walk with sorted dirs/filenames: top-level sorted files first,
        # then the sorted subdirectory's contents.
        _check("4b. 顺序为顶层排序后子目录",
               rel == ["a.txt", "b.txt", os.path.join("sub", "c.txt")],
               repr(rel))


def test_invalid_path_empty():
    _check("5. 不存在的路径 -> []", collect_files("C:/__no_such_dir_xyz_123") == [])
    _check("5b. 空字符串 -> []", collect_files("") == [])
    with tempfile.TemporaryDirectory() as d:
        f = Path(d) / "a.txt"
        f.write_text("x", encoding="utf-8")
        _check("5c. 文件路径(非目录) -> []",
               collect_files(str(f)) == [], str(f))


def test_empty_dir_empty():
    with tempfile.TemporaryDirectory() as d:
        empty = Path(d) / "empty"
        empty.mkdir()
        _check("6. 空目录递归 -> []", collect_files(str(empty)) == [])
        _check("6b. 空目录非递归 -> []", collect_files(str(empty), recursive=False) == [])


def main():
    test_recursive_collects_nested()
    test_recursive_skips_dirs()
    test_nonrecursive_only_direct_children()
    test_deterministic_order()
    test_invalid_path_empty()
    test_empty_dir_empty()
    print()
    print("ALL FOLDER SCANNER CHECKS PASSED")
    sys.exit(0)


if __name__ == "__main__":
    main()
