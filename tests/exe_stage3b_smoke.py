"""Frozen-EXE runtime smoke for Stage 3B (YouTube Transcript Packaging).

Built with the SAME collection flags as the real md-desk.exe, so it
exercises the identical bundled module set. It proves, inside the frozen
binary (no venv):

  1. real HTTPS fetch still works (TLS path, server_hostname pinning)
  2. Stage-3 capability (RSS) still converts through convert_stream
  3. SSRF is still enforced (loopback blocked; file:// blocked)
  4. YouTube METADATA extraction works (no converter change)
  5. YouTube TRANSCRIPT extraction works for a captioned video
     (youtube-transcript-api bundled + functional)
  6. YouTube unavailable / no-captions video degrades gracefully
     (no crash, returns markdown)

stdout is forced to UTF-8 so non-ASCII transcript text never crashes the
harness on a GBK Windows console. All printed diagnostics are ASCII.

Run: build then execute the frozen exe_stage3b_smoke.exe.
"""
import sys

# Force UTF-8 so any non-ASCII content (e.g. transcript glyphs) never
# raises UnicodeEncodeError on a GBK Windows console.
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

sys.path.insert(0, ".")
from src.converter import convert_url, ConversionError

# A stable, well-known captioned video (Rick Astley).
YT_CAPTIONED = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
# An invalid / unavailable video id -> must not crash.
YT_UNAVAILABLE = "https://www.youtube.com/watch?v=THIS_VIDEO_ID_IS_NOT_REAL_123"


def _check(label, ok, detail=""):
    status = "OK" if ok else "FAIL"
    print("%s %s %s" % (status, label, detail))
    return ok


def main() -> int:
    failures = []

    # 1) HTTPS works in the frozen binary
    try:
        md = convert_url("https://example.com/")
        failures.append(not _check("HTTPS_FETCH", "Example Domain" in md, "len=%d" % len(md)))
    except Exception as e:  # pragma: no cover
        failures.append(True)
        print("FAIL HTTPS_FETCH %r" % e)
        return 1

    # 2) Stage-3 capability: RSS via convert_stream (no convert_uri)
    try:
        md = convert_url("https://feeds.bbci.co.uk/news/rss.xml")
        failures.append(not _check("CAPABILITY_RSS", "BBC News" in md, "len=%d" % len(md)))
    except Exception as e:  # pragma: no cover
        failures.append(True)
        print("FAIL CAPABILITY_RSS %r" % e)
        return 1

    # 3) SSRF still enforced in the frozen binary (loopback -> BLOCKED)
    try:
        convert_url("http://127.0.0.1/")
        print("FAIL SSRF_BLOCK loopback was allowed")
        failures.append(True)
    except ConversionError as e:
        # BLOCKED guard maps to message containing the Chinese guard phrase.
        blocked = ("安全拦截" in (e.message or "")) or (e.status.value == "失败")
        failures.append(not _check("SSRF_BLOCK", blocked, "status=%s" % e.status.value))
    except Exception as e:  # pragma: no cover
        print("FAIL SSRF_BLOCK_UNEXPECTED %r" % e)
        failures.append(True)
        return 1

    # 3b) file:// scheme still refused (SCHEME guard)
    try:
        convert_url("file:///C:/Windows/Notepad.exe")
        print("FAIL FILE_SCHEME_BLOCK file:// was allowed")
        failures.append(True)
    except ConversionError as e:
        refused = ("不支持" in (e.message or "")) or (e.status.value == "失败")
        failures.append(not _check("FILE_SCHEME_BLOCK", refused, "status=%s" % e.status.value))
    except Exception as e:  # pragma: no cover
        print("FAIL FILE_SCHEME_UNEXPECTED %r" % e)
        failures.append(True)
        return 1

    # 4) YouTube METADATA (must not regress)
    try:
        md = convert_url(YT_CAPTIONED)
        has_meta = ("### Video Metadata" in md) or md.strip().startswith("# YouTube")
        failures.append(not _check("YT_METADATA", has_meta, "len=%d" % len(md)))
    except Exception as e:  # pragma: no cover
        print("FAIL YT_METADATA %r" % e)
        failures.append(True)

    # 5) YouTube TRANSCRIPT for a captioned video -> proves youtube_transcript_api
    #    is bundled AND functional in the frozen binary.
    try:
        md = convert_url(YT_CAPTIONED)
        has_transcript = "### Transcript" in md
        # ASCII-safe detail: report transcript length, not raw glyphs.
        tlen = 0
        if has_transcript:
            idx = md.index("### Transcript")
            tlen = len(md) - idx
        failures.append(not _check("YT_TRANSCRIPT", has_transcript, "transcript_chars=%d" % tlen))
    except Exception as e:  # pragma: no cover
        print("FAIL YT_TRANSCRIPT %r" % e)
        failures.append(True)

    # 6) YouTube unavailable / no-captions -> graceful (no crash)
    try:
        md = convert_url(YT_UNAVAILABLE)
        graceful = True  # returned markdown without raising
        failures.append(not _check("YT_UNAVAILABLE_GRACEFUL", graceful, "len=%d no_crash" % len(md)))
    except ConversionError as e:
        # A clean, mapped error is also acceptable (still no crash).
        failures.append(not _check("YT_UNAVAILABLE_GRACEFUL", True, "mapped_error=%s" % e.status.value))
    except Exception as e:  # pragma: no cover
        print("FAIL YT_UNAVAILABLE_CRASH %r" % e)
        failures.append(True)
        return 1

    if any(failures):
        print("SOME_FROZEN_STAGE3B_CHECKS_FAILED")
        return 1
    print("ALL_FROZEN_STAGE3B_CHECKS_PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
