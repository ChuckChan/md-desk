"""QualityInspector unit tests (v0.4 Stage 2) + quality_enabled settings migration.

Run: python tests/test_quality.py

Covers:
  * Every inspection rule with boundary cases, emphasizing that normal short
    files, small inputs, and normal Chinese/English Markdown are NOT flagged
    (low false-positive requirement).
  * Settings migration: default OFF, old config (no key) -> OFF, explicit ON,
    save/reload round-trip, corrupt file -> OFF.

This file is intentionally Qt-free so it runs headless and fast.
"""

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.converter import OCR_ERROR_MARKER, markdown_has_ocr_error  # noqa: E402
from src.quality import QualityInspector  # noqa: E402
from src.result import QualityWarning  # noqa: E402
from src.settings import Settings  # noqa: E402


def _check(name, cond, detail=""):
    print(("PASS" if cond else "FAIL"), "-", name, "" if cond else f":: {detail}")
    return cond


def _codes(warnings):
    return {w.code for w in warnings}


# --------------------------------------------------------------------------
# QualityInspector rules
# --------------------------------------------------------------------------
def test_empty_output():
    ins = QualityInspector()
    w = ins.inspect("")
    ok = _check("EMPTY: 空字符串 -> EMPTY_OUTPUT", _codes(w) == {"EMPTY_OUTPUT"}, repr(w))
    w2 = ins.inspect("   \n\t  ")
    ok &= _check("EMPTY: 纯空白 -> EMPTY_OUTPUT", _codes(w2) == {"EMPTY_OUTPUT"})
    return ok


def test_normal_short_english_no_false_positive():
    ins = QualityInspector()
    w = ins.inspect("# Hello\n\nShort note.\n", input_size=120)
    ok = _check("FP: 英文短文本(小文件) 不误报", w == (), repr(w))
    w2 = ins.inspect("# Hello")
    ok &= _check("FP: 英文短文本(无 size) 不误报", w2 == (), repr(w2))
    return ok


def test_normal_short_chinese_no_false_positive():
    ins = QualityInspector()
    w = ins.inspect("# 标题\n\n这是一段简短的中文说明。\n", input_size=200)
    ok = _check("FP: 中文短文本(小文件) 不误报", w == (), repr(w))
    w2 = ins.inspect("# 标题")
    ok &= _check("FP: 中文短文本(无 size) 不误报", w2 == (), repr(w2))
    return ok


def test_small_file_short_output_no_false_positive():
    # A legitimately small input that yields little text must NOT be flagged.
    ins = QualityInspector()
    w = ins.inspect("ok", input_size=500)  # 500 bytes < MEDIUM tier
    ok = _check("FP: 小文件(500B)短输出 不误报", w == (), repr(w))
    return ok


def test_medium_input_tiny_output_short_warning():
    ins = QualityInspector()
    w = ins.inspect("x", input_size=3000)  # 3 KB in [MEDIUM, LARGE)
    ok = _check("SHORT: 中等输入(3KB)极少文本 -> SHORT_OUTPUT",
                _codes(w) == {"SHORT_OUTPUT"}, repr(w))
    return ok


def test_large_input_tiny_output_low_yield():
    ins = QualityInspector()
    w = ins.inspect("x", input_size=60000)
    ok = _check("LOW_YIELD: 大输入(60KB)极少文本 -> LOW_TEXT_YIELD",
                _codes(w) == {"LOW_TEXT_YIELD"}, repr(w))
    # Large input WITH real text -> no warning (normal big document).
    big = "# Title\n\n" + ("这是一段正常的长中文内容，" * 200)
    w2 = ins.inspect(big, input_size=60000)
    ok &= _check("FP: 大输入(60KB)+正常中文 不误报", w2 == (), repr(w2))
    return ok


def test_garbled_fffd():
    ins = QualityInspector()
    md = "正常开头" + "\ufffd" * 3 + "结尾"
    w = ins.inspect(md, input_size=1000)
    ok = _check("GARBLED: 3 个替换符 -> GARBLED_TEXT", _codes(w) == {"GARBLED_TEXT"}, repr(w))
    w2 = ins.inspect("正常中文 English 内容", input_size=1000)
    ok &= _check("FP: 正常中英文 不误报乱码", "GARBLED_TEXT" not in _codes(w2))
    return ok


def test_garbled_mojibake():
    ins = QualityInspector()
    # 2 classic UTF-8-as-Latin1 mojibake hits (â€œ and â€™).
    w = ins.inspect("â€œHelloâ€™ world", input_size=1000)
    ok = _check("GARBLED: mojibake 序列 -> GARBLED_TEXT", _codes(w) == {"GARBLED_TEXT"}, repr(w))
    return ok


