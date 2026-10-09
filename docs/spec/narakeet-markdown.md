# Narakeet Markdown-to-video input format

A reimplementation-oriented specification of the script format accepted by
Narakeet's "Markdown to Video" builder, collected so a local tool can accept the
same projects and produce equivalent output.

- **Snapshot date:** 2026-10-08. Narakeet's format reference was last modified
  2026-07-31; the newest relevant change is the `voice: name/lang` form
  (2026-04-14).
- **Scope:** Markdown/text scripts plus their asset files. The PowerPoint path,
  the audio-only (text-to-audio) project type, the voice catalogue, previews and
  billing are out of scope except where they explain script behaviour.
- **Wording:** this document is written from Narakeet's public docs and their
  official example projects; it paraphrases rather than copies them. The
  offline snapshot it was written from lives in `reference/` (git-ignored, see
  `reference/SOURCES.md`).

## Conventions

Every rule is documented by Narakeet unless tagged:

| Tag | Meaning |
| --- | --- |
| **[obs]** | Not in the docs, but used in Narakeet's official example scripts (which build), so a compatible parser must accept it. |
| **[inf]** | Inferred from the docs or examples; strongly implied but never stated. |
| **[gap]** | Undocumented or contradictory. A reimplementation has to choose; §16 lists every gap with narrate's choice. |

Source keys used in the `Sources:` lines:

| Key | Page |
| --- | --- |
| `format` | `/docs/format/` (the full reference) |
| `script` | `/docs/script/` (getting started) |
| `subs-style` | `/docs/scripting/subtitle-font-size-color.html` |
| `subs-howto` | `/docs/add-subtitles-to-video/`, `/docs/how-to/create-closed-captions-and-subtitles.html` |
| `callouts` | `/docs/scripting/designing-callouts.html` |
| `panzoom` | `/docs/scripting/pan-zoom-image-animations.html`, `/docs/how-to/kenburns-powerpoint.html` |
| `pauses` | `/docs/how-to/add-pauses-to-text-to-speech-voiceovers.html`, `/docs/how-to/pause-voiceover-narration.html` |
| `speed` | `/docs/how-to/change-text-to-speech-reading-speed.html` |
| `pitch` | `/docs/how-to/control-voice-pitch.html` |
| `multilingual` | `/docs/how-to/create-multilingual-content.html`, `/docs/how-to/voice-over-video-language.html` |
| `pinyin` | `/docs/how-to/use-pinyin-phonemes.html` |
| `normalize` | `/docs/how-to/normalize-voiceover.html` |
| `compression` | `/docs/how-to/optimize-video-compression.html` |
| `visuals` | `/docs/improve-video-visuals/` |
| `music` | `/docs/background-music/` |
| `faq` | `/docs/faq/` |
| `api` | `/docs/automating/`, `/docs/automating/video-api/`, `/docs/automating/cli/video/`, `/docs/automating/github/` |
| `pricing` | `/docs/pricing/` (limits table) |
| `news:<date>` | `/news/<date>/…` announcement posts |
| `ex:<project>` | `github.com/narakeet/examples/<project>` |

---

## 1. Project and build inputs

A build takes two inputs:

1. **A project:** a directory or ZIP archive holding one script and every asset
   it references.
2. **A source path:** the location of the main script inside the project.

Rules:

- The script file should have a `.md`, `.mkd` or `.txt` extension.
  `ex:tiktok-style-subtitle-videos` uses `video.txt`.
- Asset references resolve **relative to the directory containing the script**.
  A flat project (script and assets side by side) is the recommended layout.
- Symbolic links are not supported; files must be real.
- The project may contain files the script never references; they are ignored
  [inf].
- Asset formats accepted:
  - **Images:** JPG, GIF (static or animated), PNG.
  - **Video:** MP4, MOV, M4V, WEBM, WMV, AVI, MPEG.
  - **Audio:** WAV, MP3, WMA, AAC, M4A.
  - **Fonts:** TrueType `.ttf`, for subtitle fonts and CSS `@font-face`.
  - **Stylesheets:** `.css` slide themes.
- Narakeet's limits for paid accounts: 500 scenes, 2,048 KB script, 350 MB
  upload. The free tier allows 30 scenes, a 10 KB script and 10 MB uploads.
  A local tool need not enforce any of these.

Sources: `script`, `format`, `api`, `pricing`, `faq`.

## 2. Document structure

A script is a sequence of **scenes**, optionally preceded by a **header**.
Each scene is a sequence of **blocks**.

```
script   := [header] scene ( separator scene )*
header   := "---" NL yaml-mapping NL "---"      ; only at the very start of the file
separator:= a line consisting of 3 or more "-" characters
```

### 2.1 Header

- The header exists only if the file **starts** with the separator line. Everything
  up to the next separator is parsed as a YAML mapping (one `key: value` per
  line; any YAML is legal, including nested maps).
- Because it is YAML, a `#` begins a comment, so hex colours must be quoted
  (`canvas: "#00FF76"`).
- Blank lines inside the header are tolerated (`ex:subtitle-styling`) [obs].

### 2.2 Scene separators

- Documented form: a paragraph consisting only of three or more dashes, with
  blank lines around it.
- Observed leniency [obs]:
  - A stage direction can sit on the line immediately after a separator
    (`---` then `(transition: none)`, `ex:code-tutorial-demo-video`).
  - A separator can sit directly after a closing code fence.
- A `---` line **inside a fenced code block is content, not a separator**.
  `ex:voices` shows a YAML header inside a fenced slide.
- Empty scenes (for example from a trailing separator) should be dropped [gap].

### 2.3 Block types inside a scene

Strip HTML comments (`<!-- … -->`, which may span lines and contain blank
lines) **before** any other recognition. `ex:hello-world` has a comment
containing `(audio: file)`, which must not run.

Then classify each block (CommonMark block structure) in this order:

