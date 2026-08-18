"""Lightweight diagnostic detail panel (v0.4 Stage 4).

Consumes a single ``ConversionReport`` **directly** (the model's
``entry.report``) to show one conversion's diagnostics. It does NOT read the
diagnostic log file (the log is only a persistent copy — see ``report.py``),
and it does NOT display the full Markdown body.

Design goals (from the v0.4 Stage 4 brief)
-----------------------------------------
  * Keep the main window simple: this panel is an opt-in tab, not the default
    view.
  * Success with no warnings  -> a plain success banner (duration/char count
    are still shown in the overview).
  * Success WITH warnings      -> "转换成功但有质量提示" banner. It is NEVER
    labelled as an error.
  * Failure (ERROR / UNSUPPORTED) -> a failure banner with the (sanitized)
    error detail; the report is still fully viewable.
  * Warnings show the human-readable message by default; the stable warning
    code is included as a secondary detail line.
  * No full Markdown copy is rendered here.
  * An "打开日志目录 / 打开日志文件" button opens the diagnostic log on disk
    via ``QDesktopServices``. There is deliberately NO in-app log browser.

Runtime dependencies: PySide6 only. It imports ``ConversionReport`` from
``.report`` (which is Qt-free and markitdown-free), so it never pulls
markitdown into the UI either.

Implementation note: the overview / error widgets are PERSISTENT (created once,
only their text/visibility changes) to avoid widget create/destroy churn on
every entry switch. Only the per-warning rows are rebuilt, and those are
removed synchronously with ``sip.delete`` so a rapid entry switch can never
show a stale warning from another entry (lifecycle-safe, deterministic).
"""

from __future__ import annotations

import os

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from .report import ConversionReport


def _fmt_duration(ms: int) -> str:
    """Human-friendly duration string (ms / s)."""
    if ms < 0:
        return "—"
    if ms < 1000:
        return f"{ms} ms"
    return f"{ms / 1000.0:.2f} s"


