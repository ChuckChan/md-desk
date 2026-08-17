# MdDesk v0.3 — Release

**状态：** 待发布（Release 工程完成，等人工批准）
**日期：** 2026-08-17
**构建方式：** PyInstaller 6.22.1 单目录打包（onedir + windowed），自包含运行环境。
  转换引擎基于 Microsoft MarkItDown 0.1.7（本工具为其非官方 GUI 封装，无关联；引擎版本锁定，不升级）。
  v0.3 在 v0.2 基础上新增 AI 增强转换（LLM 图片描述 + 图片 / 扫描件 OCR），由 vendored `markitdown-ocr` 插件驱动。

## 相较 v0.2 新增能力

- **LLM 图片描述（AI 增强）**：图片文件转换时，调用「支持 Vision 的 OpenAI 兼容 API」生成图片说明并嵌入 Markdown。
- **图片 / 扫描件 OCR（AI 增强）**：PDF、Word、PPT、Excel 中的图片与扫描页，调用同一 Vision API 做 OCR，识别文字以 `*[Image OCR] ... [End OCR]*` 块嵌入 Markdown。
- **OCR 失败有稳定、可识别标记**：OCR API 调用失败时，结果包含 `*[OCR Error] ... [End OCR Error]*`（绝不会伪装成成功的 `*[Image OCR]` 内容）。这一约定是 v0.3 的硬性要求，源码与冻结二进制中均验证通过。
- **AI 配置 UI + Windows 凭据管理器**：endpoint / model 存于设置；API key 仅存 Windows 凭据管理器，不落明文、无 Fernet 回退。
- **`vendor/markitdown-ocr`**：vendored 的 `markitdown-ocr` 插件（优先级 -1.0，注册 PDF/DOCX/PPTX/XLSX 四个 OCR converter）。

## 关于 `vendor/markitdown-ocr` 的来源与维护义务

> **重要（维护者必读）**：`vendor/markitdown-ocr` 基于 **Microsoft 官方 `markitdown-ocr` 插件**，并包含 MdDesk 的「OCR 错误块」补丁（`_ocr_service._format_ocr_block` 统一产出成功 / 错误标记，4 个 converter 全部路由经过它）。
>
> **后续升级上游插件需重新做兼容审计**：标记格式（`*[Image OCR]*` / `*[OCR Error]*`）、`register_converters` 的注册方式、4 个 converter 的优先级与类名，都可能随上游变化。升级后必须重跑 v0.3 冻结 smoke（`exe_v03_smoke.py`）与 `test_v03_ai.py` 的 OCR 标记用例（7c / 7d / 9 / 9b）。

## AI / OCR 的前提条件与验证边界

- **需要用户自备「支持 Vision 的 OpenAI 兼容 API」**（自定义 endpoint + 模型名）。MdDesk 不内置任何 API key、不内置任何模型。
- **真实 Provider 的鉴权 / 额度联网 E2E 未做**。本版本的自动化验证全部基于「离线 dummy OpenAI 兼容客户端」（不联网、无 key），覆盖：接口接线、4 个 converter 在冻结二进制中的注册与执行、OCR 成功 / 失败标记、图片描述路径。真实云服务商联网实测属于非阻断项，已记录，不在本发布阻断条件内。
- UI 当前**未**主动识别 `*[OCR Error]` 标记并弹警告（见 Remaining Gaps）。

## 验收结论

### 1. 完整测试发现（全绿）

- **`pytest tests/`**：**63 passed, 0 failed, 0 errors**（RC=0）。覆盖 URL / TLS / MSG / audio 回归 / regression_formats / 全部 v0.3 用例。
  - URL / TLS / MSG 为脚本式（`main()` 提供 `server_url` / `tmp` / `fixture`），由 `tests/conftest.py` 桥接为 pytest 可发现；二者作为脚本直接运行亦全过。
  - v0.3 用例 `test_v03_ai.py` 覆盖：AI-OFF 与 v0.2 等价、图片描述、扫描 PDF OCR、OCR 错误块标记稳定（7c）、错误块未被伪装成成功（7d）、DOCX/PPTX/XLSX OCR 失败标记（9 / 9b）。
- **`python tests/test_file_model.py`**（脚本模式）：**12 / 12 PASS**。
- **`python tests/test_audio_stage5.py`**（脚本模式）：**13 / 13 PASS**（含 `regression_formats`）。

> **测试工程修复（本发布内）**：`test_file_model.py` 原先仅能在脚本模式（`main()` 先建 `QApplication`）下运行；pytest 模式下两个实例化 Qt 控件的用例（`test_mime_drag`、`test_mainwindow_offscreen`）因无 `QApplication` 而崩溃。已补齐与仓库其他 GUI 测试一致的 `QApplication.instance() or QApplication([])` 写法，并让 `check()` 在失败时 `assert`（此前只 print，pytest 下永不失败）。修复后该文件 pytest 模式 **11 / 11 PASS**。

### 2. 冻结二进制 smoke（全绿）

