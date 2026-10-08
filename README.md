# narrate

A local tool that turns a Markdown script and its assets into a narrated video.
It accepts the script format of Narakeet's "Markdown to Video" service, which is
specified in `docs/spec/narakeet-markdown.md`.

Status: proof of concept. It renders real videos with narration, slides, images,
clips, callouts and subtitles. The features not built yet are listed below;
scripts that use them still render, and narrate prints a note for each one.

````markdown
---
voice: George
subtitles: overlay-background
---

![cover](sunrise.png)

This paragraph is read aloud, and the scene lasts as long as the narration.

---

```md
# A text slide
* rendered from Markdown
```

(pause: 1)
````

## Setup

```sh
uv sync
uv run playwright install chromium   # slides and frames are rendered by headless Chromium
```

- **Chromium's system libraries:** install them with
  `uv run playwright install-deps` (needs root). Without root, extract them
  under `~/.cache/chromium-libs/root`; the justfile adds that directory to
  `LD_LIBRARY_PATH` when it exists.
- **ffmpeg:** comes from `imageio-ffmpeg`, a static build installed with the
  Python dependencies. An `ffmpeg` on `PATH`, or `$NARRATE_FFMPEG`, takes
  precedence.
- **Kokoro:** the model (about 350 MB) downloads on first use, or ahead of time
  with `uv run narrate models`.
- **ElevenLabs:** put `ELEVENLABS_API_KEY=…` in a `.env` file (git-ignored),
  either in the directory you run from or next to the script.

## Usage

```sh
uv run narrate build script.md -o video.mp4   # or: just build script.md
uv run narrate check script.md                # parse and check files, no rendering
uv run narrate voices                         # voices per engine
just demo                                     # examples/demo rendered with both engines into out/
just test
```

`build` writes the MP4 and a poster JPG. With `subtitles: external` or `embed`
it also writes `.srt` and `.vtt` files. Intermediate files are deleted unless
you pass `--keep-work DIR`.

### Speech engines (`--tts`)

| Engine | Notes |
| --- | --- |
| `auto` (default) | ElevenLabs when `ELEVENLABS_API_KEY` is set, otherwise Kokoro |
| `elevenlabs` | `eleven_multilingual_v2` by default (change it with `--tts-model`); speed 0.7–1.2 |
| `kokoro` | Kokoro-82M on the CPU (about 7× real time here); 54 voices across 9 languages; speed 0.5–2 |
| `silent` | silence timed like speech, for fast layout previews |

Synthesised audio is cached under `~/.cache/narrate/tts/`, so a rebuild only
synthesises paragraphs that changed. That matters for ElevenLabs credits.

### Voice names

A script's voice can be named in any of three ways:

- **A Kokoro ID**, such as `bf_emma`.
- **An ElevenLabs voice:** one of its default voices (`George`) or a raw voice
  ID from your own library.
- **A Narakeet voice name**, such as `Brian`.

Each engine uses the name directly when it's one of its own voices. Otherwise
it picks its voice of the same language and gender, so scripts carry across
engines. `narrate voices` lists the voices for each engine.

## Feature status

| Area | Works | Not yet (noted when used) |
| --- | --- | --- |
| Header | `size`, `voice`, `voice-speed`, `voice-volume`, `narration-language`, `canvas`, `theme` (default, light, `.css`), `asset-resize`, `subtitles` (every mode and style property), `background` (project file, volume, fades), `poster-time`, `target` | `transition`, `voice-pitch`, built-in background tracks |
| Images | fit/contain/cover, positions, several images per scene | pan/zoom animation (shown static) |
| Videos | segments, still frames, all six sync modes, volume/mute, animated GIFs | several videos in one scene |
| Narration | paragraphs, pauses, `pause-until`, recorded audio, voices, speed, volume, ellipsis pauses, spelling (backticks and `{literal}`), `narration-mode: fragment` | emphasis, pitch, IPA/X-SAMPA/Pinyin spans and SSML (read as plain text), `merge` mode |
| Visuals | plain, Markdown and syntax-highlighted slides, themes and custom CSS, callouts (circle, rectangle, mask) | transitions (scenes cut), more than one slide per scene |
| Subtitles | cues from narration or block quotes, SRT/VTT, embedded track, burned-in styles, custom fonts | |

### Checked against Narakeet's own renders

`just reference` fetches Narakeet's example projects together with the
`result.mp4` that Narakeet rendered from each script. `tests/test_build.py`
compares timing against them. What they show so far:

- **Matches exactly:** where a script has no narration (the `slides` example
  is 14.0 s in both).
- **Transitions** don't change a video's length in Narakeet.
- **Narakeet pads `(pause: N)`** to about N + 0.5 s. narrate keeps pauses exact.

## Layout

- `src/narrate/`
  - `script.py`: parser (spec §2, §5, §7).
  - `config.py`: header settings.
  - `text.py`: narration markup.
  - `tts.py`: speech engines and voices.
  - `frames.py`: Chromium frames.
  - `subtitles.py`: subtitle cues and files.
  - `build.py`: timing, rendering and muxing.
  - `cli.py`: the command line.
- `docs/spec/narakeet-markdown.md`: the input format. §16 lists open questions
  and the answers used here.
- `examples/demo/`: the demo script. Its images and clip are generated by
  `make_assets.py`.
- `scripts/fetch-narakeet-reference.sh`: the local, git-ignored Narakeet
  reference snapshot. See `reference/SOURCES.md`.
