# MdDesk v0.4.0 — Release

**Status:** Released（已发布 / published）
**Date:** 2026-08-19
**Build:** PyInstaller onedir + windowed, self-contained runtime. Conversion engine: Microsoft **MarkItDown 0.1.7** (pinned, not upgraded). v0.4.0 layers diagnostics + opt-in quality inspection on top of v0.3; conversion behavior with quality OFF is byte-for-byte identical to v0.3.

> **MdDesk v0.4.1（收口修复版 / maintenance）** is prepared on top of this release (see the dedicated section below). It fixes the YouTube-subtitle-language batch wiring, consolidates the version into a single source, and corrects this document's RC wording. It does **not** add v0.5 features and does **not** change v0.4 default behavior.

---

## MdDesk v0.4.1（收口修复版 / maintenance）— 已发布

**Status:** Released（已发布 / published，tag `v0.4.1` + GitHub Release，2026-08-19）
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

---

## MdDesk v0.5.0（批量生产力版 / batch productivity）— 已发布

**Status:** Released（已发布 / published，tag `v0.5.0` + GitHub Release，2026-08-19）
**基线：** commit `7cf195e`（v0.4.1，已发布）
**目标：** 在 v0.4.1 之上新增「批量生产力」六项功能；不改变 v0.4 默认行为、不升级 MarkItDown 0.1.7、不引入 v0.6 AI 能力。

### 发布元数据
- **Tag:** `v0.5.0`（annotated tag → commit `b4df24d`，release commit `6b8cd93`）
- **GitHub Release:** https://github.com/ChuckChan/md-desk/releases/tag/v0.5.0
- **正式资产：** `MdDesk-v0.5.0-Windows-x64.zip` — 164,880,155 bytes (~157.2 MB)
- **SHA-256：** `0f22ed0c0b16c75143ba8f5cd6aaef2a2103321cfd65dc396ec557ce7b5b22c6`
- **本地冻结 SHA 与 GitHub 下载 SHA 完全一致** ✅

### 新增功能（6 项）
1. **文件夹导入**：支持选择 / 拖入文件夹，递归扫描（确定顺序）；忽略目录本身；按规范化路径去重；既有文件导入行为不变。
2. **批量导出**：全部成功（DONE）项导出到指定目录；目标名 `{stem}.md`，批内重名按行序追加 `_2/_3…`；目标==源文件时跳过（**绝不覆盖源文件**）；单条写入失败不中断（计数 + 截断错误消息，永不 raise）；不保留目录结构（平铺导出，规则见 `src/export_service.py`）。
3. **转换选中项**：只转换当前选中的行；其余 WAITING / DONE 项不受影响。
4. **失败重试**：重试所有 ERROR / UNSUPPORTED 项；重试行重置为 WAITING 并清空旧结果 / 报告，重跑后生成全新诊断报告；非重试行不被触碰。
5. **安全取消**：cooperative cancellation（`threading.Event`，不使用 `QThread.terminate()`）；当前文件正常收尾；剩余任务不再启动、保持 WAITING；批次以 `batch_cancelled` 收尾。
6. **Batch Summary**：批次结束按**本批次任务行**统计并展示：总数 / 成功 / 质量提示 / 失败 / 未执行 / 耗时（perf_counter 实测），状态栏单行消息。

### 架构 / 文件变化
- 新增 Qt-free 模块：`src/folder_scanner.py`（目录扫描）、`src/export_service.py`（批量导出）、`src/batch_summary.py`（批次统计 + 状态栏消息）。
- `src/worker.py`：新增 `cancel()` / `is_cancelled()` 与 `batch_cancelled(success, failed)` 信号；run() 每任务前检查取消标志（协作式）。
- `src/file_model.py`：新增 `add_folder()` / `retryable_rows()` / `done_rows()` / `tasks_for_rows()`。
- `src/main_window.py`：新增「添加文件夹 / 转换选中 / 重试失败 / 取消 / 批量导出」动作；抽取 `_start_batch` / `_finish_batch`；拖放支持目录。
- `src/version.py`：`__version__ = "0.5.0"`。
- **安全边界未动**：settings.py（AI / quality 默认 OFF）、url_fetch_service.py（SSRF）、credential_store.py、quality.py、report.py、result.py、converter.py、file_entry.py 零改动；MarkItDown 0.1.7 未升级。

