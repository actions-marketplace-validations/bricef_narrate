# narrate studio: an authoring UI

A local web app for writing and directing one narrate script, served by
`narrate studio script.md`. This page records what it is for, how it is laid
out, and the decisions behind it, with the reasons for each. Tracked in
narrate #28.

## What authoring narrate involves

- **Words make time.** A scene lasts as long as its narration, and pictures,
  cues and subtitles hang off that timeline. From the command line, that
  timeline is invisible until a render finishes.
- **Two kinds of work, often interleaved.**
  - **Writing:** structure and wording. Text is the fastest medium for this.
  - **Directing:** placement, timing, sync and polish. Text is awkward for
    callout coordinates, crops, zoom paths or where a mark goes.
- **Real costs.** ElevenLabs characters (money) and render minutes (time).
  An author should know what an action will spend before taking it.

The studio exists to shorten the loop from writing to seeing and hearing the
result, which today means a full render of the whole video.

## Principles

1. **The script file is the source of truth.** The studio edits the `.md`
   file, so editing it elsewhere, diffing it in git and building it in CI all
   keep working. There is no project database.
2. **Text first, with structure alongside.** A real editor for the script,
   with views of its structure and timing next to it. No form or block editor
   that hides the text.
3. **Direct manipulation for what text does badly.** Drawing a callout,
   dragging a crop, choosing a voice by ear. Each writes ordinary script text.
4. **Every layer previews cheaply,** from instant (structure, frames) to exact
   (one scene, then the whole video).
5. **Time and sync are visible:** scene and paragraph durations, where cues
   land, how pictures share a scene.
6. **Cost is visible before it is spent.** Free engines while drafting.
7. **Local first:** one command, offline, in Docker and over a tunnel.

## The screen

```
┌───────────┬─────────────────────────────────────┬─────────────────────────┐
│ Project   │ intro.md                       ● ✓  │ Preview (follows cursor)│
│ intro.md  │ ---                                 │ ┌─────────────────────┐ │
│ scenes/   │ voice: Lily · loudness: -16         │ │   frame at 0:03.2   │ │
│ assets/   │ ─── 1 · title · 8.4 s ───────────── │ └─────────────────────┘ │
│           │ ![](scenes/title.html)              │ ◀ ▶  0:03.2 / 1:22.7 🔊 │
│           │ This is factor-q: a self-…   ▶ 3.9s │ Inspector               │
├───────────┴─────────────────────────────────────┴─────────────────────────┤
│ timeline: scenes by duration · narration · cues                          │
└──────────────────────────────────────────────────────────────────────────┘
```

- **Editor:** the script, with each scene's separator showing its number and
  duration, a play button and length beside each paragraph, and
  `narrate check` problems inline.
- **Preview:** the frame at the cursor's moment, with playback of that scene.
- **Inspector** (milestone 2): controls for whatever is under the cursor.
- **Timeline** (milestone 2): the whole video, with scenes sized by duration.

## Decisions

### D1. A text-first editor, with structure alongside

Decided with the author (2026-10-09).
- **Why:** the script is compact, diffable text, and writing narration is
  fastest as text.
- **Alternative rejected:** scene cards. They make reordering easy, but slow
  down writing and put a second representation between the author and the
  file.

### D2. One script per session

Decided with the author: `narrate studio script.md` serves that script and the
files beside it. A workspace over many projects can come later.

### D3. No authentication yet

Decided with the author.
- **Address:** the server binds to `127.0.0.1:8787` by default; `--host` and
  `--port` change it. On the nest guest, use `--host 0.0.0.0` to reach it over
  WireGuard, or an SSH tunnel.
- **Exposure:** it can read every file in the project folder and run builds,
  so expose it only to networks you trust until access control is added.

### D4. Python and Starlette for the server

- **In-process reuse:** the server runs inside narrate, so it uses the parser,
  planner, frame HTML and speech cache directly. Nothing about the script
  format is reimplemented in the browser.
- **Starlette with uvicorn:** a small ASGI framework that serves static files,
  JSON and long-lived event streams, and its `TestClient` makes the server
  testable without a browser.
- **Alternatives:**
  - The standard library's `http.server` has no async I/O for event streams.
  - FastAPI adds a validation layer the API doesn't need.
  - aiohttp would do, but Starlette's testing story is better.

### D5. Events by server-sent events; commands by JSON over HTTP

- **Events:** the server pushes changes to the browser (the file changed on
  disk, build progress, audio ready) over one SSE stream.
- **Commands:** the browser acts with ordinary requests.
- **Why not WebSockets:** nothing needs to flow both ways continuously, and
  SSE is plain HTTP, reconnects by itself and passes through any proxy or
  tunnel.

