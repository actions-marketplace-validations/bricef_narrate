// The voice picker (#65): every voice, auditioned by ear with a sample of the script, chosen for the
// whole script or from the cursor, and names pinned to engine voices in the project's voices.yaml.
import { html, useEffect, useRef, useState } from "./vendor/htm-preact.js";

const GROUPS = [
  ["pinned", "Pinned names", "names in voices.yaml, as pinned for each engine"],
  ["kokoro", "Kokoro", "Kokoro's own voices"],
  ["elevenlabs", "ElevenLabs", "ElevenLabs' default voices"],
  ["narakeet", "Narakeet names", "Narakeet's voice names, matched by language and gender"],
];
const GENDER = { f: "female", m: "male" };
const ENGINES = { kokoro: "Kokoro", elevenlabs: "ElevenLabs", silent: "the silent engine" };

async function post(url, body, method = "POST") {
  const response = await fetch(url, { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  return { status: response.status, body: await response.json().catch(() => ({})) };
}

/** The project's pins, editable: a name, and the voice it becomes on each engine. */
function Pins({ catalogue, onSaved }) {
  const [rows, setRows] = useState([]);
  const [error, setError] = useState(null);
  useEffect(() => {
    setRows(Object.entries(catalogue.pins || {}).map(([name, engines]) => ({ name, kokoro: engines.kokoro || "", elevenlabs: engines.elevenlabs || "" })));
  }, [catalogue]);
  const kokoro = catalogue.voices.filter((v) => v.group === "kokoro").map((v) => v.name);
  const eleven = catalogue.voices.filter((v) => v.group === "elevenlabs").map((v) => v.name);
  const set = (k, key, value) => setRows(rows.map((r, n) => (n === k ? { ...r, [key]: value } : r)));
  const save = async () => {
    const pins = Object.fromEntries(rows.filter((r) => r.name.trim()).map((r) => [r.name.trim(), { kokoro: r.kokoro, elevenlabs: r.elevenlabs }]));
    const { status, body } = await post("/api/voices/pins", { pins }, "PUT");
    if (status !== 200) { setError(body.error || `couldn't save (${status})`); return; }
    setError(null);
    onSaved();
  };
  const user = Object.entries(catalogue.user_pins || {});
  return html`<section class="pins">
    <h4>Pinned names <span class="muted small">voices.yaml next to the script</span></h4>
    <table>
      <thead><tr><th>Name</th><th>Kokoro</th><th>ElevenLabs</th><th></th></tr></thead>
      <tbody>${rows.map((r, k) => html`<tr>
        <td><input aria-label="pinned name" value=${r.name} onInput=${(e) => set(k, "name", e.target.value)} /></td>
        <td><select aria-label=${`${r.name || "new"} on Kokoro`} value=${r.kokoro} onChange=${(e) => set(k, "kokoro", e.target.value)}>
          <option value="">(not pinned)</option>${kokoro.map((v) => html`<option value=${v}>${v}</option>`)}</select></td>
        <td><select aria-label=${`${r.name || "new"} on ElevenLabs`} value=${r.elevenlabs} onChange=${(e) => set(k, "elevenlabs", e.target.value)}>
          <option value="">(not pinned)</option>${eleven.map((v) => html`<option value=${v}>${v}</option>`)}
          ${r.elevenlabs && !eleven.includes(r.elevenlabs) && html`<option value=${r.elevenlabs}>${r.elevenlabs}</option>`}</select></td>
        <td><button class="quiet" title="unpin" onClick=${() => setRows(rows.filter((_, n) => n !== k))}>✕</button></td>
      </tr>`)}</tbody>
    </table>
    <p class="row"><button class="quiet" onClick=${() => setRows([...rows, { name: "", kokoro: "", elevenlabs: "" }])}>+ Pin a name</button>
      <button onClick=${save}>Save pins</button></p>
    ${error && html`<p class="preview-error">${error}</p>`}
    ${user.length > 0 && html`<p class="muted small">Also pinned in ${catalogue.user_file} (not changed here):
      ${user.map(([name, engines]) => `${name} (${Object.entries(engines).map(([e, v]) => `${e}: ${v}`).join(", ")})`).join("; ")}</p>`}
  </section>`;
}

/** Every voice, to audition and choose. `sampleAt()` is the narration at the cursor; `onChoose(voice, where)`
    writes it for the "script" (the header) or from "here" (the cursor's paragraph). */
export function VoicePicker({ engine, getText, sampleAt, current, onChoose, busy, refresh }) {
  const [catalogue, setCatalogue] = useState(null);
  const [error, setError] = useState(null);
  const [filter, setFilter] = useState("");
  const [sample, setSample] = useState("");
  const [where, setWhere] = useState("script");
  const [playing, setPlaying] = useState(null);  // {name, state: "synthesising" | "playing"}
  const audio = useRef(null);
  const load = () => fetch("/api/voices").then((r) => r.json().then((body) => ({ ok: r.ok, body })))
    .then(({ ok, body }) => { if (ok) { setCatalogue(body); setError(body.problem); } else setError(body.error); })
    .catch((e) => setError(e.message));
  useEffect(() => { load(); }, [engine, refresh]);
  useEffect(() => { setSample(sampleAt() || ""); }, []);
  useEffect(() => () => audio.current && audio.current.pause(), []);
  if (!catalogue) return html`<p class="muted">${error || "Loading voices…"}</p>`;

  const audition = async (name) => {
    if (audio.current) audio.current.pause();
    const body = { text: getText(), voice: name, sample };
    if (catalogue.engine === "elevenlabs") {
      const dry = await post("/api/voices/audition", { ...body, dry: true });
      if (dry.status !== 200) { setError(dry.body.error); return; }
      if (!dry.body.cached && !window.confirm(`Audition ${name} with ElevenLabs? It sends ${dry.body.characters} characters.`)) return;
    }
    setPlaying({ name, state: "synthesising" });
    const { status, body: result } = await post("/api/voices/audition", body);
    if (status !== 200) { setPlaying(null); setError(result.error || `couldn't audition ${name} (${status})`); return; }
    setError(null);
    if (!audio.current) {
      audio.current = new Audio();
      audio.current.addEventListener("ended", () => setPlaying(null));
    }
    audio.current.src = result.url;
    setPlaying({ name, state: "playing" });
    audio.current.play().catch((e) => { setPlaying(null); setError(`can't play: ${e.message}`); });
  };
  const needle = filter.trim().toLowerCase();
  const matches = (v) => !needle || v.name.toLowerCase().includes(needle) || (v.lang || "").includes(needle)
    || (v.resolves || "").toLowerCase().includes(needle);
  const isCurrent = (v) => current && v.name.toLowerCase() === current.toLowerCase();
  return html`<section class="voices" data-testid="voices">
    <div class="row">
      <label class="sample">Sample <textarea rows="2" aria-label="sample" value=${sample} placeholder="This is how this voice reads your script."
        onInput=${(e) => setSample(e.target.value)}></textarea></label>
    </div>
    <div class="row">
      <span class="muted small">Use for</span>
      <label class="small"><input type="radio" name="voice-where" checked=${where === "script"} onChange=${() => setWhere("script")} /> the whole script</label>
      <label class="small"><input type="radio" name="voice-where" checked=${where === "here"} onChange=${() => setWhere("here")} /> from the cursor on</label>
      <input class="filter" type="search" placeholder="Find a voice or language" aria-label="find a voice" value=${filter}
        onInput=${(e) => setFilter(e.target.value)} />
    </div>
    <p class="muted small">Auditions use ${catalogue.engine === "elevenlabs" ? "ElevenLabs, which asks before spending"
      : `${ENGINES[catalogue.engine] || catalogue.engine}, which is free`}; each sample is cached once heard.</p>
    ${error && html`<p class="preview-error">${error}</p>`}
    ${GROUPS.map(([group, title, hint]) => {
      const voices = catalogue.voices.filter((v) => v.group === group && matches(v));
      if (!voices.length) return null;
      return html`<details open=${group !== "narakeet" || Boolean(needle)} class="voice-group">
        <summary>${title} <span class="muted small">${hint}</span></summary>
        <ul>${voices.map((v) => html`<li class=${isCurrent(v) ? "current" : ""} data-voice=${v.name}>
          <button class="quiet play" aria-label=${`audition ${v.name}`} disabled=${playing && playing.state === "synthesising"}
            onClick=${() => (playing && playing.name === v.name && playing.state === "playing" ? (audio.current.pause(), setPlaying(null)) : audition(v.name))}>
            ${playing && playing.name === v.name ? (playing.state === "playing" ? "■" : "…") : "▶"}</button>
          <span class="name">${v.name}</span>
          <span class="muted small">${[v.lang, GENDER[v.gender]].filter(Boolean).join(" · ")}</span>
          ${v.resolves && v.resolves.toLowerCase() !== v.name.toLowerCase() && html`<span class="muted small resolves" title=${`on ${ENGINES[catalogue.engine] || catalogue.engine}`}>→ ${v.resolves}</span>`}
          <button class="use" disabled=${busy} onClick=${() => onChoose(v.name, where)}>Use</button>
        </li>`)}</ul>
      </details>`;
    })}
    <${Pins} catalogue=${catalogue} onSaved=${load} />
  </section>`;
}
