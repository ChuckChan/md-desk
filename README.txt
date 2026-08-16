MdDesk v0.1.0 RC（对外试用版）
================================

基于 Microsoft MarkItDown 的文档转 Markdown 桌面工具（非官方、无关联）。

【启动方式】
  双击目录内的 md-desk.exe 即可启动。

【重要】必须保留整个目录
  本程序以“目录”形式分发，运行时依赖同目录下的 _internal 文件夹
  （内含 Python 运行环境、Qt 库与转换引擎）。
  ⚠️ 不能只复制 md-desk.exe，必须把整个
  MdDesk-v0.1.0-RC 文件夹一起拷贝到目标机器上运行。

【支持的核心功能】
  • 拖拽文件或点击“添加文件”，批量导入多种格式
    支持：PDF、Word(.docx)、Excel(.xlsx/.xls)、PowerPoint(.pptx)、
    HTML、纯文本(.txt)、CSV，以及 Microsoft MarkItDown 引擎支持的其他常见格式
  • 一键“开始转换”，批量转换为 Markdown
  • 右侧同时查看：Markdown 源码 / 渲染预览（Qt 原生渲染）
  • 复制 Markdown 文本、导出为 .md 文件（UTF-8 编码）
  • 损坏或暂不支持的文件不会导致程序崩溃，会标记为 ERROR / UNSUPPORTED

【已知限制】
  • 预览区使用 Qt 原生 Markdown 渲染：GFM 表格、任务列表等扩展语法
    不会渲染为表格 / 勾选框，会以原始文本显示；但复制 / 导出的是
    标准 Markdown 源码，内容不受影响。
  • 本版本未做代码签名（无数字证书）。
  • v0.1.0 不含：OCR、LLM 增强、并发转换、原文件预览、主题切换。
  • 仅支持 Windows x64。

【关于 Windows SmartScreen / 杀毒软件提示】
  由于安装包未经代码签名，首次运行时 Windows SmartScreen 或杀毒软件
  可能弹出“未知发布者 / 已阻止”的警告。这属于正常现象，并非程序有毒：
  • 若被 SmartScreen 拦截，点击“更多信息”→“仍要运行”即可；
  • 或在文件上右键 → 属性 → 勾选“解除锁定”→ 确定；
  • 也可将本程序目录加入杀毒软件白名单。

更多验收信息见同目录的 RELEASE.md。
