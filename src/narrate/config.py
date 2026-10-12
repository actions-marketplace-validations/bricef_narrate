"""Typed settings from the script header (spec §3), plus shared value parsers."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from PIL import ImageColor

FPS = 30

SIZE_PRESETS = {
    "720p": (1280, 720), "1080p": (1920, 1080), "1440p": (2560, 1440), "4x3": (800, 600),
    "720p-portrait": (720, 1280), "1080p-portait": (1080, 1920), "1080p-portrait": (1080, 1920),
    "instagram": (1080, 1350), "instagram-square": (1080, 1080), "instagram-story": (1080, 1920),
    "pinterest-square": (1080, 1080), "pinterest-vertical": (720, 1280), "pinterest-2x3": (720, 1080),
    "linkedin": (1728, 720), "linkedin-vertical": (720, 1728), "tiktok": (1080, 1920),
    "twitter": (1280, 720), "twitter-square": (720, 720), "facebook": (1280, 720),
    "facebook-square": (1080, 1080), "facebook-carousel": (1080, 1080),
}

SPEED_PRESETS = {"slow": 0.8, "normal": 1.0, "fast": 1.2}
# Approximate SSML prosody volume steps, in dB
VOLUME_PRESETS = {"x-soft": -9.0, "soft": -4.5, "standard": 0.0, "normal": 0.0, "loud": 4.5, "x-loud": 9.0}
SUBTITLE_MODES = {"none", "external", "embed", "overlay", "overlay-background", "tiktok", "auto"}
TARGETS = {"offline", "online", "self-hosted"}
BUILTIN_MUSIC = {"ukulele-1", "ukulele-2", "uplifting-1", "uplifting-2", "corporate-1"}

# Narakeet transition names -> ffmpeg xfade transitions (spec §10)
TRANSITIONS = {
    "crossfade": "fade", "wipe": "wiperight", "wipe-right": "wiperight", "wipe-left": "wipeleft",
    "wipe-up": "wipeup", "wipe-down": "wipedown", "slide-right": "slideright", "slide-left": "slideleft",
    "slide-up": "slideup", "slide-down": "slidedown", "fade-right": "smoothright",
    "fade-left": "smoothleft", "fade-up": "smoothup", "fade-down": "smoothdown",
    "fade-circle": "circleopen", "slice-right": "hrslice", "slice-left": "hlslice",
    "slice-up": "vuslice", "slice-down": "vdslice", "dissolve": "dissolve", "pixelize": "pixelize",
    "pixelise": "pixelize", "radial": "radial", "circle": "circlecrop", "rect": "rectcrop",
    "reveal": "revealright",
}
# narrate's own: dips through a colour, half out and half in (spec §18.3), drawn
# by a custom xfade expression (build.transition_graph)
EXTRA_TRANSITIONS = {"fade-black": "custom", "fade-white": "custom"}
XFADE = {**TRANSITIONS, **EXTRA_TRANSITIONS}
DEFAULT_TRANSITION_SECONDS = 0.2


class ConfigError(Exception):
    pass


def parse_time(value: Any) -> float:
    """Seconds from `12`, `12.5`, `01:20`, `01:20.5` or `1:02:03`."""
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not re.fullmatch(r"\d+(?::\d{1,2}){0,2}(?:\.\d+)?", text):
        raise ConfigError(f"invalid time {text!r}")
    seconds = 0.0
    for part in text.split(":"):
        seconds = seconds * 60 + float(part)
    return seconds


def parse_number(value: Any, what: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        raise ConfigError(f"invalid {what} {value!r}") from None


def parse_color(value: Any, what: str = "colour") -> str:
    """A CSS colour name or #RRGGBB[AA] as #rrggbb or #rrggbbaa."""
    text = str(value).strip()
    try:
        rgba = ImageColor.getcolor(text, "RGBA")
    except ValueError:
        raise ConfigError(f"invalid {what} {text!r}") from None
    r, g, b, a = rgba
    return f"#{r:02x}{g:02x}{b:02x}" + (f"{a:02x}" if a != 255 else "")


