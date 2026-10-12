# narrate script format: the complete reference

Everything a script can say, condensed. The narrate repository's
`docs/writing-scripts.md` has longer explanations and `docs/spec/narakeet-markdown.md`
every rule; this page is enough to write any script.

Contents:
1. [Structure](#1-structure)
2. [Header keys](#2-header-keys)
3. [Narration, pauses and timing](#3-narration-pauses-and-timing)
4. [Voices](#4-voices)
5. [Pronunciation and SSML](#5-pronunciation-and-ssml)
6. [Recorded audio](#6-recorded-audio)
7. [Pictures](#7-pictures)
8. [Clips](#8-clips)
9. [Render blocks: generated pictures](#9-render-blocks-generated-pictures)
10. [HTML scenes](#10-html-scenes)
11. [Slides and themes](#11-slides-and-themes)
12. [Callouts](#12-callouts)
13. [Subtitles and transcripts](#13-subtitles-and-transcripts)
14. [Music, loudness and fades](#14-music-loudness-and-fades)
15. [Transitions](#15-transitions)
16. [Size, poster and file size](#16-size-poster-and-file-size)
17. [Commands](#17-commands)

## 1. Structure

````markdown
---
size: 1080p
voice: bf_emma
---

<!-- comments are ignored -->

![](photo.jpg)

Narration for the first scene.

---

Second scene.
````

- **Header:** optional YAML between the first two `---` lines, starting on line 1. Quote values
  starting with `#`.
- **Scenes:** separated by a line of three or more dashes.
- **Blocks:** separated by blank lines. Each is a picture or clip (`![…](file)`), a stage direction
  (`(key: value)` alone on its line(s)), a slide (fenced code block), a block quote (`> text`),
  an SSML paragraph (`<speak>…</speak>`), or narration.
- **Multi-line directions:** open with `(key:` and end with `)`; the lines between are YAML:

  ```
  (video:
    file: clip.mp4
    sync: loop)
  ```

- **Files** are relative to the script. Pictures: JPG, PNG, GIF. Clips: MP4, MOV, M4V, WEBM, WMV,
  AVI, MPEG. Recordings: WAV, MP3, WMA, AAC, M4A. Pages: HTML. Anything else in image syntax is read
  aloud, with a warning. Scripts end in `.md`, `.mkd` or `.txt`.
- A direction sets things for the rest of its scene; each scene starts again from the header.

## 2. Header keys

| Key | Value | Default |
| --- | --- | --- |
| `size` | a preset (§16) or `WIDTHxHEIGHT` | `720p` |
| `voice` | a voice name (§4) | the engine's default |
| `voice-speed` | `slow` (0.8), `normal`, `fast` (1.2), or 0.3–2 | `normal` |
| `voice-pitch` | `x-low` `low` `normal` `high` `x-high` (±2 semitone steps), or −150 to 150 (hundredths of an octave) | `normal` |
| `voice-volume` | `x-soft` `soft` `standard` `loud` `x-loud` (4.5 dB steps), or `normalized` | `standard` |
| `narration-language` | a language code (`fr`, `de-DE`) for the whole video | the voice's |
| `canvas` | colour behind letterboxed pictures and plain slides | black behind pictures; the theme's (white) behind slides |
| `theme` | `default`, `light`, or a `.css` file (§11) | `default` |
| `asset-resize` | default fit for pictures and clips: `cover` `contain` `fit` | `cover` |
| `image-zoom` | how far pan/zoom moves, above 1 (narrate only) | 1.25 zoom, 1.15 pan |
| `transition` | `TYPE [SECONDS]` between every scene (§15) | none |
| `overlay` | web pages over the whole video: a page, a map, or a list (§10, narrate only) | none |
| `fade-in`, `fade-out` | seconds from/to black at the video's start/end (narrate only) | 0 |
| `subtitles` | a mode, or a style map (§13) | `none` |
| `transcript` | `true`: also write `<name>.transcript.txt` (narrate only) | `false` |
| `background` | music: `FILE-or-TRACK [VOLUME] [fade-in] [fade-out]` (§14) | none |
| `loudness` | `web` (−16 LUFS), `broadcast` (−23), or a number (narrate only) | unchanged |
| `poster-time` | `start`, `end`, a percentage, seconds or `MM:SS` | `50%` |
| `target` | `offline` (best), `online` (uploads), `self-hosted` (smallest) | `offline` |

## 3. Narration, pauses and timing

- Every paragraph that isn't something else is spoken, followed by a short pause (about 0.5 s).
- `(pause: N)`: N seconds of silence. An ellipsis (`…` or `...`) adds about half a second.
- `(pause-until: T)`: wait until T seconds (or `MM:SS`) into the scene; nothing if already past.
- `(duration: N)`: the length of a scene with no narration; with narration, the scene lasts at least
  N (the longer of the two). Without narration or duration, a picture or slide lasts 1 s and a clip
  plays to its end.
- To hold the last picture after the words, end the scene with `(pause: N)`.
- **Emphasis:** `*x*` (moderate), `**x**` (strong), `~~x~~` (reduced), or `(voice-emphasis: moderate|strong|reduced|none)`
  for the paragraphs that follow. Emphasise whole sentences; mid-sentence emphasis adds a join.
- `(narration-mode: merge)`: from this scene until one that says `(narration-mode: normal)`, the
  scenes' narration is spoken as one, and they share its time equally. `fragment` keeps scenes
  separate but shortens the pause after each paragraph.
- **Speaking rate:** about 150 words a minute (narrate estimates 0.065 s per character until speech
  is synthesised).

## 4. Voices

- `(voice: NAME)` switches voice for the following paragraphs, to the end of the scene.
- **Names:** Kokoro IDs (`af_heart`, `bf_emma`, `am_michael`, `bm_george`, `bf_lily`, …), ElevenLabs
  default voices (`George`, `Lily`, `Sarah`, `Brian`, `Alice`, …) or Narakeet names (`Amy`, `Arthur`,
  `Matt`, …). Each engine uses its own voice by that name, or the closest of the same language and
  gender, with a note. `NAME/ll-RR` pins the language (`Amy/de-DE`).
- `narrate voices [script.md]` lists every voice and the pins in effect.
- **Pins:** `voices.yaml` next to the script maps a name to a voice per engine:

  ```yaml
  Narrator:
    kokoro: bf_lily
    elevenlabs: Lily
  ```

- `(voice-speed: …)`, `(voice-pitch: …)`, `(voice-volume: …)`: as in the header (§2), for the rest of
  the scene. `normal` resets to the default, not the header's value.
- `(narration-language: fr)` reads the rest of the scene in French with the same voice; `default`
  switches back.

## 5. Pronunciation and SSML

- `` `NRT` `` or `[NRT]{literal}`: spelled out letter by letter.
- `[ˈnær.eɪt]{ipa}`, `[…]{x-sampa}`, `[Běi jīng]{pinyin}`, `[hoeng1 gong2]{jyutping}`: phonetic.
  The subtitles and transcript show the phonetic text itself; for a word that's also shown, use
  `<phoneme>` or `<sub alias>` inside `<speak>`, which keep the written word.
- `[Schadenfreude]{de}`: one phrase in another language.
- `<speak>…</speak>` paragraphs, interpreted by narrate the same for every engine: `<break time="1s"/>`
  (or `strength`), `<prosody rate|pitch|volume>`, `<emphasis>`, `<say-as interpret-as="characters">`,
  `<phoneme>`, `<lang>`, `<sub alias>`, `<p>`, `<s>`, and `<mark name="NAME"/>` (a timing point for
  HTML scenes, §10). Other tags are read as text.
- Russian stress: `^` before the stressed vowel (ElevenLabs only).

## 6. Recorded audio

- `(audio: talk.mp3)` plays a recording as part of the narration, in order with spoken paragraphs
  (never overlapping). The scene lasts as long as all of it.
- With subtitles or a transcript on, recordings are transcribed on the computer (faster-whisper,
  ~460 MB model on first use).

## 7. Pictures

- `![OPTIONS](file)`, where OPTIONS are words: a fit, a position, a motion.
- **Fit:** `cover` (fill and crop; default), `contain` (letterbox with `canvas`), `fit` (stretch).
- **Position:** `center`, `top-left`, `left`, `right`, `top`, `bottom`: which part survives a crop,
  and where a motion heads.
- **Motion:** `zoom`, `zoomout`, `pan`, `panzoom`, `panzoomout`. Use pictures bigger than the video.
- **Map form:** `(image: photo.jpg)` or `(image: {file: photo.jpg, size: zoom, position: left, zoom: 1.4})`.
  `size` takes a fit or a motion; `zoom` (above 1) is how far it moves.
- **Free framing** (narrate only, map form only):
  - `position: 70% 25%`: a focal point, kept as central as the crop allows; motions head for it.
  - `from: 50% 50%` and `to: 72% 30% 2.5`: the first and last frames' windows, each a centre and a
    zoom (1 = the plain crop, 2 = half as wide). The picture moves between them. Windows past the
    edge are moved in, with a note.
- `(image-size: …)` and `(image-position: …)`: defaults for the following pictures in the scene.
- **Several pictures** in a scene take turns, sharing its time equally.
- Animated GIFs loop for the scene, or play once with `freeze`.

## 8. Clips

- `![OPTIONS](clip.mp4)`: OPTIONS as for pictures, plus a range and a sync mode.
- **Range:** `00:01-00:03` or `10-14.5` (no spaces); `start` and `end` stand for the ends. A single
  time (`00:05`, `start`, `end`) shows that frame as a still.
- **Sync**, when the clip and the narration differ in length:

  | Mode | Behaviour | Scene length |
  | --- | --- | --- |
  | `freeze` (default) | plays once; last frame holds | the longer |
  | `match` | sped up or slowed to fit the narration | the narration |
  | `trim` | stops when either ends | the shorter |
  | `loop` | repeats to cover the narration | the longer |
  | `trim-or-loop` | loops if shorter, cut if longer | the narration |
  | `loop-audio` | the narration repeats to cover the clip | the longer |

- **Sound:** `mute` as a word, or `volume: 0.3` in the map form `(video: {file: clip.mp4, sync: loop, volume: 0.3})`.
  The clip's sound plays under the narration.

## 9. Render blocks: generated pictures

A fenced block whose info string is `render:NAME [OPTIONS]` becomes a picture, placed like `![OPTIONS](…)`.
An optional `---`-delimited YAML block at the top holds settings; `size`, `position`, `zoom`, `from`
and `to` there place the output.

````markdown
```render:mermaid zoom
---
title: Release flow
config:
  theme: neutral
background: "#ffffff"
scale: 0.9
---
flowchart LR
  A[Commit] --> B[CI] --> C[Deploy]
```
````

- **`render:mermaid`:** any Mermaid diagram (flowchart, sequence, class, state, ER, gantt, pie,
  mindmap, timeline…), fitted to 90% of the frame. Settings: `background`, `scale`, and Mermaid's
  `title`, `displayMode`, `config`. Syntax errors show up in `narrate check`.
- **`render:placeholder`:** a card showing the block's text and the video size, for a picture still
  to come. Settings: `background`, `color`.
- **`render:web`:** captures a live page at build time (needs the network the first time; stored in
  `.narrate/generated/web/` and reused; `narrate build --regenerate` retakes it). The block can be
  just a URL. Settings: `url`, `viewport`, `scale` (default 2), `color-scheme` (`light`, `dark`),
  `hide` (CSS selectors), `css`, `scroll-to` (text), `selector` (one element), `wait` (`load`,
  `networkidle`, or ms), `auth` (an environment variable holding `user:password`).

## 10. HTML scenes

- `![](scene.html)` or `(html: {file: scene.html, viewport: 1280x720, size: contain})`: a local web
  page, captured frame by frame on the video's clock (CSS animations, SVG, JS timers,
  `requestAnimationFrame`, `Date`).
- Lasts as long as the scene; with no narration or duration, until its last finite animation ends.
- **Cues** (CSS custom properties, in seconds from the page's start): `--cue-1`, `--cue-2`, … when each
  narration block starts; `--cue-NAME` when the voice reaches `<mark name="NAME"/>` (plain or SSML);
  `--narrate-duration`. Scripts get `window.narrate.duration` and `window.narrate.cues`.
- No network, and no `<video>`/`<audio>` inside. See `html-scenes.md` for how to write them.

**Overlays** (narrate only): a transparent web page laid over the picture, such as a ticker, a lower third,
a legend or labels.
- `(overlay: legend.html)` or `(overlay: {file: lower-third.html, name: "Ada", role: "Lead"})` in a scene:
  over that scene, on the scene's clock, with its cues; other keys reach the page as `window.narrate.params`.
- Header `overlay: ticker.html` (or a list; an entry may take `scenes: 2-5`): over the whole video, on the
  video's clock, so it runs on through cuts. `(overlay: none)` hides it for a scene. Pages get `--scene-N`
  and `window.narrate.scenes`.
- Leave the page's background unset so the picture shows through. Layers: picture, callouts and slides,
  scene overlays, video overlays, burned-in subtitles. A still page is captured once; a moving one frame
  by frame.

## 11. Slides and themes

- A fenced code block is a slide, shown and never spoken. Info string: none or `txt` (plain, big and
  bold), `md` (Markdown: headings, bullets, emphasis), or a language (`python`, `yaml`…) for
  highlighted code.
- `(font-size: N)`: the scene's slide text size in pixels (default 50); overflowing text shrinks.
- Over a picture, the `default` theme darkens the picture behind the slide; over a clip, no backdrop.
- Several slides in a scene take turns, sharing its time.
- `(theme: light)` or a `.css` file (header or direction): `body` styles the slide, `.backdrop` the
  layer over a picture, `@font-face` loads project fonts.
- `(canvas: "#202020")`: the scene's background colour.

## 12. Callouts

````markdown
(callout:
  cx: 640
  cy: 360
  size: 150)

(callout:
  type: rectangle
  left: 900
  top: 50
  right: 1250
  bottom: 200
  style: mask)
````

- Circle: `cx`, `cy`, `size` (radius, default 100). Rectangle: `type: rectangle`, `left`, `top`,
  `right`, `bottom`.
- `alpha` (0–1, default 0.5): how dark the rest of the frame goes. `style: mask` blacks out the shape
  instead.
- Coordinates are pixels of the finished video (for 1080p, 1920×1080), and apply for the whole scene.

## 13. Subtitles and transcripts

- **Modes** (`subtitles:` in the header, or `narrate build --subtitles MODE` per build):

  | Mode | Result |
  | --- | --- |
  | `none` | none (default) |
  | `external` | `.srt` and `.vtt` files only |
  | `embed` | a subtitle track in the MP4, plus the files |
  | `overlay` | burned in, outlined text, plus the files |
  | `overlay-background` | burned in on a dark box, plus the files |
  | `tiktok` | burned in, large, a few words at a time, plus the files |

- **Style map:** `subtitles: {mode: overlay, break: 60, color: yellow, background: "#00000080", position: top}`.
  Keys: `break` (characters per cue, default 135), `scale` or `size`, `color`, `outline` or
  `background`, `font` (a `.ttf`), `position` (`top`, `middle`, `bottom`).
- Each paragraph becomes a subtitle, split at `break`. One sentence per paragraph reads best.
- `> text` replaces a scene's subtitles (shown even with mode `none`); a lone `>` hides them.
- **Transcript:** `transcript: true` or `--transcript` writes `<name>.transcript.txt`: what's spoken,
  a line per paragraph, a blank line between scenes.

## 14. Music, loudness and fades

- `background: music.mp3 0.5 fade-in fade-out`: a project file or a built-in track (`ukulele-1`,
  `ukulele-2`, `uplifting-1`, `uplifting-2`, `corporate-1`), then a volume multiplier and the fades
  (over the first and last scene). It loops under everything.
- `loudness: web`: the whole mix brought to −16 LUFS (or `broadcast`, or a number).
- `fade-in: 0.5`, `fade-out: 1`: the video and its sound fade from and to black.

## 15. Transitions

- Header `transition: crossfade 0.5` for every scene; `(transition: wipe-left 1)` into one scene;
  `(transition: none)` to cut. The time defaults to 0.2 s; a transition plays over the start of the
  next scene and doesn't change the length.
- **Types:** `crossfade`; `wipe` (`wipe-right`), `wipe-left`, `wipe-up`, `wipe-down`; `slide-right`,
  `slide-left`, `slide-up`, `slide-down`; `fade-right`, `fade-left`, `fade-up`, `fade-down`,
  `fade-circle`; `slice-right`, `slice-left`, `slice-up`, `slice-down`; `dissolve`, `pixelize`;
  `radial`, `circle`, `rect`, `reveal`; `fade-black`, `fade-white` (dips, narrate only).

## 16. Size, poster and file size

- **Size presets:** `720p` (1280×720, default), `1080p`, `1440p`, `4x3`, `720p-portrait`,
  `1080p-portrait`, `instagram`, `instagram-square`, `instagram-story`, `tiktok`, `linkedin`,
  `linkedin-vertical`, `twitter`, `twitter-square`, `facebook`, `facebook-square`, `facebook-carousel`,
  `pinterest-2x3`, `pinterest-square`, `pinterest-vertical`; or `WIDTHxHEIGHT`.
- Pick by platform: YouTube `1080p`; Shorts, Reels, TikTok and stories `1080p-portrait`, `tiktok` or
  `instagram-story`; LinkedIn, Instagram and Facebook feeds `instagram-square` (1080×1080). The
  `linkedin` preset is a wide banner (1728×720), small in a phone's feed.
- `poster-time`, `target`: §2.

## 17. Commands

| Command | Does |
| --- | --- |
| `narrate check S [--timing --tts E] [--json]` | problems with lines; with `--timing`, scene lengths, total, characters to synthesise |
| `narrate build S --tts E [-o OUT.mp4]` | the video, poster (`.jpg`), and any subtitle files or transcript |
| `narrate build S --scenes 3` (or `3-5`, `2,4`) | just those scenes, exactly as in the whole video (`S-scene-3.mp4`) |
| `narrate build S --subtitles MODE --transcript` | choose subtitle outputs and a transcript for this build |
| `narrate frames V --script S --tts E` | a contact sheet: one frame from the middle of each scene |
| `narrate frames V [--count 12 \| --every 5 \| --at 1,9.5]` | frames by time instead |
| `narrate hear V --script S` | where the narration sounds different from the script (speech-to-text) |
| `narrate audio S --tts E [-o OUT.mp3]` | narration and music only |
| `narrate voices [S]` | voices, and the pins in effect |
| `narrate doctor` | check the setup |
| `narrate studio S --open` | a web editor for people (not for agents) |

Engines (`--tts`): `silent` (timing only, instant), `kokoro` (free, local), `elevenlabs`
(paid per character; needs `ELEVENLABS_API_KEY`), `auto` (ElevenLabs if a key is set, else Kokoro:
avoid it, always say which).
