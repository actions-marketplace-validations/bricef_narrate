"""Voices in the studio (#65): the catalogue, auditions by ear, and voices.yaml pins.

An audition is the sample sentence read the way the script would read it:
the script's own header (voice speed, pitch and the rest), then `(voice: …)`,
then the sentence, planned and synthesised as a scene (studio/audio.py). So
voices.yaml pins and the engine's own matching apply as in a build, and the
speech lands in the usual cache: the second play, and a build that uses the
same words, cost nothing.
"""

from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path
from typing import Any

import yaml

from .. import voicemap
from ..tts import ELEVENLABS_VOICES, KOKORO_PREFIX_LANG, KOKORO_VOICES, NARAKEET_PROFILES

SAMPLE = "This is how this voice reads your script."
_IDS = {voice_id: name for name, (voice_id, _) in ELEVENLABS_VOICES.items()}
_SEPARATOR = re.compile(r"^ {0,3}-{3,}\s*$")


def _resolved(synth: Any, voice_map: dict, name: str) -> str:
    """What `name` becomes on the session's engine, as a name a person can read."""
    mapped = voicemap.apply(voice_map, name, synth.name)
    try:
        voice = synth.resolve(mapped, None, set())
    except Exception:  # noqa: BLE001 - an engine that can't resolve offline: show the name as it is
        return mapped or name
    return _IDS.get(voice.id, voice.id).title() if voice.id in _IDS else voice.id


def catalogue(synth: Any, project: Path) -> dict:
    """Every voice the studio offers, grouped, each with its language, gender and what it becomes on the engine."""
    try:
        voice_map = voicemap.load(project)
        project_pins = voicemap.read(project / "voices.yaml") if (project / "voices.yaml").is_file() else {}
        problem = None
    except voicemap.VoiceMapError as e:
        voice_map, project_pins, problem = {}, {}, str(e)
    user_pins = voicemap.read(voicemap.user_file()) if voicemap.user_file().is_file() else {}

    def entry(name: str, group: str, lang: str | None, gender: str | None) -> dict:
        return {"name": name, "group": group, "lang": lang, "gender": gender, "resolves": _resolved(synth, voice_map, name)}

    voices = [entry(name, "pinned", None, None) for name in sorted(voice_map)]
    voices += [entry(v, "kokoro", KOKORO_PREFIX_LANG[v[0]], v[1]) for v in KOKORO_VOICES]
    voices += [entry(name.title(), "elevenlabs", lang, gender) for name, (_, (lang, gender)) in ELEVENLABS_VOICES.items()]
    voices += [entry(name.title(), "narakeet", lang, gender) for name, (lang, gender) in sorted(NARAKEET_PROFILES.items())]
    return {"engine": synth.name, "voices": voices, "pins": project_pins, "user_pins": user_pins,
            "user_file": str(voicemap.user_file()), "problem": problem}


def sample_script(text: str, voice: str, sample: str) -> str:
    """A one-scene script: `text`'s header, then the voice, then the sample's first paragraph."""
    lines = text.split("\n")
    header = ""
    if lines and _SEPARATOR.match(lines[0]):
        end = next((k for k in range(1, len(lines)) if _SEPARATOR.match(lines[k])), None)
        if end is not None:
            header = "\n".join(lines[:end + 1]) + "\n\n"
    words = " ".join((sample.strip().split("\n\n")[0] or SAMPLE).split()) or SAMPLE
    if not re.fullmatch(r"[\w .'/-]+", voice):
        raise ValueError(f"not a voice name: {voice!r}")
    return f"{header}(voice: {voice})\n\n{words}\n"


def characters(text: str, script: Path, synth: Any) -> dict:
    """What auditioning would send to the engine: nothing if it's cached."""
    from .analysis import analyse

    missing = analyse(text, script, synth)["missing"] or {"characters": 0}
    return {"characters": missing["characters"], "cached": missing["characters"] == 0}


def write_pins(project: Path, pins: dict[str, dict[str, str]]) -> None:
    """Write the project's voices.yaml, checked as a build would read it, in one step."""
    clean = {str(name).strip(): {engine: str(v).strip() for engine, v in engines.items() if str(v).strip()}
             for name, engines in pins.items() if str(name).strip()}
    clean = {name: engines for name, engines in clean.items() if engines}
    target = project / "voices.yaml"
    fd, tmp = tempfile.mkstemp(dir=project, prefix=".voices.", suffix=".yaml")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write("# Voice names pinned to engine voices (narrate studio; see `narrate voices`)\n")
            if clean:
                yaml.safe_dump(clean, f, sort_keys=True, allow_unicode=True)
        try:
            voicemap.read(Path(tmp))  # as a build would read it
        except voicemap.VoiceMapError as e:  # a voice an engine doesn't have: said of voices.yaml, not the temp file
            raise voicemap.VoiceMapError(str(e).replace(tmp, "voices.yaml")) from None
        if target.exists():
            os.chmod(tmp, target.stat().st_mode & 0o777)
        os.replace(tmp, target)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