class DiagnosticsPanel(QWidget):
    """Renders one ``ConversionReport`` (or a placeholder when none selected)."""

    def __init__(self, parent: QWidget | None = None, log_path: str | None = None) -> None:
        super().__init__(parent)
        self._log_path = log_path
        self._build_ui()
        self.show_report(None)

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)

        # Banner (success / warning / error / idle) -------------------------
        self._banner = QLabel("")
        self._banner.setMinimumHeight(34)
        self._banner.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._banner.setWordWrap(True)
        root.addWidget(self._banner)

        # Scrollable detail body -------------------------------------------
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        body = QWidget()
        self._body_layout = QVBoxLayout(body)
        self._body_layout.setContentsMargins(0, 0, 0, 0)

        # Overview (persistent) --------------------------------------------
        self._overview = QGroupBox("转换概览")
        ov = QVBoxLayout(self._overview)
        self._ov_source_row, self._ov_source = self._kv("来源")
        self._ov_type_row, self._ov_type = self._kv("类型")
        self._ov_status_row, self._ov_status = self._kv("状态")
        self._ov_duration_row, self._ov_duration = self._kv("耗时")
        self._ov_chars_row, self._ov_chars = self._kv("输出字符数")
        self._ov_time_row, self._ov_time = self._kv("时间")
        for row in (self._ov_source_row, self._ov_type_row, self._ov_status_row,
                    self._ov_duration_row, self._ov_chars_row, self._ov_time_row):
            ov.addWidget(row)

        # Warnings (persistent container; hidden when empty) ----------------
        self._warnings = QGroupBox("质量提示")
        self._warnings_layout = QVBoxLayout(self._warnings)
        self._warnings.setVisible(False)
        # Reused pool of (item, msg_label, code_label) rows. We never delete
        # these widgets on entry switch — we hide + clear the extras — so a
        # stale warning can never linger (lifecycle-safe, no churn).
        self._warn_rows: list = []

        # Error (persistent; hidden when none) -----------------------------
        self._error = QGroupBox("错误信息")
        ev = QVBoxLayout(self._error)
        self._error_label = QLabel("")
        self._error_label.setWordWrap(True)
        self._error_label.setStyleSheet("color: #c0392b;")
        ev.addWidget(self._error_label)
        self._error.setVisible(False)

        self._body_layout.addWidget(self._overview)
        self._body_layout.addWidget(self._warnings)
        self._body_layout.addWidget(self._error)
        self._body_layout.addStretch(1)
        scroll.setWidget(body)
        root.addWidget(scroll, 1)

        # Log open buttons (no in-app log browser) -------------------------
        btn_row = QHBoxLayout()
        self._open_dir_btn = QPushButton("打开日志目录")
        self._open_file_btn = QPushButton("打开日志文件")
        self._open_dir_btn.clicked.connect(self._open_log_dir)
        self._open_file_btn.clicked.connect(self._open_log_file)
        btn_row.addStretch(1)
        btn_row.addWidget(self._open_dir_btn)
        btn_row.addWidget(self._open_file_btn)
        root.addLayout(btn_row)

    # ----------------------------------------------------------------- data
    def set_log_path(self, log_path: str | None) -> None:
        """Update the diagnostic log path (called by the host window)."""
        self._log_path = log_path

    def show_report(self, report: ConversionReport | None) -> None:
        """Render ``report``. When ``None``, show a neutral placeholder."""
        if report is None:
            self._set_banner("暂无诊断信息", "idle")
            self._set_log_buttons_enabled(False)
            for lbl in (self._ov_source, self._ov_type, self._ov_status,
                        self._ov_duration, self._ov_chars, self._ov_time):
                lbl.setText("—")
            self._set_warnings(())
            self._set_error(None)
            return

        self._set_log_buttons_enabled(self._log_path is not None)

        # Banner state: success / success+warning / failure.
        if report.ok:
            if report.warnings:
                self._set_banner("转换成功，但有质量提示", "warning")
            else:
                self._set_banner("转换成功", "success")
        else:
            self._set_banner(f"转换失败（{report.status.value}）", "error")

        # Overview fields. Tolerate unknown source types (new kinds added
        # later) — never crash on a None / unexpected value.
        self._ov_source.setText(report.source or "—")
        self._ov_type.setText(str(report.source_type) if report.source_type else "—")
        self._ov_status.setText(report.status.value)
        self._ov_duration.setText(_fmt_duration(report.duration_ms))
        self._ov_chars.setText(f"{report.output_chars:,}")
        self._ov_time.setText(report.timestamp)

        # Warnings + error (rebuilt / toggled, no full Markdown body).
        self._set_warnings(report.warnings)
        self._set_error(report.error)

    def clear(self) -> None:
        """Alias for show_report(None) — used on deselect / clear list."""
        self.show_report(None)

    # -------------------------------------------------------------- helpers
    def _kv(self, key: str):
        """Build a key/value row; return (row_widget, value_label)."""
        row = QWidget()
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 2, 0, 2)
        k = QLabel(f"{key}：")
        k.setFixedWidth(72)
        k.setStyleSheet("color: #888;")
        v = QLabel("—")
        v.setWordWrap(True)
        h.addWidget(k)
        h.addWidget(v, 1)
        return row, v

    def _set_warnings(self, warnings) -> None:
        """Show ``warnings`` using a reused row pool.

        Rows beyond the current count are hidden and their text cleared, so a
        previously displayed warning can never survive an entry switch (there
        is no deletion race and no stale text for ``findChildren`` to find).
        """
        # Grow the pool if needed.
        while len(self._warn_rows) < len(warnings):
            item = QWidget()
            il = QVBoxLayout(item)
            il.setContentsMargins(0, 0, 0, 0)
            msg = QLabel("")
            msg.setWordWrap(True)
            msg.setStyleSheet("font-weight: bold;")
            code = QLabel("")
            code.setStyleSheet("color: #888; font-family: monospace;")
            il.addWidget(msg)
            il.addWidget(code)
            self._warnings_layout.addWidget(item)
            self._warn_rows.append((item, msg, code))
        # Assign / hide.
        for i, (item, msg, code) in enumerate(self._warn_rows):
            if i < len(warnings):
                w = warnings[i]
                # Tolerate unknown / non-QualityWarning warning objects: recover
                # whatever readable message + code we can; never raise. New
                # warning codes (added later) are shown as-is.
                message = getattr(w, "message", None)
                if not message:
                    message = str(w)
                code_val = getattr(w, "code", None) or "?"
                msg.setText(message)
                code.setText(f"代码：{code_val}")
                item.setVisible(True)
            else:
                msg.setText("")
                code.setText("")
                item.setVisible(False)
        if warnings:
            self._warnings.setTitle(f"质量提示（{len(warnings)}）")
            self._warnings.setVisible(True)
        else:
            self._warnings.setVisible(False)

    def _set_error(self, error: str | None) -> None:
        if error:
            self._error_label.setText(error)
            self._error.setVisible(True)
        else:
            self._error.setVisible(False)

    def _set_banner(self, text: str, kind: str) -> None:
        self._banner.setText(text)
        styles = {
            "success": ("#e8f5e9", "#1b5e20"),
            "warning": ("#fff8e1", "#8d6e00"),
            "error":   ("#fdecea", "#c0392b"),
            "idle":    ("#eceff1", "#455a64"),
        }
        bg, fg = styles.get(kind, styles["idle"])
        self._banner.setStyleSheet(
            f"background: {bg}; color: {fg}; border-radius: 4px; "
            f"padding: 6px; font-weight: bold;"
        )

    def _set_log_buttons_enabled(self, enabled: bool) -> None:
        self._open_dir_btn.setEnabled(enabled)
        self._open_file_btn.setEnabled(enabled)

    def _open_log_file(self) -> None:
        if not self._log_path:
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(self._log_path))

    def _open_log_dir(self) -> None:
        if not self._log_path:
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.dirname(self._log_path)))
