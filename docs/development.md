# Development

How to work on narrate itself: set up a checkout, run the tests, build the
container image, and find your way around the code.

## Set up

Follow [Install from source](../README.md#from-source), then install
[just](https://github.com/casey/just) for the recipes below. `just` lists
them:

| Recipe | Does |
| --- | --- |
| `just test [ARGS]` | run the test suite (`ARGS` go to pytest) |
| `just lint [ARGS]` | check the code with ruff (`ARGS` go to `ruff check`, such as `--fix`) |
| `just build SCRIPT [ARGS]` | render a script |
| `just studio SCRIPT [ARGS]` | edit a script in narrate studio, opened in a browser |
| `just demo` | render `examples/demo` with Kokoro and ElevenLabs into `out/` |
| `just reference` | download Narakeet's example projects and renders, for the conformance tests |
| `just image` | build the container image as `narrate:local` |
| `just image-test` | run the test suite inside the image |

Put `ELEVENLABS_API_KEY` in a `.env` at the repository root (it is
git-ignored) for the ElevenLabs parts.

## Run the tests

```sh
just test                     # everything except live ElevenLabs calls
just test tests/test_ssml.py  # one file
just test -m "not kokoro"     # skip the tests that need the Kokoro model
```

Markers select the slow or costly tests:

| Marker | Needs | Default |
| --- | --- | --- |
| `kokoro` | the Kokoro model (downloads on first use) | runs |
| `stt` | the faster-whisper model (downloads on first use) | runs |
| `conformance` | `just reference` first; skipped without it | runs |
| `elevenlabs` | `ELEVENLABS_API_KEY`; spends a few credits | off: `just test -m elevenlabs` |

`tests/test_docs.py` builds every script example in the README and `docs/`
(each fenced with four backticks and `markdown`), with placeholder pictures,
clips and audio, and fails on any warning. Fence new script examples the same
way, so they stay correct. Examples that need the network (`render:web`) are
fenced with `md` instead, which the test skips.

## Conformance with Narakeet

`just reference` downloads Narakeet's 22 example projects, with their media
and the `result.mp4` Narakeet rendered from each, into `reference/` (about
140 MB). The examples have no licence and Narakeet's docs are copyrighted, so
`reference/` is git-ignored: never commit or vendor it
([reference/SOURCES.md](../reference/SOURCES.md)).

`tests/test_conformance.py` builds each example that has no narration and
compares it with Narakeet's render:
- Lengths match within 0.1 s.
- Once each scene has settled, frames match within a few grey levels.

Where Narakeet departs from its own documentation, the difference is pinned
in the test and explained in [spec §17](spec/narakeet-markdown.md#17-observations-from-narakeets-renders):
- Narakeet pads some slide-and-pause scenes by about 0.5 s.
- It overruns some clip ranges.

## The container image

The `Dockerfile` has four stages:

1. **`ffmpeg`:** builds ffmpeg from the signed release tarball, pinned by
   version and SHA-256. It keeps every native decoder, demuxer and filter, but
   only the external libraries narrate uses: x264, libass, rubberband, LAME,
   Opus and dav1d. The result is 30 MB, against 173 MB for a static build.
2. **`python`:** installs narrate into `/opt/narrate` with uv from `uv.lock`,
   Playwright's headless Chromium shell into `/opt/playwright`, and mermaid.js
   (checked against narrate's pinned SHA-256) as `/opt/mermaid.min.js`.
3. **`runtime`:** the published image. It holds the two stages' output, Chromium's
   libraries and the fonts. `libgbm` comes without its Debian package's Mesa
   drivers (about 200 MB of LLVM), which only load when a GPU is used and
   headless Chromium never does.
4. **`test`:** runs the test suite against the runtime image, without the tests
   that download models or call ElevenLabs.

```sh
just image          # docker build --target runtime -t narrate:local .
just image-test     # docker build --target test .
```

Everything narrate writes at run time goes under `/cache` or `/tmp`, so the
image runs as any user ID.

**Updating ffmpeg:**
1. Download the new `ffmpeg-X.Y.Z.tar.xz` and its `.asc` from
   ffmpeg.org/releases.
2. Check the signature against FFmpeg's release key,
   `FCF9 86EA 15E6 E293 A564 4F10 B432 2F04 D676 58D8`.
3. Set `FFMPEG_VERSION` and `FFMPEG_SHA256` in the Dockerfile, then run
   `just image-test`.

The managed ffmpeg for source checkouts is pinned separately, in
`src/narrate/media.py`.

**Updating mermaid.js:**
1. Take the version from the npm registry
   (`https://registry.npmjs.org/mermaid/latest`).
2. Check the package tarball against the registry's `integrity` value.
3. Take the SHA-256 of its `dist/mermaid.min.js`, and confirm the jsDelivr copy
   matches it.
4. Set `MERMAID_VERSION` and `MERMAID_SHA256` in `src/narrate/mermaid.py`.
5. Run `just test tests/test_mermaid.py tests/test_docs.py`.

## The studio

`narrate studio` serves a browser app from `src/narrate/studio/`. The app's
own code is plain ES modules, loaded as they are; change a file and reload
the page. `tests/test_studio.py` covers the server with Starlette's test
client, and `tests/test_studio_e2e.py` drives the app in headless Chromium
with Playwright, so neither needs Node.

## CI and releases

`.github/workflows/checks.yml` runs on every pull request, forks' included,
and on pushes to `main`. It takes a few minutes:
- **Lint:** `ruff check`, as `just lint` runs it. The rules are in
  `pyproject.toml`.
- **Tests:** the test suite on the runner, with headless Chromium and the
  DejaVu fonts, without the `kokoro`, `stt`, `conformance` and `elevenlabs`
  tests. uv's packages and narrate's downloads are cached between runs.

`.github/workflows/image.yml` runs on pushes that touch the code, tests,
examples, Dockerfile or action. It also runs on pull requests from forks that
change the Dockerfile, the action or the workflow:

1. Runs the test suite in the image.
2. Builds the image's `runtime` stage, the one that's published.
3. Builds a short script with it the way the README does: the folder at
   `/work`, a new cache volume and the runner's own user.
4. Renders `examples/demo` through the action with that image, keeping the
   video as the `demo-video` artifact.
5. On `main` and on `v*` tags only: publishes the image to
   `ghcr.io/bricef/narrate`, then renders the demo again with the published
   image. That second render pulls it the way other repositories do.

Build layers are cached in GitHub's Actions cache. A warm run takes about 4
minutes. A cold one takes about 17, most of it compiling ffmpeg, after a
Dockerfile change or a week without builds.

**Image tags:**

| Push | Tags |
| --- | --- |
| `main` | `latest` and `sha-<commit>` |
| tag `v1.2.3` | `1.2.3` and `1.2` |

To release, tag a commit on `main` and push the tag:

```sh
git tag v1.2.3
git push origin v1.2.3
```

Workflows can then pin both parts: `uses: bricef/narrate@v1.2.3`, with
`image: ghcr.io/bricef/narrate:1.2.3`.

## How a build works

1. **Parse:** `script.py` splits the script into scenes and blocks, and
   `config.py` reads the header.
2. **Plan:** `build.py` synthesises each scene's narration (in the background,
   in script order). It then lays out the scene on a frame-exact timeline:
   30 frames a second, 800 audio samples per frame at 24 kHz.
3. **Render:**
   - Headless Chromium draws every still frame, slide and callout as HTML and
     CSS (`frames.py`), so CSS themes apply as written. HTML scenes and
     overlay pages are captured frame by frame on the video's clock
     (`pages.py`).
   - ffmpeg encodes the segments in parallel, lays each scene's overlays over
     the joined scene, and joins the scenes with transitions. The video's own
     overlays go on next, then burned-in subtitles, music and the header's
     fades.
4. **Output:** the result is byte-identical to a one-at-a-time build.

Some choices worth knowing when changing behaviour:
- **Emphasis:** neither engine has an emphasis control, so emphasis is a
  bundle of speed, pitch and gain applied the same way on every engine.
- **Speeds** beyond an engine's own range are synthesised at the nearest
  speed it supports, then time-stretched with pitch kept (ffmpeg's `atempo`).
  Pitch changes, including emphasis, use rubberband.
- **SSML** is interpreted by narrate (`ssml.py`) rather than passed to the
  engine, so both engines render the same subset.
- **Slide CSS:** the default slide CSS follows measurements of Narakeet's
  renders, inside `:where()` so that themes always win.

## Code layout

- `src/narrate/`:
  - `cli.py`: the `narrate` command.
  - `narakeet_cli.py`: `narakeet-api-client`.
  - `script.py`: the parser.
  - `config.py`: header values.
  - `build.py`: timing, rendering and mixing.
  - `text.py`, `ssml.py` and `phonetics.py`: narration markup, SSML and
    phonetic alphabets.
  - `tts.py` and `voicemap.py`: speech engines, voices and `voices.yaml`.
  - `frames.py` and `motion.py`: Chromium frames, and pan and zoom.
  - `render.py`: render blocks, their cache, and `render:placeholder`.
  - `mermaid.py`: `render:mermaid`, the pinned mermaid.js, and the page the
    studio draws diagrams live with.
  - `web.py`: `render:web`, web pages captured and stored in the project.
  - `pages.py`: HTML scenes and overlay pages, captured frame by frame.
  - `review.py`: reviewing a built video without watching it: contact sheets
    (`narrate frames`) and what speech-to-text hears (`narrate hear`).
  - `subtitles.py` and `stt.py`: subtitle cues, and speech-to-text for
    recordings.
  - `media.py`: ffmpeg.
  - `music.py`: the synthesised background tracks.
  - `project.py`: ZIP projects.
  - `designer.py`: the callout designer page.
  - `cache.py`: the `cache` command.
  - `studio/`: `narrate studio` ([design](design/studio.md)):
    - `server.py`, the Starlette server;
    - `analysis.py`, the live timing, problems and timeline data;
    - `preview.py`, `audio.py` and `builds.py`: frames, narration playback,
      and builds and scene renders in a child process;
    - `edits.py`, the script edits behind the inspector, callouts and voices;
      `voices.py`, the voice picker's catalogue, auditions and pins;
    - `static/`, the browser app: plain ES modules, no build step;
      `page.js` and `page-clock.js` scrub HTML scenes and overlays in the
      preview, on the app's side and the page's;
    - `static/vendor/`, the vendored Preact (htm), CodeMirror and fake clock
      files, with their sources and hashes in its README.
  - `child.py`: runs one of narrate's commands in a child process and reads
    its progress (the studio's builds, the service's jobs).
  - `service/`: `narrate serve` ([design](design/service.md)):
    - `server.py`, the Starlette app;
    - `store.py`, files by hash, job folders and records (SQLite);
    - `projects.py`, checking and laying out a request's project;
    - `jobs.py`, running jobs and collecting their outputs;
    - `options.py`, what a job takes, checked against the CLI's flags;
      `openapi.py`, the API's description.
  - `doctor.py`: the `doctor` command.
- `tests/`: pytest. The `test_conformance.py` and `test_docs.py` suites are
  described above.
- `docs/`: these guides, `spec/narakeet-markdown.md` (the format
  specification), `design/` (design records, such as the studio's) and
  `research/` (dated research behind a design, such as the AI image and video
  models report for #41 and #42).
- `examples/demo/`: the demo script. `make_assets.py` generates its pictures
  and clip.
- `scripts/`:
  - the reference download (`fetch-narakeet-reference.sh`) and its
    HTML-to-Markdown converter;
  - `vendor.sh`, which rebuilds the studio's CodeMirror and fake clock bundles
    from the versions pinned in `scripts/codemirror/` and
    `scripts/fake-timers/`. It needs Node, through `mise exec node@24 --` for
    example, and is only for updating them.
- `Dockerfile`, `action.yml` and `.github/workflows/image.yml`: the image, the
  GitHub Action and CI.
