"""Compose still frames and video overlays as HTML, rendered by headless Chromium.

A frame is one page at the output size: the scene image (object-fit does the
cover/contain/fit resizing), the theme backdrop, the text slide and any
callouts. Over a video the same page is rendered with a transparent background
and composited by ffmpeg. Custom `theme: x.css` files are linked in as-is, so
Narakeet themes that style `body`, headings, lists or `.backdrop` apply directly.
"""

from __future__ import annotations

import html
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from markdown_it import MarkdownIt
from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import TextLexer, get_lexer_by_name
from pygments.util import ClassNotFound

OBJECT_POSITION = {
    "center": "50% 50%", "top-left": "0 0", "left": "0 50%", "right": "100% 50%",
    "top": "50% 0", "bottom": "50% 100%",
}
OBJECT_FIT = {"cover": "cover", "contain": "contain", "fit": "fill"}
PLAIN_LANGS = {"", "txt", "text", "plaintext", "plain"}
MARKDOWN_LANGS = {"md", "markdown"}

_md = MarkdownIt("commonmark").enable("strikethrough").enable("table")

_BASE_CSS = """
html, body { margin: 0; padding: 0; width: %(w)dpx; height: %(h)dpx; overflow: hidden; }
body { font-family: "DejaVu Sans", Arial, sans-serif; font-size: 50px; color: #000; background: #fff; }
body.theme-light { color: #fff; background: #000; }
body.over { color: #fff; }
body.over .slide { text-shadow: 0 2px 8px rgba(0, 0, 0, .75); }
img.media { position: absolute; inset: 0; width: 100%%; height: 100%%; }
.backdrop { position: absolute; inset: 0; background: rgba(0, 0, 0, .45); }
body.theme-light .backdrop { background: none; }
.slide { position: absolute; inset: 0; display: flex; align-items: center; justify-content: center;
         box-sizing: border-box; padding: 5%% 7%%; }
.content { max-width: 100%%; }
.plain { white-space: pre-wrap; text-align: center; }
.md { text-align: center; }
.md ul, .md ol { display: inline-block; text-align: left; margin: .2em 0; }
.md h1 { font-size: 1.5em; margin: .2em 0; }
.md h2 { font-size: 1.2em; margin: .2em 0; }
.md p { margin: .3em 0; }
.code pre { font-family: "DejaVu Sans Mono", monospace; font-size: .85em; text-align: left;
            margin: 0; white-space: pre; line-height: 1.35; }
svg.callout { position: absolute; inset: 0; }
"""

_SHRINK_JS = """() => {
  const slide = document.querySelector('.slide');
  if (!slide) return;
  const content = slide.querySelector('.content');
  let size = parseFloat(getComputedStyle(document.body).fontSize);
  for (let i = 0; i < 60 && size > 8; i++) {
    if (content.scrollHeight <= slide.clientHeight * 0.92 && content.scrollWidth <= slide.clientWidth) break;
    size *= 0.92;
    document.body.style.fontSize = size + 'px';
  }
}"""


@dataclass
class SlideSpec:
    lang: str
    text: str


@dataclass
class FrameSpec:
    image: Path | None = None
    fit: str = "cover"
    position: str = "center"
    canvas: str | None = None
    theme: str = "default"  # default | light | path to a .css file
    slide: SlideSpec | None = None
    font_size: int | None = None
    callouts: list[dict[str, Any]] = field(default_factory=list)
    over_video: bool = False  # transparent overlay for ffmpeg to composite
    backdrop: bool = False  # in an overlay, keep the theme backdrop (over an animated image)


def slide_html(slide: SlideSpec, dark: bool) -> str:
    lang = slide.lang
    if lang in PLAIN_LANGS:
        return f'<div class="content plain">{html.escape(slide.text)}</div>'
    if lang in MARKDOWN_LANGS:
        return f'<div class="content md">{_md.render(slide.text)}</div>'
    try:
        lexer = get_lexer_by_name(lang)
    except ClassNotFound:
        lexer = TextLexer()
    formatter = HtmlFormatter(noclasses=True, nobackground=True, style="monokai" if dark else "default")
    return f'<div class="content code">{highlight(slide.text, lexer, formatter)}</div>'


