# MdDesk v0.2 Implementation Plan — REVISED

> 审计基准日期：2026-08-16
> 审计对象：当前 MdDesk GUI（`markitdown-gui/`） + 本地 `markitdown` 源码（版本 **0.1.7**） + Microsoft `markitdown` **v0.1.7** git tag（commit `fd239d5`）
> 上游 `main` 仅用于发现未来变化，**不作为 v0.2 生产依赖**
> 本文仅做审计与计划 + 已执行 Stage 0（可复现构建基线）与 Stage 1A（当前环境基线探针）；**未修改任何功能代码、未安装依赖、未构建 EXE、未进入 Stage 1B**。
> 修订版相对初版纠正了：版本前提、EPUB 依赖、URL 架构安全性、Audio 设计、Settings 拆分、URL-native 能力误拆；相对上一轮再纠正 4 项执行级问题：MSG 不预设“必失败”、requirements 用官方 extras、URL 架构改用 convert_stream、Stage 1 拆 1A/1B。

---

## 1. Audit Baseline（审计基准）

| 项 | 内容 | 来源 |
|---|---|---|
| MdDesk 引擎调用 | `src/converter.py` → `MarkItDown().convert(path).markdown`：默认 `MarkItDown()`、仅本地路径、**无 option、无 URL、无 stream_info、无设置面板** | 直接读取 `markitdown-gui/src/converter.py`、`worker.py`、`main_window.py` |
| MdDesk GUI | PySide6；文件对话框筛选器为 `"所有文件 (*.*)"`（不限格式）；顺序批量转换；Markdown 源码/渲染预览；复制、导出 .md | 直接读取 `main_window.py` |
| 本地 markitdown 源码版本 | `__version__ = "0.1.7"`（`packages/markitdown/src/markitdown/__about__.py`） | 直接读取 |
| PyPI 最新稳定版 | **0.1.7**（发布 2026-07-29，yanked=false）；截至审计日**无更新版本** | `https://pypi.org/pypi/markitdown/json` |
| v0.1.7 git tag | `v0.1.7`（注意带 `v` 前缀），commit `fd239d5` | GitHub releases/tag/v0.1.7 |
| `main` 分支 | 转换器注册表 `__init__.py` 与 v0.1.7 **逐行一致**（22 个导出类）；无确认的“新增转换器” | raw.githubusercontent.com `main` vs `v0.1.7` 对比 |
| 注册机制 | `MarkItDown.enable_builtins()` 注册全部 converter；可选依赖在模块加载时 `try/except` 惰性导入，缺失时 `convert()` 抛 `MissingDependencyException` | 直接读取 `_markitdown.py`、`converters/__init__.py` |
| 打包基线 | `md-desk.spec` 的 `hiddenimports` 含 `defusedxml`、`mammoth`、`pdfminer`、`pptx`、`pandas`、`xlrd`、`bs4`、`markdownify`、`magika`、`requests`、`PIL` 等；**不含** `olefile`、`pydub`、`speech_recognition`、`ebooklib`、`youtube_transcript_api`、`openai`、`azure.*` | 直接读取 `md-desk.spec` |
| 版本钉死 | `build_exe.sh` 依赖 `markitdown_packaging_venv` 中已装版本；仓库**无 `requirements.txt`、无 NSIS/.iss**；任何文件都**未钉死版本** | 全局 glob 确认 |

---

## 2. Verified Facts（已核实事实）

1. **markitdown 稳定版仍为 0.1.7**，本地源码与 PyPI 均为 0.1.7，无更新版本 → “升级 markitdown” 是空前提，**改为锁定 `markitdown==0.1.7`**。
2. **EPUB 不依赖 `ebooklib`**。源码 `_epub_converter.py` 仅导入 `zipfile`（stdlib）、`defusedxml.minidom`（**基础依赖**）、`HtmlConverter`。无需任何额外 pip 包。
3. **MSG 依赖 `olefile`**。`_outlook_msg_converter.py` 惰性导入 `olefile`；`olefile` 在 `outlook` 与 `all` extra 中；但 **`md-desk.spec` 的 hiddenimports 未包含 olefile** → EXE 内 MSG 会抛 `MissingDependencyException`（真实打包缺口）。
4. **ZIP** 仅用 `zipfile`（stdlib），递归调用 `convert_stream`。已支持。
5. **TXT/MD/JSON/JSONL** 由 `PlainTextConverter` 处理（依赖 `charset_normalizer`，基础依赖）。注意：JSON/JSONL 为**纯文本透传**，并非结构化解析。
6. **XML 无专用 converter**，分两条路径：
   - RSS/Atom **feed**（`.xml/.rss/.atom`）由 `RssConverter` 处理（`defusedxml`+`bs4`，基础依赖），仅在检测到 feed 结构时命中；
   - 其它 XML 由 `PlainTextConverter` 借 **Magika 文本检测**（`text/xml`）兜底透传。`.xml` 扩展名**不在** PlainText 的显式 `ACCEPTED_FILE_EXTENSIONS` 中，`application/xml` 也不在其显式 MIME 前缀中 → XML 支持是**机会性**的，非显式保证。
