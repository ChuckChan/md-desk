"""Runtime engine configuration for MdDesk v0.3 (AI-enhanced conversion).

``EngineConfig`` is the SINGLE source of truth the conversion engine is built
from. It is intentionally separate from ``Settings`` (which is the persisted,
user-facing config) because it also carries the resolved API Key (pulled from
Windows Credential Manager at build time — never stored in settings.json) and
the runtime OCR-plugin availability flag.

The factory (``markitdown_factory.create``) is the ONLY place that constructs a
``MarkItDown`` instance, eliminating the scattered ``MarkItDown()`` calls that
existed before v0.3 and guaranteeing AI-OFF is byte-for-byte the v0.2 path.

This module is UI / Qt-agnostic and independently testable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from . import credential_store
from .ai_provider import AIProviderConfig
from .settings import AI_TIMEOUT_DEFAULT_SECONDS, PROVIDER_OPENAI_COMPATIBLE, Settings


def is_ocr_plugin_available() -> bool:
    """True if the official ``markitdown-ocr`` plugin package is importable.

    In the frozen EXE the package is collected by PyInstaller, so this returns
    True there too. When False, OCR is simply skipped (image description still
    works if AI is enabled) and the UI surfaces a clear warning.
    """
    try:
        import markitdown_ocr  # noqa: F401

        return True
    except Exception:
        return False


@dataclass
class EngineConfig:
    """Resolved, runtime configuration consumed by the factory.

    ``ai_enabled`` False  -> the factory returns a plain ``MarkItDown()``
        (identical to v0.2; no AI, no plugins).
    ``ai_enabled`` True   -> the factory builds an OpenAI-compatible client and
        (when available) registers the official OCR plugin converters.
    """

    ai_enabled: bool = False
    ai_provider: str = PROVIDER_OPENAI_COMPATIBLE  # v0.6: "openai-compatible"
    ai_endpoint: str = ""  # OpenAI-compatible base_url (e.g. https://api.openai.com/v1)
    ai_api_key: str = ""  # resolved from Windows Credential Manager
    ai_model: str = ""  # e.g. gpt-4o
    ai_timeout: float = AI_TIMEOUT_DEFAULT_SECONDS  # v0.6: finite per-request timeout (s)
    ai_prompt: Optional[str] = None  # None -> official defaults for both OCR & image desc
    ai_ocr_enabled: bool = True  # v0.6: independent OCR capability toggle
    ai_image_description_enabled: bool = True  # v0.6: independent description toggle
    ocr_plugin_available: bool = False

    # Internal, non-serialized cache of the constructed OpenAI-compatible
    # client so a batch of files shares one client instance.
    _client: object = field(default=None, repr=False, compare=False)

    @staticmethod
    def disabled() -> "EngineConfig":
        """The v0.2-equivalent configuration: no AI, no plugins."""
        return EngineConfig()

    @classmethod
    def from_settings(cls, settings: Optional[Settings]) -> "EngineConfig":
        """Build a runtime config from persisted ``Settings``.

        Resolves the API Key from Windows Credential Manager (absent -> empty
        string, which the factory turns into a placeholder so a misconfigured
        endpoint still produces a clear auth error rather than crashing).
        New v0.6 fields (provider / timeout / capability toggles) default so
        that a pre-v0.6 settings file keeps its exact old behavior.
        """
        if settings is None or not getattr(settings, "ai", None) or not settings.ai.enabled:
            return cls.disabled()

        key = ""
        try:
            key = credential_store.get_api_key() or ""
        except credential_store.CredentialStoreError:
            # Key store unavailable; let conversion surface a clear auth error.
            key = ""

        return cls(
            ai_enabled=True,
            ai_provider=getattr(settings.ai, "provider", PROVIDER_OPENAI_COMPATIBLE)
            or PROVIDER_OPENAI_COMPATIBLE,
            ai_endpoint=settings.ai.endpoint or "",
            ai_api_key=key,
            ai_model=settings.ai.model or "",
            ai_timeout=getattr(settings.ai, "timeout_seconds", AI_TIMEOUT_DEFAULT_SECONDS),
            ai_prompt=(settings.ai.prompt or None),
            ai_ocr_enabled=bool(getattr(settings.ai, "ocr_enabled", True)),
            ai_image_description_enabled=bool(
                getattr(settings.ai, "image_description_enabled", True)),
            ocr_plugin_available=is_ocr_plugin_available(),
        )

    def should_enable_ocr(self) -> bool:
        """OCR converters should be registered only when AI is on, the user
        enabled the OCR capability, and the official plugin is importable."""
        return self.ai_enabled and self.ai_ocr_enabled and self.ocr_plugin_available

    def should_enable_image_description(self) -> bool:
        """The built-in LLM image description runs only when AI is on and the
        user enabled the image-description capability."""
        return self.ai_enabled and self.ai_image_description_enabled

    def to_provider_config(self) -> AIProviderConfig:
        """The resolved provider connection (for the client factory and the
        connection test). Never persists or logs the key."""
        return AIProviderConfig(
            provider=self.ai_provider,
            api_key=self.ai_api_key,
            endpoint=self.ai_endpoint,
            model=self.ai_model,
            timeout_seconds=self.ai_timeout,
            prompt=self.ai_prompt,
        )
