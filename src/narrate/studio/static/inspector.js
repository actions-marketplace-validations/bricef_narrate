// The inspector (#62): controls for the picture, clip, page or render block at the cursor.
// Each change is an edit the server makes to the script's text (POST /api/edit), so the
// script stays the source of truth and every change can be undone in the editor.
import { html, useEffect, useRef, useState } from "./vendor/htm-preact.js";

const FITS = [["cover", "fill the frame, cropping"], ["contain", "show it all, with bars"], ["fit", "stretch to the frame"]];
const MOTIONS = ["zoom", "zoomout", "pan", "panzoom", "panzoomout"];
const SYNCS = ["freeze", "match", "trim", "loop", "trim-or-loop", "loop-audio"];
// The positions narrate has, laid out as a grid; the corners it doesn't have stay empty
const GRID = [["top-left", "top", null], ["left", "center", "right"], [null, "bottom", null]];
const DEFAULT_ZOOM = { zoom: 1.25, zoomout: 1.25, panzoom: 1.25, panzoomout: 1.25, pan: 1.15 };
export const KIND_NAMES = { picture: "Picture", clip: "Clip", page: "HTML scene", render: "Render block" };

/** Which way a picture has room to move: the axis it overflows (cover) or doesn't fill (contain). */
export function slack(entry, fit, frame) {
  if (!entry.size || fit === "fit") return { x: false, y: false };
  const [iw, ih] = entry.size;
  const [w, h] = frame;
  const scale = fit === "contain" ? Math.min(w / iw, h / ih) : Math.max(w / iw, h / ih);
  const sw = iw * scale, sh = ih * scale;
  return { x: Math.abs(sw - w) > 0.5, y: Math.abs(sh - h) > 0.5 };
}

const AXES = { "top-left": [-1, -1], top: [0, -1], left: [-1, 0], center: [0, 0], right: [1, 0], bottom: [0, 1] };

/** The position a drag of (dx, dy) fractions of the frame leads to from `from`, on the axes with room. */
export function draggedPosition(from, dx, dy, room) {
  const [cx, cy] = AXES[from] || [0, 0];
  // Dragging the picture right shows more of its left side
  let x = room.x ? Math.max(-1, Math.min(1, Math.round(cx - dx / 0.15))) : 0;
  let y = room.y ? Math.max(-1, Math.min(1, Math.round(cy - dy / 0.15))) : 0;
  const find = (a, b) => Object.keys(AXES).find((p) => AXES[p][0] === a && AXES[p][1] === b);
  if (find(x, y)) return find(x, y);
  // No such corner: keep the axis dragged further
  return Math.abs(dx) >= Math.abs(dy) ? find(x, 0) : find(0, y);
}

// -- free framing (#63): focal points and windows, in fractions of the picture ---------------

const clamp = (v, lo, hi) => Math.min(Math.max(v, lo), hi);
const coverSize = ([iw, ih], [w, h]) => { const s = Math.min(iw / w, ih / h); return [w * s, h * s]; };
const pct = (v, digits = 0) => `${(Math.round(v * 100 * 10 ** digits) / 10 ** digits)}%`;
const focusText = ([x, y]) => `${pct(x)} ${pct(y)}`;
const windowText = ([x, y, z]) => `${pct(x, 1)} ${pct(y, 1)}${Math.abs(z - 1) > 0.005 ? ` ${Math.round(z * 100) / 100}` : ""}`;
const NAMED = { center: [0.5, 0.5], left: [0, 0.5], right: [1, 0.5], top: [0.5, 0], bottom: [0.5, 1], "top-left": [0, 0] };

/** A cover crop kept as near `focus` as the picture allows, in its pixels. */
export function cropAround(focus, size, frame) {
  const [cw, ch] = coverSize(size, frame);
  return [clamp(focus[0] * size[0] - cw / 2, 0, size[0] - cw), clamp(focus[1] * size[1] - ch / 2, 0, size[1] - ch), cw, ch];
}

/** A window (centre and zoom) as a rect in the picture's pixels, kept inside it. */
function windowRect([cx, cy, z], size, frame) {
  const [cw, ch] = coverSize(size, frame);
  const w = cw / z, h = ch / z;
  return [clamp(cx * size[0] - w / 2, 0, size[0] - w), clamp(cy * size[1] - h / 2, 0, size[1] - h), w, h];
}

const windowOf = ([x, y, w, h], size, frame) => [(x + w / 2) / size[0], (y + h / 2) / size[1], coverSize(size, frame)[0] / w];

/** The named position a focal point amounts to for this crop, if any: scripts stay simple where they can. */
export function namedFor(focus, size, frame) {
  const crop = cropAround(focus, size, frame);
  const align = [0, 1].map((k) => (size[k] - crop[k + 2] < 0.5 ? null : crop[k] / (size[k] - crop[k + 2])));
  return Object.keys(NAMED).find((name) => align.every((a, k) => a === null || Math.abs(a - NAMED[name][k]) < 0.02)) || null;
}

