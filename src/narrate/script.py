"""Parse Narakeet-style Markdown video scripts into a header and scenes of blocks.

Implements docs/spec/narakeet-markdown.md §2 (structure), §5 (media references)
and §7 (stage directions), including the lenient forms found in Narakeet's own
example scripts (stacked directives, directives straight after a fence or a
separator). Also narrate's own `render:` code blocks (spec §18), which become
media blocks that the builder renders.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".gif"}
VIDEO_EXT = {".mp4", ".mov", ".m4v", ".webm", ".wmv", ".avi", ".mpeg", ".mpg"}
AUDIO_EXT = {".wav", ".mp3", ".wma", ".aac", ".m4a"}
HTML_EXT = {".html", ".htm"}  # animated HTML scenes, a narrate extension (spec §18)

SIZES = {"fit", "contain", "cover"}
ANIMATED_SIZES = {"zoom", "zoomout", "pan", "panzoom", "panzoomout"}
POSITIONS = {"center", "top-left", "left", "right", "top", "bottom"}
SYNCS = {"freeze", "match", "trim", "loop", "trim-or-loop", "loop-audio"}
# Frontmatter keys of a render block that place its output, as in (image: …) / (video: …)
PLACEMENT = {"size", "position", "sync", "segment", "volume", "zoom", "from", "to"}
# Free framing (narrate extension, #63): a focal point "X% Y%", and pan/zoom windows "X% Y% ZOOM"
_FOCUS_RE = re.compile(r"^(\d+(?:\.\d+)?)%\s+(\d+(?:\.\d+)?)%$")
_WINDOW_RE = re.compile(r"^(\d+(?:\.\d+)?)%\s+(\d+(?:\.\d+)?)%(?:\s+(\d+(?:\.\d+)?))?$")

DIRECTIVES = {
    "audio", "callout", "canvas", "duration", "font-size", "html", "image", "image-size",
    "image-position", "narration-mode", "narration-language", "overlay", "pause", "pause-until",
    "theme", "transition", "video", "voice", "voice-emphasis", "voice-pitch",
    "voice-speed", "voice-volume",
}

_TIME = r"\d+(?::\d{1,2}){0,2}(?:\.\d+)?"
_SEGMENT_RE = re.compile(rf"^(start|end|{_TIME})(?:-(start|end|{_TIME}))?$")
_SEPARATOR_RE = re.compile(r"^ {0,3}-{3,}\s*$")
_FENCE_RE = re.compile(r"^( {0,3})(`{3,}|~{3,})(.*)$")
_IMAGE_RE = re.compile(r'^\s*!\[([^\]]*)\]\(\s*(<[^>]*>|[^)\s]+)(?:\s+"[^"]*")?\s*\)\s*$')
_DIRECTIVE_LINE_RE = re.compile(r"^\s*\(\s*([A-Za-z][\w -]*?)\s*:.*\)\s*$")
_DIRECTIVE_OPEN_RE = re.compile(r"^\s*\(\s*([A-Za-z][\w-]*)\s*:\s*$")


class ScriptError(Exception):
    def __init__(self, message: str, line: int | None = None):
        super().__init__(message)
        self.line = line


@dataclass
class Directive:
    key: str
    value: Any
    line: int


@dataclass
class Render:
    """What a `render:NAME` code block asks for; the builder turns it into a file."""

    name: str  # the renderer, e.g. "mermaid"
    body: str
    settings: dict[str, Any] = field(default_factory=dict)  # frontmatter keys the renderer owns


@dataclass
class Media:
    kind: str  # "image" | "video" | "audio"
    path: str  # for a render block, empty until the builder renders it
    line: int
    size: str | None = None
    position: str | None = None
    sync: str | None = None
    # (start, end) as written; end is None for a single still frame
    segment: tuple[str, str | None] | None = None
    volume: float | None = None
    render: Render | None = None
    viewport: str | None = None  # an HTML scene's design size, as written ("1280x720")
    zoom: float | None = None  # how far pan and zoom move (narrate extension, #49)
    focus: tuple[float, float] | None = None  # a focal point, fractions of the picture (#63)
    windows: tuple[tuple[float, float, float] | None, tuple[float, float, float] | None] | None = None  # from, to


@dataclass
class Slide:
    lang: str
    text: str
    line: int


@dataclass
class Quote:
    text: str  # empty for a lone ">", which suppresses subtitles for the scene
    line: int


@dataclass
class Narration:
    text: str
    line: int
    ssml: bool = False


Block = Directive | Media | Slide | Quote | Narration


@dataclass
class Scene:
    index: int
    line: int
    blocks: list[Block] = field(default_factory=list)


@dataclass
class Script:
    path: Path
    header: dict[str, Any]
    scenes: list[Scene]
    warnings: list[str] = field(default_factory=list)

    @property
    def base_dir(self) -> Path:
        return self.path.parent


def parse_file(path: str | Path) -> Script:
    path = Path(path)
    return parse(path.read_text(encoding="utf-8-sig"), path)


def parse(text: str, path: str | Path = "script.md") -> Script:
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    stripped = _strip_comments(lines)
    warnings: list[str] = []
    header, body_start = _parse_header(stripped)
    scenes: list[Scene] = []
    for chunk in _split_scenes(stripped, body_start):
        blocks = _parse_blocks(chunk, warnings)
        if blocks:
            scenes.append(Scene(index=len(scenes) + 1, line=chunk[0][0], blocks=blocks))
    return Script(path=Path(path), header=header, scenes=scenes, warnings=warnings)


# A line is None when a comment consumed all of it, so it neither carries
# content nor separates paragraphs.
Line = tuple[int, str | None]


def _closes(fence: str, line: str) -> bool:
    m = _FENCE_RE.match(line)
    return bool(m and m.group(2)[0] == fence[0] and len(m.group(2)) >= len(fence) and not m.group(3).strip())


def _strip_comments(lines: list[str]) -> list[str | None]:
    out: list[str | None] = []
    in_comment = False
    fence: str | None = None
    for line in lines:
        if not in_comment:
            if fence:
                if _closes(fence, line):
                    fence = None
                out.append(line)
                continue
            m = _FENCE_RE.match(line)
            if m:
                fence = m.group(2)
                out.append(line)
                continue
        kept: list[str] = []
        rest = line
        touched = False
        while True:
            if in_comment:
                end = rest.find("-->")
                touched = True
                if end < 0:
                    break
                rest = rest[end + 3:]
                in_comment = False
            else:
                start = rest.find("<!--")
                if start < 0:
                    kept.append(rest)
                    break
                kept.append(rest[:start])
                rest = rest[start + 4:]
                in_comment = True
                touched = True
        joined = "".join(kept)
        out.append(None if touched and not joined.strip() else joined)
    return out


def _parse_header(lines: list[str | None]) -> tuple[dict[str, Any], int]:
    first = next((i for i, line in enumerate(lines) if line is not None and line.strip()), None)
    if first is None or not _SEPARATOR_RE.match(lines[first] or ""):
        return {}, 0
    for end in range(first + 1, len(lines)):
        line = lines[end]
        if line is not None and _SEPARATOR_RE.match(line):
            break
    else:
        raise ScriptError("script header is not closed with ---", first + 1)
    text = "\n".join(line for line in lines[first + 1:end] if line is not None)
    try:
        # BaseLoader keeps every scalar a string: no YAML 1.1 surprises such as
        # `no` -> False or `1:20` -> 80; values are typed by their consumers.
        data = yaml.load(text, Loader=yaml.BaseLoader) if text.strip() else {}
    except yaml.YAMLError as e:
        raise ScriptError(f"invalid YAML in script header: {e}", first + 1) from e
    if not isinstance(data, dict):
        # Not a header after all: the leading --- just separates nothing
        return {}, first + 1
    return {str(k).strip().lower(): v for k, v in data.items()}, end + 1


def _split_scenes(lines: list[str | None], start: int) -> list[list[Line]]:
    chunks: list[list[Line]] = [[]]
    fence: str | None = None
    for i in range(start, len(lines)):
        line = lines[i]
        n = i + 1
        if line is None:
            chunks[-1].append((n, None))
            continue
        if fence:
            if _closes(fence, line):
                fence = None
        elif (m := _FENCE_RE.match(line)):
            fence = m.group(2)
        elif _SEPARATOR_RE.match(line):
            chunks.append([])
            continue
        chunks[-1].append((n, line))
    return [c for c in chunks if c]


def _parse_blocks(chunk: list[Line], warnings: list[str]) -> list[Block]:
    blocks: list[Block] = []
    para: list[tuple[int, str]] = []

    def flush() -> None:
        if para:
            blocks.extend(_paragraph(para, warnings))
            para.clear()

    i = 0
    while i < len(chunk):
        n, line = chunk[i]
        if line is None:
            i += 1
            continue
        if not line.strip():
            flush()
            i += 1
            continue

        if (m := _FENCE_RE.match(line)):
            flush()
            fence, info, indent = m.group(2), m.group(3).strip(), len(m.group(1))
            body: list[str] = []
            i += 1
            while i < len(chunk) and not (chunk[i][1] is not None and _closes(fence, chunk[i][1])):
                text = chunk[i][1] or ""
                pad = len(text) - len(text.lstrip(" "))
                body.append(text[min(indent, pad):])
                i += 1
            if i >= len(chunk):
                warnings.append(f"line {n}: code fence is never closed")
            lang = info.split()[0].lower() if info else ""
            if lang.startswith("render:"):
                blocks.append(_render_block(info.split(), body, n, warnings))
            else:
                blocks.append(Slide(lang=lang, text="\n".join(body), line=n))
            i += 1
            continue

        if line.lstrip().startswith(">"):
            flush()
            quote: list[str] = []
            while i < len(chunk) and chunk[i][1] is not None and chunk[i][1].lstrip().startswith(">"):
                quote.append(re.sub(r"^\s*> ?", "", chunk[i][1]).rstrip())
                i += 1
            blocks.append(Quote(text="\n".join(quote).strip(), line=n))
            continue

        if line.lstrip().startswith("<speak"):
            flush()
            ssml = [line]
            while "</speak>" not in ssml[-1] and i + 1 < len(chunk):
                i += 1
                ssml.append(chunk[i][1] or "")
            blocks.append(Narration(text="\n".join(ssml).strip(), line=n, ssml=True))
            i += 1
            continue

        if _DIRECTIVE_LINE_RE.match(line) or _DIRECTIVE_OPEN_RE.match(line):
            text_lines = [line]
            j = i
            if not line.rstrip().endswith(")"):
                # Multi-line form: "(key:" then indented YAML up to a line ending in ")"
                j += 1
                while j < len(chunk):
                    nxt = chunk[j][1]
                    if nxt is not None:
                        if not nxt.strip():
                            break
                        text_lines.append(nxt)
                        if nxt.rstrip().endswith(")"):
                            break
                    j += 1
                if not text_lines[-1].rstrip().endswith(")"):
                    para.append((n, line))  # never closed: plain narration
                    i += 1
                    continue
            parsed = _directive(text_lines, n, warnings)
            if parsed is not None:
                flush()
                blocks.extend(parsed)
                i = j + 1
                continue

        para.append((n, line))
        i += 1

    flush()
    return blocks


def _paragraph(lines: list[tuple[int, str]], warnings: list[str]) -> list[Block]:
    out: list[Block] = []
    text: list[tuple[int, str]] = []

    def emit_text() -> None:
        if text:
            out.append(Narration(text=" ".join(t.strip() for _, t in text), line=text[0][0]))
            text.clear()

    for n, line in lines:
        m = _IMAGE_RE.match(line)
        media = _media_from_alt(m.group(1), m.group(2), n, warnings) if m else None
        if media is None:
            text.append((n, line))
            continue
        emit_text()
        out.append(media)
    emit_text()
    return out


def media_kind(path: str) -> str | None:
    ext = Path(path).suffix.lower()
    if ext in IMAGE_EXT:
        return "image"
    if ext in VIDEO_EXT:
        return "video"
    if ext in AUDIO_EXT:
        return "audio"
    if ext in HTML_EXT:
        return "html"
    return None


def parse_focus(value: str) -> tuple[float, float] | None:
    """A focal point written "70% 25%", as fractions of the picture; None if it isn't one."""
    m = _FOCUS_RE.match(value.strip())
    if not m or float(m.group(1)) > 100 or float(m.group(2)) > 100:
        return None
    return float(m.group(1)) / 100, float(m.group(2)) / 100


