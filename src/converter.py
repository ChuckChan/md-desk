"""Thin wrapper around MarkItDown (Stage 3).

Responsibilities:
- path -> markdown via MarkItDown().convert(path).markdown
- map MarkItDown exceptions to a (FileStatus, message) pair

This module is UI/Qt-agnostic and independently testable. It MUST NOT
import Qt or any GUI module.
"""

from markitdown import (
    MarkItDown,
    UnsupportedFormatException,
    FileConversionException,
    MissingDependencyException,
)

from .file_entry import FileStatus


class ConversionError(Exception):
    """Raised by convert_file on any conversion failure.

    Carries the mapped FileStatus so the caller can update the UI.
    """

    def __init__(self, status: FileStatus, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


def map_exception(exc: Exception) -> tuple[FileStatus, str]:
    """Map a MarkItDown exception to (status, human message).

    UnsupportedFormatException      -> UNSUPPORTED
    FileConversionException        -> ERROR
    MissingDependencyException     -> ERROR
    any other Exception            -> ERROR
    """
    if isinstance(exc, UnsupportedFormatException):
        return FileStatus.UNSUPPORTED, f"不支持的文件格式: {exc}"
    if isinstance(exc, (FileConversionException, MissingDependencyException)):
        return FileStatus.ERROR, f"转换失败: {exc}"
    return FileStatus.ERROR, f"转换错误: {exc}"


def convert_file(path: str) -> str:
    """Convert a single file to Markdown.

    Returns the markdown string. Raises ConversionError on failure, with
    .status mapped per map_exception(). Does NOT reimplement parsing.
    """
    try:
        return MarkItDown().convert(path).markdown
    except Exception as exc:  # noqa: BLE001 - map all failures to ERROR/UNSUPPORTED
        status, message = map_exception(exc)
        raise ConversionError(status, message) from exc