/** What setting a focal point writes: a named position when it is one, else the point. */
export function positionFor(focus, size, frame) {
  const named = namedFor(focus, size, frame);
  return named ? (named === "center" ? null : named) : focusText(focus);
}

/** The whole picture, with its framing on it. A still shows its crop and focal point: click or drag to move
    the point. A pan or zoom shows its first (dashed) and last windows: drag one to move it, or its corner to
    zoom, and Show the motion plays it. */
function Framing({ entry, frame, moving, onSet, busy }) {
  const svg = useRef(null);
  const mode = useRef(null);
  const [draft, setDraft] = useState(null);
  const [t, setT] = useState(null);
  const animation = useRef(null);
  useEffect(() => () => cancelAnimationFrame(animation.current), []);
  useEffect(() => setDraft(null), [entry.options.position, entry.options.from, entry.options.to, entry.options.motion]);
  if (!entry.size || !entry.crop) return null;
  const size = entry.size;
  const [iw, ih] = size;
  const stroke = Math.max(iw, ih) / 160;
  const toPicture = (e) => {
    const r = svg.current.getBoundingClientRect();
    return [clamp((e.clientX - r.left) / r.width, 0, 1) * iw, clamp((e.clientY - r.top) / r.height, 0, 1) * ih];
  };
  const windows = moving && entry.windows ? (draft && draft.windows) || entry.windows.map((r) => windowOf(r, size, frame)) : null;
  const rects = windows && windows.map((w) => windowRect(w, size, frame));
  const focus = (draft && draft.focus) || entry.focus;
  const crop = draft && draft.focus ? cropAround(draft.focus, size, frame) : entry.crop;

  const onPointerDown = (e) => {
    if (busy || e.button !== 0) return;
    e.preventDefault();  // no text selection or native drag, which would cancel the pointer
    const p = toPicture(e);
    e.currentTarget.setPointerCapture(e.pointerId);
    if (!windows) {
      mode.current = { kind: "focus" };
      setDraft({ focus: [p[0] / iw, p[1] / ih] });
      return;
    }
    const near = Math.max(iw, ih) * 0.04;
    for (const k of [1, 0]) {  // the last window first: it's usually the smaller, inside the first
      const [x, y, w, h] = rects[k];
      if (Math.hypot(p[0] - (x + w), p[1] - (y + h)) < near) { mode.current = { kind: "resize", k, anchor: [x, y] }; return; }
      if (p[0] >= x && p[0] <= x + w && p[1] >= y && p[1] <= y + h) {
        mode.current = { kind: "move", k, offset: [p[0] - (x + w / 2), p[1] - (y + h / 2)] };
        return;
      }
    }
    mode.current = null;
  };
  /** Where the drag has got to: a focal point, or the windows with one moved or resized. */
  const track = (e) => {
    const m = mode.current;
    const p = toPicture(e);
    if (m.kind === "focus") return { focus: [p[0] / iw, p[1] / ih] };
    const next = windows.slice();
    const [cw] = coverSize(size, frame);
    if (m.kind === "move") {
      next[m.k] = [(p[0] - m.offset[0]) / iw, (p[1] - m.offset[1]) / ih, windows[m.k][2]];
    } else {  // resize from the top-left corner, keeping the frame's shape
      const w = clamp(p[0] - m.anchor[0], cw / 6, cw);
      const h = (w * frame[1]) / frame[0];
      next[m.k] = [(m.anchor[0] + w / 2) / iw, (m.anchor[1] + h / 2) / ih, cw / w];
    }
    return { windows: next.map((w) => windowOf(windowRect(w, size, frame), size, frame)) };
  };
  const onPointerMove = (e) => { if (mode.current) setDraft(track(e)); };
  const onPointerUp = (e) => {
    // The release says where the pointer ended: moves before it may have been coalesced away
    const done = mode.current && e.type === "pointerup" ? track(e) : null;
    mode.current = null;
    if (!done) return;
    if (done.focus) onSet({ position: positionFor(done.focus, size, frame) });
    else if (done.windows) onSet({ from: windowText(done.windows[0]), to: windowText(done.windows[1]), motion: null, zoom: null });
  };
  const play = () => {
    const started = performance.now();
    const step = (now) => {
      const p = Math.min(1, (now - started) / 2500);
      setT(p);
      if (p < 1) animation.current = requestAnimationFrame(step);
      else setTimeout(() => setT(null), 400);
    };
    cancelAnimationFrame(animation.current);
    animation.current = requestAnimationFrame(step);
  };
  const between = rects && t != null ? rects[0].map((v, k) => v + (rects[1][k] - v) * t) : null;
  const handle = (r) => html`<circle cx=${r[0] + r[2]} cy=${r[1] + r[3]} r=${stroke * 2.2} class="handle" />`;
  return html`<div class="windows">
    <div class="windows-picture">
      <img src=${`/files/${encodeURI(entry.file)}`} alt="" />
      <svg ref=${svg} viewBox=${`0 0 ${iw} ${ih}`} preserveAspectRatio="none" data-testid="framing" data-focus=${focusText(entry.focus)}
        aria-label=${rects ? "first and last windows" : "crop and focal point"}
        onPointerDown=${onPointerDown} onPointerMove=${onPointerMove} onPointerUp=${onPointerUp} onPointerCancel=${onPointerUp}>
        ${rects ? html`
          <rect x=${rects[0][0]} y=${rects[0][1]} width=${rects[0][2]} height=${rects[0][3]} class="first" stroke-width=${stroke}
            stroke-dasharray=${`${stroke * 3} ${stroke * 2}`} />
          <rect x=${rects[1][0]} y=${rects[1][1]} width=${rects[1][2]} height=${rects[1][3]} class="last" stroke-width=${stroke} />
          ${handle(rects[0])}${handle(rects[1])}
          ${between && html`<rect x=${between[0]} y=${between[1]} width=${between[2]} height=${between[3]} class="now" stroke-width=${stroke * 1.5} />`}`
        : html`
          <rect x=${crop[0]} y=${crop[1]} width=${crop[2]} height=${crop[3]} class="last" stroke-width=${stroke} />
          <g class="focus" stroke-width=${stroke}>
            <line x1=${focus[0] * iw - stroke * 6} x2=${focus[0] * iw + stroke * 6} y1=${focus[1] * ih} y2=${focus[1] * ih} />
            <line y1=${focus[1] * ih - stroke * 6} y2=${focus[1] * ih + stroke * 6} x1=${focus[0] * iw} x2=${focus[0] * iw} />
          </g>`}
      </svg>
    </div>
    ${rects
      ? html`<p class="hint"><span><i class="swatch first"></i>first <i class="swatch last"></i>last · drag to move, corner to zoom</span>
          <button class="quiet" onClick=${play}>▶ Show the motion</button></p>`
      : html`<p class="hint"><span>Click or drag to set the focal point${draft && draft.focus ? `: ${focusText(draft.focus)}` : ""}</span></p>`}
  </div>`;
}

