// narrate studio: the app shell (docs/design/studio.md).
import { html, render, useCallback, useEffect, useRef, useState } from "./vendor/htm-preact.js";
import { createEditor, followLine, goToLine, seconds, showAnalysis } from "./editor.js";
import { Timeline } from "./timeline.js";

const ANALYSE_AFTER_MS = 300;
const PREVIEW_AFTER_MS = 150;

async function getJSON(url, options) {
  const response = await fetch(url, options);
  const body = await response.json().catch(() => ({}));
  return { status: response.status, body };
}

function Notice({ notice, onReload, onOverwrite, onDismiss }) {
  if (!notice) return null;
  const message = notice.kind === "conflict"
    ? "The script changed on disk since you opened it, so it wasn't saved."
    : "The script changed on disk, and you have unsaved edits.";
  return html`<div class="notice" role="alert">
    <span>${message}</span>
    <button onClick=${onReload}>Load the file (lose my edits)</button>
    <button onClick=${onOverwrite}>${notice.kind === "conflict" ? "Keep mine and save" : "Keep mine (overwrite the file)"}</button>
    ${notice.kind === "changed" && html`<button class="quiet" onClick=${onDismiss}>Decide later</button>`}
  </div>`;
}

const ENGINE_NAMES = { kokoro: "Kokoro", elevenlabs: "ElevenLabs", silent: "silent", auto: "auto" };

/** The speech engine for timing, playback and builds; switching asks the server first. */
function EnginePicker({ engine, onPick }) {
  return html`<label class="engine" title="speech engine for timing, playback and builds">
    <select value=${engine} onChange=${(e) => onPick(e.target.value)} aria-label="speech engine">
      ${Object.entries(ENGINE_NAMES).map(([value, name]) => html`<option value=${value}>${name}</option>`)}
    </select></label>`;
}

/** What the chosen engine still has to synthesise before a build (D10). */
function Cost({ analysis }) {
  if (!analysis || !analysis.missing) return null;
  const engine = ENGINE_NAMES[analysis.engine] || analysis.engine;
  const { paragraphs, characters } = analysis.missing;
  const text = paragraphs
    ? `${engine}: ${paragraphs} paragraph${paragraphs === 1 ? "" : "s"} to synthesise (${characters} characters)`
    : `${engine}: all speech cached`;
  return html`<span class=${`cost ${paragraphs && analysis.engine === "elevenlabs" ? "spends" : ""}`}
    title="paragraphs whose speech isn't in the cache yet, and the characters they'd send" data-testid="cost">${text}</span>`;
}

/** The scenes, with when each starts and how long it lasts; click to jump there. */
function Outline({ analysis, current, onPick }) {
  if (!analysis) return html`<nav class="outline" aria-label="scenes"><p class="muted">Analysing…</p></nav>`;
  const problems = analysis.problems.filter((p) => p.severity === "error").length;
  return html`<nav class="outline" aria-label="scenes">
    <ol>
      ${analysis.scenes.map((scene) => html`
        <li key=${scene.index} class=${scene.index === current ? "current" : ""}>
          <button onClick=${() => onPick(scene.line)} title=${`line ${scene.line}`}>
            <span class="index">${scene.index}</span>
            <span class="title">${scene.title}</span>
            <span class="time">${scene.duration == null ? "?" : seconds(scene.duration)}</span>
            <span class="start">${seconds(scene.start)}</span>
          </button>
        </li>`)}
    </ol>
    <p class="total"><span>Total</span><span data-testid="total">${analysis.duration == null ? "?" : seconds(analysis.duration)}</span></p>
    ${problems > 0 && html`<p class="problems">${problems} problem${problems === 1 ? "" : "s"} to fix</p>`}
    ${analysis.notes && analysis.notes.length > 0 && html`<details class="notes"><summary>Notes</summary>
      <ul>${analysis.notes.map((n) => html`<li>${n}</li>`)}</ul></details>`}
  </nav>`;
}

/** The scene holding `line`: the last one starting at or before it. */
function sceneAt(analysis, line) {
  if (!analysis) return null;
  let found = null;
  for (const scene of analysis.scenes) if (scene.line - 1 <= line) found = scene.index;
  return found;
}

