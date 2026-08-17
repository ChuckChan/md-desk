MdDesk v0.3（正式版）
================================

基于 Microsoft MarkItDown 的文档转 Markdown 桌面工具（非官方、无关联）。

【启动方式】
  双击目录内的 md-desk.exe 即可启动。

【重要】必须保留整个目录
  本程序以“目录”形式分发，运行时依赖同目录下的 _internal 文件夹
  （内含 Python 运行环境、Qt 库与转换引擎）。
  ⚠️ 不能只复制 md-desk.exe，必须把整个
  MdDesk-v0.3 文件夹一起拷贝到目标机器上运行。

【支持的核心功能】
  • 拖拽文件或点击“添加文件”，批量导入多种格式
    支持：PDF、Word(.docx)、Excel(.xlsx/.xls)、PowerPoint(.pptx)、
    HTML、纯文本(.txt)、CSV、Outlook(.msg)、安全的远程 URL、音频，
    以及 Microsoft MarkItDown 引擎支持的其他常见格式
  • 一键“开始转换”，批量转换为 Markdown
  • 右侧同时查看：Markdown 源码 / 渲染预览（Qt 原生渲染）
  • 复制 Markdown 文本、导出为 .md 文件（UTF-8 编码）
  • 损坏或暂不支持的文件不会导致程序崩溃，会标记为 ERROR / UNSUPPORTED
  • v0.3 新增「AI 增强转换」（可选，默认关闭）：LLM 图片描述 +
    图片 / 扫描件 OCR，结果嵌入 Markdown。

【AI / OCR 前置条件（重要）】
  • 该功能需要你自备一个“支持 Vision 的 OpenAI 兼容 API”
    （自定义 endpoint + 模型名）。
  • API key 保存在 Windows 凭据管理器，不会以明文写入任何文件。
  • 本版本未对真实云服务商做联网鉴权 / 额度实测；请使用你信任的
    兼容服务。详见同目录 RELEASE.md。

【已知限制】
  • 预览区使用 Qt 原生 Markdown 渲染：GFM 表格、任务列表等扩展语法
    不会渲染为表格 / 勾选框，会以原始文本显示；但复制 / 导出的是
    标准 Markdown 源码，内容不受影响。
  • 本版本未做代码签名（无数字证书）。
  • OCR 若调用失败，结果会包含“*[OCR Error] … [End OCR Error]*”
    标记，便于你识别“转换完成但 OCR 未成功”，不会被伪装成正常内容。
  • 仅支持 Windows x64。

【关于 Windows SmartScreen / 杀毒软件提示】
  由于安装包未经代码签名，首次运行时 Windows SmartScreen 或杀毒软件
  可能弹出“未知发布者 / 已阻止”的警告。这属于正常现象，并非程序有毒：
  • 若被 SmartScreen 拦截，点击“更多信息”→“仍要运行”即可；
  • 或在文件上右键 → 属性 → 勾选“解除锁定”→ 确定；
  • 也可将本程序目录加入杀毒软件白名单。

更多验收信息与 AI/OCR 技术说明见同目录的 RELEASE.md。
