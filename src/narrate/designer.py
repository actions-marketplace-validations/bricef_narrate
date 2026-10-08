"""`narrate callouts`: a page for placing callouts on a frame exactly as narrate renders it.

Callout coordinates are output-frame pixels, which depend on the frame size and
on how the image is fitted. The page shows the composed frame (rendered by the
same code as a build) under an SVG whose viewBox is the frame in pixels, so a
shape drawn on it maps one to one onto the `(callout: …)` direction it prints.
"""

from __future__ import annotations

import base64
import html
import tempfile
from pathlib import Path

from . import media
from .frames import FrameRenderer, FrameSpec
from .script import media_kind

PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Callout designer</title>
<style>
:root { --bg: #f6f6f4; --fg: #1d1d1f; --panel: #ffffff; --line: #d8d8d4; --accent: #2f6fdd; }
@media (prefers-color-scheme: dark) {
  :root { --bg: #17181a; --fg: #ececec; --panel: #222326; --line: #3a3b3f; --accent: #6f9cf0; }
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--fg); font: 15px/1.45 system-ui, sans-serif; }
main { max-width: 1100px; margin: 0 auto; padding: 16px; }
h1 { font-size: 18px; margin: 0 0 4px; }
p.hint { margin: 0 0 12px; opacity: .75; }
.stage { position: relative; border: 1px solid var(--line); background: #000; line-height: 0; }
.stage img, .stage svg { width: 100%%; height: auto; display: block; }
.stage svg { position: absolute; inset: 0; height: 100%%; cursor: crosshair; touch-action: none; }
.controls { display: flex; flex-wrap: wrap; gap: 12px 20px; align-items: center; margin: 12px 0; }
.controls label { display: flex; gap: 6px; align-items: center; }
textarea { width: 100%%; height: 9.5em; font: 14px/1.4 ui-monospace, monospace; background: var(--panel);
           color: var(--fg); border: 1px solid var(--line); border-radius: 6px; padding: 8px; }
button { background: var(--accent); color: #fff; border: 0; border-radius: 6px; padding: 6px 14px; font: inherit; cursor: pointer; }
</style></head>
<body><main>
<h1>Callout designer</h1>
<p class="hint">%(caption)s Drag on the frame to draw a callout, drag inside it to move it, then copy the direction into your script.</p>
<div class="stage">
  <img src="data:image/png;base64,%(png)s" width="%(w)d" height="%(h)d" alt="The frame as narrate renders it">
  <svg id="svg" viewBox="0 0 %(w)d %(h)d" xmlns="http://www.w3.org/2000/svg">
    <defs><mask id="hole"><rect width="100%%" height="100%%" fill="white"/><g id="hole-shape"></g></mask></defs>
    <rect id="shade" width="100%%" height="100%%" fill="black" mask="url(#hole)" opacity="0.5"/>
    <g id="shape"></g>
  </svg>
</div>
<div class="controls">
  <label><input type="radio" name="type" value="circle" checked> Circle</label>
  <label><input type="radio" name="type" value="rectangle"> Rectangle</label>
  <label><input type="checkbox" id="mask"> Mask (hide the area)</label>
  <label>Shading <input type="range" id="alpha" min="0" max="1" step="0.05" value="0.5"> <span id="alpha-value">0.5</span></label>
  <button id="copy" type="button">Copy direction</button>
</div>
<textarea id="out" readonly spellcheck="false"></textarea>
</main>
<script>
const W = %(w)d, H = %(h)d, svg = document.getElementById("svg");
let shape = {type: "circle", cx: W / 2, cy: H / 2, size: 100};
let drag = null;

function point(event) {
  const p = svg.createSVGPoint();
  p.x = event.clientX; p.y = event.clientY;
  const q = p.matrixTransform(svg.getScreenCTM().inverse());
  return {x: Math.max(0, Math.min(W, q.x)), y: Math.max(0, Math.min(H, q.y))};
}

function inside(p) {
  if (shape.type === "circle") return Math.hypot(p.x - shape.cx, p.y - shape.cy) <= shape.size;
  return p.x >= shape.left && p.x <= shape.right && p.y >= shape.top && p.y <= shape.bottom;
}

function element() {
  if (shape.type === "circle") return `<circle cx="${shape.cx}" cy="${shape.cy}" r="${shape.size}"/>`;
  return `<rect x="${shape.left}" y="${shape.top}" width="${shape.right - shape.left}" height="${shape.bottom - shape.top}"/>`;
}

function directive() {
  const lines = ["(callout:"];
  if (shape.type === "circle") {
    lines.push(`  cx: ${Math.round(shape.cx)}`, `  cy: ${Math.round(shape.cy)}`, `  size: ${Math.round(shape.size)}`);
  } else {
    lines.push("  type: rectangle", `  left: ${Math.round(shape.left)}`, `  top: ${Math.round(shape.top)}`,
               `  right: ${Math.round(shape.right)}`, `  bottom: ${Math.round(shape.bottom)}`);
  }
  if (document.getElementById("mask").checked) lines.push("  style: mask");
  const alpha = Number(document.getElementById("alpha").value);
  if (!document.getElementById("mask").checked && alpha !== 0.5) lines.push(`  alpha: ${alpha}`);
  return lines.join("\\n") + ")";
}

function draw() {
  const masked = document.getElementById("mask").checked;
  const alpha = document.getElementById("alpha").value;
  document.getElementById("alpha-value").textContent = alpha;
  document.getElementById("shade").setAttribute("opacity", masked ? 0 : alpha);
  document.getElementById("hole-shape").innerHTML = element().replace("/>", ' fill="black"/>');
  document.getElementById("shape").innerHTML = element().replace("/>",
    masked ? ' fill="black"/>' : ' fill="none" stroke="#ffd166" stroke-width="3" stroke-dasharray="10 6"/>');
  document.getElementById("out").value = directive();
}

svg.addEventListener("pointerdown", event => {
  const p = point(event);
  svg.setPointerCapture(event.pointerId);
  const type = document.querySelector("input[name=type]:checked").value;
  if (type === shape.type && inside(p)) {
    drag = {mode: "move", from: p, start: {...shape}};
  } else {
    drag = {mode: "draw", from: p};
    shape = type === "circle" ? {type, cx: p.x, cy: p.y, size: 4}
                              : {type, left: p.x, top: p.y, right: p.x + 4, bottom: p.y + 4};
  }
  draw();
});
svg.addEventListener("pointermove", event => {
  if (!drag) return;
  const p = point(event), dx = p.x - drag.from.x, dy = p.y - drag.from.y;
  if (drag.mode === "move") {
    const s = drag.start;
    shape = s.type === "circle" ? {...s, cx: s.cx + dx, cy: s.cy + dy}
                                : {...s, left: s.left + dx, right: s.right + dx, top: s.top + dy, bottom: s.bottom + dy};
  } else if (shape.type === "circle") {
    shape.size = Math.max(4, Math.hypot(dx, dy));
  } else {
    Object.assign(shape, {left: Math.min(drag.from.x, p.x), right: Math.max(drag.from.x, p.x),
                          top: Math.min(drag.from.y, p.y), bottom: Math.max(drag.from.y, p.y)});
  }
  draw();
});
svg.addEventListener("pointerup", () => { drag = null; });
document.querySelectorAll("input").forEach(input => input.addEventListener("input", draw));
document.getElementById("copy").addEventListener("click", async () => {
  try { await navigator.clipboard.writeText(directive()); } catch { document.getElementById("out").select(); }
});
draw();
</script></body></html>
"""


def designer_page(source: Path, out: Path, *, width: int, height: int, fit: str = "cover",
                  position: str = "center", at: float = 0.0, canvas: str | None = None) -> Path:
    """Write the designer page for an image (or a video frame) as narrate would frame it."""
    with tempfile.TemporaryDirectory(prefix="narrate-callouts-") as tmp:
        work = Path(tmp)
        image = source
        if media_kind(str(source)) == "video":
            image = media.extract_frame(source, at, work / "frame.png")
        with FrameRenderer(width, height, work) as renderer:
            png = renderer.render(FrameSpec(image=image.resolve(), fit=fit, position=position, canvas=canvas),
                                  work / "composed.png")
        caption = (f"{source.name} at {width}×{height}, {fit}"
                   + (f", {position}" if fit == "cover" and position != "center" else "")
                   + (f", frame at {at:g} s" if image is not source else "") + ".")
        out.write_text(PAGE % {"png": base64.b64encode(png.read_bytes()).decode(), "w": width, "h": height,
                               "caption": html.escape(caption)}, encoding="utf-8")
    return out
