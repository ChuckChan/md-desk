"""Conversion quality inspection (v0.4 Stage 2).

A small, pure-Python (Qt-free) ``QualityInspector`` that examines a *successful*
conversion's Markdown output and returns a tuple of immutable ``QualityWarning``
notices. It NEVER mutates the Markdown, NEVER changes the conversion status, and
NEVER raises a quality-class exception — it is advisory only.

Design goals:
  * Low false-positive: rules fire only on clearly suspicious signals. Normal
    short files (small input), normal Chinese/English Markdown, and legitimately
    small-but-valid output are NOT flagged.
  * Reuse, don't reimplement: the OCR-failure hook reuses the existing
    ``markdown_has_ocr_error`` from ``src.converter`` (single source of truth).
  * Size-aware: the "short output" rules only apply when the input size is known
    (the worker passes ``entry.size`` for local files; URL entries pass None and
    are skipped by those rules). This prevents flagging small-but-valid files.
  * Conservative thresholds: every constant below is a deliberate, documented
    knob that can be tuned later without touching call sites.

Import note: this module intentionally imports nothing from ``result`` (to keep
``result`` importable without pulling in markitdown). It imports
``QualityWarning`` from ``src.result`` and the OCR hook from ``src.converter``.
"""

import re

from .converter import markdown_has_ocr_error
from .result import QualityWarning

# Minimum number of "meaningful" characters (letters / digits / CJK / Kana /
# Hangul) below which an output is considered suspicious for its input size.
_MIN_MEANINGFUL_CHARS = 30

# Input-size tiers (bytes). Size-aware rules only fire when input_size is known
# (local files); URL entries pass None and skip these rules entirely.
_MEDIUM_INPUT_BYTES = 2_000
_LARGE_INPUT_BYTES = 50_000

# Garbled-text heuristics — conservative, strong signals only.
_FFFD = "�"
_GARBLED_MOJIBAKE_RE = re.compile(r"Ã[\x80-\xff]|â€|Ã¢â‚¬")

# Characters that count as "real text" for the short-output heuristic.
_WORDCHAR_RE = re.compile(
    r"[A-Za-z0-9一-鿿぀-ヿ가-힯]"
)


class QualityInspector:
    """Stateless inspector for successful conversion output.

    Use ``inspect(markdown, input_size=...)``. It returns a tuple of
    ``QualityWarning`` (possibly empty), is safe to call repeatedly, and never
    raises. It is intended to run only on successful (DONE) conversions; the
    worker guarantees that.
    """

    def inspect(
        self, markdown: str, *, input_size: int | None = None
    ) -> tuple[QualityWarning, ...]:
        """Return quality warnings for a successful conversion's Markdown.

        ``input_size`` is the source file size in bytes (None when unknown, e.g.
        a not-yet-fetched URL). Size-aware rules are skipped when it is None/0.
        """
        md = markdown if isinstance(markdown, str) else ""
        stripped = md.strip()
        warnings: list[QualityWarning] = []

        # 1. Empty output (fires regardless of input size).
        if not stripped:
            warnings.append(
                QualityWarning("EMPTY_OUTPUT", "转换结果为空，可能内容未被提取。")
            )
            return tuple(warnings)

        word_chars = len(_WORDCHAR_RE.findall(stripped))

        # 2 & 3. Short output relative to input size (only when size known).
        if input_size is not None and input_size > 0:
            if (
                input_size >= _LARGE_INPUT_BYTES
                and word_chars < _MIN_MEANINGFUL_CHARS
            ):
                warnings.append(
                    QualityWarning(
                        "LOW_TEXT_YIELD",
                        f"输入较大（{input_size} 字节）但提取文本极少"
                        f"（{word_chars} 字），转换可能不完整。",
                    )
                )
            elif (
                _MEDIUM_INPUT_BYTES <= input_size < _LARGE_INPUT_BYTES
                and word_chars < _MIN_MEANINGFUL_CHARS
            ):
                warnings.append(
                    QualityWarning(
                        "SHORT_OUTPUT",
                        f"输入 {input_size} 字节但提取文本较短"
                        f"（{word_chars} 字），请检查转换是否完整。",
                    )
                )

        # 4. Obvious garbled / mojibake text.
        if self._is_garbled(stripped):
            warnings.append(
                QualityWarning(
                    "GARBLED_TEXT",
                    "检测到明显乱码（编码错误或字符损坏），转换内容可能不可用。",
                )
            )

        # 5. OCR failure marker (reuse existing hook, do not reimplement).
        if markdown_has_ocr_error(md):
            warnings.append(
                QualityWarning(
                    "OCR_ERROR_MARKER",
                    "转换完成但包含 OCR 失败块（部分扫描内容未被识别）。",
                )
            )

        return tuple(warnings)

    @staticmethod
    def _is_garbled(text: str) -> bool:
        """Conservative garble detector: only strong, unambiguous signals.

        * 3+ Unicode replacement characters (U+FFFD) => definite decode failure.
        * 2+ classic UTF-8-as-Latin1 mojibake sequences (e.g. "â€" from
          mis-decoded smart quotes/dashes, "Ã©" from mis-decoded accented
          letters) => near-certain encoding corruption.

        Deliberately does NOT flag a single stray mojibake hit or lone "Â",
        which can appear in legitimate text (e.g. Portuguese/Turkish), keeping
        the false-positive rate near zero for normal Chinese/English content.
        """
        if text.count(_FFFD) >= 3:
            return True
        return len(_GARBLED_MOJIBAKE_RE.findall(text)) >= 2
