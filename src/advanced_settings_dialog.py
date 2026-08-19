"""Advanced Settings dialog (Stage 4 — hidden-by-default power-user panel;
AI area reworked in v0.6 for the unified Provider infrastructure).

This is the ONLY place normal users can reach the advanced capabilities:
  * Conversion Options: YouTube transcript preferred languages.
  * AI Provider (v0.6): provider / API Key / endpoint / model / timeout /
    connection test, plus INDEPENDENT OCR and image-description toggles and
    the vision prompt.
  * 转换质量检查 (v0.4).
  * Input Detection Override: extension / mimetype / charset / filename for
    the currently selected entry (advanced; fixes misidentified inputs).

UI boundary (plan §4.4): the dialog only collects settings -> validates ->
saves -> calls the provider service (``ai_provider``). All network work for
the connection test runs on a QThread so the UI never blocks; the API Key is
never displayed in clear text and never written to settings.json.

Kept in its own module so MainWindow stays a thin layout + signal driver.
"""

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from . import ai_provider
from .credential_store import CredentialStoreError, delete_api_key, get_api_key, set_api_key
from .file_entry import FileEntry
from .settings import (
    AI_TIMEOUT_DEFAULT_SECONDS,
    AI_TIMEOUT_MAX_SECONDS,
    AI_TIMEOUT_MIN_SECONDS,
    PROVIDER_OPENAI_COMPATIBLE,
    Settings,
    StreamInfoOverride,
)