7. **Audio**：`_audio_converter.py` + `_transcribe_audio.py` 惰性导入 `pydub` + `speech_recognition`，转写调用 `recognizer.recognize_google(audio)` → **Google Speech Recognition 联网**。`pydub` 对 `mp3/mp4/m4a` 需要外部 **FFmpeg 二进制**（非 pip 包、不在任何 extra）；`wav/aiff/flac` 不需要 ffmpeg，但仍需 Google SR 联网。缺包时抛 `MissingDependencyException`。
8. **URL 类 converter 全部基础依赖即可**：`HtmlConverter`(bs4/markdownify)、`RssConverter`(defusedxml/bs4)、`WikipediaConverter`(bs4)、`BingSerpConverter`(bs4)、`YouTubeConverter`(bs4，**仅字幕**部分惰性导入 `youtube_transcript_api`)。→ **Stage 2 完成后这些能力零新依赖自动解锁**，仅 YouTube 字幕需 `youtube_transcript_api`。
9. **`convert_uri` 安全现状（直接读取 `_markitdown.py`）**：
   - `file:` scheme → `convert_local` → **允许通过 URL 输入读取任意本地文件**（SSRF/任意文件读取风险），新设计必须**禁止**。
   - `data:` scheme → 内联 data URI 转换；新设计限定仅 http/https → 亦禁止。
   - http(s)：`self._requests_session.get(uri, stream=True)` —— **无 connect/read 超时**、**无最大下载体积**、**默认跟随重定向且不对每一跳重新校验**、**无 SSRF IP/主机拦截**（localhost、127.0.0.0/8、::1、RFC1918、link-local、元数据 169.254.169.254、IPv6 ULA 均可达）、**未缓解 DNS rebinding**（requests 每次连接重新解析）。旧计划“拒绝私有地址”的客户端正则检查**既未实现也不充分**。
   - `convert_response` 内部用 `iter_content` 全量读入 `BytesIO` 且无体积上限；**新设计不使用 `convert_response`**，改由 `UrlFetchService` 自行限流后把 `BytesIO`+`StreamInfo` 交给 `convert_stream`（见 6.1，Fix 3）。

---

## 3. Full Capability Matrix（完整能力矩阵）

判定列：Engine=上游 0.1.7 是否支持；GUI=当前 MdDesk 是否暴露；Package=EXE 打包依赖是否齐；EXE=是否已验证可跑；Action；Gap 类别。
Gap 类别取值：**Engine / GUI / Packaging / Configuration / External**。

| # | 格式/能力 | Engine | GUI | Package | EXE | Action | Gap |
|---|---|---|---|---|---|---|---|
| 1 | PDF | ✅ | ✅ | ✅ | ✅ 已发布 | 无 | — |
| 2 | DOCX | ✅ mammoth | ✅ | ✅ | ✅ | 无 | — |
| 3 | XLSX | ✅ pandas/openpyxl | ✅ | ✅ | ✅ | 无 | — |
| 4 | XLS | ✅ xlrd | ✅ | ✅ | ✅ | 无 | — |
| 5 | PPTX | ✅ python-pptx | ✅ | ✅ | ✅ | 无 | — |
| 6 | HTML（本地文件） | ✅ | ✅ | ✅ | ✅ | 无 | — |
| 7 | CSV | ✅ `_csv_converter` | ✅ | ✅ | ✅ | 无 | — |
| 8 | TXT / MD | ✅ PlainText | ✅ | ✅ | ✅ | 无 | — |
| 9 | JSON / JSONL | ✅ PlainText 透传（非结构化） | ✅ | ✅ | ✅ | 无（注：raw text） | — |
| 10 | XML（通用） | ⚠️ 机会性（RssConverter feed / PlainText+Magika） | ✅ `*.*` | ✅ defusedxml 已打包 | ⚠️ 未验证 | Stage 1 零代码验证；可选把 `.xml` 显式纳入检测 | GUI/EXE 验证（轻微） |
| 11 | ZIP 递归展开 | ✅ zipfile | ✅ | ✅ | ✅ | 无（输出组织可打磨） | — |
| 12 | IPYNB | ✅ | ✅ | ✅ | ✅ | 无 | — |
| 13 | 图片 EXIF 元数据 | ✅ Pillow（exiftool 可选） | ✅ | ✅ PIL | ✅ | 无 | — |
| 14 | **EPUB** | ✅ zipfile+defusedxml+HtmlConverter（基础依赖） | ✅ `*.*` | ✅ defusedxml 已打包 | ⚠️ 未验证 | **Stage 1 仅 smoke test，不改依赖** | EXE 验证-only |
| 15 | **Outlook MSG** | ✅ olefile | ✅ `*.*` | ❌ olefile 不在 hiddenimports/venv | ⚠️ 高概率失败（Evidence before Patch；源码环境已证 FAIL，EXE 待实测） | Stage 1A 实测 → 仅 FAIL 才进 Stage 1B 补 `markitdown[outlook]` | **Packaging** + Configuration |
| 16 | 音频 元数据 EXIF | ✅（exiftool 可选，否则仅元数据） | ✅ | ⚠️ exiftool 二进制未捆绑 | ⚠️ 未验证 | Stage 5 | External(binary，轻微) |
| 17 | **音频 语音转录** | ✅ pydub+SpeechRecognition+Google SR+FFmpeg(mp3/mp4) | ❌ | ❌ pydub/SR 未打包；FFmpeg 外部 | ❌ 未打包 | Stage 5（SHOULD，独立设计） | **Packaging + External(binary) + External(Google SR) + Configuration** |
| 18 | **YouTube 元数据** | ✅ bs4（URL 自动） | ❌ 无 URL 输入 | ✅ 基础依赖 | n/a | **Stage 2 自动解锁（零依赖）** | GUI（URL 入口）only |
| 19 | YouTube 字幕转录 | ✅ youtube_transcript_api（可选） | ❌ | ❌ 未打包 | n/a | Stage 3（SHOULD，可选） | Packaging + GUI + External(network) |
| 20 | RSS / Atom | ✅ defusedxml+bs4（URL 自动） | ❌ 无 URL | ✅ | n/a | Stage 2 自动解锁 | GUI only |
| 21 | Wikipedia | ✅ bs4（URL 自动） | ❌ 无 URL | ✅ | n/a | Stage 2 自动解锁 | GUI only |
| 22 | Bing SERP | ✅ bs4（URL 自动） | ❌ 无 URL | ✅ | n/a | Stage 2 自动解锁 | GUI only |
| 23 | **普通网页（远程）** | ✅ HtmlConverter | ❌ 无 URL | ✅ | n/a | Stage 2 | GUI + **Security** |
| 24 | **远程文件**（URL→pdf/docx…） | ✅ via convert_stream（Stage 2 UrlFetchService 安全 fetch） | ❌ 无 URL | ✅ | n/a | Stage 2 | GUI + **Security** |
| 25 | 图片 LLM 描述 | ✅ openai+llm_client | ❌ | ❌ openai 未打包 | n/a | v0.3+ | Packaging + Configuration + External(OpenAI) |
| 26 | Azure Document Intelligence | ✅ endpoint+key | ❌ | ❌ azure-* 未打包 | n/a | v0.3+ | Packaging + Configuration + External(Azure) |
| 27 | Azure Content Understanding | ✅ endpoint+key | ❌ | ❌ azure-* 未打包 | n/a | v0.3+ | Packaging + Configuration + External(Azure) |
| 28 | 插件系统 enable_plugins | ✅ | ❌ | n/a | n/a | v0.3+（安全） | Configuration + Security |
| 29 | markitdown-ocr 插件 | 独立包 | — | — | — | v0.3+ | External |
| 30 | MCP 服务器 | 独立服务 | — | — | — | v0.3+ | External |
| 31 | stream_info 覆盖（扩展名/MIME/charset） | ✅ API 存在 | ❌ GUI | n/a | n/a | Stage 4（高级） | GUI / Configuration |
| 32 | data: URI | ✅（convert_uri） | ❌ | n/a | n/a | **新设计禁用**（仅 http/https） | Security（收敛） |

