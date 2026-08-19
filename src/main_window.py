"""Main application window.

Layout (Stage 2):
    +-------------------------------------------+
    | MdDesk                        |
    +------------------+------------------------+
    | 文件列表(工具栏+表格) | 内容区域(占位)    |
    +------------------+------------------------+
    | 状态栏: 共 N 个文件                       |
    +-------------------------------------------+

Left  (file area)   : FileTableView + FileModel + toolbar (add/remove/clear,
                      add folder / convert selected / retry failed / cancel),
                      accepts Windows Explorer drag-drop of local files and
                      directories (folders are scanned recursively).
Right (content area): placeholder for later stages.
Bottom              : status bar showing file count.

Architecture: MainWindow -> QTableView -> FileModel -> FileEntry,
and MainWindow -> ConversionWorker (QThread) -> converter -> MarkItDown.
MainWindow must NOT import markitdown directly; it drives conversion via the
worker and only updates FileModel/UI from worker signals (main thread).
"""

import os
import time
from pathlib import Path

from PySide6.QtCore import QFileInfo, QModelIndex, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QFileDialog,
    QHeaderView,
    QHBoxLayout,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QStatusBar,
    QTabWidget,
    QTableView,
    QTextBrowser,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from .advanced_settings_dialog import AdvancedSettingsDialog
from .batch_summary import summarize, summary_message
from .diagnostics_panel import DiagnosticsPanel
from .engine_config import EngineConfig
from .export_service import export_batch
from .file_entry import FileStatus
from .file_model import FileModel
from .report import DiagnosticLogger, ReportBuilder
from .result import ConversionResult
from .settings import Settings
from .worker import ConversionWorker


class FileTableView(QTableView):
    """QTableView that also accepts Windows Explorer file/folder drag-drop.

    Emits files_dropped(list_of_local_paths). Both local files and folders
    are accepted; folders are scanned recursively by the main window
    (the directories themselves are never added as conversion entries).
    """

    files_dropped = Signal(list)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setAlternatingRowColors(True)
        self.setShowGrid(False)
        self.verticalHeader().setVisible(False)

        header = self.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)

    def dragEnterEvent(self, event):  # noqa: N802
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):  # noqa: N802
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):  # noqa: N802
        paths = self.extract_local_files(event.mimeData())
        if paths:
            self.files_dropped.emit(paths)
            event.acceptProposedAction()
        else:
            event.ignore()

    @staticmethod
    def extract_local_files(mime) -> list[str]:
        """From dropped MIME data, return all local file and directory paths.

        Directories are kept (not expanded here): the main window routes them
        through ``add_folder`` for recursive scanning.
        """
        out: list[str] = []
        if not mime.hasUrls():
            return out
        for url in mime.urls():
            if url.isLocalFile():
                local = url.toLocalFile()
                if QFileInfo(local).isFile() or QFileInfo(local).isDir():
                    out.append(local)
        return out


