"""Background conversion worker (Stage 3).

A single QThread processes files ONE AT A TIME, in order. No concurrency,
no QThreadPool/QRunnable. It MUST NOT touch FileModel or any Widget:
it only emits signals carrying (row, data). MainWindow updates the model
and UI in the main thread upon receiving those signals.

Task shape: list of (row_index, file_path).
"""

from PySide6.QtCore import QThread, Signal

from .converter import ConversionError, convert_file


class ConversionWorker(QThread):
    # row indices reference the FileModel as it was at batch start.
    file_started = Signal(int)                 # (row)
    file_done = Signal(int, str)               # (row, markdown)
    file_failed = Signal(int, str, str)        # (row, status_value, error_message)
    progress = Signal(int, int)                # (done, total)
    batch_finished = Signal(int, int)          # (success_count, fail_count)

    def __init__(self, tasks: list[tuple[int, str]]) -> None:
        super().__init__()
        self._tasks = list(tasks)
        self._success = 0
        self._failed = 0

    def run(self) -> None:  # executed in the worker thread
        total = len(self._tasks)
        done = 0
        for row, path in self._tasks:
            self.file_started.emit(row)
            try:
                markdown = convert_file(path)
                self.file_done.emit(row, markdown)
                self._success += 1
            except ConversionError as exc:
                self.file_failed.emit(row, exc.status.value, exc.message)
                self._failed += 1
            done += 1
            self.progress.emit(done, total)
        self.batch_finished.emit(self._success, self._failed)
