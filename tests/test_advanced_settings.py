"""Stage 4 (Advanced Conversion Settings) verification.

Run:python tests/test_advanced_settings.py

Covers the Stage 4 requirements:
  1. default settings -> existing conversion behavior unchanged
  2. settings save -> reload -> consistent
  3. corrupt / wrong-typed config -> safe fallback to defaults (no crash)
  4. StreamInfo extension override reaches the engine (mechanism, mocked)
  5. StreamInfo MIME override reaches the engine (mechanism, mocked)
  6. StreamInfo charset override reaches the engine (mechanism, mocked)
  7. mislabeled-extension fixture (.csv actually plain text) converts via
     PlainText after an .txt override (end-to-end, real markitdown)
  8. regression gate over network-free existing suites
  (Build PASS and Frozen-EXE settings/runtime PASS are covered by the
   build step + exe_stage4_smoke.py, not this unit file.)

This file is intentionally Qt-free so it runs headless and fast.
"""

import io
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from markitdown import StreamInfo  # noqa: E402

from src.converter import convert_entry, convert_file, convert_url  # noqa: E402
from src.file_entry import FileEntry, FileStatus  # noqa: E402
from src.settings import Settings, StreamInfoOverride  # noqa: E402

TEST_INPUT = ROOT.parent / "test_input.html"


def _check(name, cond, detail=""):
    print(("PASS" if cond else "FAIL"), "-", name, "" if cond else f":: {detail}")
    return cond


# --------------------------------------------------------------------------
# 1. default settings -> existing behavior unchanged
# --------------------------------------------------------------------------
def test_default_unchanged():
    assert TEST_INPUT.exists(), f"missing {TEST_INPUT}"
    # No override path must be byte-for-byte the legacy MarkItDown().convert()
    md_legacy = convert_file(str(TEST_INPUT))
    md_default = convert_file(str(TEST_INPUT), override=None)
    ok = _check("1. 默认（无覆盖）与遗留转换一致",
                isinstance(md_legacy, str) and md_legacy == md_default and len(md_legacy) > 0,
                f"len1={len(md_legacy)} len2={len(md_default)}")
    # A default Settings object must not inject any youtube kwarg.
    s = Settings.default()
    ok &= _check("1b. 默认设置不含字幕语言", s.youtube_transcript_languages == [],
                 repr(s.youtube_transcript_languages))
    return ok


# --------------------------------------------------------------------------
# 2. save -> reload -> consistent
# --------------------------------------------------------------------------
def test_save_reload():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "settings.json"
        s = Settings(youtube_transcript_languages=["zh-Hans", "en", "ja"])
        s.save(p)
        reloaded = Settings.load(p)
        ok = _check("2. 保存->重载 一致",
                    reloaded.youtube_transcript_languages == ["zh-Hans", "en", "ja"]
                    and reloaded.version == s.version,
                    f"reloaded={reloaded.to_dict()}")
        # file actually exists and is valid json with expected keys
        ok &= _check("2b. 落盘 JSON 可读",
                     p.exists() and isinstance(json.loads(p.read_text(encoding="utf-8")), dict))
    return ok


# --------------------------------------------------------------------------
# 3. corrupt / wrong-typed config -> safe fallback
# --------------------------------------------------------------------------
def test_corrupt_fallback():
    ok = True
    with tempfile.TemporaryDirectory() as d:
        # (a) invalid JSON
        bad = Path(d) / "bad1.json"
        bad.write_text("{ this is : not json ", encoding="utf-8")
        s1 = Settings.load(bad)
        ok &= _check("3a. 非法 JSON -> 默认且未崩溃",
                     s1.youtube_transcript_languages == [] and s1.version == 1,
                     f"{s1.to_dict()}")

        # (b) wrong-typed languages (not a list)
        bad2 = Path(d) / "bad2.json"
        bad2.write_text(json.dumps({"youtube_transcript_languages": "en"}), encoding="utf-8")
        s2 = Settings.load(bad2)
        ok &= _check("3b. 类型错误(非 list) -> 默认",
                     s2.youtube_transcript_languages == [], f"{s2.to_dict()}")

        # (c) languages list containing non-strings -> dropped
        bad3 = Path(d) / "bad3.json"
        bad3.write_text(json.dumps({"youtube_transcript_languages": ["en", 123, "", "  ja  "]}),
                        encoding="utf-8")
        s3 = Settings.load(bad3)
        ok &= _check("3c. 非字符串/空字符串被剔除",
                     s3.youtube_transcript_languages == ["en", "ja"], f"{s3.to_dict()}")

        # (d) missing file -> defaults (first start)
        s4 = Settings.load(Path(d) / "does_not_exist.json")
        ok &= _check("3d. 缺失文件 -> 默认（首次启动）",
                     s4.youtube_transcript_languages == [])
    return ok


# --------------------------------------------------------------------------
# 4-6. override mechanism reaches the engine (mocked, no network/no real parse)
# --------------------------------------------------------------------------
class _FakeFetchService:
    def fetch(self, url):
        si = StreamInfo(url=url, filename="remote.bin", extension=".bin",
                        mimetype="application/octet-stream")
        return type("FetchResult", (), {
            "content": io.BytesIO(b"dummy"),
            "stream_info": si,
            "final_url": url,
            "status_code": 200,
        })()


