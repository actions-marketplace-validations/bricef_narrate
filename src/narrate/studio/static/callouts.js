// Callouts on the preview (#64): drawn, selected, moved and resized over the frame, in frame pixels,
// as the callout designer does. Each change is an edit to a (callout: …) direction.
import { html, useRef, useState } from "./vendor/htm-preact.js";

const MIN = 6;  // frame pixels: smaller drags are clicks, not shapes

const round = (props) => Object.fromEntries(Object.entries(props).map(([k, v]) => [k, typeof v === "number" ? Math.round(v) : v]));

/** A rectangle's corners, whichever way it was dragged. */
function box(a, b) {
  return { left: Math.min(a[0], b[0]), top: Math.min(a[1], b[1]), right: Math.max(a[0], b[0]), bottom: Math.max(a[1], b[1]) };
}

/** Geometry moved by (dx, dy), or resized by dragging handle `handle` to `p`. */
function reshaped(c, mode, p) {
  if (mode.kind === "move") {
    const [dx, dy] = [p[0] - mode.from[0], p[1] - mode.from[1]];
    return c.type === "circle"
      ? { cx: c.cx + dx, cy: c.cy + dy }
      : { left: c.left + dx, top: c.top + dy, right: c.right + dx, bottom: c.bottom + dy };
  }
  if (c.type === "circle") return { size: Math.max(MIN, Math.hypot(p[0] - c.cx, p[1] - c.cy)) };
  // The corner dragged follows the pointer; the opposite one stays
  const opposite = { nw: [c.right, c.bottom], ne: [c.left, c.bottom], sw: [c.right, c.top], se: [c.left, c.top] }[mode.handle];
  return box(opposite, p);
}

/** The geometry of one callout as an SVG shape. */
function Shape({ c, className, onPointerDown }) {
  return c.type === "circle"
    ? html`<circle cx=${c.cx} cy=${c.cy} r=${c.size} class=${className} onPointerDown=${onPointerDown} />`
    : html`<rect x=${c.left} y=${c.top} width=${c.right - c.left} height=${c.bottom - c.top} class=${className}
        onPointerDown=${onPointerDown} />`;
}

function Handles({ c, start, r }) {
  const points = c.type === "circle"
    ? [["r", c.cx + c.size, c.cy]]
    : [["nw", c.left, c.top], ["ne", c.right, c.top], ["sw", c.left, c.bottom], ["se", c.right, c.bottom]];
  return points.map(([handle, x, y]) => html`<circle cx=${x} cy=${y} r=${r} class="callout-handle" data-handle=${handle}
    onPointerDown=${(e) => start(e, { kind: "resize", handle })} />`);
}

