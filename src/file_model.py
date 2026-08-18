"""Table model backing the file list (Stage 2).

Owns the list of FileEntry objects and exposes them to a QTableView.
Responsible for: add / dedup / remove / clear / metadata display.
Must NOT touch MarkItDown, conversion threads, or file content.
"""

from pathlib import Path
import os
from urllib.parse import urlparse

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PySide6.QtWidgets import QApplication

from .file_entry import FileEntry, FileStatus


_COLUMNS = ["文件名", "类型", "大小", "状态"]


def humanize_size(size: int) -> str:
    if size < 1024:
        return f"{size} B"
    val = size / 1024.0
    for unit in ("KB", "MB", "GB", "TB"):
        if val < 1024 or unit == "TB":
            return f"{val:.1f} {unit}"
        val /= 1024
    return f"{val:.1f} TB"


class FileModel(QAbstractTableModel):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._entries: list[FileEntry] = []
        self._paths: set[str] = set()

    # ---- model interface ----
    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._entries)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(_COLUMNS)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return _COLUMNS[section]
        return super().headerData(section, orientation, role)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        entry = self._entries[index.row()]
        col = index.column()
        if role == Qt.ItemDataRole.DisplayRole:
            if col == 0:
                return entry.filename
            if col == 1:
                return entry.extension.lstrip(".").upper() or "—"
            if col == 2:
                return humanize_size(entry.size)
            if col == 3:
                # Stage 4: a DONE entry that also produced quality warnings is
                # surfaced as "完成 (质量提示)" — NEVER as an error. This keeps
                # the main list readable while the full detail lives in the
                # diagnostics panel.
                if entry.status == FileStatus.DONE and entry.report and entry.report.warnings:
                    return "完成 (质量提示)"
                return entry.status.value
        if role == Qt.ItemDataRole.TextAlignmentRole:
            if col == 2:
                return Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            if col == 3:
                return Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter
        return None

    # ---- mutations ----
    def add_paths(self, paths) -> tuple[int, int]:
        """Add valid local files. Dedup by normalized path; ignore
        nonexistent paths and directories. Returns (added, skipped)."""
        added = 0
        skipped = 0
        new_entries: list[FileEntry] = []
        for raw in paths:
            p = Path(raw)
            if not p.exists() or not p.is_file():
                skipped += 1
                continue
            norm = os.path.normcase(os.path.abspath(raw))
            if norm in self._paths:
                skipped += 1
                continue
            try:
                entry = FileEntry.from_path(raw)
            except OSError:
                skipped += 1
                continue
            new_entries.append(entry)
            self._paths.add(entry.norm_path)
            added += 1
        if new_entries:
            start = len(self._entries)
            self.beginInsertRows(QModelIndex(), start, start + len(new_entries) - 1)
            self._entries.extend(new_entries)
            self.endInsertRows()
        return added, skipped

    def add_url(self, url: str) -> tuple[int, int]:
        """Add a remote http/https URL entry. Dedup by URL string.

        Returns (added, skipped). Rejects empty / non-http(s) URLs and
        duplicates. Full security validation happens later in UrlFetchService
        at conversion time; this only performs the lightweight scheme gate.
        """
        u = (url or "").strip()
        if not u:
            return 0, 1
        try:
            scheme = urlparse(u).scheme.lower()
        except Exception:
            scheme = ""
        if scheme not in ("http", "https"):
            return 0, 1
        if u in self._paths:
            return 0, 1
        try:
            entry = FileEntry.from_url(u)
        except Exception:
            return 0, 1
        start = len(self._entries)
        self.beginInsertRows(QModelIndex(), start, start)
        self._entries.append(entry)
        self._paths.add(entry.norm_path)
        self.endInsertRows()
        return 1, 0

    def removeRows(self, row: int, count: int, parent: QModelIndex = QModelIndex()) -> bool:
        if parent.isValid() or count <= 0 or row < 0 or row + count > len(self._entries):
            return False
        removed = self._entries[row:row + count]
        self.beginRemoveRows(parent, row, row + count - 1)
        del self._entries[row:row + count]
        for e in removed:
            self._paths.discard(e.norm_path)
        self.endRemoveRows()
        return True

    def clear(self) -> None:
        if not self._entries:
            return
        self.beginResetModel()
        self._entries.clear()
        self._paths.clear()
        self.endResetModel()

    # ---- accessors ----
    def entry_at(self, row: int) -> FileEntry | None:
        if 0 <= row < len(self._entries):
            return self._entries[row]
        return None

    def set_status(self, row: int, status: FileStatus) -> None:
        entry = self.entry_at(row)
        if entry is None:
            return
        entry.status = status
        idx = self.index(row, 3)
        self.dataChanged.emit(idx, idx, [Qt.ItemDataRole.DisplayRole])

    def set_result(self, row: int, markdown: str | None = None,
                   error_message: str | None = None) -> None:
        entry = self.entry_at(row)
        if entry is None:
            return
        if markdown is not None:
            entry.markdown = markdown
        if error_message is not None:
            entry.error_message = error_message

    def set_report(self, row: int, report) -> None:
        """Attach the latest ``ConversionReport`` to an entry (Stage 4).

        Stored ON the entry object so the report's lifecycle follows the
        entry's own lifecycle: removing / clearing / re-batching an entry drops
        its report with it, and a re-batched row gets a fresh report — no stale
        report from another row can ever be shown (there is no separate
        row-indexed dict that could leak across re-batches).

        Emits ``dataChanged`` for the status column because a DONE entry with
        warnings now displays as "完成 (质量提示)".
        """
        entry = self.entry_at(row)
        if entry is None:
            return
        entry.report = report
        idx = self.index(row, 3)
        self.dataChanged.emit(idx, idx, [Qt.ItemDataRole.DisplayRole])
