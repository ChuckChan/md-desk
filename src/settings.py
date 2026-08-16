"""MdDesk settings infrastructure (Stage 4 — Advanced Conversion Settings).

This module is UI / Qt-agnostic and independently testable. It MUST NOT
import Qt or any GUI module.

It owns two concerns from MdDesk-v0.2-Plan.md section 6.2:

  * Conversion Options  -> ``Settings.youtube_transcript_languages``
    (the only genuinely useful, verifiable conversion-level option in
    markitdown 0.1.7; forwarded to the engine converter as the
    ``youtube_transcript_languages`` kwarg).

  * Input Detection Override (advanced, per-entry) -> ``StreamInfoOverride``
    lets power users correct a misidentified extension / mimetype / charset /
    filename before conversion. It is applied per FileEntry, NOT globally.

Engine Configuration (enable_plugins / llm_* / docintel_* / cu_* / exiftool)
and Audio / Azure / Plugin toggles are intentionally OUT OF SCOPE for v0.2
(see plan section 5 MUST/SHOULD/LATER and the Stage 4 DON'T list). They are
not modeled here so we never expose unimplemented feature toggles.

Persistence: ``%APPDATA%/MdDesk/settings.json``. First start with no file
falls back to ``Settings.default()``. A missing or corrupt (unparseable /
wrong-typed) file is silently replaced by defaults — never raises.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional


# --------------------------------------------------------------------------
# StreamInfo Override (advanced, per-entry Input Detection Override)
# --------------------------------------------------------------------------
@dataclass
class StreamInfoOverride:
    """Optional correction of how a single entry is detected by the engine.

    Any field left as ``None`` means "do not override" — the engine's normal
    guess (from path / content / URL) is used for that dimension. This makes
    partial overrides safe-by-construction (only the supplied fields win).

    These map 1:1 onto markitdown's public ``StreamInfo`` fields
    (extension / mimetype / charset / filename); we deliberately do NOT expose
    ``local_path`` / ``url`` because those describe where the bytes came from
    and must never be overridden by the user.
    """

    extension: Optional[str] = None
    mimetype: Optional[str] = None
    charset: Optional[str] = None
    filename: Optional[str] = None

    def is_empty(self) -> bool:
        """True when no field is set -> no override should be applied."""
        return (
            self.extension is None
            and self.mimetype is None
            and self.charset is None
            and self.filename is None
        )

    def as_kwargs(self) -> dict[str, str]:
        """Return only the set fields as a kwargs dict for StreamInfo.

        Empty strings are treated as unset so a blank dialog field means
        "no override".
        """
        out: dict[str, str] = {}
        for key in ("extension", "mimetype", "charset", "filename"):
            value = getattr(self, key)
            if value:  # non-empty string
                out[key] = value
        return out


# --------------------------------------------------------------------------
# Settings (persisted configuration)
# --------------------------------------------------------------------------
@dataclass
class Settings:
    """Persisted MdDesk configuration.

    Only contains options that are real and verifiable in markitdown 0.1.7.
    ``version`` enables safe future migrations (unknown keys are ignored on
    load; a version mismatch falls back to defaults rather than crashing).
    """

    version: int = 1
    youtube_transcript_languages: list[str] = field(default_factory=list)

    # Path the settings were last loaded from / should be saved to.
    # Not serialized.
    _path: Optional[str] = field(default=None, repr=False, compare=False)

    # --- defaults ---------------------------------------------------------
    @staticmethod
    def default() -> "Settings":
        """Factory for the out-of-the-box configuration.

        Empty ``youtube_transcript_languages`` means "let the engine choose
        its default languages" — i.e. default settings change NOTHING about
        existing conversion behavior.
        """
        return Settings(version=1, youtube_transcript_languages=[])

    # --- serialization ----------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "youtube_transcript_languages": list(self.youtube_transcript_languages),
        }

    @classmethod
    def from_dict(cls, data: Any) -> "Settings":
        """Build a Settings from a parsed JSON object, validating types.

        Returns ``Settings.default()`` if the shape is wrong. Unknown keys are
        ignored; missing keys fall back to defaults.
        """
        if not isinstance(data, dict):
            return cls.default()
        try:
            version = data.get("version", 1)
            if not isinstance(version, int):
                version = 1
            langs = data.get("youtube_transcript_languages", [])
            if not isinstance(langs, list):
                langs = []
            # Keep only real, non-empty strings; drop anything else.
            clean_langs: list[str] = []
            for item in langs:
                if isinstance(item, str) and item.strip():
                    clean_langs.append(item.strip())
            return cls(version=version, youtube_transcript_languages=clean_langs)
        except Exception:  # noqa: BLE001 - any surprise -> safe default
            return cls.default()

    # --- persistence ------------------------------------------------------
    @staticmethod
    def default_path() -> Path:
        """%APPDATA%/MdDesk/settings.json (Windows). Falls back to a local
        ``.md_desk`` dir when APPDATA is unavailable (e.g. some CI / Linux)."""
        appdata = os.environ.get("APPDATA")
        if appdata:
            base = Path(appdata) / "MdDesk"
        else:
            base = Path.home() / ".md_desk"
        return base / "settings.json"

    @classmethod
    def load(cls, path: Optional[str | Path] = None) -> "Settings":
        """Load settings from ``path`` (or the default path).

        Missing file -> defaults (first start). Unparseable / wrong-typed file
        -> defaults (corrupt config safe fallback). Never raises.
        """
        target = Path(path) if path is not None else cls.default_path()
        try:
            if not target.exists():
                settings = cls.default()
                settings._path = str(target)
                return settings
            text = target.read_text(encoding="utf-8")
            parsed = json.loads(text)
            settings = cls.from_dict(parsed)
            settings._path = str(target)
            return settings
        except Exception:  # noqa: BLE001 - missing / corrupt -> defaults
            settings = cls.default()
            settings._path = str(target)
            return settings

    def save(self, path: Optional[str | Path] = None) -> None:
        """Persist to ``path`` (or the path it was loaded from / default).

        Creates the parent directory if needed. A save failure (e.g. read-only
        FS) is swallowed rather than crashing the app — settings are best-
        effort persistent, never load-bearing for conversion.
        """
        target = Path(path) if path is not None else Path(self._path or self.default_path())
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2),
                              encoding="utf-8")
            self._path = str(target)
        except OSError:
            # Best-effort only; do not crash the GUI over a config write.
            pass
