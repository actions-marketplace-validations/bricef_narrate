"""The studio's frame preview (#53): what's on screen at a moment of a scene.

Composed from the analysis's own scene plan, by the HTML a build uses
(frames.frame_html), with files loaded from the studio's routes instead of
file:// (design D9). A clip shows a still from that moment, a pan or zoom
the crop it has reached, and an HTML scene the page itself, on a clock the
studio moves (#73, D12). A render block shows the output a build already
made, or a card until then.
"""

from __future__ import annotations

import dataclasses
import hashlib
import html
import json
import re
import shutil
from pathlib import Path
from urllib.parse import quote

from PIL import Image

from .. import media, motion, pages, render
from ..build import FPS, ScenePlan, Visual, allocate_frames
from ..config import Settings
from ..frames import frame_html


class Files:
    """Turns files into the addresses the preview loads them from."""

    def __init__(self, project: Path, scratch: Path):
        self.project, self.scratch = project.resolve(), scratch.resolve()

    def url(self, path: Path) -> str:
        path = path.resolve()
        if path.is_relative_to(self.project) and not path.is_relative_to(self.scratch):
            return "/files/" + quote(path.relative_to(self.project).as_posix())
        if not path.is_relative_to(self.scratch):  # a render cache file, outside the project
            copy = self.scratch / f"{hashlib.sha256(str(path).encode()).hexdigest()[:16]}{path.suffix}"
            if not copy.exists():
                shutil.copyfile(path, copy)
            path = copy
        return "/scratch/" + quote(path.name)

    def page(self, path: Path, narrate: dict) -> str | None:
        """Where an HTML scene loads from with what it learns about the narration (`narrate`: duration,
        cues, …), or None outside the project. The address changes with the cues or the file, which
        reloads the page, and stays the same while only the moment changes."""
        path = path.resolve()
        if not path.is_relative_to(self.project) or path.is_relative_to(self.scratch):
            return None
        query = quote(json.dumps(narrate, separators=(",", ":"), sort_keys=True))
        return f"/pages/{quote(path.relative_to(self.project).as_posix())}?v={path.stat().st_mtime_ns}&narrate={query}"


def _card(title: str, note: str, w: int, h: int) -> str:
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>
html, body {{ margin: 0; width: {w}px; height: {h}px; background: #1d2127; color: #c9d1d9;
             font: {round(h * 0.05)}px system-ui, sans-serif; display: flex; flex-direction: column;
             align-items: center; justify-content: center; text-align: center; }}
