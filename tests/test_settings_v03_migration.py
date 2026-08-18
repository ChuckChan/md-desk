"""v0.3 -> v0.4 settings migration acceptance (Stage 6 RC).

A real v0.3 ``settings.json`` carries ``version: 2`` with
``youtube_transcript_languages`` and an ``ai`` block, but NO
``quality_enabled`` key (quality inspection was added in v0.4 Stage 2 and
defaults OFF). Loading such a file in v0.4 must:

  * preserve the original config (youtube languages + AI block),
  * default ``quality_enabled`` to False (so v0.3 conversion behavior is
    byte-for-byte unchanged), and
  * round-trip cleanly (saving does not lose the user's config and writes
    ``quality_enabled: false`` so a later load stays consistent).

This file is Qt-free and runs headless.
"""

import json
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
import sys

sys.path.insert(0, str(ROOT))

from src.settings import Settings  # noqa: E402


def _check(name, cond, detail=""):
    print(("PASS" if cond else "FAIL"), "-", name, "" if cond else f":: {detail}")
    return cond


def _write(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def test_v03_file_loads_quality_off():
    """A representative v0.3 settings file loads with quality_enabled=False
    and keeps its original youtube / AI config."""
    ok = True
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "settings.json"
        v03 = {
            "version": 2,
            "youtube_transcript_languages": ["zh-Hans", "en", "ja"],
            "ai": {
                "enabled": True,
                "endpoint": "https://api.openai.com/v1",
                "model": "gpt-4o",
                "prompt": "",
            },
            # NOTE: no quality_enabled key in v0.3
        }
        _write(p, v03)

        s = Settings.load(p)
        ok &= _check("v03 加载: quality_enabled 默认 False",
                     s.quality_enabled is False, repr(s.quality_enabled))
        ok &= _check("v03 加载: YouTube 字幕语言保留",
                     s.youtube_transcript_languages == ["zh-Hans", "en", "ja"],
                     repr(s.youtube_transcript_languages))
        ok &= _check("v03 加载: AI 启用状态保留",
                     s.ai.enabled is True, repr(s.ai.enabled))
        ok &= _check("v03 加载: AI endpoint 保留",
                     s.ai.endpoint == "https://api.openai.com/v1", repr(s.ai.endpoint))
        ok &= _check("v03 加载: AI model 保留",
                     s.ai.model == "gpt-4o", repr(s.ai.model))
        ok &= _check("v03 加载: schema version 不变 (2)",
                     s.version == 2, repr(s.version))
    return ok


def test_v03_roundtrip_writes_quality_off():
    """Saving a migrated v0.3 config must not drop the user's settings and
    must persist ``quality_enabled: false`` so re-load stays consistent."""
    ok = True
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "settings.json"
        v03 = {
            "version": 2,
            "youtube_transcript_languages": ["zh-Hans", "en"],
            "ai": {"enabled": True, "endpoint": "https://x/v1", "model": "gpt-4o", "prompt": ""},
        }
        _write(p, v03)
        s = Settings.load(p)

        out = Path(d) / "out.json"
        s.save(out)
        reloaded = Settings.load(out)

        ok &= _check("v03 回写: 仍是 quality_enabled=False",
                     reloaded.quality_enabled is False, repr(reloaded.quality_enabled))
        ok &= _check("v03 回写: YouTube 语言保留",
                     reloaded.youtube_transcript_languages == ["zh-Hans", "en"],
                     repr(reloaded.youtube_transcript_languages))
        ok &= _check("v03 回写: AI 配置保留",
                     reloaded.ai.enabled and reloaded.ai.model == "gpt-4o",
                     repr(reloaded.ai.to_dict()))
        # The persisted JSON must actually contain the quality key (so a fresh
        # v0.4 start reads it explicitly rather than relying on the default).
        blob = json.loads(out.read_text(encoding="utf-8"))
        ok &= _check("v03 回写: JSON 含 quality_enabled 字段",
                     "quality_enabled" in blob and blob["quality_enabled"] is False,
                     repr(blob))
    return ok


def test_v02_minimal_file_loads():
    """A minimal v0.2-style file (version=2, no ai block, no quality) also
    migrates cleanly: AI disabled, quality OFF, no crash."""
    ok = True
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "settings.json"
        _write(p, {"version": 2, "youtube_transcript_languages": ["en"]})
        s = Settings.load(p)
        ok &= _check("v02 最小文件: quality_enabled=False", s.quality_enabled is False)
        ok &= _check("v02 最小文件: AI 默认禁用", s.ai.enabled is False)
        ok &= _check("v02 最小文件: YouTube 语言保留",
                     s.youtube_transcript_languages == ["en"])
    return ok


def test_quality_on_explicit_preserved():
    """If a v0.4 user already enabled quality, loading keeps it True
    (forward-compat sanity)."""
    ok = True
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "settings.json"
        _write(p, {"version": 2, "quality_enabled": True,
                   "youtube_transcript_languages": [], "ai": {}})
        s = Settings.load(p)
        ok &= _check("v04 已开启 quality 保留为 True", s.quality_enabled is True)
    return ok


def main():
    results = [
        test_v03_file_loads_quality_off(),
        test_v03_roundtrip_writes_quality_off(),
        test_v02_minimal_file_loads(),
        test_quality_on_explicit_preserved(),
    ]
    ok = all(results)
    print()
    print("ALL v0.3->v0.4 SETTINGS MIGRATION CHECKS PASSED" if ok
          else "SOME SETTINGS MIGRATION CHECKS FAILED")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
