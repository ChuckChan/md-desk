"""MdDesk v0.6 Advanced Settings dialog tests (plan §3.3 / §3.4).

Offscreen Qt. Verifies:
  * AI detail fields stay DISABLED until the master switch is on (clear UI
    for non-AI users, plan §3.3)
  * the four v0.6 fields (provider/timeout/OCR/description) load from and
    persist to Settings on accept
  * "测试连接" requires a model, runs OFF the GUI thread (QThread), and
    renders the sanitized result without freezing the dialog
  * the API Key goes to the credential store only — settings.json never sees it

Run: python tests/test_v06_settings_ui.py  (or pytest tests/test_v06_settings_ui.py)
"""

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEventLoop, QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from src.advanced_settings_dialog import (  # noqa: E402
    _ConnectionTestRunner,
    AdvancedSettingsDialog,
)
from src.ai_provider import ConnectionTestResult  # noqa: E402
from src.settings import Settings  # noqa: E402

SECRET = "sk-DIALOG-SECRET-987654321"


def _check(name, cond, detail=""):
    print(("PASS" if cond else "FAIL"), "-", name, "" if cond else f":: {detail}")
    return cond


def _app():
    return QApplication.instance() or QApplication([])


def _wait_signal(signal, timeout_ms=15000):
    loop = QEventLoop()
    signal.connect(loop.quit)
    QTimer.singleShot(timeout_ms, loop.quit)
    loop.exec()


def _dialog(settings, app):
    # Never touch the real Windows Credential Manager in tests.
    with patch("src.advanced_settings_dialog.get_api_key", return_value=""), \
         patch("src.advanced_settings_dialog.set_api_key"), \
         patch("src.advanced_settings_dialog.delete_api_key"):
        dlg = AdvancedSettingsDialog(settings, None, None)
        return dlg


def test_ai_fields_gating():
    ok = True
    app = _app()
    dlg = _dialog(Settings.default(), app)
    ok &= _check("U1. 默认（AI 关）: 细节字段禁用",
                 not dlg._ai_model.isEnabled() and not dlg._ai_key.isEnabled()
                 and not dlg._ai_timeout.isEnabled() and not dlg._test_btn.isEnabled())
    ok &= _check("U2. 默认（AI 关）: 总开关可用", dlg._ai_enabled.isEnabled())
    dlg._ai_enabled.setChecked(True)
    ok &= _check("U3. 勾选后: 细节字段启用",
                 dlg._ai_model.isEnabled() and dlg._ai_key.isEnabled()
                 and dlg._ai_timeout.isEnabled() and dlg._test_btn.isEnabled())
    dlg._ai_enabled.setChecked(False)
    ok &= _check("U4. 取消勾选: 字段再次禁用", not dlg._ai_model.isEnabled())
    dlg.deleteLater()
    return ok


def test_accept_persists_v06_fields():
    ok = True
    app = _app()
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "settings.json"
        s = Settings.default()
        s._path = str(p)

        dlg = _dialog(s, app)
        dlg._ai_enabled.setChecked(True)
        dlg._ai_endpoint.setText("https://gw.example/v1")
        dlg._ai_model.setText("gpt-4o-mini")
        dlg._ai_timeout.setValue(30)
        dlg._ai_ocr.setChecked(False)
        dlg._ai_desc.setChecked(True)
        dlg._ai_prompt.setText("看图说话")
        dlg._ai_key.setText(SECRET)
        dlg.accept()

        ok &= _check("P1. 保存: enabled", s.ai.enabled is True)
        ok &= _check("P2. 保存: endpoint/model/prompt",
                     s.ai.endpoint == "https://gw.example/v1"
                     and s.ai.model == "gpt-4o-mini"
                     and s.ai.prompt == "看图说话")
        ok &= _check("P3. 保存: timeout=30", s.ai.timeout_seconds == 30.0)
        ok &= _check("P4. 保存: OCR 关", s.ai.ocr_enabled is False)
        ok &= _check("P5. 保存: 描述开", s.ai.image_description_enabled is True)
        ok &= _check("P6. 保存: provider", s.ai.provider == "openai-compatible")

        text = Path(p).read_text(encoding="utf-8")
        ok &= _check("P7. settings.json 不含 Key", SECRET not in text)
        ok &= _check("P8. settings.json 不含 api_key 键", "api_key" not in text)
        parsed = json.loads(text)
        ok &= _check("P9. settings.json 含新键",
                     "timeout_seconds" in parsed["ai"]
                     and "ocr_enabled" in parsed["ai"]
                     and "image_description_enabled" in parsed["ai"])
    return ok


def test_connection_test_button():
    ok = True
    app = _app()
    dlg = _dialog(Settings.default(), app)
    dlg._ai_enabled.setChecked(True)

    # No model -> immediate guidance, no thread started.
    dlg._on_test_connection()
    ok &= _check("T1. 无模型名 -> 提示且不启动线程",
                 "模型" in dlg._test_result.text() and dlg._test_runner is None)

    # With model -> runs on a QThread, button disabled while probing.
    dlg._ai_model.setText("gpt-4o")
    canned = ConnectionTestResult(ok=True, message="连接成功：服务可达，Key 有效，模型 gpt-4o 可调用。",
                                  duration_ms=42, model="gpt-4o")
    with patch("src.ai_provider.test_connection", return_value=canned):
        dlg._on_test_connection()
        ok &= _check("T2. 探测启动后按钮禁用", not dlg._test_btn.isEnabled())
        ok &= _check("T3. 状态显示测试中", "测试中" in dlg._test_result.text())
        _wait_signal(dlg._test_runner.finished_with_result)
        # Let queued signal delivery run.
        for _ in range(20):
            app.processEvents()
    ok &= _check("T4. 结果渲染（✓ + 消息 + 耗时）",
                 "✓" in dlg._test_result.text() and "42" in dlg._test_result.text(),
                 dlg._test_result.text())
    ok &= _check("T5. 探测完成后按钮恢复", dlg._test_btn.isEnabled())

    # Failure rendering.
    fail = ConnectionTestResult(ok=False, message="无法连接：xxx 不可达。", duration_ms=7)
    with patch("src.ai_provider.test_connection", return_value=fail):
        dlg._on_test_connection()
        _wait_signal(dlg._test_runner.finished_with_result)
        for _ in range(20):
            app.processEvents()
    ok &= _check("T6. 失败渲染（✗）", "✗" in dlg._test_result.text())

    # The runner thread must be finished before teardown (no destroyed-while-
    # running crash).
    ok &= _check("T7. 探测线程已结束", dlg._test_runner.isFinished())
    dlg.deleteLater()
    return ok


def test_runner_thread_is_qthread():
    """The probe runs OFF the GUI thread by construction (plan §3.4 barrier)."""
    ok = True
    runner = _ConnectionTestRunner.__new__(_ConnectionTestRunner)
    from PySide6.QtCore import QThread
    ok &= _check("R1. 探测运行于 QThread", isinstance(runner, QThread))
    return ok


def _main():
    ok = True
    ok &= test_ai_fields_gating()
    ok &= test_accept_persists_v06_fields()
    ok &= test_connection_test_button()
    ok &= test_runner_thread_is_qthread()
    print("RESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(_main())