/** The moment the cursor points at: its scene, and the start of the paragraph it's in or after. */
function momentAt(analysis, line) {
  const index = sceneAt(analysis, line);
  const scene = analysis && analysis.scenes.find((s) => s.index === index);
  if (!scene || scene.duration == null) return null;
  let time = 0;
  for (const p of scene.paragraphs) if (p.line <= line) time = p.start;
  return { scene: scene.index, time, start: scene.start };
}

/** The moment `t` seconds into the video: its scene, the time into it, and the paragraph playing then. */
function momentOf(analysis, t) {
  const timed = analysis ? analysis.scenes.filter((s) => s.duration != null && s.duration > 0) : [];
  if (!timed.length) return null;
  const scene = timed.find((s) => t < s.start + s.duration) || timed[timed.length - 1];
  const time = Math.max(0, Math.min(t - scene.start, scene.duration - 1 / 30));
  let line = scene.line;
  for (const p of scene.paragraphs) if (p.start <= time + 1e-3) line = p.line;
  return { scene: scene.index, time, start: scene.start, line };
}

/** Build progress, and Cancel while it runs (#55). */
function BuildStatus({ build, onCancel }) {
  if (!build || build.state === "idle") return null;
  const text = {
    starting: "Starting the build…",
    running: build.of ? `Building: scene ${build.scene} of ${build.of}` : "Building…",
    done: `Built${build.summary ? `: ${build.summary.split(" (")[1]?.split(",")[0] || ""}` : ""}`,
    failed: "The build failed",
    cancelled: "Build cancelled",
  }[build.state] || build.state;
  return html`<span class=${`build-status ${build.state}`} data-testid="build">${text}
    ${(build.state === "running" || build.state === "starting") && html`<button class="quiet" onClick=${onCancel}>Cancel</button>`}
  </span>`;
}

/** The last build's video, with its notes. */
function Player({ build }) {
  if (!build || build.state !== "done") return html`<p class="muted">Build the video to watch it here.</p>`;
  return html`<div class="player">
    <video controls src=${build.video} poster=${build.poster} data-testid="video"></video>
    ${build.notes && build.notes.length > 0 && html`<details class="notes"><summary>Notes from the build</summary>
      <ul>${build.notes.map((n) => html`<li>${n}</li>`)}</ul></details>`}
  </div>`;
}

/** The frame at the cursor's moment, at the video's size, scaled to fit the pane. */
function Preview({ analysis, shown, moment, error, playback, onPlay, onStop, tab, onTab, build }) {
  const box = useRef(null);
  const [scale, setScale] = useState(0.4);
  const [w, h] = (analysis && analysis.size) || [1280, 720];
  useEffect(() => {
    if (!box.current) return;
    const observer = new ResizeObserver(([entry]) => setScale(entry.contentRect.width / w));
    observer.observe(box.current);
    return () => observer.disconnect();
  }, [w]);
  const frameStyle = `width:${w}px;height:${h}px;transform:scale(${scale})`;
  return html`<aside class="preview" aria-label="preview">
    <div class="tabs" role="tablist">
      <button role="tab" aria-selected=${tab === "frame"} onClick=${() => onTab("frame")}>Frame</button>
      <button role="tab" aria-selected=${tab === "video"} onClick=${() => onTab("video")}>Video</button>
    </div>
    ${tab === "video" ? html`<${Player} build=${build} />` : html`<div class="frame-tab">
    <div class="screen" ref=${box} style=${`height:${h * scale}px`}>
      ${shown && shown.kind === "frame" && html`<iframe title="frame" srcdoc=${shown.html} style=${frameStyle} tabindex="-1"></iframe>`}
      ${shown && shown.kind === "page" && html`<iframe title="frame" src=${shown.url} style=${frameStyle} tabindex="-1"></iframe>`}
    </div>
    <p class="caption" data-testid="moment">
      ${moment ? `scene ${moment.scene} · ${seconds(moment.time)} into it · ${seconds(moment.start + moment.time)} in the video` : "No scene here"}
      <span class="size">${w} × ${h}</span>
    </p>
    <div class="transport">
      ${playback.state === "playing"
        ? html`<button onClick=${onStop}>■ Stop</button>`
        : html`<button onClick=${onPlay} disabled=${!moment || playback.state === "synthesising"}>▶ Play scene</button>`}
      <span class="playback" data-testid="playback">${
        playback.state === "synthesising" ? `Synthesising scene ${playback.scene}…`
        : playback.state === "playing" ? `Playing scene ${playback.scene}: ${seconds(playback.time)} of ${seconds(playback.duration)}`
        : ""}</span>
    </div></div>`}
    ${error && html`<p class="preview-error">${error}</p>`}
  </aside>`;
}

