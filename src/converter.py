"""Thin wrapper around MarkItDown (Stage 3).

Responsibilities:
- path -> markdown via MarkItDown().convert(path).markdown
- map MarkItDown exceptions to a (FileStatus, message) pair

This module is UI/Qt-agnostic and independently testable. It MUST NOT
import Qt or any GUI module.
"""

from io import BytesIO

from markitdown import (
    MarkItDown,
    StreamInfo,
    UnsupportedFormatException,
    FileConversionException,
    MissingDependencyException,
)

from .file_entry import FileEntry, FileStatus
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


def map_exception(exc: Exception) -> tuple[FileStatus, str]:
    """Map a MarkItDown exception to (status, human message).

    UnsupportedFormatException      -> UNSUPPORTED
    FileConversionException        -> ERROR (audio-aware friendly text)
    MissingDependencyException     -> ERROR (audio-aware friendly text)
    any other Exception            -> ERROR
    """
    if isinstance(exc, UnsupportedFormatException):
        return FileStatus.UNSUPPORTED, f"不支持的文件格式: {exc}"
    if isinstance(exc, (FileConversionException, MissingDependencyException)):
        base = f"转换失败: {exc}"
        return FileStatus.ERROR, _refine_message(exc, base)
    return FileStatus.ERROR, f"转换错误: {exc}"


def convert_file(path: str, override: StreamInfoOverride | None = None) -> str:
    """Convert a single local file to Markdown.

    Returns the markdown string. Raises ConversionError on failure, with
    .status mapped per map_exception(). Does NOT reimplement parsing.

    Stage 4 (advanced): when ``override`` is supplied and non-empty, the file
    is converted via ``convert_stream`` with a StreamInfo that merges the
    override fields (extension / mimetype / charset / filename) over the
    normal path-derived guess. When ``override`` is None/empty the call is
    byte-for-byte the legacy ``MarkItDown().convert(path)`` path, so default
    behavior is unchanged.
    """
    if override is None or override.is_empty():
        # Legacy path — identical to pre-Stage-4 behavior.
        try:
            return MarkItDown().convert(path).markdown
        except Exception as exc:  # noqa: BLE001 - map all failures to ERROR/UNSUPPORTED
            status, message = map_exception(exc)
            raise ConversionError(status, message) from exc

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
        return MarkItDown().convert_stream(BytesIO(data), stream_info=merged).markdown
    except Exception as exc:  # noqa: BLE001 - map all failures to ERROR/UNSUPPORTED
        status, message = map_exception(exc)
        raise ConversionError(status, message) from exc


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

    Returns the markdown string. Raises ConversionError on failure.
    """
    svc = service or UrlFetchService()
    try:
        result = svc.fetch(url)
    except FetchError as exc:
        raise ConversionError(FileStatus.ERROR, _fetch_message(exc)) from exc
    try:
        stream_info = result.stream_info
        if override is not None and not override.is_empty():
            # copy_and_update merges only non-None fields, so the fetched
            # url/filename/extension survive unless explicitly overridden.
            stream_info = stream_info.copy_and_update(**override.as_kwargs())

        kwargs: dict = {}
        if youtube_languages:
            kwargs["youtube_transcript_languages"] = list(youtube_languages)

        return MarkItDown().convert_stream(
            result.content, stream_info=stream_info, **kwargs
        ).markdown
    except Exception as exc:  # noqa: BLE001 - map engine failures to ERROR/UNSUPPORTED
        status, message = map_exception(exc)
        raise ConversionError(status, message) from exc


def convert_entry(entry: FileEntry, settings: Settings | None = None) -> str:
    """Convert a FileEntry, dispatching to URL or local-file handling.

    URL-backed entries go through convert_url(); local files through
    convert_file(). Both raise ConversionError on failure.

    ``settings`` (optional) supplies the global Conversion Options:
      * youtube_transcript_languages -> forwarded to convert_url when set.
    The per-entry ``stream_info_override`` (from the Advanced Settings dialog)
    is always applied when present. With ``settings=None`` and no per-entry
    override the behavior is exactly the legacy conversion flow.
    """
    if getattr(entry, "url", None):
        langs = None
        if settings is not None:
            langs = settings.youtube_transcript_languages or None
        return convert_url(
            entry.url,
            override=getattr(entry, "stream_info_override", None),
            youtube_languages=langs,
        )
    return convert_file(
        entry.path, override=getattr(entry, "stream_info_override", None)
    )
