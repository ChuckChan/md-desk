# MdDesk

> A desktop tool that converts documents to Markdown, built on Microsoft MarkItDown (unofficial, not affiliated).

![Version](https://img.shields.io/github/v/release/ChuckChan/md-desk?label=version&color=blue) ![License](https://img.shields.io/github/license/ChuckChan/md-desk?color=green) ![Platform](https://img.shields.io/badge/platform-Windows%20x64-0078D4)

[简体中文](README.zh-CN.md)

MdDesk is a Windows desktop GUI that batch-converts many document types (PDF / Word / Excel / PowerPoint / HTML / plain text / CSV / Outlook `.msg` / safe remote URLs / audio, etc.) into Markdown. The conversion engine is [Microsoft MarkItDown](https://github.com/microsoft/markitdown); MdDesk is only its graphical wrapper and is not affiliated with Microsoft.

## Download & Run

- Go to **[Releases](https://github.com/ChuckChan/md-desk/releases/latest)** and download `MdDesk-0.6.0-Windows-x64.zip`
- Extract the ZIP and copy the **entire folder** to the target machine
- Double-click `md-desk.exe` to launch

> ⚠️ Do not copy `md-desk.exe` alone — keep the sibling `_internal/` directory (it contains the Python runtime, Qt libraries, and the conversion engine).

## Key Features

- Drag-and-drop / add files; batch import of many formats
- One-click batch conversion to Markdown
- Markdown source view + rendered preview on the right (native Qt rendering)
- Copy Markdown, export `.md` (UTF-8)
- Corrupt / unsupported files are flagged as ERROR / UNSUPPORTED instead of crashing
- **AI-enhanced conversion (added in v0.3, optional)**:
  - **LLM image description**: when converting image files (PNG/JPG, etc.), calls a "Vision-capable OpenAI-compatible API" to generate a caption, embedded in the Markdown.
  - **Image / scanned-page OCR**: for images and scanned pages inside PDF, Word, PPT, and Excel, calls the same Vision API to OCR the text, embedded as a `*[Image OCR] ... [End OCR]*` block.
  - AI is **off by default**. Once enabled, set endpoint / model in **Advanced Settings**; the API key is stored in the **Windows Credential Manager** — never written as plaintext, no Fernet fallback.
- **Diagnostics panel (new in v0.4.0)**: a "Diagnostics" tab shows each file's conversion report (source, status, duration, output size) and, when quality inspection is on, quality warnings and error details. It never renders the Markdown body and has buttons to open the diagnostic log.
- **Conversion quality check (new in v0.4.0, opt-in, off by default)**: when enabled in **Advanced Settings**, successful conversions run a lightweight static check (empty / abnormally short output, low text yield, garbled text, OCR-failure markers) and surface advisory warnings. It never changes the conversion result or status.
- **Batch productivity (new in v0.5.0)**: import whole folders (recursive scan, dedup), convert only the selected files, retry only the failed (ERROR / UNSUPPORTED) items, export all successful results to a chosen directory (safe naming, never overwrites source files), cooperative cancel (the current file finishes, the rest stay pending), and a batch summary (total / success / quality hints / failed / not-executed / duration) shown when a batch ends.
- **AI provider unification (new in v0.6.0)**: a single, secure AI configuration path — bring your own OpenAI-compatible endpoint, test the connection in-app, toggle OCR and image description independently, and fail-safe isolation (AI errors never break a conversion; you get the Markdown plus an advisory warning). API keys are stored only in the Windows Credential Manager, never in plaintext.

## Requirements / Prerequisites

- **Windows x64 only.**
- **AI / OCR requires your own "Vision-capable OpenAI-compatible API"** (endpoint + key). MdDesk ships no API key and no model. This release's automated tests cover wiring + an offline dummy client only; **real-provider auth / quota end-to-end testing was not performed** (non-blocking, recorded in RELEASE.md).
- **Audio transcription** uses Google online Speech Recognition (needs internet); MP3/M4A/MP4 need a system **FFmpeg** (not bundled — a friendly message is shown if missing, not a crash).
- **YouTube** subtitle fetching does not go through MdDesk's safe URL layer (follows upstream markitdown).

## Known Limitations

- The preview pane uses native Qt Markdown rendering: GFM tables, task lists, and similar extensions are shown as raw text (the copied / exported Markdown source is standard and unaffected).
- **No code signing.** On first run Windows SmartScreen / antivirus may block it (right-click → Properties → "Unblock", or add to allowlist; non-blocking).
- **OCR failure has a stable marker**: when the OCR API call fails, the result contains a `*[OCR Error] ... [End OCR Error]*` block (never disguised as a successful `*[Image OCR]` block). When **转换质量检查 (quality check)** is enabled, the **Diagnostics** tab surfaces this (and other quality warnings) proactively; by default quality check is off, so no warning is shown unless you opt in.
- The `vendor/markitdown-ocr` plugin is **based on Microsoft's official `markitdown-ocr` plugin** and includes MdDesk's "OCR error-block" patch. **Upgrading the upstream plugin later requires a fresh compatibility audit** (marker format, `register_converters` registration, and the 4 converters' priorities may change).
- v0.2 already included: Outlook `.msg`, safe remote http/https URLs, YouTube subtitles, audio transcription, and Advanced Settings. v0.3 adds the AI enhancements above.

## Development

```bash
pip install pyside6 markitdown   # run from source
python main.py                    # launch GUI (needs PySide6 + markitdown)
bash build_exe.sh                 # build the exe using the standalone packaging venv (see build_exe.sh comments)
python make_dist_zip.py           # generate the distribution ZIP
python verify_dist_zip.py         # verify ZIP (extract / structure / offscreen boot / SHA-256)
```

Tests (need the packaging venv + PySide6 available):

```bash
pip install pytest
pytest tests/ -q                    # 168 pytest cases, all pass
python tests/test_file_model.py     # Stage 2 file model, 12 checks (script mode)
python tests/test_audio_stage5.py   # audio / regression, 13 checks (script mode)
```

## License

[MIT](LICENSE) — based on Microsoft MarkItDown (also MIT). Unofficial wrapper, not affiliated with Microsoft.
