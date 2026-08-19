# MdDesk v0.4.0 — Release

**Status:** Released（已发布 / published）
**Date:** 2026-08-19
**Build:** PyInstaller onedir + windowed, self-contained runtime. Conversion engine: Microsoft **MarkItDown 0.1.7** (pinned, not upgraded). v0.4.0 layers diagnostics + opt-in quality inspection on top of v0.3; conversion behavior with quality OFF is byte-for-byte identical to v0.3.

> **MdDesk v0.4.1（收口修复版 / maintenance）** is prepared on top of this release (see the dedicated section below). It fixes the YouTube-subtitle-language batch wiring, consolidates the version into a single source, and corrects this document's RC wording. It does **not** add v0.5 features and does **not** change v0.4 default behavior.

---

## MdDesk v0.4.1（收口修复版 / maintenance）— 待发布

**Status:** 待发布（基于 v0.4.0；未 tag / 未 push / 未创建 Release）
**基线：** tag `v0.4.0`（commit `0324e39`）
**目标：** 修复 v0.4.0 遗留的收口问题；不新增 v0.5 功能；不改变 v0.4 默认行为与功能。

### 修复内容
1. **YouTube 字幕优先语言接入批量路径（核心修复）**：批量转换时 `ConversionWorker` 此前只把 `engine_config` 传给 `convert_entry`，未传 `settings`，导致「高级设置」里的 `youtube_transcript_languages` 实际不生效。`v0.4.1` 在 worker 中把 `settings` 一并传入，真实批量路径下该设置会转发到引擎的 `youtube_transcript_languages` 参数（转换器层支持此前已具备，验证见 `tests/test_youtube_batch.py`）。
2. **单一版本来源**：新增 `src/version.py`（`__version__ = "0.4.1"` + `user_agent()`）。`url_fetch_service.DEFAULT_USER_AGENT` 不再硬编码 `MdDesk/0.3`，改为从单一来源读取；`make_dist_zip.py` / `verify_dist_zip.py` 的 ZIP 名称与根目录也统一引用该来源，消除版本漂移。
3. **RELEASE.md 修正**：原文档仍标记为 “Release Candidate / 等待发布批准”，已改为 “Released（已发布）”，与正式 v0.4.0 Release 一致。
4. **README 一致性**：README.md / README.zh-CN.md 中过时的 “63 pytest cases” 改为真实用例数（见下方验收），三者（README.md / README.zh-CN.md / README.txt）关于版本与发布事实保持一致。README.txt 已为「正式版」，无需改动。
5. 默认行为不变：quality 默认 OFF、AI 默认 OFF、安全 URL、凭据存储、OCR/诊断语义均未回归。

### 回归
- `pytest tests/` 全绿（含新增：YouTube 批量接线测试 `tests/test_youtube_batch.py`、版本单一来源回归 `tests/test_version.py`）。
- 源码模式 RC 冒烟 `python tests/exe_stage6_rc_smoke.py` → RC_PASS。
- 冻结 EXE RC 冒烟（`md-desk-rc-smoke.spec`）→ RC_PASS。

## What's new in v0.4.0 (vs v0.3)

- **Unified conversion-result pipeline** (`ConversionResult` + a single `file_finished` signal) — one terminal path now carries both success and failure, removing the old dual-signal handling and making terminal-state updates robust.
- **Conversion quality inspection** (`QualityInspector`, v0.4 Stage 2) — opt-in via **Advanced Settings**, **default OFF**. On a successful conversion it runs a lightweight static check (empty output / abnormally short output / low text yield / garbled text / OCR-failure markers) and surfaces *advisory* warnings only. It never modifies the conversion result or status.
- **Conversion report + diagnostic log** (`ConversionReport` + `DiagnosticLogger`, v0.4 Stage 3) — each conversion produces a metadata-only report (source, status, duration, output size, warnings) persisted to a **rotating, size-capped** log (stdlib only). The log contains **no Markdown body and no secrets** (URLs/errors are redacted).
- **Diagnostics UI panel** ("诊断" tab, v0.4 Stage 4) — shows the per-file report, quality warnings, and error details; has buttons to open the diagnostic log. It never renders the Markdown body.
- **Stage 5 stabilization** — fixed a regression subprocess hang (Windows `close_fds` handle inheritance), added log rotation, hardened the UI against unknown warning codes / source types; no user-facing behavior change, quality OFF by default.

---

## 相较 v0.3 新增能力（中文）

- **统一转换结果管线**（`ConversionResult` + 单一 `file_finished` 信号）：成功与失败共用一条终态路径，取代旧的双信号处理，终态更新更稳健。
- **转换质量检查**（`QualityInspector`，v0.4 Stage 2）：在「高级设置」中开启，**默认关闭**。成功的转换会做轻量静态检查（空输出 / 异常短 / 文字产出过低 / 乱码 / OCR 失败标记），仅产生*提示*，绝不修改转换结果或状态。
- **转换报告 + 诊断日志**（`ConversionReport` + `DiagnosticLogger`，v0.4 Stage 3）：每次转换产出仅含元数据的报告（来源、状态、耗时、输出字数、提示），写入**带大小上限的轮转日志**（纯标准库）。日志**不包含 Markdown 正文、不包含密钥**（URL / 错误已脱敏）。
- **诊断面板**（「诊断」标签页，v0.4 Stage 4）：展示每个文件的报告、质量提示与错误详情，可一键打开诊断日志；不渲染 Markdown 正文。
- **Stage 5 稳定化**：修复回归子进程挂死（Windows `close_fds` 句柄继承）、增加日志轮转、加固界面对未知 warning code / source type 的兼容；不改变用户可见行为，质量检查默认关闭。

