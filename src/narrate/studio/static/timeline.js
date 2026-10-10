// The timeline (#60): the whole video, with scenes sized by duration, what's on screen when,
// the narration's waveform, transitions and cues. Clicking or dragging on it seeks.
import { html, useEffect, useLayoutEffect, useRef, useState } from "./vendor/htm-preact.js";
import { seconds } from "./editor.js";

const MIN_PPS = 2;
const MAX_PPS = 400;
const STEPS = [0.5, 1, 2, 5, 10, 15, 30, 60, 120, 300, 600];
const FRAME = 1 / 30;
const MAX_CANVAS = 16384;  // device pixels: browsers refuse wider canvases

const KINDS = { picture: "picture", clip: "clip", page: "HTML page", render: "render block", missing: "missing file",
                slide: "slide" };

/** One scene's waveform, drawn from the server's min/max peaks. */
function Wave({ peaks, duration, width, height }) {
  const canvas = useRef(null);
  useEffect(() => {
    const el = canvas.current;
    if (!el) return;
    const ratio = window.devicePixelRatio || 1;
    const w = Math.max(1, Math.min(MAX_CANVAS, Math.round(width * ratio)));
    const h = Math.round(height * ratio);
    el.width = w;
    el.height = h;
    const ctx = el.getContext("2d");
    ctx.clearRect(0, 0, w, h);
    if (!peaks) return;
    ctx.fillStyle = getComputedStyle(el).getPropertyValue("--accent").trim() || "#2f6fdd";
    const data = peaks.peaks;
    const buckets = data.length / 2;
    const perPixel = (peaks.rate * duration) / w;
    const mid = h / 2;
    const scale = (mid / 100) * 1.6;  // speech rarely peaks above 0.6
    for (let x = 0; x < w; x++) {
      const b0 = Math.floor(x * perPixel);
      if (b0 >= buckets) break;
      const b1 = Math.min(buckets, Math.max(b0 + 1, Math.floor((x + 1) * perPixel)));
      let lo = 0, hi = 0;
      for (let b = b0; b < b1; b++) {
        if (data[2 * b] < lo) lo = data[2 * b];
        if (data[2 * b + 1] > hi) hi = data[2 * b + 1];
      }
      const top = Math.max(0, mid - hi * scale);
      const bottom = Math.min(h, mid - lo * scale);
      ctx.fillRect(x, top, 1, Math.max(ratio, bottom - top));
    }
  }, [peaks, duration, width, height]);
  return html`<canvas ref=${canvas} class="tl-wave" style=${`width:${width}px;height:${height}px`}></canvas>`;
}

/** Ruler ticks every few seconds, spaced at least 70 px apart. */
function Ruler({ duration, pps }) {
  const step = STEPS.find((s) => s * pps >= 70) || STEPS[STEPS.length - 1];
  const ticks = [];
  for (let t = 0; t <= duration + 1e-6; t += step) ticks.push(t);
  return html`<div class="tl-ruler">${ticks.map((t) => html`
    <span class="tl-tick-label" style=${`left:${t * pps}px`}>${seconds(t)}</span>`)}</div>`;
}

function Scene({ scene, pps, peaks, current, onLine }) {
  const width = scene.duration * pps;
  const marks = Object.entries(scene.marks || {}).filter(([name]) => !/^\d+$/.test(name));
  return html`<div class=${`tl-scene ${scene.estimated ? "estimated" : ""} ${current ? "current" : ""}`}
      style=${`left:${scene.start * pps}px;width:${width}px`} data-scene=${scene.index}>
    <div class="tl-head" title=${`scene ${scene.index} · ${scene.title} · starts ${seconds(scene.start)}, lasts ${seconds(scene.duration)}${scene.estimated ? " (estimated: some speech isn't synthesised yet)" : ""}`}>
      <b>${scene.index}</b> ${scene.title} <span class="tl-length">${seconds(scene.duration)}</span>
    </div>
    <div class=${`tl-visuals ${scene.visuals.length && scene.slides.length ? "with-slides" : ""}`}>
      ${[...scene.visuals, ...scene.slides].map((v) => html`
        <div class=${`tl-visual ${v.kind}`} style=${`left:${v.start * pps}px;width:${Math.max(1, v.length * pps - 1)}px`}
          title=${`${v.name} (${KINDS[v.kind] || v.kind}${v.motion ? `, ${v.motion}` : ""}), line ${v.line}: ${seconds(v.start)} to ${seconds(v.start + v.length)} · double-click to edit`}
          onDblClick=${(e) => { e.stopPropagation(); onLine(v.line); }}>${v.name}</div>`)}
      ${scene.transition && html`<div class="tl-transition" style=${`width:${Math.max(4, scene.transition.seconds * pps)}px`}
        title=${`${scene.transition.type}, ${seconds(scene.transition.seconds)}`}></div>`}
    </div>
    <div class="tl-sound">
      <${Wave} peaks=${peaks} duration=${scene.duration} width=${width} height=${36} />
      ${scene.paragraphs.filter((p) => p.estimated).map((p) => html`
        <div class="tl-estimate" style=${`left:${p.start * pps}px;width:${Math.max(1, (p.end - p.start) * pps)}px`}
          title="estimated from the text: not synthesised yet"></div>`)}
      ${scene.paragraphs.map((p) => html`<div class="tl-cue" style=${`left:${p.start * pps}px`} title=${`paragraph on line ${p.line}`}></div>`)}
      ${marks.map(([name, t]) => html`<div class="tl-mark" style=${`left:${t * pps}px`} title=${`cue "${name}" at ${seconds(t)}`}><span>${name}</span></div>`)}
    </div>
  </div>`;
}