def parse_transition(value: Any, default_type: str = "crossfade") -> tuple[str, float] | None:
    """`wipe 0.5` -> ("wipe", 0.5); `none` -> None; a bare duration takes `default_type`."""
    tokens = str(value).strip().lower().split()
    if not tokens or tokens[0] == "none":
        return None
    if re.fullmatch(r"\d+(?:\.\d+)?", tokens[0]):
        kind, rest = default_type, tokens
    else:
        kind, rest = tokens[0], tokens[1:]
    if kind not in XFADE:
        raise ConfigError(f"unknown transition {kind!r}")
    seconds = parse_number(rest[0], "transition duration") if rest else DEFAULT_TRANSITION_SECONDS
    if seconds <= 0:
        raise ConfigError("transition duration must be positive")
    return kind, seconds


def parse_size(value: Any) -> tuple[int, int]:
    text = str(value).strip().lower()
    if text in SIZE_PRESETS:
        return SIZE_PRESETS[text]
    m = re.fullmatch(r"(\d+)\s*x\s*(\d+)", text)
    if not m:
        raise ConfigError(f"invalid size {value!r}")
    w, h = int(m.group(1)), int(m.group(2))
    # x264 with yuv420p needs even dimensions
    return w + w % 2, h + h % 2


def parse_speed(value: Any) -> float:
    text = str(value).strip().lower()
    if text in SPEED_PRESETS:
        return SPEED_PRESETS[text]
    speed = parse_number(text, "voice-speed")
    if not 0.3 <= speed <= 2:
        raise ConfigError(f"voice-speed {speed} is outside 0.3–2")
    return speed


# voice-pitch presets in semitones; numbers (-150..150) are read as hundredths
# of an octave, so 100 is an octave up and Narakeet's "squeaky" 130 is very high
PITCH_PRESETS = {"x-low": -4.0, "low": -2.0, "normal": 0.0, "medium": 0.0, "high": 2.0, "x-high": 4.0}


def parse_pitch(value: Any) -> float:
    """A frequency ratio: 1.0 leaves the voice unchanged."""
    text = str(value).strip().lower()
    if text in PITCH_PRESETS:
        return 2 ** (PITCH_PRESETS[text] / 12)
    amount = parse_number(text, "voice-pitch")
    if not -150 <= amount <= 150:
        raise ConfigError(f"voice-pitch {amount} is outside -150–150")
    return 2 ** (amount / 100)


def parse_volume(value: Any) -> float | str:
    """Gain in dB, or "normalized"."""
    text = str(value).strip().lower()
    if text == "normalized":
        return text
    if text not in VOLUME_PRESETS:
        raise ConfigError(f"invalid voice-volume {value!r}")
    return VOLUME_PRESETS[text]


@dataclass
class SubtitleConfig:
    mode: str = "none"  # none | external | embed | overlay | overlay-background | tiktok
    break_chars: int = 135
    scale: float = 1.0
    size: int | None = None
    color: str = "#ffffff"
    outline: str | None = None
    background: str | None = None
    font: str | None = None
    position: str = "bottom"

    @property
    def burned(self) -> bool:
        return self.mode in ("overlay", "overlay-background", "tiktok")

    @property
    def files(self) -> bool:
        """Every mode but none writes .srt and .vtt files, burned-in ones too (#58)."""
        return self.mode != "none"


@dataclass
class Background:
    source: str
    volume: float = 1.0
    fade_in: bool = False
    fade_out: bool = False


@dataclass
class OverlaySpec:
    """A web page laid over the picture (#59): over one scene, or over the whole video from the header."""

    file: str
    params: dict[str, str] = field(default_factory=dict)  # reach the page as window.narrate.params
    viewport: tuple[int, int] | None = None  # the size the page was designed at, if not the video's
    scenes: tuple[int, int] | None = None  # a header overlay's first and last scene (inclusive)
    line: int = 0  # where a scene's overlay is written, for errors


def parse_overlay(value: Any, header: bool = False) -> OverlaySpec | None:
    """`file.html`, or a map with `file` (and `viewport`, `scenes` for the header, any other keys as
    parameters); None for `none`, which hides the video's overlays for a scene."""
    if isinstance(value, str):
        text = value.strip()
        if text.lower() == "none":
            return None
        props: dict[str, Any] = {"file": text}
    elif isinstance(value, dict):
        props = {str(k).strip(): v for k, v in value.items()}
    else:
        raise ConfigError("overlay takes a page, as in overlay: ticker.html, or a map with file:")
    file = str(props.pop("file", "")).strip()
    if not file:
        raise ConfigError("overlay needs a file: the page to lay over the picture")
    if not file.lower().endswith((".html", ".htm")):
        raise ConfigError(f"an overlay is a web page (.html), not {file!r}")
    spec = OverlaySpec(file)
    if "viewport" in props:
        spec.viewport = parse_size(str(props.pop("viewport")))
    if header and "scenes" in props:
        text = str(props.pop("scenes")).replace(" ", "")
        m = re.fullmatch(r"(\d+)(?:-(\d+))?", text)
        if not m or int(m.group(1)) < 1 or (m.group(2) and int(m.group(2)) < int(m.group(1))):
            raise ConfigError(f"overlay scenes are a scene or a range, as in 2-5, not {text!r}")
        spec.scenes = (int(m.group(1)), int(m.group(2) or m.group(1)))
    spec.params = {k: str(v) for k, v in props.items()}
    return spec


