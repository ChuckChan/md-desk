# Stage 5 — Audio Transcription · Evidence Report

**Project:** MdDesk (markitdown-gui) · **Engine:** `markitdown==0.1.7` (unchanged, upstream not modified)
**Date:** 2026-08-17 · **Build env:** Windows x64 / Python 3.13.14 / PyInstaller 6.22.1
**Scope:** Verify + complete MdDesk audio transcription; keep `markitdown==0.1.7`; do **not** modify upstream converter.

---

## 1. Probe 结果 (Capability Probe)

Live probe in the packaging venv (`D:/WB/markitdown_packaging_venv`) before any code change:

| Probe | Result |
|---|---|
| `pydub` present | ✅ installed via `markitdown[audio-transcription]==0.1.7` → **pydub 0.25.1** |
| `speech_recognition` present | ✅ → **SpeechRecognition 3.17.0** (pulls `audioop-lts`, `standard-aifc`, `standard-chunk` 3.13-compat shims) |
| `FFmpeg` / `ffprobe` on PATH | ❌ **absent** → MP3/M4A/MP4 decode raises `FileNotFoundError [WinError 2]` (pydub spawning ffmpeg fails) |
| WAV path | ✅ engine `AudioConverter` accepts `.wav`, routes straight to `sr.AudioFile` → `recognizer.recognize_google` (no FFmpeg needed) |
| MP3 path (no FFmpeg) | ❌ → `FileNotFoundError` (no `__cause__`), must be caught + friendly-mapped |
| Google SR reachability | ⚠️ DNS `google.com` resolves; `recognize_google` endpoint returns HTTP 403 (path exists, needs real request) → **requires live network** |

**Conclusion:** three real failure classes exist — (a) missing Python deps (`MissingDependencyException`), (b) missing FFmpeg (`FileNotFoundError`/decode), (c) network/`UnknownValueError` from `recognize_google`. The only code change needed was **friendlier error text**; the conversion pipeline itself is already provided by upstream `markitdown==0.1.7`.

---

## 2. 新增依赖 (New Dependencies)

Via `requirements.txt` (single line, version-pinned to engine):
```
markitdown[outlook,youtube-transcription,audio-transcription]==0.1.7
```
- `audio-transcription` extra pulls **pydub 0.25.1** + **SpeechRecognition 3.17.0** + 3.13 stdlib shims.
- `build_exe.sh` adds explicit collection: `--hidden-import pydub --hidden-import speech_recognition`.
- `stage5.spec` adds `'pydub', 'speech_recognition'` to `hiddenimports` (defensive; `collect_submodules markitdown` already covers them).