/** The whole video. `playhead` is in seconds from the start; `onSeek(t)` is called while clicking or dragging. */
export function Timeline({ analysis, playhead, onSeek, onLine }) {
  const scroller = useRef(null);
  const track = useRef(null);
  const dragging = useRef(false);
  const fetched = useRef(new Map());  // sound id -> peaks, or "pending"
  const [, setFetches] = useState(0);
  const [fit, setFit] = useState(true);
  const [pps, setPps] = useState(20);
  const duration = (analysis && analysis.duration) || 0;

  // Fit the whole video in view, until zoomed by hand
  useLayoutEffect(() => {
    if (!fit || !scroller.current) return;
    const resize = () => {
      const width = scroller.current.clientWidth - 24;
      setPps(Math.max(MIN_PPS / 4, Math.min(MAX_PPS, duration > 0 ? width / duration : 20)));
    };
    resize();
    const observer = new ResizeObserver(resize);
    observer.observe(scroller.current);
    return () => observer.disconnect();
  }, [fit, duration]);

  // Waveforms: fetched once per sound, so typing doesn't refetch scenes whose sound didn't change
  useEffect(() => {
    if (!analysis) return;
    for (const scene of analysis.scenes) {
      const id = scene.sound;
      if (!id || fetched.current.has(id)) continue;
      fetched.current.set(id, "pending");
      fetch(`/api/peaks/${id}`).then((r) => (r.ok ? r.json() : null)).then((peaks) => {
        if (peaks) fetched.current.set(id, peaks);
        else fetched.current.delete(id);
        setFetches((n) => n + 1);
      }).catch(() => fetched.current.delete(id));
    }
  }, [analysis]);

  // Keep the playhead in view, unless it's being dragged
  useEffect(() => {
    const el = scroller.current;
    if (!el || dragging.current) return;
    const x = playhead * pps;
    if (x < el.scrollLeft || x > el.scrollLeft + el.clientWidth - 20) el.scrollLeft = Math.max(0, x - el.clientWidth * 0.2);
  }, [playhead, pps]);

  if (!analysis || !analysis.scenes.length) return null;

  const timeAt = (clientX) => {
    const left = track.current.getBoundingClientRect().left;
    return Math.max(0, Math.min(duration, (clientX - left) / pps));
  };
  const zoom = (factor, anchorX = null) => {
    const el = scroller.current;
    const anchor = anchorX ?? el.clientWidth / 2;
    const t = (el.scrollLeft + anchor) / pps;
    const next = Math.max(MIN_PPS, Math.min(MAX_PPS, pps * factor));
    setFit(false);
    setPps(next);
    requestAnimationFrame(() => { el.scrollLeft = Math.max(0, t * next - anchor); });
  };
  const onPointerDown = (e) => {
    if (e.button !== 0) return;
    dragging.current = true;
    e.currentTarget.setPointerCapture(e.pointerId);
    onSeek(timeAt(e.clientX));
  };
  const onPointerMove = (e) => { if (dragging.current) onSeek(timeAt(e.clientX)); };
  const onPointerUp = () => { dragging.current = false; };
  const onKeyDown = (e) => {
    const step = e.shiftKey ? 1 : FRAME;
    const to = { ArrowLeft: playhead - step, ArrowRight: playhead + step, Home: 0, End: duration - FRAME }[e.key];
    if (to === undefined) return;
    e.preventDefault();
    onSeek(Math.max(0, Math.min(duration - FRAME, to)));
  };
  const onWheel = (e) => {
    if (!(e.ctrlKey || e.metaKey)) return;
    e.preventDefault();
    zoom(e.deltaY < 0 ? 1.25 : 0.8, e.clientX - scroller.current.getBoundingClientRect().left);
  };

  const currentScene = analysis.scenes.find((s) => s.duration != null && playhead >= s.start && playhead < s.start + s.duration);
  return html`<section class="timeline" aria-label="timeline">
    <div class="tl-tools">
      <span class="tl-title">Timeline</span>
      <button class="quiet" onClick=${() => setFit(true)} disabled=${fit} title="fit the whole video">Fit</button>
      <button class="quiet" onClick=${() => zoom(0.67)} title="zoom out (Ctrl+wheel)" aria-label="zoom out">−</button>
      <button class="quiet" onClick=${() => zoom(1.5)} title="zoom in (Ctrl+wheel)" aria-label="zoom in">+</button>
      <span class="tl-time" data-testid="playhead">${seconds(playhead)} / ${seconds(duration)}</span>
      <span class="tl-hint">click or drag to seek · ←/→ a frame, Shift a second</span>
    </div>
    <div class="tl-scroll" ref=${scroller} tabindex="0" onKeyDown=${onKeyDown} onWheel=${onWheel}>
      <div class="tl-track" ref=${track} style=${`width:${duration * pps + 24}px`}
          onPointerDown=${onPointerDown} onPointerMove=${onPointerMove} onPointerUp=${onPointerUp} onPointerCancel=${onPointerUp}>
        <${Ruler} duration=${duration} pps=${pps} />
        ${analysis.scenes.map((scene) => scene.duration == null
          ? html`<div class="tl-untimed" style=${`left:${scene.start * pps}px`} title=${`scene ${scene.index} can't be timed: see the problems`}></div>`
          : html`<${Scene} key=${scene.index} scene=${scene} pps=${pps} current=${currentScene === scene}
              peaks=${typeof fetched.current.get(scene.sound) === "object" ? fetched.current.get(scene.sound) : null}
              onLine=${onLine} />`)}
        <div class="tl-playhead" style=${`left:${playhead * pps}px`}></div>
      </div>
    </div>
  </section>`;
}
