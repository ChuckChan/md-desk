"""v0.5.0 cooperative-cancel tests for ConversionWorker.

Coverage:
  * mid-batch cancel: the fake convert calls worker.cancel() from inside the
    worker thread on the second task; the current file finishes, the rest are
    never started, and batch_cancelled(success, failed) fires.
  * pre-start cancel: cancel() before start() -> batch_cancelled(0, 0) with no
    per-file signals at all.
  * static guard: worker.py never regresses to QThread.terminate().
"""

import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication

from src.worker import ConversionWorker


def _check(name, cond, detail=""):
    print(("PASS" if cond else "FAIL"), "-", name, "" if cond else f":: {detail}")
    assert cond, f"{name} :: {detail}"


class _DummyEntry:
    def __init__(self, path: str) -> None:
        self.path = path


def _flush(app):
    # Deliver cross-thread queued signals to the main thread (same pattern as
    # test_worker._run: processEvents + sendPostedEvents after w.wait()).
    app.processEvents()
    app.sendPostedEvents()


def test_cancel_mid_batch():
    app = QApplication.instance() or QApplication([])
    tasks = [(i, _DummyEntry(f"f{i}.html")) for i in range(5)]
    started, finished, progress = [], [], []
    cancelled, batch_finished = [], []

    w = ConversionWorker(tasks)
    w.file_started.connect(lambda r: started.append(r))
    w.file_finished.connect(lambda res: finished.append(res))
    w.progress.connect(lambda d, t: progress.append((d, t)))
    w.batch_cancelled.connect(lambda s, f: cancelled.append((s, f)))
    w.batch_finished.connect(lambda s, f: batch_finished.append((s, f)))

    calls = {"n": 0}

    def fake(entry, settings=None, **kwargs):
        calls["n"] += 1
        if calls["n"] == 2:
            # Runs in the worker thread; cancel() is a thread-safe Event set.
            w.cancel()
        return "# ok"

    with patch("src.worker.convert_entry", side_effect=fake):
        w.start()
        w.wait()
    _flush(app)

    _check("C1. 取消前两个任务启动", started == [0, 1], repr(started))
    _check("C2. 仅前两个任务收尾",
           [r.row for r in finished] == [0, 1],
           repr([r.row for r in finished]))
    _check("C3. batch_cancelled(2,0)",
           cancelled == [(2, 0)], repr(cancelled))
    _check("C4. batch_finished 未收到", batch_finished == [], repr(batch_finished))
    _check("C5. 进度恰好 (1,5),(2,5)", progress == [(1, 5), (2, 5)], repr(progress))
    _check("C6. is_cancelled() True", w.is_cancelled() is True)
    _check("C7. 剩余任务未启动(共2次转换)", calls["n"] == 2, f"n={calls['n']}")

    # Assert is_cancelled() BEFORE tearing the QThread C++ object down.
    w.deleteLater()
    _flush(app)


def test_cancel_before_start():
    app = QApplication.instance() or QApplication([])
    tasks = [(i, _DummyEntry(f"f{i}.html")) for i in range(3)]
    started, finished, progress = [], [], []
    cancelled, batch_finished = [], []

    w = ConversionWorker(tasks)
    w.file_started.connect(lambda r: started.append(r))
    w.file_finished.connect(lambda res: finished.append(res))
    w.progress.connect(lambda d, t: progress.append((d, t)))
    w.batch_cancelled.connect(lambda s, f: cancelled.append((s, f)))
    w.batch_finished.connect(lambda s, f: batch_finished.append((s, f)))

    w.cancel()
    with patch("src.worker.convert_entry", side_effect=lambda e, **k: "# x"):
        w.start()
        w.wait()
    _flush(app)

    _check("C8. 开始前取消 -> batch_cancelled(0,0)",
           cancelled == [(0, 0)], repr(cancelled))
    _check("C9. 无任何 file 信号", started == [] and finished == [] and progress == [],
           f"started={started} finished={finished} progress={progress}")
    _check("C10. batch_finished 未收到", batch_finished == [], repr(batch_finished))

    w.deleteLater()
    _flush(app)


def test_no_terminate():
    """Static guard: cooperative cancel must never regress to a forced kill."""
    src = (ROOT / "src" / "worker.py").read_text(encoding="utf-8")
    _check("C11. worker.py 不含 terminate", "terminate" not in src)


def main():
    test_cancel_mid_batch()
    test_cancel_before_start()
    test_no_terminate()
    print()
    print("ALL WORKER CANCEL CHECKS PASSED")
    sys.exit(0)


if __name__ == "__main__":
    main()
