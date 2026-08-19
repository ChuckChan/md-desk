"""MdDesk v0.6 settings migration & compatibility tests (plan §7.9 / §6).

The v0.6 schema ADDS optional keys to the ``ai`` block (provider /
timeout_seconds / ocr_enabled / image_description_enabled) with defaults that
keep a pre-v0.6 "AI on" config behaving EXACTLY as before (both capabilities
on, provider openai-compatible, finite 60 s timeout). Old files:

  * v0.3–v0.5 settings.json (version 2, ai: {enabled,endpoint,model,prompt})
  * file with garbage timeout / non-bool toggles / unknown provider
  * round-trip: saving a migrated config persists the v0.6 keys and the API
    key never appears in settings.json (it stays in Credential Manager).

Run: python tests/test_v06_settings.py   (or: pytest tests/test_v06_settings.py)
"""

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.settings import (  # noqa: E402
    AI_TIMEOUT_DEFAULT_SECONDS,
    PROVIDER_OPENAI_COMPATIBLE,
    AIConfig,
    Settings,
)

SECRET = "sk-OLD-SECRET-KEY-abcdef"


def _check(name, cond, detail=""):
    print(("PASS" if cond else "FAIL"), "-", name, "" if cond else f":: {detail}")
    return cond


def test_v05_file_migrates_to_v06_defaults():
    """A representative v0.5 settings.json loads with the v0.6 defaults."""
    ok = True
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "settings.json"
        v05 = {
            "version": 2,
            "youtube_transcript_languages": ["zh-Hans", "en"],
            "ai": {
                "enabled": True,
                "endpoint": "https://api.openai.com/v1",
                "model": "gpt-4o",
                "prompt": "描述这张图",
            },
            "quality_enabled": True,
            # NOTE: none of the v0.6 keys exist
        }
        p.write_text(json.dumps(v05, ensure_ascii=False, indent=2), encoding="utf-8")

        s = Settings.load(p)
        ok &= _check("M1. v0.5 加载: enabled 保留", s.ai.enabled is True)
        ok &= _check("M2. v0.5 加载: endpoint/model/prompt 保留",
                     s.ai.endpoint == "https://api.openai.com/v1"
                     and s.ai.model == "gpt-4o"
                     and s.ai.prompt == "描述这张图")
        ok &= _check("M3. v0.5 迁移: provider 默认 openai-compatible",
                     s.ai.provider == PROVIDER_OPENAI_COMPATIBLE)
        ok &= _check("M4. v0.5 迁移: timeout 默认 60s",
                     s.ai.timeout_seconds == AI_TIMEOUT_DEFAULT_SECONDS)
        ok &= _check("M5. v0.5 迁移: OCR 默认开（旧行为）", s.ai.ocr_enabled is True)
        ok &= _check("M6. v0.5 迁移: 图片描述默认开（旧行为）",
                     s.ai.image_description_enabled is True)
        ok &= _check("M7. quality_enabled 保留", s.quality_enabled is True)
        ok &= _check("M8. is_effectively_configured 仍有效",
                     s.ai.is_effectively_configured())
    assert ok


def test_garbage_values_fall_back_safely():
    ok = True
    bad = AIConfig.from_dict({
        "enabled": True,
        "provider": 123,                 # non-str -> default
        "endpoint": None,                # non-str -> ""
        "model": ["x"],                  # non-str -> ""
        "timeout_seconds": "thirty",     # non-num -> default
        "prompt": None,                  # non-str -> ""
        "ocr_enabled": "yes",            # truthy str -> True (bool() coercion)
        "image_description_enabled": [], # falsy -> False
    })
    ok &= _check("G1. 垃圾 provider -> 默认", bad.provider == PROVIDER_OPENAI_COMPATIBLE)
    ok &= _check("G2. 垃圾 endpoint/model/prompt -> 空串",
                 bad.endpoint == "" and bad.model == "" and bad.prompt == "")
    ok &= _check("G3. 垃圾 timeout -> 60s", bad.timeout_seconds == 60.0)
    ok &= _check("G4. 越界 timeout 钳制",
                 AIConfig.from_dict({"timeout_seconds": -3}).timeout_seconds == 1.0)
    ok &= _check("G5. 超大 timeout 钳制",
                 AIConfig.from_dict({"timeout_seconds": 10**9}).timeout_seconds == 600.0)
    ok &= _check("G6. 非 dict ai 块 -> 默认", AIConfig.from_dict("junk").enabled is False)
    ok &= _check("G7. 未知 provider 归一化",
                 AIConfig.from_dict({"provider": "claude"}).provider
                 == PROVIDER_OPENAI_COMPATIBLE)
    assert ok


def test_roundtrip_and_no_secret_in_file():
    ok = True
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "settings.json"
        v05 = {
            "version": 2,
            "youtube_transcript_languages": [],
            "ai": {"enabled": True, "endpoint": "https://gw/v1", "model": "m1"},
        }
        p.write_text(json.dumps(v05), encoding="utf-8")
        s = Settings.load(p)
        # v0.6-style edits, then save
        s.ai.ocr_enabled = False
        s.ai.timeout_seconds = 30
        s.save()

        text = p.read_text(encoding="utf-8")
        ok &= _check("R1. 保存后含新键", '"ocr_enabled": false' in text and '"timeout_seconds": 30' in text)
        ok &= _check("R2. 保存后含 provider 键", PROVIDER_OPENAI_COMPATIBLE in text)
        ok &= _check("R3. settings.json 不含任何 api_key 字段", "api_key" not in text)
        ok &= _check("R4. settings.json 不含密钥值", SECRET not in text)

        s2 = Settings.load(p)
        ok &= _check("R5. 重载后 OCR 关闭保留", s2.ai.ocr_enabled is False)
        ok &= _check("R6. 重载后 timeout 保留", s2.ai.timeout_seconds == 30)
        ok &= _check("R7. 重载后图片描述默认开", s2.ai.image_description_enabled is True)
    assert ok


def test_default_settings_ai_off():
    ok = True
    s = Settings.default()
    ok &= _check("D1. 默认 AI 关闭", s.ai.enabled is False)
    ok &= _check("D2. 默认 timeout 有限", 1.0 <= s.ai.timeout_seconds <= 600.0)
    ok &= _check("D3. to_dict 键集不含 api_key",
                 "api_key" not in json.dumps(s.to_dict()))
    assert ok


def _main():
    ok = True
    ok &= test_v05_file_migrates_to_v06_defaults()
    ok &= test_garbage_values_fall_back_safely()
    ok &= test_roundtrip_and_no_secret_in_file()
    ok &= test_default_settings_ai_off()
    print("RESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(_main())
