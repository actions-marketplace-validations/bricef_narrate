"""What a job can ask for (#79): each option, the CLI flag it becomes, and what it takes.

One table, read three ways: to check a request, to make the child's command
line, and to describe the API (openapi.py). A test checks every option against
the CLI's own flags, so the two can't drift.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..cli import SUBTITLE_CHOICES

RENDERS = ("build", "audio")  # jobs that make a video or audio from a project
REVIEWS = ("frames", "hear")  # jobs that look at, or listen to, what a job made
KINDS = RENDERS + REVIEWS
ENGINES = ("auto", "kokoro", "elevenlabs", "silent")
AUDIO_FORMATS = ("mp3", "m4a", "ogg", "opus", "flac", "wav")


@dataclass(frozen=True)
class Option:
    flag: str | None  # the CLI flag it becomes; None for what the service applies itself
    type: type  # str, bool, int or float
    kinds: tuple[str, ...]  # the jobs that take it
    description: str
    choices: tuple[str, ...] | None = None


OPTIONS: dict[str, Option] = {
    "tts": Option("--tts", str, (*RENDERS, "frames"), "speech engine; the service's own unless given (Kokoro by "
                                                       "default). For frames, the one the video was built with", ENGINES),
    "tts_model": Option("--tts-model", str, (*RENDERS, "frames"), "ElevenLabs model id (default eleven_multilingual_v2)"),
    "scenes": Option("--scenes", str, ("build",), "build only these scenes: 3, 3-5 or 2,4"),
    "subtitles": Option("--subtitles", str, RENDERS, "subtitles for this build, over the script's own; every mode "
                                                     "but none also writes .srt and .vtt", SUBTITLE_CHOICES),
    "transcript": Option("--transcript", bool, RENDERS, "also write what's spoken as plain text"),
    "regenerate": Option("--regenerate", bool, ("build",), "take render:web captures again, rather than reuse them"),
    "format": Option(None, str, ("audio",), "the audio file's format (default mp3)", AUDIO_FORMATS),
    "at": Option("--at", str, ("frames",), "frames at these seconds, as in 1.5,12,30"),
    "every": Option("--every", float, ("frames",), "a frame every so many seconds"),
    "count": Option("--count", int, ("frames",), "frames spread evenly across the video"),
    "width": Option("--width", int, ("frames",), "each frame's width in pixels (default 480)"),
    "language": Option("--language", str, ("hear",), "the narration's language, as in en or fr (default: the "
                                                     "script's, else detected)"),
}
_TYPES = {str: ("a string", "string"), bool: ("true or false", "boolean"), int: ("a whole number", "integer"),
          float: ("a number", "number")}


class OptionError(ValueError):
    """A request asked for something a job doesn't take."""


def check(kind: str, options: Any) -> dict[str, Any]:
    """`options` for a `kind` job, checked: unknown names, wrong types and values are refused."""
    if kind not in KINDS:
        raise OptionError(f"kind must be one of {', '.join(KINDS)}, not {kind!r}")
    if not isinstance(options, dict):
        raise OptionError("options must be an object")
    for name, value in options.items():
        option = OPTIONS.get(name)
        if option is None or kind not in option.kinds:
            raise OptionError(f"{kind} jobs don't take {name!r}")
        number = option.type in (int, float) and isinstance(value, (int, float)) and not isinstance(value, bool)
        fits = number and (option.type is float or isinstance(value, int)) or (
            option.type in (str, bool) and isinstance(value, option.type))
        if not fits or (option.type is str and not value.strip()):
            raise OptionError(f"{name} must be {_TYPES[option.type][0]}")
        if option.choices and value not in option.choices:
            raise OptionError(f"{name} must be one of {', '.join(option.choices)}, not {value!r}")
    return dict(options)


def arguments(kind: str, options: dict[str, Any]) -> list[str]:
    """The CLI flags for checked `options`."""
    out: list[str] = []
    for name, value in options.items():
        option = OPTIONS[name]
        if option.flag is None:
            continue
        if option.type is bool:
            out += [option.flag] if value else []
        else:
            out += [option.flag, str(value)]
    return out


def schema(kind: str) -> dict:
    """The options a `kind` job takes, as JSON Schema."""
    properties = {}
    for name, option in OPTIONS.items():
        if kind in option.kinds:
            prop: dict = {"type": _TYPES[option.type][1], "description": option.description}
            if option.choices:
                prop["enum"] = list(option.choices)
            properties[name] = prop
    return {"type": "object", "properties": properties, "additionalProperties": False}