def parse_window(value: str) -> tuple[float, float, float] | None:
    """A pan/zoom window written "72% 30% 2.5": its centre, as fractions of the picture, and its zoom
    (1, the default, is the plain cover framing). None if it isn't one."""
    m = _WINDOW_RE.match(value.strip())
    if not m or float(m.group(1)) > 100 or float(m.group(2)) > 100:
        return None
    zoom = float(m.group(3)) if m.group(3) else 1.0
    if zoom < 1:
        return None
    return float(m.group(1)) / 100, float(m.group(2)) / 100, zoom


def _segment(value: str) -> tuple[str, str | None] | None:
    m = _SEGMENT_RE.match(value.replace(" ", ""))
    return (m.group(1), m.group(2)) if m else None


def _media_from_alt(alt: str, target: str, line: int, warnings: list[str]) -> Media | None:
    path = target.strip("<>").strip()
    kind = media_kind(path)
    if kind is None:
        warnings.append(f"line {line}: unsupported media type for {path!r}, read as narration")
        return None
    media = Media(kind=kind, path=path, line=line)
    _apply_tokens(media, alt.split(), line, warnings)
    return media


def _apply_tokens(media: Media, tokens: list[str], line: int, warnings: list[str]) -> None:
    """Options written as words, as in an image's alt text."""
    for token in tokens:
        t = token.lower()
        if t in SIZES or t in ANIMATED_SIZES:
            media.size = t
        elif t in POSITIONS:
            media.position = t
        elif t in SYNCS:
            media.sync = t
        elif t == "mute":
            media.volume = 0.0
        elif (seg := _segment(t)):
            media.segment = seg
        else:
            warnings.append(f"line {line}: unknown media option {token!r} ignored")


