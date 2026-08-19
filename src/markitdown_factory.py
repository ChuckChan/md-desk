"""The single factory that builds a configured ``MarkItDown`` instance (v0.3,
reworked in v0.6 for capability-independent control).

This replaces the three scattered ``MarkItDown()`` calls that previously lived
in ``converter.py``. Centralizing construction here guarantees:

  * AI-OFF  -> ``MarkItDown()`` exactly as v0.2 (no plugins, no llm_client).
  * AI-ON   -> an OpenAI-compatible client is attached via the unified
    ``ClientFactory`` (v0.6: with a finite timeout), and the two AI
    capabilities are wired INDEPENDENTLY (plan §3.2):
      - image description (built-in ``ImageConverter``)  -> llm_* kwargs
        are passed to the ``MarkItDown`` constructor only when the user
        enabled that capability;
      - OCR (official ``markitdown-ocr`` plugin)         -> the plugin is
        registered only when the user enabled OCR.

Why explicit plugin registration in BOTH dev and frozen runs (v0.6):
``MarkItDown.enable_plugins(**kwargs)`` forwards the SAME constructor kwargs
to every plugin, and ``enable_builtins(**kwargs)`` stores the same
``llm_client`` for the built-in ``ImageConverter``. There is therefore no way
to hand a client to the OCR plugin via constructor kwargs without also
switching image description on. We instead always use
``enable_plugins=False`` and call ``markitdown_ocr.register_converters``
directly with the plugin's own kwargs — the SAME code path the entry point
would invoke — which is what the frozen build already did since v0.3.
"""

from __future__ import annotations

from .ai_provider import AIProviderConfig, ClientFactory
from .engine_config import EngineConfig, is_ocr_plugin_available

from markitdown import MarkItDown


def _build_openai_client(endpoint: str, api_key: str, timeout: float = 60.0):
    """Construct an OpenAI-compatible client via the unified ClientFactory.

    Kept as a module function (v0.3 API) for backwards compatibility with
    tests; the actual construction path is ``ClientFactory.create``.
    """
    return ClientFactory.create(AIProviderConfig(
        endpoint=endpoint, api_key=api_key, timeout_seconds=timeout,
    ))


def create(config: EngineConfig) -> MarkItDown:
    """Return a ``MarkItDown`` instance configured per ``config``.

    Capability wiring (v0.6):
      * neither capability enabled -> plain ``MarkItDown()`` (AI effectively
        off even if the master switch is on);
      * image description only    -> llm_* kwargs on the constructor;
      * OCR only                  -> plugin registered with its own llm kwargs
        (constructor gets none, so the built-in ImageConverter skips
        description);
      * both                      -> both wirings.
    """
    if not config.ai_enabled:
        # v0.2-equivalent path: no AI, no plugins.
        return MarkItDown()

    desc_on = config.should_enable_image_description()

    # OCR wiring needs the plugin's real availability — re-check directly
    # (NOT via config.should_enable_ocr, whose ocr_plugin_available flag only
    # reflects the EngineConfig built by from_settings) so OCR works no matter
    # how the EngineConfig was constructed. Same policy as the v0.3 factory.
    ocr_on = bool(config.ai_enabled and config.ai_ocr_enabled
                  and is_ocr_plugin_available())

    if not desc_on and not ocr_on:
        # Master switch on but both capabilities off -> nothing AI-shaped
        # should happen; identical to the plain engine.
        return MarkItDown()

    # Reuse a single client across a batch when possible (v0.3 behavior).
    client = config._client
    if client is None:
        client = ClientFactory.create(config.to_provider_config())
        config._client = client

    # kwargs for the built-in LLM image description (via the MarkItDown
    # constructor -> enable_builtins stores them for ImageConverter).
    llm_kwargs: dict = {}
    if desc_on:
        llm_kwargs = {
            "llm_client": client,
            "llm_model": config.ai_model or None,
            "llm_prompt": config.ai_prompt or None,
        }

    md = MarkItDown(enable_plugins=False, **llm_kwargs)

    if ocr_on:
        # Explicit registration (dev AND frozen) so the plugin receives the
        # OCR kwargs regardless of the image-description toggle.
        import markitdown_ocr

        markitdown_ocr.register_converters(
            md,
            llm_client=client,
            llm_model=config.ai_model or None,
            llm_prompt=config.ai_prompt or None,
        )
    return md


class MarkItDownFactory:
    """Public namespace for the MarkItDown factory.

    Callers use ``MarkItDownFactory.create(config)``. The implementation lives
    in the module-level functions above; this class just exposes them as a
    stable, import-friendly namespace so ``from .markitdown_factory import
    MarkItDownFactory`` works the same way in dev, tests, and the frozen EXE.
    """

    create = staticmethod(create)
    _build_openai_client = staticmethod(_build_openai_client)
