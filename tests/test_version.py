"""Single version source regression (v0.4.1).

Guards against the version drifting into multiple hardcoded copies (the
historical bug shipped a ``"MdDesk/0.3"`` User-Agent well into the v0.4.x
line, and the release scripts hardcoded ``MdDesk-v0.4.0`` independently).
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.url_fetch_service import DEFAULT_USER_AGENT
from src.version import APP_NAME, __version__, user_agent


def test_version_format():
    assert re.fullmatch(r"\d+\.\d+\.\d+", __version__), __version__


def test_user_agent_derivative():
    ua = user_agent()
    assert ua.startswith(f"{APP_NAME}/"), ua
    assert __version__ in ua, ua
    assert "(+safe-url-fetch)" in ua, ua


def test_user_agent_no_stale_drift():
    # The classic bug: the UA hardcoded "MdDesk/0.3" deep into the v0.4.x line.
    assert "0.3" not in DEFAULT_USER_AGENT, DEFAULT_USER_AGENT
    # The runtime User-Agent must be derived from the single source, not a
    # second hardcoded string.
    assert DEFAULT_USER_AGENT == user_agent(), DEFAULT_USER_AGENT
    assert __version__ in DEFAULT_USER_AGENT, DEFAULT_USER_AGENT


def test_release_scripts_reference_single_source():
    # The release scripts must derive the ZIP name / root folder from
    # src/version, not hardcode a version string of their own.
    import make_dist_zip
    import verify_dist_zip

    assert make_dist_zip.VERSION == __version__, make_dist_zip.VERSION
    assert verify_dist_zip.VERSION == __version__, verify_dist_zip.VERSION
    assert f"MdDesk-{__version__}" in make_dist_zip.OUT
    assert f"MdDesk-{__version__}" in verify_dist_zip.ZIP
