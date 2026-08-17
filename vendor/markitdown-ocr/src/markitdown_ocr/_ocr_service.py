"""
OCR Service Layer for MarkItDown
Provides LLM Vision-based image text extraction.
"""

import base64
from typing import Any, BinaryIO
from dataclasses import dataclass

from markitdown import StreamInfo


@dataclass
class OCRResult:
    """Result from OCR extraction."""

    text: str
    confidence: float | None = None
    backend_used: str | None = None
    error: str | None = None
    # The original exception (when any), kept so callers can classify the
    # failure by type (auth / quota / network / vision) rather than only by a
    # string message. Added by MdDesk's vendored copy of markitdown-ocr.
    error_exc: BaseException | None = None


# Stable, recognizable markers for OCR output. The ERROR marker MUST be
# distinct from the SUCCESS marker so callers (e.g. MdDesk's UI) can tell a
# failed OCR apart from genuine extracted text — it must never masquerade as
# normal OCR content.
OCR_ERROR_OPEN = "*[OCR Error]"
OCR_ERROR_CLOSE = "[End OCR Error]*"
OCR_SUCCESS_OPEN = "*[Image OCR]"
OCR_SUCCESS_CLOSE = "[End OCR]*"


def _classify_ocr_error(exc: BaseException | None) -> str:
    """Classify an OCR backend failure into a clear, user-facing Chinese
    message. Shared by all vendored OCR converters and MdDesk's converter
    so auth/quota/network/vision failures are explicit, not a generic
    "could not process" string.
    """
    if exc is None:
        return "OCR 服务未返回任何文本（未知原因）。"
    try:
        import openai
    except Exception:
        return f"OCR 服务调用失败：{exc}"
    if isinstance(exc, openai.AuthenticationError):
        return "OCR 失败：API Key 无效或未授权（401）。"
    if isinstance(exc, openai.PermissionDeniedError):
        return "OCR 失败：当前 Key 无权限调用该模型（403）。"
    if isinstance(exc, openai.RateLimitError):
        return "OCR 失败：额度或频率超限（429），请稍后重试。"
    if isinstance(exc, (openai.APIConnectionError, openai.APITimeoutError)):
        return "OCR 失败：AI 服务连接失败（网络不可达或超时）。"
    if isinstance(exc, openai.BadRequestError):
        return "OCR 失败：请求被拒绝（400），模型或图片不支持该 Vision 请求。"
    if isinstance(exc, openai.APIStatusError):
        code = getattr(exc, "status_code", "?")
        return f"OCR 失败：AI 服务返回错误（状态码 {code}）。"
    return f"OCR 失败：{exc}"


def _format_ocr_block(result: "OCRResult") -> str | None:
    """Render an ``OCRResult`` as a Markdown block with a stable marker.

    * backend error (``error_exc`` set) -> ``*[OCR Error] ... [End OCR Error]*``
    * successful text                -> ``*[Image OCR] ... [End OCR]*``
    * nothing                        -> ``None`` (caller omits the image)
    """
    if result.error_exc is not None:
        return f"{OCR_ERROR_OPEN}\n{_classify_ocr_error(result.error_exc)}\n{OCR_ERROR_CLOSE}"
    if result.text and result.text.strip():
        return f"{OCR_SUCCESS_OPEN}\n{result.text.strip()}\n{OCR_SUCCESS_CLOSE}"
    return None


class LLMVisionOCRService:
    """OCR service using LLM vision models (OpenAI-compatible)."""

    def __init__(
        self,
        client: Any,
        model: str,
        default_prompt: str | None = None,
    ) -> None:
        """
        Initialize LLM Vision OCR service.

        Args:
            client: OpenAI-compatible client
            model: Model name (e.g., 'gpt-4o', 'gemini-2.0-flash')
            default_prompt: Default prompt for OCR extraction
        """
        self.client = client
        self.model = model
        self.default_prompt = default_prompt or (
            "Extract all text from this image. "
            "Return ONLY the extracted text, maintaining the original "
            "layout and order. Do not add any commentary or description."
        )

    def extract_text(
        self,
        image_stream: BinaryIO,
        prompt: str | None = None,
        stream_info: StreamInfo | None = None,
        **kwargs: Any,
    ) -> OCRResult:
        """Extract text using LLM vision."""
        if self.client is None:
            return OCRResult(
                text="",
                backend_used="llm_vision",
                error="LLM client not configured",
            )

        try:
            image_stream.seek(0)

            content_type: str | None = None
            if stream_info:
                content_type = stream_info.mimetype

            if not content_type:
                try:
                    from PIL import Image

                    image_stream.seek(0)
                    img = Image.open(image_stream)
                    fmt = img.format.lower() if img.format else "png"
                    content_type = f"image/{fmt}"
                except Exception:
                    content_type = "image/png"

            image_stream.seek(0)
            base64_image = base64.b64encode(image_stream.read()).decode("utf-8")
            data_uri = f"data:{content_type};base64,{base64_image}"

            actual_prompt = prompt or self.default_prompt
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": actual_prompt},
                            {
                                "type": "image_url",
                                "image_url": {"url": data_uri},
                            },
                        ],
                    }
                ],
            )

            text = response.choices[0].message.content
            return OCRResult(
                text=text.strip() if text else "",
                backend_used="llm_vision",
            )
        except Exception as e:
            return OCRResult(
                text="", backend_used="llm_vision", error=str(e), error_exc=e
            )
        finally:
            image_stream.seek(0)
