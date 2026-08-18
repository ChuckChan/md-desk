"""Lightweight import-isolation test (v0.4 Stage 3).

This verifies, in a FRESH Python process, that importing ``src.report`` (the
Stage 3 report data layer) does NOT transitively pull in MarkItDown. A shared
pytest session can't prove this reliably (other suites import the engine), so
we spawn a clean interpreter that imports only ``src.report`` and checks
``sys.modules``.

Run: pytest tests/test_report_light.py
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _fresh_import_check() -> bool:
    """Return True if a clean interpreter can import src.report WITHOUT
    loading markitdown into sys.modules."""
    script = (
        "import sys\n"
        "sys.path.insert(0, sys.argv[1])\n"
        "import src.report\n"          # only the report layer
        "import src.result\n"          # QualityWarning lives here, not in quality/
        "print('markitdown' in sys.modules)\n"
    )
    proc = subprocess.run(
        [sys.executable, "-c", script, str(ROOT)],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"fresh-import subprocess failed:\n{proc.stderr}"
        )
    return proc.stdout.strip() == "False"


def test_report_layer_is_markitdown_free():
    # The whole point of Stage 3's separation: the report layer must not drag
    # the heavy conversion engine into an import -- proven in a clean process.
    assert _fresh_import_check() is True


def test_qualitywarning_lives_in_result_not_quality():
    # Confirms result.py owns QualityWarning (so it stays engine-free).
    from src.result import QualityWarning

    assert QualityWarning.__module__ == "src.result"


def test_build_report_without_engine():
    # Build a report purely from a result (no FileEntry needed) -- no engine.
    from src.report import ConversionResult, ReportBuilder

    res = ConversionResult.success(0, "# hi", duration_ms=1)
    rep = ReportBuilder.build(res, None)
    assert rep.row == 0
    assert rep.source_type == "unknown"
    assert rep.ok is True
    assert "markdown" not in rep.to_dict()
