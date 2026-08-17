"""The single factory that builds a configured ``MarkItDown`` instance (v0.3).

This replaces the three scattered ``MarkItDown()`` calls that previously lived
in ``converter.py``. Centralizing construction here guarantees:

  * AI-OFF  -> ``MarkItDown()`` exactly as v0.2 (no plugins, no llm_client).
  * AI-ON   -> an OpenAI-compatible client is attached for BOTH the built-in
    LLM image description AND the official ``markitdown-ocr`` plugin's
    LLM-vision backend (they share the same client, per the v0.3 design).

Two registration paths for the OCR plugin:

  * Dev / venv / tests (not frozen): we use the official
    ``MarkItDown(enable_plugins=True, ...)``. MarkItDown discovers
    ``markitdown_ocr`` via its ``markitdown.plugin`` entry point and calls the
    plugin's ``register_converters`` with the llm_* kwargs. This is the
    canonical, supported mechanism.
  * Frozen PyInstaller EXE: entry-point metadata (``.dist-info``) is NOT
    collected by PyInstaller, so plugin auto-discovery finds nothing. Instead
    we explicitly import the official ``markitdown_ocr`` package and call its
    ``register_converters`` directly — the SAME code path the entry point would
    invoke — so OCR works identically in the frozen build.
"""

from __future__ import annotations

import sys

from markitdown import MarkItDown

from .engine_config import EngineConfig, is_ocr_plugin_available


def _build_openai_client(endpoint: str, api_key: str):
    """Construct an OpenAI-compatible client.

    ``endpoint`` is the base_url (e.g. https://api.openai.com/v1 or a local
    OpenAI-compatible gateway). ``api_key`` may be empty for endpoints that do
    not require auth; we substitute a non-empty placeholder so the SDK does not
    reject an empty key outright, and any real auth failure surfaces as a
    clear error during the actual API call.
    """
    from openai import OpenAI

    return OpenAI(
        api_key=api_key or "not-required",
        base_url=endpoint or None,
    )


def create(config: EngineConfig) -> MarkItDown:
    """Return a ``MarkItDown`` instance configured per ``config``."""
    if not config.ai_enabled:
        # v0.2-equivalent path: no AI, no plugins.
        return MarkItDown()

    # Reuse a single client across a batch when possible.
    client = config._client
    if client is None:
        client = _build_openai_client(config.ai_endpoint, config.ai_api_key)
        config._client = client

    llm_kwargs = {
        "llm_client": client,
        "llm_model": config.ai_model or None,
        "llm_prompt": config.ai_prompt or None,
    }

    if getattr(sys, "frozen", False):
        # Frozen EXE: entry-point metadata isn't collected -> register the
        # official OCR plugin explicitly (same code path, deterministic).
        # We re-check availability directly (not via config.should_enable_ocr,
        # which only reflects the EngineConfig built by from_settings) so OCR
        # works no matter how the EngineConfig was constructed.
        md = MarkItDown(enable_plugins=False, **llm_kwargs)
        if is_ocr_plugin_available():
            import markitdown_ocr

            markitdown_ocr.register_converters(md, **llm_kwargs)
        return md

    # Dev / venv / tests: official plugin auto-discovery via entry point.
    return MarkItDown(enable_plugins=True, **llm_kwargs)


class MarkItDownFactory:
    """Public namespace for the v0.3 MarkItDown factory.

    Callers use ``MarkItDownFactory.create(config)``. The implementation lives
    in the module-level functions above; this class just exposes them as a
    stable, import-friendly namespace so ``from .markitdown_factory import
    MarkItDownFactory`` works the same way in dev, tests, and the frozen EXE.
    """

    create = staticmethod(create)
    _build_openai_client = staticmethod(_build_openai_client)