/** The scene's callouts over the preview. `tool` ("circle" or "rectangle") draws a new one. */
export function CalloutLayer({ callouts, frame, tool, selected, onDraw, onChange, onSelect }) {
  const svg = useRef(null);
  const mode = useRef(null);
  const [draft, setDraftState] = useState(null);  // {line, geometry} while dragging
  const setDraft = setDraftState;
  const [w, h] = frame;
  const toFrame = (e) => {
    const r = svg.current.getBoundingClientRect();
    return [Math.min(Math.max((e.clientX - r.left) / r.width, 0), 1) * w, Math.min(Math.max((e.clientY - r.top) / r.height, 0), 1) * h];
  };
  const start = (e, next) => {
    if (e.button !== 0) return;
    e.stopPropagation();
    e.preventDefault();  // no text selection or native drag, which would cancel the pointer
    svg.current.setPointerCapture(e.pointerId);
    mode.current = { ...next, from: toFrame(e) };
  };
  /** Where the drag has got to: the shape being drawn, or the callout moved or resized. */
  const track = (e) => {
    const m = mode.current;
    const p = toFrame(e);
    if (m.kind === "draw") {
      const geometry = tool === "circle"
        ? { type: "circle", cx: m.from[0], cy: m.from[1], size: Math.hypot(p[0] - m.from[0], p[1] - m.from[1]) }
        : { type: "rectangle", ...box(m.from, p) };
      return { line: null, geometry };
    }
    const c = callouts.find((x) => x.line === m.line);
    return { line: m.line, geometry: { ...c, ...reshaped(c, m, p) }, moved: Math.hypot(p[0] - m.from[0], p[1] - m.from[1]) > 1 };
  };
  const onPointerMove = (e) => { if (mode.current) setDraft(track(e)); };
  const onPointerUp = (e) => {
    const m = mode.current;
    // The release says where the pointer ended: moves before it may have been coalesced away
    const done = m && e.type === "pointerup" ? track(e) : null;
    mode.current = null;
    setDraft(null);
    if (!done) return;
    const g = done.geometry;
    if (m.kind === "draw") {
      const big = g.type === "circle" ? g.size >= MIN : g.right - g.left >= MIN && g.bottom - g.top >= MIN;
      if (big) onDraw(round(g));
      return;
    }
    if (!done.moved) return;  // a click selects; it doesn't move
    const keys = g.type === "circle" ? (m.kind === "move" ? ["cx", "cy"] : ["size"]) : ["left", "top", "right", "bottom"];
    onChange(m.line, round(Object.fromEntries(keys.map((k) => [k, g[k]]))));
  };
  const shown = callouts.map((c) => (draft && draft.line === c.line ? { ...c, ...draft.geometry } : c));
  return html`<svg ref=${svg} class=${`callout-layer ${tool ? "drawing" : ""}`} viewBox=${`0 0 ${w} ${h}`}
      data-testid="callout-layer" onPointerMove=${onPointerMove} onPointerUp=${onPointerUp} onPointerCancel=${onPointerUp}>
    ${tool && html`<rect class="capture" width=${w} height=${h} onPointerDown=${(e) => start(e, { kind: "draw" })} />`}
    ${shown.map((c) => html`<${Shape} c=${c} className=${`callout-shape ${c.line === selected ? "selected" : ""}`}
      onPointerDown=${(e) => { if (tool) return; onSelect(c.line); start(e, { kind: "move", line: c.line }); }} />`)}
    ${shown.filter((c) => c.line === selected && !tool).map((c) => html`<${Handles} c=${c} r=${Math.max(w, h) / 80}
      start=${(e, next) => { onSelect(c.line); start(e, { ...next, line: c.line }); }} />`)}
    ${draft && draft.line === null && html`<${Shape} c=${draft.geometry} className="callout-shape drawing" />`}
  </svg>`;
}

/** Controls for the callout on the cursor's line: its shape, shading, mask, and Delete. */
export function CalloutInspector({ callout, onChange, onDelete, busy }) {
  if (!callout) return null;
  const c = callout;
  // Switching shape keeps the same place: a circle's bounding square, or the circle inside a rectangle
  const toRectangle = () => ({ type: "rectangle", left: c.cx - c.size, top: c.cy - c.size, right: c.cx + c.size, bottom: c.cy + c.size });
  const toCircle = () => ({ type: "circle", cx: (c.left + c.right) / 2, cy: (c.top + c.bottom) / 2,
                            size: Math.min(c.right - c.left, c.bottom - c.top) / 2 });
  const where = c.type === "circle"
    ? `centre ${Math.round(c.cx)}, ${Math.round(c.cy)} · radius ${Math.round(c.size)}`
    : `${Math.round(c.left)}, ${Math.round(c.top)} to ${Math.round(c.right)}, ${Math.round(c.bottom)}`;
  return html`<section class="inspector" aria-label="callout" data-testid="callout-inspector" aria-busy=${busy ? "true" : "false"}>
    <h3>Callout <span class="muted">line ${c.line}</span></h3>
    <div class="row">
      <span class="label">Shape</span>
      <div class="segmented" role="group" aria-label="shape">
        <button aria-pressed=${c.type === "circle"} disabled=${busy} onClick=${() => c.type !== "circle" && onChange(round(toCircle()))}>circle</button>
        <button aria-pressed=${c.type === "rectangle"} disabled=${busy} onClick=${() => c.type !== "rectangle" && onChange(round(toRectangle()))}>rectangle</button>
      </div>
      <span class="muted small">${where}</span>
    </div>
    <div class="row">
      <span class="label">Shading</span>
      <input type="range" min="0" max="1" step="0.05" value=${c.alpha} aria-label="shading" disabled=${busy || c.style === "mask"}
        onChange=${(e) => onChange({ alpha: Number(e.target.value) === 0.5 ? null : Number(e.target.value) })} />
      <span class="small">${Math.round(c.alpha * 100)}%</span>
      <label class="small"><input type="checkbox" checked=${c.style === "mask"} disabled=${busy}
        onChange=${(e) => onChange({ style: e.target.checked ? "mask" : null })} /> mask (black out)</label>
    </div>
    <div class="row"><button onClick=${onDelete} disabled=${busy}>Delete callout</button></div>
  </section>`;
}
