// narrate studio: the app shell (docs/design/studio.md).
import { html, render, useCallback, useEffect, useRef, useState } from "./vendor/htm-preact.js";
import { createEditor } from "./editor.js";

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

  const setDirty = (value) => { dirtyRef.current = value; setDirtyState(value); };

  const load = useCallback(async () => {
    const { body } = await getJSON("/api/script");
    version.current = body.version;
    setName(body.name);
    if (editor.current) editor.current.replace(body.text);
    else editor.current = createEditor(host.current, body.text, {
      onChange: () => setDirty(true),
      onSave: () => save(false),
    });
    setDirty(false);
    setNotice(null);
  }, []);

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
      <span class=${`status ${dirty ? "unsaved" : ""} ${online ? "" : "offline"}`} data-testid="status">${status}</span>
      <button class="primary" onClick=${() => save(false)} disabled=${saving || !dirty}>Save</button>
    </header>
    <${Notice} notice=${notice} onReload=${load} onOverwrite=${() => save(true)} onDismiss=${() => setNotice(null)} />
    ${error && html`<div class="notice error" role="alert">${error}</div>`}
    <main class="workspace">
      <section class="editor" ref=${host} aria-label="script"></section>
    </main>`;
}

render(html`<${App} />`, document.getElementById("app"));