| Block | Recognised by | Section |
| --- | --- | --- |
| Fenced code block (` ``` ` or `~~~`) | CommonMark fence | §9 text slides |
| Block quote | lines starting with `>` | §8 subtitles |
| Stage direction | a paragraph whose text is `( … )` | §7 |
| Media reference | a paragraph consisting of a Markdown image `![tokens](file)` | §5 |
| SSML narration | a paragraph wrapped in `<speak> … </speak>` | §6.6 |
| Narration | any other paragraph | §6 |

Separation rules:

- The docs require a blank line around every stage direction. A direction
  without blank lines is otherwise read aloud as narration.
- Observed leniencies [obs]:
  - Several single-line directions stacked on consecutive lines, with no
    blank lines between them, each take effect (`ex:transition-types`:
    `(canvas: sienna)` / `(duration: 1)` / `(transition: circle 0.5)`).
  - A single-line direction directly after a closing fence also takes effect
    (`ex:code-tutorial-demo-video`).

  A compatible parser should therefore treat **any line that is entirely
  `(key: value)`** as a direction, and treat a multi-line `(` … `)` paragraph as
  one direction.
- Some Narakeet doc pages show directions inline within a sentence on one line
  (for example `… load. (pause-until: 10.04) Click …`). These come from
  whitespace collapsed in Narakeet's published HTML (the same pages show
  `--- size: 720p target: self-hosted ---` on one line), **not** from an inline
  syntax. Inline directions are not supported.

Sources: `format` (Header, Scenes, Comments, Stage directions), `script`,
`add-voice-to-video`, `ex:*`.

---

## 3. Header properties

Header-only properties:

| Property | Value | Default |
| --- | --- | --- |
| `asset-resize` | `fit` \| `contain` \| `cover` | `cover` |
| `background` | `<file-or-builtin> [volume] [fade-in] [fade-out]` | none |
| `poster-time` | `start` \| `end` \| `N%` \| seconds \| timecode | `50%` [gap] |
| `size` | preset (§3.2) or `WIDTHxHEIGHT` | `720p` (1280×720) |
| `subtitles` | mode string or map (§8) | none [inf] |
| `target` | `offline` \| `online` \| `self-hosted` | `offline` |

Properties that are also stage directions (as a header they set the default
for every scene):

| Property | Value | Default |
| --- | --- | --- |
| `canvas` | colour name or quoted `"#RRGGBB"` (no alpha) | black padding; slide background comes from the theme |
| `narration-language` | `ll` or `ll-RR` (ISO 639-1 / 3166-1) | voice's primary language |
| `theme` | `default` \| `light` \| `<file>.css` | `default` |
| `transition` | `<type> [seconds]` (§10) | none |
| `voice` | voice name, or `name/ll-RR` (§6.1) | account default [gap] |
| `voice-pitch` | `x-low` \| `low` \| `normal` \| `high` \| `x-high` \| number −150…150 | `normal` |
| `voice-speed` | `slow` \| `normal` \| `fast` \| number 0.3…2 (multiplier) | `normal` |
| `voice-volume` | `x-soft` \| `soft` \| `standard` \| `loud` \| `x-loud` \| `normalized` | `standard` |

Notes:

- **`asset-resize`** sets the default fit policy for images and videos whose
  aspect ratio differs from the output:
  - `fit` stretches the asset.
  - `contain` letterboxes it, padding with the `canvas` colour (black by
    default).
  - `cover` scales it to fill the frame and crops the overflow.

  Each asset can override the policy (§5).
- **`background`:**
  - A project audio file, or one of the built-in tracks `ukulele-1`,
    `ukulele-2`, `uplifting-1`, `uplifting-2`, `corporate-1`.
  - The track loops for the whole video.
  - Optional tokens, separated by spaces, after the name:
    - a positive volume multiplier (1 means original level);
    - `fade-in`, which ramps the volume up during the first scene;
    - `fade-out`, which ramps it down during the last scene.
  - The fades may appear in any order (`jungle.mp3 0.5 fade-out fade-in`).
  - The music mixes with narration and with any audio from embedded videos.
- **`canvas`:**
  - Pads resized assets and is the default slide background.
  - Takes a colour name or a quoted `#RRGGBB` value. RGBA is rejected because
    video has no transparency.
- **`poster-time`:**
  - Picks the frame used for the poster image: `start`, `end`, a percentage, a
    number of seconds (`33`) or a timecode (`01:30`).
  - The docs state both "from the first frame" and "default is 50%" [gap].
- **`target`** selects an encoding profile (§12).
- **`voice-volume`:**
  - `standard` applies no adjustment, so voices may differ in loudness.
  - `normalized` loudness-normalises every voice sample to EBU R 128 so mixed
    voices sound equally loud. Pitch changes combined with normalisation "may
    create unexpected effects".
  - The old value `normal` is a deprecated alias of `standard`.
- **`voice-pitch`:** the number's unit is unspecified [gap]. About 80% of
  Narakeet voices support pitch at all.

Sources: `format` (Header), `music`, `normalize`, `pitch`, `compression`, `news:2023/01/09`.

### 3.2 Size presets

| Preset | Pixels | Preset | Pixels |
| --- | --- | --- | --- |
| `720p` | 1280×720 | `pinterest-square` | 1080×1080 |
| `1080p` | 1920×1080 | `pinterest-vertical` | 720×1280 |
| `1440p` | 2560×1440 | `pinterest-2x3` | 720×1080 |
| `4x3` | 800×600 | `linkedin` | 1728×720 |
| `720p-portrait` | 720×1280 | `linkedin-vertical` | 720×1728 |
| `1080p-portait` ¹ | 1080×1920 | `tiktok` | 1080×1920 |
| `instagram` | 1080×1350 | `twitter` | 1280×720 |
| `instagram-square` | 1080×1080 | `twitter-square` | 720×720 |
| `instagram-story` | 1080×1920 | `facebook` | 1280×720 |
| | | `facebook-square` / `facebook-carousel` | 1080×1080 |

¹ Spelled `portait` in the docs; accept `1080p-portrait` too [gap].

Custom sizes use `WxH` (for example `800x600` or `1080x1920`).

---

## 4. Scene model and timing

This section describes how a scene's tracks combine. It is the core behaviour
a renderer has to reproduce.

### 4.1 Tracks in a scene

- **Visual track**
  - **Images:** zero or more. Several images play in sequence, sharing the
    scene's duration roughly equally (`news:2022/05/12`).
  - **Videos:** zero or more. Mixing several videos, or videos with images,
    in one scene is undocumented [gap].
  - **Text slide:** zero or one fenced code block, composited **over** the
    image or video, or over the `canvas` colour when there is no image or
    video (§9). More than one slide per scene is undocumented [gap].
  - **Callouts:** zero or more highlights or masks over the image or video
    (§7, `callout`).
  - **No visual at all:** a scene with only narration is legal
    (`ex:subtitles`) and renders the canvas/theme background [inf].
- **Narration track:** an ordered sequence of segments, played back to back,
  never in parallel:
  - **TTS block:** one narration paragraph, followed by an end-of-block pause
    set by `narration-mode`.
  - **`pause: N`:** N seconds of silence.
  - **`pause-until: T`:** silence until offset T from the scene start. It does
    nothing if T has already passed. T is at most 10 minutes.
  - **`audio: file`:** a recorded clip, played in sequence with the
    generated narration.
- **Clip audio:** the soundtrack of embedded videos, scaled by their `volume`.
- **Background music:** a global track (§3).
- **Subtitle track:** cues generated from narration, or written explicitly as
  block quotes (§8).

### 4.2 Scene duration

Let **A** be the total length of the narration track.

1. **The scene has a video.** The video's `sync` mode decides the length
   (table below).
2. **No video and A > 0.** The duration is A. Images, slides and animated
   GIFs follow the audio.
3. **No audio.**
   - With a `duration: N` direction, the scene lasts N seconds. Decimals are
     allowed (`0.5` in `ex:slide-css-theming`).
   - A scene with only a video and no narration plays the whole video
     (`ex:video-segments`) [obs].
   - An animated GIF with no audio plays **one cycle** (`ex:gifs`) [obs].
   - A text slide with no audio lasts **1 second**.
   - An image with no audio and no `duration`: undocumented [gap]. The
     PowerPoint path uses 5 seconds.
4. **`duration` together with audio:** undocumented [gap].

`pause` also works for lengthening a scene, because it adds silence to A. The
docs recommend `duration` for silent scenes and `pause` to "hold" the final
scene after the narration ends.

**Video `sync` modes** (default `freeze`). Here V is the video length and A the
audio length:

| Mode | Behaviour | Scene length |
| --- | --- | --- |
| `freeze` | Plays at normal speed. If V < A the last frame holds; if V > A the video still plays to the end. | max(V, A) |
| `match` | Time-stretches the video (faster or slower) to fit the audio. | A |
| `trim` | Normal speed; the scene stops when **either** the video or the audio ends, cutting off any remaining audio. | min(V, A) |
| `loop` | Repeats the video to cover the audio. If V > A the whole video plays and the audio is not repeated. | max(V, A) |
| `trim-or-loop` | Loops if V < A, cuts the video if V > A. | A |
| `loop-audio` | Repeats the audio to cover the video. If A > V the video is not repeated (it holds) [inf]. | max(V, A) |

**Animated GIFs** use the same modes, but default to `loop`.

### 4.3 State and scoping

- **Header values are the baseline for every scene.**
- **Scene-scoped directions** apply to the narration blocks that follow them
  in the **same scene**, and reset to the header value at the next scene:
  `voice`, `voice-speed`, `voice-pitch`, `voice-volume`, `voice-emphasis`,
  `narration-language`. Use them repeatedly to switch back and forth.
- **Whole-scene directions:**
  - `canvas`, `theme`, `transition`, `font-size`, `duration`.
  - `image-size` / `image-position` apply to the images that follow them in
    the scene.
  - `callout` applies to the scene's image or video. `ex:callouts` puts one
    before the image and one after; both work [obs].
  - Placement of `duration` relative to the image doesn't matter [obs].
- **`theme` placement:** it must appear before the slide it styles.
- **`narration-mode` is the exception: it persists across scenes.**
  - `merge` is set in the first scene of a run and stays on until
    `(narration-mode: normal)` in the last scene.
  - `fragment` is re-stated in each scene in the examples. Whether it persists
    across scenes is unclear [gap].

### 4.4 Narration modes

| Mode | End-of-block pause | Sync point |
| --- | --- | --- |
| `normal` | a paragraph-length pause | each scene is synced to its own audio |
| `fragment` | a short, between-words pause, so one sentence can run across scenes | each scene is still synced to its own audio |
| `merge` | the narration of every merged scene is synthesised as **one continuous** block | the images of the merged scenes split that block's time proportionally |

The docs note that `merge` mostly matters for PowerPoint. In a script, putting
several images in one scene gives the same result.

Sources: `format` (Images, Videos, Narration, Audio files, Text slides, Stage
directions), `visuals`, `pauses`, `speed`, `news:2020/09/15`, `news:2022/05/12`,
`news:2023/05/10`, `ex:gifs`, `ex:video-audio-sync`, `ex:video-segments`,
`ex:callouts`.

---

## 5. Media references

### 5.1 Syntax

Either Markdown image syntax, with the options written in the alt text:

```
![<token> <token> …](path)
```

or the equivalent stage direction, whose value is a file name or a YAML map:

```
(image: file.jpg)
(image:
  file: file.jpg
  size: panzoom
  position: left
  sync: freeze)
(video: {file: clip.mp4, segment: 00:02 - 00:04, sync: loop, volume: 0.5})
```

- The media type comes from the file extension.
- The directive form exists because some Markdown editors won't show a video
  in image syntax.
- The format reference itself uses `![](audio.mp3)` once (Subtitles section).
  An audio file in image syntax is probably treated like `(audio: …)` [gap].

### 5.2 Alt-text tokens

The alt text is a list of tokens separated by whitespace. Each token falls into
one category by its value, and tokens combine freely (`![cover top-left]`,
`![00-08 match]`, `![0-2 trim-or-loop]`, `![panzoom right]`, all [obs]).

| Category | Values | Applies to |
| --- | --- | --- |
| size | `fit`, `contain`, `cover` | images, videos |
| animated size | `zoom`, `zoomout`, `pan`, `panzoom`, `panzoomout` | images |
| position | `center`, `top-left`, `left`, `right`, `top`, `bottom` | images ([gap] for videos) |
| sync | `freeze`, `match`, `trim`, `loop`, `trim-or-loop`, `loop-audio` | videos, animated GIFs |
| segment | `T-T` (no spaces), `start`, `end`, single `T` | videos |
| volume | `mute` (same as volume 0) | videos |

There are no `top-right`, `bottom-left` or `bottom-right` positions.

### 5.3 Images

- **Static sizes:** `fit`, `contain` and `cover` work as in `asset-resize`.
  With `cover`, the position chooses which part survives the crop; the default
  is the centre.
- **Animated sizes** (Ken Burns):
  - `zoom` starts at full cover and zooms in.
  - `zoomout` starts zoomed in and ends at full cover.
  - `pan` covers the frame, then drifts from the centre toward the `position`
    edge.
  - `panzoom` and `panzoomout` combine the pan with a zoom in or out.
  - The pan forms need a position. Without one the effect stays centred
    (`panzoom`).
  - The source should be well above the frame size (1080p or 1440p for a 720p
    video), or the motion looks jittery.
- **Several images in one scene** play in sequence, each for roughly an equal
  share of the scene.
- **Animated GIFs** loop to match the scene audio by default. `freeze` plays
  one cycle and then holds the last frame.

### 5.4 Videos

- **Size:** as for images (`fit`, `contain`, `cover`).
- **`segment`:** `start-end`, where each end is a time (§5.5) or the word
  `start`/`end`.
  - In alt text there must be no spaces (`00:02-00:04`, `10-14.5`, `00-08`).
  - The directive form may use spaces (`00:02 - 00:04`, `1 - 2`).
  - A single value (`start`, `end` or a time `T`) shows that one **still
    frame**.
- **`sync`:** §4.2. Defaults to `freeze`.
- **`volume`:** a multiplier on the clip's own soundtrack (`0.5`, `3`). `0` or
  `mute` silences it.
- **PowerPoint only:** a slide's embedded video replaces the slide image.

### 5.5 Time values

```
time := seconds | MM:SS | HH:MM:SS     ; seconds may be zero-padded ("08") and fractional;
                                       ; fractional seconds also allowed on MM:SS ("01:20.5", "00:15.512")
```

Used by `segment`, `pause-until`, `poster-time` and (seconds only) `pause` and
`duration`.

Sources: `format` (Images, Videos), `panzoom`, `news:2020/04/15`, `ex:image-sizing`,
`ex:image-panzoom`, `ex:video-segments`, `ex:video-sizing`, `ex:video-volume`,
`ex:screencast-demo-video`, `ex:gifs`.

---

## 6. Narration

Any paragraph that isn't another block type is narrated by the active voice.

- Soft line breaks inside a paragraph join into one stretch of text.
- A blank line between paragraphs:
  - makes a slightly longer pause;
  - starts a new subtitle cue (§8).

  More blank lines don't lengthen the pause.

### 6.1 Voices

- `voice` (header or direction) takes a Narakeet voice name.
- Names are case-insensitive [obs: `brian` vs `Brian`, `carmen` vs `Carmen`].
- Since 2026-04 a polyglot voice can be pinned to a language:
  `(voice: xenobot/de-DE)` (`news:2026/04/14`). This form is not in the format
  reference.
- A local implementation needs a mapping from voice names (and optionally
  `name/lang`) to its own engine voices. Narakeet's catalogue (~900 voices) is
  not part of the format.

### 6.2 Inline markup inside narration

| Markup | Effect |
| --- | --- |
| `_text_` or `*text*` | moderate emphasis |
| `__text__` or `**text**` | strong emphasis |
| `~~text~~` | reduced emphasis |
| `` `text` `` | spell out letter by letter (literal style), including punctuation such as `` `?` `` |
| `[text]{style}` | narration span with a pronunciation style (§6.3) |
| `[text]{lang}` | narration span read in another language, e.g. `[See]{de}`, `[Amy]{en}`, `[See]{de-DE}` |
| `…` or `...` | explicit inline pause of about 0.5 s (since 2024-05, `news:2024/05/28`) |
| `^` before a vowel | stress mark; only for some Russian voices (`news:2020/12/08`) |

Notes:

- The docs advise wrapping emphasis around **whole sentences**. Mid-sentence
  emphasis "might create weird pauses".
- The emphasis markup does the same as the `voice-emphasis` direction.
- Can one span combine a style and a language? Undocumented [gap].
- Other inline Markdown in narration (links, inline HTML) is undocumented
  [gap]. Treating it as plain text is the safe choice.
- Engine behaviour rather than syntax, but users rely on it:
  - Punctuation gives short natural pauses.
  - Most voices spell out ALL-CAPS words as acronyms.

### 6.3 Narration styles (span `{style}` values)

| Style | Content of the span |
| --- | --- |
| `normal` | read normally |
| `ipa` | IPA phonemes, e.g. `[təˈmeɪ.toʊ]{ipa}` |
| `x-sampa` | X-SAMPA phonemes |
| `literal` | spell out (same as backticks) |
| `pinyin` | Mandarin Pinyin. Whole syllables separated by spaces, tones as diacritics or digits (`[Běi jīng]`, `[bei3 jing1]`, `[bei 3 - jing 1]`). |
| `jyutping` | Cantonese Jyutping, with tone digits (superscript or plain): `[hoeng1 gong2]`, `[Hoeng¹ Gong²]` |

Narakeet supports each style only on some voices. Its `/docs/narration-styles/`
page has a per-voice table, which a local tool doesn't need.

### 6.4 Language switching

- **For a whole run of text:** the `narration-language` direction switches the
  pronunciation language without changing the voice. It applies to everything
  that follows in the scene; `default` switches back.
- **For a word or phrase:** a `{lang}` span does the same.
- **The voice keeps its own accent.** A German voice reading English sounds
  German-accented. Polyglot voices give a native accent in the second
  language.
- Valid values are `default`, `ll` (ISO 639-1) or `ll-RR` (plus ISO 3166-1
  region). Narakeet accepts only the combinations it supports.

### 6.5 Voice-property directions

`voice-speed`, `voice-pitch`, `voice-volume` and `voice-emphasis` (values in
§3 and §7) change the narration that follows in the scene. Use `normal` (or
`none` for emphasis) to switch back.

### 6.6 SSML

- A paragraph wrapped entirely in `<speak>…</speak>` is passed to the engine as
  SSML. It may span several lines with indentation.
- SSML can't be mixed with plain text inside a paragraph.
- Tags used in the docs and examples: `<prosody rate pitch>` (`pitch="-2st"`),
  `<say-as interpret-as="verbatim">`, `<emphasis level>`. Tag support varies
  by voice.
- A local tool should define the SSML subset it supports and reject or strip
  the rest [gap].

Sources: `format` (Narration, Controlling pronunciation, Using SSML),
`add-voice-to-video`, `pauses`, `multilingual`, `pinyin`, `news:2020/12/08`,
`news:2024/05/28`, `news:2026/04/14`, `ex:pronunciation`, `ex:voices`.

---

## 7. Stage directions

The syntax is a paragraph in parentheses. The content inside the parentheses
is parsed as **YAML**:

- `(key: value)` gives `{key: value}`.
- An indented block or a flow map gives a map value:
  - `(callout:` / `  cx: 200` / `  cy: 250)`
  - `(image: {file: a.jpg, size: cover})`
- The closing parenthesis may end the last value line or sit on its own line.
- Sub-properties are indented with two spaces or a tab.

| Direction | Value | Effect and scope |
| --- | --- | --- |
| `audio` | file | Adds a recorded clip to the narration sequence. Several play in order and mix freely with TTS blocks. |
| `callout` | map (below) | Highlights or masks part of the scene's image or video. |
| `canvas` | colour | Padding and slide background for this scene. |
| `duration` | seconds | How long a scene with no audio lasts (§4.2). |
| `font-size` | positive integer (px) | Base font size of this scene's text slide (default 50). |
| `image` | file or map {`file`, `size`, `position`, `sync`} | Adds an image (§5). |
| `image-size` | size or animated-size token | Default size for the images that follow in the scene. |
| `image-position` | position token | Default position for the images that follow in the scene. |
| `narration-mode` | `fragment` \| `merge` \| `normal` | §4.4. Applies to the blocks that follow; persists across scenes. |
| `narration-language` | `default` \| `ll` \| `ll-RR` | §6.4. Scene-scoped. |
| `pause` | seconds (decimals OK) | Silence in the narration sequence. |
| `pause-until` | seconds or timecode | Silence until an offset from the scene start (max 10 min). Does nothing if the offset has passed. |
| `theme` | `default` \| `light` \| `<file>.css` | Slide theme for this scene. Place it before the slide. |
| `transition` | `<type> [seconds]`, or `<seconds>` alone [obs] | Incoming transition into this scene. Not allowed on the first scene. `none` disables a global transition. |
| `video` | file or map {`file`, `size`, `segment`, `sync`, `volume`} | Adds a video (§5). |
| `voice` | name or `name/ll-RR` | Active voice for the blocks that follow (scene-scoped). |
| `voice-emphasis` | `strong` \| `moderate` \| `none` \| `reduced` | Scene-scoped. |
| `voice-pitch` | as the header | Scene-scoped. |
| `voice-speed` | as the header | Scene-scoped. |
| `voice-volume` | as the header | Scene-scoped. |

**`callout` map:**

| Key | Value | Default |
| --- | --- | --- |
| `type` | `circle` \| `rectangle` | `circle` |
| `cx`, `cy` | circle centre in output-frame pixels from the top-left | — |
| `size` | circle radius in px | 100 |
| `left`, `top`, `right`, `bottom` | rectangle bounds in output-frame pixels | — |
| `alpha` | opacity of the shade over the **rest** of the frame, 0–1 | 0.5 |
| `style` | `mask` paints over the area itself (for example to hide a password) instead of highlighting it; works with circles too [obs] | highlight |

Notes:

- Coordinates are in **output video** pixels, after resizing. Narakeet's web UI
  has a visual "callout designer" for this reason.
- The mask colour (black, opaque) is shown but not specified [gap].
- How callouts combine with several images or a video segment is unspecified
  [gap].

**Deprecated aliases a compatible parser should accept:**

- `subtitles: auto`, the same as `overlay` (still used by `ex:gifs`).
- `voice-volume: normal`, the same as `standard`.

Sources: `format` (Stage directions), `callouts`, `news:2021/03/16`, `ex:callouts`,
`ex:transition-types`, `ex:feature-announcement-demo-video`, `ex:slide-css-theming`.

---

## 8. Subtitles

### 8.1 Modes (`subtitles:` header string)

| Mode | Output |
| --- | --- |
| `none` | no subtitles |
| `external` | SRT and VTT files only |
| `embed` | an MP4 subtitle track in the video, plus SRT and VTT files |
| `overlay` | burned in: white text with a black outline |
| `overlay-background` | burned in: white text on a semi-transparent black box |
| `tiktok` | burned in: very large font in the middle of the frame |
| `auto` | deprecated alias of `overlay` |

### 8.2 Map form

The map form sets `mode` (required) to `embed` or `overlay`, plus these
properties:

| Key | Applies to | Value |
| --- | --- | --- |
| `break` | embed and overlay | Maximum characters per cue. The default break falls at 130–140 characters. |
| `scale` | overlay | Font-size multiplier on the automatic size. The automatic size fits about two lines in the frame. Exclusive with `size`. |
| `size` | overlay | Font size in px. Exclusive with `scale`. |
| `color` | overlay | Text colour: a web colour name or quoted `"#RRGGBB"` / `"#RRGGBBAA"`. Default white. |
| `outline` | overlay | Outline colour. Exclusive with `background`. |
| `background` | overlay | Colour of a box behind the text, instead of an outline. |
| `font` | overlay | A `.ttf` file in the project. |
| `position` | overlay | `top` \| `middle` \| `bottom` (default). |

The reference says `outline` and `background` both default to "white". That
contradicts the described black outline and black box [gap; use black].

### 8.3 Cue generation

1. **From narration** (when a mode other than `none` is set):
   - Each narration paragraph becomes a cue that starts when its audio starts.
   - A paragraph longer than `break` splits into several cues.
   - The split cues share the paragraph's audio time "equally" [gap: equal or
     by character count].
   - Cues follow the real audio timeline, so pauses delay the next cue
     (`ex:subtitles`).
   - The docs advise one sentence per paragraph for tight sync.