> 结论：**Engine Gap 为零**——0.1.7 覆盖所有核心格式，无需 fork 任何 converter。所有真实缺口都在 GUI / Packaging / Configuration / External 四类。

---

## 4. Corrected Gap Analysis（纠正后的缺口分析）

原则：**先证明 Gap 存在，再实施**。不因计划里写了某 Gap 就默认其存在；EPUB 等须经 EXE smoke test 实证。

### 4.1 真实缺口（已按源码/打包基线证实）
- **Packaging Gap — MSG（高概率，须实测确认，不得提前判定“必失败”）**：`olefile` 不在 `md-desk.spec` hiddenimports，且打包 venv pip freeze **未包含** `olefile`（Stage 0 已核实）。但 `hiddenimports` 缺失不能单独证明 EXE 产物一定不含它（PyInstaller 可能经 import 分析收集）。须按序验证，仅实际 FAIL 后才进 Stage 1B（**Evidence before Patch**）：
  (1) packaging venv 是否装 `olefile` → **否**（pip freeze 无）；
  (2) 当前源码环境能否转 `.msg` → **否**（Stage 1A 实测：`MissingDependencyException`，因 olefile 缺失）；
  (3) 当前已发布 EXE 能否转 `.msg` → **NOT TESTABLE**（EXE 无 CLI，纯模块封于 PYZ 无法按文件夹枚举；须 GUI/CLI 实测）。
  结论：构建环境级已证 FAIL；EXE 级 indirect 证据高度一致（olefile 不在 venv + 不在 hiddenimports），但须经 EXE 运行时实测方可最终定性。
- **GUI Gap — 无 URL 输入**：当前 `converter.py` 只收本地路径。这同时阻塞了 #18–#24 全部远程能力——但它们**零新依赖即可解锁**，属于“GUI 暴露”而非“开发新功能”。
- **Configuration Gap — 版本未钉**：无 `requirements.txt`、无版本锁；`build_exe.sh` 依赖 venv 隐式版本。须 Stage 0 显式 `markitdown==0.1.7`。
- **Configuration Gap — 无设置持久化 / 无 stream_info 入口**：现状零设置对象（无 `settings.py`/`engine_config.py`）。旧计划把它们当“既有”描述是错误的——它们是 v0.2 待建目标。

### 4.2 待验证（须 smoke test，不预设）
- **EXE 验证-only — EPUB**：引擎源码证明无需 ebooklib；`defusedxml` 已在 hiddenimports → 极可能已可用，但**须经 EXE smoke test 后才能确认**。不许提前声称“已支持”。
- **EXE 验证-only — XML 通用**：机会性路径，须 fixtures 验证 `.xml`/非 feed 文件在 EXE 内能转。
- **EXE 验证-only — ZIP/TXT/JSON**：虽为基础能力，仍须 Stage 1 补 fixtures + source tests 固化。

### 4.3 外部依赖缺口（须独立设计，不得轻描淡写）
- **Audio 转录**：`pydub`+`SpeechRecognition`（pip）+ **FFmpeg 外部二进制**（非 pip，clean machine 可能不存在）+ **Google SR 联网**（隐私/在线依赖）。EXE 体积受 SpeechRecognition 与（若捆绑）FFmpeg 显著影响。失败模式：`MissingDependencyException`、FFmpeg `FileNotFound`（mp3 无 ffmpeg）、`sr.RequestError`（网络）、`sr.UnknownValueError`（无语音）、长音频超时/配额。
- **YouTube 字幕**：`youtube_transcript_api` + 联网。
- **Image LLM / Azure**：OpenAI / Azure 资源 + Key + 成本 + 体积。