### 回归与验证（全部真实执行）
- `pytest tests/`：**151 passed, 0 failed**（基线 122 → 151；新增 29 例：文件夹扫描 / add_folder / worker cancel / 批量导出 / 批次统计 / selected-retry / v0.5 GUI 冒烟 + UnicodeError 回归）。
- 源码 RC 冒烟 `python tests/exe_stage6_rc_smoke.py` → **RC_PASS / SMOKE_EXIT=0**。
- v0.5 RC 冒烟（源码 + 冻结）：`tests/exe_v050_rc_smoke.py` → **ALL V0.5.0 RC CHECKS PASSED**。
- 冻结 EXE RC 冒烟（全新 name+workpath：`md-desk-rc-smoke-v050.spec` → `dist_rc_v050`）→ **RC_EXIT=0**（含 V5.7 冻结 EXE 内 markitdown 可导入）。
- 独立只读 Reviewer：**PASS**（4 条 NIT 已消化 2 条：批次统计范围改为「仅本批次任务行」、export_service 补捕获 `UnicodeError`；另 2 条按设计保留并记入已知限制）。

### 已知限制（非阻断）
1. **批量导出在 GUI 线程同步执行**：批量导出是纯文件 I/O（非转换），不违反「GUI 线程不执行耗时转换」硬约束；但条目极多时 UI 可能短暂卡顿。后续版本可移至后台线程。
2. **导出失败可能留下半成品文件**：单条写入失败（如权限 / 编码）会留下一个空 / 部分的目标 `.md`（标准写入行为），不覆盖源文件；已计入 failed 统计。沙箱安全策略下不做进程内删除。
3. 统计口径：批次摘要只统计本批次任务行（转换选中 / 重试失败时不会混入批次外行）；「未执行」= 本批次内取消后仍为 WAITING 的行。
4. 批内重名去重以行序为准：被「目标==源文件」跳过的条目仍占用其目标名，后续同名条目得 `_2` 后缀（一致的去重语义，无安全影响，见 `src/export_service.py` docstring）。

---

## MdDesk v0.6.0（AI 实用化版 / AI provider unification）— 已发布

**Status:** Released（已发布 / published，tag `v0.6.0` + GitHub Release，2026-08-20）
**基线：** tag `v0.5.0`（release commit `6b8cd93`，已发布）
**目标：** 在 v0.5.0 之上建立统一 AI Provider 抽象与 AI 实用化能力（连接测试 / 能力独立开关 / 故障隔离 / 凭据安全）；不进入 v0.7 功能（STT / 视频 / Azure DI / 知识库 / MCP / Agent 等一律不做）。

### 发布元数据
- **Tag:** `v0.6.0`（annotated tag object `10fe7bc0` → **release commit `146f8ec`**）
- **GitHub Release:** https://github.com/ChuckChan/md-desk/releases/tag/v0.6.0
- **正式资产：** `MdDesk-v0.6.0-Windows-x64.zip` — 164,897,910 bytes (~157.2 MB)
- **SHA-256：** `e953cbd61e4a33829b8814f7a8ae42347acb786362b3e1415ab138b1a9f31a8f`
- **本地冻结 SHA 与 GitHub 下载 SHA 完全一致** ✅（下载后实算 SHA-256 比对）