/** Controls for the media block on `line`; `onEdit(line, changes)` asks for the edit. */
export function Inspector({ analysis, line, onEdit, busy }) {
  const entry = analysis && analysis.media && analysis.media[String(line)];
  const [zoomDraft, setZoomDraft] = useState(null);
  const [segment, setSegment] = useState(["", ""]);
  const o = entry ? entry.options : null;
  useEffect(() => {
    setZoomDraft(null);
    const [a, b] = (o && o.segment ? o.segment : "").split("-");
    setSegment([a || "", b || ""]);
  }, [entry && entry.line, o && o.segment, o && o.zoom]);
  if (!entry) return null;

  const defaults = analysis.defaults || { fit: "cover" };
  const frame = analysis.size || [1280, 720];
  const fit = o.motion ? "cover" : o.fit || defaults.fit;
  const position = o.position || "center";
  const room = slack(entry, fit, frame);
  // A pan or zoom heads for the position, so every one counts; a still crop only moves where there's room
  const matters = (p) => Boolean(o.motion) || p === "center" || (AXES[p][0] !== 0 && room.x) || (AXES[p][1] !== 0 && room.y);
  const focal = Boolean(o.position) && !AXES[o.position];  // a focal point such as 70% 25%
  const set = (changes) => onEdit(entry.line, changes);
  const zoom = zoomDraft ?? (o.zoom || defaults.zoom || DEFAULT_ZOOM[o.motion] || 1.25);
  const applySegment = () => {
    const [a, b] = segment.map((v) => v.trim());
    const value = a || b ? `${a || "start"}${b ? `-${b}` : ""}` : null;
    if (value !== (o.segment || null)) set({ segment: value });
  };
  const volume = o.volume === "mute" ? 0 : o.volume ?? 1;
  const custom = Boolean(o.from || o.to);
  const pickMotion = (value) => {
    if (value !== "custom") { set({ motion: value || null, from: null, to: null, ...(value ? { fit: null } : {}) }); return; }
    // Custom windows start from what's there: the motion's own windows, or the crop zooming in on the focal point
    const size = entry.size;
    if (!size) return;
    const windows = entry.windows
      ? entry.windows.map((r) => windowOf(r, size, frame))
      : [windowOf(entry.crop, size, frame), [entry.focus[0], entry.focus[1], 1.5]];
    set({ from: windowText(windows[0]), to: windowText(windows[1]), motion: null, zoom: null });
  };

  return html`<section class="inspector" aria-label="inspector" data-testid="inspector" aria-busy=${busy ? "true" : "false"}>
    <h3>${KIND_NAMES[entry.kind] || entry.kind} <span class="file">${entry.file || ""}</span>
      <span class="muted">line ${entry.line}</span></h3>
    <div class="row">
      <span class="label">Fit</span>
      <div class="segmented" role="group" aria-label="fit">
        ${FITS.map(([value, title]) => html`<button aria-pressed=${fit === value} title=${title} disabled=${busy}
          onClick=${() => set({ fit: value === defaults.fit ? null : value, motion: value === "cover" ? o.motion : null })}>${value}</button>`)}
      </div>
    </div>
    <div class="row">
      <span class="label">Position</span>
      <div class="positions" role="group" aria-label="position">
        ${GRID.flat().map((p) => (p
          ? html`<button aria-pressed=${!focal && position === p} aria-label=${p} title=${matters(p) ? p : `${p} (no different here)`}
              class=${matters(p) ? "" : "dim"} disabled=${busy}
              onClick=${() => set({ position: p === "center" ? null : p })}></button>`
          : html`<span class="none" title="narrate has no such position"></span>`))}
      </div>
      <span class="muted small">${position}${fit === "fit" ? " (stretched: position doesn't apply)" : ""}</span>
    </div>
    ${(entry.kind === "picture" || entry.kind === "render") && html`<div class="row">
      <span class="label">Motion</span>
      <select aria-label="motion" value=${custom ? "custom" : o.motion || ""} disabled=${busy} onChange=${(e) => pickMotion(e.target.value)}>
        <option value="">none</option>
        ${MOTIONS.map((m) => html`<option value=${m}>${m}</option>`)}
        ${entry.kind === "picture" && html`<option value="custom">custom (from/to)</option>`}
      </select>
      ${o.motion && !custom && entry.kind === "picture" && html`<label class="zoom">
        <input type="range" min="1.05" max="3" step="0.05" value=${zoom} aria-label="zoom amount" disabled=${busy}
          onInput=${(e) => setZoomDraft(Number(e.target.value))}
          onChange=${(e) => set({ zoom: Number(e.target.value) })} />
        <span class="small">×${Number(zoom).toFixed(2)}</span>
        ${o.zoom && html`<button class="quiet small" onClick=${() => set({ zoom: null })} title="back to the default">reset</button>`}
      </label>`}
    </div>`}
    ${entry.kind === "picture" && (fit === "cover" || custom) && html`<${Framing} entry=${entry} frame=${frame}
      moving=${Boolean(o.motion || custom)} onSet=${set} busy=${busy} />`}
    ${entry.kind === "clip" && html`
      <div class="row">
        <span class="label">Sync</span>
        <select aria-label="sync" value=${o.sync || ""} disabled=${busy} onChange=${(e) => set({ sync: e.target.value || null })}>
          <option value="">default</option>
          ${SYNCS.map((s) => html`<option value=${s}>${s}</option>`)}
        </select>
      </div>
      <div class="row">
        <span class="label">Segment</span>
        <input class="time" aria-label="segment start" placeholder="start" value=${segment[0]} disabled=${busy}
          onInput=${(e) => setSegment([e.target.value, segment[1]])} onBlur=${applySegment}
          onKeyDown=${(e) => e.key === "Enter" && applySegment()} />
        <span>to</span>
        <input class="time" aria-label="segment end" placeholder="end" value=${segment[1]} disabled=${busy}
          onInput=${(e) => setSegment([segment[0], e.target.value])} onBlur=${applySegment}
          onKeyDown=${(e) => e.key === "Enter" && applySegment()} />
        ${entry.length != null && html`<span class="muted small">of ${entry.length.toFixed(1)} s</span>`}
      </div>
      <div class="row">
        <span class="label">Volume</span>
        <input type="range" min="0" max="2" step="0.05" value=${volume} aria-label="volume" disabled=${busy}
          onChange=${(e) => set({ volume: Number(e.target.value) === 0 ? "mute" : Number(e.target.value) })} />
        <span class="small">${volume === 0 ? "muted" : `${Math.round(volume * 100)}%`}</span>
        <label class="small"><input type="checkbox" checked=${volume === 0} disabled=${busy}
          onChange=${(e) => set({ volume: e.target.checked ? "mute" : null })} /> mute</label>
      </div>`}
    ${room.x || room.y ? html`<p class="hint">Drag the preview to move the picture ${room.x && room.y ? "" : room.x ? "sideways" : "up or down"}.</p>` : ""}
  </section>`;
}