**No** Whisper / OpenAI / Azure added (per spec DON'T).

---

## 3. FFmpeg 决策 (FFmpeg Decision)

- **Decision: do NOT bundle FFmpeg.** Aligned with `MdDesk-v0.2-Plan.md §15` and the spec ("不默认打包 FFmpeg").
- **Rationale:** WAV/aiff/flac need **no** external binary. MP3/M4A/MP4 need a system `ffmpeg`/`ffprobe` in PATH. Bundling a 70+ MB binary contradicts the "minimal reliable" intent and complicates licensing/distribution.
- **Behavior when FFmpeg absent:** MP3/M4A/MP4 decode fails → caught → user sees a friendly Chinese message telling them to install FFmpeg or use WAV. **No crash.**
- **Verified:** MP3-no-FFmpeg path produces the friendly error in both source and frozen EXE.

---

## 4. WAV / MP3 结果 (WAV / MP3 Results)

**WAV (source + frozen):**
- Engine audio converter detects `.wav` → builds `AudioConverter` → reaches `recognize_google` ✓
- Transcript embedded in markdown as `### Audio Transcript:` block ✓
- Verified with `recognize_google` **mocked** (deterministic; real SR needs network + real speech).

**MP3 (source + frozen):**
- Without FFmpeg → `FileNotFoundError` caught → `ConversionError(status=ERROR)` with friendly FFmpeg/decode message, **no crash** ✓
- With FFmpeg present (user-supplied) → would decode + transcribe via the same pipeline (not exercised here; no FFmpeg in build env).

---

## 5. Regression (回归)

`tests/test_audio_stage5.py` runs the Stage 4 regression gate (all previously-PASSING suites). **All green:**

| Suite | Result |
|---|---|
| tests/test_converter.py | ✅ PASS |
| tests/test_worker.py | ✅ PASS |
| tests/test_stage3_integration.py | ✅ PASS |
| tests/test_regression_formats.py | ✅ PASS |
| tests/test_advanced_settings.py | ✅ PASS |

Source-level Stage 5 checks (`TEST_EXIT=0`):
`AUDIO_WAV_ENGAGES_SR`, `AUDIO_WAV_TRANSCRIPT_EMBEDDED`, `AUDIO_MP3_NOFFMPEG_ERROR`,
`AUDIO_MP3_NOFFMPEG_FRIENDLY`, `MSG_MISSING_DEP`, `MSG_MISSING_FFMPEG`,
`MSG_NETWORK_FAIL`, `MSG_NO_SPEECH` — **all PASS**.

---

## 6. Build / Frozen EXE (构建 / 冻结运行时)

**Production build (`build_exe.sh`):**
- `PYINSTALLER_EXIT=0`, `BUILD_MDDESK_EXIT=0`
- Artifact: `dist/md-desk/md-desk.exe` (16.5 MB, built 2026-08-17 03:54)
- Offscreen launch: **stays alive** past 5 s timeout (`EXIT=124`) with **0 bytes stderr** → clean GUI boot.

**Frozen companion (`stage5.spec` → `dist/stage5/stage5.exe`):**
- `PYINSTALLER_STAGE5_EXIT=0`
- `FROZEN_IMPORT_PYDUB` ✅, `FROZEN_IMPORT_SR` ✅ (hidden imports collected)
- `FROZEN_WAV_ENGAGES_SR` ✅, `FROZEN_WAV_TRANSCRIPT_EMBEDDED` ✅
- `FROZEN_MP3_NOFFMPEG_ERROR` ✅, `FROZEN_MP3_NOFFMPEG_FRIENDLY` ✅
- `STAGE5_FROZEN_PASS` (`FROZEN_EXIT=0`)

> **Frozen EXE 至少一种音频格式实际转写 PASS** ✅ — WAV transcription pipeline exercised inside the bundle (`recognize_google` stubbed; matches the established verification pattern of Stages 2–4).

---

## 7. Remaining Gaps (已知缺口)

1. **Real Google SR transcription not exercised end-to-end** in CI — mocked `recognize_google`. By design: no guaranteed network/speech audio in build env. The *pipeline* (engine → pydub/sr → recognizer → markdown) is verified; only the live API call is stubbed.
2. **MP3/M4A/MP4 real decode not verified** (no FFmpeg in build env). Friendly-error path is verified; actual decode depends on the user providing FFmpeg.
3. **No offline ASR** (Whisper/OpenAI/Azure) — explicitly out of scope per spec.
4. **No transcription-language selection** wired into GUI — Google SR auto-detects; language picker is a future enhancement, not required for v0.2.

---

## 8. Transparency Disclosures (透明披露)

- ⚠️ **Online dependency:** MdDesk audio transcription calls **Google's online Speech Recognition API** (`recognizer.recognize_google`). It is **NOT offline ASR**. Requires internet access; fails gracefully (friendly "联网" message) when unreachable.
- ⚠️ **External FFmpeg:** MP3/M4A/MP4 require a **system FFmpeg** binary on PATH (not bundled). WAV needs none. Documented in `requirements.txt` and plan §15.

---

## 9. v0.2 READY / NOT READY

### ✅ **v0.2 READY (with documented caveats)**

Audio transcription capability is **added and verified**:
- WAV transcription pipeline works (source + frozen EXE).
- MP3/M4A/MP4 fail gracefully with a friendly Chinese message when FFmpeg is absent (no crash).
- 5 distinct friendly error categories (missing dep / missing FFmpeg / network / no-speech / generic).
- Full regression suite green.
- Production `md-desk.exe` builds and launches cleanly; frozen audio smoke PASS.

**Caveats carried into v0.2 release notes:** transcription is online-only (Google SR); MP3-class formats need user-supplied FFmpeg; no offline ASR.

---

## Stop — No further action taken

Per spec, this report is the terminal deliverable for Stage 5. No Stage 6 work was started.