class MainWindow(QMainWindow):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("MdDesk")
        self.resize(1000, 700)
        self._model = FileModel()
        self._worker: ConversionWorker | None = None
        self._converting = False
        self._current_row: int | None = None
        # v0.5.0: last batch summary (for later use), batch start timestamp,
        # and the row indices of the CURRENT batch's tasks (used so the batch
        # summary counts only this batch's rows, never outside rows).
        self._last_summary = None
        self._batch_t0 = 0.0
        self._batch_rows: list[int] = []
        # Stage 4: load persisted settings (first start -> defaults; corrupt ->
        # defaults). Never raises.
        self._settings = Settings.load()
        # v0.4 Stage 3: lightweight diagnostic logger. Created once; writing
        # never affects conversion (all failures are swallowed inside it).
        self._diag_logger = DiagnosticLogger()
        self._build_layout()
        self._show_entry(None)
        self._update_status()
        self._update_action_states()

    def _build_layout(self) -> None:
        splitter = QSplitter(Qt.Orientation.Horizontal)

        splitter.addWidget(self._build_file_panel())

        self.content_area = self._build_content_panel()
        splitter.addWidget(self.content_area)

        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        splitter.setSizes([340, 660])

        self.setCentralWidget(splitter)

        status = QStatusBar(self)
        self.setStatusBar(status)

    def _build_file_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)

        # Minimal URL entry (Stage 2): a single line + "添加 URL" button.
        url_row = QHBoxLayout()
        self._url_edit = QLineEdit()
        self._url_edit.setPlaceholderText("粘贴 http/https 链接，例如 https://example.com/page.html")
        self._url_edit.returnPressed.connect(self._on_add_url)
        self._act_add_url = QPushButton("添加 URL")
        self._act_add_url.clicked.connect(self._on_add_url)
        url_row.addWidget(self._url_edit, 1)
        url_row.addWidget(self._act_add_url)
        layout.addLayout(url_row)

        toolbar = QToolBar()
        toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self._act_add = toolbar.addAction("添加文件")
        self._act_add.triggered.connect(self._on_add_files)
        self._act_remove = toolbar.addAction("移除选中")
        self._act_remove.triggered.connect(self._on_remove_selected)
        self._act_clear = toolbar.addAction("清空")
        self._act_clear.triggered.connect(self._on_clear)
        self._act_add_folder = toolbar.addAction("添加文件夹")
        self._act_add_folder.triggered.connect(self._on_add_folder)
        self._act_convert_selected = toolbar.addAction("转换选中")
        self._act_convert_selected.triggered.connect(self._on_convert_selected)
        self._act_retry_failed = toolbar.addAction("重试失败")
        self._act_retry_failed.triggered.connect(self._on_retry_failed)
        self._act_convert = toolbar.addAction("开始转换")
        self._act_convert.triggered.connect(self.start_conversion)
        self._act_cancel = toolbar.addAction("取消")
        self._act_cancel.triggered.connect(self._on_cancel)
        self._act_advanced = toolbar.addAction("高级设置")
        self._act_advanced.triggered.connect(self._on_advanced_settings)

        self._table = FileTableView()
        self._table.setModel(self._model)
        self._table.files_dropped.connect(self._on_files_dropped)
        self._table.selectionModel().selectionChanged.connect(self._on_selection_changed)

        layout.addWidget(toolbar)
        layout.addWidget(self._table, 1)
        return panel

    # ---- URL entry (Stage 2) ----
    def _on_add_url(self) -> None:
        if self._converting:
            return
        url = self._url_edit.text().strip()
        if not url:
            return
        added, _ = self._model.add_url(url)
        if added:
            self._url_edit.clear()
            self._update_status()
        else:
            QMessageBox.warning(self, "无法添加链接", "仅支持 http/https 链接，且不能重复添加。")

    # ---- handlers ----
    def _on_add_files(self) -> None:
        if self._converting:
            return
        files, _ = QFileDialog.getOpenFileNames(self, "选择文件", "", "所有文件 (*.*)")
        if files:
            self._model.add_paths(files)
            self._update_status()
            self._update_action_states()

    def _on_files_dropped(self, paths: list[str]) -> None:
        if self._converting:
            return
        # Files keep their existing behavior; directories are scanned
        # recursively. Mixed drops are supported.
        for p in paths:
            if QFileInfo(p).isDir():
                self._model.add_folder(p)
            else:
                self._model.add_paths([p])
        self._update_status()
        self._update_action_states()

    def _on_add_folder(self) -> None:
        if self._converting:
            return
        dir_path = QFileDialog.getExistingDirectory(self, "选择文件夹")
        if not dir_path:
            return
        added, skipped = self._model.add_folder(dir_path)
        self._update_status()
        self._update_action_states()
        self.statusBar().showMessage(f"已添加文件夹：新增 {added} 个文件，跳过 {skipped} 个")

    def _on_remove_selected(self) -> None:
        if self._converting:
            return
        indexes = self._table.selectionModel().selectedRows()
        rows = sorted({i.row() for i in indexes}, reverse=True)
        for r in rows:
            self._model.removeRows(r, 1)
        self._update_status()
        self._update_action_states()

    def _on_clear(self) -> None:
        if self._converting:
            return
        self._model.clear()
        self._update_status()
        self._update_action_states()

    # ---- advanced settings (Stage 4) ----
    def _on_advanced_settings(self) -> None:
        if self._converting:
            return
        # Operate on the currently selected entry, if any.
        entry = self._model.entry_at(self._current_row) if self._current_row is not None else None
        dialog = AdvancedSettingsDialog(self._settings, entry, self)
        if dialog.exec() == AdvancedSettingsDialog.DialogCode.Accepted:
            # If the user changed the selected entry's override, mark it as
            # needing re-conversion so the stale result is not shown as DONE.
            if entry is not None and entry.stream_info_override is not None:
                self._model.set_status(self._current_row, FileStatus.WAITING)
                e = self._model.entry_at(self._current_row)
                if e is not None:
                    e.markdown = None
                    e.error_message = None
                self._show_entry(self._current_row)

    # ---- conversion (Stage 3, batch flow extracted in v0.5.0) ----
    def start_conversion(self) -> None:
        """Convert every file in the list, sequentially, in a worker thread.

        GUI thread stays responsive; only one batch may run at a time.
        Queued files stay WAITING until their file_started signal fires.
        """
        if self._converting or self._model.rowCount() == 0:
            return
        total = self._model.rowCount()
        tasks = [(row, self._model.entry_at(row)) for row in range(total)]
        self._start_batch(tasks)

    def _start_batch(self, tasks) -> None:
        """Start one sequential batch from the given (row, entry) tasks."""
        if self._converting or not tasks:
            return
        total = len(tasks)
        self._batch_rows = [row for row, _ in tasks]
        self._set_converting(True)
        self.statusBar().showMessage(f"准备转换 {total} 个文件…")

        # Resolve the runtime engine config ONCE (v0.3). If AI is enabled AND
        # the user wants OCR but the official OCR plugin is missing, surface a
        # clear, non-fatal warning: image description still works, only
        # scan/OCR is unavailable. (v0.6: respects the independent OCR toggle.)
        engine_config = EngineConfig.from_settings(self._settings)
        if (engine_config.ai_enabled
                and not (engine_config.ai_model or "").strip()):
            # Non-modal on purpose: a modal QMessageBox here would block
            # headless/automated runs forever whenever the persisted settings
            # have AI on with an empty model, and would re-prompt on every
            # batch. Per-file AI failures already surface as
            # AI_PROVIDER_FAILURE warnings in the result/report.
            self.statusBar().showMessage(
                "AI 已启用但未配置模型名：OCR 与图片描述将不可用（高级设置 → AI）",
                10000,
            )
        if (engine_config.ai_enabled and engine_config.ai_ocr_enabled
                and not engine_config.ocr_plugin_available):
            QMessageBox.warning(
                self,
                "AI 已启用，但 OCR 插件缺失",
                "AI 已启用，但未找到官方 markitdown-ocr 插件：\n"
                "扫描件 / 图片中的文字将无法识别（OCR 不可用）。\n"
                "图片描述（LLM）仍可使用。请确认 markitdown-ocr 已安装。",
            )

        self._worker = ConversionWorker(
            tasks, engine_config=engine_config,
            quality_enabled=self._settings.quality_enabled,
        )
        self._worker.file_started.connect(self._on_file_started)
        self._worker.file_finished.connect(self._on_file_finished)
        self._worker.progress.connect(self._on_progress)
        self._worker.batch_finished.connect(self._on_batch_finished)
        self._worker.batch_cancelled.connect(self._on_batch_cancelled)
        self._batch_t0 = time.perf_counter()
        self._worker.start()

    def _on_convert_selected(self) -> None:
        """Convert only the currently selected rows (reset to WAITING first)."""
        if self._converting:
            return
        rows = [i.row() for i in self._table.selectionModel().selectedRows()]
        tasks = self._model.tasks_for_rows(rows)
        if not tasks:
            return
        self._reset_rows([r for r, _ in tasks])
        self._start_batch(tasks)

    def _on_retry_failed(self) -> None:
        """Re-run every ERROR / UNSUPPORTED row (reset to WAITING first)."""
        if self._converting:
            return
        rows = self._model.retryable_rows()
        if not rows:
            return
        self._reset_rows(rows)
        self._start_batch(self._model.tasks_for_rows(rows))

    def _on_cancel(self) -> None:
        """Cooperative cancel: the current file finishes, the rest are skipped."""
        if self._worker is not None:
            self._worker.cancel()
            self.statusBar().showMessage("正在取消…")

    def _reset_rows(self, rows) -> None:
        """Reset rows to WAITING and drop stale results / reports.

        ``set_result`` only applies non-None values, so stale fields are
        cleared by mutating the entry directly.
        """
        for row in rows:
            self._model.set_status(row, FileStatus.WAITING)
            entry = self._model.entry_at(row)
            if entry is not None:
                entry.markdown = None
                entry.error_message = None
            self._model.set_report(row, None)

    def _finish_batch(self, cancelled: bool) -> None:
        """Tear down a finished (or cancelled) batch and summarize it.

        The summary counts ONLY the rows this batch was given (``_batch_rows``),
        so a convert-selected / retry-failed batch never mixes in rows that
        were not part of it.
        """
        self._set_converting(False)
        elapsed = int((time.perf_counter() - self._batch_t0) * 1000)
        entries = [self._model.entry_at(r) for r in self._batch_rows
                   if self._model.entry_at(r) is not None]
        summary = summarize(entries, elapsed)
        self._last_summary = summary
        self.statusBar().showMessage(summary_message(summary, cancelled=cancelled))
        if self._worker is not None:
            self._worker.deleteLater()
            self._worker = None
        self._update_action_states()

    def _on_file_started(self, row: int) -> None:
        self._model.set_status(row, FileStatus.PROCESSING)
        entry = self._model.entry_at(row)
        name = entry.filename if entry else f"#{row}"
        self.statusBar().showMessage(f"正在转换: {name}")

    def _on_file_finished(self, result: ConversionResult) -> None:
        """Unified terminal handler for both success and failure.

        On success the entry is marked DONE and its markdown stored; on failure
        the mapped status (ERROR / UNSUPPORTED) is applied and the friendly
        error message stored. The stable ``result.row`` is the only handle
        used to locate the entry — no "current task" guessing.
        """
        self._model.set_status(result.row, result.status)
        if result.ok:
            self._model.set_result(result.row, markdown=result.markdown)
        else:
            self._model.set_result(result.row, error_message=result.error_message)
        # v0.4 Stage 3/4: build + persist a diagnostic report (store it ON the
        # entry, then append one log line). Non-invasive side-effect: failures
        # here are swallowed so conversion and UI are never affected. The
        # worker is untouched.
        self._record_diagnostic(result)
        # Refresh the panel for the selected row AFTER the report is attached,
        # so it shows the just-finished conversion's diagnostics.
        if result.row == self._current_row:
            self._show_entry(result.row)
        # Context actions (e.g. retry) may have become enabled/disabled.
        self._update_action_states()

    def _record_diagnostic(self, result: ConversionResult) -> None:
        """Build a ``ConversionReport`` and persist it.

        Stores the report on the entry (lifecycle-safe: delete / clear /
        re-batch drop or replace it with the entry) and appends one diagnostic
        log line. Pure side-effect — any failure is swallowed.
        """
        try:
            entry = self._model.entry_at(result.row)
            report = ReportBuilder.build(result, entry)
            self._model.set_report(result.row, report)
            self._diag_logger.record(report)
        except Exception:  # noqa: BLE001 - logging must never break conversion
            pass

    def _on_progress(self, done: int, total: int) -> None:
        self.statusBar().showMessage(f"已完成 {done} / {total}")

    def _on_batch_finished(self, success: int, failed: int) -> None:
        self._finish_batch(False)

    def _on_batch_cancelled(self, success: int, failed: int) -> None:
        self._finish_batch(True)

    def _set_converting(self, on: bool) -> None:
        self._converting = on
        for act in (
            self._act_add,
            self._act_remove,
            self._act_clear,
            self._act_convert,
            self._act_advanced,
            self._act_add_folder,
            self._act_convert_selected,
            self._act_retry_failed,
            self._act_export_batch,
        ):
            act.setEnabled(not on)
        self._act_cancel.setEnabled(on)
        self._url_edit.setEnabled(not on)
        self._act_add_url.setEnabled(not on)

    def _update_action_states(self) -> None:
        """Enable/disable context-sensitive batch actions (v0.5.0)."""
        converting = self._converting
        selected = self._table.selectionModel().selectedRows()
        self._act_convert_selected.setEnabled(not converting and bool(selected))
        self._act_retry_failed.setEnabled(
            not converting and bool(self._model.retryable_rows())
        )
        self._act_export_batch.setEnabled(
            not converting and bool(self._model.done_rows())
        )
        self._act_cancel.setEnabled(converting)

    # ---- right panel: source / preview (Stage 4) ----
    def _build_content_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)

        bar = QToolBar()
        bar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self._act_copy = bar.addAction("复制 Markdown")
        self._act_copy.triggered.connect(self._on_copy)
        self._act_export = bar.addAction("导出 .md")
        self._act_export.triggered.connect(self._on_export)
        self._act_export_batch = bar.addAction("批量导出")
        self._act_export_batch.triggered.connect(self._on_export_batch)

        tabs = QTabWidget()
        self._source_view = QPlainTextEdit()
        self._source_view.setReadOnly(True)
        tabs.addTab(self._source_view, "Markdown 源码")
        self._preview_view = QTextBrowser()
        tabs.addTab(self._preview_view, "渲染预览")
        # Stage 4 (v0.4): lightweight diagnostics tab. It consumes the entry's
        # ConversionReport directly (no log reading, no Markdown body copy),
        # keeping the main window's default source/preview tabs clean.
        self._diag_panel = DiagnosticsPanel(log_path=self._diag_logger.log_path)
        tabs.addTab(self._diag_panel, "诊断")

        layout.addWidget(bar)
        layout.addWidget(tabs, 1)
        return panel

    def _on_selection_changed(self, selected, deselected) -> None:
        rows = self._table.selectionModel().selectedRows()
        if rows:
            self._current_row = rows[0].row()
            self._show_entry(self._current_row)
        else:
            self._current_row = None
            self._show_entry(None)
        self._update_action_states()

    def _show_entry(self, row: int | None) -> None:
        if row is None or row < 0 or row >= self._model.rowCount():
            self._source_view.setPlainText("未选择文件")
            self._preview_view.setMarkdown("")
            self._diag_panel.clear()
            return
        entry = self._model.entry_at(row)
        if entry is None:
            self._source_view.setPlainText("未选择文件")
            self._preview_view.setMarkdown("")
            self._diag_panel.clear()
            return
        if entry.status == FileStatus.DONE:
            md = entry.markdown or ""
            self._source_view.setPlainText(md)
            self._preview_view.setMarkdown(md)
        elif entry.status in (FileStatus.ERROR, FileStatus.UNSUPPORTED):
            msg = entry.error_message or "未知错误"
            self._source_view.setPlainText(f"转换失败（{entry.status.value}）:\n{msg}")
            self._preview_view.setMarkdown(f"**转换失败（{entry.status.value}）**\n\n{msg}")
        elif entry.status == FileStatus.PROCESSING:
            self._source_view.setPlainText("转换中…")
            self._preview_view.setMarkdown("转换中…")
        else:  # WAITING
            self._source_view.setPlainText("等待转换")
            self._preview_view.setMarkdown("等待转换")
        # Stage 4: feed the diagnostics panel the entry's current report
        # (None when not yet converted). The panel never reads the log file.
        self._diag_panel.show_report(entry.report)
        self._update_actions()

    # ---- copy / export (Stage 5) ----
    def _update_actions(self) -> None:
        enabled = False
        if self._current_row is not None:
            entry = self._model.entry_at(self._current_row)
            enabled = entry is not None and entry.status == FileStatus.DONE and bool(entry.markdown)
        self._act_copy.setEnabled(enabled)
        self._act_export.setEnabled(enabled)

    def _on_copy(self) -> None:
        entry = self._current_entry()
        if entry is None or entry.status != FileStatus.DONE or not entry.markdown:
            return
        QApplication.clipboard().setText(entry.markdown)
        self.statusBar().showMessage("已复制 Markdown 到剪贴板")

    def _on_export(self) -> None:
        entry = self._current_entry()
        if entry is None or entry.status != FileStatus.DONE or not entry.markdown:
            return
        default_name = Path(entry.filename).stem + ".md"
        path, _ = QFileDialog.getSaveFileName(self, "导出 Markdown", default_name, "Markdown 文件 (*.md)")
        if not path:
            return  # user cancelled
        # URL-backed entries have no local source file to overwrite.
        if not entry.is_url and os.path.abspath(path) == os.path.abspath(entry.path):
            self.statusBar().showMessage("不能覆盖源文件")
            return
        try:
            Path(path).write_text(entry.markdown, encoding="utf-8")
        except OSError as e:
            QMessageBox.critical(self, "导出失败", f"写入失败：{e}")
            return
        self.statusBar().showMessage(f"已导出：{path}")

    def _on_export_batch(self) -> None:
        """Export all DONE entries to a chosen directory (v0.5.0)."""
        if self._converting:
            return
        out_dir = QFileDialog.getExistingDirectory(self, "选择导出目录")
        if not out_dir:
            return  # user cancelled
        entries = [self._model.entry_at(r) for r in range(self._model.rowCount())]
        res = export_batch(entries, out_dir)
        self.statusBar().showMessage(
            f"批量导出完成：成功 {res.exported}，跳过冲突 {res.skipped_conflict}，失败 {res.failed}"
        )
        if res.failed > 0 and res.errors:
            detail = "\n".join(res.errors)
            QMessageBox.warning(self, "批量导出部分失败", detail)

    def _current_entry(self):
        if self._current_row is None:
            return None
        return self._model.entry_at(self._current_row)

    def _update_status(self) -> None:
        self.statusBar().showMessage(f"共 {self._model.rowCount()} 个文件")