def _media_from_directive(key: str, value: Any, line: int, warnings: list[str]) -> Media | None:
    if isinstance(value, str):
        props: dict[str, Any] = {"file": value}
    elif isinstance(value, dict):
        props = {str(k).lower(): v for k, v in value.items()}
    else:
        warnings.append(f"line {line}: ({key}: …) needs a file name")
        return None
    path = str(props.pop("file", "")).strip()
    if not path:
        warnings.append(f"line {line}: ({key}: …) has no file")
        return None
    media = Media(kind=key, path=path, line=line)
    _apply_props(media, props, key, line, warnings)
    return media


def _apply_props(media: Media, props: dict[str, Any], what: str, line: int, warnings: list[str]) -> None:
    """Options written as a map, as in (image: {file: …, size: …})."""
    for prop, raw in props.items():
        val = str(raw).strip()
        low = val.lower()
        if prop == "size" and low in SIZES | ANIMATED_SIZES:
            media.size = low
        elif prop == "position" and low in POSITIONS:
            media.position = low
        elif prop == "position" and (focus := parse_focus(low)):
            media.focus = focus
        elif prop in ("from", "to") and (window := parse_window(low)):
            start, end = media.windows or (None, None)
            media.windows = (window, end) if prop == "from" else (start, window)
        elif prop == "sync" and low in SYNCS:
            media.sync = low
        elif prop == "segment" and (seg := _segment(low)):
            media.segment = seg
        elif prop == "viewport" and media.kind == "html":
            media.viewport = val
        elif prop == "zoom":
            try:
                if float(val) <= 1:
                    raise ValueError
                media.zoom = float(val)
            except ValueError:
                warnings.append(f"line {line}: zoom must be a number above 1, not {val!r}; ignored")
        elif prop == "volume":
            try:
                media.volume = 0.0 if low == "mute" else float(val)
            except ValueError:
                warnings.append(f"line {line}: invalid volume {val!r} ignored")
        else:
            warnings.append(f"line {line}: unknown or invalid {what} property {prop}: {val!r} ignored")