def callout_svg(index: int, props: dict[str, Any], width: int, height: int) -> str:
    def num(key: str, default: float | None = None) -> float:
        value = props.get(key, default)
        if value is None:
            raise ValueError(f"callout needs {key}")
        return float(value)

    kind = str(props.get("type", "circle")).lower()
    if kind == "rectangle":
        left, top = num("left"), num("top")
        shape = (f'<rect x="{left}" y="{top}" width="{num("right") - left}" '
                 f'height="{num("bottom") - top}" fill="%s"/>')
    elif kind == "circle":
        shape = f'<circle cx="{num("cx")}" cy="{num("cy")}" r="{num("size", 100)}" fill="%s"/>'
    else:
        raise ValueError(f"unknown callout type {kind!r}")
    svg = f'<svg class="callout" width="{width}" height="{height}" xmlns="http://www.w3.org/2000/svg">'
    if str(props.get("style", "")).lower() == "mask":
        return svg + (shape % "#000") + "</svg>"
    alpha = min(1.0, max(0.0, num("alpha", 0.5)))
    return (svg + f'<defs><mask id="m{index}"><rect width="100%" height="100%" fill="white"/>'
            + (shape % "black") + f'</mask></defs><rect width="100%" height="100%" '
            f'fill="rgba(0,0,0,{alpha})" mask="url(#m{index})"/></svg>')


def frame_html(spec: FrameSpec, width: int, height: int) -> str:
    custom_css = spec.theme if spec.theme.endswith(".css") else None
    theme = "light" if spec.theme == "light" else "default"
    over = spec.image is not None or spec.over_video
    classes = [f"theme-{theme}"] + (["over"] if over else [])

    styles = [_BASE_CSS % {"w": width, "h": height}]
    if spec.over_video:
        styles.append("html, body { background: transparent !important; }")
    elif spec.image is not None:
        styles.append(f"body {{ background: {spec.canvas or '#000'}; }}")
    elif spec.canvas:
        styles.append(f"body {{ background: {spec.canvas}; }}")
    if spec.image is not None:
        styles.append(f"img.media {{ object-fit: {OBJECT_FIT[spec.fit]}; "
                      f"object-position: {OBJECT_POSITION[spec.position]}; }}")
    head = f"<style>{''.join(styles)}</style>"
    if custom_css:
        head += f'<link rel="stylesheet" href="{Path(custom_css).resolve().as_uri()}">'

    body_style = f' style="font-size: {spec.font_size}px"' if spec.font_size else ""
    parts = []
    if spec.image is not None:
        parts.append(f'<img class="media" src="{spec.image.resolve().as_uri()}">')
    if spec.slide is not None:
        dark = over or theme == "light"
        slide = f'<div class="slide">{slide_html(spec.slide, dark)}</div>'
        # Over a still image the slide sits inside the backdrop, which custom
        # themes restyle; Narakeet has no backdrop over videos
        parts.append(f'<div class="backdrop">{slide}</div>' if spec.image is not None or spec.backdrop else slide)
    for i, props in enumerate(spec.callouts):
        parts.append(callout_svg(i, props, width, height))
    return (f"<!doctype html><html><head><meta charset='utf-8'>{head}</head>"
            f"<body class=\"{' '.join(classes)}\"{body_style}>{''.join(parts)}</body></html>")


class FrameRenderer:
    """One headless Chromium page reused for every frame of a build."""

    def __init__(self, width: int, height: int, workdir: Path):
        self.width, self.height, self.workdir = width, height, workdir
        self._count = 0
        self._pw = self._browser = self._page = None

    def __enter__(self) -> FrameRenderer:
        from playwright.sync_api import sync_playwright

        from .doctor import launch_chromium

        self._pw = sync_playwright().start()
        try:
            # Pages are file:// URLs that load project images, CSS and fonts from disk
            self._browser = launch_chromium(self._pw, ["--allow-file-access-from-files"])
        except Exception:
            self._pw.stop()
            raise
        self._page = self._browser.new_page(
            viewport={"width": self.width, "height": self.height}, device_scale_factor=1
        )
        return self

    def __exit__(self, *exc: object) -> None:
        if self._browser:
            self._browser.close()
        if self._pw:
            self._pw.stop()

    def render(self, spec: FrameSpec, out: Path) -> Path:
        self._count += 1
        page_path = self.workdir / f"frame-{self._count:04d}.html"
        page_path.write_text(frame_html(spec, self.width, self.height), encoding="utf-8")
        self._page.goto(page_path.as_uri(), wait_until="load")
        self._page.evaluate("document.fonts.ready.then(() => true)")
        self._page.evaluate(_SHRINK_JS)
        self._page.screenshot(path=str(out), omit_background=spec.over_video, type="png")
        return out
