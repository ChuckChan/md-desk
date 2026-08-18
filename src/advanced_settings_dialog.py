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
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QVBoxLayout,
)

from .credential_store import CredentialStoreError, delete_api_key, get_api_key, set_api_key
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

        # ---- AI 增强转换 (v0.3) ----
        ai_box = QGroupBox("AI 增强转换")
        ai_form = QFormLayout(ai_box)
        self._ai_enabled = QCheckBox("启用 AI（图片描述 + OCR）")
        self._ai_enabled.setChecked(bool(settings.ai.enabled))
        ai_form.addRow(self._ai_enabled)
        self._ai_endpoint = QLineEdit(settings.ai.endpoint)
        self._ai_endpoint.setPlaceholderText("OpenAI 兼容 Endpoint，例如 https://api.openai.com/v1（留空用默认）")
        ai_form.addRow("Endpoint", self._ai_endpoint)
        self._ai_model = QLineEdit(settings.ai.model)
        self._ai_model.setPlaceholderText("模型名，例如 gpt-4o（必填）")
        ai_form.addRow("模型", self._ai_model)
        self._ai_prompt = QLineEdit(settings.ai.prompt)
        self._ai_prompt.setPlaceholderText("自定义 Prompt（留空则用官方默认，不强制图片/OCR 共用）")
        ai_form.addRow("Prompt", self._ai_prompt)
        self._ai_key = QLineEdit()
        self._ai_key.setEchoMode(QLineEdit.EchoMode.Password)
        self._ai_key.setPlaceholderText("API Key（保存在 Windows 凭据管理器，不写入 settings.json）")
        try:
            existing = get_api_key() or ""
        except CredentialStoreError:
            existing = ""
        self._ai_key.setText(existing)
        ai_form.addRow("API Key", self._ai_key)
        layout.addWidget(ai_box)

        # ---- 转换质量检查 (v0.4 Stage 2) ----
        qual_box = QGroupBox("转换质量检查")
        qual_form = QFormLayout(qual_box)
        self._quality_enabled = QCheckBox("启用转换质量检查 (QualityInspector)")
        self._quality_enabled.setChecked(bool(settings.quality_enabled))
        self._quality_enabled.setToolTip(
            "默认关闭。开启后，成功的转换会做轻量静态检查"
            "（空输出 / 异常短 / 乱码 / OCR 失败），仅产生提示，"
            "不会修改转换结果或状态。"
        )
        qual_form.addRow(self._quality_enabled)
        layout.addWidget(qual_box)

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

        # Conversion quality inspection (v0.4 Stage 2). Default OFF in code;
        # this is the only user-facing switch for it.
        self._settings.quality_enabled = self._quality_enabled.isChecked()

        # AI 增强转换 (v0.3): non-secret fields go to Settings; the Key goes to
        # Windows Credential Manager (never to settings.json).
        self._settings.ai.enabled = self._ai_enabled.isChecked()
        self._settings.ai.endpoint = self._ai_endpoint.text().strip()
        self._settings.ai.model = self._ai_model.text().strip()
        self._settings.ai.prompt = self._ai_prompt.text().strip()

        new_key = self._ai_key.text()
        try:
            if new_key:
                set_api_key(new_key)
            else:
                # Empty key field -> clear any previously stored key so a saved
                # "AI on" config without a key fails clearly at call time
                # rather than reusing a stale secret.
                delete_api_key()
        except CredentialStoreError as exc:
            # Non-fatal: the app still runs; surface the limitation to the user.
            from PySide6.QtWidgets import QMessageBox

            QMessageBox.warning(
                self,
                "无法保存 API Key",
                f"{exc}\n\nAI 已勾选但不会生效，直到在受支持的平台上保存 Key。",
            )

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