def _render_block(info: list[str], body: list[str], line: int, warnings: list[str]) -> Media:
    """A ```render:NAME [tokens] block, with optional YAML frontmatter between --- lines."""
    name = info[0][len("render:"):].lower()
    if not name:
        raise ScriptError("a render block needs a renderer, as in ```render:mermaid", line)
    settings: dict[str, Any] = {}
    if body and body[0].strip() == "---":
        end = next((k for k in range(1, len(body)) if body[k].strip() == "---"), None)
        if end is None:
            raise ScriptError("render block frontmatter is not closed with ---", line + 1)
        text = "\n".join(body[1:end])
        try:
            # Typed YAML, unlike the header: renderer settings pass through to
            # tools such as Mermaid, whose numbers and booleans must survive
            data = yaml.safe_load(text) if text.strip() else {}
        except yaml.YAMLError as e:
            raise ScriptError(f"invalid YAML in render block frontmatter: {e}", line + 1) from None
        if not isinstance(data, dict):
            raise ScriptError("render block frontmatter must be a map of key: value lines", line + 1)
        # Key case is kept: renderer settings such as Mermaid's displayMode are camelCase
        settings = {str(k).strip(): v for k, v in data.items()}
        body = body[end + 1:]
    media = Media(kind="image", path="", line=line)
    _apply_tokens(media, info[1:], line, warnings)
    placement = {k.lower(): settings.pop(k) for k in list(settings) if k.lower() in PLACEMENT}
    _apply_props(media, placement, f"render:{name}", line, warnings)
    media.render = Render(name, "\n".join(body).strip("\n"), settings)
    return media


def _directive(text_lines: list[str], line: int, warnings: list[str]) -> list[Block] | None:
    """Parse "(key: value)" text into blocks, or None if it is not a directive after all."""
    raw = "\n".join(text_lines).strip()
    inner = raw[1:-1]
    try:
        data = yaml.load(inner, Loader=yaml.BaseLoader)
    except yaml.YAMLError:
        return None
    if not isinstance(data, dict) or len(data) != 1:
        return None
    (key, value), = data.items()
    key = str(key).strip().lower()
    if " " in key:
        normal = key.replace(" ", "-")
        if normal not in DIRECTIVES:
            return None  # a parenthetical remark such as "(As noted: …)"
        warnings.append(f"line {line}: write ({key}: …) as ({normal}: …)")
        key = normal
    if key not in DIRECTIVES:
        if key != key.lower() or not re.fullmatch(r"[a-z][a-z-]*", key):
            return None
        warnings.append(f"line {line}: unknown stage direction ({key}: …) ignored")
        return []
    if key in ("image", "video", "audio", "html"):
        media = _media_from_directive(key, value, line, warnings)
        return [media] if media else []
    if isinstance(value, str):
        value = value.strip()
    return [Directive(key=key, value=value, line=line)]
