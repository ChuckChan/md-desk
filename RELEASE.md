# MdDesk v0.2 — Release

**状态：** 已发布（Release）
**日期：** 2026-08-17
**构建方式：** PyInstaller 6.22.1 单目录打包（onedir + windowed），自包含运行环境。
  转换引擎基于 Microsoft MarkItDown 0.1.7（本工具为其非官方 GUI 封装，无关联；引擎版本锁定，不升级）。

## 相较 v0.1.0 新增能力

- **Outlook `.msg` 邮件转换**（依赖 `olefile`，由 `markitdown[outlook]` 引入）
- **安全的远程 http/https URL 输入**：自研 `UrlFetchService`（纯 stdlib）做 SSRF / 重定向 / 超时 / 体积防护，连接 PIN 到已校验 IP 防 DNS rebinding；**禁用 `MarkItDown.convert_uri()`**
- **YouTube 字幕提取**（`youtube-transcript-api`，可在高级设置选择字幕语言）
- **音频转写**：调用 Google 在线语音识别（需联网）；WAV 免 FFmpeg，MP3/M4A/MP4 需系统 FFmpeg（不打包）
- **高级设置**：YouTube 字幕语言 + 单文件输入探测覆盖（扩展名 / MIME / 字符集 / 文件名）

## 验收结论

v0.2 测试矩阵全部 PASS（13 个测试脚本，共 185 项断言），`verify_dist_zip.py` 三关全过：

- **源码测试矩阵**（packaging venv，offscreen）：converter(9) / worker(10) / stage3_integration(8) / regression_formats(13) / advanced_settings(20) / file_model(12) / msg_stage1b(8) / tls_stage2(9) / url_stage2(42) / audio_stage5(13) / url_native_stage3(11) / stage4(16) / stage5(14)，全部 rc=0、0 FAIL。
  - 注：`test_tls_stage2` 原有一处误报（grep 模式 `environ` 命中 `src/settings.py` 中合法的 `os.environ.get("APPDATA")` 配置目录定位），已将其扫描模式收窄为 `ALLOW_HOSTS|allow_hosts`（仅限测试修正，不动产品代码），复跑 9/9 PASS。产品代码无任何 allow_hosts 启用钩子。
- **EXE 构建**：`build_exe.sh` 干净重建，`PYINSTALLER_EXIT=0`；真实 `md-desk.exe`（16.5MB）offscreen 启动存活、无 traceback（仅 pydub 关于系统未安装 FFmpeg 的良性 RuntimeWarning，音频功能缺失时优雅降级）。
- **分发校验 `verify_dist_zip.py`**：EXTRACT_OK / STRUCTURE_OK（exe + `_internal` + RELEASE.md + README.txt）/ BOOT_OK（offscreen 启动存活）全部 PASS。
- **分发包**：`MdDesk-v0.2-Windows-x64.zip`，137,636,508 字节，SHA-256 `144f61f77ac736f6d5592e23c19c578da37d676da39ec05a3b281ea19400b1df`，顶层目录 `MdDesk-v0.2`。

## 运行时依赖

- VC Runtime 已内嵌（`VCRUNTIME140.dll` + `VCRUNTIME140_1.dll`），无需单独安装 VC Redist。
- Qt 平台插件 `qwindows.dll` 已随包发布。
- 音频转写依赖 Google 在线 SR（需联网）；MP3/M4A/MP4 需系统 FFmpeg（不打包，缺失时给出友好提示而非崩溃）。
- YouTube 字幕网络请求不经过 MdDesk 的 `UrlFetchService` 安全层（遵循上游 markitdown 实现）。

## 已知非阻塞事项

- 首次运行可能被 Windows Defender / SmartScreen 拦截（未知发布者提示）。**非阻塞**：文件属性中「解除锁定」或将目录加入杀软白名单即可。无法在 headless 沙箱内观测。

## 交付物

- 可执行目录：`dist/md-desk/`（启动器 + 自包含 `_internal/` 目录，需整目录拷贝）
- 回归验证脚本：`tests/` 下全套源码测试 + `tests/exe_*_smoke.py` 冻结烟雾测试
- 构建脚本：`build_exe.sh`
- 分发包：`MdDesk-v0.2-Windows-x64.zip`（顶层目录 `MdDesk-v0.2`）

## 范围说明（v0.2 不做）

OCR / LLM 图片描述 / 并发转换 / 原文件预览 / 主题切换 / 插件系统 / Azure DI·CU / exiftool —— 均不在本版本范围内。
