"""ConversionResult unit tests (v0.4 Stage 1).

Run: python tests/test_result.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.converter import ConversionError
from src.file_entry import FileStatus
from src.result import ConversionResult, QualityWarning


def _check(name, cond, detail=""):
    print(("PASS" if cond else "FAIL"), "-", name, "" if cond else f":: {detail}")
    return cond


def main():
    ok = True

    # 1. success carries markdown + DONE, no error
    res = ConversionResult.success(0, "# hello")
    ok &= _check("1. success: status DONE", res.status == FileStatus.DONE, f"{res.status}")
    ok &= _check("1b. success: markdown 透传", res.markdown == "# hello", repr(res.markdown))
    ok &= _check("1c. success: error_message None", res.error_message is None)
    ok &= _check("1d. success: ok == True", res.ok is True)

    # 2. failure carries status + message, no markdown
    err = ConversionResult.failure(1, FileStatus.ERROR, "boom")
    ok &= _check("2. failure: status ERROR", err.status == FileStatus.ERROR)
    ok &= _check("2b. failure: error_message 透传", err.error_message == "boom")
    ok &= _check("2c. failure: markdown None", err.markdown is None)
    ok &= _check("2d. failure: ok == False", err.ok is False)

    # 3. from_error reuses ConversionError's mapped status + message
    ce = ConversionError(FileStatus.UNSUPPORTED, "不支持")
    r = ConversionResult.from_error(2, ce)
    ok &= _check("3. from_error: 复用 status", r.status == FileStatus.UNSUPPORTED, f"{r.status}")
    ok &= _check("3b. from_error: 复用 message", r.error_message == "不支持")
    ok &= _check("3c. from_error: row 透传", r.row == 2)

    # 4. warnings is an immutable tuple of QualityWarning
    w = ConversionResult.success(
        3, "md",
        warnings=(QualityWarning("X", "y"), QualityWarning("Z", "w")),
    )
    ok &= _check("4. warnings 为 tuple", isinstance(w.warnings, tuple), type(w.warnings).__name__)
    ok &= _check(
        "4b. warnings 内容为 QualityWarning",
        w.warnings == (QualityWarning("X", "y"), QualityWarning("Z", "w")),
    )

    # 5. duration_ms captured
    d = ConversionResult.success(4, "md", duration_ms=123)
    ok &= _check("5. duration_ms 透传", d.duration_ms == 123, f"{d.duration_ms}")

    # 6. frozen: attribute assignment raises
    try:
        res.markdown = "x"
        ok &= _check("6. frozen 不可变", False, "assignment succeeded")
    except Exception:
        ok &= _check("6. frozen 不可变", True)

    # 7. from_error rejects non-ConversionError
    try:
        ConversionResult.from_error(5, ValueError("nope"))
        ok &= _check("7. from_error 拒绝非 ConversionError", False, "accepted")
    except TypeError:
        ok &= _check("7. from_error 拒绝非 ConversionError", True)

    print()
    print("ALL RESULT CHECKS PASSED" if ok else "SOME RESULT CHECKS FAILED")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
