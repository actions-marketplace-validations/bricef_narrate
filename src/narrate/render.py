"""Render blocks: ```render:NAME code blocks that a renderer turns into a picture.

narrate's own extension to the script format (spec §18). The builder renders
every block before planning, then places the output exactly as it would place
`![…](file)`: same timing, fit, pan and zoom, callouts and slides on top.

Outputs are cached by a hash of the renderer, its settings, the body and the
frame, so unchanged blocks aren't rendered again. A cache hit refreshes the
file's modification time, so `narrate cache --prune` removes the least
recently used, as it does for speech.
"""

from __future__ import annotations

import hashlib
import html
import json
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .config import ConfigError, parse_color
from .script import Media, Render
from .tts import cache_dir

if TYPE_CHECKING:
    from .frames import FrameRenderer


class RenderError(Exception):
    def __init__(self, message: str, line: int | None = None):
        super().__init__(message)
        self.line = line


@dataclass
class Context:
    """What a renderer may depend on, besides the block itself."""

    width: int
    height: int
    theme: str  # default | light | path to a .css file
    canvas: str | None
    frames: FrameRenderer | None = None  # the build's Chromium, for renderers that draw HTML


class Renderer:
    name: str
    kind = "image"  # what the output is placed as
    version = 1  # bump when the output for the same input changes, to retire cached files
    settings: frozenset[str] = frozenset()  # the frontmatter keys it takes, besides placement

    def check(self, block: Render) -> list[str]:
        """Problems with the block, found without rendering it."""
        unknown = sorted(set(block.settings) - self.settings)
        return [f"render:{self.name} doesn't take {key!r}" for key in unknown]

    def render(self, block: Render, ctx: Context, out: Path) -> None:
        raise NotImplementedError


RENDERERS: dict[str, Renderer] = {}


def register(cls: type[Renderer]) -> type[Renderer]:
    RENDERERS[cls.name] = cls()
    return cls


def renderer(name: str) -> Renderer:
    try:
        return RENDERERS[name]
    except KeyError:
        known = ", ".join(f"render:{n}" for n in sorted(RENDERERS))
        raise RenderError(f"unknown renderer render:{name} (known: {known})") from None


def check(media: Media) -> list[str]:
    try:
        return renderer(media.render.name).check(media.render)
    except RenderError as e:
        return [str(e)]


def output(media: Media, ctx: Context) -> Path:
    """The rendered file for a render block, from the cache when it's there."""
    r = renderer(media.render.name)
    problems = r.check(media.render)
    if problems:
        raise RenderError("; ".join(problems), media.line)
    key = json.dumps([r.name, r.version, media.render.body, media.render.settings,
                      ctx.width, ctx.height, ctx.theme, ctx.canvas], sort_keys=True, default=str)
    path = cache_dir() / "render" / r.name / f"{hashlib.sha256(key.encode()).hexdigest()[:24]}.png"
    if path.exists():
        path.touch()
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_name(f"{path.stem}.part.png")
    try:
        r.render(media.render, ctx, part)
    except RenderError as e:
        raise RenderError(str(e), e.line or media.line) from None
    part.replace(path)
    return path


def colour(block: Render, key: str, default: str) -> str:
    try:
        return parse_color(block.settings.get(key, default), key)
    except ConfigError as e:
        raise RenderError(f"render:{block.name}: {e}") from None


@register
class Placeholder(Renderer):
    """A card standing in for a picture still to come: the body as its label."""

    name = "placeholder"
    settings = frozenset({"background", "color"})

    def check(self, block: Render) -> list[str]:
        problems = super().check(block)
        for key in ("background", "color"):
            try:
                colour(block, key, "grey")
            except RenderError as e:
                problems.append(str(e))
        return problems

    def render(self, block: Render, ctx: Context, out: Path) -> None:
        w, h = ctx.width, ctx.height
        background, fg = colour(block, "background", "#d9d9d9"), colour(block, "color", "#4d4d4d")
        label = html.escape(block.body.strip()) or "Placeholder"
        size = round(min(w, h) * 0.07)
        page = f"""<!doctype html><html><head><meta charset="utf-8"><style>
html, body {{ margin: 0; width: {w}px; height: {h}px; overflow: hidden; background: {background}; }}
svg {{ position: absolute; inset: 0; }}
.label {{ position: absolute; inset: 0; display: flex; flex-direction: column; align-items: center;
          justify-content: center; text-align: center; padding: 0 12%; box-sizing: border-box;
          color: {fg}; font: bold {size}px/1.25 "Liberation Sans", "DejaVu Sans", sans-serif; }}
.label span {{ background: {background}; padding: .2em .5em; white-space: pre-wrap; }}
.size {{ font-size: .45em; font-weight: normal; opacity: .8; margin-top: .6em; }}
</style></head><body>
<svg width="{w}" height="{h}"><g stroke="{fg}" stroke-opacity=".35" stroke-width="{max(2, w // 400)}" fill="none">
<rect x="0" y="0" width="{w}" height="{h}" stroke-width="{max(4, w // 160)}"/>
<line x1="0" y1="0" x2="{w}" y2="{h}"/><line x1="{w}" y1="0" x2="0" y2="{h}"/></g></svg>
<div class="label"><span>{label}</span><span class="size">{w} × {h}</span></div>
</body></html>"""
        ctx.frames.screenshot(page, out)
