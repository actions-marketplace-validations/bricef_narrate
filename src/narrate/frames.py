"""Compose still frames and video overlays as HTML, rendered by headless Chromium.

A frame is one page at the output size: the scene image (object-fit does the
cover/contain/fit resizing), the theme backdrop, the text slide and any
callouts. Over a video the same page is rendered with a transparent background
and composited by ffmpeg. Custom `theme: x.css` files are linked in as-is, so
Narakeet themes that style `body`, headings, lists or `.backdrop` apply directly.
"""

from __future__ import annotations

import html
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from markdown_it import MarkdownIt
from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import TextLexer, get_lexer_by_name
from pygments.style import Style
from pygments.token import Comment, Generic, Keyword, Name, Number, Operator, String
from pygments.util import ClassNotFound

OBJECT_POSITION = {
    "center": "50% 50%", "top-left": "0 0", "left": "0 50%", "right": "100% 50%",
    "top": "50% 0", "bottom": "50% 100%",
}
OBJECT_FIT = {"cover": "cover", "contain": "contain", "fit": "fill"}
PLAIN_LANGS = {"", "txt", "text", "plaintext", "plain"}
MARKDOWN_LANGS = {"md", "markdown"}

_md = MarkdownIt("commonmark").enable("strikethrough").enable("table")

# Measured against Narakeet's own renders (narrate #20): a 50 px base with
# browser-default proportions, bold 2em plain slides, sans headings, body text
# in the browser's default serif, code at 1em in a Courier-style face
SANS = '"Helvetica Neue", Helvetica, Arial, "Liberation Sans", "Noto Sans", "DejaVu Sans", sans-serif'
SERIF = '"Times New Roman", Times, "Liberation Serif", "DejaVu Serif", serif'
MONO = '"Courier New", Courier, "Liberation Mono", "DejaVu Sans Mono", monospace'

_BASE_CSS = """
html, body { margin: 0; padding: 0; width: %(w)dpx; height: %(h)dpx; overflow: hidden; }
body { font-family: %(serif)s; font-size: 50px; color: #000; background: #fff; }
body.theme-light { color: #fff; background: #000; }
body.over { color: #fff; }
body.over .slide { text-shadow: 0 2px 8px rgba(0, 0, 0, .75); }
img.media { position: absolute; inset: 0; width: 100%%; height: 100%%; }
/* Narakeet darkens the image under a slide with a backdrop filter (measured: x0.45),
   which a theme's own backdrop-filter replaces outright */
.backdrop { position: absolute; inset: 0; backdrop-filter: brightness(.45); }
body.theme-light .backdrop { backdrop-filter: none; }
/* An overlay has nothing behind it for a filter to act on: darken with a layer */
body.overlay .backdrop { backdrop-filter: none; background: rgba(0, 0, 0, .55); }
body.overlay.theme-light .backdrop { background: none; }
.slide { position: absolute; inset: 0; display: flex; align-items: center; justify-content: center;
         box-sizing: border-box; padding: 5%% 7%%; }
.content { max-width: 100%%; }
/* The slide sets its own 50 px base, as Narakeet's does: a theme's body font-size
   doesn't reach slide text (colour still inherits from body) */
:where(.slide) { font-size: 50px; }
/* :where() keeps these at zero specificity, so a theme's plain `h1 {…}` still wins */
:where(.plain, .md h1, .md h2, .md h3, .md h4) { font-family: %(sans)s; }
:where(.plain) { white-space: pre-wrap; text-align: center; font-weight: bold; font-size: 2em; }
:where(.md) { text-align: center; }
:where(.md h1) { font-size: 2em; margin: .67em 0; }
:where(.md h2) { font-size: 1.5em; margin: .83em 0; }
:where(.md h3) { font-size: 1.17em; margin: 1em 0; }
:where(.md ul, .md ol) { display: inline-block; text-align: left; margin: 1em 0; }
:where(.md li > ul, .md li > ol) { display: block; margin: 0; }
:where(.md p) { margin: 1em 0; }
:where(.code pre) { font-family: %(mono)s; font-size: 1em; text-align: left; margin: 0; white-space: pre; }
.code pre { line-height: normal !important; /* Pygments inlines 125%% */ }
svg.callout { position: absolute; inset: 0; }
"""

_SHRINK_JS = """() => {
  const slide = document.querySelector('.slide');
  if (!slide) return;
  const content = slide.querySelector('.content');
  let size = parseFloat(getComputedStyle(slide).fontSize);
  for (let i = 0; i < 60 && size > 8; i++) {
    if (content.scrollHeight <= slide.clientHeight * 0.92 && content.scrollWidth <= slide.clientWidth) break;
    size *= 0.92;
    slide.style.fontSize = size + 'px';
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


class CodeLight(Style):
    """Narakeet's code colours: dark-red names and numbers, bold black keywords."""

    background_color = "#ffffff"
    styles = {
        Comment: "italic #999988", Keyword: "bold #000000", Keyword.Constant: "#000000",
        Keyword.Type: "#990000", Name.Class: "#990000", Name.Tag: "#990000", Name.Function: "#990000",
        Name.Builtin: "#0086b3", Number: "#990000", String: "#dd1144", Operator: "bold #000000",
        Generic.Deleted: "#990000", Generic.Inserted: "#008800",
    }