def test_extension_override_mechanism():
    ov = StreamInfoOverride(extension=".txt")
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tf:
        tf.write(b"hello,world\n")  # content irrelevant; engine is mocked
        path = tf.name
    try:
        with patch("src.converter.MarkItDown") as M:
            M.return_value.convert_stream.return_value = type("R", (), {"markdown": "x"})()
            convert_file(path, override=ov)
            args, kwargs = M.return_value.convert_stream.call_args
            passed_si = kwargs.get("stream_info")
            ok = _check("4. 扩展名覆盖到达引擎",
                        passed_si is not None and passed_si.extension == ".txt",
                        f"si={passed_si}")
    finally:
        os.unlink(path)
    return ok


def test_mime_override_mechanism():
    ov = StreamInfoOverride(mimetype="text/plain")
    with tempfile.NamedTemporaryFile(suffix=".bin", delete=False) as tf:
        tf.write(b"data")
        path = tf.name
    try:
        with patch("src.converter.MarkItDown") as M:
            M.return_value.convert_stream.return_value = type("R", (), {"markdown": "x"})()
            convert_file(path, override=ov)
            _, kwargs = M.return_value.convert_stream.call_args
            passed_si = kwargs.get("stream_info")
            ok = _check("5. MIME 覆盖到达引擎",
                        passed_si is not None and passed_si.mimetype == "text/plain",
                        f"si={passed_si}")
    finally:
        os.unlink(path)
    return ok


def test_charset_and_youtube_override_mechanism():
    ov = StreamInfoOverride(charset="latin-1")
    with patch("src.converter.UrlFetchService", _FakeFetchService), \
         patch("src.converter.MarkItDown") as M:
        M.return_value.convert_stream.return_value = type("R", (), {"markdown": "x"})()
        convert_url("https://example.com/x.bin",
                    override=ov,
                    youtube_languages=["zh-Hans", "en"])
        _, kwargs = M.return_value.convert_stream.call_args
        passed_si = kwargs.get("stream_info")
        yt = kwargs.get("youtube_transcript_languages")
        ok = _check("6. 字符编码覆盖到达引擎",
                    passed_si is not None and passed_si.charset == "latin-1", f"si={passed_si}")
        ok &= _check("6b. 字幕语言 kwarg 转发到引擎",
                     yt == ["zh-Hans", "en"], repr(yt))
        ok &= _check("6c. URL 元数据在覆盖后仍保留",
                     passed_si is not None and passed_si.url == "https://example.com/x.bin",
                     f"si={passed_si}")

    # When languages is empty/None, the kwarg must NOT be forwarded
    # (preserves legacy behavior).
    with patch("src.converter.UrlFetchService", _FakeFetchService), \
         patch("src.converter.MarkItDown") as M:
        M.return_value.convert_stream.return_value = type("R", (), {"markdown": "x"})()
        convert_url("https://example.com/y.bin", youtube_languages=[])
        _, kwargs = M.return_value.convert_stream.call_args
        ok &= _check("6d. 空语言列表时不转发 kwarg（保持遗留行为）",
                     "youtube_transcript_languages" not in kwargs, repr(kwargs))
    return ok


# --------------------------------------------------------------------------
# 7. mislabeled-extension fixture converts correctly after override (real)
# --------------------------------------------------------------------------
def test_mislabeled_extension_fixture():
    raw = "Hello world\nThis is plain text content, not a spreadsheet.\n"
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "data.csv"  # mislabeled: actually plain text
        p.write_text(raw, encoding="utf-8")

        # Default: routes to the CSV converter (output != raw text).
        default_md = convert_file(str(p))
        # Override extension -> .txt: routes to PlainText (raw passthrough).
        override_md = convert_file(str(p), override=StreamInfoOverride(extension=".txt"))

        ok = _check("7. 默认 .csv 误标 -> 走 CSV 转换（!= 原文）",
                    default_md.strip() != raw.strip(), repr(default_md[:80]))
        ok &= _check("7b. 覆盖为 .txt -> PlainText 原文透传",
                     override_md.strip() == raw.strip(),
                     f"got={override_md!r} want={raw!r}")
    return ok


# --------------------------------------------------------------------------
# 8. regression gate (network-free existing suites)
# --------------------------------------------------------------------------
def test_regression():
    # Network-free regression suites that validate Stage 4 changes and the
    # MSG/EPUB/ZIP/TXT/JSON/XML format matrix. (URL/YouTube-native live probes
    # require network and are exercised by the frozen-EXE smoke instead.)
    # test_stage4/test_stage5 are intentionally excluded: they test unrelated
    # features and carry a pre-existing interpreter-shutdown hang (a lingering
    # non-daemon QThread) plus nested regression gates.
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    suites = [
        "test_converter.py",
        "test_worker.py",
        "test_stage3_integration.py",
        "test_regression_formats.py",
    ]
    ok = True
    for name in suites:
        r = subprocess.run([sys.executable, str(ROOT / "tests" / name)],
                           capture_output=True, text=True, env=env)
        last = (r.stdout.strip().splitlines() or [""])[-1]
        ok &= _check(f"8. 回归 {name}", r.returncode == 0,
                     last if r.returncode == 0 else r.stderr[-300:])
    return ok


def main():
    results = [
        test_default_unchanged(),
        test_save_reload(),
        test_corrupt_fallback(),
        test_extension_override_mechanism(),
        test_mime_override_mechanism(),
        test_charset_and_youtube_override_mechanism(),
        test_mislabeled_extension_fixture(),
        test_regression(),
    ]
    ok = all(results)
    print()
    print("ALL STAGE 4 (ADVANCED SETTINGS) CHECKS PASSED" if ok
          else "SOME STAGE 4 (ADVANCED SETTINGS) CHECKS FAILED")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