### D6. Heavy work off the event loop, builds in a subprocess

- **Builds** (whole video or one scene) run `narrate build` as a child
  process. Playwright's sync API can't run on the event loop or share a
  browser across threads, and a separate process isolates Chromium and
  ffmpeg, can be cancelled by killing it, and reports progress through its
  log lines.
- **Analysis and speech** (parsing, planning, synthesis) run in worker
  threads, because they're fast or free of Playwright.

### D7. No build step for the studio's own code

- **Studio code:** plain ES modules served as they are. UI components use
  Preact through htm, which writes markup as tagged template literals instead
  of JSX. htm publishes a single-file module with Preact built in, which narrate
  vendors.
- **Editor:** CodeMirror 6, which has no single-file release. narrate vendors
  one bundle made by `scripts/vendor-codemirror.sh`, which pins every package
  version and esbuild. Node is needed only to run that script, when updating
  CodeMirror.
- **Why:** narrate is a Python project. Without a JavaScript toolchain in the
  everyday loop, a change is an edit and a browser refresh. The studio's tests
  drive it with the Playwright and Chromium narrate already depends on, so
  they run without Node, and the pip and uv install needs nothing extra.
- **Alternatives:**
  - Svelte or Preact with a Vite build: nicer component syntax, but a Node
    build in every change and built files to ship or commit.
  - Plain DOM code: no dependency, but too much hand-written state for the
    editor, preview and timeline together.

### D8. Saving and external edits

- **Saving:** the editor saves the whole file, sending the modification time
  it last loaded. If the file changed on disk in between, the server refuses,
  and the studio offers to reload or overwrite.
- **External edits:** a watcher polls the script, and the files it references,
  twice a second and announces changes over the event stream. That's a
  handful of files, so a dependency such as `watchfiles` isn't worth adding.

### D9. Previews reuse the renderer's code

- **Timing:** narrate's planner, with a speech engine that answers from the
  real engine's cache where it can and estimates from text length where it
  can't. Durations sharpen as audio is synthesised.
- **Frames:** the HTML that `frames.py` composes for a build, with project
  files served over HTTP instead of `file://`, shown in an iframe. The preview
  is the build's own composition, drawn by the user's browser instead of
  headless Chromium.
- **Narration:** a scene's audio is the planner's own track for that scene,
  synthesised by the chosen engine and cached as usual. Paragraph play
  buttons start it at that paragraph.

### D10. Engines and cost

- **Default:** the studio previews with Kokoro, which is free, unless you
  choose otherwise. ElevenLabs is an explicit choice.
- **Shown before you spend:** which paragraphs are already cached, and how
  many characters would be sent.
- **Builds** use the engine the session uses.

### D11. Where the studio writes

- **Video:** "Build" writes the same files as `narrate build` would, next to
  the script (`intro.mp4`, `intro.jpg`).
- **Scratch files:** scene audio and single-scene renders go in a temporary
  folder for the session.
- **Unchanged:** the speech, render and capture caches work exactly as for the
  command line.

## API

| Request | Does |
| --- | --- |
| `GET /` | the app |
| `GET /api/script` | the script's text and modification time |
| `PUT /api/script` | save `{text, mtime}`; 409 if the file changed meanwhile |
| `POST /api/analyse` | parse, check and plan `{text}`: scenes with times, blocks with lines, problems |
| `GET /api/frame` | the frame HTML for a scene at a moment |
| `POST /api/scenes/{n}/audio` | synthesise a scene's narration; returns a WAV URL and paragraph start times |
| `GET /api/peaks/{sound}` | a scene's waveform, as min/max pairs, by the sound id the analysis gives |
| `POST /api/build` | start a build; progress over the event stream |
| `GET /api/events` | the event stream (SSE) |
| `GET /files/{path}` | the project's own files, nothing outside its folder |

## Milestones

1. **M1, a working loop:**
   - the server and editor, with saving and live reload of outside edits
     (#51);
   - live problems and a scene outline with durations (#52);
   - a frame preview that follows the cursor (#53);
   - per-paragraph narration playback (#54);
   - building from the studio, with progress and a player (#55).
2. **M2, directing (#56):** the timeline with real durations and waveforms; an
   inspector for pictures (crop, focal point, zoom path), callouts drawn on the
   preview, voice audition; exact single-scene renders.
3. **M3, HTML scenes and render blocks (#57):** a scrubbable page preview
   using the renderer's own seeking, marks placed by clicking words, and live
   previews of Mermaid and other render blocks.
