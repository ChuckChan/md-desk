"""Unified conversion outcome for MdDesk (v0.4 Stage 1).

A single immutable value object that carries BOTH the success and failure
terminal states of a conversion as one unified ``file_finished`` signal
argument. It is intentionally Qt-free and ``frozen`` so it can be passed
safely across the ``QThread`` boundary and is immutable once constructed.

It reuses the existing ``FileStatus`` vocabulary and the existing
``ConversionError`` mapping (see ``src.converter``) — we do NOT invent a
second error model. ``from_error`` is the bridge that turns an already-
mapped ``ConversionError`` (which carries the correct ``FileStatus`` and a
friendly Chinese message produced by ``map_exception``) into a result.

Field notes:
  * ``row``            — the stable task/entry index in the FileModel as it was
                         at batch start. This is the ONLY handle the UI uses to
                         locate the corresponding entry; it never guesses from a
                         "current task" pointer.
  * ``status``         — a ``FileStatus`` (DONE on success, ERROR/UNSUPPORTED on
                         failure). Reused, not redefined.
  * ``markdown``       — the converted text on success, else None.
  * ``error_message``  — the friendly, user-facing message on failure, else None.
  * ``warnings``       — an immutable tuple of non-fatal quality notices
                         (``QualityWarning``: stable ``code`` + readable
                         ``message``). Empty when quality checking is OFF
                         (Stage 2 default) or when no rule fires; typed as a
                         tuple (not a list) per the v0.4 spec.
  * ``duration_ms``    — wall-clock conversion time (perf_counter), for future
                         reporting / diagnostics.
"""

from dataclasses import dataclass
from typing import Tuple

from .file_entry import FileStatus


@dataclass(frozen=True)
class QualityWarning:
    """A single, non-fatal conversion-quality notice.

    Carries a STABLE machine ``code`` (consumed by future UI / report layers)
    and a user-readable Chinese ``message``. Immutable so it is safe to pass
    across the ``QThread`` boundary inside a ``ConversionResult``.
    """

    code: str
    message: str


@dataclass(frozen=True)
class ConversionResult:
    """Immutable terminal outcome of one conversion, success or failure."""

    row: int
    status: FileStatus
    markdown: str | None = None
    error_message: str | None = None
    warnings: Tuple[QualityWarning, ...] = ()
    duration_ms: int = 0

    # ---- constructors --------------------------------------------------
    @classmethod
    def success(
        cls,
        row: int,
        markdown: str,
        *,
        duration_ms: int = 0,
        warnings: Tuple[QualityWarning, ...] = (),
    ) -> "ConversionResult":
        return cls(
            row=row,
            status=FileStatus.DONE,
            markdown=markdown,
            error_message=None,
            warnings=warnings,
            duration_ms=duration_ms,
        )

    @classmethod
    def failure(
        cls,
        row: int,
        status: FileStatus,
        message: str,
        *,
        duration_ms: int = 0,
        warnings: Tuple[QualityWarning, ...] = (),
    ) -> "ConversionResult":
        return cls(
            row=row,
            status=status,
            markdown=None,
            error_message=message,
            warnings=warnings,
            duration_ms=duration_ms,
        )

    @classmethod
    def from_error(
        cls,
        row: int,
        exc,
        *,
        duration_ms: int = 0,
        warnings: Tuple[QualityWarning, ...] = (),
    ) -> "ConversionResult":
        """Build a failure result from an already-mapped ``ConversionError``.

        The ``ConversionError`` produced by ``src.converter`` carries the
        correct ``FileStatus`` (ERROR / UNSUPPORTED) and a friendly Chinese
        message, so we reuse it directly instead of re-mapping. The import is
        local so this module stays importable without pulling in markitdown.
        """
        from .converter import ConversionError

        if not isinstance(exc, ConversionError):
            raise TypeError(
                f"from_error expects a ConversionError, got {type(exc).__name__}"
            )
        return cls.failure(
            row,
            exc.status,
            exc.message,
            duration_ms=duration_ms,
            warnings=warnings,
        )

    # ---- convenience ----------------------------------------------------
    @property
    def ok(self) -> bool:
        """True when the conversion succeeded (status == DONE)."""
        return self.status == FileStatus.DONE
