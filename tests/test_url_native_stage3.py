"""Stage 3: URL-native capability verification for MdDesk.

Verifies the existing URL entry (GUI -> Worker -> convert_url ->
UrlFetchService -> convert_stream) triggers MarkItDown 0.1.7's BUILT-IN
converters for real remote capabilities, WITHOUT re-implementing any
converter and WITHOUT using MarkItDown.convert_uri().

All capability checks hit REAL public endpoints (network required). If a
host is momentarily unreachable the check is reported as FAIL with the
underlying error; re-run when network is available.

Run:  python tests/test_url_native_stage3.py   (from the project root)
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.converter import convert_url, ConversionError

ROOT = Path(__file__).resolve().parent.parent

_CAPS = []


def _record(capability: str, result: str, evidence: str) -> None:
    _CAPS.append((capability, result, evidence))
    mark = {"PASS": "PASS", "FAIL": "FAIL"}.get(result, result)
    print(f"  [{mark}] {capability}: {result}  | {evidence}")


def _probe(capability: str, url: str, expect: list[str], timeout_ok: bool = True) -> None:
    try:
        md = convert_url(url)
    except ConversionError as e:
        _record(capability, "FAIL", f"ConversionError({e.status.value}): {e.message[:80]}")
        return
    except Exception as e:
        _record(capability, "FAIL", f"{type(e).__name__}: {str(e)[:80]}")
        return
    if not md or not md.strip():
        _record(capability, "FAIL", "empty markdown")
        return
    missing = [s for s in expect if s not in md]
    if missing:
        _record(capability, "FAIL", f"missing markers {missing}; head={md[:70]!r}")
        return
    _record(capability, "PASS", f"len={len(md)}; markers={expect}")


def _static_no_convert_uri() -> None:
    """Confirm src/ never calls MarkItDown.convert_uri / the .convert_url alias."""
    import io

    src_dir = ROOT / "src"
    hits = []
    for f in src_dir.rglob("*.py"):
        if "__pycache__" in str(f):
            continue
        text = f.read_text(encoding="utf-8")
        # strip docstrings/comments crudely
        cleaned = re.sub(r'""".*?"""', "", text, flags=re.S)
        cleaned = re.sub(r"#.*$", "", cleaned, flags=re.M)
        for tok in (".convert_uri(", "convert_uri(", ".convert_url(", "convert_url("):
            if tok in cleaned and not (tok == "convert_url(" and f.name == "converter.py"):
                hits.append((f.name, tok))
    if hits:
        _record("convert_uri NOT used", "FAIL", str(hits))
    else:
        _record("convert_uri NOT used", "PASS", "no convert_uri/convert_url(MarkItDown) calls in src/")


def main() -> int:
    print("\n=== Stage 3: URL-native capability matrix (real network) ===")
    _static_no_convert_uri()

    # 1) Plain web page
    _probe("Web page (HTML)", "https://example.com/",
           ["Example Domain"])

    # 2) RSS / Atom
    _probe("RSS feed", "https://feeds.bbci.co.uk/news/rss.xml",
           ["BBC News"])

    # 3) Wikipedia
    _probe("Wikipedia article", "https://en.wikipedia.org/wiki/Markdown",
           ["Markdown"])

    # 4) Bing SERP
    _probe("Bing SERP", "https://www.bing.com/search?q=markitdown+python",
           ["Bing"])

    # 5) YouTube metadata
    _probe("YouTube metadata", "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
           ["# YouTube", "Never Gonna Give You Up"])

    # 6) YouTube transcript status
    try:
        from markitdown.converters._youtube_converter import IS_YOUTUBE_TRANSCRIPT_CAPABLE
    except Exception:
        IS_YOUTUBE_TRANSCRIPT_CAPABLE = False
    if IS_YOUTUBE_TRANSCRIPT_CAPABLE:
        _record("YouTube transcript", "AVAILABLE", "youtube_transcript_api installed")
    else:
        _record("YouTube transcript", "MISSING_DEPENDENCY",
                "youtube_transcript_api not installed (by design; not added this round)")

    # 7) Remote TXT
    _probe("Remote TXT file", "https://www.gnu.org/licenses/gpl-3.0.txt",
           ["GNU GENERAL PUBLIC LICENSE"])

    # 8) Remote PDF
    _probe("Remote PDF file", "https://www.w3.org/WAI/ER/tests/xhtml/testfiles/resources/pdf/dummy.pdf",
           ["Dummy PDF file"])

    # --- Regression (existing suites must stay green) ---
    print("\n=== Existing regression suites ===")
    reg_pass = True
    for suite in ("test_msg_stage1b.py", "test_regression_formats.py"):
        p = subprocess.run(
            [sys.executable, str(ROOT / "tests" / suite)],
            cwd=str(ROOT), capture_output=True, text=True,
            env={**__import__("os").environ, "CODEBUDDY_SESSION_ID": "",
                 "CLAUDE_SESSION_ID": ""},
        )
        ok = p.returncode == 0
        reg_pass &= ok
        snippet = (p.stdout or p.stderr).strip().splitlines()[-1] if (p.stdout or p.stderr) else ""
        _record(f"Regression: {suite}", "PASS" if ok else "FAIL",
                f"rc={p.returncode} :: {snippet[:70]}")

    # --- Summary ---
    fails = [c for c in _CAPS if c[1] == "FAIL"]
    print("\n=== Capability Matrix ===")
    for cap, res, ev in _CAPS:
        print(f"  {cap:28s} | {res:18s} | {ev[:60]}")
    print(f"\nSTAGE3_CAPS_PASS={len(_CAPS)-len(fails)} FAIL={len(fails)}")
    ok = len(fails) == 0
    print("STAGE3_ALL_PASS" if ok else "STAGE3_NOT_ALL_PASS")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