class _ConnectionTestRunner(QThread):
    """Runs ``ai_provider.test_connection`` OFF the GUI thread.

    Emits ``finished_with_result(ConnectionTestResult)`` exactly once. The
    thread is bounded by the configured timeout (the client is built with
    ``max_retries=0``), so it always terminates on its own.
    """

    finished_with_result = Signal(object)

    def __init__(self, provider_config: "ai_provider.AIProviderConfig", parent=None) -> None:
        super().__init__(parent)
        self._config = provider_config

    def run(self) -> None:  # executed on the runner thread
        result = ai_provider.test_connection(self._config)
        self.finished_with_result.emit(result)


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
        self._test_runner: _ConnectionTestRunner | None = None

        layout = QVBoxLayout(self)

        # ---- Conversion Options ----
        conv_box = QGroupBox("转换选项")
        conv_form = QFormLayout(conv_box)
        self._yt_edit = QLineEdit(", ".join(settings.youtube_transcript_languages))
        self._yt_edit.setPlaceholderText("例如：zh-Hans, en, ja（逗号分隔，留空使用引擎默认）")
        conv_form.addRow("YouTube 字幕语言", self._yt_edit)
        layout.addWidget(conv_box)

        # ---- AI Provider (v0.6) ----
        ai_box = QGroupBox("AI Provider（OpenAI 兼容）")
        ai_form = QFormLayout(ai_box)
        self._ai_enabled = QCheckBox("启用 AI（总开关；下方功能需分别开启）")
        self._ai_enabled.setChecked(bool(settings.ai.enabled))
        self._ai_enabled.toggled.connect(self._update_ai_fields_enabled)
        ai_form.addRow(self._ai_enabled)

        self._ai_provider = QComboBox()
        self._ai_provider.addItem("OpenAI 兼容 (openai-compatible)", PROVIDER_OPENAI_COMPATIBLE)
        self._ai_provider.setToolTip("v0.6 支持 OpenAI 兼容服务（OpenAI / Azure 代理 / 本地网关等）。")
        ai_form.addRow("Provider", self._ai_provider)

        self._ai_key = QLineEdit()
        self._ai_key.setEchoMode(QLineEdit.EchoMode.Password)
        self._ai_key.setPlaceholderText("API Key（保存在 Windows 凭据管理器，不写入 settings.json）")
        try:
            existing = get_api_key() or ""
        except CredentialStoreError:
            existing = ""
        self._ai_key.setText(existing)
        ai_form.addRow("API Key", self._ai_key)

        self._ai_endpoint = QLineEdit(settings.ai.endpoint)
        self._ai_endpoint.setPlaceholderText("OpenAI 兼容 Endpoint，例如 https://api.openai.com/v1（留空用默认）")
        ai_form.addRow("Endpoint", self._ai_endpoint)

        self._ai_model = QLineEdit(settings.ai.model)
        self._ai_model.setPlaceholderText("模型名，例如 gpt-4o（必填）")
        ai_form.addRow("模型", self._ai_model)

        self._ai_timeout = QDoubleSpinBox()
        self._ai_timeout.setRange(AI_TIMEOUT_MIN_SECONDS, AI_TIMEOUT_MAX_SECONDS)
        self._ai_timeout.setDecimals(1)
        self._ai_timeout.setSingleStep(5.0)
        self._ai_timeout.setValue(float(settings.ai.timeout_seconds))
        self._ai_timeout.setSuffix(" 秒")
        self._ai_timeout.setToolTip("每次 AI 网络调用的超时上限（1–600 秒）。")
        ai_form.addRow("Timeout", self._ai_timeout)

        # Independent capability toggles (v0.6 plan §3.2).
        self._ai_ocr = QCheckBox("OCR：识别 PDF / Word / PPT / Excel 中的图片文字")
        self._ai_ocr.setChecked(bool(getattr(settings.ai, "ocr_enabled", True)))
        ai_form.addRow(self._ai_ocr)
        self._ai_desc = QCheckBox("图片描述：用视觉模型描述 JPG / PNG 图片内容")
        self._ai_desc.setChecked(bool(getattr(settings.ai, "image_description_enabled", True)))
        ai_form.addRow(self._ai_desc)

        self._ai_prompt = QLineEdit(settings.ai.prompt)
        self._ai_prompt.setPlaceholderText("自定义 Vision Prompt（留空则用官方默认，图片描述与 OCR 各自回退）")
        ai_form.addRow("Vision Prompt", self._ai_prompt)

        # Connection test row (plan §3.4): button + result label.
        test_row = QHBoxLayout()
        self._test_btn = QPushButton("测试连接")
        self._test_btn.clicked.connect(self._on_test_connection)
        self._test_result = QLabel("")
        self._test_result.setWordWrap(True)
        self._test_result.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        test_row.addWidget(self._test_btn)
        test_row.addWidget(self._test_result, 1)
        ai_form.addRow(test_row)
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

        self._update_ai_fields_enabled()

    # -- helpers ----------------------------------------------------------
    @staticmethod
    def _normalize_extension(value: str) -> str | None:
        value = (value or "").strip()
        if not value:
            return None
        if not value.startswith("."):
            value = "." + value
        return value.lower()

    def _update_ai_fields_enabled(self) -> None:
        """Keep the panel clear for users who have not enabled AI (plan §3.3):
        all provider details stay disabled until the master switch is on."""
        on = self._ai_enabled.isChecked()
        for w in (self._ai_provider, self._ai_key, self._ai_endpoint,
                  self._ai_model, self._ai_timeout, self._ai_ocr,
                  self._ai_desc, self._ai_prompt):
            w.setEnabled(on)
        self._test_btn.setEnabled(on)
        if not on:
            self._test_result.setText("")

    # -- connection test (v0.6, plan §3.4) --------------------------------
    def _current_provider_config(self) -> "ai_provider.AIProviderConfig":
        """Build the provider config from the CURRENT (unsaved) form fields —
        the test must reflect what the user sees, not the last saved state."""
        key = self._ai_key.text()
        return ai_provider.AIProviderConfig(
            provider=self._ai_provider.currentData() or PROVIDER_OPENAI_COMPATIBLE,
            api_key=key,
            endpoint=self._ai_endpoint.text().strip(),
            model=self._ai_model.text().strip(),
            timeout_seconds=float(self._ai_timeout.value()),
            prompt=self._ai_prompt.text().strip() or None,
        )

    def _on_test_connection(self) -> None:
        if self._test_runner is not None and self._test_runner.isRunning():
            return  # one probe at a time
        config = self._current_provider_config()
        if not config.model:
            self._test_result.setStyleSheet("color: #c0392b;")
            self._test_result.setText("请先填写模型名，再测试连接。")
            return
        self._test_btn.setEnabled(False)
        self._test_result.setStyleSheet("")
        self._test_result.setText(f"测试中（最长等待 {config.timeout_seconds:.0f} 秒）…")
        self._test_runner = _ConnectionTestRunner(config, self)
        self._test_runner.finished_with_result.connect(self._on_test_result)
        self._test_runner.start()

    def _on_test_result(self, result) -> None:
        """Show the probe outcome. The message is produced by ``ai_provider``
        and is already sanitized (no key / Authorization / secret URL)."""
        color = "#1b5e20" if result.ok else "#c0392b"
        self._test_result.setStyleSheet(f"color: {color};")
        self._test_result.setText(
            f"{'✓' if result.ok else '✗'} {result.message}（{result.duration_ms} ms）"
        )
        self._test_btn.setEnabled(self._ai_enabled.isChecked())

    def _wait_for_test_runner(self) -> None:
        # Never destroy a running QThread: let the in-flight probe finish
        # (bounded by its timeout) while keeping the event loop pumping so
        # the UI stays responsive during the wait. Called from closeEvent,
        # accept and reject alike — the OK/Cancel buttons route through
        # accept()/reject() and would otherwise bypass the closeEvent wait.
        runner = self._test_runner
        if runner is not None and runner.isRunning():
            while not runner.wait(50):
                QApplication.processEvents()

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt naming
        self._wait_for_test_runner()
        super().closeEvent(event)

    def reject(self) -> None:  # noqa: N802 - QDialog override
        self._wait_for_test_runner()
        super().reject()

    def accept(self) -> None:
        self._wait_for_test_runner()

        # Conversion Options: YouTube languages.
        langs = [s.strip() for s in self._yt_edit.text().split(",") if s.strip()]
        self._settings.youtube_transcript_languages = langs

        # Conversion quality inspection (v0.4 Stage 2). Default OFF in code;
        # this is the only user-facing switch for it.
        self._settings.quality_enabled = self._quality_enabled.isChecked()

        # AI Provider (v0.3 + v0.6): non-secret fields go to Settings; the Key
        # goes to Windows Credential Manager (never to settings.json).
        self._settings.ai.enabled = self._ai_enabled.isChecked()
        self._settings.ai.provider = (
            self._ai_provider.currentData() or PROVIDER_OPENAI_COMPATIBLE
        )
        self._settings.ai.endpoint = self._ai_endpoint.text().strip()
        self._settings.ai.model = self._ai_model.text().strip()
        self._settings.ai.timeout_seconds = float(self._ai_timeout.value())
        self._settings.ai.prompt = self._ai_prompt.text().strip()
        self._settings.ai.ocr_enabled = self._ai_ocr.isChecked()
        self._settings.ai.image_description_enabled = self._ai_desc.isChecked()

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
