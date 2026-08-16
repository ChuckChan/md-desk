"""File entry data model for the MdDesk GUI.

Holds only metadata about a file to be converted later. No file content,
no MarkItDown, no conversion logic.
"""

from dataclasses import dataclass
from enum import Enum
import os
from pathlib import Path


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