- **`md-desk-v03-smoke.exe`**（独立构建，与 `md-desk.exe` 同收集标志）：**10 / 10 PASS**，含：
  1. `openai` 与 `markitdown_ocr` 被正确收集（importable）；
  2. `is_ocr_plugin_available()` 在冻结构建中为 True；
  3. AI-OFF 与 `MarkItDown()` 字节级等价（v0.2 行为保留）；
  4. 冻结插件路径（显式 `import markitdown_ocr` + `register_converters`，因 PyInstaller 丢弃 `.dist-info` 入口点）实际注册 4 个 OCR converter；
  5. 图片描述端到端 PASS；
  6. 扫描 PDF OCR 端到端 PASS（`*[Image OCR]*` 出现）；
  7. 扫描 PDF OCR 失败 → 稳定 `*[OCR Error]` 标记；
  8. DOCX / PPTX / XLSX OCR 失败 → 稳定 `*[OCR Error]` 标记（无 `*[Image OCR]`）。
- **`exe_stage4_smoke.exe`**（高级设置 / StreamInfo 覆盖）：PASS。

### 3. EXE 构建

- `build_exe.sh` 干净重建：`PYINSTALLER_EXIT=0`。
- 真实 `md-desk.exe`：**23,463,031 字节**（v0.2 为 16.5MB；增加来自 `markitdown_ocr` + `openai` 收集）。
- 收集标志新增：`--collect-submodules markitdown_ocr`、`--hidden-import openai`。

### 4. 冻结启动证据（准确表述）

- 真实 `md-desk.exe` offscreen 启动，**浸泡 6 秒无 fatal stderr**（仅 pydub 关于系统未安装 FFmpeg 的良性 `RuntimeWarning`，音频缺失时优雅降级）。
- 启动 harness 返回 **RC=124**：这是**测试 harness 主动超时（6s 后 kill）**，**不是**「程序正常退出」。程序在浸泡期间存活、无崩溃、无 traceback。

### 5. 分发校验 `verify_dist_zip.py`

- 三关：EXTRACT_OK / STRUCTURE_OK（`md-desk.exe` + `_internal` + `README.txt` + `README.md` + `RELEASE.md`）/ BOOT_OK（offscreen 启动存活）。
- 分发包：`MdDesk-v0.3-Windows-x64.zip`，顶层目录 `MdDesk-v0.3`。
- **大小**：164,834,816 字节（约 157 MB）
- **SHA-256**：`123270967480efa4da95579437f8c6b85ad45baa698861fad0300a1a68a9095f`

## 运行时依赖

- VC Runtime 已内嵌（`VCRUNTIME140.dll` + `VCRUNTIME140_1.dll`），无需单独安装 VC Redist。
- Qt 平台插件 `qwindows.dll` 已随包发布。
- 音频转写依赖 Google 在线 SR（需联网）；MP3/M4A/MP4 需系统 FFmpeg（不打包，缺失时给出友好提示而非崩溃）。
- AI / OCR 依赖用户自备的 Vision 兼容 API；key 走 Windows 凭据管理器。
- YouTube 字幕网络请求不经过 MdDesk 的 `UrlFetchService` 安全层（遵循上游 markitdown 实现）。

## 已知 Remaining Gaps（非阻断）

1. **UI 未接入 `markdown_has_ocr_error()`**：源码已有 `converter.markdown_has_ocr_error()`（识别 `*[OCR Error]` 标记），但 UI 尚不据其弹出「转换完成但 OCR 失败 / 部分失败」警告。本发布阶段不做 UI 扩功能，保留为已知 Gap。
2. **真实 Provider 鉴权 / 额度联网 E2E 未做**：仅离线 dummy 客户端验证。需用户用自有服务实测。
3. **首次运行 SmartScreen / 杀软拦截**：未知发布者提示，非阻塞（文件属性「解除锁定」或加白名单）。
4. **预览区 Qt 原生渲染**：GFM 表格 / 任务列表等扩展语法不渲染为表格 / 勾选框（源码不受影响）。
5. **测试工程**：`test_file_model.py` 的 GUI 用例在受资源约束的 headless harness 中，若单进程累积内存超限可能被 kill；已通过逐文件独立进程验证全绿，且同 MainWindow 启动路径由冻结 EXE offscreen 启动独立证明。

## 交付物

- 可执行目录：`dist/md-desk/`（启动器 + 自包含 `_internal/` 目录，需整目录拷贝）
- 冻结 smoke：`dist/md-desk-v03-smoke/md-desk-v03-smoke.exe`（可复跑的冻结验证；不随产品 ZIP 分发给终端用户，作为发布工程产物保留）
- 回归验证脚本：`tests/` 下全套源码测试 + `tests/exe_*_smoke.py` 冻结烟雾测试
- 构建脚本：`build_exe.sh`
- 分发包：`MdDesk-v0.3-Windows-x64.zip`（顶层目录 `MdDesk-v0.3`）

## 范围说明（v0.3 不做）

v0.3.1 / v0.4 功能、Azure DI·CU、并发转换、原文件预览、主题切换、MCP —— 均不在本版本范围内。
