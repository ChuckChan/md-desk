"""Thin wrapper around MarkItDown (Stage 3).

Responsibilities:
- path -> markdown via MarkItDown().convert(path).markdown
- map MarkItDown exceptions to a (FileStatus, message) pair

This module is UI/Qt-agnostic and independently testable. It MUST NOT
import Qt or any GUI module.
"""

from io import BytesIO
import time

from markitdown import (
    MarkItDown,
    StreamInfo,
    UnsupportedFormatException,
    FileConversionException,
    MissingDependencyException,
)

from .engine_config import EngineConfig
from .file_entry import FileEntry, FileStatus
from .markitdown_factory import MarkItDownFactory
from .result import QualityWarning
from .settings import Settings, StreamInfoOverride
from .url_fetch_service import FetchError, FetchErrorCategory, UrlFetchService


# ---------------------------------------------------------------------------
# Stage 5 — Audio transcription friendly-error refinement.
#
# markitdown 0.1.7's AudioConverter delegates speech recognition to
# `speech_recognition`, which calls Google's online Speech Recognition API
# (`recognizer.recognize_google`). The raw failures it can raise are wrapped by
# MarkItDown as a single `FileConversionException`. To give MdDesk users a
# clear, actionable message we inspect the wrapped exception chain / message
# and surface 5 distinct categories:
#
#   * MissingDependencyException  -> 缺依赖 (pydub / speech_recognition 未装)
#   * "FFmpeg" / pydub decode     -> 缺 FFmpeg / 解码失败 (MP3/M4A/MP4 需要)
#   * "RequestError"              -> 网络失败 (Google SR 不可达)
#   * "UnknownValueError"         -> 未检测到语音
#   * anything else               -> 通用转换错误
#
# IMPORTANT: this file NEVER modifies upstream markitdown, the URL/YouTube or
# Settings architecture, threads, or the GUI. It only refines the error text.
# ---------------------------------------------------------------------------

def _refine_message(exc: Exception, base_message: str) -> str:
    """Produce a friendly, Chinese audio-aware error message.

    ``exc`` is the exception caught by the conversion wrappers (usually a
    ``FileConversionException`` whose message embeds the original audio
    converter failure type). ``base_message`` is the generic text already
    produced by ``map_exception``.
    """
    # Walk the exception cause chain to find the original audio failure.
    chain: list[Exception] = []
    cur = exc
    while cur is not None:
        chain.append(cur)
        cur = getattr(cur, "__cause__", None)

    blob = " ".join(
        (getattr(e, "__name__", type(e).__name__) + " " + str(e)) for e in chain
    ).lower()

    # 2) FFmpeg / decode failure FIRST — MP3/M4A/MP4 need an external ffmpeg
    #    binary. pydub raises FileNotFoundError (WinError 2 "系统找不到指定的
    #    文件") or CouldntDecodeError when ffmpeg/ffprobe is absent.
    if ("ffmpeg" in blob or "ffprobe" in blob or "couldn" in blob
            or "decode" in blob or "pydub" in blob
            or "filenotfound" in blob or "找不到" in blob or "no such file" in blob):
        return ("音频解码失败：MP3/M4A/MP4 需要系统已安装 FFmpeg 二进制。"
                "WAV 不需要 FFmpeg。请在 PATH 中提供 ffmpeg，或改用 WAV 文件。")

    # 1) Missing transcription dependency (pydub / speech_recognition).
    if "missingdependency" in blob:
        return ("音频转写不可用：缺少组件。请安装 "
                "`markitdown[audio-transcription]`（含 pydub / SpeechRecognition）。")

    # 3) Network failure reaching Google Speech Recognition.
    if "requesterror" in blob or "urlopen" in blob or "urllib" in blob or "connection" in blob:
        return ("语音识别失败：无法连接 Google 在线语音识别服务（需联网）。"
                "MdDesk 的音频转写依赖 Google SR，离线环境不可用。")

    # 4) No speech detected by the recognizer.
    if "unknownvalueerror" in blob or "no speech" in blob or "could not understand" in blob:
        return "未在音频中检测到可识别的语音。"

    # 5) Generic fallback (keep the upstream message for diagnostics).
    return base_message


