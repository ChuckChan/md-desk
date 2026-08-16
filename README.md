# MdDesk

> 基于 Microsoft MarkItDown 的文档转 Markdown 桌面工具（非官方、无关联）。

MdDesk 是一个 Windows 桌面 GUI，把各种文档（PDF / Word / Excel / PowerPoint / HTML / 纯文本 / CSV 等）批量转换为 Markdown。底层转换由 [Microsoft MarkItDown](https://github.com/microsoft/markitdown) 驱动；MdDesk 只是它的图形界面封装，与 Microsoft 无关联。

## 下载与运行

- 前往 **Releases** 下载 `MdDesk-v0.2-Windows-x64.zip`
- 解压后**整个文件夹**一起拷贝到目标机器
- 双击 `md-desk.exe` 启动

> ⚠️ 不能只复制 `md-desk.exe`，必须保留同目录的 `_internal/`（内含 Python 运行环境、Qt 库与转换引擎）。

## 核心功能

- 拖拽 / 添加文件，批量导入多种格式
- 一键批量转换为 Markdown
- 右侧查看 Markdown 源码 + 渲染预览（Qt 原生渲染）
- 复制 Markdown、导出 `.md`（UTF-8）
- 错误文件（损坏 / 不支持）不会崩溃，标记为 ERROR / UNSUPPORTED

## 已知限制

- 预览区使用 Qt 原生 Markdown 渲染：GFM 表格、任务列表等扩展语法不会渲染为表格 / 勾选框，会以原始文本显示（复制 / 导出的是标准 Markdown 源码，不受影响）。
- 未做代码签名；首次运行可能被 Windows SmartScreen / 杀软拦截（文件属性「解除锁定」或加白名单即可，非阻塞）。
- v0.2 新增：Outlook `.msg`、安全的远程 http/https URL 输入、YouTube 字幕提取、音频转写（Google 在线识别，需联网）、高级设置（字幕语言 / 输入探测覆盖）。
- v0.2 不含：OCR、LLM 增强、并发转换、原文件预览、主题切换。
- 仅支持 Windows x64。

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
pytest tests/ -q
```

## License

[MIT](LICENSE) — 基于 Microsoft MarkItDown（同样 MIT）。非官方封装，与 Microsoft 无关联。