small {{ font-size: .55em; opacity: .7; margin-top: .6em; }}
</style></head><body><div>{html.escape(title)}</div><small>{html.escape(note)}</small></body></html>"""


def _page_box(v: Visual, w: int, h: int) -> dict:
    """Where a page laid out at its viewport sits in the w×h frame, as a build fits it
    (build._encode_page, _resize_filters): its offset and its scale across and down."""
    vw, vh = v.viewport
    if v.fit == "fit":
        return {"left": 0.0, "top": 0.0, "scale_x": w / vw, "scale_y": h / vh}
    scale = (min if v.fit == "contain" else max)(w / vw, h / vh)
    if v.align:
        ax, ay = v.align
    elif v.fit == "contain":
        ax, ay = 0.5, 0.5
    else:
        ax = {"left": 0.0, "top-left": 0.0, "right": 1.0}.get(v.position, 0.5)
        ay = {"top": 0.0, "top-left": 0.0, "bottom": 1.0}.get(v.position, 0.5)
    return {"left": (w - vw * scale) * ax, "top": (h - vh * scale) * ay, "scale_x": scale, "scale_y": scale}


def _page(plan: ScenePlan, index: int, t: float, into: float, settings: Settings, files: Files) -> dict:
    """An HTML scene at `into` seconds of its own time: the page's address, with the cues a build gives
    it (counted from the frame it starts on), and where it sits in the frame. `start`, when the page
    began in the scene, lets the studio move its clock without asking again."""
    v = plan.visuals[index]
    w, h = settings.width, settings.height
    if plan.layout.repeat:
        counts = [max(1, round(p * FPS)) for p in plan.layout.pieces]
    else:
        counts = allocate_frames(max(1, round(plan.duration * FPS)), plan.layout.pieces)
    first, count = sum(counts[:index]), counts[index]
    narrate = {"duration": round(count / FPS, 4),
               "cues": {k: round(c - first / FPS, 4) for k, c in plan.marks.items()}}
    url = files.page(v.path, narrate)
    if url is None:
        return {"kind": "frame", "html": _card(v.path.name, "outside the project folder: shown once built", w, h)}
    # On screen from its first frame; a looping sequence restarts it on each pass
    start = t - into if plan.layout.repeat else first / FPS
    return {"kind": "page", "url": url, "time": round(max(0.0, t - start), 4), "start": round(start, 4),
            "size": list(v.viewport), "box": _page_box(v, w, h), "canvas": plan.spec.canvas or "#000000"}


# Injected before a page's own scripts; marked so the page's runtime can tell them from the page's
_PAGE_HEAD = """<script data-narrate src="/static/vendor/fake-timers.js"></script>
<script data-narrate>window.__narrateSeek = {seek};
{cues}</script>
<script data-narrate src="/static/page-clock.js"></script>
"""


def page_html(source: str, narrate: dict) -> str:
    """An HTML scene as the preview serves it (#73): the page with a fake clock, the renderer's own
    seeking (pages._SEEK_JS) and the cue script (pages.cue_script) installed before its own scripts,
    and page-clock.js to move the clock when the studio says. Inserted after the doctype, and inside
    the head when the page writes one, so the page keeps its rendering mode."""
    cues = pages.cue_script(float(narrate.get("duration", 0)), {str(k): float(c) for k, c in narrate.get("cues", {}).items()},
                            narrate.get("params"), narrate.get("scenes"))
    head = _PAGE_HEAD.format(seek=pages._SEEK_JS, cues=cues.replace("</", "<\\/"))
    for pattern in (r"<head\b[^>]*>", r"<html\b[^>]*>", r"<!doctype[^>]*>"):
        found = re.search(pattern, source, re.IGNORECASE)
        if found:
            return source[:found.end()] + "\n" + head + source[found.end():]
    return head + source


def frame(plan: ScenePlan, t: float, settings: Settings, files: Files) -> dict:
    """{"kind": "frame", "html": …} composed at `t` seconds into the scene, or {"kind": "page", "url": …}
    for an HTML scene (_page)."""
    w, h = settings.width, settings.height
    t = max(0.0, min(t, plan.duration - 1 / FPS))
    spec = plan.spec
    if plan.slides:
        share = plan.duration / len(plan.slides)
        spec = dataclasses.replace(spec, slide=plan.slides[min(len(plan.slides) - 1, int(t / share))])

    visual, index, into, fraction = None, 0, 0.0, 0.0
    if plan.visuals:
        pieces, total = plan.layout.pieces, sum(plan.layout.pieces)
        moment = t % total if plan.layout.repeat and total > 0 else t
        offset = 0.0
        for index, (v, piece, tempo) in enumerate(zip(plan.visuals, pieces, plan.layout.tempo)):
            if moment < offset + piece or v is plan.visuals[-1]:
                visual, into = v, (moment - offset) * tempo
                fraction = min(1.0, max(0.0, (moment - offset) / piece)) if piece else 0.0
                break
            offset += piece

    if visual is None:
        return {"kind": "frame", "html": frame_html(spec, w, h, files.url)}
    if visual.kind == "page":
        return _page(plan, index, t, max(0.0, into), settings, files)
    spec = dataclasses.replace(spec, fit=visual.fit, position=visual.css_position)
    if visual.kind == "video":
        at = visual.start + min(into, max(0.0, visual.length - 0.05))
        still = files.scratch / f"clip-{hashlib.sha256(f'{visual.path}:{at:.2f}'.encode()).hexdigest()[:16]}.png"
        if not still.exists():
            media.extract_frame(visual.path, at, still)
        return {"kind": "frame", "html": frame_html(dataclasses.replace(spec, image=still), w, h, files.url)}
    image = visual.path
    if image is None and visual.render is not None:  # a render block a build hasn't drawn yet
        ctx = render.Context(w, h, spec.theme, spec.canvas, project=files.project)
        image = render.existing(visual.render, ctx)
        if image is None:
            if visual.render.name == "placeholder":
                return {"kind": "frame", "html": render.renderer("placeholder").page(visual.render, w, h)}
            return {"kind": "frame", "html": _card(f"render:{visual.render.name}", "drawn when the video is built", w, h)}
    if image is None:
        return {"kind": "frame", "html": frame_html(spec, w, h, files.url)}
    spec = dataclasses.replace(spec, image=image)
    if visual.motion:
        with Image.open(image) as im:
            size = im.size
        start, end = motion.endpoints(visual.motion, visual.position, size[0], size[1], w, h, visual.zoom,
                                      visual.focus, visual.windows)
        crop = tuple(a + (b - a) * fraction for a, b in zip(start, end))
        spec = dataclasses.replace(spec, crop=crop, image_size=size)
    return {"kind": "frame", "html": frame_html(spec, w, h, files.url)}