### 4.4 已证伪的旧判断（详见第 14 节 Corrections）
- “升级 markitdown 到当前发行版” —— 当前即 0.1.7，无更新，改为锁定。
- “EPUB 需打包 ebooklib” —— 错，EPUB 不用 ebooklib。
- “JSON/XML 为结构化完整支持” —— JSON 为透传；XML 为机会性，非显式。
- “Audio 装几个小 Python 包即可” —— 错，涉及 FFmpeg 二进制 + Google 联网 + 体积 + 隐私。
- “URL 仅做 file:/私有地址 客户端校验即可” —— 错，`convert_uri` 无超时/限流/重定向校验/SSRF 拦截，须 `UrlFetchService`。
- Stage 5（YouTube）/LATER（RSS/Wikipedia/Bing）被误拆成独立开发任务 —— 实为 Stage 2 后自动解锁，仅 YouTube 字幕需额外依赖。

---

## 5. v0.2 Scope（建议范围）

### MUST（v0.2 必交付）
1. **建立可复现构建基线（reproducible build baseline）**：锁定 `markitdown==0.1.7`（用官方 extra 语法，非自创分组）；记录 Python / PySide6 / PyInstaller / MdDesk 直接依赖 / 构建环境 resolved 版本（见第 14 节）；`build_exe.sh` 引用锁定文件；**禁止跟踪 `main`**。
2. **完整 capability matrix + 真实 Gap 清单**（本文第 3、4 节），不改功能代码。
3. **Stage 1A 实测 + Stage 1B 修复（仅 FAIL 项）**：EPUB/MSG/ZIP/TXT/JSON/XML 基线探针（PASS/FAIL/CONDITIONAL/NOT TESTABLE）；仅对实测 FAIL 项（如 MSG→`markitdown[outlook]`）做依赖/打包修复；PASS 项只补 fixtures/回归，不改依赖。
4. **Stage 2 安全远程 URL**：`UrlFetchService`（安全 fetch → `convert_stream(...)`，不使用 `convert_response`）+ SSRF/重定向/超时/限流 + 生成正确 StreamInfo；测试正常与恶意 URL。

### SHOULD（v0.2 争取）
5. **Stage 3 URL-native 能力**：验证 YouTube/RSS/Wikipedia/Bing/网页/远程文件——**仅为已自动解锁的能力补 UI/依赖**，不为其“开发”。
6. **Stage 4 高级转换设置**：Engine 配置 / Conversion 选项 / StreamInfo 覆盖（高级）。
7. **Stage 5 Audio（独立）**：Python 依赖 + FFmpeg + 联网语音识别 + 隐私 + 打包 + 失败处理。

### LATER（v0.3+，单独评估 Key/成本/安全/体积）
8. Image LLM、Azure DI、Azure CU、Plugin 系统、OCR 集成、MCP。

---

## 6. Architecture（架构）

保持 `PySide6 GUI → Service/Adapter → Microsoft MarkItDown`，**不 fork/重写 converter**。

### 6.1 引擎调用分层
```
GUI (MainWindow / Worker)
  ├─ 本地文件 ──▶ MarkItDown().convert(local_path)            # 现状，保留
  └─ 远程 URL  ──▶ UrlFetchService.fetch(url)                # 新增，Stage 2
                     ├─ scheme 校验（仅 http/https；拒绝 file:/data:/其它）
                     ├─ DNS 解析 + IP 校验（见 6.2）
                     ├─ 每重定向跳 重新解析+校验（pin IP / 自定义 adapter 防 DNS rebinding）
                     ├─ connect timeout + read timeout
                     ├─ 最大下载体积上限（超限中止）
                     └─ 安全 HTTP Fetch → BytesIO / binary stream
                        + 正确生成的 StreamInfo(url/filename/extension/mimetype/charset)
                          └─▶ MarkItDown().convert_stream(stream, stream_info=StreamInfo(...))   # 交给引擎

  核心原则（Fix 3）：
  - **MdDesk 负责全部网络访问与网络安全**（UrlFetchService 承担 scheme/DNS/IP/redirect/超时/限流/防 rebinding）。
  - **MarkItDown 只负责 Stream → Markdown**（convert_stream 接收二进制流 + StreamInfo，不接触网络）。
  - HTTP 请求发生在 `convert_uri()` 路径（源码 `_markitdown.py:475` 执行 `self._requests_session.get(uri, stream=True)`），而非 `convert_response()` 内部；`convert_response()` 仅接收已获取的 `requests.Response` 并读取流。`MdDesk Stage 2 将不使用 `convert_uri()` 承担网络访问，而采用 `UrlFetchService → BytesIO + StreamInfo → MarkItDown.convert_stream()`（由 UrlFetchService 生成正确的 StreamInfo 后交给 convert_stream）。
