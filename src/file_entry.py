"""File entry data model for the MdDesk GUI.

Holds only metadata about a file to be converted later. No file content,
no MarkItDown, no conversion logic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import os
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from .settings import StreamInfoOverride


class FileStatus(str, Enum):
    """Conversion lifecycle status (display strings are zh-CN)."""

    WAITING = "等待"
    PROCESSING = "转换中"
    DONE = "完成"
    ERROR = "失败"
    UNSUPPORTED = "不支持"


@dataclass
class FileEntry:
    path: str
    filename: str
    extension: str
    size: int
    status: FileStatus = FileStatus.WAITING
    norm_path: str = ""
    markdown: str | None = None
    error_message: str | None = None
    url: str | None = None
    # Stage 4 (advanced): per-entry Input Detection Override. None means
    # "use the engine's normal guess". Set via the Advanced Settings dialog.
    stream_info_override: Optional[StreamInfoOverride] = None
    # Stage 4 (v0.4): the latest ConversionReport for this entry, stored ON the
    # entry so report lifecycle tracks the entry's own lifecycle. None until a
    # conversion produces one. Keyed by object (not row) so delete / clear /
    # re-batch can never show another entry's stale report. The string
    # annotation + `from __future__ import annotations` keeps this import lazy
    # and avoids a circular import with report.py (which imports FileEntry).
    report: "ConversionReport | None" = None

    @staticmethod
    def from_path(path: str) -> "FileEntry":
        """Build an entry from a filesystem path.

        Reads only metadata (name/size), never file content.
        Raises OSError if the path cannot be stat-ed.
        """
        p = Path(path)
        norm = os.path.normcase(os.path.abspath(path))
        return FileEntry(
            path=str(p),
            filename=p.name,
            extension=p.suffix.lower(),
            size=p.stat().st_size,
            status=FileStatus.WAITING,
            norm_path=norm,
        )

    @staticmethod
    def from_url(url: str) -> "FileEntry":
        """Build an entry from a remote http/https URL (no network access).

        Derives a display filename/extension from the URL path; the actual
        content is fetched lazily by the worker via convert_url().
        """
        u = url.strip()
        parsed = urlparse(u)
        path_part = parsed.path.rstrip("/")
        name = os.path.basename(path_part) if path_part else (parsed.netloc or "remote")
        if not name:
            name = "remote-content"
        _, ext = os.path.splitext(name)
        return FileEntry(
            path=u,
            filename=name,
            extension=ext.lower(),
            size=0,  # unknown until fetched; resolved at convert time
            status=FileStatus.WAITING,
            norm_path=u,
            url=u,
        )

    @property
    def is_url(self) -> bool:
        return self.url is not None
