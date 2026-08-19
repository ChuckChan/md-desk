"""Real batch-path test: youtube_transcript_languages must reach the engine.

Regression test for the v0.4.1 fix. ``ConversionWorker`` previously passed only
``engine_config`` to ``convert_entry`` and omitted ``settings``, so a user's
``youtube_transcript_languages`` (configured in Advanced Settings) never reached
the conversion chain during a *real* batch run. This test drives the actual
worker thread with the network fetch and the engine factory mocked, and asserts
the engine receives the kwarg through the full worker -> convert_entry ->
convert_url -> engine path.
"""

import io
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication

from src.engine_config import EngineConfig
from src.file_entry import FileEntry
from src.settings import Settings
from src.worker import ConversionWorker


class _FakeEngine:
    """Records the StreamInfo + kwargs handed to the conversion engine."""

    def __init__(self):
        self.calls = []

    def convert_stream(self, stream, stream_info=None, **kwargs):
        self.calls.append((stream_info, dict(kwargs)))
        return type("R", (), {"markdown": "# Converted\n\nyt markdown"})

    def convert(self, path):
        self.calls.append((None, {"path": path}))
        return type("R", (), {"markdown": "# Converted"})


class _FakeFetchService:
    """Returns canned HTML for any URL so convert_url runs without network."""

    def fetch(self, url):
        from markitdown import StreamInfo

        si = StreamInfo(
            url=url, filename="watch.html", extension=".html", mimetype="text/html"
        )
        return type(
            "FetchResult",
            (),
            {
                "content": io.BytesIO(b"<html><body>yt</body></html>"),
                "stream_info": si,
                "final_url": url,
                "status_code": 200,
            },
        )()


def _run_worker_to_completion(worker):
    """Start the worker thread, block until done, then flush/clean up."""
    app = QApplication.instance() or QApplication([])
    worker.start()
    worker.wait()
    # Destroy the QThread handle so it does not linger in the pytest process
    # (root cause of the Windows subprocess pipe-EOF deadlock seen in other
    # worker tests when later tests spawn children).
    worker.deleteLater()
    app.processEvents()
    app.sendPostedEvents()


def test_worker_forwards_youtube_languages_to_engine():
    settings = Settings.default()
    settings.youtube_transcript_languages = ["zh-Hans", "en"]

    entry = FileEntry.from_url("https://www.youtube.com/watch?v=v041fix")
    worker = ConversionWorker(
        [(0, entry)],
        settings=settings,
        engine_config=EngineConfig.disabled(),
    )

    eng = _FakeEngine()
    with patch(
        "src.markitdown_factory.MarkItDownFactory.create", return_value=eng
    ), patch("src.converter.UrlFetchService", _FakeFetchService):
        _run_worker_to_completion(worker)

    # The batch path must have succeeded...
    assert worker._success == 1, f"expected 1 success, got {worker._success}"
    # ...and the engine must have been called with the user's languages.
    assert eng.calls, "engine was never called"
    kwargs = eng.calls[0][1]
    assert (
        kwargs.get("youtube_transcript_languages") == ["zh-Hans", "en"]
    ), kwargs


def test_worker_omits_youtube_languages_when_empty():
    settings = Settings.default()  # empty languages -> legacy behavior

    entry = FileEntry.from_url("https://www.youtube.com/watch?v=empty")
    worker = ConversionWorker(
        [(0, entry)],
        settings=settings,
        engine_config=EngineConfig.disabled(),
    )

    eng = _FakeEngine()
    with patch(
        "src.markitdown_factory.MarkItDownFactory.create", return_value=eng
    ), patch("src.converter.UrlFetchService", _FakeFetchService):
        _run_worker_to_completion(worker)

    assert worker._success == 1
    kwargs = eng.calls[0][1]
    # No languages configured => the kwarg must NOT be forwarded (byte-for-byte
    # identical to the v0.4 default-off behavior).
    assert "youtube_transcript_languages" not in kwargs, kwargs
