"""Advanced Settings dialog (Stage 4 — hidden-by-default power-user panel).

This is the ONLY place normal users can reach the advanced capabilities:
  * Conversion Options: YouTube transcript preferred languages.
  * Input Detection Override: extension / mimetype / charset / filename for
    the currently selected entry (advanced; fixes misidentified inputs).

The dialog is deliberately minimal and self-contained. It mutates the passed
``Settings`` object in place on accept and saves it; for the per-entry
override it writes ``entry.stream_info_override`` directly. It does NOT touch
converters or the engine API beyond what ``Settings`` / ``StreamInfoOverride``
already expose.

Kept in its own module so MainWindow stays a thin layout + signal driver.
"""

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QVBoxLayout,
)

from .file_entry import FileEntry
from .settings import Settings, StreamInfoOverride


class AdvancedSettingsDialog(QDialog):
    def __init__(
        self,
        settings: Settings,
        entry: FileEntry | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("高级设置")
        self._settings = settings
        self._entry = entry

        layout = QVBoxLayout(self)

        # ---- Conversion Options ----
        conv_box = QGroupBox("转换选项")
        conv_form = QFormLayout(conv_box)
        self._yt_edit = QLineEdit(", ".join(settings.youtube_transcript_languages))
        self._yt_edit.setPlaceholderText("例如：zh-Hans, en, ja（逗号分隔，留空使用引擎默认）")
        conv_form.addRow("YouTube 字幕优先语言", self._yt_edit)
        layout.addWidget(conv_box)

        # ---- Input Detection Override (per selected entry) ----
        override_box = QGroupBox("输入识别覆盖（仅作用于当前选中的文件）")
        override_form = QFormLayout(override_box)
        self._ext_edit = QLineEdit()
        self._mime_edit = QLineEdit()
        self._charset_edit = QLineEdit()
        self._fname_edit = QLineEdit()
        self._ext_edit.setPlaceholderText("例如：.txt（以 . 开头）")
        self._mime_edit.setPlaceholderText("例如：text/plain")
        self._charset_edit.setPlaceholderText("例如：utf-8")
        self._fname_edit.setPlaceholderText("仅修改展示名，不改路由")
        override_form.addRow("扩展名", self._ext_edit)
        override_form.addRow("MIME 类型", self._mime_edit)
        override_form.addRow("字符编码", self._charset_edit)
        override_form.addRow("文件名", self._fname_edit)

        if entry is not None and entry.stream_info_override is not None:
            o = entry.stream_info_override
            self._ext_edit.setText(o.extension or "")
            self._mime_edit.setText(o.mimetype or "")
            self._charset_edit.setText(o.charset or "")
            self._fname_edit.setText(o.filename or "")

        # No selected entry -> the override section is meaningless; disable it.
        if entry is None:
            override_box.setEnabled(False)
            override_box.setTitle("输入识别覆盖（先选中一个文件再设置）")
        layout.addWidget(override_box)

        hint = QLabel(
            "以上均为可选覆盖；留空即沿用引擎自动检测结果。普通转换无需改动此处。"
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)

        # ---- buttons ----
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    # -- helpers ----------------------------------------------------------
    @staticmethod
    def _normalize_extension(value: str) -> str | None:
        value = (value or "").strip()
        if not value:
            return None
        if not value.startswith("."):
            value = "." + value
        return value.lower()

    def accept(self) -> None:
        # Conversion Options: YouTube languages.
        langs = [s.strip() for s in self._yt_edit.text().split(",") if s.strip()]
        self._settings.youtube_transcript_languages = langs
        self._settings.save()  # persists to %APPDATA%/MdDesk/settings.json

        # Input Detection Override (only when an entry is selected).
        if self._entry is not None:
            override = StreamInfoOverride(
                extension=self._normalize_extension(self._ext_edit.text()),
                mimetype=(self._mime_edit.text().strip() or None),
                charset=(self._charset_edit.text().strip() or None),
                filename=(self._fname_edit.text().strip() or None),
            )
            # Empty override -> clear it so the legacy path is used.
            self._entry.stream_info_override = None if override.is_empty() else override

        super().accept()