def parse_overlays(value: Any) -> list[OverlaySpec]:
    """The header's overlay: one page, one map, or a list of them."""
    items = value if isinstance(value, list) else [value]
    specs = [parse_overlay(item, header=True) for item in items]
    if any(spec is None for spec in specs):
        raise ConfigError("overlay: none belongs in a scene, to hide the video's overlays there")
    return specs


@dataclass
class Settings:
    width: int = 1280
    height: int = 720
    voice: str | None = None
    voice_speed: float = 1.0
    voice_volume: float | str = 0.0
    voice_pitch: float = 1.0
    narration_language: str | None = None
    canvas: str | None = None
    theme: str = "default"
    asset_resize: str = "cover"
    transition: str | None = None
    subtitles: SubtitleConfig = field(default_factory=SubtitleConfig)
    background: Background | None = None
    poster_time: str = "50%"
    target: str = "offline"
    fade_in: float = 0.0  # seconds from black at the start (narrate extension)
    fade_out: float = 0.0  # seconds to black at the end
    loudness: float | None = None  # integrated LUFS for the finished mix (narrate extension)
    image_zoom: float | None = None  # how far pan and zoom move by default (narrate extension)
    transcript: bool = False  # write <name>.transcript.txt beside the output (narrate extension, #58)
    overlays: list[OverlaySpec] = field(default_factory=list)  # web pages over the whole video (#59)


def parse_subtitles(value: Any) -> SubtitleConfig:
    if isinstance(value, str):
        mode = value.strip().lower()
        if mode not in SUBTITLE_MODES:
            raise ConfigError(f"invalid subtitles mode {value!r}")
        cfg = SubtitleConfig(mode="overlay" if mode == "auto" else mode)
        if mode == "overlay-background":
            cfg.background = "#00000099"
        elif mode == "tiktok":
            cfg.scale, cfg.break_chars, cfg.position = 1.8, 25, "middle"
        return cfg
    if not isinstance(value, dict):
        raise ConfigError("subtitles must be a mode or a map")
    props = {str(k).lower(): v for k, v in value.items()}
    mode = str(props.pop("mode", "")).strip().lower()
    if mode not in ("embed", "overlay"):
        raise ConfigError("subtitles map needs mode: embed or overlay")
    return _style(SubtitleConfig(mode=mode), props)


def subtitles_with_mode(header: Any, mode: str) -> SubtitleConfig:
    """The header's subtitles with another mode (narrate build --subtitles, #58): the mode's own
    defaults, then any style keys the header's map sets (break, color, font, position, ...)."""
    cfg = parse_subtitles(mode)
    if isinstance(header, dict):
        cfg = _style(cfg, {str(k).lower(): v for k, v in header.items() if str(k).lower() != "mode"})
    return cfg


def _style(cfg: SubtitleConfig, props: dict[str, Any]) -> SubtitleConfig:
    """`cfg` with the style keys of a subtitles map applied."""
    for key, raw in props.items():
        if key == "break":
            cfg.break_chars = int(parse_number(raw, "subtitles break"))
        elif key == "scale":
            cfg.scale = parse_number(raw, "subtitles scale")
        elif key == "size":
            cfg.size = int(parse_number(raw, "subtitles size"))
        elif key in ("color", "outline", "background"):
            setattr(cfg, key, parse_color(raw, f"subtitles {key}"))
        elif key == "font":
            cfg.font = str(raw).strip()
        elif key == "position":
            pos = str(raw).strip().lower()
            if pos not in ("top", "middle", "bottom"):
                raise ConfigError(f"invalid subtitles position {raw!r}")
            cfg.position = pos
        else:
            raise ConfigError(f"unknown subtitles property {key!r}")
    return cfg