class CodeDark(Style):
    """The same palette, lightened for slides over images, videos or the light theme."""

    background_color = "#000000"
    styles = {
        Comment: "italic #bbbbbb", Keyword: "bold #ffffff", Keyword.Constant: "#ffffff",
        Keyword.Type: "#ffab91", Name.Class: "#ffab91", Name.Tag: "#ffab91", Name.Function: "#ffab91",
        Name.Builtin: "#80deea", Number: "#ffab91", String: "#ff8a80", Operator: "bold #ffffff",
        Generic.Deleted: "#ffab91", Generic.Inserted: "#a5d6a7",
    }


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
    formatter = HtmlFormatter(noclasses=True, nobackground=True, style=CodeDark if dark else CodeLight)
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
    classes = [f"theme-{theme}"] + (["over"] if over else []) + (["overlay"] if spec.over_video else [])

    styles = [_BASE_CSS % {"w": width, "h": height, "sans": SANS, "serif": SERIF, "mono": MONO}]
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

    parts = []
    if spec.image is not None:
        parts.append(f'<img class="media" src="{spec.image.resolve().as_uri()}">')
    if spec.slide is not None:
        dark = over or theme == "light"
        size = f' style="font-size: {spec.font_size}px"' if spec.font_size else ""
        slide = f'<div class="slide"{size}>{slide_html(spec.slide, dark)}</div>'
        # Over a still image the slide sits inside the backdrop, which custom
        # themes restyle; Narakeet has no backdrop over videos
        parts.append(f'<div class="backdrop">{slide}</div>' if spec.image is not None or spec.backdrop else slide)
    for i, props in enumerate(spec.callouts):
        parts.append(callout_svg(i, props, width, height))
    return (f"<!doctype html><html><head><meta charset='utf-8'>{head}</head>"
            f"<body class=\"{' '.join(classes)}\">{''.join(parts)}</body></html>")


class FrameRenderer:
    """One headless Chromium page reused for every frame of a build."""

    def __init__(self, width: int, height: int, workdir: Path):
        self.width, self.height, self.workdir = width, height, workdir
        self._count = 0
        self._pw = self._browser = self._page = None
        self._pages: dict[int, Any] = {}  # pages for render blocks, by device scale

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
        self._load(self._page, frame_html(spec, self.width, self.height))
        self._page.evaluate(_SHRINK_JS)
        self._page.screenshot(path=str(out), omit_background=spec.over_video, type="png")
        return out

    def screenshot(self, page_html: str, out: Path, *, scale: int = 1, script: str | None = None,
                   arg: Any = None) -> Any:
        """Any page at the frame size, for render blocks: load it, run `script` (a JS
        function given `arg`), then capture it at `scale` pixels per CSS pixel.
        Returns what the script returned."""
        page = self._render_page(scale)
        self._load(page, page_html)
        result = page.evaluate(script, arg) if script else None
        page.evaluate("document.fonts.ready.then(() => true)")
        page.screenshot(path=str(out), type="png")
        return result

    def evaluate(self, page_html: str, script: str, arg: Any = None) -> Any:
        """Load a page and run `script` on it, without capturing anything."""
        page = self._render_page(1)
        self._load(page, page_html)
        return page.evaluate(script, arg)

    @contextmanager
    def page(self, path: Path, viewport: tuple[int, int], scale: float = 1.0, init_script: str | None = None):
        """An HTML scene loaded in a page of its own, with its clock paused at the start.

        Time in the page moves only when the caller advances it, so timers,
        requestAnimationFrame and Date are deterministic (see pages.py)."""
        context = self._browser.new_context(viewport={"width": viewport[0], "height": viewport[1]},
                                            device_scale_factor=scale)
        try:
            page = context.new_page()
            page.clock.install(time=0)
            page.clock.pause_at(1)  # until now the clock ran in real time; from here it waits for us
            if init_script:
                page.add_init_script(init_script)
            page.goto(path.resolve().as_uri(), wait_until="load")
            page.evaluate("document.fonts.ready.then(() => true)")
            yield page
        finally:
            context.close()

    @contextmanager
    def web(self, viewport: tuple[int, int], scale: float, color_scheme: str = "light",
            credentials: dict[str, str] | None = None):
        """A fresh page for capturing a live web page (render:web): its own viewport,
        pixel density, colour scheme and Basic-auth credentials, no cookies, real time."""
        context = self._browser.new_context(
            viewport={"width": viewport[0], "height": viewport[1]}, device_scale_factor=scale,
            color_scheme=color_scheme, http_credentials=credentials)
        try:
            yield context.new_page()
        finally:
            context.close()

    def _render_page(self, scale: int):
        if scale not in self._pages:
            self._pages[scale] = self._browser.new_page(
                viewport={"width": self.width, "height": self.height}, device_scale_factor=scale)
        return self._pages[scale]

    def _load(self, page, page_html: str) -> None:
        self._count += 1
        page_path = self.workdir / f"frame-{self._count:04d}.html"
        page_path.write_text(page_html, encoding="utf-8")
        page.goto(page_path.as_uri(), wait_until="load")
        page.evaluate("document.fonts.ready.then(() => true)")
