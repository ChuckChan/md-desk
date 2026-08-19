"""Single source of truth for the MdDesk version.

Historically the version was hardcoded in several places (most visibly the
safe-URL User-Agent shipped as ``"MdDesk/0.3 ..."`` well into the v0.4.x line,
and the distribution ZIP name/root in the release scripts). That drift is now
consolidated here:

  * ``__version__``  -- the canonical release version (semver-ish).
  * ``APP_NAME``     -- the product name.
  * ``user_agent()`` -- the outbound User-Agent for MdDesk's safe-URL fetch
                        layer, derived from the two above.

Runtime code, the User-Agent, diagnostics, and the release scripts all import
from this module instead of hardcoding a version string.
"""

__version__ = "0.5.0"

APP_NAME = "MdDesk"


def user_agent() -> str:
    """Outbound User-Agent string for MdDesk's safe-URL fetch layer."""
    return f"{APP_NAME}/{__version__} (+safe-url-fetch)"
