"""Unified AI Provider layer (v0.6 — AI 实用化版).

This is the SINGLE place that knows how to turn AI settings into a usable
AI client and how to probe that client's health. Everything above it
(``EngineConfig`` / ``markitdown_factory`` / the Settings dialog) talks to
this module; nothing below it (the OpenAI SDK) leaks upwards.

Two responsibilities (plan §4.1 / §4.2 / §3.4):

  * ``AIProviderConfig``  — the provider-agnostic connection description
    (provider / api_key / endpoint / model / timeout / prompt).
  * ``ClientFactory``     — ``AIProviderConfig -> OpenAI-compatible client``.
    The ONLY client construction path in the app. OCR, image description
    and any future v0.7 capability MUST reuse it, never build their own.

Plus the v0.6 Connection Test (plan §3.4): ``test_connection`` performs one
minimal, time-bounded chat request and classifies the outcome into a
user-understandable Chinese message. It NEVER returns or logs the API key
or the Authorization header; every message passes through the same
redaction used by the diagnostic report.

Qt-free and markitdown-free; imports only ``settings`` (constants) and
``report`` (redaction helpers) so it stays independently testable.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from .report import _redact_secrets, _sanitize_url
from .settings import (
    AI_TIMEOUT_DEFAULT_SECONDS,
    PROVIDER_OPENAI_COMPATIBLE,
    normalize_ai_timeout,
)

# Supported provider ids (v0.6: exactly one).
SUPPORTED_PROVIDERS = (PROVIDER_OPENAI_COMPATIBLE,)


class ProviderConfigError(Exception):
    """Raised when a provider configuration cannot be turned into a client.

    The message is user-facing (Chinese) and contains no secrets.
    """


@dataclass
class AIProviderConfig:
    """Resolved provider connection description (plan §4.1).

    ``api_key`` is the resolved secret (from Windows Credential Manager);
    it lives ONLY in this runtime object — never in ``Settings`` /
    settings.json / logs / reports.
    """

    provider: str = PROVIDER_OPENAI_COMPATIBLE
    api_key: str = ""
    endpoint: str = ""
    model: str = ""
    timeout_seconds: float = AI_TIMEOUT_DEFAULT_SECONDS
    prompt: Optional[str] = None

    def __post_init__(self) -> None:
        self.timeout_seconds = normalize_ai_timeout(self.timeout_seconds)

    def describe(self) -> str:
        """Sanitized, loggable description (provider + model + endpoint)."""
        endpoint = _sanitize_url(self.endpoint) if self.endpoint else "默认 OpenAI"
        model = self.model or "（未设置）"
        return f"provider={self.provider} model={model} endpoint={endpoint}"


class ClientFactory:
    """The single client construction path (plan §4.2).

    ``Settings → EngineConfig → AIProviderConfig → ClientFactory.create``.
    Constructing an OpenAI-compatible client anywhere else is a bug.

    ``max_retries=0`` is deliberate: it makes the configured timeout a hard
    upper bound for every AI call (the SDK default of 2 retries would
    silently multiply it by 3).
    """

    @staticmethod
    def create(config: AIProviderConfig):
        if config.provider not in SUPPORTED_PROVIDERS:
            raise ProviderConfigError(
                f"不支持的 AI Provider：{config.provider}。"
                f"v0.6 仅支持 {PROVIDER_OPENAI_COMPATIBLE}。"
            )
        from openai import OpenAI

        return OpenAI(
            api_key=config.api_key or "not-required",
            base_url=config.endpoint or None,
            timeout=float(config.timeout_seconds),
            max_retries=0,
        )


@dataclass(frozen=True)
class ConnectionTestResult:
    """Outcome of one connection test (plan §3.4)."""

    ok: bool
    message: str                 # sanitized, user-facing Chinese message
    duration_ms: int
    provider: str = PROVIDER_OPENAI_COMPATIBLE
    model: str = ""
    endpoint: str = ""           # sanitized display form (no secrets/query)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "message": self.message,
            "duration_ms": self.duration_ms,
            "provider": self.provider,
            "model": self.model,
            "endpoint": self.endpoint,
        }


def _sanitize_message(text: str) -> str:
    """Redact any credential-shaped substring from a message (defense)."""
    return _redact_secrets(text or "")


def _classify_connection_error(exc: BaseException, endpoint_display: str) -> str:
    """Map an OpenAI SDK exception from the probe call to a clear Chinese
    message. Order: specific subclasses before their common bases."""
    try:
        import openai
    except Exception:  # pragma: no cover - openai is a hard dependency
        return _sanitize_message(f"连接测试失败：{exc}")

    if isinstance(exc, openai.AuthenticationError):
        return ("凭据无效：服务返回 401（API Key 无效或未授权）。"
                "请检查 API Key。")
    if isinstance(exc, openai.PermissionDeniedError):
        return ("凭据被拒绝：服务返回 403（当前 Key 无权限访问该模型）。"
                "请检查 Key 权限与模型名。")
    if isinstance(exc, openai.RateLimitError):
        return ("服务可达且已通过鉴权，但当前额度/频率受限（429）。"
                "连接本身可用，稍后即可正常调用。")
    if isinstance(exc, openai.APITimeoutError):
        return (f"连接超时：{endpoint_display} 在设定时间内未响应。"
                "请检查网络或在设置中增大 Timeout。")
    if isinstance(exc, openai.APIConnectionError):
        return (f"无法连接：{endpoint_display} 不可达（DNS 解析失败、"
                "网络不通或地址错误）。请检查 Endpoint。")
    if isinstance(exc, openai.BadRequestError):
        return ("服务可达，但请求被拒绝（400）：通常是模型名无效或该模型"
                "不支持此请求。请检查模型名。")
    if isinstance(exc, openai.NotFoundError):
        return ("服务可达，但未找到该模型或路径（404）。请检查模型名与 "
                "Endpoint 地址（通常以 /v1 结尾）。")
    if isinstance(exc, openai.APIStatusError):
        code = getattr(exc, "status_code", "?")
        return f"服务返回错误（状态码 {code}）。"
    # Anything else (malformed response, JSON error, ...) — keep the sanitized
    # text so the user can still see what happened without any secret.
    return _sanitize_message(f"连接测试失败：{exc}")


def test_connection(
    config: AIProviderConfig,
    *,
    client: Optional[Any] = None,
    client_factory: Optional[Callable[[AIProviderConfig], Any]] = None,
) -> ConnectionTestResult:
    """Actively probe the provider described by ``config`` (plan §3.4).

    Sends ONE minimal chat completion (``max_tokens=1``) so the probe
    verifies, in a single round-trip: endpoint reachability, credential
    validity, and that the service accepts a call to the configured model.

    ``client`` / ``client_factory`` let tests inject a fake client instead
    of touching the network. Never raises; every failure — including an
    unbuildable client — is returned as ``ConnectionTestResult(ok=False)``
    with a sanitized message. All messages are redacted before return, so
    the API key / Authorization header can never appear in UI or logs.
    """
    endpoint_display = _sanitize_url(config.endpoint) if config.endpoint else "默认 OpenAI 端点"

    if config.provider not in SUPPORTED_PROVIDERS:
        return ConnectionTestResult(
            ok=False,
            message=(f"不支持的 AI Provider：{config.provider}。"
                     f"v0.6 仅支持 {PROVIDER_OPENAI_COMPATIBLE}。"),
            duration_ms=0,
            provider=config.provider,
            model=config.model,
            endpoint=endpoint_display,
        )

    t0 = time.perf_counter()
    duration = lambda: int((time.perf_counter() - t0) * 1000)  # noqa: E731

    # -- build (or take) the client ---------------------------------------
    probe_client = client
    if probe_client is None:
        factory = client_factory or ClientFactory.create
        try:
            probe_client = factory(config)
        except ProviderConfigError as exc:
            return ConnectionTestResult(
                ok=False, message=str(exc), duration_ms=duration(),
                provider=config.provider, model=config.model,
                endpoint=endpoint_display,
            )
        except Exception as exc:  # noqa: BLE001 - client build failure
            return ConnectionTestResult(
                ok=False,
                message=_sanitize_message(f"无法创建 AI 客户端：{exc}"),
                duration_ms=duration(),
                provider=config.provider, model=config.model,
                endpoint=endpoint_display,
            )

    # -- one minimal, time-bounded call -----------------------------------
    try:
        response = probe_client.chat.completions.create(
            model=config.model,
            messages=[{"role": "user", "content": "ping"}],
            max_tokens=1,
        )
        # Malformed-response guard: a 200 with no parsable choice still means
        # the endpoint answered but is not a sane OpenAI-compatible service.
        choices = getattr(response, "choices", None)
        if not choices:
            return ConnectionTestResult(
                ok=False,
                message=("服务有响应，但返回内容不是有效的 OpenAI 兼容格式"
                         "（缺少 choices）。请确认 Endpoint 指向兼容服务。"),
                duration_ms=duration(),
                provider=config.provider, model=config.model,
                endpoint=endpoint_display,
            )
        return ConnectionTestResult(
            ok=True,
            message=(f"连接成功：服务可达，Key 有效，模型 {config.model} "
                     f"可调用。"),
            duration_ms=duration(),
            provider=config.provider, model=config.model,
            endpoint=endpoint_display,
        )
    except Exception as exc:  # noqa: BLE001 - every probe failure is a result
        return ConnectionTestResult(
            ok=False,
            message=_classify_connection_error(exc, endpoint_display),
            duration_ms=duration(),
            provider=config.provider, model=config.model,
            endpoint=endpoint_display,
        )


# ---------------------------------------------------------------------------
# Capability layer vocabulary (plan §4.3)
# ---------------------------------------------------------------------------
# Capabilities describe WHAT the model is asked to do; the provider layer
# describes HOW to reach it. v0.6 ships exactly two capabilities; the names
# are stable identifiers used in warnings / diagnostics.
CAPABILITY_OCR = "ocr"
CAPABILITY_IMAGE_DESCRIPTION = "image_description"

SUPPORTED_CAPABILITIES = (CAPABILITY_OCR, CAPABILITY_IMAGE_DESCRIPTION)
