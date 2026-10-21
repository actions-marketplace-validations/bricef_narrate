"""The studio's frame preview (#53): what's on screen at a moment of a scene.

Composed from the analysis's own scene plan, by the HTML a build uses
(frames.frame_html), with files loaded from the studio's routes instead of
file:// (design D9). A clip shows a still from that moment, a pan or zoom
the crop it has reached, and an HTML scene the page itself, on a clock the
studio moves (#73, D12). A render block shows the output a build already
made; until then, a Mermaid diagram is drawn live (#76, D15) and other render
blocks show a card. Overlays go over the frame as pages of their
own (#74, D13). Each is shown in a sandboxed frame (D17).
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

from .. import media, mermaid, motion, pages, render
from ..build import FPS, ScenePlan, Visual, allocate_frames
from ..config import OverlaySpec, Settings
from ..frames import frame_html


# Where the studio serves narrate's own pinned mermaid.js (server.mermaid_js)
MERMAID_JS = f"/mermaid/{mermaid.MERMAID_VERSION}/mermaid.min.js"


class Files:
    """Turns files into the addresses the preview loads them from. The preview's frames are sandboxed
    (D17), so the project's files come from /pages/ with the session's `key`, which lets their fonts
    and fetches read them."""

    def __init__(self, project: Path, scratch: Path, key: str):
        self.project, self.scratch = project.resolve(), scratch.resolve()
        self.root = f"/pages/{quote(key)}/"

    def url(self, path: Path) -> str:
        path = path.resolve()
        if path.is_relative_to(self.project) and not path.is_relative_to(self.scratch):
            url = self.root + quote(path.relative_to(self.project).as_posix())
            if path.is_relative_to(self.project / ".narrate" / "generated"):
                url += f"?v={path.stat().st_mtime_ns}"  # replaced in place when retaken (#77): show the new one
            return url
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
        where = quote(path.relative_to(self.project).as_posix())
        return f"{self.root}{where}?v={path.stat().st_mtime_ns}&narrate={query}"


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


def _timeline(plans: dict[int, ScenePlan]) -> dict[int, tuple[int, int]]:
    """Each scene's first frame in the whole video, and how many frames it has, counted as a build counts them."""
    placed, at = {}, 0
    for index in sorted(plans):
        count = max(1, int(round(at + plans[index].duration * FPS)) - at)
        placed[index], at = (at, count), at + count
    return placed


def _overlay(spec: OverlaySpec, narrate: dict, start: float, t: float, settings: Settings, files: Files) -> dict | None:
    """An overlay page (#59) to lay over the frame: like an HTML scene (_page), on a clock `start` seconds
    behind the scene's, laid out at its viewport and centred as a build lays it (build._capture_overlay)."""
    path = files.project / spec.file
    url = files.page(path, narrate) if path.is_file() else None
    if url is None:  # missing (the analysis says so), or outside the project
        return None
    w, h = settings.width, settings.height
    vw, vh = spec.viewport or (w, h)
    scale = min(w / vw, h / vh)
    return {"url": url, "start": round(start, 4), "time": round(max(0.0, t - start), 4), "size": [vw, vh],
            "box": {"left": float((w - round(vw * scale)) // 2), "top": float((h - round(vh * scale)) // 2),
                    "scale_x": scale, "scale_y": scale}}


def _overlays(plan: ScenePlan, t: float, settings: Settings, files: Files, plans: dict[int, ScenePlan]) -> list[dict]:
    """The overlays over the scene at `t`, in the order a build lays them: the scene's own, on its clock
    with its cues, then the video's that cover it, on the whole video's clock with each scene's start."""
    placed = _timeline(plans)
    first, count = placed.get(plan.index, (0, max(1, round(plan.duration * FPS))))
    shown = [_overlay(spec, {"duration": round(count / FPS, 4), "params": spec.params,
                             "cues": {k: round(c, 4) for k, c in plan.marks.items()}}, 0.0, t, settings, files)
             for spec in plan.overlays]
    if not plan.hide_overlays:
        end = max(a + n for a, n in placed.values()) if placed else count
        scenes = [{"index": i, "start": round(a / FPS, 4), "duration": round(n / FPS, 4)} for i, (a, n) in placed.items()]
        shown += [_overlay(spec, {"duration": round(end / FPS, 4), "cues": {}, "params": spec.params, "scenes": scenes},
                           -first / FPS, t, settings, files)
                  for spec in settings.overlays if spec.scenes is None or spec.scenes[0] <= plan.index <= spec.scenes[1]]
    return [o for o in shown if o is not None]


def frame(plan: ScenePlan, t: float, settings: Settings, files: Files, plans: dict[int, ScenePlan] | None = None) -> dict:
    """What's on screen `t` seconds into the scene: {"kind": "frame", "html": …} composed as a build composes
    it, or {"kind": "page", "url": …} for an HTML scene (_page); with the overlays to lay over it (#74).
    `plans`, every scene's, place the scene in the whole video for the video's overlays."""
    t = max(0.0, min(t, plan.duration - 1 / FPS))
    shown = _picture(plan, t, settings, files)
    shown["overlays"] = _overlays(plan, t, settings, files, plans or {plan.index: plan})
    return shown


def _picture(plan: ScenePlan, t: float, settings: Settings, files: Files) -> dict:
    w, h = settings.width, settings.height
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
            if visual.render.name == "mermaid":  # drawn live by the user's browser, as a build draws it (#76)
                return {"kind": "frame", "html": mermaid.live_page(visual.render, ctx, MERMAID_JS)}
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
