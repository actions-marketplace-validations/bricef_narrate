"""Pin voice names to engine voices with voices.yaml.

    # voices.yaml, next to the script or in ~/.config/narrate/
    Brian:
      kokoro: bm_lewis
      elevenlabs: George            # a default voice name, or a voice id
    Narrator:
      kokoro: af_heart
      elevenlabs: 21m00Tcm4TlvDq8ikWAM

A script's `voice: Brian` then resolves to bm_lewis on Kokoro and George on
ElevenLabs. The project file overrides the user file name by name. The silent
engine follows the Kokoro mapping, since it times speech like Kokoro.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import yaml

from .tts import ELEVENLABS_VOICES, KOKORO_VOICES

ENGINES = ("kokoro", "elevenlabs")
VoiceMap = dict[str, dict[str, str]]  # lowercase name -> engine -> voice


class VoiceMapError(Exception):
    pass


def user_file() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return Path(base) / "narrate" / "voices.yaml"


def _validate(engine: str, value: str, name: str, source: Path) -> str:
    if engine == "kokoro" and value.lower() not in KOKORO_VOICES:
        raise VoiceMapError(f"{source}: {name} maps to {value!r}, which is not a Kokoro voice")
    if engine == "elevenlabs" and value.lower() not in ELEVENLABS_VOICES and not re.fullmatch(r"[A-Za-z0-9]{20}", value):
        raise VoiceMapError(f"{source}: {name} maps to {value!r}, neither an ElevenLabs default voice nor a voice id")
    return value


def read(path: Path) -> VoiceMap:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as e:
        raise VoiceMapError(f"{path}: invalid YAML: {e}") from None
    if not isinstance(data, dict):
        raise VoiceMapError(f"{path}: expected a map of voice names")
    result: VoiceMap = {}
    for name, engines in data.items():
        if not isinstance(engines, dict):
            raise VoiceMapError(f"{path}: {name} needs a map of engine: voice")
        for engine, value in engines.items():
            if engine not in ENGINES:
                raise VoiceMapError(f"{path}: {name}: unknown engine {engine!r} (expected {', '.join(ENGINES)})")
            result.setdefault(str(name).strip().lower(), {})[engine] = _validate(engine, str(value).strip(), name, path)
    return result


def load(project_dir: Path | None) -> VoiceMap:
    merged: VoiceMap = {}
    for path in (user_file(), project_dir / "voices.yaml" if project_dir else None):
        if path is not None and path.is_file():
            for name, engines in read(path).items():
                merged[name] = {**merged.get(name, {}), **engines}
    return merged


def apply(voice_map: VoiceMap, name: str | None, engine: str) -> str | None:
    """The script's voice name with any mapping for this engine applied (keeping a /lang suffix)."""
    if not name:
        return name
    base, slash, lang = name.partition("/")
    target = voice_map.get(base.strip().lower(), {}).get("kokoro" if engine == "silent" else engine)
    return f"{target}{slash}{lang}" if target else name
