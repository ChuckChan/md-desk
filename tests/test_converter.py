"""Converter unit tests (Stage 3 requirements 1-5).

Run: python tests/test_converter.py
"""

import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from markitdown import (
    UnsupportedFormatException,
    FileConversionException,
    MissingDependencyException,
)

from src.converter import convert_file, map_exception, ConversionError
from src.file_entry import FileStatus

TEST_INPUT = ROOT.parent / "test_input.html"


def _check(name, cond, detail=""):
    print(("PASS" if cond else "FAIL"), "-", name, "" if cond else f":: {detail}")
    return cond


def main():
    ok = True

    # 1. convert a real file
    assert TEST_INPUT.exists(), f"missing {TEST_INPUT}"
    md = convert_file(str(TEST_INPUT))
    ok &= _check("1. 转换 test_input.html", isinstance(md, str) and len(md) > 0, f"len={len(md) if md else 0}")

    # 2. success yields markdown content
    ok &= _check("2. 成功结果得到 Markdown", "#" in md or "|" in md, repr(md[:60]))

    # 3. UnsupportedFormatException -> UNSUPPORTED
    st, msg = map_exception(UnsupportedFormatException("nope"))
    ok &= _check("3. UnsupportedFormatException 映射", st == FileStatus.UNSUPPORTED and "不支持" in msg, f"{st}={msg}")

    # 4. FileConversionException -> ERROR
    st, msg = map_exception(FileConversionException("bad"))
    ok &= _check("4. FileConversionException 映射", st == FileStatus.ERROR, f"{st}={msg}")

    # 5. MissingDependencyException -> ERROR
    st, msg = map_exception(MissingDependencyException("dep"))
    ok &= _check("5. MissingDependencyException 映射", st == FileStatus.ERROR, f"{st}={msg}")

    # 5b. other exceptions -> ERROR (through convert_file, with MarkItDown patched)
    for exc_type, expected_status in (
        (UnsupportedFormatException, FileStatus.UNSUPPORTED),
        (FileConversionException, FileStatus.ERROR),
        (MissingDependencyException, FileStatus.ERROR),
        (ValueError, FileStatus.ERROR),
    ):
        with patch("src.converter.MarkItDown") as M, patch(
            "src.markitdown_factory.MarkItDown"
        ) as Mf:
            # v0.3 routes conversion through MarkItDownFactory, which holds its
            # own MarkItDown binding; alias it so the patch is effective.
            Mf.return_value = M.return_value
            M.return_value.convert.side_effect = exc_type("x")
            try:
                convert_file("dummy.bin")
                ok &= _check(f"5b. convert_file 映射 {exc_type.__name__}", False, "did not raise")
            except ConversionError as e:
                ok &= _check(f"5b. convert_file 映射 {exc_type.__name__}", e.status == expected_status,
                             f"status={e.status}")

    print()
    print("ALL CONVERTER CHECKS PASSED" if ok else "SOME CONVERTER CHECKS FAILED")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
