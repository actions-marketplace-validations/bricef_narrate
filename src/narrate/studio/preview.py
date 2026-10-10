"""The studio's frame preview (#53): what's on screen at a moment of a scene.

Composed from the analysis's own scene plan, by the HTML a build uses
(frames.frame_html), with files loaded from the studio's routes instead of
file:// (design D9). A clip shows a still from that moment, a pan or zoom
the crop it has reached, and an HTML scene the page itself, live. A render
block shows the output a build already made, or a card until then.
"""

from __future__ import annotations

import dataclasses
import hashlib
import html
import shutil
from pathlib import Path
from urllib.parse import quote

from PIL import Image

from .. import media, motion, render
from ..build import FPS, ScenePlan
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


def _card(title: str, note: str, w: int, h: int) -> str:
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>
html, body {{ margin: 0; width: {w}px; height: {h}px; background: #1d2127; color: #c9d1d9;
             font: {round(h * 0.05)}px system-ui, sans-serif; display: flex; flex-direction: column;
             align-items: center; justify-content: center; text-align: center; }}
small {{ font-size: .55em; opacity: .7; margin-top: .6em; }}
</style></head><body><div>{html.escape(title)}</div><small>{html.escape(note)}</small></body></html>"""


def frame(plan: ScenePlan, t: float, settings: Settings, files: Files) -> dict:
    """{"kind": "frame", "html": …} composed at `t` seconds into the scene, or {"kind": "page", "url": …}."""
    w, h = settings.width, settings.height
    t = max(0.0, min(t, plan.duration - 1 / FPS))
    spec = plan.spec
    if plan.slides:
        share = plan.duration / len(plan.slides)
        spec = dataclasses.replace(spec, slide=plan.slides[min(len(plan.slides) - 1, int(t / share))])

    visual, into, fraction = None, 0.0, 0.0
    if plan.visuals:
        pieces, total = plan.layout.pieces, sum(plan.layout.pieces)
        moment = t % total if plan.layout.repeat and total > 0 else t
        offset = 0.0
        for v, piece, tempo in zip(plan.visuals, pieces, plan.layout.tempo):
            if moment < offset + piece or v is plan.visuals[-1]:
                visual, into = v, (moment - offset) * tempo
                fraction = min(1.0, max(0.0, (moment - offset) / piece)) if piece else 0.0
                break
            offset += piece

    if visual is None:
        return {"kind": "frame", "html": frame_html(spec, w, h, files.url)}
    if visual.kind == "page":
        return {"kind": "page", "url": files.url(visual.path)}
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
