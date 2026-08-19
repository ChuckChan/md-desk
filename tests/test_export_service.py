"""v0.5.0 export_service.export_batch unit tests.

Pure-function suite (Qt-free): successful export, within-batch duplicate-name
suffixes, source-file conflict skip, write-failure tolerance (never raises),
and the empty / all-WAITING degenerate cases.
"""

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.export_service import export_batch
from src.file_entry import FileEntry, FileStatus


def _check(name, cond, detail=""):
    print(("PASS" if cond else "FAIL"), "-", name, "" if cond else f":: {detail}")
    assert cond, f"{name} :: {detail}"


def _entry(path, filename=None, status=FileStatus.DONE, markdown="# MD"):
    return FileEntry(
        path=str(path),
        filename=filename if filename is not None else Path(path).name,
        extension=Path(path).suffix.lower() or ".txt",
        size=0,
        status=status,
        markdown=markdown,
    )


def test_export_success(tmp):
    out = tmp / "out"
    out.mkdir()
    src = tmp / "a.txt"
    entries = [_entry(src, markdown="# A content")]
    res = export_batch(entries, str(out))

    _check("1. 成功导出计数", res.exported == 1 and res.failed == 0 and res.skipped_conflict == 0,
           f"exported={res.exported} failed={res.failed} conflict={res.skipped_conflict}")
    _check("1b. 错误为空", res.errors == (), repr(res.errors))
    _check("1c. 目标文件内容一致",
           (out / "a.md").read_text(encoding="utf-8") == "# A content")
    _check("1d. exported_paths 正确",
           len(res.exported_paths) == 1
           and os.path.normcase(res.exported_paths[0]) == os.path.normcase(str(out / "a.md")),
           repr(res.exported_paths))


def test_export_duplicate_names(tmp):
    out = tmp / "out"
    out.mkdir()
    # Three different source files that share the same basename -> a.md,
    # a_2.md, a_3.md in candidate order.
    entries = [
        _entry(tmp / "x" / "a.txt", filename="a.txt", markdown="# one"),
        _entry(tmp / "y" / "a.txt", filename="a.txt", markdown="# two"),
        _entry(tmp / "z" / "a.txt", filename="a.txt", markdown="# three"),
    ]
    res = export_batch(entries, str(out))

    _check("2. 批内重名全部导出",
           res.exported == 3 and res.failed == 0, f"exported={res.exported}")
    files = sorted(p.name for p in out.glob("*.md"))
    _check("2b. 目标名 a/a_2/a_3",
           files == ["a.md", "a_2.md", "a_3.md"], repr(files))
    _check("2c. 内容与各自 markdown 一致",
           (out / "a.md").read_text(encoding="utf-8") == "# one"
           and (out / "a_2.md").read_text(encoding="utf-8") == "# two"
           and (out / "a_3.md").read_text(encoding="utf-8") == "# three")


def test_export_conflict_skip(tmp):
    src = tmp / "a.md"  # source file already has the .md extension
    src.write_text("original", encoding="utf-8")
    entries = [_entry(src, filename="a.md", markdown="# NEW")]
    res = export_batch(entries, str(tmp))

    _check("3. 目标==源文件 -> skipped_conflict",
           res.skipped_conflict == 1 and res.exported == 0 and res.failed == 0,
           f"conflict={res.skipped_conflict} exported={res.exported}")
    _check("3b. 源文件内容未被改写",
           src.read_text(encoding="utf-8") == "original",
           src.read_text(encoding="utf-8"))


def test_export_write_failure(tmp):
    # Pre-create a DIRECTORY named x.md so the target write raises an OSError
    # (IsADirectoryError / PermissionError depending on platform).
    out = tmp / "out"
    out.mkdir()
    (out / "x.md").mkdir()
    entries = [_entry(tmp / "x.txt", filename="x.txt", markdown="# X")]
    res = export_batch(entries, str(out))  # must not raise

    _check("4. 写入失败计入 failed", res.failed == 1 and res.exported == 0,
           f"failed={res.failed} exported={res.exported}")
    _check("4b. errors 非空且消息截断到 120",
           len(res.errors) == 1 and len(res.errors[0]) <= 120,
           repr(res.errors))
    _check("4c. 目录未被破坏",
           (out / "x.md").is_dir(), str(out / "x.md"))


def test_export_empty_or_waiting(tmp):
    out = tmp / "out"
    out.mkdir()
    res = export_batch([], str(out))
    _check("5. 空条目全 0",
           (res.exported, res.skipped_conflict, res.failed, res.errors, res.exported_paths)
           == (0, 0, 0, (), ()),
           repr(res))

    src = tmp / "w.txt"
    entries = [_entry(src, status=FileStatus.WAITING, markdown="# W"),
               _entry(src, status=FileStatus.ERROR, markdown="# E")]
    res = export_batch(entries, str(out))
    _check("5b. 无 DONE 条目全 0",
           (res.exported, res.skipped_conflict, res.failed, res.errors, res.exported_paths)
           == (0, 0, 0, (), ()),
           repr(res))
    _check("5c. 未写入任何文件", list(out.iterdir()) == [], repr(list(out.iterdir())))


def test_export_unicode_error(tmp):
    """A markdown containing an unencodable lone surrogate must be counted as
    a failed export (UnicodeEncodeError), never raised (v0.5.0 NIT fix). A
    partial target may be left on disk by the failed write (standard write
    behavior); it is a NEW file in out_dir, never a source file."""
    out = tmp / "out"
    out.mkdir()
    src = tmp / "u.txt"
    src.write_text("source payload", encoding="utf-8")
    entries = [_entry(src, markdown="# OK \ud800")]  # lone surrogate
    res = export_batch(entries, str(out))
    _check("6. UnicodeEncodeError -> failed+1 且不 raise",
           res.failed == 1 and res.exported == 0 and len(res.errors) == 1,
           repr(res))
    _check("6b. 源文件未被触碰(仍存在且原样)",
           src.exists() and src.read_text(encoding="utf-8") == "source payload")
    _check("6c. 失败目标不是源文件(半成品为 out 内新文件)",
           not (out / "u.md").samefile(src) if (out / "u.md").exists() else True)


def main():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        test_export_success(root)
        test_export_duplicate_names(root)
        test_export_conflict_skip(root)
        test_export_write_failure(root)
        test_export_empty_or_waiting(root)
        test_export_unicode_error(root)
    print()
    print("ALL EXPORT SERVICE CHECKS PASSED")
    sys.exit(0)


if __name__ == "__main__":
    main()