```

### 6.2 Settings 重新设计（拆分，不把 stream_info 等同于设置面板）
- **Engine Configuration**（引擎级）：`enable_plugins`、`llm_client`、`llm_model`、`llm_prompt`、`docintel_*`、`cu_*`、其它 engine-level options。
- **Conversion Options**（转换级）：converter kwargs / 转换级选项。
- **Input Detection Override**（高级）：`StreamInfo`（extension / mimetype / charset / filename / url·path metadata）——归入**高级功能**，非普通用户主设置。
- 持久化到 `%APPDATA%/MdDesk/settings.json`；API Key 优先 Windows 凭据管理器（keyring/DPAPI）。现状**无**该模块，属 v0.2 新建目标。

### 6.3 URL-native 自然解锁（Stage 2 后免费）
Stage 2 落地的 `UrlFetchService`（安全 fetch → `convert_stream(...)`）后，下列官方 converter **零新依赖自动可用**（仅基础依赖已打包）：普通网页(HtmlConverter)、RSS(RssConverter)、Wikipedia(WikipediaConverter)、Bing SERP(BingSerpConverter)、YouTube **元数据**(YouTubeConverter)、远程文件(`convert_stream`→按 MIME 路由)。**仅 YouTube 字幕**需 `youtube_transcript_api`（Stage 3 可选）。

---

## 7. Stages（可逐阶段执行）

> 每阶段含 Goal / MUST / DON'T / Tests / Done / Stop。Stop 后即停，不自动进入下一阶段（除非你确认）。

### Stage 0 — Stable Baseline & Capability Audit（MUST）
- **Goal**：建立**可复现构建基线（reproducible build baseline）** + 真实能力/缺口基线，不改功能代码。至少记录/锁定：Python 版本、`markitdown`、`PySide6`、`PyInstaller`、MdDesk 直接依赖、构建环境实际 resolved 依赖版本（见第 14 节）。不本轮为“完美依赖锁”大规模重构构建系统——先建立可重复、可审计的 baseline。
- **MUST**：
  - 新增/落地锁定文件（如 `requirements.txt` 或既有构建方式），**使用 MarkItDown 官方 extras**，不得自创分组语法：基础 `markitdown==0.1.7`；后续按需启用官方 extra，例如 Outlook → `markitdown[outlook]==0.1.7`、音频 → `markitdown[audio-transcription]==0.1.7`、YouTube 字幕 → `markitdown[youtube-transcription]==0.1.7`。`build_exe.sh` 引用之。
  - 落地本文第 3 节 Capability Matrix 与第 4 节 Gap 清单（文档化）。
  - 明确“真实 Gap”仅含 #15(MSG 打包)、#18–#24(GUI URL)、Audio/YouTube/LLM/Azure 外部依赖；标注 EPUB/XML 为“待 EXE 验证”。
- **DON'T**：改功能代码、装依赖（仅写锁定文件文本）、构建 EXE、进 Stage 1A。
- **Done**：可复现构建基线 + 矩阵与 Gap 清单固化（见第 14 节）。
- **Stop**：等确认再进 Stage 1A。

### Stage 1A — Current EXE / Source Baseline Probe（MUST，零功能修改）
- **Goal**：仅验证当前 RC / 当前源码 / 当前 packaging environment 的真实状态，不动任何功能代码。
- **MUST（只读探针）**：对以下格式做实测，输出真实状态：
  - EPUB、MSG、ZIP、TXT、JSON、XML
  - 状态取值：**PASS / FAIL / CONDITIONAL / NOT TESTABLE**
  - 数据源：当前 packaging venv 的 `markitdown==0.1.7`（构建环境）+ 真实样本文件；EXE 运行时若无法 headless 触发则标 NOT TESTABLE。
- **DON'T**：修改任何 `.py`、不改 build script、不改 installer、不安装依赖、不构建 EXE、不进 Stage 1B。
- **Tests**：每个格式记录来源（venv/EXE）、命令、输出片段、判定。
- **Done**：产出真实状态矩阵与证据链（见第 14 节）。
- **Stop**：等确认再进 Stage 1B。

### Stage 1B — Local Gap Fix（仅 Stage 1A 实际 FAIL 的项才进入）
- **原则（Evidence → Gap → Patch → Regression）**：
  - 只有 Stage 1A 实际证明 FAIL 的项目才允许修改。
  - 例：若 MSG FAIL 且确认根因是 `olefile` 缺失 → Stage 1B 才允许启用官方 extra `markitdown[outlook]==0.1.7` 并补 hiddenimports / 重新打包。
  - 例：若 EPUB 当前已 PASS → **不允许为 EPUB 修改任何东西**。
- **MUST（仅对已证 FAIL 项）**：
  - 真实 FAIL 项的依赖/打包修复（如 MSG → `markitdown[outlook]==0.1.7` + hiddenimports + 重打包）。
  - 对 PASS 项补 fixtures + source tests 固化回归（不改动依赖）。
  - 依赖/错误提示：对 `MissingDependencyException` 给出“需安装 X / 配置 Y”的明确信息。
- **DON'T**：URL、Audio、Azure、LLM、Plugin、MCP；不 fork upstream converter；不为已 PASS 项引入任何改动；不新增除已证 FAIL 项所需外的依赖。
- **Tests**：已 FAIL 项修复后在 EXE 内产出非空 markdown；现有 acceptance 仍绿。
- **Done**：真实缺口闭合、本地格式矩阵全绿。
- **Stop**：验证通过并 commit 后停止。

### Stage 2 — Safe Remote URL（MUST）
- **Goal**：GUI 支持 http/https 链接转换，带完整 SSRF 防护。
- **MUST**：
  - `UrlFetchService`：scheme 白名单（仅 http/https，拒绝 file:/data:/其它）；DNS 解析→IP 校验（拒绝 loopback 127.0.0.0/8、::1、RFC1918、link-local、metadata 169.254.169.254、IPv6 ULA/站点本地）；connect+read timeout；最大下载体积；重定向次数上限 + **每跳重新解析+校验**（pin IP 或自定义 adapter 防 DNS rebinding）；明确错误信息。
  - GUI “添加链接”输入框（http/https 校验）。
  - worker 调 `UrlFetchService.fetch` → 得到 `BytesIO` + `StreamInfo` → `MarkItDown().convert_stream(stream, stream_info=...)`（**不用 `convert_response`**）。
- **Tests**：公开 HTML/PDF URL 返回 markdown；拒绝 `file://`/私有/元数据地址；重定向到内网被拦截；断网/超时/超大文件返回明确错误而非崩溃。
- **Done**：安全远程转换在 EXE 内可用。
- **Stop**：验证通过并 commit 后停止。

### Stage 3 — URL-native Features（SHOULD）
- **Goal**：验证并暴露 Stage 2 自动解锁的远程能力。
- **MUST（仅验证/补 UI/补依赖）**：
  - 验证 YouTube/RSS/Wikipedia/Bing/网页/远程文件经 Stage 2 入口可转（零新依赖）。
  - 仅当要 YouTube 字幕时，启用 `[youtube-transcription]` 并打包 `youtube_transcript_api`。
