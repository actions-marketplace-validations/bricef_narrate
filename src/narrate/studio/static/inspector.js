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

/** The whole picture, with the first (dashed) and last windows of its pan or zoom, and a play button. */
function Windows({ entry }) {
  const [t, setT] = useState(null);
  const frame = useRef(null);
  useEffect(() => () => cancelAnimationFrame(frame.current), []);
  if (!entry.windows || !entry.size) return null;
  const [iw, ih] = entry.size;
  const [a, b] = entry.windows;
  const play = () => {
    const started = performance.now();
    const step = (now) => {
      const p = Math.min(1, (now - started) / 2500);
      setT(p);
      if (p < 1) frame.current = requestAnimationFrame(step);
      else setTimeout(() => setT(null), 400);
    };
    cancelAnimationFrame(frame.current);
    frame.current = requestAnimationFrame(step);
  };
  const between = t == null ? null : a.map((v, k) => v + (b[k] - v) * t);
  const stroke = Math.max(iw, ih) / 160;
  return html`<div class="windows">
    <div class="windows-picture">
      <img src=${`/files/${encodeURI(entry.file)}`} alt="" />
      <svg viewBox=${`0 0 ${iw} ${ih}`} preserveAspectRatio="none" aria-label="first and last windows">
        <rect x=${a[0]} y=${a[1]} width=${a[2]} height=${a[3]} class="first" stroke-width=${stroke} stroke-dasharray=${`${stroke * 3} ${stroke * 2}`} />
        <rect x=${b[0]} y=${b[1]} width=${b[2]} height=${b[3]} class="last" stroke-width=${stroke} />
        ${between && html`<rect x=${between[0]} y=${between[1]} width=${between[2]} height=${between[3]} class="now" stroke-width=${stroke * 1.5} />`}
      </svg>
    </div>
    <p class="hint"><span><i class="swatch first"></i>first frame <i class="swatch last"></i>last frame</span>
      <button class="quiet" onClick=${play}>▶ Show the motion</button></p>
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
  const set = (changes) => onEdit(entry.line, changes);
  const zoom = zoomDraft ?? (o.zoom || defaults.zoom || DEFAULT_ZOOM[o.motion] || 1.25);
  const applySegment = () => {
    const [a, b] = segment.map((v) => v.trim());
    const value = a || b ? `${a || "start"}${b ? `-${b}` : ""}` : null;
    if (value !== (o.segment || null)) set({ segment: value });
  };
  const volume = o.volume === "mute" ? 0 : o.volume ?? 1;

  return html`<section class="inspector" aria-label="inspector" data-testid="inspector">
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
          ? html`<button aria-pressed=${position === p} aria-label=${p} title=${matters(p) ? p : `${p} (no different here)`}
              class=${matters(p) ? "" : "dim"} disabled=${busy}
              onClick=${() => set({ position: p === "center" ? null : p })}></button>`
          : html`<span class="none" title="narrate has no such position"></span>`))}
      </div>
      <span class="muted small">${position}${fit === "fit" ? " (stretched: position doesn't apply)" : ""}</span>
    </div>
    ${(entry.kind === "picture" || entry.kind === "render") && html`<div class="row">
      <span class="label">Motion</span>
      <select aria-label="motion" value=${o.motion || ""} disabled=${busy}
        onChange=${(e) => set({ motion: e.target.value || null, ...(e.target.value ? { fit: null } : {}) })}>
        <option value="">none</option>
        ${MOTIONS.map((m) => html`<option value=${m}>${m}</option>`)}
      </select>
      ${o.motion && entry.kind === "picture" && html`<label class="zoom">
        <input type="range" min="1.05" max="3" step="0.05" value=${zoom} aria-label="zoom amount" disabled=${busy}
          onInput=${(e) => setZoomDraft(Number(e.target.value))}
          onChange=${(e) => set({ zoom: Number(e.target.value) })} />
        <span class="small">×${Number(zoom).toFixed(2)}</span>
        ${o.zoom && html`<button class="quiet small" onClick=${() => set({ zoom: null })} title="back to the default">reset</button>`}
      </label>`}
    </div>`}
    ${entry.kind === "picture" && html`<${Windows} entry=${entry} />`}
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
