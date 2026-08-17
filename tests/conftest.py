"""Pytest configuration for MdDesk's test suite.

Some suites (test_url_stage2, test_tls_stage2, test_msg_stage1b) are written
in a *script* style: their ``test_*`` functions receive runtime arguments
(``server_url`` / ``tmp`` / ``fixture``) that are normally supplied by the
module's own ``main()`` when run as ``python tests/test_x.py``. To make them
discoverable by a single ``pytest tests/`` run as well, we provide those
arguments as fixtures here. The script entry points remain the canonical
v0.2-style validation and still pass on their own.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402


@pytest.fixture
def tmp(tmp_path):
    """Alias for pytest's ``tmp_path`` so script-style suites can use ``tmp``."""
    return tmp_path


@pytest.fixture(scope="session")
def server_url():
    """Start the local mock HTTP server used by test_url_stage2."""
    import test_url_stage2 as m

    server, _, url = m._start_server()
    try:
        yield url
    finally:
        server.shutdown()
        server.server_close()


@pytest.fixture
def fixture():
    """Ensure and return the Outlook .msg fixture path (test_msg_stage1b)."""
    import test_msg_stage1b as m

    return m._ensure_fixture()