2. **Explicit block quotes** (`> text`):
   - A scene with any block quote shows the quotes **instead of** its
     narration text.
   - Consecutive `>` lines form one multi-line cue.
   - Separate block quotes become separate cues, shown in turn [gap: how
     their timing is split].
   - Block quotes are also how scenes with recorded audio or no audio get
     captions.
   - Block quotes show even without a `subtitles` header
     (`ex:callouts`, `ex:video-segments`) [obs]. With no mode set they are
     burned in [inf].
3. **An empty block quote** (a lone `>`) suppresses subtitles for that scene
   (`ex:subtitles`) [obs].
4. **Inline markup** (`**`, backticks, spans) is presumably removed from cue
   text [inf].

Sources: `format` (subtitles header, Subtitles), `subs-style`, `subs-howto`,
`news:2023/07/22`, `ex:subtitles`, `ex:subtitle-styling`, `ex:tiktok-style-subtitle-videos`.

---

## 9. Text slides and themes

### 9.1 Slides

- A fenced code block (` ``` ` or `~~~`) is rendered **on screen** as a slide.
  It is not narrated.
- The info string after the opening fence sets the content type:
  - **None, or `txt`/`plaintext`:** plain text.
  - **`md`:** rendered Markdown (headings, bullets with nesting, emphasis).
  - **Any language name** (`css`, `js`, `xml`, `yml`, …): syntax-highlighted
    code.
- Text inside a fence is literal. `(voice: Joanna)` or `---` inside a fence is
  displayed, not run (`ex:voices`).
- Base font size is 50 px; the `font-size` direction changes it.
- **Slide over an image:**
  - The `default` theme adds a backdrop that greys the image and adds a light
    shadow.
  - The `light` theme adds no backdrop.
- **Slide over a video:** backdrops are not supported.

### 9.2 Themes

| Theme | No background | Over an image or video |
| --- | --- | --- |
| `default` | black text on white | white text on a backdrop |
| `light` | white text on black | white text, no backdrop |
| `<file>.css` | your CSS | your CSS |

### 9.3 CSS theme contract

The slide is rendered as HTML, so a reimplementation needs a browser-grade
renderer (or must deliberately support only a subset). The CSS contract:

- Style `body`, `h1`, `h2`, … and lists directly.
- `@font-face` may load a project font by relative URL
  (`src: url('waltographUI.ttf')`).
- The `body` background (colour or pattern) shows only when the slide is
  **not** over an image or video.
- The `.backdrop` class takes any CSS `backdrop-filter` (for example
  `blur(20px)`) for slides over images.

Sources: `format` (theme, Text slides, font-size), `ex:slides`,
`ex:slide-css-theming`, `ex:code-tutorial-demo-video`, `news:2020/04/10`.

---

## 10. Transitions

- **Syntax:** `<type> [seconds]`. The default duration is 0.2 s.
- **As a header**, it sets the transition between every pair of scenes. **As a
  direction**, it sets the incoming transition of one scene. It is not allowed
  on the first scene. `none` turns the transition off for one scene.
- **Duration-only form:** `(transition: 1)` and `(transition: 0.2)` appear in
  official examples [obs]. The meaning is not stated [gap].

| Family | Values |
| --- | --- |
| fade | `crossfade` |
| wipe (new scene slides over the old) | `wipe` (= `wipe-right`), `wipe-right`, `wipe-left`, `wipe-up`, `wipe-down` |
| slide (pushes the old scene out) | `slide-right`, `slide-left`, `slide-up`, `slide-down` |
| soft wipe (wipe with a small fade) | `fade-right`, `fade-left`, `fade-up`, `fade-down`, `fade-circle` |
| slice (stepped wipe) | `slice-right`, `slice-left`, `slice-up`, `slice-down` |
| pixel | `dissolve` (fine), `pixelize` / `pixelise` (coarse) |
| shape | `radial` (clockwise from the centre), `circle`, `rect` (shrink then grow), `reveal` |
| off | `none` |

The directional descriptions in the docs are inconsistent (for example
`slide-left` "moving vertically"). Most of these names match ffmpeg `xfade`
transitions (`wipeleft`, `slideright`, `fadeblack`, `circleopen`, `dissolve`,
`pixelize`, `radial`, `rectcrop`, …), which suggests how Narakeet renders them
[inf]. Whether a transition overlaps the two scenes (shortening the video) or
adds time is unspecified [gap].

Sources: `format` (transition), `news:2021/03/16`, `ex:transition-types`, `ex:transitions`.

---

## 11. Audio mixing summary

The final audio mix combines:

- **The narration sequence**, with `voice-volume` applied per block, or EBU
  R 128 normalisation per sample when `normalized` is set.
- **Clip audio** from embedded videos, scaled by `volume`.
- **Background music**, looped, scaled by its volume multiplier and shaped by
  `fade-in` and `fade-out`.

Narration and clip audio play at the same time; a clip's soundtrack is not
ducked automatically [inf]. Narakeet's only automatic ducking is the
background `fade-out`.

---

## 12. Outputs

What Narakeet produces, and what a local tool should produce for parity:

| Output | Notes |
| --- | --- |
| Video | MP4 (`result.mp4` by default in the CLI). Codecs are unstated; H.264 + AAC is the safe assumption [inf]. |
| Poster | A JPG frame chosen by `poster-time`. |
| Subtitles | `.srt` and `.vtt` for the `external` and `embed` modes. |
| Duration | Seconds, rounded up (the API's `durationInSeconds`). |

The `target` profiles:

| `target` | Compression | `moov` atom |
| --- | --- | --- |
| `offline` (default) | very low compression, the largest files, meant for editing | at the end |
| `online` | slightly more compression, for upload to YouTube and similar | at the start (faststart) |
| `self-hosted` | the smallest files, for HTML5 and in-app playback, not for re-transcoding | at the start (faststart) |

Narakeet's own interfaces (for reference if the local CLI should mirror them):

- **CLI:** `narakeet-api-client --repository-type local-dir|local-zip|zip-url|github
  --repository <path|url|owner/repo> --source <script path> [--output file.mp4]`.
- **REST:** upload a ZIP to a presigned URL, `POST /video/build {repositoryType,
  repository, source}`, then poll the status URL for `finished`, `percent`,
  `succeeded`, `result`, `poster`, `message` and `durationInSeconds`.
- **GitHub Action outputs:** `video-file`, `poster-file`, `srt-file`,
  `vtt-file`, plus signed URLs for each.

Sources: `compression`, `api`, `news:2023/01/09`.

---

## 13. Defaults at a glance

| Setting | Default |
| --- | --- |
| size | 720p, 1280×720 |
| asset resize | `cover`, centred |
| padding colour | black |
| theme | `default` |
| slide font size | 50 px |
| transition | none (0.2 s when a type is given without a duration) |
| video sync | `freeze` |
| animated GIF sync | `loop` |
| scene with only a text slide | 1 s |
| scene with only an animated GIF | one cycle [obs] |
| scene with only a video | the whole video [obs] |
| ellipsis pause | about 0.5 s |
| `pause-until` maximum | 10 min |
| subtitle break | about 130–140 characters |
| subtitle position | bottom |
| subtitle style | white text, black outline |
| callout | circle, radius 100 px, alpha 0.5 |
| poster | 50% of the duration [gap] |
| encoding target | `offline` |
| voice speed / pitch / volume / emphasis | `normal` / `normal` / `standard` / `none` |

---

## 14. Features that depend on the speech engine

These are part of the format, but whether they can be honoured depends on the
TTS engine. A local tool should either support them or warn and degrade
gracefully, never fail silently:

- **Prosody:** emphasis levels; pitch presets and numbers; speed presets and
  multipliers; volume presets.
- **Phonetics:** IPA and X-SAMPA spans; Pinyin and Jyutping spans; Russian `^`
  stress.
- **Language:** language spans and `narration-language` (cross-language
  pronunciation).
- **Spelling:** literal spelling (backticks and `{literal}`), which can be
  implemented in text by expanding letters.
- **SSML** paragraphs.
- **Voice catalogue:** voice names, including the `name/lang` form.

---

## 15. Conformance corpus

`github.com/narakeet/examples` holds 22 small projects, each with a script and
its assets. They are the closest thing to a test suite.

**The repository has no licence.** Fetch it at test time; don't vendor it into
this repo. `scripts/fetch-narakeet-reference.sh` copies the scripts into
`reference/examples/`; with `--media` (`just reference`) it also fetches their
media and the `result.mp4` Narakeet rendered from each.

| Project | Exercises |
| --- | --- |
| `hello-world` | images, narration, `(audio:)`, comments containing directive-like text |
| `voices` | `voice` header and direction; fenced slides containing `---` and directives |
| `pronunciation` | `pause`, emphasis markup, `voice-emphasis`, `voice-volume`, `voice-speed`, SSML paragraph |
| `image-sizing` | `![](…)`, `contain`, `fit`, `top`, `bottom` |
| `image-panzoom` | several images per scene; all animated sizes with positions; built-in background with `fade-in` |
| `gifs` | GIF `loop`/`freeze`; GIF with no narration; `pause` extending a GIF; `subtitles: auto` |
| `video-sizing` | video `cover`/`contain`/`fit`; directive with `size` and `segment` |
| `video-segments` | whole video; `start`/`end` still frames; a `T-T` range |
| `video-audio-sync` | every `sync` mode, in both alt-text and directive form |
| `video-volume` | `volume` 0.5 and 3; `mute` |
| `slides` | plain, `md` and `css` slides; `font-size`; slides over an image and a video; `theme: light` |
| `slide-css-theming` | `theme: custom.css`; a font via `@font-face`; `.backdrop`; `theme: default` reset; duration-only `transition` |
| `subtitles` | narration cues following pauses; explicit `>` cue; empty `>`; paragraph split; long-text break |
| `subtitle-styling` | map form with `break`, `background`, `color`, `scale` |
| `tiktok-style-subtitle-videos` | `.txt` script; custom size; `font`, `position: middle`, `size`, `break`; `match` |
| `callouts` | circle, rectangle, `alpha`, `style: mask`; callout on a video |
| `transitions` | header transition; per-scene override; directive `segment` with spaces |
| `transition-types` | every transition type; stacked directives on consecutive lines; `canvas` names |
| `background-audio` | `background: file volume` |
| `vendor-audio` | built-in background track |
| `code-tutorial-demo-video` | long-form script: theme CSS, `subtitles: embed`, video segments with `match`, `transition: none` straight after `---` |
| `feature-announcement-demo-video` | `narration-mode: fragment` across scenes, `.mov` clips, `(transition: 1)` |
| `screencast-demo-video` | fractional segments, `trim` intro, rectangle callout, backticked acronyms |

---

## 16. Gaps and how narrate resolves them

Each item below is something the docs leave open, or where the docs and the
examples disagree, with what narrate does about it. The choices favour what
the official examples imply.

1. **Directive recognition.** Any whole line `(key: value)` is a directive,
   which covers the stacked and fence-adjacent forms in the examples. A
   multi-line directive opens with `(key:` alone on its line and ends on a line
   ending in `)`; its content is a one-key YAML map. A parenthesis that isn't
   shaped like that (capitals, spaces or no colon in the key) stays narration,
   and an unknown lowercase key is dropped with a warning.
2. **Separator recognition.** Outside fenced code, any line of 3 or more `-`
   ends the scene, with or without blank lines around it. Never read it as a
   CommonMark setext heading underline.
3. **Empty scenes** (for example from a trailing `---`) are dropped.
4. **An image with no audio and no `duration`.** 1 s, the documented script
   default for slides. It is fixed, and several such images share it.
5. **`duration` together with audio.** The scene lasts max(`duration`, audio),
   with no warning when `duration` is the shorter.
6. **Several videos, or videos plus images, in one scene.** *Implemented
   (narrate #4).* The visuals play in order as one sequence:
   - Clips count at their own length, and images at 1 s each.
   - The first clip's `sync` mode applies to the whole sequence.
   - `freeze` (and `loop-audio`): spare narration time goes to the images,
     or holds the last clip's final frame if there are none.
   - `match`: scales every item in proportion.
   - `trim`: cuts the sequence in order.
   - `loop` / `trim-or-loop`: repeat the whole sequence.
   - Clip soundtracks play where their clip does.
7. **Several slides in one scene.** *Implemented (narrate #3).* The slides
   share the scene's time equally, independently of the visuals.
   - With as many slides as images (and no clips), slide *i* shows over
     image *i*.
   - An image is split where its slide changes.
   - Over clips, and over a looping sequence, each slide is an overlay shown
     during its share.
8. **Duration-only `transition: N`.** Use the header's transition type if one
   is set, otherwise `crossfade`, for N seconds. *Implemented (narrate #1).*
9. **Transition timing.** *Answered by Narakeet's own render (§17).*
   - Total length equals the sum of the scenes.
   - A transition starts at the cut and plays over the start of the incoming
     scene, while the outgoing scene holds its last frame. Measured on
     `transition-types`: each 0.5 s wipe runs from the cut to cut + 0.5 s.

   *Implemented (narrate #1, placement corrected in #35):* clamped to the
   incoming scene's length; the names map onto ffmpeg `xfade` transitions.
10. **Poster default.** 50% of the duration (explicitly stated, and the later
    of the two statements).
11. **`voice-pitch` numbers.** *Implemented (narrate #6):* N is read as
    N/100 octaves.
    - 100 is an octave up and −100 an octave down.
    - ±10 is subtle, and Narakeet's "squeaky" example, 130, is very high.
    - Presets: `x-low` −4, `low` −2, `high` +2 and `x-high` +4 semitones.
    - The shift is applied after synthesis (rubberband), keeping duration.

    (Percent would make −150 meaningless.)
12. **Subtitle cue timing within a paragraph.** Split proportionally to
    character count (this reads as "equal" per character).
13. **Timing of several block quotes in one scene.** Split the scene duration
    proportionally to each quote's length.
14. **Block quotes with `subtitles: none` or no header.** Burn them in with
    the `overlay` style. They are explicit content, so `none` only suppresses
    **automatic** cues.
15. **Subtitle `outline` and `background` defaults.** The outline is black
    (the reference's "white" contradicts its own description). There is no box
    unless `background` is set, which then replaces the outline;
    `overlay-background` uses semi-transparent black.
16. **`fragment` scope.** Like every `narration-mode`, `fragment` persists
    across scenes until another `narration-mode` changes it; the examples
    repeat it in every scene, which does no harm. *`merge` implemented
    (narrate #10)*, ended by the next scene that sets any other mode:
    - The narration of the run of scenes from the one that sets `merge` to the
      one that sets `normal` is synthesised as one track.
    - The scenes share its time equally, in whole frames, and each keeps its
      own visuals, slides, quotes and callouts within its share.
17. **Span combining a style and a language** (`[x]{ipa de}`). Not
    supported: the span is read as plain text, with a note.
18. **Audio file in image syntax** (`![](a.mp3)`). Treat it as `(audio: a.mp3)`.
19. **Position on videos.** Accept the image position tokens for `cover` crops.
20. **Missing positions** (`top-right`, `bottom-left`, `bottom-right`).
    Not accepted, as in Narakeet: in alt text or an `(image:)` map they are
    dropped with a warning, and `(image-position: top-right)` is an error.
21. **`1080p-portait` spelling.** Accept both spellings.
22. **Built-in background track names.** A project file with that name wins;
    otherwise a recording of that name in `$NARRATE_MUSIC_DIR`, otherwise
    narrate's own synthesised stand-in, rendered once into the tools cache.
23. **Unknown voice names.** They never fail. `voices.yaml` pins apply first;
    otherwise each engine picks a voice of the same language and gender (with
    an accent fallback), or its default voice, and notes the substitution.
24. **SSML.** *Implemented (narrate #9):* narrate interprets a subset
    itself, the same on every engine: break, prosody, emphasis, say-as
    (spelling), phoneme, lang, sub, p and s. Unknown tags keep their text and
    are noted; malformed XML is read as plain text.
25. **Callout mask colour.** Opaque black. `alpha` doesn't apply to masks.

---

## 17. Observations from Narakeet's renders

Every project in `github.com/narakeet/examples` includes `result.mp4`, the video
Narakeet rendered from that script. Measured with ffprobe and ffmpeg
scene-change detection (2026-10-08):

| Example | Narakeet | What it shows |
| --- | --- | --- |
| `slides` | 14.04 s | Text slide without audio = 1 s; `duration: 2` = 2 s exactly; a video with no narration plays in full (5 s). This matches §4.2. |
| `transition-types` | 25.08 s | 25 scenes of `duration: 1` with 24 transitions of 0.5 s. Transitions do **not** shorten the video (gap 9). Frame by frame, each wipe runs from the cut to cut + 0.5 s (narrate #35). |
| `video-sizing`, `video-volume` | 16.03 s, 23.52 s | Clips with `cover`/`contain`/`fit`, segments, `volume` and `mute`: lengths match the rules within 0.05 s and frames match. |
| `slide-css-theming` | 8.97 s | Themes, fonts and the custom backdrop match narrate's frames (narrate #20, #35). Narakeet's default backdrop is `backdrop-filter: brightness(0.45)` (measured), which a theme's `backdrop-filter` replaces. The render runs 0.47 s longer than the rules, around its slides. |
| `transitions` | 8.05 s | Departs from the rules: the clip segments `1 - 2` and `4 - 5` play for about 1.4 s and 2 s, and the header's 2 s wipe isn't visible. The same segment-range fault as `video-segments`. |
| `image-sizing` | 12.60 s | Scene cuts every 2.52 s for scenes of an image, a text slide and `(pause: 2)`. |
| `image-panzoom` | 9.96 s | The first scene, an image and `(pause: 1)` with no slide, cuts at exactly 1.0 s: no padding. |
| `video-segments` | 11.71 s | The first three scenes match the rules: the full 5 s clip under short narration (`freeze`), then two 2.0 s stills (cuts at 4.97, 6.97 and 8.97 s). The last scene, `![00:02-00:04](stopwatch.mp4)`, runs 2.76 s instead of 2.0 s (narrate #18). Its frames do start at source 2.00 s, but play past 4.0 s (source 4.60 s at 11.6 s) until the render ends. The clip has a single keyframe, so this isn't keyframe snapping: Narakeet ignored the segment's end, against its own documentation. narrate follows the documented range. |

**Automated checks (narrate #35).** `tests/test_conformance.py` builds every
example without narration and compares it with Narakeet's render:
- Lengths are compared for `slides`, `transition-types`, `video-sizing` and
  `video-volume`.
- Frames are compared once each scene has settled, for all of those plus
  `image-sizing` (at Narakeet's own pace) and `slide-css-theming`.
- The differences above are pinned, so a change on either side shows up.

**Pauses (narrate #19).** The extra 0.5 s in `image-sizing` is not a pause
rule: an unpadded `(pause: 1)` scene in `image-panzoom` shows that. The extra
time appears only in scenes that also contain a text slide. Narakeet's renders
date from different years, so this may be version drift rather than a rule.
narrate keeps pauses exact and offers no "Narakeet timing" mode, since there's
no consistent behaviour to reproduce.

---

## 18. narrate extensions

Features narrate adds to the format. Narakeet doesn't have them, so scripts
that use them build only with narrate.

### 18.1 Render blocks

A fenced code block whose info string starts with `render:` is not a slide. A
renderer turns it into a picture, which is placed as a media reference (§5)
would be.

```
render-block := fence "render:" NAME [ token ]* NL [ frontmatter ] body fence
frontmatter  := "---" NL yaml-mapping NL "---" NL      ; at the very top of the body
```

- **`NAME`** picks the renderer, case-insensitively. An unknown name is an
  error that lists the known renderers.
- **Tokens** after the name are alt-text tokens (§5.2): size, animated size,
  position, sync, segment and `mute`.
- **Frontmatter** is parsed as typed YAML, unlike the header, because
  renderer settings may pass through to other tools.
  - The keys `size`, `position`, `sync`, `segment`, `volume` and `zoom` place the
    output, as in an `(image:)` or `(video:)` map, and win over tokens.
  - Every other key belongs to the renderer, with its case kept. A renderer
    rejects keys it doesn't take.
- **Body:** the rest of the block, what the renderer draws.
- **Placement:** the output joins the scene's visuals in script order, sharing
  the scene's time and taking callouts, slides and transitions as an image
  would. Audio builds ignore it.
- **Rendering:** each block is drawn at the frame size with the theme and canvas
  in effect at its position in the scene. The output is cached by a hash of the
  renderer, its settings, the body, the frame size, the theme and the canvas.
- **Stored renderers:** a renderer whose output can't be reproduced, such as
  `web`, keeps it in the project instead of the cache.
  - **Where:** `.narrate/generated/<renderer>/<hash>.png` beside the script,
    with a JSON sidecar recording the settings and when it was made.
  - **Reuse:** later builds reuse the stored file until a build asks to
    regenerate.
  - **Key:** a stored renderer's hash leaves out what can't change its output
    (for `web`, the theme and canvas).

| Renderer | Draws | Settings |
| --- | --- | --- |
| `mermaid` | the body as a Mermaid diagram (mermaid.js 12, pinned), fitted to 90% of the frame and captured at twice its size; Mermaid's dark theme on a dark background | `background` (default: the canvas, else the theme's slide background), `scale` (of the fitted size, default 1); Mermaid's `title`, `displayMode` and `config` pass through |
| `placeholder` | a card labelled with the body (or "Placeholder") and the frame size | `background`, `color` |
| `web` (narrate #50) | a live web page, captured at build time; stored, not cached | `url` (or a body that is just a URL), `viewport`, `scale` (default 2), `color-scheme`, `hide`, `css`, `scroll-to`, `selector`, `wait`, `auth` (an environment variable's name) |

`narrate check` also runs each renderer's deeper validation, such as Mermaid's
parser. Planned renderers: AI-generated pictures and clips (narrate #41, #42).

### 18.2 HTML scenes

An `.html` or `.htm` file is a media reference (§5) of its own kind: an
animated page (narrate #44).

```
![<tokens>](scene.html)
(html: {file: scene.html, viewport: WxH, size: …, position: …})
```

- **Placement:** like an image. The page joins the scene's visuals in script
  order and takes callouts, slides, subtitles and transitions as a clip does.
  Size and position tokens apply when the viewport's shape differs from the
  frame's; animated sizes are ignored.
- **`viewport`:** the size the page is laid out at, default the frame size. It is
  rendered at the pixel density that fits it to the frame, not enlarged
  afterwards.
- **Timing:** a page lasts as long as its scene, and is timed like an image
  (§4.2). A scene with no audio and no `duration` lasts until the page's last
  finite animation ends; a static page lasts 1 s.
- **Capture:** frame by frame at the output frame rate.
  - The page's clock (timers, `requestAnimationFrame`, `Date`) is paused before
    it loads and advanced one frame at a time.
  - Every animation in `document.getAnimations()` is paused and seeked to the
    frame's time, counted from the frame where it first appears. SVG
    animations are seeked with `setCurrentTime`.
  - A page without scripts whose finite animations have all ended, with no
    infinite ones, is settled: its last frame is reused.
- **Not captured:** sound, and `<video>` or `<audio>` elements in the page.
- **Cues** (narrate #45): before the page's scripts run, its root element gets
  CSS custom properties, and `window.narrate` gets the same values in seconds.
  - `--narrate-duration`: how long the page is on screen.
  - `--cue-N`: when the scene's Nth narration block (a paragraph or a
    recording) starts, after any pause before its first words.
  - `--cue-NAME`: when an SSML `<mark name="NAME"/>` is reached. A mark splits
    the run there, and names match `[A-Za-z_][A-Za-z0-9_-]*`.
  - Times count from the page's start, and may be negative.
  - Pages in merged scenes get no cues.

### 18.3 Dips and fades (narrate #46)

- **Transitions:** `fade-black` and `fade-white` are extra transition types
  (§10). Over the transition's time, the outgoing frame fades to the colour
  during the first half, then the incoming scene fades in from it during the
  second. Placement and length follow §10 and §16.9: the dip starts at the cut,
  and the video's length is unchanged.
- **Header `fade-in: N` and `fade-out: N`** (seconds, default 0): the video
  fades from black at the start and to black at the end, after burned-in
  subtitles. The mixed sound fades linearly over the same time, in audio
  builds as well. The length is unchanged.

### 18.4 Loudness (narrate #48)

Header `loudness`: an integrated loudness in LUFS (−70 to −5), or `web` (−16)
or `broadcast` (−23).
- **Measured:** the finished mix (narration, recordings, clip sound and
  music), in two passes of ffmpeg's `loudnorm`.
- **Applied** in linear mode where the true-peak ceiling of −1.5 dBTP allows,
  otherwise dynamically.
- **Applied before** the header fades, in video and audio builds.
- **Silence**, and audio too short to measure, are left unchanged.
- **Absent:** the mix is only peak-limited, as before.

### 18.5 Zoom amount (narrate #49)

- **Per picture:** `zoom` in an `(image:)` map, or in a render block's
  frontmatter, sets how far an animated size moves. It must be above 1.
  - For `zoom`, `zoomout`, `panzoom` and `panzoomout`, it is the zoom reached
    over the scene (default 1.25).
  - For `pan`, it is the fixed zoom the pan travels at (default 1.15).
- **Default:** the header's `image-zoom` sets it for every picture.
- **Precedence:** the picture's own value wins over the header's.
