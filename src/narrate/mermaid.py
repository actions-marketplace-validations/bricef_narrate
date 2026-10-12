"""render:mermaid: Mermaid diagrams, drawn by mermaid.js in the build's headless Chromium (#40).

mermaid.js is pinned by version and SHA-256 and downloaded once into the tools
directory, as ffmpeg is; $NARRATE_MERMAID_JS points at another copy (the
container image brings its own). A diagram is drawn as SVG, scaled to fit the
frame, and captured at twice the frame size, so text stays sharp and pan and
zoom have pixels to spare.

Mermaid's own frontmatter keys (title, config, displayMode) pass through to it
unchanged; narrate keeps `background` and `scale` for itself.

The studio draws the same page live in the user's browser (#76): live_page.
"""

from __future__ import annotations

import hashlib
import html
import json
import os
import sys
import tempfile
import threading
import urllib.request
from pathlib import Path

import yaml

from .render import Context, Renderer, RenderError, colour, register
from .script import Render
from .tts import tools_dir

MERMAID_VERSION = "12.1.0"
MERMAID_SHA256 = "6484afc32872a3aa16cac9a76ba1816a1ed4cc870a6593cc2e17757750f518b2"
MERMAID_URL = f"https://cdn.jsdelivr.net/npm/mermaid@{MERMAID_VERSION}/dist/mermaid.min.js"
OWN_SETTINGS = frozenset({"background", "scale"})
MERMAID_SETTINGS = frozenset({"title", "config", "displayMode"})  # Mermaid's frontmatter
MARGIN = 0.9  # a diagram fills at most this share of the frame's width and height
SCALE = 2  # device pixels per CSS pixel in the capture

_lock = threading.Lock()

_DRAW_JS = """async ({text, theme, scale, margin}) => {
  mermaid.initialize({startOnLoad: false, theme, securityLevel: 'strict'});
  try {
    const {svg} = await mermaid.render('diagram', text);
    const box = document.getElementById('diagram-box');
    box.innerHTML = svg;
    const el = box.querySelector('svg');
    const {width, height} = el.viewBox.baseVal;
    const fit = Math.min(innerWidth * margin / width, innerHeight * margin / height) * scale;
    el.removeAttribute('style');  // Mermaid's max-width and background
    el.setAttribute('width', width * fit);
    el.setAttribute('height', height * fit);
    return null;
  } catch (e) {
    return String((e && e.message) || e);
  }
}"""

_PARSE_JS = """async (texts) => {
  mermaid.initialize({startOnLoad: false});
  const problems = [];
  for (const text of texts) {
    try { await mermaid.parse(text); problems.push(null); }
    catch (e) { problems.push(String((e && e.message) || e)); }
  }
  return problems;
}"""


def managed_script() -> Path:
    """Where narrate keeps its own mermaid.js (it may not be downloaded yet)."""
    return tools_dir() / "mermaid" / MERMAID_VERSION / "mermaid.min.js"


def ensure(log=lambda msg: print(msg, file=sys.stderr), opener=urllib.request.urlopen) -> Path:
    """mermaid.js: $NARRATE_MERMAID_JS, else narrate's pinned copy, downloaded on first use."""
    if env := os.environ.get("NARRATE_MERMAID_JS"):
        return Path(env)
    path = managed_script()
    with _lock:
        if path.exists():
            return path
        log(f"downloading mermaid.js {MERMAID_VERSION} (first use only, about 5 MB) …")
        with opener(MERMAID_URL) as resp:
            data = resp.read()
        if hashlib.sha256(data).hexdigest() != MERMAID_SHA256:
            raise RenderError(f"checksum mismatch for mermaid.js {MERMAID_VERSION}; download discarded")
        path.parent.mkdir(parents=True, exist_ok=True)
        part = path.with_suffix(".part")
        part.write_bytes(data)
        part.replace(path)
    return path


def diagram_text(block: Render) -> str:
    """The body, with Mermaid's own frontmatter keys put back in front of it."""
    passthrough = {k: v for k, v in block.settings.items() if k not in OWN_SETTINGS}
    if not passthrough:
        return block.body
    return f"---\n{yaml.safe_dump(passthrough, sort_keys=False, allow_unicode=True)}---\n{block.body}"