- **DON'T**：把这些能力误当成“需开发”的独立模块；不为它们写新 converter。
- **Tests**：各 URL 类型样例返回合理 markdown；字幕（若启用）返回文本。
- **Done**：URL-native 能力可用且经测试。
- **Stop**：验证通过并 commit 后停止。

### Stage 4 — Advanced Conversion Settings（SHOULD）
- **Goal**：暴露 Engine 配置 / Conversion 选项 / StreamInfo 覆盖（高级）。
- **MUST**：`settings.py` + `engine_config.py` 落地（第 6.2 节拆分）；StreamInfo 覆盖作为高级面板；普通 UI 保持简洁。
- **Tests**：扩展名错标的 `.csv`（实为 txt）经覆盖正确转换；设置存取往返一致。
- **Done**：高级用户可纠正误判格式/编码。
- **Stop**：验证通过并 commit 后停止。

### Stage 5 — Audio（SHOULD，独立）
- **Goal**：音频转写，**独立处理全部外部约束**。
- **MUST（独立设计）**：
  - Python 依赖：`pydub`+`SpeechRecognition`（经 `requirements.txt` + hiddenimports）。
  - **FFmpeg**：决策“捆绑二进制”还是“依赖系统 FFmpeg 并给出缺失提示”；明确 wav/aiff/flac 不需 ffmpeg，mp3/mp4/m4a 需要。
  - **联网语音识别**：明确默认 Google SR 的隐私影响与离线不可用；给出离线/失败时的明确提示与降级。
  - **打包/体积**：评估 SpeechRecognition 与（若捆绑）FFmpeg 对 EXE 体积影响。
  - **失败处理**：`MissingDependencyException`、FFmpeg 缺失、`RequestError`、`UnknownValueError`、长音频超时。
- **DON'T**：简化为“装几个小包即可”。
- **Tests**：样例音频（wav 与 mp3 分别）产出转录或明确错误；断网/缺 ffmpeg 时不崩溃且提示清晰。
- **Done**：Audio 在 EXE 内可用且边界清晰。
- **Stop**：验证通过并 commit 后停止。

---

## 8. v0.3+ Backlog（LATER）
- Image LLM 描述（openai + Key + 成本）
- Azure Document Intelligence（资源 + Key + 体积 + 成本）
- Azure Content Understanding
- 插件系统启用 + 发现（任意代码执行风险，需显式授权 + 警告）
- markitdown-ocr 插件对接（独立包）
- MCP 服务器（独立服务，非库 API）
- exiftool 二进制捆绑、style_map / llm_prompt UI

---

## 9. Packaging Impact（打包影响，已纠正）

| 维度 | 影响（纠正后） |
|---|---|
| **版本钉死** | 当前无锁；须 `requirements.txt` 写 `markitdown==0.1.7`（Stage 0）。 |
| **EXE 体积** | EPUB **不增体积**（无需 ebooklib，基础依赖已打包）。MSG 仅 +`olefile`（~0.1MB）。Audio 显著：SpeechRecognition（数 MB）+ 若捆绑 FFmpeg（数十 MB）。LATER 的 openai/azure 明显增大——建议 LATER 评估“是否仍打进同一 EXE”。 |
| **hidden imports / extras** | 通过官方 extra 引入：Outlook 用 `markitdown[outlook]==0.1.7`（含 `olefile`，Stage 1B）、音频用 `markitdown[audio-transcription]==0.1.7`（含 `pydub`/`SpeechRecognition`，Stage 5）、YouTube 字幕用 `markitdown[youtube-transcription]==0.1.7`（Stage 3 可选）；**删除旧计划中错误的 `ebooklib`**。 |
| **可选依赖** | 保持“按需装”；MUST/SHOULD 中除 Audio/YouTube 外无需 Key/网络服务。 |
| **启动速度** | 新增纯 Python 小依赖影响可忽略；Audio/Azure/LLM 惰性导入，不拖慢默认启动。 |
| **clean-machine** | 仍一目录 zip，拷贝即跑；FFmpeg 若未捆绑则需在缺包时明确提示用户安装。 |

---

## 10. Security Model（安全模型，Stage 2 必须体现）

- **Scheme 白名单**：仅 `http`/`https`；显式拒绝 `file:`（防任意本地文件读取）、`data:`、及其它 scheme。
- **主机/IP 边界**（解析后校验，拒绝）：
  - loopback：`127.0.0.0/8`、`::1`
  - RFC1918 私网：`10.0.0.0/8`、`172.16.0.0/12`、`192.168.0.0/16`
  - link-local：`169.254.0.0/16`（含云元数据 `169.254.169.254`）、IPv6 `fe80::/10`
  - IPv6 私网/站点本地：`fc00::/7`(ULA) 等
  - localhost 主机名解析结果同样落入上述范围 → 拒绝
- **重定向防护**：重定向次数上限；**每一跳重新解析域名并重新执行上述 IP 校验**；用 pin-IP / 自定义 HTTP adapter 防止 DNS rebinding（避免“校验时安全、连接时被解析到内网”）。
- **超时**：connect timeout（如 10s）+ read timeout（如 30s）；避免 worker 线程挂死。
- **体积上限**：最大下载字节数（如 50MB）；超限立即中止并提示。
- **错误信息**：区分“scheme 不允许 / 主机被拦截 / 重定向到受限地址 / 超时 / 体积超限 / 网络错误”，对用户明确且不泄露内网拓扑。
- **线程隔离**：网络获取在 worker 线程；结果不自动打开。

---

## 11. Risk Register（风险登记表）

