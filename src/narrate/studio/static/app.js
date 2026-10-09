// narrate studio: the app shell (docs/design/studio.md).
import { html, render, useCallback, useEffect, useRef, useState } from "./vendor/htm-preact.js";
import { createEditor, goToLine, seconds, showAnalysis } from "./editor.js";

const ANALYSE_AFTER_MS = 300;

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
  const [analysis, setAnalysis] = useState(null);
  const [cursorLine, setCursorLine] = useState(1);
  const analyseTimer = useRef(null);

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
      onCursor: (line, docChanged) => { setCursorLine(line); if (docChanged) scheduleAnalysis(); },
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
      if (status === 409) { setNotice({ kind: "conflict" }); return; }
      if (status !== 200) { setError(body.error || `saving failed (${status})`); return; }
      version.current = body.version;
      setDirty(false);
      setNotice(null);
      setError(null);
    } catch (e) {
      setError(`saving failed: ${e.message}`);
    } finally {
      setSaving(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    const events = new EventSource("/api/events");
    events.addEventListener("open", () => setOnline(true));
    events.addEventListener("error", () => setOnline(false));
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
      <${Cost} analysis=${analysis} />
      <span class=${`status ${dirty ? "unsaved" : ""} ${online ? "" : "offline"}`} data-testid="status">${status}</span>
      <button class="primary" onClick=${() => save(false)} disabled=${saving || !dirty}>Save</button>
    </header>
    <${Notice} notice=${notice} onReload=${load} onOverwrite=${() => save(true)} onDismiss=${() => setNotice(null)} />
    ${error && html`<div class="notice error" role="alert">${error}</div>`}
    <main class="workspace">
      <${Outline} analysis=${analysis} current=${sceneAt(analysis, cursorLine)}
        onPick=${(line) => goToLine(editor.current.view, line)} />
      <section class="editor" ref=${host} aria-label="script"></section>
    </main>`;
}

render(html`<${App} />`, document.getElementById("app"));
