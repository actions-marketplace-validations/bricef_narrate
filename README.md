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
- **ffmpeg:** narrate downloads its own static ffmpeg 9.0 build on first use
  (about 150 MB, checked against the release's SHA-256), or ahead of time
  with `uv run narrate models`.
  - It doesn't use an installed ffmpeg, because ffmpeg 7.0 crashes
    intermittently on narrate's transition graphs (#37).
  - `$NARRATE_FFMPEG` overrides it.
  - Downloaded tools live under `~/.cache/narrate` (`$NARRATE_TOOLS`); speech
    audio is cached apart from them (`$NARRATE_CACHE`).
  - `uv run narrate doctor` checks the whole setup.
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
just test -m elevenlabs                       # live API check (spends a few credits)
```

`build` writes the MP4 and a poster JPG. With `subtitles: external` or `embed`
it also writes `.srt` and `.vtt` files. Intermediate files are deleted unless
you pass `--keep-work DIR`.

### Speech engines (`--tts`)

| Engine | Notes |
| --- | --- |
| `auto` (default) | ElevenLabs when `ELEVENLABS_API_KEY` is set, otherwise Kokoro |
| `elevenlabs` | `eleven_multilingual_v2` by default (change it with `--tts-model`); renders speeds 0.7–1.2 natively |
| `kokoro` | Kokoro-82M on the CPU (about 7× real time here); 54 voices across 9 languages; renders speeds 0.5–2 natively |
| `silent` | silence timed like speech, for fast layout previews |

Speeds beyond an engine's native range (Narakeet allows 0.3–2) are synthesised at the
nearest native speed and time-stretched the rest of the way, preserving pitch.
Measured: Kokoro within 5% of the requested length; ElevenLabs within 6% at 1.8×,
because its own speed setting is slightly non-linear.

Synthesised audio is cached under `~/.cache/narrate/tts/`, so a rebuild only
synthesises paragraphs that changed. That matters for ElevenLabs credits.

The cache is never pruned automatically:
- `narrate cache` shows its size per engine.
- `narrate cache --prune --max-size 500M` and/or `--older-than 90` (days)
  remove the least recently used entries.
- Entries used in the last hour (`--keep-recent`) are never removed, so a
  build in progress keeps what it needs.

### Parallelism

Builds overlap their stages. Speech is synthesised in the background in
script order while earlier scenes render, and video segments encode in a
thread pool. The output is byte-identical to a sequential build.

| Setting | Default |
| --- | --- |
| `--jobs N` (or `NARRATE_JOBS`) | up to 4 parallel encodes |
| `NARRATE_KOKORO_WORKERS` | up to 4 Kokoro sessions |
| `NARRATE_ELEVENLABS_CONCURRENCY` | 2, the free plan's limit |

### Emphasis

Neither engine exposes an emphasis control, so emphasis is a prosody bundle
applied on any engine. The speed change is rendered by the engine itself.

| Level | Markup | Speed | Pitch | Gain |
| --- | --- | --- | --- | --- |
| `moderate` | `*x*`, `_x_` | 0.96× | +0.75 semitones | +1.5 dB |
| `strong` | `**x**`, `__x__` | 0.92× | +1.5 semitones | +3 dB |
| `reduced` | `~~x~~` | 1.06× | −1 semitone | −4 dB |

Inline markup splits a paragraph into runs. Narakeet advises wrapping whole
sentences, and mid-sentence emphasis adds a short join. `voice-emphasis` sets
the level for the paragraphs that follow.

### Phonetic spans

`[təˈmeɪ.toʊ]{ipa}`, `{x-sampa}`, `{pinyin}` and `{jyutping}` give a word's
pronunciation.
- X-SAMPA is converted to IPA.
- Pinyin can use tone marks or tone numbers, and is phonemised by espeak's
  Mandarin.
- Jyutping is converted to IPA from tables of initials and finals; tones are
  dropped.
- Kokoro speaks the IPA directly as phonemes, inside the same utterance.
- ElevenLabs only reads IPA in `<phoneme>` tags on its flash/turbo v2 models,
  so phonetic words are voiced by `eleven_flash_v2` with the same voice.

### SSML

A paragraph wrapped in `<speak>…</speak>` is interpreted by narrate, so every
engine renders the same subset:
- `<break>` (time or strength) is silence.
- `<prosody rate pitch volume>` sets speed, pitch and gain.
- `<emphasis>` uses the emphasis levels above.
- `<say-as interpret-as="characters">` spells the text out.
- `<phoneme>` and `<lang>` become phonetic and language spans.
- `<sub alias>` reads the alias.
- `<p>` and `<s>` add sentence breaks.

Other tags keep their text, with a note. Malformed XML is read as plain text,
with a warning.

### Slide look

Default slides follow measurements of Narakeet's own renders:
- A 50 px base set on the slide itself, so a theme's `body` font size doesn't
  shrink slide text, while colour still inherits.
- Plain slides in bold at 2em.
- Browser-default heading sizes and margins (`h1` 2em, `h2` 1.5em).
- Sans-serif headings, with body and list text in the default serif (as
  Narakeet renders them).
- Code at 1em in a Courier-style font, in Narakeet's dark-red and bold-black
  palette.

The base rules have zero specificity, so a custom `.css` theme overrides any
of them.

### Background music

The built-in track names (`ukulele-1`, `ukulele-2`, `uplifting-1`,
`uplifting-2`, `corporate-1`) play narrate's own synthesised loops, since
Narakeet's tracks can't be redistributed.
- They're licence-free, rendered once into the tools cache, and mastered to
  sit about 10 dB under narration; `background: ukulele-1 2` doubles the
  level.
- Put real recordings with the same names in `$NARRATE_MUSIC_DIR` to use
  those instead.

### Russian stress marks

Narakeet's `^` before a Russian vowel (`гвозд^ики`) becomes the standard
written stress mark, a combining acute accent (`гвозди́ки`).
- ElevenLabs sees it as ordinary Russian text.
- Kokoro has no Russian voice, and espeak (its phonemiser) honours the mark
  in some words but not all.

### Voice names

A script's voice can be named in any of three ways:

- **A Kokoro ID**, such as `bf_emma`.
- **An ElevenLabs voice:** one of its default voices (`George`) or a raw voice
  ID from your own library.
- **A Narakeet voice name**, such as `Brian`.

Each engine uses the name directly when it's one of its own voices.
ElevenLabs also tries your account's library, if the key may list voices.
Otherwise the engine picks its voice of the same language and gender, so
scripts carry across engines. Australian, Indian, Irish, Scottish and South
African English fall back to British, then American.

To choose exactly, pin names per engine in `voices.yaml`, either next to the
script or in `~/.config/narrate/voices.yaml` (the project file wins):

```yaml
Brian:
  kokoro: bm_lewis
  elevenlabs: George      # a default voice name, or a voice id
```

`narrate voices [script]` lists each engine's voices and the pins in effect.

## Feature status

| Area | Works | Not yet (noted when used) |
| --- | --- | --- |
| Header | `size`, `voice`, `voice-speed`, `voice-volume`, `narration-language`, `canvas`, `theme` (default, light, `.css`), `asset-resize`, `subtitles` (every mode and style property), `background` (project file or built-in track, volume, fades), `poster-time`, `target`, `transition` (all 26 types), `voice-pitch`, built-in background tracks | |
| Images | fit/contain/cover, positions, several images per scene, pan/zoom animation (`zoom`, `zoomout`, `pan`, `panzoom`, `panzoomout`) | |
| Videos | segments, still frames, all six sync modes, volume/mute, animated GIFs, several clips and images in one scene | |
| Narration | paragraphs, pauses, `pause-until`, recorded audio, voices, speed (any 0.3–2), volume (presets, or `normalized` to EBU R 128), pitch, emphasis (markup and `voice-emphasis`), language spans (`[See]{de}`), phonetic spans (IPA, X-SAMPA, Pinyin, Jyutping), SSML paragraphs, ellipsis pauses, spelling (backticks and `{literal}`, with letter names in English, Spanish, French, German, Italian and Portuguese), `narration-mode` (`fragment`, and `merge` across scenes) | |
| Visuals | plain, Markdown and syntax-highlighted slides (several per scene take turns), themes and custom CSS, callouts (circle, rectangle, mask), transitions between scenes | |
| Subtitles | cues from narration or block quotes, SRT/VTT, embedded track, burned-in styles, custom fonts | |

### Checked against Narakeet's own renders

`just reference` fetches Narakeet's example projects together with the
`result.mp4` that Narakeet rendered from each script. `tests/test_build.py`
compares timing against them. What they show so far:

- **Matches exactly:** where a script has no narration (the `slides` example
  is 14.0 s in both).
- **Transitions** don't change a video's length in Narakeet, and narrate matches that (the `transition-types` example is 25.0 s in both).
- **Pauses:** Narakeet adds about 0.5 s to some scenes that hold a text slide and a pause, but not to a plain `(pause: 1)` scene. That's no consistent rule, so narrate keeps pauses exact (spec §17).

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