---

## Acceptance / 验收结论

### 1. Full test suite / 完整测试

- `pytest tests/` (no regression excluded): **116 passed, 0 failed, 84 warnings, 308.60s**.
  - Includes the new `test_settings_v03_migration.py` (v0.3 → v0.4 settings migration: original config preserved, `quality_enabled=False`).
  - Includes regression subprocess gates (`test_advanced_settings`, `test_stage4`, `test_stage5`) which previously hung; fixed in Stage 5.

### 2. Frozen RC smoke / 冻结 RC 冒烟

- `dist/md-desk-rc-smoke-fix/md-desk-rc-smoke-fix.exe`（由 `tests/exe_stage6_rc_smoke.py` 经 `md-desk-rc-smoke.spec` 冻结；**全新 name/workpath 重建以规避失效的 Analysis 缓存**）：**RC_PASS / RC_EXIT=0**，覆盖全部 S6.1–S6.11 断言：
  local file（真实 MarkItDown）、batch、URL 端到端（mock fetch+engine）、YouTube（accept + `youtube_transcript_languages` 转换器层转发）、StreamInfo 覆盖（机制 + 真实误标扩展名透传）、Advanced Settings（quality 开关持久化）、preview/copy/export、quality OFF（无警告）、quality ON+warning（状态显示"完成 (质量提示)"）、diagnostics UI（成功/警告/错误/未知类型）、日志脱敏+轮转（仅元数据）、**magika 模型已打包 / markitdown 冻结可导入**。
  证据：`rc_smoke_fix.log`。

> **修复记录（2026-08-19 02:03）**：早期冻结构建 6 次失败，根因已修复——① PYZ 未收集 `src`（旧 `build_rc` Analysis 缓存失效 + harness 在冻结模式把不稳定 `ROOT` 路径塞入 `sys.path`）；② harness `_run_batch` 手动 `deleteLater()`+`sendPostedEvents()` 同步删除 worker QThread 触发 shiboken "already deleted"。修复：harness 仅源码模式插入 `sys.path`、移除手动 worker 删除；以全新 `--workpath build_rc_fix` + spec 内 `name='md-desk-rc-smoke-fix'` 重建。修复后 PYZ 含 16 个 `src` 模块（含裸 `src` 包），冻结冒烟全绿。

- **Source-mode RC smoke（同源验证）**：`python tests/exe_stage6_rc_smoke.py` → **RC_PASS / SRC_EXIT=0**（S6.11 冻结专属检查在源码模式跳过）。证据：`rc_source2.log`。

### 3. Product EXE / 产品可执行文件

- `dist/md-desk/md-desk.exe` rebuilt via `build_exe.sh` (official config): **23487300 bytes**.
- Offscreen boot survives (no fatal stderr; only the benign pydub/FFmpeg `RuntimeWarning`).
- Frozen resources verified: `magika` model `standard_v3_3/model.onnx` bundled; `markitdown` importable; `markitdown_ocr` collected.

### 4. Distribution / 分发校验

- `MdDesk-v0.4.0-Windows-x64.zip`: **164866334 bytes (~157 MB)**, SHA-256 `615b064cc0ad0db0b1661383cc9587504b945d4f0b100bf13b176e43d3e2a786`.
- `verify_dist_zip.py` passes: extract + structure (`md-desk.exe` + `_internal` + `RELEASE.md` + `README.txt` + `README.md` + `README.zh-CN.md`) + content audit (no tests / source `.py` / secrets / temp `.log`) + offscreen boot.

---

## Known gaps (non-blocking) / 已知限制（非阻断）

1. ~~**YouTube 字幕优先语言未接入批量转换路径**~~ → **已在 v0.4.1 修复**：worker 现把 `settings` 一并传给 `convert_entry`，`youtube_transcript_languages` 在真实批量路径下转发到引擎（验证见 `tests/test_youtube_batch.py`）。
2. **真实 Provider AI/OCR 联网 E2E 未做**：仅离线 dummy 客户端验证接线与标记。需用自有服务实测。
3. **未做代码签名**：首次运行 SmartScreen / 杀软拦截（解除锁定或加白名单）。
4. **预览区 Qt 原生渲染**：GFM 表格 / 任务列表等扩展语法以原始文本显示（复制 / 导出源码不受影响）。
5. Vision / OCR / Audio 本身为 v0.3 既有能力；v0.4 未新增相关功能，亦未改变其默认关闭行为。

---

## Deliverables / 交付物

- 可执行目录：`dist/md-desk/`（启动器 + 自包含 `_internal/`）
- RC 冒烟：`dist/md-desk-rc-smoke-fix/`（发布工程产物，不随产品 ZIP 分发给终端用户）
- 回归验证：`tests/` + `tests/exe_stage6_rc_smoke.py`
- 构建/分发脚本：`build_exe.sh`, `make_dist_zip.py`, `verify_dist_zip.py`
- 分发包：`MdDesk-v0.4.0-Windows-x64.zip`（顶层目录 `MdDesk-v0.4.0`）