function App() {
  const host = useRef(null);
  const editor = useRef(null);
  const version = useRef(null);
  const dirtyRef = useRef(false);
  const [name, setName] = useState("");
  const [dirty, setDirtyState] = useState(false);
  const [saving, setSaving] = useState(false);
  const [online, setOnline] = useState(true);
  const [notice, setNotice] = useState(null);
  const [error, setError] = useState(null);
  const [analysis, setAnalysisState] = useState(null);
  const analysisRef = useRef(null);
  const setAnalysis = (value) => { analysisRef.current = value; setAnalysisState(value); };
  const [cursorLine, setCursorLine] = useState(1);
  const [seek, setSeek] = useState(null);  // a moment chosen on the timeline, until the cursor moves (#60)
  const analyseTimer = useRef(null);
  const [shown, setShown] = useState(null);
  const [previewError, setPreviewError] = useState(null);
  const previewTimer = useRef(null);
  const [engine, setEngine] = useState(null);
  const audio = useRef(null);
  const sceneAudio = useRef(new Map());  // "analysis id:scene" -> {url, paragraphs, duration}
  const [playback, setPlayback] = useState({ state: "idle" });
  const [build, setBuild] = useState(null);
  const [tab, setTab] = useState("frame");
  const cursorMoment = analysis ? momentAt(analysis, cursorLine) : null;
  // While narration plays, the preview follows it paragraph by paragraph
  const playingMoment = playback.state === "playing" && playback.paragraphs
    ? { scene: playback.scene, start: playback.start,
        time: playback.paragraphs.filter((p) => p.start <= playback.time + 0.05).map((p) => p.start).pop() ?? 0 }
    : null;
  const moment = playingMoment || seek || cursorMoment;
  const playhead = playback.state === "playing" ? playback.start + playback.time
    : moment ? moment.start + moment.time : 0;

  const stop = useCallback(() => {
    if (audio.current) audio.current.pause();
    setPlayback({ state: "idle" });
  }, []);

  /** Play `sceneIndex` from `at` seconds, or the paragraph on `line` (or its start), synthesising it first if need be. */
  const play = useCallback(async (sceneIndex, line, at = null) => {
    const current = analysisRef.current;
    const scene = current && current.scenes.find((s) => s.index === sceneIndex);
    if (!scene) return;
    const key = `${current.id}:${sceneIndex}`;
    let track = sceneAudio.current.get(key);
    if (!track) {
      if (current.engine === "elevenlabs" && scene.missing_chars > 0
          && !window.confirm(`Synthesise scene ${sceneIndex} with ElevenLabs? It sends ${scene.missing_chars} characters.`)) return;
      setPlayback({ state: "synthesising", scene: sceneIndex });
      const { status, body } = await getJSON(`/api/scenes/${sceneIndex}/audio`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ id: current.id }),
      }).catch((e) => ({ status: 0, body: { error: e.message } }));
      if (status === 409) { setPlayback({ state: "idle" }); scheduleAnalysis(); return; }
      if (status !== 200) { setPlayback({ state: "idle" }); setError(body.error || `no narration (${status})`); return; }
      track = body;
      sceneAudio.current.set(key, track);
      scheduleAnalysis();  // the speech is cached now: exact timing replaces the estimates
    }
    const from = at ?? (track.paragraphs.find((p) => p.line === line) || { start: 0 }).start;
    if (!audio.current) {
      audio.current = new Audio();
      audio.current.addEventListener("timeupdate", () =>
        setPlayback((pb) => (pb.state === "playing" ? { ...pb, time: audio.current.currentTime } : pb)));
      audio.current.addEventListener("ended", () => setPlayback({ state: "idle" }));
    }
    audio.current.src = track.url;
    audio.current.currentTime = from;
    setPlayback({ state: "playing", scene: sceneIndex, start: scene.start, time: from, duration: track.duration,
                  paragraphs: track.paragraphs });
    await audio.current.play().catch((e) => { setPlayback({ state: "idle" }); setError(`can't play: ${e.message}`); });
  }, []);

  const pickEngine = useCallback(async (value) => {
    const { status, body } = await getJSON("/api/engine", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ engine: value }),
    });
    if (status !== 200) { setError(body.error || `can't switch to ${value}`); setEngine(body.engine || engine); return; }
    setEngine(body.engine);
    setError(null);
    sceneAudio.current.clear();
    scheduleAnalysis();
  }, [engine]);

  const setDirty = (value) => { dirtyRef.current = value; setDirtyState(value); };

  const analyse = useCallback(async () => {
    const view = editor.current.view;
    const sent = view.state.doc;
    try {
      const { status, body } = await getJSON("/api/analyse", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text: sent.toString() }),
      });
      if (view.state.doc !== sent) return;  // typed since: the next analysis is on its way
      if (status !== 200) { setError(body.error || `analysis failed (${status})`); return; }
      showAnalysis(view, body);
      setAnalysis(body);
      setEngine(body.engine);
    } catch {
      /* offline: the event stream reports it */
    }
  }, []);

  const scheduleAnalysis = useCallback(() => {
    clearTimeout(analyseTimer.current);
    analyseTimer.current = setTimeout(analyse, ANALYSE_AFTER_MS);
  }, [analyse]);

  const load = useCallback(async () => {
    const { body } = await getJSON("/api/script");
    version.current = body.version;
    setName(body.name);
    if (editor.current) editor.current.replace(body.text);
    else editor.current = createEditor(host.current, body.text, {
      onChange: () => setDirty(true),
      onSave: () => save(false),
      onCursor: (line, docChanged, followed) => {
        setCursorLine(line);
        if (!followed) setSeek(null);  // the user moved on: the preview follows the cursor again
        if (docChanged) scheduleAnalysis();
      },
    });
    setDirty(false);
    setNotice(null);
    scheduleAnalysis();
  }, [scheduleAnalysis]);

  const save = useCallback(async (force) => {
    setSaving(true);
    try {
      let base = version.current;
      if (force) base = (await getJSON("/api/script")).body.version;
      const { status, body } = await getJSON("/api/script", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: editor.current.text(), version: base }),
      });
      if (status === 409) { setNotice({ kind: "conflict" }); return false; }
      if (status !== 200) { setError(body.error || `saving failed (${status})`); return false; }
      version.current = body.version;
      setDirty(false);
      setNotice(null);
      setError(null);
      return true;
    } catch (e) {
      setError(`saving failed: ${e.message}`);
      return false;
    } finally {
      setSaving(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  // The last build survives a reload
  useEffect(() => { getJSON("/api/build").then(({ body }) => setBuild(body)).catch(() => {}); }, []);

  const startBuild = useCallback(async () => {
    if (dirtyRef.current && !(await save(false))) return;  // builds the file on disk, so save first
    const { status, body } = await getJSON("/api/build", { method: "POST" });
    if (status !== 202) setError(body.error || `can't build (${status})`);
    else setBuild(body);
  }, [save]);

  const cancelBuild = useCallback(() => getJSON("/api/build/cancel", { method: "POST" }), []);

  /** Show the moment `t` seconds into the video, with the editor's cursor on the paragraph playing then. */
  const seekTo = useCallback((t) => {
    const found = momentOf(analysisRef.current, t);
    if (!found) return;
    if (audio.current && !audio.current.paused) stop();
    setSeek(found);
    followLine(editor.current.view, found.line);
  }, [stop]);

  // A paragraph's play button (editor.js) plays its scene from there
  useEffect(() => {
    const listener = (e) => play(sceneAt(analysisRef.current, e.detail.line), e.detail.line);
    window.addEventListener("narrate-play", listener);
    return () => window.removeEventListener("narrate-play", listener);
  }, [play]);

  // The preview follows the cursor, and a new analysis
  useEffect(() => {
    clearTimeout(previewTimer.current);
    if (!analysis || !moment) return;
    previewTimer.current = setTimeout(async () => {
      const { status, body } = await getJSON("/api/frame", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id: analysis.id, scene: moment.scene, time: moment.time }),
      }).catch(() => ({ status: 0, body: {} }));
      if (status === 200) { setShown(body); setPreviewError(null); }
      else if (status === 409) scheduleAnalysis();
      else if (status) setPreviewError(body.error || `no preview (${status})`);
    }, PREVIEW_AFTER_MS);
  }, [analysis, moment && moment.scene, moment && moment.time]);

  useEffect(() => {
    const events = new EventSource("/api/events");
    events.addEventListener("open", () => setOnline(true));
    events.addEventListener("error", () => setOnline(false));
    events.addEventListener("build", (e) => {
      const status = JSON.parse(e.data);
      setBuild(status);
      if (status.state === "done") setTab("video");
    });
    events.addEventListener("script-changed", (e) => {
      const changed = JSON.parse(e.data);
      if (changed.version === version.current) return;  // our own save
      if (!dirtyRef.current) load();
      else setNotice({ kind: "changed" });
    });
    return () => events.close();
  }, [load]);

  useEffect(() => {
    document.title = `${dirty ? "● " : ""}${name || "narrate"} · narrate studio`;
  }, [name, dirty]);

  useEffect(() => {
    // Mod-S anywhere on the page; the editor handles it itself when focused
    const key = (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key === "s" && !e.defaultPrevented) { e.preventDefault(); save(false); }
    };
    window.addEventListener("keydown", key);
    return () => window.removeEventListener("keydown", key);
  }, [save]);

  useEffect(() => {
    const warn = (e) => { if (dirtyRef.current) { e.preventDefault(); e.returnValue = ""; } };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, []);

  const status = !online ? "Offline: reconnecting…" : saving ? "Saving…" : dirty ? "Unsaved changes" : "Saved";
  return html`
    <header class="bar">
      <span class="brand">narrate studio</span>
      <span class="file" title="the script being edited">${name}</span>
      ${engine && html`<${EnginePicker} engine=${engine} onPick=${pickEngine} />`}
      <${Cost} analysis=${analysis} />
      <span class=${`status ${dirty ? "unsaved" : ""} ${online ? "" : "offline"}`} data-testid="status">${status}</span>
      <button onClick=${() => save(false)} disabled=${saving || !dirty}>Save</button>
      <${BuildStatus} build=${build} onCancel=${cancelBuild} />
      <button class="primary" onClick=${startBuild}
        disabled=${build && (build.state === "running" || build.state === "starting")}>Build video</button>
    </header>
    <${Notice} notice=${notice} onReload=${load} onOverwrite=${() => save(true)} onDismiss=${() => setNotice(null)} />
    ${error && html`<div class="notice error" role="alert">${error}</div>`}
    ${build && build.state === "failed" && html`<div class="notice error" role="alert" data-testid="build-errors">
      <span>The build failed:</span>
      ${build.errors.map((e) => e.line
        ? html`<button class="quiet" onClick=${() => goToLine(editor.current.view, e.line)}>line ${e.line}: ${e.message}</button>`
        : html`<span class="build-error">${e.message}</span>`)}
    </div>`}
    <main class="workspace">
      <${Outline} analysis=${analysis} current=${sceneAt(analysis, cursorLine)}
        onPick=${(line) => goToLine(editor.current.view, line)} />
      <section class="editor" ref=${host} aria-label="script"></section>
      <${Preview} analysis=${analysis} shown=${shown} moment=${moment} error=${previewError} playback=${playback}
        onPlay=${() => (seek ? play(seek.scene, seek.line, seek.time) : cursorMoment && play(cursorMoment.scene, cursorLine))}
        onStop=${stop} tab=${tab} onTab=${setTab} build=${build} />
    </main>
    <${Timeline} analysis=${analysis} playhead=${playhead} onSeek=${seekTo}
      onLine=${(line) => goToLine(editor.current.view, line)} />`;
}

render(html`<${App} />`, document.getElementById("app"));
