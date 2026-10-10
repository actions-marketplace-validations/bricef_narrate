# Writing scripts

A narrate script is a Markdown file that describes a video scene by scene:
what is on screen, what is said, and what you hear. narrate reads the format
of Narakeet's "Markdown to Video" builder, so Narakeet scripts work unchanged.
This page shows how to do each common task. The
[format specification](spec/narakeet-markdown.md) has every rule and default.

The examples use placeholder file names (`photo.jpg`, `forest.jpg`,
`clip.mp4`, `talk.mp3`, `music.mp3`, `theme.css`, `font.ttf`). Put files with
those names next to the script, or change the names. Build an example with
`narrate build script.md`, and add `--tts silent` for a quick preview without
speech. [Building videos](building.md) covers the commands.

- [Start a script](#start-a-script)
- [Narrate text and add pauses](#narrate-text-and-add-pauses)
- [Choose a voice and change how it sounds](#choose-a-voice-and-change-how-it-sounds)
- [Control pronunciation](#control-pronunciation)
- [Use recorded audio](#use-recorded-audio)
- [Show pictures](#show-pictures)
- [Play video clips](#play-video-clips)
- [Generate pictures from code blocks](#generate-pictures-from-code-blocks)
- [Draw diagrams](#draw-diagrams)
- [Capture web pages](#capture-web-pages)
- [Show animated HTML scenes](#show-animated-html-scenes)
- [Show text slides](#show-text-slides)
- [Style slides with a theme](#style-slides-with-a-theme)
- [Add subtitles](#add-subtitles)
- [Add background music](#add-background-music)
- [Set the overall loudness](#set-the-overall-loudness)
- [Add transitions](#add-transitions)
- [Highlight part of the frame](#highlight-part-of-the-frame)
- [Set the size, poster and file size](#set-the-size-poster-and-file-size)
- [Run narration across scenes](#run-narration-across-scenes)
- [Package a project as a ZIP](#package-a-project-as-a-zip)
- [Differences from Narakeet](#differences-from-narakeet)

## Start a script

````markdown
---
size: 1080p
voice: Arthur
---

<!-- Comments like this one are ignored. -->

![](photo.jpg)

This paragraph is read aloud while the photo is on screen. The scene lasts as
long as its narration.

---

![](forest.jpg)

A line of three dashes starts the next scene.
````

- **Header:** the optional block between the first two `---` lines sets
  defaults for the whole video. It must start on the first line. It is YAML, so
  quote colours that start with `#` (`canvas: "#202020"`).
- **Scenes** are separated by a line of three or more dashes.
- **Blocks:** inside a scene, each paragraph is one of these:
  - an image or clip (`![…](file)`);
  - a stage direction in parentheses (`(pause: 1)`);
  - a text slide (a fenced code block);
  - a block quote (`> text`), shown as a subtitle;
  - narration (anything else).
- **Stage directions** sit on lines of their own, as `(key: value)`. A
  multi-line one opens with `(key:` and ends with `)`. Narakeet also needs a
  blank line around each one, so add them to keep scripts portable.
- **Files** are found relative to the script, so keep the script and its media
  in one folder. Scripts end in `.md`, `.mkd` or `.txt`.
- **Formats:**
  - **Pictures:** JPG, PNG and GIF.
  - **Clips:** MP4, MOV, M4V, WEBM, WMV, AVI and MPEG.
  - **Recordings:** WAV, MP3, WMA, AAC and M4A.

  Other files in image syntax (`![](logo.webp)`) aren't shown: the line is
  read aloud, with a warning.

`narrate check script.md` finds missing pictures, clips and recordings, and
lines it doesn't understand, in a second. It doesn't catch bad values (such
as `voice-speed: 3`) or missing theme, music and font files. A preview build,
`narrate build script.md --tts silent`, finds those in seconds.

## Narrate text and add pauses

````markdown
![](photo.jpg)

Each paragraph is read aloud, with a short pause after it.

(pause: 2)

Two seconds later the narration goes on… after a half-second pause.

---

![](clip.mp4)

The clip starts playing.

(pause-until: 00:04)

This sentence starts four seconds into the scene, whatever came before it.

---

![](forest.jpg)

(duration: 3)
````

- `(pause: N)` adds N seconds of silence (decimals are fine).
- An ellipsis (`…` or `...`) adds about half a second.
- `(pause-until: T)` waits until T seconds (or `MM:SS`) from the start of the
  scene. It does nothing if that moment has passed.
- A scene with no narration lasts as long as `(duration: N)` says. Without it,
  a picture or slide stays up for 1 second, and a clip plays to its end.
- To hold the final picture after the last words, end the scene with a
  `(pause: N)`.

## Choose a voice and change how it sounds

````markdown
---
voice: Arthur
voice-speed: 1.1
---

![](photo.jpg)

Arthur reads this, a little faster than normal.

(voice: Amy)

(voice-pitch: high)

Amy answers, with her voice raised a little.

(voice: Arthur)

(voice-volume: loud)

**Arthur closes, louder and with strong emphasis.**
````

- **`voice`** in the header sets the voice for the whole video. As a direction
  it switches voice for the paragraphs that follow, until the end of the scene.
  Each new scene starts again from the header's settings.
- **Voice names:** use Narakeet names (`Arthur`, `Amy`), Kokoro IDs
  (`bf_emma`) or ElevenLabs voices (`George`). narrate maps each name to a
  voice of the engine you build with. `Name/ll-RR` (`Amy/de-DE`) pins the
  language. [Pick voices](building.md#pick-voices) explains the mapping and how
  to pin your own choices.
- **`voice-speed`:** `slow` (0.8×), `normal` or `fast` (1.2×), or a multiplier
  from 0.3 to 2.
- **`voice-pitch`:** `x-low`, `low`, `normal`, `high` or `x-high` (−4, −2, 0,
  +2 and +4 semitones), or a number from −150 to 150 in hundredths of an
  octave (100 is an octave up).
- **`voice-volume`:** `x-soft`, `soft`, `standard`, `loud` or `x-loud` (steps of
  4.5 dB), or `normalized`, which evens out the loudness of different voices.
- **Emphasis:** inline markup, or `(voice-emphasis: …)` for the paragraphs that
  follow. Emphasise whole sentences; mid-sentence emphasis adds a short join.

  | Markup | Level | Speed | Pitch | Volume |
  | --- | --- | --- | --- | --- |
  | `*x*` or `_x_` | `moderate` | 0.96× | +0.75 semitones | +1.5 dB |
  | `**x**` or `__x__` | `strong` | 0.92× | +1.5 semitones | +3 dB |
  | `~~x~~` | `reduced` | 1.06× | −1 semitone | −4 dB |

- **Resetting:** `normal` sets speed, pitch or volume back to the default (not
  to the header's value), and `none` turns emphasis off. To go back to an
  earlier voice, name it again.

## Control pronunciation

````markdown
![](photo.jpg)

Our product is called `NRT`, and it is pronounced [ˈnær.eɪt]{ipa}.

The word [Schadenfreude]{de} keeps its German pronunciation.

<speak>
  Say it <prosody rate="slow">slowly</prosody>.
  <break time="1s"/>
  <say-as interpret-as="characters">SSML</say-as> works with every engine.
</speak>
````

- **Spell out** letters and symbols with backticks (`` `NRT` ``) or
  `[NRT]{literal}`. Letter names are read in English, Spanish, French, German,
  Italian or Portuguese, following the narration language.
- **Phonetic spelling:** `[…]{ipa}`, `[…]{x-sampa}`, `[Běi jīng]{pinyin}`
  (tone marks or numbers) and `[hoeng1 gong2]{jyutping}`.
- **Another language:** a `[word]{de}` span reads one phrase in German.
  `(narration-language: fr)` switches the rest of the scene, and `default`
  switches back. The voice keeps its own accent.
- **SSML:** a paragraph wrapped in `<speak>…</speak>`. narrate interprets
  these tags itself, so they work the same with every engine:
  - `<break>` (`time` or `strength`)
  - `<prosody>` (`rate`, `pitch`, `volume`)
  - `<emphasis>`
  - `<say-as interpret-as="characters">`
  - `<phoneme>`, `<lang>` and `<sub alias>`
  - `<p>` and `<s>`
  - `<mark name>`, a timing point for [HTML scenes](#time-a-page-to-the-narration)

  Other tags are read as plain text, with a note.
- **Russian stress:** `^` before a vowel (`гвозд^ики`) marks the stressed
  syllable. ElevenLabs honours it; Kokoro has no Russian voice.

## Use recorded audio

````markdown
![](photo.jpg)

(audio: talk.mp3)

The generated voice carries on after the recording.
````

- `(audio: file)` plays a recording as part of the narration. Recordings and
  generated speech play one after the other, never at the same time.
- The scene lasts as long as all its narration together.
- With subtitles on, recordings are transcribed for their captions (see
  [Add subtitles](#add-subtitles)).

## Show pictures

````markdown
---
asset-resize: contain
canvas: "#202020"
---

![](photo.jpg)

Letterboxed on a dark grey background.

---

![cover top](photo.jpg)

Cropped to fill the frame, keeping the top of the picture.

---

![panzoom left](photo.jpg)

![zoom](forest.jpg)

Two pictures share this scene. The first drifts left while zooming in, then
the second zooms in.
````

- **Fit:** `cover` fills the frame and crops (the default), `contain`
  letterboxes with the `canvas` colour, and `fit` stretches.
  `asset-resize` in the header sets the default for every picture and clip.
- **Position** (with `cover`): `center`, `top-left`, `left`, `right`, `top` or
  `bottom` chooses which part survives the crop.
- **Movement:** `zoom`, `zoomout`, `pan`, `panzoom` and `panzoomout` animate a
  picture. Add a position to set the direction of a pan. Use pictures well
  above the video size (1080p or more for a 720p video) for smooth motion.
- **How far it moves** (narrate only):
  - **Defaults:** zooms reach 1.25× over the scene, and pans travel at 1.15×.
  - **One picture:** `(image: {file: photo.jpg, size: zoom, zoom: 1.1})`
    zooms to 1.1× instead.
  - **Every picture:** `image-zoom: 1.1` in the header.
  - Gentler amounts suit short scenes.
- **Any point, any path** (narrate only):
  - **Focal point:** `(image: {file: photo.jpg, position: 70% 25%})` keeps
    that point, 70% across and 25% down, as near the middle as the crop
    allows. Zooms and pans head for it too.
  - **Windows:** `from` and `to` give the first and last frames outright, each
    as its centre and a zoom (1 is the plain crop, 2 shows half as much):

    ```
    (image:
      file: photo.jpg
      from: 50% 50%
      to: 72% 30% 2.5)
    ```

    A window past the picture's edge is moved in, with a note. The studio's
    inspector draws both on the whole picture, to drag and resize.
- **Several pictures** in one scene play in turn and share its time equally.
- **Directive form:** `(image: photo.jpg)`, or a map such as
  `(image: {file: photo.jpg, size: panzoom, position: left})`.
  `(image-size: …)` and `(image-position: …)` set defaults for the pictures
  that follow in the scene.
- Animated GIFs loop for the length of the scene, or play once with `freeze`.

## Play video clips

````markdown
![00:01-00:03 match](clip.mp4)

Only seconds one to three of the clip play, stretched to fit this narration.

---

![end](clip.mp4)

This scene shows the clip's last frame as a still.

---

(video:
  file: clip.mp4
  sync: loop
  volume: 0.3)

The clip loops under this narration, with its own sound at 30 percent.
````

- **Part of a clip:** a range `start-end` in the alt text, with no spaces
  (`00:01-00:03`, `10-14.5`). The words `start` and `end` stand for the clip's
  first and last moments.
- **Still frame:** a single time (`00:05`), `start` or `end`.
- **Sync**, when the clip and the narration differ in length:

  | Mode | What happens | Scene length |
  | --- | --- | --- |
  | `freeze` (default) | the clip plays once; its last frame holds if the narration is longer | the longer of the two |
  | `match` | the clip is sped up or slowed down to fit the narration | the narration |
  | `trim` | stops when either one ends | the shorter of the two |
  | `loop` | the clip repeats to cover the narration | the longer of the two |
  | `trim-or-loop` | loops if shorter, is cut if longer | the narration |
  | `loop-audio` | the narration repeats to cover the clip | the longer of the two |

- **Clip sound:** `mute`, or a `volume` multiplier in the directive form
  (`0.5`, `2`). The clip's sound plays under the narration.
- Fit and position work as for pictures.

## Generate pictures from code blocks

````markdown
```render:placeholder
Product shot goes here
```

The finished video will show the product here.

---

```render:placeholder cover
---
background: navy
color: white
---
Chart: sales by region
```

(duration: 2)
````

- **`render:NAME`:** a code block whose first word is `render:` and a
  renderer's name is turned into a picture. It is then shown exactly like
  `![…](file)`: same timing, fit, pan and zoom, callouts and slides on top. It
  is not shown as code.
- **Options:** words after the name are the picture options from alt text
  (`cover top`, `panzoom left`).
- **Settings:** an optional block between `---` lines at the top holds the
  renderer's settings. `size`, `position` and `zoom` there work as in
  `(image: …)`.
- **Renderers:**
  - `render:mermaid` draws a Mermaid diagram (see [Draw diagrams](#draw-diagrams)).
  - `render:web` captures a web page (see [Capture web pages](#capture-web-pages)).
  - `render:placeholder` draws a card labelled with the block's text and the
    video's size, standing in for a picture still to come. `background` and
    `color` set its colours.
- Pictures are drawn at the video's size and cached, so an unchanged block
  isn't drawn again.
- `narrate check` reports unknown renderers and settings.
- These blocks are narrate's own; Narakeet would show them as code.

## Draw diagrams

````markdown
```render:mermaid
flowchart LR
  Script --> Parser --> Builder --> Video
```

The parser reads the script, and the builder renders each scene.

---

```render:mermaid
---
title: How a build works
config:
  theme: forest
background: "#f4f1ea"
scale: 0.8
---
sequenceDiagram
  participant You
  participant narrate
  You->>narrate: narrate build script.md
  narrate-->>You: script.mp4
```

(pause: 1)
````

- **Any Mermaid diagram:** flowcharts, sequence, class, state and entity
  diagrams, Gantt charts, pie charts, mind maps, timelines and more.
  [Mermaid's documentation](https://mermaid.js.org/intro/) covers the syntax.
  The diagram is drawn sharply at the video's size, then shown like a picture.
- **Size:** it fills up to 90% of the frame, centred. `scale: 0.8` makes it
  smaller.
- **Background:** the scene's canvas, otherwise the theme's (white, or black
  for `light`). `background` sets another colour. On a dark background,
  Mermaid's dark theme is used.
- **Mermaid's own settings** go in the same block: `title`, `displayMode` and
  `config` (such as `theme`, `look: handDrawn` or `themeVariables`) pass to
  Mermaid unchanged.
- **Movement:** ```` ```render:mermaid zoom ```` zooms slowly into the
  diagram, and the other pan and zoom options work too.
- **Errors:** `narrate check` runs Mermaid's parser and reports syntax errors
  with the block's line.
- The first diagram downloads Mermaid itself (about 5 MB); the Docker image
  already has it.

## Capture web pages

````md
```render:web zoom
---
url: https://github.com/bricef/narrate/issues/43
color-scheme: dark
hide: header.AppHeader, .js-notification-shelf
scroll-to: Done when
---
```

The issue that tracks all of this work.

---

```render:web
https://example.com
```

(duration: 2)
````

- **What it does:** a `render:web` block captures a web page when the video
  is built, then shows it like a picture, so screenshots of live pages come
  from the script rather than a separate step. A block holding just a URL is
  enough.
- **Settings:**

  | Setting | Does |
  | --- | --- |
  | `url` | the page, http or https (or put the URL in the block) |
  | `viewport` | the window size, default the video's size |
  | `scale` | pixels per CSS pixel, default 2, which leaves room to zoom |
  | `color-scheme` | `light` (default), `dark` or `no-preference`, for sites that follow it |
  | `hide` | CSS selectors to hide, such as banners and headers |
  | `css` | extra CSS to add to the page |
  | `scroll-to` | text to scroll into view first |
  | `selector` | capture only the element it matches |
  | `wait` | `load` (default), `networkidle`, or milliseconds to wait after loading |
  | `auth` | the name of an environment variable holding `user:password`, for Basic auth |

- **Kept in the project:** pages change, so each capture is saved beside the
  script, in `.narrate/generated/web/`, with a note of the URL and when it was
  taken.
  - Later builds reuse the capture, offline too.
  - `narrate build --regenerate` takes it again.
  - Commit the folder to keep the video stable.
  - A ZIP project is unpacked afresh each time, so its pages are captured on
    every build.
- **Privacy:** the page opens with no cookies or saved logins. Credentials come
  only from the environment variable that `auth` names; the secret never goes
  in the script or the saved note.
- `narrate check` validates the settings without fetching anything.

## Show animated HTML scenes

````markdown
![](scene.html)

The title appears first.

Then its subtitle, as this paragraph begins.

---

(html: {file: scene.html, viewport: 1280x720, size: contain})

(duration: 4)
````

`scene.html`, next to the script:

```html
<!doctype html>
<style>
  html, body { margin: 0; width: 100%; height: 100%; background: #0d1117; color: #e6edf3;
               font: 48px sans-serif; display: grid; place-content: center; text-align: center; }
  .up { opacity: 0; transform: translateY(14px); animation: up .5s ease-out forwards; }
  @keyframes up { to { opacity: 1; transform: none; } }
</style>
<h1 class="up" style="animation-delay: .3s">factor-q</h1>
<p class="up" style="animation-delay: var(--cue-2, 1.2s)">Agents that run continuously.</p>
```

- **Any web page** in the project folder can be a scene, with its CSS, fonts,
  pictures, SVG and JavaScript.
- **Animations play on the video's clock:**
  - CSS animations and transitions;
  - SVG animations;
  - JavaScript timers, `requestAnimationFrame` and `Date`.

  narrate captures the page frame by frame rather than recording it, so every
  build gives the same video however fast the computer is.
- **Timing:** the page starts with its scene and lasts as long as the scene.
  With no narration and no `(duration:)`, the scene lasts until the page's last
  animation ends (one that repeats forever doesn't count).
- **Size:** the page is laid out at the video's size, unless `viewport` gives
  the size it was designed for. It is then drawn sharply at the video's size,
  with `size` and `position` as for pictures when the shapes differ.
- **On top:** callouts, slides, subtitles and transitions work over pages.
- **Speed:** capture runs at about twice real time. A page without scripts
  stops being captured once its animations have finished.
- **Limits:** a page's own sound, and `<video>` or `<audio>` inside it, aren't
  captured or kept in time. Keep its files local; anything fetched from the
  network slows capture and ties the build to the network.
- HTML scenes are narrate's own; Narakeet would read the line as narration.

### Time a page to the narration

The example's subtitle appears when the second paragraph starts, wherever
that falls, rather than after a fixed delay. narrate gives each page the
scene's timing as CSS custom properties:

| Property | Holds |
| --- | --- |
| `--cue-1`, `--cue-2`, … | when the scene's first, second, … narration block (a paragraph or a recording) starts |
| `--cue-NAME` | when the voice reaches `<mark name="NAME"/>` |
| `--narrate-duration` | how long the page is on screen |

````markdown
![](scene.html)

<speak>Five hundred and thirty-one pull requests merged. <mark name="fleet"/>A hundred and fifty-two by the fleet.</speak>
````

- **Delays:** use them as animation delays: `animation-delay: var(--cue-fleet)`.
  A fallback value keeps the page working on its own:
  `var(--cue-2, 1.2s)`.
- **Leaving:** `calc(var(--narrate-duration) - .5s)` starts an exit animation
  half a second before the page goes.
- **Scripts** get the same numbers, in seconds, before they run:
  `window.narrate.duration` and `window.narrate.cues["2"]`.
- **Marks:** a mark splits the speech at that point, so its time is exact.
  Splitting mid-sentence can add a short join, as emphasis does. Marks work
  in `<speak>` paragraphs; use names made of letters, digits, `-` and `_`,
  starting with a letter.
- **Timing:** times count from the page's start, which matters when it follows
  another picture in the scene.
- **Not here:** pages in merged scenes (`narration-mode: merge`) get no cues.

## Show text slides

````markdown
```
A plain slide
```

(duration: 2)

---

![](photo.jpg)

```md
# A heading
* bullet points
  * nested ones too
```

The slide sits over the picture, on a darkened backdrop.

---

(font-size: 36)

```python
def hello():
    print("Code is syntax highlighted")
```

(duration: 3)
````

- A fenced code block is shown on screen, never read aloud.
- The word after the opening fence sets what it shows: nothing (or `txt`) for
  plain text, `md` for formatted Markdown, any language name (`python`, `css`,
  `yaml`, …) for highlighted code.
- `(font-size: N)` sets the scene's slide text size in pixels (default 50).
  Text that would overflow the frame is shrunk to fit.
- Over a picture, the `default` theme darkens the picture behind the slide.
  Over a clip there is no backdrop.
- Several slides in one scene take turns, sharing its time.

## Style slides with a theme

````markdown
---
theme: theme.css
---

```md
# Styled by theme.css
```

(duration: 2)

---

(theme: light)

![](photo.jpg)

```md
# The light theme: no backdrop
```

(duration: 2)
````

- `default`: black text on white, or white text on a darkened backdrop over a
  picture.
- `light`: white text on black, and no backdrop over a picture.
- A `.css` file next to the script styles slides like a web page:

  ```css
  @font-face { font-family: "Brand"; src: url("font.ttf"); }
  body { background: navy; color: white; font-family: "Brand", sans-serif; }
  h1 { color: gold; }
  .backdrop { backdrop-filter: blur(20px); }
  ```

  - `body` styles the slide; its background shows only when the slide isn't
    over a picture or clip.
  - `.backdrop` styles the layer between a picture and the slide.
  - `@font-face` loads a font file from the project folder.
- `theme` works in the header or as a direction placed before the slide.

narrate's default look follows measurements of Narakeet's renders:
- **Text:** a 50 px base size, with plain slides in bold at twice that.
- **Fonts:** headings in sans-serif, body text in serif, and code in a
  Courier-style font.

Its rules carry no CSS specificity, so any rule in your theme wins.

## Add subtitles

````markdown
---
subtitles:
  mode: overlay
  break: 60
  color: yellow
  background: "#00000080"
  position: top
---

![](photo.jpg)

Each paragraph becomes a subtitle, split into cues of at most sixty
characters, timed to the speech.

---

![](forest.jpg)

> A block quote is shown instead of this scene's narration.

This narration plays, but the quote above is what the viewer reads.
````

- **Modes:**

  | Mode | Result |
  | --- | --- |
  | `none` | no subtitles (the default) |
  | `external` | `.srt` and `.vtt` files next to the video |
  | `embed` | a subtitle track inside the MP4, plus the files |
  | `overlay` | burned in: white text with a black outline |
  | `overlay-background` | burned in: white text on a dark box |
  | `tiktok` | burned in: large text, a few words at a time, mid-frame |

- **Style:** the map form shown above takes `mode: overlay` or `mode: embed`,
  plus any of:
  - `break`: the most characters per cue (default 135).
  - `scale` or `size`: the text size, relative or in pixels.
  - `color`, and either `outline` or `background`: colour names or quoted
    `"#RRGGBB"` / `"#RRGGBBAA"`.
  - `font`: a `.ttf` file in the project.
  - `position`: `top`, `middle` or `bottom`.

  For a box behind the text, use `mode: overlay` with `background`.
- **Block quotes** (`> text`) replace a scene's automatic subtitles.
  Consecutive `>` lines make one cue; separate quotes are shown in turn. A
  lone `>` hides subtitles for that scene. Quotes show even when no mode is
  set.
- **Recorded audio** (`(audio: …)`) is transcribed on the computer with
  faster-whisper when subtitles are on and the scene has no block quote. Its
  model, about 460 MB, downloads the first time.
- Write one sentence per paragraph for subtitles that change with the speech.

## Add background music

````markdown
---
background: music.mp3 0.5 fade-in fade-out
---

![](photo.jpg)

Music plays under the whole video, at half volume, fading in and out.
````

- `background` takes a file from the project, or a built-in track:
  `ukulele-1`, `ukulele-2`, `uplifting-1`, `uplifting-2` or `corporate-1`.
- Then, in any order: a volume multiplier (`2` doubles it), `fade-in` (over
  the first scene) and `fade-out` (over the last).
- The music loops for the length of the video and plays under narration and
  clip sound.
- The built-in tracks are narrate's own synthesised loops, mixed to sit under
  the narration.
- **Your own recordings under those names:** name each file after its track
  (`ukulele-1.mp3`; WAV, MP3, M4A, AAC, OGG or FLAC), put them in one folder,
  and point `$NARRATE_MUSIC_DIR` at it.

## Set the overall loudness

````markdown
---
loudness: web
---

![](photo.jpg)

Every video from this script comes out equally loud, whichever voice reads it.
````

- **`loudness`** (narrate only) brings the finished mix to an integrated
  loudness:
  - `web` (−16 LUFS), the usual level for streaming sites and podcasts;
  - `broadcast` (−23 LUFS, EBU R 128);
  - or a number in LUFS, such as `-14`.
- The narration, recordings, clip sound and music are measured together and
  adjusted as one, with peaks kept below −1.5 dB.
- Without it, the mix keeps each voice's own level, which varies by engine and
  voice.
- `voice-volume: normalized` is different: it evens out the voices within a
  video, not the level of the whole.

## Add transitions

````markdown
---
transition: crossfade 0.5
---

![](photo.jpg)

(duration: 2)

---

(transition: wipe-left 1)

![](forest.jpg)

(duration: 2)

---

(transition: none)

![](photo.jpg)

(duration: 2)
````

- In the header, a transition plays between every pair of scenes. As a
  direction, it sets the transition into that scene, and `none` turns it off.
- The time is optional (default 0.2 s). `(transition: 1)` alone uses the
  header's type, or a crossfade.
- A transition starts at the cut and plays over the start of the next scene,
  so it doesn't change the video's length.
- **Types:**
  - **Fade:** `crossfade`.
  - **Wipe:** `wipe` (`wipe-right`), `wipe-left`, `wipe-up`, `wipe-down`.
  - **Slide:** `slide-right`, `slide-left`, `slide-up`, `slide-down`.
  - **Soft wipe:** `fade-right`, `fade-left`, `fade-up`, `fade-down`,
    `fade-circle`.
  - **Slice:** `slice-right`, `slice-left`, `slice-up`, `slice-down`.
  - **Pixel:** `dissolve`, `pixelize`.
  - **Shape:** `radial`, `circle`, `rect`, `reveal`.
  - **Dip** (narrate only): `fade-black` and `fade-white`. The outgoing
    picture fades to the colour over the first half, and the next scene fades
    in over the second. A 0.6 s dip is 0.3 s out and 0.3 s in.

### Fade in and out of the whole video

````markdown
---
transition: fade-black 0.6
fade-in: 0.5
fade-out: 1
---

![](photo.jpg)

(duration: 2)

---

![](forest.jpg)

(duration: 2)
````

- **`fade-in: N` and `fade-out: N`** (narrate only) fade the video from black
  at the start, and to black at the end, over N seconds.
- **Sound:** the narration and music fade with the picture, in audio builds
  too.
- The video's length doesn't change.

## Highlight part of the frame

````markdown
![](photo.jpg)

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

The circle draws the eye to the centre, and the black box hides a corner.
````

- **Circle:** centre `cx`, `cy` and radius `size` (default 100).
- **Rectangle:** `type: rectangle` with `left`, `top`, `right` and `bottom`.
- **Shading:** `alpha` sets how dark the rest of the frame goes, from 0 to 1
  (default 0.5).
- **Mask:** `style: mask` blacks out the area instead, for example to hide a
  password.
- **Coordinates** are pixels of the finished video, after resizing.
- **Designer:** `narrate callouts photo.jpg --size 720p --fit cover` writes a
  web page showing the frame exactly as the build will. Drag to draw a callout,
  then copy the direction it prints. For a clip, add `--at 3.5` to pick the
  moment.

## Set the size, poster and file size

````markdown
---
size: instagram-story
poster-time: 2
target: online
---

![](photo.jpg)

A vertical video for stories, with its poster taken two seconds in.
````

- **`size`:** a preset or `WIDTHxHEIGHT` (`800x600`). Presets include `720p`
  (the default), `1080p`, `1440p`, `4x3`, `720p-portrait`, `1080p-portrait`,
  `instagram`, `instagram-square`, `instagram-story`, `tiktok`, `linkedin`,
  `twitter` and `facebook`. [§3.2](spec/narakeet-markdown.md#32-size-presets)
  lists them all.
- **`canvas`:** the colour behind letterboxed pictures and plain slides.
- **`poster-time`:** where the poster image comes from: `start`, `end`, a
  percentage (`50%`, the default), seconds or `MM:SS`.
- **`target`:**
  - `offline` (the default): the largest, best-quality files, for further
    editing.
  - `online`: for uploading to YouTube and similar sites.
  - `self-hosted`: the smallest files, for playing on your own website.

## Run narration across scenes

````markdown
---
voice: Arthur
---

(narration-mode: merge)

![](photo.jpg)

This sentence is spoken in one go,

---

(narration-mode: normal)

![](forest.jpg)

while both pictures share its time.
````

- `merge` joins the narration of every scene from the one that sets it to the
  one that sets `normal`. The joined narration is spoken as one recording, and
  the scenes share its time equally.
- `fragment` keeps scenes separate but shortens the pause after each
  paragraph, so one sentence can run across a few scenes. It stays on until
  another `(narration-mode: …)` changes it.
- For a few pictures under one stretch of narration, putting them all in one
  scene is simpler.

## Package a project as a ZIP

```sh
zip -r project.zip script.md photo.jpg clip.mp4
narrate build project.zip
narrate build project.zip --source videos/intro.md   # when it holds several scripts
```

narrate finds the script inside the archive when there is only one; otherwise
name it with `--source`.

## Differences from Narakeet

- **Voices:** narrate has no copy of Narakeet's catalogue of about 900 voices.
  Names map to the closest Kokoro or ElevenLabs voice
  ([Pick voices](building.md#pick-voices)).
- **Music:** the built-in background tracks are narrate's own, since
  Narakeet's can't be redistributed.
- **Timing:** pauses last exactly as long as written; Narakeet pads some
  scenes by about half a second. Clip ranges end where the script says, which
  Narakeet sometimes overruns.
- **Not supported:** PowerPoint, Google Slides and Keynote input; Narakeet's
  REST API and web editor.
- **narrate only** ([§18](spec/narakeet-markdown.md#18-narrate-extensions)):
  - [render blocks](#generate-pictures-from-code-blocks) generate pictures
    from code blocks, which Narakeet would show as code;
  - [HTML scenes](#show-animated-html-scenes) animate web pages, which
    Narakeet would read out as narration;
  - [free framing](#show-pictures) (`position: 70% 25%`, `from` and `to`)
    frames a picture on any point and pans or zooms between any two windows.
- **Open questions:** where Narakeet's documentation is silent or
  contradicts itself, narrate makes a choice;
  [§16](spec/narakeet-markdown.md#16-gaps-and-how-narrate-resolves-them) lists each
  one.
