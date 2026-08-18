"""Background conversion worker (Stage 3, refined in v0.4 Stage 1).

A single QThread processes files ONE AT A TIME, in order. No concurrency,
no QThreadPool/QRunnable. It MUST NOT touch FileModel or any Widget:
it only emits signals carrying (row, data). MainWindow updates the model
and UI in the main thread upon receiving those signals.

The single terminal signal ``file_finished`` carries a ``ConversionResult``
that represents both success and failure. Non-terminal signals
(file_started, progress, batch_finished) are unchanged.

Task shape: list of (row_index, FileEntry).
"""

import time

from PySide6.QtCore import QThread, Signal

from .converter import ConversionError, convert_entry
from .engine_config import EngineConfig
from .file_entry import FileEntry
from .quality import QualityInspector
from .result import ConversionResult
from .settings import Settings


# Single stateless inspector instance shared by all workers (it holds no
# mutable state, so reuse is safe across threads).
_INSPECTOR = QualityInspector()


class ConversionWorker(QThread):
    # row indices reference the FileModel as it was at batch start.
    file_started = Signal(int)                 # (row)
    file_finished = Signal(ConversionResult)   # (result) — unified terminal outcome
    progress = Signal(int, int)                # (done, total)
    batch_finished = Signal(int, int)          # (success_count, fail_count)

    def __init__(
        self,
        tasks: list[tuple[int, FileEntry]],
        settings: Settings | None = None,
        engine_config: EngineConfig | None = None,
        quality_enabled: bool = False,
    ) -> None:
        super().__init__()
        self._tasks = list(tasks)
        self._settings = settings
        # Resolve the runtime engine config ONCE for the whole batch so the
        # OpenAI-compatible client (and OCR plugin registration) is shared
        # across all files instead of being rebuilt per file.
        self._engine_config = engine_config or (
            EngineConfig.from_settings(settings) if settings else EngineConfig.disabled()
        )
        # v0.4 Stage 2: optional quality inspection on successful conversions.
        # Default OFF so v0.3 / S1 behavior is byte-for-byte unchanged unless
        # the user explicitly enables it in Advanced Settings.
        self._quality_enabled = quality_enabled
        self._success = 0
        self._failed = 0

    def run(self) -> None:  # executed in the worker thread
        total = len(self._tasks)
        done = 0
        for row, entry in self._tasks:
            self.file_started.emit(row)
            t0 = time.perf_counter()
            try:
                # Network access (URL entries) happens here, OFF the GUI
                # thread, so the UI stays responsive.
                markdown = convert_entry(entry, engine_config=self._engine_config)
                duration_ms = _elapsed_ms(t0)
                # Quality is advisory only and runs solely on success. When OFF
                # (default) we skip it entirely, so the result is identical to
                # S1. When ON, we feed the output + known input size to the
                # inspector and attach any warnings to the result.
                warnings = ()
                if self._quality_enabled:
                    size = entry.size if getattr(entry, "size", 0) > 0 else None
                    warnings = _INSPECTOR.inspect(markdown, input_size=size)
                result = ConversionResult.success(
                    row, markdown, duration_ms=duration_ms, warnings=warnings
                )
            except ConversionError as exc:
                result = ConversionResult.from_error(
                    row, exc, duration_ms=_elapsed_ms(t0)
                )
            self.file_finished.emit(result)
            if result.ok:
                self._success += 1
            else:
                self._failed += 1
            done += 1
            self.progress.emit(done, total)
        self.batch_finished.emit(self._success, self._failed)


def _elapsed_ms(t0: float) -> int:
    """Milliseconds since ``t0`` (perf_counter), truncated to int."""
    return int((time.perf_counter() - t0) * 1000)
