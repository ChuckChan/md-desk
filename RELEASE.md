# MdDesk v0.1.0 — Release

**状态：** 已发布（Release）
**日期：** 2026-08-16
**构建方式：** PyInstaller 6.22.1 单目录打包（onedir + windowed），自包含运行环境。
  转换引擎基于 Microsoft MarkItDown（本工具为其非官方 GUI 封装，无关联）。

## 验收结论

Stage 7 验收全部 MUST 项通过（13/13 回归检查 PASS）：

- ✅ 不依赖 Python 解释器
- ✅ 不依赖源码目录（中性目录独立启动）
- ✅ 双击 `.exe` 可启动（offscreen 启动存活，零 stderr）
- ✅ 拖拽文件正常 + 选择文件正常 + 重复文件去重
- ✅ PDF / DOCX / XLSX 至少各 1 个转换成功（=DONE）
- ✅ 批量转换正常
- ✅ Markdown 源码查看正常（`_source_view` 只读展示）
- ✅ 渲染预览正常（`QTextBrowser.setMarkdown()` toHtml 非空）
- ✅ 复制正常（`_act_copy` 随 DONE 启用，剪贴板无异常）
- ✅ 导出 `.md` 正常（UTF-8 写出，取消导出无异常）
- ✅ 错误文件不崩溃：损坏 PDF → ERROR、随机二进制 → UNSUPPORTED
- ✅ 关闭后可再次正常启动（relaunch）

## 运行时依赖

- VC Runtime 已内嵌（`VCRUNTIME140.dll` + `VCRUNTIME140_1.dll`），无需单独安装 VC Redist。
- Qt 平台插件 `qwindows.dll` 已随包发布。

## 已知非阻塞事项

- 首次运行可能被 Windows Defender / SmartScreen 拦截（未知发布者提示）。**非阻塞**：文件属性中「解除锁定」或将目录加入杀软白名单即可。无法在 headless 沙箱内观测。

## 交付物

- 可执行目录：`dist/md-desk/`（13.7 MB 启动器 + 223 MB 自包含目录，需整目录拷贝）
- 回归验证脚本：`_acceptance_test.py`（13 项检查）
- 构建脚本：`build_exe.sh`

## 范围说明（v0.1.0 不做）

OCR / LLM / 并发 / 原文件预览 / 主题切换 / 新 UI —— 均不在本版本范围内。
