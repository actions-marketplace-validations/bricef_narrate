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
| `just build SCRIPT [ARGS]` | render a script |
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
way, so they stay correct.

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
   and Playwright's headless Chromium shell into `/opt/playwright`.
3. **`runtime`:** the published image. It holds the two stages' output, Chromium's
   libraries and the fonts. `libgbm` comes without its Debian package's Mesa
   drivers (about 200 MB of LLVM), which only load when a GPU is used and
   headless Chromium never does.
4. **`test`:** runs the test suite against the runtime image, without the tests
   that download models or call ElevenLabs.

```sh
just image          # docker build -t narrate:local .
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

## CI and releases

`.github/workflows/image.yml` runs on pushes that touch the code, tests,
examples, Dockerfile or action:

1. Runs the test suite in the image.
2. Builds the image.
3. Renders `examples/demo` through the action with that image, keeping the
   video as the `demo-video` artifact.
4. On `main` and on `v*` tags only: publishes the image to
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
   - Headless Chromium draws every still frame, slide and overlay as HTML and
     CSS (`frames.py`), so CSS themes apply as written.
   - ffmpeg encodes the segments in parallel and joins them with transitions,
     music and subtitles.
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
  - `subtitles.py` and `stt.py`: subtitle cues, and speech-to-text for
    recordings.
  - `media.py`: ffmpeg.
  - `music.py`: the synthesised background tracks.
  - `project.py`: ZIP projects.
  - `designer.py`: the callout designer page.
  - `cache.py`: the `cache` command.
  - `doctor.py`: the `doctor` command.
- `tests/`: pytest. The `test_conformance.py` and `test_docs.py` suites are
  described above.
- `docs/`: these guides, and `spec/narakeet-markdown.md`, the format
  specification.
- `examples/demo/`: the demo script. `make_assets.py` generates its pictures
  and clip.
- `scripts/`: the reference download (`fetch-narakeet-reference.sh`) and its
  HTML-to-Markdown converter.
- `Dockerfile`, `action.yml` and `.github/workflows/image.yml`: the image, the
  GitHub Action and CI.