def background(block: Render, ctx: Context) -> str:
    """`background`, else the scene's canvas, else the theme's slide background."""
    if "background" in block.settings:
        return colour(block, "background", "#ffffff")
    return ctx.canvas or ("#000000" if ctx.theme == "light" else "#ffffff")


def is_dark(hex_colour: str) -> bool:
    r, g, b = (int(hex_colour[i:i + 2], 16) / 255 for i in (1, 3, 5))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b < 0.4


def _page(script: str, back: str, then: str = "") -> str:
    """The page a diagram is drawn in, loading mermaid.js from `script` (a URL); `then` ends its body."""
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>
html, body {{ margin: 0; width: 100%; height: 100%; overflow: hidden; background: {back}; }}
#diagram-box {{ position: absolute; inset: 0; display: flex; align-items: center; justify-content: center; }}
#diagram-box.error {{ box-sizing: border-box; padding: 6%; color: #f85149; white-space: pre-wrap;
                      font: 2.4vh/1.4 ui-monospace, monospace; align-items: flex-start; justify-content: flex-start; }}
</style><script src="{html.escape(script)}"></script></head>
<body><div id="diagram-box"></div>{then}</body></html>"""


def _arg(block: Render, back: str) -> dict:
    """What _DRAW_JS draws: the diagram, in the theme its background calls for, at its scale."""
    return {"text": diagram_text(block), "theme": "dark" if is_dark(back) else "default",
            "scale": float(block.settings.get("scale", 1)), "margin": MARGIN}


def live_page(block: Render, ctx: Context, script: str) -> str:
    """The page a build draws the diagram in, drawing it as it loads, for the studio's preview (#76):
    the same fit, background and theme, with mermaid.js from `script`. A diagram Mermaid can't parse
    shows its message instead. The page says which it showed in <html data-drawn>."""
    back = background(block, ctx)
    arg = json.dumps(_arg(block, back)).replace("</", "<\\/")
    return _page(script, back, f"""<script>({_DRAW_JS})({arg}).then((error) => {{
  if (error) {{
    for (const stray of document.querySelectorAll('body > :not(#diagram-box):not(script)')) stray.remove();
    const box = document.getElementById('diagram-box');
    box.className = 'error';
    box.textContent = error;
  }}
  document.documentElement.dataset.drawn = error ? 'error' : 'diagram';
}});</script>""")


@register
class Mermaid(Renderer):
    name = "mermaid"
    settings = OWN_SETTINGS | MERMAID_SETTINGS

    def check(self, block: Render) -> list[str]:
        problems = super().check(block)
        if not block.body.strip():
            problems.append("render:mermaid needs a diagram")
        try:
            colour(block, "background", "#ffffff")
        except RenderError as e:
            problems.append(str(e))
        try:
            if float(block.settings.get("scale", 1)) <= 0:
                raise ValueError
        except (TypeError, ValueError):
            problems.append(f"render:mermaid: scale must be a positive number, not {block.settings['scale']!r}")
        if not isinstance(block.settings.get("config", {}), dict):
            problems.append("render:mermaid: config must be a map of Mermaid settings")
        return problems

    def validate(self, blocks: list[Render]) -> list[list[str]]:
        """Mermaid's parser on every diagram, in one headless page, without drawing them."""
        from .frames import FrameRenderer

        with tempfile.TemporaryDirectory(prefix="narrate-check-") as tmp, FrameRenderer(320, 180, Path(tmp)) as frames:
            found = frames.evaluate(_page(ensure().resolve().as_uri(), "#ffffff"), _PARSE_JS,
                                    [diagram_text(b) for b in blocks])
        return [[f"render:mermaid: {problem}"] if problem else [] for problem in found]

    def render(self, block: Render, ctx: Context, out: Path) -> None:
        back = background(block, ctx)
        error = ctx.frames.screenshot(_page(ensure().resolve().as_uri(), back), out, scale=SCALE, script=_DRAW_JS,
                                      arg=_arg(block, back))
        if error:
            raise RenderError(f"render:mermaid: {error}")