def test_ocr_error_marker():
    ins = QualityInspector()
    md = f"# Doc\n\n正文 {OCR_ERROR_MARKER} 部分失败\n"
    w = ins.inspect(md, input_size=1000)
    ok = _check("OCR: OCR error marker -> OCR_ERROR_MARKER",
                _codes(w) == {"OCR_ERROR_MARKER"}, repr(w))
    ok &= _check("OCR: 复用 markdown_has_ocr_error", markdown_has_ocr_error(md) is True)
    return ok


def test_multiple_warnings_combined():
    ins = QualityInspector()
    # Large, garbled, tiny-text document triggers two rules.
    md = "\ufffd" * 3 + "xy"
    w = ins.inspect(md, input_size=60000)
    ok = _check("COMBINE: 大输入+乱码 同时触发",
                _codes(w) == {"LOW_TEXT_YIELD", "GARBLED_TEXT"}, repr(w))
    return ok


def test_warnings_immutable_and_typed():
    ins = QualityInspector()
    w = ins.inspect("", input_size=None)
    ok = _check("TYPE: 返回 tuple[QualityWarning]",
                isinstance(w, tuple) and all(isinstance(x, QualityWarning) for x in w),
                repr(w))
    # QualityWarning is frozen: assignment raises.
    try:
        w[0].code = "X"
        ok &= _check("TYPE: QualityWarning 不可变", False, "assignment succeeded")
    except Exception:
        ok &= _check("TYPE: QualityWarning 不可变", True)
    return ok


# --------------------------------------------------------------------------
# quality_enabled settings migration (default OFF, old config safe)
# --------------------------------------------------------------------------
def test_quality_default_off():
    s = Settings.default()
    ok = _check("SETTINGS: 默认 quality_enabled == False", s.quality_enabled is False)
    ok &= _check("SETTINGS: version 仍为 2（向后兼容）", s.version == 2, f"{s.version}")
    return ok


def test_quality_old_config_off():
    # A v0.2/0.3-style settings file WITHOUT the quality_enabled key must load
    # as OFF (safe default).
    old = {"version": 2, "youtube_transcript_languages": ["en"]}
    s = Settings.from_dict(old)
    ok = _check("SETTINGS: 旧配置(无 quality_enabled) -> False", s.quality_enabled is False)
    return ok


def test_quality_explicit_on():
    # Explicit booleans round-trip exactly.
    ok = _check("SETTINGS: 显式 True -> True",
                Settings.from_dict({"quality_enabled": True}).quality_enabled is True)
    ok &= _check("SETTINGS: 显式 False -> False",
                 Settings.from_dict({"quality_enabled": False}).quality_enabled is False)
    # bool() coercion (consistent with the existing ai.enabled field): a truthy
    # non-bool is treated as enabled, a falsy non-bool as disabled. No crash.
    ok &= _check("SETTINGS: 真值('yes') -> True (bool 强制)",
                 Settings.from_dict({"quality_enabled": "yes"}).quality_enabled is True)
    ok &= _check("SETTINGS: 假值(0) -> False (bool 强制)",
                 Settings.from_dict({"quality_enabled": 0}).quality_enabled is False)
    # Missing key is the real backward-compat guarantee (covered by
    # test_quality_old_config_off); re-asserted here for proximity.
    ok &= _check("SETTINGS: 缺失键 -> False",
                 Settings.from_dict({}).quality_enabled is False)
    return ok


def test_quality_save_reload():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "settings.json"
        s = Settings(quality_enabled=True)
        s.save(p)
        reloaded = Settings.load(p)
        ok = _check("SETTINGS: 保存->重载 保留 True",
                    reloaded.quality_enabled is True, repr(reloaded.to_dict()))
        data = json.loads(p.read_text(encoding="utf-8"))
        ok &= _check("SETTINGS: 落盘含 quality_enabled", data.get("quality_enabled") is True, repr(data))
    return ok


def test_quality_corrupt_fallback_off():
    with tempfile.TemporaryDirectory() as d:
        bad = Path(d) / "bad.json"
        bad.write_text("{ not json ", encoding="utf-8")
        s = Settings.load(bad)
        ok = _check("SETTINGS: 损坏文件 -> quality_enabled False", s.quality_enabled is False)
    return ok


def main():
    results = [
        test_empty_output(),
        test_normal_short_english_no_false_positive(),
        test_normal_short_chinese_no_false_positive(),
        test_small_file_short_output_no_false_positive(),
        test_medium_input_tiny_output_short_warning(),
        test_large_input_tiny_output_low_yield(),
        test_garbled_fffd(),
        test_garbled_mojibake(),
        test_ocr_error_marker(),
        test_multiple_warnings_combined(),
        test_warnings_immutable_and_typed(),
        test_quality_default_off(),
        test_quality_old_config_off(),
        test_quality_explicit_on(),
        test_quality_save_reload(),
        test_quality_corrupt_fallback_off(),
    ]
    ok = all(results)
    print()
    print("ALL QUALITY CHECKS PASSED" if ok else "SOME QUALITY CHECKS FAILED")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