| 风险 | 类别 | 缓解 |
|---|---|---|
| API Key 安全（LLM/Azure） | External/Config | 存 Windows 凭据管理器；禁写日志；UI 明示“不会上传第三方”。 |
| 网络资源（超时/大文件/离线） | External | URL 入口仅 http/https + 超时 + 体积上限 + 友好错误；离线降级。 |
| **SSRF / 任意文件读取** | Security | 禁止 `file:`；IP/主机边界 + 每跳重定向校验 + DNS rebinding 防护（Stage 2）。 |
| Audio 隐私/在线依赖 | External/Security | 明示默认 Google SR 联网；离线不可用；失败明确提示。 |
| Audio 打包体积（FFmpeg） | Packaging | 评估捆绑 vs 系统依赖；缺包明确提示。 |
| 插件执行安全 | Security | 仅用户显式勾选；启动列插件并警告“将执行第三方代码”；默认关闭。 |
| 打包兼容性 | Packaging | 每阶段独立验证 `build_exe.sh` + `verify_dist_zip.py`。 |
| 上游 API 变化 | Configuration | 锁 `markitdown==0.1.7`；按特性探测而非硬编码版本。 |

---

## 12. Tests / Acceptance Criteria（测试与验收）

### 12.1 规划阶段已证明（本轮只读审计）
- markitdown 稳定版本判断有依据：PyPI 0.1.7、本地源码 0.1.7、main 无新增。
- EPUB 依赖判断来自实际源码：`_epub_converter.py` 仅 zipfile+defusedxml+HtmlConverter，无 ebooklib。
- MSG 依赖有依据：`_outlook_msg_converter.py` 导入 olefile；spec 缺失 → 真实打包缺口。
- URL 调用路径已检查：直接读取 `_markitdown.py` 的 `convert`/`convert_uri`/`convert_response`/`_convert`。
- redirect / SSRF 风险已进入架构（第 6.1、10 节）。
- Audio 外部依赖已确认：pydub、SpeechRecognition、FFmpeg（二进制）、Google SR 联网。
- ZIP/TXT/JSON/XML 已有能力已重新审计（第 3 节矩阵）。
- 所有 Gap 已区分：Engine / GUI / Packaging / Configuration / External（第 4 节）。

### 12.2 各 Stage 验收（仅 Stage 0/1 在 v0.2 前期；URL/Audio 后续）
- **Stage 0**：建立可复现构建基线——记录 Python / markitdown / PySide6 / PyInstaller / MdDesk 直接依赖 / 构建环境 resolved 版本（见第 14 节）；矩阵与 Gap 清单定稿；无功能代码改动。
- **Stage 1A**：产出真实状态矩阵（PASS/FAIL/CONDITIONAL/NOT TESTABLE）+ 证据链；零功能修改（见第 14 节）。
- **Stage 1B**：仅对 1A 实测 FAIL 项修复（如 MSG→`markitdown[outlook]==0.1.7` + hiddenimports + 重打包），修复后在 EXE 内产出非空 markdown；现有 acceptance 仍绿；`MissingDependencyException` 有明确提示。
- **Stage 2**：正常 URL 成功；`file://`/私网/元数据/重定向到内网均被拦截；超时/超大/断网返回明确错误。
- **Stage 3**：YouTube/RSS/Wikipedia/Bing/网页/远程文件经 URL 入口可用；字幕（若启用）可用。
- **Stage 4**：StreamInfo 覆盖生效；设置存取一致；普通 UI 保持简洁。
- **Stage 5**：wav 与 mp3 样例产出转录或明确错误；缺 ffmpeg/断网不崩溃且提示清晰。

---

## 13. Stop Conditions（停止条件）

- 所有“真实 Gap”须先经源码/EXE 实证，不得因计划写了就默认存在。
- 不 fork Microsoft converter；不把 `main` 当生产依赖；不新增未经上游源码验证的依赖。
- 不删除当前 MdDesk 已有能力。
- 每阶段 Stop 后等确认再进下一阶段；**不自动进入 Stage 1B**（Stage 1A 仅探针，不修复）。

---

## 14. Execution Record — Stage 0 & Stage 1A（2026-08-16，零功能修改）

> 本轮仅执行 Stage 0（可复现构建基线）与 Stage 1A（当前环境基线探针）。**未修改任何 .py、未装依赖、未构建 EXE、未进入 Stage 1B。**

### 14.1 Stage 0 — Reproducible Build Baseline（构建环境 resolved 版本）

| 组件 | 版本（构建环境 `D:\WB\markitdown_packaging_venv`，Python 3.13.14） | 备注 |
|---|---|---|
| Python | 3.13.14 | venv 解释器 |
| markitdown | **0.1.7** | pip（构建用） |
| PySide6 | 6.11.1（`PySide6_Essentials` + `shiboken6`） | pip |
| PyInstaller | 6.22.1（+ `pyinstaller-hooks-contrib` 2026.6） | pip |
| MdDesk 直接依赖 | PySide6、markitdown | 源码 imports |
| 文档格式依赖 | mammoth 1.12.1、pdfminer.six 20260107、pdfplumber 0.11.10、pypdfium2 5.13.0、python-pptx 1.0.2、pandas 3.0.5、openpyxl 3.1.5、xlrd 2.0.2、lxml 6.1.1、pillow 12.3.0 | pip freeze |
| 引擎基础依赖 | beautifulsoup4 4.15.0、requests 2.34.2、markdownify 1.2.3、magika 0.6.3、charset-normalizer 3.5.1、defusedxml 0.7.1、numpy 2.5.2 | pip freeze |
| **缺失（尚未装）** | `olefile`、`pydub`、`SpeechRecognition`、`youtube_transcript_api`、`openai`、`azure-*` | pip freeze 未出现 |

