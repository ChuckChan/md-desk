"""Frozen-EXE runtime smoke for Stage 4 (Advanced Conversion Settings).

Built with the SAME collection flags as the real md-desk.exe, so it
exercises the identical bundled module set. It proves, inside the frozen
binary (no venv):

  1. Settings infrastructure works: default / save-reload / corrupt fallback
     (the %APPDATA%/MdDesk/settings.json persistence layer).
  2. StreamInfo Override (advanced) reaches the engine end-to-end: a
     mislabeled .csv (actually plain text) converts via PlainText after an
     .txt extension override, while the default path goes through the CSV
     converter. This is the core Stage 4 capability.

stdout is forced to UTF-8 so non-ASCII content never crashes the harness on
a GBK Windows console. All printed diagnostics are ASCII.

Run: build then execute the frozen stage4.exe.
"""

import io
import json
import os
import sys
import tempfile
from pathlib import Path

# Force UTF-8 so any non-ASCII transcript/content never raises
# UnicodeEncodeError on a GBK Windows console.
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

sys.path.insert(0, ".")

from src.converter import convert_file  # noqa: E402
from src.settings import Settings, StreamInfoOverride  # noqa: E402


def _check(label, ok, detail=""):
    print(("PASS" if ok else "FAIL"), "-", label, "" if ok else ":: " + detail)
    return ok


def _settings_tests():
    ok = True
    # 1. default
    d = Settings.default()
    ok &= _check("SETTINGS_DEFAULT_NO_LANGS", d.youtube_transcript_languages == [],
                 repr(d.youtube_transcript_languages))

    # 2. save -> reload (explicit temp path; do not touch real APPDATA here)
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "settings.json"
        s = Settings(youtube_transcript_languages=["zh-Hans", "en"])
        s.save(p)
        reloaded = Settings.load(p)
        ok &= _check("SETTINGS_SAVE_RELOAD",
                     reloaded.youtube_transcript_languages == ["zh-Hans", "en"],
                     repr(reloaded.to_dict()))

        # 3. corrupt -> safe fallback to defaults (no crash)
        bad = Path(td) / "bad.json"
        bad.write_text("{ not valid json ", encoding="utf-8")
        fb = Settings.load(bad)
        ok &= _check("SETTINGS_CORRUPT_FALLBACK",
                     fb.youtube_transcript_languages == [] and fb.version == 2,
                     repr(fb.to_dict()))
    return ok


def _override_logic_tests():
    ok = True
    # Pure-logic checks for the override helper (no mock needed in frozen).
    ov = StreamInfoOverride(mimetype="text/plain", charset="utf-8")
    ok &= _check("OVERRIDE_AS_KWARGS", ov.as_kwargs() == {"mimetype": "text/plain", "charset": "utf-8"},
                 repr(ov.as_kwargs()))
    ok &= _check("OVERRIDE_NOT_EMPTY", ov.is_empty() is False)
    empty = StreamInfoOverride()
    ok &= _check("OVERRIDE_EMPTY", empty.is_empty() is True)
    return ok


def _override_e2e_tests():
    ok = True
    # A plain-text file mislabeled with a .csv extension.
    raw = b"Hello world\nThis is plain text content, not a spreadsheet.\n"
    ascii_raw = raw.decode("ascii")
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "data.csv"
        p.write_bytes(raw)

        # Default: routes through the CSV converter (output != raw text).
        default_md = convert_file(str(p))
        # Override extension -> .txt: routes through PlainText (raw passthrough).
        override_md = convert_file(str(p), override=StreamInfoOverride(extension=".txt"))

        ok &= _check("OVERRIDE_DEFAULT_CSV_NE_RAW",
                     default_md.strip() != ascii_raw.strip(), repr(default_md[:60]))
        ok &= _check("OVERRIDE_TXT_PASSTHROUGH",
                     override_md.strip() == ascii_raw.strip(),
                     "got=" + repr(override_md[:60]))
    return ok


def main():
    ok = True
    ok &= _settings_tests()
    ok &= _override_logic_tests()
    ok &= _override_e2e_tests()
    print()
    if ok:
        print("STAGE4_FROZEN_PASS")
        sys.exit(0)
    else:
        print("STAGE4_FROZEN_FAIL")
        sys.exit(1)


if __name__ == "__main__":
    main()
