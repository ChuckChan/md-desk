# MdDesk

> 基于 Microsoft MarkItDown 的文档转 Markdown 桌面工具（非官方、无关联）。

![版本](https://img.shields.io/github/v/release/ChuckChan/md-desk?label=版本&color=blue) ![License](https://img.shields.io/github/license/ChuckChan/md-desk?color=green) ![平台](https://img.shields.io/badge/平台-Windows%20x64-0078D4)

[English](README.md)

MdDesk 是一个 Windows 桌面 GUI，把各种文档（PDF / Word / Excel / PowerPoint / HTML / 纯文本 / CSV / Outlook `.msg` / 安全的远程 URL / 音频 等）批量转换为 Markdown。底层转换由 [Microsoft MarkItDown](https://github.com/microsoft/markitdown) 驱动；MdDesk 只是它的图形界面封装，与 Microsoft 无关联。

## 下载与运行

- 前往 **[Releases](https://github.com/ChuckChan/md-desk/releases/latest)** 下载 `MdDesk-v0.5.0-Windows-x64.zip`
- 解压后把**整个文件夹**拷贝到目标机器
- 双击 `md-desk.exe` 启动

> ⚠️ 不能只复制 `md-desk.exe`，必须保留同目录的 `_internal/`（内含 Python 运行环境、Qt 库与转换引擎）。

## 核心功能

- 拖拽 / 添加文件，批量导入多种格式
- 一键批量转换为 Markdown
- 右侧查看 Markdown 源码 + 渲染预览（Qt 原生渲染）
- 复制 Markdown、导出 `.md`（UTF-8）
- 错误文件（损坏 / 不支持）不会崩溃，标记为 ERROR / UNSUPPORTED
- **AI 增强转换（v0.3 新增，可选）**：
  - **LLM 图片描述**：图片文件（PNG/JPG 等）转换时，调用「支持 Vision 的 OpenAI 兼容 API」生成图片说明，嵌入 Markdown。
  - **图片 / 扫描件 OCR**：PDF、Word、PPT、Excel 中的图片与扫描页，调用同一 Vision API 做 OCR，识别文字以 `*[Image OCR] ... [End OCR]*` 块嵌入 Markdown。
  - AI 默认关闭。开启后在「高级设置」填写 endpoint / model；API key 存入 **Windows 凭据管理器**，不落明文、无 Fernet 回退。
- **诊断面板（v0.4.0 新增）**：「诊断」标签页展示每个文件的转换报告（来源、状态、耗时、输出字数）；开启质量检查后还会显示质量提示与错误详情。不渲染 Markdown 正文，可一键打开诊断日志。
- **转换质量检查（v0.4.0 新增，可选，默认关闭）**：在「高级设置」开启后，对成功的转换做轻量静态检查（空输出 / 异常短 / 文字产出过低 / 乱码 / OCR 失败标记），仅产生提示，绝不修改转换结果或状态。
- **批量生产力（v0.5.0 新增）**：支持整文件夹导入（递归扫描、去重）；只转换选中的文件；只重试失败的（ERROR / UNSUPPORTED）项；把全部成功结果批量导出到指定目录（重名安全、绝不覆盖源文件）；协作式取消（当前文件正常收尾，其余保持等待）；批次结束展示真实统计（总数 / 成功 / 质量提示 / 失败 / 未执行 / 耗时）。

## 使用条件 / 前提

- **仅支持 Windows x64。**
- **AI / OCR 需要用户自备「支持 Vision 的 OpenAI 兼容 API」**（endpoint + key）。MdDesk 不内置任何 API key、不内置任何模型。本版本自动化验证仅覆盖「接口接线 + 离线 dummy 客户端」；**真实 Provider 的鉴权 / 额度联网 E2E 未做**（非阻断项，已记录于 RELEASE.md）。
- **音频转写**依赖 Google 在线语音识别（需联网）；MP3/M4A/MP4 需系统 **FFmpeg**（不捆绑，缺失时给出友好提示而非崩溃）。
- **YouTube** 字幕获取不经过 MdDesk 的安全 URL 层（遵循上游 markitdown 实现）。

## 已知限制

- 预览区使用 Qt 原生 Markdown 渲染：GFM 表格、任务列表等扩展语法不会渲染为表格 / 勾选框，会以原始文本显示（复制 / 导出的是标准 Markdown 源码，不受影响）。
- **未做代码签名**；首次运行可能被 Windows SmartScreen / 杀软拦截（文件属性「解除锁定」或加白名单即可，非阻塞）。
- **OCR 失败有稳定标记**：当 OCR API 调用失败时，转换结果会包含 `*[OCR Error] ... [End OCR Error]*` 块（绝不会伪装成成功的 `*[Image OCR]` 内容）。开启「转换质量检查」后，「诊断」面板会主动显示该提示；默认关闭，因此不开质量检查则不会弹出提示。
- `vendor/markitdown-ocr` 插件**基于 Microsoft 官方 `markitdown-ocr` 插件**，并包含 MdDesk 的「OCR 错误块」补丁。**后续升级上游插件需重新做兼容审计**（标记格式、`register_converters` 注册方式、4 个 converter 的优先级可能变化）。
- v0.2 已含：Outlook `.msg`、安全的远程 http/https URL、YouTube 字幕、音频转写、高级设置。v0.3 在其上新增上述 AI 增强。

## 开发

```bash
pip install pyside6 markitdown   # 运行源码所需
python main.py                    # 启动 GUI（需 PySide6 + markitdown）
bash build_exe.sh                 # 用独立打包 venv 构建 exe（见 build_exe.sh 注释）
python make_dist_zip.py           # 生成分发 ZIP
python verify_dist_zip.py         # 校验 ZIP（解压/结构/offscreen 启动/SHA-256）
```

测试（需打包 venv + PySide6 可用）：

```bash
pip install pytest
pytest tests/ -q                    # 151 个 pytest 用例全过
python tests/test_file_model.py     # Stage 2 文件模型 12 项（脚本模式）
python tests/test_audio_stage5.py   # 音频 / 回归 13 项（脚本模式）
```

## License

[MIT](LICENSE) — 基于 Microsoft MarkItDown（同样 MIT）。非官方封装，与 Microsoft 无关联。