class ConversionError(Exception):
    """Raised by convert_file on any conversion failure.

    Carries the mapped FileStatus so the caller can update the UI.
    """

    def __init__(self, status: FileStatus, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


def _classify_ai_error(exc: Exception) -> str | None:
    """Return a friendly Chinese message for an AI (OpenAI-compatible) API
    failure, or ``None`` if the exception carries no AI error.

    Why we gather more than the ``__cause__`` / ``__context__`` chain:

    MarkItDown's ``_convert`` swallows a converter exception (e.g. an OpenAI SDK
    error raised inside the built-in LLM image-description path) and, with no
    ``raise ... from`` / active handler, re-raises a fresh
    ``FileConversionException``. The original OpenAI error is NOT reachable via
    ``__cause__`` / ``__context__`` — it lives in
    ``FileConversionException.attempts[i].exc_info[1]``. So we collect:

      * the explicit ``__cause__`` / ``__context__`` chain of ``exc``, and
      * for every ``FailedConversionAttempt`` in ``exc.attempts``, the raw
        exception value plus ITS own cause/context chain.

    The same messages apply to the built-in LLM image description and the
    markitdown-ocr plugin backend (they share one OpenAI-compatible client).
    """
    try:
        import openai
    except Exception:
        return None

    candidates: list[BaseException] = []

    def _collect_chain(e: BaseException | None) -> None:
        seen: set[int] = set()
        cur = e
        while cur is not None and id(cur) not in seen:
            seen.add(id(cur))
            candidates.append(cur)
            nxt = getattr(cur, "__cause__", None) or getattr(cur, "__context__", None)
            cur = nxt

    _collect_chain(exc)

    attempts = getattr(exc, "attempts", None)
    if isinstance(attempts, (list, tuple)):
        for attempt in attempts:
            ei = getattr(attempt, "exc_info", None)
            if isinstance(ei, tuple) and len(ei) >= 2 and isinstance(ei[1], BaseException):
                _collect_chain(ei[1])

    # Order matters: the specific subclasses must be tested before their
    # common base ``APIStatusError`` / ``APIError``.
    for e in candidates:
        if isinstance(e, openai.AuthenticationError):
            return ("AI 服务鉴权失败：API Key 无效或未授权（401）。"
                    "请在「高级设置 → AI 增强转换」中检查 Key。")
        if isinstance(e, openai.PermissionDeniedError):
            return "AI 服务拒绝访问：当前 Key 无权限调用该模型（403）。"
        if isinstance(e, openai.RateLimitError):
            return "AI 服务额度或频率超限（429）。请稍后重试或检查配额。"
        if isinstance(e, (openai.APIConnectionError, openai.APITimeoutError)):
            return ("AI 服务连接失败：网络不可达或超时。请检查网络与 Endpoint "
                    "（OpenAI 兼容地址）。")
        if isinstance(e, openai.BadRequestError):
            return ("AI 请求被拒绝（400）：模型或图片不支持该 Vision 请求，"
                    "或 Prompt 过长。请检查模型名与图片。")
        if isinstance(e, openai.APIStatusError):
            code = getattr(e, "status_code", "?")
            return f"AI 服务返回错误（状态码 {code}）。"
    return None


def map_exception(exc: Exception) -> tuple[FileStatus, str]:
    """Map a MarkItDown exception to (status, human message).

    UnsupportedFormatException      -> UNSUPPORTED
    FileConversionException        -> ERROR (AI-aware, then audio-aware text)
    MissingDependencyException     -> ERROR (AI-aware, then audio-aware text)
    any other Exception            -> ERROR
    """
    if isinstance(exc, UnsupportedFormatException):
        return FileStatus.UNSUPPORTED, f"不支持的文件格式: {exc}"
    if isinstance(exc, (FileConversionException, MissingDependencyException)):
        ai_msg = _classify_ai_error(exc)
        if ai_msg:
            return FileStatus.ERROR, ai_msg
        base = f"转换失败: {exc}"
        return FileStatus.ERROR, _refine_message(exc, base)
    return FileStatus.ERROR, f"转换错误: {exc}"


# Stable marker for a failed OCR block (vendored markitdown-ocr produces it).
# Distinct from the success marker ``*[Image OCR] ... [End OCR]*`` so callers
# can tell a failed OCR apart from real extracted text.
OCR_ERROR_MARKER = "*[OCR Error]"


def markdown_has_ocr_error(markdown: str) -> bool:
    """Return True if the markdown contains an OCR failure block.

    This is the hook MdDesk's UI can use to show "转换完成但 OCR 失败/部分失败"
    without re-parsing conversion internals. The conversion itself still
    succeeds (the failure is surfaced inline), so this is a soft warning, not
    an error status.
    """
    return OCR_ERROR_MARKER in (markdown or "")


# Stable warning code for "the AI call failed and the conversion was
# automatically downgraded to the non-AI path" (v0.6 error isolation).
AI_PROVIDER_FAILURE_CODE = "AI_PROVIDER_FAILURE"


def _ai_fallback_warning(cfg: EngineConfig, ai_msg: str, duration_ms: int) -> QualityWarning:
    """Build the advisory warning attached when an AI failure is isolated.

    Carries the diagnostic dimensions required by the v0.6 plan (§4.5):
    provider / capability context / duration / sanitized error — but NEVER
    the API key, an Authorization header, or a secret-bearing URL.
    """
    provider = getattr(cfg, "ai_provider", "openai-compatible") or "openai-compatible"
    model = getattr(cfg, "ai_model", "") or "未知模型"
    return QualityWarning(
        AI_PROVIDER_FAILURE_CODE,
        f"AI 调用失败，已自动降级为无 AI 转换（provider={provider}, "
        f"model={model}, 降级耗时={duration_ms}ms）：{ai_msg}",
    )


def _convert_with_ai_fallback(call, cfg: EngineConfig, warnings_out: "list | None"):
    """Run ``call(engine_config) -> markdown`` with v0.6 AI error isolation.

    When the conversion fails with an AI-classified error (auth / connection /
    timeout / quota raised through the OpenAI-compatible client) while AI is
    enabled, the SAME conversion is retried once with AI fully disabled:

      * retry succeeds -> the non-AI result is returned and an
        ``AI_PROVIDER_FAILURE`` warning is appended to ``warnings_out`` (when
        provided). The file still converts — an AI outage must never break
        ordinary document conversion (plan §3.4).
      * retry fails too -> the retry's (real) conversion error is raised;
        the AI failure stays chained as the cause for diagnostics.

    Non-AI failures never trigger a retry. The OCR plugin already fails soft
    (inline ``*[OCR Error]*`` blocks) and is unaffected by this path.
    """
    try:
        return call(cfg)
    except Exception as exc:  # noqa: BLE001 - all failures mapped below
        ai_msg = _classify_ai_error(exc) if cfg.ai_enabled else None
        if ai_msg is None:
            status, message = map_exception(exc)
            raise ConversionError(status, message) from exc
        t0 = time.perf_counter()
        try:
            markdown = call(EngineConfig.disabled())
        except Exception as exc2:  # noqa: BLE001 - the real conversion error
            status, message = map_exception(exc2)
            raise ConversionError(status, message) from exc
        if warnings_out is not None:
            duration_ms = int((time.perf_counter() - t0) * 1000)
            warnings_out.append(_ai_fallback_warning(cfg, ai_msg, duration_ms))
        return markdown


def convert_file(
    path: str,
    override: StreamInfoOverride | None = None,
    engine_config: EngineConfig | None = None,
    warnings_out: "list | None" = None,
) -> str:
    """Convert a single local file to Markdown.

    Returns the markdown string. Raises ConversionError on failure, with
    .status mapped per map_exception(). Does NOT reimplement parsing.

    When ``engine_config`` (v0.3) is provided and AI is enabled, the engine is
    built via ``MarkItDownFactory`` with the shared LLM client + OCR plugin.
    When ``None`` the v0.2-equivalent configuration is used.

    ``warnings_out`` (v0.6, optional): a list that receives advisory
    ``QualityWarning`` objects — currently only the AI_PROVIDER_FAILURE notice
    emitted when an AI failure was isolated and the conversion downgraded.
    Pass the worker's list to surface it in the result / report / diagnostics.

    Stage 4 (advanced): when ``override`` is supplied and non-empty, the file
    is converted via ``convert_stream`` with a StreamInfo that merges the
    override fields (extension / mimetype / charset / filename) over the
    normal path-derived guess. When ``override`` is None/empty the call is
    byte-for-byte the legacy ``MarkItDown().convert(path)`` path, so default
    behavior is unchanged.
    """
    cfg = engine_config or EngineConfig.disabled()

    if override is None or override.is_empty():
        # Legacy path — identical to pre-Stage-4 behavior (v0.2 when AI off).

        def _plain(engine: EngineConfig) -> str:
            return MarkItDownFactory.create(engine).convert(path).markdown

        return _convert_with_ai_fallback(_plain, cfg, warnings_out)

    # Advanced override path.
    from pathlib import Path as _Path  # local import keeps module top clean

    try:
        with open(path, "rb") as fh:
            data = fh.read()
        base = StreamInfo(
            local_path=path,
            extension=_Path(path).suffix.lower(),
            filename=_Path(path).name,
        )
        merged = base.copy_and_update(**override.as_kwargs())
    except Exception as exc:  # noqa: BLE001 - I/O error reading the file
        status, message = map_exception(exc)
        raise ConversionError(status, message) from exc

    def _overridden(engine: EngineConfig) -> str:
        return MarkItDownFactory.create(engine).convert_stream(
            BytesIO(data), stream_info=merged
        ).markdown

    return _convert_with_ai_fallback(_overridden, cfg, warnings_out)


def _fetch_message(exc: FetchError) -> str:
    """Turn a FetchError into a friendly, user-facing Chinese message."""
    msg = exc.message
    if exc.category == FetchErrorCategory.BLOCKED:
        return f"安全拦截：{msg}"
    if exc.category == FetchErrorCategory.SCHEME:
        return f"不支持的链接：{msg}"
    if exc.category == FetchErrorCategory.TIMEOUT:
        return f"网络超时：{msg}"
    if exc.category == FetchErrorCategory.TOO_LARGE:
        return f"文件过大：{msg}"
    if exc.category == FetchErrorCategory.REDIRECT:
        return f"重定向错误：{msg}"
    if exc.category == FetchErrorCategory.SSL_ERROR:
        return f"证书错误：{msg}"
    return f"网络错误：{msg}"


def convert_url(
    url: str,
    service: UrlFetchService | None = None,
    override: StreamInfoOverride | None = None,
    youtube_languages: list[str] | None = None,
    engine_config: EngineConfig | None = None,
    warnings_out: "list | None" = None,
) -> str:
    """Safely fetch a remote http/https URL and convert it to Markdown.

    Uses UrlFetchService (SSRF/redirect/timeout/size protected) ->
    BytesIO + StreamInfo -> MarkItDown.convert_stream(). This deliberately
    does NOT use MarkItDown.convert_uri() / convert() with an http(s) string.

    Stage 4 (advanced):
      * ``override`` (non-empty) merges extension/mimetype/charset/filename
        over the URL-derived StreamInfo (e.g. fix a misidentified remote MIME).
        The fetched ``url`` is always preserved on the final StreamInfo.
      * ``youtube_languages`` (non-empty) is forwarded to the engine as the
        ``youtube_transcript_languages`` kwarg so the user can prefer specific
        caption languages. Empty/None -> not forwarded (legacy behavior).

    ``warnings_out`` (v0.6): optional list receiving advisory warnings when an
    AI failure is isolated and the conversion downgraded (same contract as
    ``convert_file``).

    Returns the markdown string. Raises ConversionError on failure.
    """
    svc = service or UrlFetchService()
    try:
        result = svc.fetch(url)
    except FetchError as exc:
        raise ConversionError(FileStatus.ERROR, _fetch_message(exc)) from exc
    stream_info = result.stream_info
    if override is not None and not override.is_empty():
        # copy_and_update merges only non-None fields, so the fetched
        # url/filename/extension survive unless explicitly overridden.
        stream_info = stream_info.copy_and_update(**override.as_kwargs())

    kwargs: dict = {}
    if youtube_languages:
        kwargs["youtube_transcript_languages"] = list(youtube_languages)

    cfg = engine_config or EngineConfig.disabled()

    def _engine_convert(engine: EngineConfig) -> str:
        return MarkItDownFactory.create(engine).convert_stream(
            result.content, stream_info=stream_info, **kwargs
        ).markdown

    return _convert_with_ai_fallback(_engine_convert, cfg, warnings_out)


def convert_entry(
    entry: FileEntry,
    settings: Settings | None = None,
    engine_config: EngineConfig | None = None,
    warnings_out: "list | None" = None,
) -> str:
    """Convert a FileEntry, dispatching to URL or local-file handling.

    URL-backed entries go through convert_url(); local files through
    convert_file(). Both raise ConversionError on failure.

    ``engine_config`` (v0.3) is the resolved runtime engine configuration
    (built once per batch by the worker). If omitted, it is derived from
    ``settings`` (or the v0.2-equivalent disabled config).

    ``settings`` (optional) supplies the global Conversion Options:
      * youtube_transcript_languages -> forwarded to convert_url when set.
    The per-entry ``stream_info_override`` (from the Advanced Settings dialog)
    is always applied when present. With no config and no per-entry override
    the behavior is exactly the legacy conversion flow.

    ``warnings_out`` (v0.6): optional list receiving advisory warnings from
    AI failure isolation; the worker forwards them into the
    ConversionResult / ConversionReport / diagnostics.
    """
    cfg = engine_config or (
        EngineConfig.from_settings(settings) if settings else EngineConfig.disabled()
    )
    if getattr(entry, "url", None):
        langs = None
        if settings is not None:
            langs = settings.youtube_transcript_languages or None
        return convert_url(
            entry.url,
            override=getattr(entry, "stream_info_override", None),
            youtube_languages=langs,
            engine_config=cfg,
            warnings_out=warnings_out,
        )
    return convert_file(
        entry.path,
        override=getattr(entry, "stream_info_override", None),
        engine_config=cfg,
        warnings_out=warnings_out,
    )