def parse_background(value: Any) -> Background:
    tokens = str(value).split()
    if not tokens:
        raise ConfigError("background needs a file or track name")
    bg = Background(source=tokens[0])
    for token in tokens[1:]:
        t = token.lower()
        if t == "fade-in":
            bg.fade_in = True
        elif t == "fade-out":
            bg.fade_out = True
        else:
            bg.volume = parse_number(t, "background volume")
    return bg


def _header_handlers(s: Settings) -> dict[str, Any]:
    """How each header key sets `s`."""
    return {
        "size": lambda v: setattr(s, "width", parse_size(v)[0]) or setattr(s, "height", parse_size(v)[1]),
        "voice": lambda v: setattr(s, "voice", str(v).strip()),
        "voice-speed": lambda v: setattr(s, "voice_speed", parse_speed(v)),
        "voice-volume": lambda v: setattr(s, "voice_volume", parse_volume(v)),
        "voice-pitch": lambda v: setattr(s, "voice_pitch", parse_pitch(v)),
        "narration-language": lambda v: setattr(s, "narration_language", str(v).strip()),
        "canvas": lambda v: setattr(s, "canvas", parse_color(v, "canvas")),
        "theme": lambda v: setattr(s, "theme", str(v).strip()),
        "asset-resize": lambda v: setattr(s, "asset_resize", _choice(v, {"fit", "contain", "cover"}, "asset-resize")),
        "transition": lambda v: setattr(s, "transition", str(v).strip()),
        "subtitles": lambda v: setattr(s, "subtitles", parse_subtitles(v)),
        "background": lambda v: setattr(s, "background", parse_background(v)),
        "poster-time": lambda v: setattr(s, "poster_time", str(v).strip()),
        "target": lambda v: setattr(s, "target", _choice(v, TARGETS, "target")),
        "fade-in": lambda v: setattr(s, "fade_in", _seconds(v, "fade-in")),
        "fade-out": lambda v: setattr(s, "fade_out", _seconds(v, "fade-out")),
        "loudness": lambda v: setattr(s, "loudness", parse_loudness(v)),
        "image-zoom": lambda v: setattr(s, "image_zoom", parse_zoom(v)),
        "transcript": lambda v: setattr(s, "transcript", parse_switch(v, "transcript")),
        "overlay": lambda v: setattr(s, "overlays", parse_overlays(v)),
    }


HEADER_KEYS = tuple(_header_handlers(Settings()))  # every key a header may hold


def settings_from_header(header: dict[str, Any], warnings: list[str]) -> Settings:
    s = Settings()
    handlers = _header_handlers(s)
    for key, value in header.items():
        handler = handlers.get(key)
        if handler is None:
            warnings.append(f"header: unknown property {key!r} ignored")
            continue
        try:
            handler(value)
        except ConfigError as e:
            raise ConfigError(f"header {key}: {e}") from None
    return s


def parse_switch(value: Any, what: str) -> bool:
    """true/false, yes/no, on/off."""
    text = str(value).strip().lower()
    if text in ("true", "yes", "on"):
        return True
    if text in ("false", "no", "off"):
        return False
    raise ConfigError(f"{what} is true or false, not {value!r}")


LOUDNESS_PRESETS = {"web": -16.0, "broadcast": -23.0}  # streaming norm; EBU R 128


def parse_loudness(value: Any) -> float:
    """`-16`, `web` or `broadcast`: the integrated loudness to bring the finished mix to, in LUFS."""
    text = str(value).strip().lower()
    if text in LOUDNESS_PRESETS:
        return LOUDNESS_PRESETS[text]
    lufs = parse_number(text.removesuffix("lufs").strip(), "loudness")
    if not -70 <= lufs <= -5:
        raise ConfigError(f"loudness {lufs} is outside -70 to -5 LUFS")
    return lufs


def parse_zoom(value: Any) -> float:
    zoom = parse_number(value, "image-zoom")
    if zoom <= 1:
        raise ConfigError(f"image-zoom must be above 1, not {zoom}")
    return zoom


def _seconds(value: Any, what: str) -> float:
    seconds = parse_number(value, what)
    if seconds < 0:
        raise ConfigError(f"{what} can't be negative")
    return seconds


def _choice(value: Any, allowed: set[str], what: str) -> str:
    text = str(value).strip().lower()
    if text not in allowed:
        raise ConfigError(f"invalid {what} {value!r}; expected one of {', '.join(sorted(allowed))}")
    return text
