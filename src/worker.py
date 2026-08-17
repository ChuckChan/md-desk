"""Background conversion worker (Stage 3).

A single QThread processes files ONE AT A TIME, in order. No concurrency,
no QThreadPool/QRunnable. It MUST NOT touch FileModel or any Widget:
it only emits signals carrying (row, data). MainWindow updates the model
and UI in the main thread upon receiving those signals.

Task shape: list of (row_index, file_path).
"""

from PySide6.QtCore import QThread, Signal

from .converter import ConversionError, convert_entry
from .engine_config import EngineConfig
from .file_entry import FileEntry
from .settings import Settings


class ConversionWorker(QThread):
    # row indices reference the FileModel as it was at batch start.
    file_started = Signal(int)                 # (row)
    file_done = Signal(int, str)               # (row, markdown)
    file_failed = Signal(int, str, str)        # (row, status_value, error_message)
    progress = Signal(int, int)                # (done, total)
    batch_finished = Signal(int, int)          # (success_count, fail_count)

    def __init__(
        self,
        tasks: list[tuple[int, FileEntry]],
        settings: Settings | None = None,
        engine_config: EngineConfig | None = None,
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
        self._success = 0
        self._failed = 0

    def run(self) -> None:  # executed in the worker thread
        total = len(self._tasks)
        done = 0
        for row, entry in self._tasks:
            self.file_started.emit(row)
            try:
                # Network access (URL entries) happens here, OFF the GUI
                # thread, so the UI stays responsive.
                markdown = convert_entry(entry, engine_config=self._engine_config)
                self.file_done.emit(row, markdown)
                self._success += 1
            except ConversionError as exc:
                self.file_failed.emit(row, exc.status.value, exc.message)
                self._failed += 1
            done += 1
            self.progress.emit(done, total)
        self.batch_finished.emit(self._success, self._failed)
