"""Frozen-EXE runtime smoke for Stage 2 (HTTPS) + Stage 3 (URL-native).

This entry point is frozen with the SAME collection flags as the real
md-desk.exe, so it exercises the identical bundled modules:
  UrlFetchService (incl. the _PinnedTLSHTTPConnection HTTPS path) +
  MarkItDown converters + src.converter.

It proves, inside the frozen binary (no venv):
  1. real HTTPS fetch works (TLS path, server_hostname pinning)
  2. a real Stage-3 capability (RSS) converts through convert_stream
  3. SSRF is still enforced (loopback + file:// blocked)

Run: build then execute the frozen exe_stage23_smoke.exe.
"""
import sys

sys.path.insert(0, ".")
from src.converter import convert_url, ConversionError


def main() -> int:
    # 1) HTTPS works in the frozen binary (real public HTTPS endpoint)
    try:
        md = convert_url("https://example.com/")
        assert "Example Domain" in md, "unexpected markdown"
        print("HTTPS_FETCH_OK len=%d" % len(md))
    except Exception as e:  # pragma: no cover
        print("HTTPS_FETCH_FAIL %r" % e)
        return 1

    # 2) Stage-3 capability: RSS via convert_stream (no convert_uri)
    try:
        md = convert_url("https://feeds.bbci.co.uk/news/rss.xml")
        assert "BBC News" in md, "RSS not converted"
        print("CAPABILITY_RSS_OK len=%d" % len(md))
    except Exception as e:  # pragma: no cover
        print("CAPABILITY_RSS_FAIL %r" % e)
        return 1

    # 3) SSRF still enforced in the frozen binary
    try:
        convert_url("http://127.0.0.1/")
        print("SSRF_BLOCK_FAIL loopback was allowed")
        return 1
    except ConversionError as e:
        print("SSRF_BLOCK_OK status=%s" % e.status.value)
    except Exception as e:  # pragma: no cover
        print("SSRF_BLOCK_UNEXPECTED %r" % e)
        return 1

    try:
        convert_url("file:///C:/Windows/Notepad.exe")
        print("FILE_SCHEME_FAIL file:// was allowed")
        return 1
    except ConversionError as e:
        print("FILE_SCHEME_BLOCK_OK status=%s" % e.status.value)
    except Exception as e:  # pragma: no cover
        print("FILE_SCHEME_UNEXPECTED %r" % e)
        return 1

    print("ALL_FROZEN_STAGE23_CHECKS_PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
