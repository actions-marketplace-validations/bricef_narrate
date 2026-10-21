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
  `--port` change it. On the nest guest, use `--host 0.0.0.0` with
  `--allow-host` for the name it's opened by, to reach it over WireGuard, or
  an SSH tunnel.
- **Exposure:** it can read every file in the project folder and run builds,
  so expose it only to networks you trust until access control is added.
- **Pages in your browser (#93):** any page you have open can send requests to
  localhost, so the studio checks where each request comes from:
  - **Host names:** it answers only to `localhost`, `127.0.0.1`, `[::1]`, its
    `--host` address and each `--allow-host`; anything else gets 403. A page
    that points its own name at 127.0.0.1 can't read its answers.
  - **Origin:** a request that changes something gets 403 when its `Origin`
    isn't one of those names on the port it was sent to. Browsers send an
    `Origin` with every such request; programs and curl don't.
  - **No CORS:** the API sends no CORS headers, so other sites' pages can't
    read its answers. Only the preview's own pages get one (D17).
  - **No framing:** other sites can't show the studio in a frame (D17).
  - **Docker:** in the container it binds `0.0.0.0`, and the browser opens it
    as `localhost` or `127.0.0.1`, so publishing the port on `127.0.0.1` needs
    no other option.
- **Pages in your project (#93):** they run sandboxed, so they can't use the
  studio either (D17).

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
  one bundle made by `scripts/vendor.sh codemirror`, which pins every package
  version and esbuild. The fake clock for HTML scenes (D12) is bundled the same
  way. Node is needed only to run that script, when updating a bundle.
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
  files served over HTTP instead of `file://`, shown in a sandboxed iframe
  (D17). The preview is the build's own composition, drawn by the user's
  browser instead of headless Chromium.
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

- **Script:** the `.md` file, on Save; every direct manipulation edits its
  text in the editor first.
- **Voice pins:** the project's `voices.yaml`, when pins are saved in the
  voice picker (#65), written in one step and checked as a build reads it.
  The user-level file is only read.
- **Video:** "Build" writes the same files as `narrate build` would, next to
  the script (`intro.mp4`, `intro.jpg`).
- **Scratch files:** scene audio and single-scene renders go in a temporary
  folder for the session.
- **Unchanged:** the speech, render and capture caches work exactly as for the
  command line.

### D12. HTML scenes are scrubbed in the browser

- **How:** the preview runs the page in the studio's own browser, on a fake
  clock. `/pages/` serves it with three scripts ahead of its own:
  - the fake clock (`@sinonjs/fake-timers`, vendored);
  - the renderer's own seeking, `pages._SEEK_JS`, served from the same string
    so the two never drift;
  - the cue script a build gives the page.

  The studio posts the page its time. `page-clock.js`, in the page, then
  moves the clock on a frame at a time, as a build does, and seeks every
  animation after each step. While the scene plays, the studio posts the
  narration's time on every animation frame.
- **Going back:** timers can't run backwards.
  - A page with scripts of its own reloads and runs forward to the moment.
  - A page without scripts seeks straight there.
- **Its address:** the page's path in the project, under the session's key
  (D17), plus its version and cues.
  - Its relative files load naturally.
  - Moving the moment never reloads it; a new cue or an edited file does.
- **Exactness:** the clock steps and seeking are the build's own, but the
  browser is the user's, which may differ from narrate's Chromium in fonts or
  features. **Render scene** stays the exact check.
- **Alternatives:**
  - *Frames rendered by the server's headless Chromium:* exact, but a round
    trip and a screenshot for every moment, so scrubbing and playing would
    stutter.
  - *Playwright's own clock in the browser:* the build's clock is Playwright's,
    but it's compiled into Playwright's driver and not published on its own.
    fake-timers is the library it was forked from.

### D13. Overlays are previewed as stacked pages

Each overlay (#59) is a transparent page over the frame, in the build's order
(the scene's, then the video's). Each runs on its own clock (the scene's or
the video's) with D12's runtime, so the preview shows what a build lays on
top.
- **The video's clock:** a video overlay's address is the same in every
  scene, so its page runs on across cuts instead of reloading. Scenes start
  on whole frames, as a build counts them.
- **Transparency:** each overlay iframe declares the light colour scheme
  its page has by default. Otherwise a browser showing the studio in dark
  mode paints the page opaque, because the schemes differ.

### D14. Marks are placed by an edit, in narration as it's written

Adding a mark at a word is a direct manipulation like the others (D11): the
server writes `<mark name="…"/>` before the word, and the editor applies it as
one undoable change.
- **Plain paragraphs take marks** (#75) and stay plain, rather than being
  wrapped in `<speak>` as first planned. Converting plain markup to SSML
  can't keep the speech identical:
  - emphasis and ellipses pause where SSML doesn't, so matching them would
    take `<break>`s through the user's text;
  - pinyin and jyutping spans have no SSML form;
  - an escaped `&` shows in subtitles.

  A mark in plain text splits the speech there without a pause, as in SSML,
  and changes nothing else. A test checks this for every word of paragraphs
  with each kind of markup.
- **Where it goes:** before the whole token the word is in (the voice reads
  `A&B` as one), and before markup it can't go inside: code, spans and links
  in plain text; `say-as`, `phoneme` and `sub` in SSML.
- **Positions:** the editor counts UTF-16 units, the server characters; the
  server converts at its edge, for every edit.

### D15. Mermaid is drawn live with narrate's own copy

The preview draws a diagram in the browser from the text being typed. It uses
the page a build draws it with and the mermaid.js narrate already pins and
checks for builds, so the preview and the video agree and there's no second
copy to vendor.

### D16. A web capture is retaken by a scene render

**Retake capture** renders the scene with `--regenerate`. That reuses the
scene render's child process, progress and **Cancel** (D6), and stores the
capture where a build would. No new command or code path is needed.

### D17. Project pages run sandboxed, in origins of their own

A project may come from someone else: a ZIP project, a shared repository. Its
HTML scenes, overlays and slides used to run in the preview with the studio's
own origin, so they could use its API as the app does (#93).
- **Sandboxed frames:** every frame in the preview has
  `sandbox="allow-scripts"`, without `allow-same-origin`. That's HTML scenes,
  overlays, and the frame composed for slides, pictures and Mermaid, whose
  slides may carry HTML of their own.
- **Opened on their own:** `/pages/` sends
  `Content-Security-Policy: sandbox allow-scripts`, so a page opened outside
  the app is sandboxed too. `/files/` and `/scratch/` send `sandbox`.
- **What that defends:** a sandboxed page's origin is opaque.
  - A request it sends to change something carries `Origin: null`, which the
    studio refuses (D3).
  - The API sends no CORS headers, so the page can't read the script, the
    voices or the build's state.
  - It can't reach into the app's page, open windows or move the app
    elsewhere.
- **Its own files:** a page's fonts, module scripts and `fetch()` are
  cross-origin requests from its sandbox, which need CORS.
  - `/pages/` answers them with `Access-Control-Allow-Origin: null`, but only
    under a random key in the address, made for each session.
  - The key is only in `/api/frame`'s answers, which other sites can't read,
    so their sandboxed pages can't read the project.
  - The preview's frames load every project file from there, and a page's
    relative files resolve there, so they load as in a build.
- **What a page loses:** storage (`localStorage`, cookies, IndexedDB), and
  reading back the pixels of its own pictures from a canvas, unless it loads
  them with `crossorigin`. A build's page has both. **Render scene** stays the
  exact check.
- **Messages:** the app posts each page its time to `"*"`, since an opaque
  origin can't be named; the time is no secret. The app listens to no messages
  from pages.
- **Links:** the inspector links a capture's address only when it's `http` or
  `https`, so a `javascript:` address in a script can't run as the studio.
- **Framing:** the app and its API send `frame-ancestors 'self'` and
  `X-Frame-Options: SAMEORIGIN`, so other sites can't frame them. The service
  does the same.
- **Alternatives:**
  - *Project pages on a second port:* they would keep a real origin, with
    storage and canvases. But Docker, the dev container and Codespaces would
    need a second port published or forwarded. Codespaces gives that port an
    address and a sign-in of its own, which a frame in the app may not get.
  - *Another host name on the same port,* such as `localhost` for the app and
    `127.0.0.1` for pages: Codespaces, a tunnel or `--allow-host` reach the
    studio by one name only.

## API

| Request | Does |
| --- | --- |
| `GET /` | the app |
| `GET /api/script` | the script's text and version (modification time and size) |
| `PUT /api/script` | save `{text, version}`; 409 if the file changed meanwhile |
| `POST /api/analyse` | parse, check and plan `{text}`: an id, scenes with times, blocks with lines, problems |
| `POST /api/frame` | the frame HTML (or page URL) for `{id, scene, time}`, from that analysis |
| `POST /api/engine` | switch the speech engine; refused if it can't start |
| `POST /api/edit` | the text change for a direct manipulation: properties set on the block at a line (`{text, line, set}`), or `op` `callout` (set a callout's), `insert-callout` (`{after, callout}`), `delete` (`{line}`), `header` (`{key: voice, value}`) or `voice` (`{line, voice}`) |
| `POST /api/scenes/{n}/audio` | synthesise a scene's narration; returns a WAV URL and paragraph start times |
| `GET /api/peaks/{sound}` | a scene's waveform, as min/max pairs, by the sound id the analysis gives |
| `GET /api/voices` | every voice, grouped, with what it becomes on the session's engine, and the pins |
| `POST /api/voices/audition` | `{text, voice, sample}`: the sample read as the script would read it (a WAV URL), or with `dry` what it would send |
| `PUT /api/voices/pins` | write the project's `voices.yaml`; announced as `voices-changed` |
| `POST /api/build` | start a build; progress over the event stream |
| `GET /api/build` | the latest build's state |
| `POST /api/build/cancel` | stop the running build |
| `POST /api/scenes/{n}/render` | render scene n into scratch (`narrate build --scenes n`), or reuse an unchanged render; `{regenerate: true}` takes its web captures again (D16) |
| `GET /api/scenes/render` | the latest scene render's state |
| `POST /api/scenes/render/cancel` | stop the scene render |
| `GET /api/events` | the event stream (SSE) |
| `GET /files/{path}` | the project's own files, nothing outside its folder and no hidden files, sandboxed (D17) |
| `GET /mermaid/{version}/mermaid.min.js` | narrate's own pinned mermaid.js, for live diagrams (D15) |
| `GET /pages/{key}/{path}` | the same files for the preview's frames, under the session's key, readable by their sandbox (D17); an HTML scene is set up to be scrubbed (D12) with the narration its `narrate` query gives |
| `GET /scratch/{name}` | the session's scratch files: clip stills, scene audio, copies of renders, sandboxed |

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
3. **M3, HTML scenes and render blocks (#57):**
   - HTML scenes scrubbed in the preview with the renderer's own seeking (#73);
   - overlays in the preview (#74);
   - marks placed by selecting a word (#75);
   - Mermaid drawn live (#76);
   - retaking web captures (#77).
