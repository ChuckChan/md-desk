#!/usr/bin/env python
"""Stage 1B MSG verification: environment + engine + MdDesk source path.

Run from the project root:
    python tests/test_msg_stage1b.py

Covers:
  Test 1 - Environment (python / markitdown / olefile versions + location)
  Test 2 - MarkItDown engine converts the .msg fixture (no MissingDependencyException)
  Test 3 - MdDesk converter.convert_file() path converts the same fixture

The fixture is generated on demand by tests/make_msg_fixture.py if missing.
"""

import importlib.metadata as md
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

FIXTURE = ROOT / "tests" / "fixtures" / "sample_outlook.msg"
SUBJECT = "Quarterly Report Reminder"
BODY_HINT = "quarterly report"


def _check(name, cond, detail=""):
    print(("PASS" if cond else "FAIL"), "-", name, "" if cond else f":: {detail}")
    return cond


def _ensure_fixture():
    if not FIXTURE.exists():
        import make_msg_fixture
        make_msg_fixture.main()
    return str(FIXTURE)


def test1_environment():
    print("\n--- TEST 1: ENVIRONMENT ---")
    import olefile
    py = sys.version.split()[0]
    mk = md.version("markitdown")
    ol = md.version("olefile")
    print(f"python={py} markitdown={mk} olefile={ol}")
    print(f"olefile_location={olefile.__file__}")
    ok = _check("markitdown == 0.1.7", mk == "0.1.7", mk)
    ok &= _check("olefile importable", True)
    return ok


def test2_engine(fixture):
    print("\n--- TEST 2: MARKITDOWN ENGINE ---")
    from markitdown import MarkItDown
    try:
        out = MarkItDown().convert(fixture).markdown
    except Exception as exc:  # noqa: BLE001
        return _check("engine converts .msg without exception", False, repr(exc))
    print("engine markdown length:", len(out))
    has_subj = SUBJECT in out
    has_body = BODY_HINT in out.lower()
    ok = _check("engine markdown non-empty", bool(out and out.strip()), f"len={len(out)}")
    ok &= _check("engine contains Subject", has_subj)
    ok &= _check("engine contains Body", has_body)
    return ok


def test3_source_path(fixture):
    print("\n--- TEST 3: MdDesk SOURCE PATH (converter.convert_file) ---")
    from src.converter import convert_file
    try:
        out = convert_file(fixture)
    except Exception as exc:  # noqa: BLE001
        return _check("MdDesk convert_file .msg without exception", False, repr(exc))
    print("source-path markdown length:", len(out))
    has_subj = SUBJECT in out
    has_body = BODY_HINT in out.lower()
    ok = _check("source-path markdown non-empty", bool(out and out.strip()), f"len={len(out)}")
    ok &= _check("source-path contains Subject", has_subj)
    ok &= _check("source-path contains Body", has_body)
    return ok


def main():
    fixture = _ensure_fixture()
    results = [test1_environment(), test2_engine(fixture), test3_source_path(fixture)]
    ok = all(results)
    print("\n" + ("ALL MSG STAGE 1B CHECKS PASSED" if ok else "SOME MSG CHECKS FAILED"))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