- 完整 `pip freeze`（构建环境 resolved 版本）已捕获；本轮**仅记录，不重构构建系统**。锁定策略：基础 `markitdown==0.1.7`，后续能力按需启用官方 extra（见 §5/§9）。
- 注意：PyInstaller 将纯 Python 模块封入 `PYZ-00.pyz`，**不能**靠 `_internal/` 文件夹枚举判断某包是否被打包；EXE 运行时能力须经实际运行确认（见 14.2）。

### 14.2 Stage 1A — Current Environment Baseline Probe（真实结果）

方法：用构建环境 venv 的 `markitdown==0.1.7` 对真实样本（`markitdown/packages/markitdown/tests/test_files/`）做本地路径转换；EXE 运行时因无 CLI 无法 headless 触发，标 NOT TESTABLE。

| 格式 | 样本 | 来源环境 | 结果 | 判定 | 证据/说明 |
|---|---|---|---|---|---|
| EPUB | test.epub | venv markitdown 0.1.7 | **PASS**（len 485，含标题/作者/目录） | PASS | 无需 ebooklib；引擎 + defusedxml 已支持 |
| MSG | test_outlook_msg.msg | venv markitdown 0.1.7 | **FAIL** | FAIL | `MissingDependencyException`：`olefile` 未装（pip freeze 无） |
| ZIP | test_files.zip | venv markitdown 0.1.7 | **PASS**（len 281059，递归展开） | PASS | zipfile 标准库 |
| JSON | test.json | venv markitdown 0.1.7 | **PASS**（len 229，raw text 透传） | PASS | PlainTextConverter |
| XML（RSS feed） | test_rss.xml | venv markitdown 0.1.7 | **PASS**（len 7956） | PASS | RssConverter |
| TXT | 合成样本 | venv markitdown 0.1.7 | **PASS** | PASS | PlainTextConverter |
| XML（通用, application/xml） | 合成样本 | venv markitdown 0.1.7 | **PASS**（经 Magika text/xml 兜底） | PASS | 机会性路径证实可用 |
| XML（通用, ext-only） | 合成样本 | venv markitdown 0.1.7 | **PASS** | PASS | 机会性路径证实可用 |
| EPUB（EXE 运行时） | — | 已发布 EXE | NOT TESTABLE | NOT TESTABLE | EXE 无 CLI；纯模块在 PYZ 内，无法按文件夹枚举 |
| MSG（EXE 运行时） | — | 已发布 EXE | NOT TESTABLE | NOT TESTABLE | 同上；indirect 证据（olefile 不在 venv + 不在 hiddenimports）高度一致，但须经 EXE 运行实测最终定性 |

### 14.3 修正后的真实 Gap 清单（Evidence before Patch）

- **MSG（Packaging，已证 FAIL @ 环境级）**：venv 无 `olefile` + 源码环境转换抛 `MissingDependencyException`。→ Stage 1A 已证 FAIL；**进入 Stage 1B 的条件已满足**，但本轮停在 1A，未修复。EXE 级待实测。
- **EPUB（无 Gap）**：环境级 PASS，无需任何依赖变更；EXE 运行时待 smoke test，但引擎层已证实无 ebooklib 需求。
- **ZIP / TXT / JSON / XML（无 Gap，待固化回归）**：环境级全 PASS；Stage 1B 仅补 fixtures/source tests 固化，不改依赖。
- **GUI — 无 URL 输入**：阻塞 #18–#24 远程能力（零新依赖即可解锁），属 GUI 暴露。
- **Configuration — 版本/构建未钉**：Stage 0 已记录 resolved 版本，待落地 `requirements` 锁定（用官方 extra 语法）。
- **External（Audio / YouTube 字幕 / Image LLM / Azure）**：待 Stage 3/5/v0.3+，独立设计。
- **Engine Gap：零。**

### 14.4 停止声明

- 已完成：Stage 0（可复现构建基线）+ Stage 1A（当前环境基线探针，真实结果如上）。
- 未做：任何功能代码修改、依赖安装、EXE 构建、Stage 1B 修复。
- 下一步：待你确认后，仅对 Stage 1A 已证 FAIL 的项（MSG）进入 Stage 1B。

---

## 15. Known Limitations（已知限制，Stage 4 记录）

> 以下两条限制属上游行为或架构边界，**不修改 MarkItDown / 不修改 YouTube 实现**，仅作记录。

1. **YouTube 字幕网络请求不经过 `UrlFetchService`**：Stage 3 启用 `markitdown[youtube-transcription]` 后，字幕抓取由 `youtube-transcript-api` 自身直接发起网络请求（绕过 MdDesk 的 `UrlFetchService`）。因此其请求**不受 Stage 2 的 SSRF / 重定向 / 超时 / 限流保护**约束。普通网页/远程文件仍走 `UrlFetchService`（受保护）；仅 YouTube 字幕这一条链路例外。如未来需要为字幕请求也加防护，须另行 patch 或在 `youtube-transcript-api` 外层代理，不在 v0.2 范围内。

2. **不可用 YouTube 的降级行为遵循上游 MarkItDown**：当视频无字幕 / 不可用 / 被区域封锁时，MarkItDown 的 `YouTubeConverter` 回退到仅抓取元数据（标题/描述等）还是抛错，由上游实现决定，**MdDesk 不保证“仅返回元数据”这一特定降级形态**。v0.2 仅依赖上游行为，不对此做定制；如需要确定性降级（始终返回元数据而非失败），须未来在 MdDesk 适配层显式捕获并 fallback，不在 v0.2 范围内。

---

*本计划为审计 + 规划 + Stage 0/1A 执行记录产物；未改动任何功能源码、未安装依赖、未构建 EXE、未进入 Stage 1B。等待审核。*
