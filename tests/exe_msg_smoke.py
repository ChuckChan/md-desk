"""Frozen-bundle .msg smoke test (Stage 1B, Test 6B).

This script is frozen with the SAME PyInstaller configuration family used for
the real MdDesk EXE (same packaging venv, same `markitdown[outlook]==0.1.7`,
same `--collect-submodules markitdown`). Because `olefile` and `markitdown`
are bundled into the PyInstaller PYZ (NOT loose files), the only processes that
can load them are frozen binaries. This harness therefore exercises the EXACT
frozen conversion pipeline the shipping EXE uses:

  olefile (PYZ) -> markitdown.OutlookMsgConverter -> src.converter.convert_file

It verifies:
  1) The .msg fixture converts to non-empty Markdown containing the expected
     Subject / From / To / Body tokens.
  2) The MissingDependencyException error path maps to FileStatus.ERROR with a
     clear, user-facing message (no raw traceback leaking to ordinary users).

It intentionally avoids Qt so the build stays focused on the conversion path;
the GUI boot is covered separately by launching the real md-desk.exe (Test 6A).
"""

import os
import sys
from pathlib import Path


def _resolve_fixture() -> str:
    """Locate the .msg fixture.

    The frozen executable lives at <repo>/dist/<name>/<name>.exe, so the repo
    root is three path components up from the executable. An explicit path may
    also be passed as argv[1].
    """
    if len(sys.argv) > 1 and sys.argv[1]:
        return sys.argv[1]
    exe = Path(sys.executable).resolve()
    repo = exe.parents[2]  # <repo>/dist/<name>/<name>.exe -> <repo>
    return str(repo / "tests" / "fixtures" / "sample_outlook.msg")


def main() -> int:
    fixture = _resolve_fixture()
    if not os.path.isfile(fixture):
        print("FAIL: fixture not found: %s" % fixture)
        return 1

    # ---- Import the frozen modules exactly as the shipping EXE would ----
    print("HARNESS: importing frozen olefile + markitdown + src.converter ...")
    import olefile  # noqa: F401  (proves olefile is present in the PYZ)
    from markitdown import MissingDependencyException
    from src.converter import convert_file, map_exception

    print("HARNESS: olefile resolved at %s" % olefile.__file__)

    # ---- 1) Real .msg conversion through the frozen pipeline ----
    try:
        md = convert_file(fixture)
    except Exception as exc:  # noqa: BLE001
        print("FAIL: convert_file raised %s: %s" % (type(exc).__name__, exc))
        return 1

    if not md or not md.strip():
        print("FAIL: conversion produced empty Markdown")
        return 1

    expected_tokens = (
        "Quarterly Report Reminder",  # Subject
        "Alice Example",              # From
        "Bob Recipient",              # To
        "quarterly report",           # Body
    )
    missing = [t for t in expected_tokens if t not in md]
    if missing:
        print("FAIL: Markdown missing expected tokens: %r" % missing)
        print("---- Markdown (first 400 chars) ----")
        print(md[:400])
        return 1

    print("CONVERT_OK len=%d" % len(md.strip()))

    # ---- 2) Error-path mapping (MissingDependencyException) ----
    status, message = map_exception(MissingDependencyException("olefile"))
    if status.name != "ERROR":
        print("FAIL: expected ERROR status, got %s" % status.name)
        return 1
    if "转换失败" not in message:
        print("FAIL: error message not user-facing: %r" % message)
        return 1
    print("ERRORPATH_OK status=%s message=%s" % (status.name, message))

    print("ALL_FROZEN_CHECKS_PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