### 新增能力（6 项）
1. **统一 AI Provider 配置 + Client Factory**：`Settings → EngineConfig → AIProviderConfig → ClientFactory` 单一构建路径；OpenAI 兼容客户端强制注入 `timeout` 与 `max_retries=0`（避免 SDK 默认重试使实际等待 3 倍超时）；timeout 钳制 [1,600] 秒，默认 60。
2. **API Key 安全**：仅存 Windows Credential Manager（`MdDesk/AI/OpenAI-Compatible-Key`），永不进入 settings.json / 日志 / 报告；错误消息经 `_redact_secrets` 脱敏（含 Authorization / Bearer / JWT / key=value / 裸 `sk-…` 形态）。
3. **连接测试**：高级设置内一键测试（后台 QThread，不卡 UI）；单次最小 chat completion 一次往返验证 endpoint / credential / model；错误分类（鉴权 / 权限 / 配额 / 超时 / 网络 / 参数 / 404 / 服务端），消息恒定中文且不含异常原文。
4. **OCR 与图片描述独立开关**：`ocr_enabled` 控制 markitdown-ocr 插件（PDF/DOCX/PPTX/XLSX 扫描识别），`image_description_enabled` 控制内置 ImageConverter（JPG/PNG LLM 描述）；因 markitdown 构造参数无法只喂 OCR 插件而不喂图片描述，采用显式 `markitdown_ocr.register_converters(md, …)` 接线，dev 与 frozen 同一路径。
5. **AI 故障隔离**：Provider 故障（鉴权 / 超时 / 网络 / 配额等）时自动以无 AI 配置重试，文件照常 DONE 产出，并附加 `AI_PROVIDER_FAILURE` QualityWarning（含 provider / model / 耗时 / 脱敏错误）；报告与诊断面板可见；重试仍失败才报错（错误保持链式）。
6. **旧 Settings 兼容**：v0.5 文件无需迁移即用（新增可选键 provider / timeout_seconds / ocr_enabled / image_description_enabled 均带默认值，不 bump schema version）；垃圾值安全回退；无 AI 配置时行为与 v0.5 完全一致（纯 `MarkItDown()`）。

### 架构 / 文件变化
- 新增：`src/ai_provider.py`（Provider 模型 + ClientFactory + 连接测试，Qt-free）；测试 `tests/test_v06_provider.py` / `test_v06_settings.py` / `test_v06_capabilities.py` / `test_v06_settings_ui.py` / `tests/exe_v060_rc_smoke.py`。
- 修改：`src/settings.py`（AI 新键 + timeout 规范化）、`src/engine_config.py`（provider 字段 + `to_provider_config()`）、`src/markitdown_factory.py`（能力解耦接线）、`src/converter.py`（AI 失败隔离 + URL 流回卷）、`src/worker.py`（warning 透传）、`src/advanced_settings_dialog.py`（新 UI + 连接测试）、`src/main_window.py`（OCR/模型缺失提示）、`src/report.py`（裸 `sk-` 脱敏）、`src/version.py`（0.6.0）。
- **安全边界未动**：credential_store.py / quality.py / file_entry.py 零改动；MarkItDown 0.1.7 未升级。

### 回归与验证（全部真实执行）
- `pytest tests/`：**168 passed, 0 failed**（v0.5 基线 151 → 168；新增 17 例：provider / settings 迁移 / 能力开关矩阵 / 设置 UI / URL 流回卷回归）。
- 源码 RC 冒烟 `tests/exe_v060_rc_smoke.py` → **ALL V0.6.0 RC CHECKS PASSED**（含真实 localhost 连接测试 4 场景：成功 / 401 / 超时 / 不可达）。
- 冻结 EXE RC 冒烟（`md-desk-rc-smoke-v060.spec` → `dist_rc_v060b`）→ **32/32 PASS / SMOKE_EXIT=0**（V6.1–V6.7，含冻结 EXE 内 markitdown / markitdown_ocr / openai / src.ai_provider 可导入）。
- 独立 Reviewer 两轮：首轮 **FAIL**（BLOCKER：URL 条目 AI 降级重试复用已耗尽 BytesIO → 静默空输出；MAJOR：新测试 `return ok` 不被 pytest 强制）→ 全部修复（`e8bdc8c` / `146f8ec`，含回归测试，验证去修复必 FAIL）→ 复核 **PASS**。
- 正式产物（`dist_v060`，md-desk.spec）：offscreen boot **8 秒存活无致命退出**；`verify_dist_zip.py` → EXTRACT_OK / STRUCTURE_OK / CONTENT_AUDIT_OK（无 `.py` / tests / logs / secrets）。
- 已知：未做代码签名，Windows Defender / SmartScreen 可能对首次下载的 exe 弹提示或隔离（v0.4 起已记录，非 v0.6 回归）。

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
