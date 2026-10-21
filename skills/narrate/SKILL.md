---
name: narrate
description: Make narrated videos from text with the narrate CLI. Write a Markdown script (scenes, voice-over, pictures, clips, slides, Mermaid diagrams, animated HTML scenes), turn existing material such as a README, blog post, outline or docs page into a video, then build it, check its timing and cost, and review the frames. Use this whenever someone wants an explainer, walkthrough, product intro, tutorial, announcement, slideshow or demo with a voice-over, asks for a video made from a document, or mentions narrate, Narakeet, a "Markdown to video" script or text-to-video, even if they don't name narrate.
---

# Making videos with narrate

narrate turns a Markdown script into an MP4. Each paragraph you write is
spoken by a synthetic voice, and each scene lasts exactly as long as its
narration, so **the words are the timeline**: pictures, slides and cues hang
off them.

You can't watch a video, so you'll work from evidence instead: the script's
timing before building (`narrate check --timing`), a fast silent preview, and
a contact sheet of the result's frames (`narrate frames`), which you can look
at as an image. The loop below uses all three.

## Getting narrate running

Run `narrate doctor`. It checks ffmpeg, Chromium, fonts, the voice model and
any ElevenLabs key, and says what's missing.

If `narrate` isn't on the PATH, use one of these, and use it in place of
`narrate` in every command below:
- **A source checkout:** `uv run --project <checkout> narrate …`. On the
  author's machines the checkout is `~/Code/github.com/bricef/narrate`.
- **Docker:** `docker run --rm --user "$(id -u):$(id -g)" -v "$PWD:/work" -v narrate-cache:/cache ghcr.io/bricef/narrate …`,
  run from the folder holding the script. On Apple Silicon (`uname -m`
  prints `arm64`), add `--platform linux/amd64` after `docker run`: the image
  is built for x86-64 only, so it runs under emulation, several times more
  slowly than a source checkout.

The first real build downloads the Kokoro voice model (about 350 MB), so
expect it to be slower than later ones.

## The loop

1. **Understand the brief.** Who is it for, how long, which platform (the
   platform decides the `size` and how subtitles ship), which voice or tone,
   and what material exists: look in the folder for pictures and clips before
   inventing any. Ask about what you can't sensibly assume. Otherwise choose,
   and say what you chose.
2. **Plan the scenes** before writing the script: one idea per scene, each
   with what's on screen and roughly how many words. narrate speaks about
   **150 words a minute**, so a 90-second video is about 220 words of
   narration, less the pauses. Most scenes run 5–15 seconds.
3. **Write the script** next to its media (paths are relative to the script).
   [Script essentials](#script-essentials) below covers most videos;
   `references/format.md` has every option.
4. **Check and time it:**
   `narrate check script.md --timing --tts kokoro`
   - **Errors:** missing files, bad values and render-block mistakes are
     errors with their line numbers. Fix them all.
   - **Length:** it lists each scene's length and the total. Adjust the words
     until the total meets the brief. Lengths marked `≈` are estimates until
     the speech is synthesised.
5. **Preview silently:**
   `narrate build script.md --tts silent -o preview.mp4`
   - **Speed:** it builds in seconds, with silence timed like speech.
   - **What it proves:** layout, pictures, slides, diagrams, HTML scenes,
     subtitles and transitions all render.
   - **Read the notes it prints:** they tell you what narrate approximated
     or ignored.
6. **Look at it:**
   `narrate frames preview.mp4 --script script.md --tts silent`
   Then open the PNG it writes, with one frame from the middle of each scene.
   Check each frame:
   - text is readable;
   - nothing important is cropped;
   - slides don't overflow;
   - diagrams are legible at video size;
   - subtitles don't cover the point of the picture;
   - each scene shows what its words talk about.

   Fix the script and repeat steps 4–6 until it's right.
7. **Make the real draft with the free voice:**
   `narrate build script.md --tts kokoro`
   Then `narrate frames script.mp4 --script script.md --tts kokoro` if
   anything changed. Speech is cached, so later builds re-synthesise only the
   paragraphs you edit.
8. **Hear it:** `narrate hear script.mp4 --script script.md`
   - **What it does:** it listens with speech-to-text and lists only where
     the narration sounds different from the script, with scene, line and
     moment.
   - **What it catches:** names, product words, acronyms and jargon the voice
     gets wrong.
   - **How to fix one:** see [Pronunciation](#pronunciation), then rebuild
     and hear again.

   A difference is worth fixing when the voice is the cause. Speech-to-text
   also mishears homophones ("your" for "you're"), so judge each one.
9. **ElevenLabs only when the user asks for it.** See
   [Speech and cost](#speech-and-cost).
10. **Deliver:**
   - the video's path, its length and its poster (`script.jpg`);
   - subtitle files or a transcript, if asked for;
   - what you assumed;
   - anything left for the user, such as placeholders standing in for
     pictures they need to supply.

## Script essentials

````markdown
---
size: 1080p
voice: bf_emma
subtitles: overlay
transition: crossfade 0.4
background: uplifting-1 0.4 fade-in fade-out
---

```md
# Shipping on Fridays
How our team releases safely
```

(pause: 1)

---

![cover top](team.jpg)

Every Friday at four, the release train leaves.

Here's what has to happen before it does.

---

```render:mermaid
flowchart LR
  PR[Pull request] --> CI --> Staging --> Production
```

Each change goes through the same four steps.

---

```render:placeholder
Screenshot: the deploy dashboard
```

(callout:
  cx: 960
  cy: 400
  size: 180)

The dashboard shows each step turning green.
````

- **Blocks:** scenes are separated by a line of `---`. Inside a scene, each
  paragraph is exactly one of these:
  - a picture or clip, `![options](file)`;
  - a stage direction on its own line, `(key: value)`;
  - a slide, a fenced code block (shown, never spoken);
  - a block quote, `> text` (shown as a subtitle);
  - narration (anything else).
- **Scene length:** a scene lasts as long as its narration and pauses. A
  scene with no narration needs `(duration: N)`, or it lasts 1 second.
- **Sharing time:** several pictures in one scene take turns, sharing its
  time equally. So do several slides.
- **Slides:**
  - a ```` ```md ```` fence renders Markdown (headings, bullets);
  - a plain fence shows big bold text;
  - a language name (```` ```python ````) shows highlighted code.

  Over a picture, a slide sits on a darkened backdrop.
- **Pictures:** fit is `cover` (the default, crops), `contain` (letterboxed)
  or `fit` (stretched). Add a position (`top`, `left`, …) and motion (`zoom`,
  `pan`, `panzoom`, …) as words in the alt text. For smooth motion, use
  pictures larger than the video.
- **Generated pictures:**
  - `render:mermaid` draws diagrams.
  - `render:placeholder` draws a labelled card for a picture that doesn't
    exist yet. Use it instead of inventing a file name.
  - `render:web` captures a live web page.
- **Voices:**
  - Kokoro IDs (`bf_emma`, `am_michael`), ElevenLabs default names
    (`George`, `Lily`) and Narakeet names (`Amy`, `Arthur`) all work on
    every engine.
  - `narrate voices` lists them.
  - `(voice: X)` switches voice until the end of the scene.
- **Pauses:** `(pause: 1.5)` adds silence. An ellipsis adds about half a
  second. `(pause-until: 4)` waits for a moment in the scene (for instance to
  let a clip play).

For everything else, read `references/format.md`:
- clip ranges and sync, free framing (`position: 70% 25%`, `from`/`to`);
- callouts, subtitle styles, transitions, themes, music, loudness and sizes;
- pronunciation and SSML, merged narration, header keys.

## Writing narration that works

Narration is heard once, at speaking pace, alongside a picture. Write it to
be heard:
- short sentences;
- one point per paragraph;
- concrete words;
- numbers said the way people say them.

Each paragraph becomes one subtitle, so one or two sentences per paragraph
keeps subtitles changing with the speech. `references/writing.md` covers this
in depth, including how to turn a long document into a short script without
losing its point.

### Pronunciation

1. **Write words plainly first.** The voices read most names, acronyms and
   numbers correctly as written.
2. **Then let `narrate hear` tell you what's wrong.** Don't guess in advance:
   markup added "just in case" often makes things worse. For example,
   spelling `` `API` `` letter by letter came out as "IP".
3. **Fix only what it flags, inside a `<speak>` paragraph**, so the subtitles
   and transcript keep the real word. Use a respelling alias first, since it
   works reliably with every voice:
   - `<sub alias="quiet tube">quietube</sub>` says "quiet tube", and the
     subtitle shows `quietube`.
   - `<sub alias="Y T D L P">yt-dlp</sub>`: spaced capitals spell an acronym
     out, letter by letter.
   - `<phoneme alphabet="ipa" ph="…">word</phoneme>` is a last resort. Voices
     follow IPA unevenly; Kokoro misread it in testing.

   Hear it again after each fix. Avoid `[…]{ipa}` spans in videos with
   subtitles or a transcript: they show the phonetic symbols themselves, not
   the word.

## Choosing visuals

Use the user's own pictures and clips when they exist. When they don't:
- a slide for a title, a list, a quote or a number;
- `render:mermaid` for anything with structure (a process, an architecture,
  a timeline, a comparison);
- `render:web` for a live page;
- an **animated HTML scene** for titles, data that builds up, or anything
  that should move in step with the words;
- an **overlay** (`(overlay: page.html)`, or `overlay:` in the header for the
  whole video) to lay a transparent web page over the picture: a ticker, a
  speaker's name, a legend, labels.

HTML scenes are the most powerful option and the most work. Read
`references/html-scenes.md` before writing one. They're local web pages that
narrate captures frame by frame on the video's clock, with CSS variables
that say when each paragraph, or a named word, is spoken.

**When the real picture doesn't exist** (a screenshot of an app, a photo of
the team), choose between two stand-ins:
- **A `render:placeholder` card** when the user will supply the picture
  before the video is used. It's a labelled gap, and swapping in the real file
  is a one-line change. List every one when you deliver.
- **A drawn illustration** (an HTML scene, a diagram or a slide) when the
  video should work as it is. Label it ("Illustration") if it could pass for
  the real thing. A blank card in a finished video looks unfinished.

Never pass off an illustration as a real screenshot. Never invent product
details that the source material doesn't have.

## Speech and cost

- **Silent** (`--tts silent`): instant and free, for checking layout and
  timing.
- **Kokoro** (`--tts kokoro`): a good free voice running on the computer, for
  real drafts.
- **ElevenLabs** (`--tts elevenlabs`): the best voices, but every character
  synthesised spends the user's credits.

Always pass `--tts`. The default, `auto`, picks ElevenLabs whenever a key is
set, which would spend credits without asking.

Use ElevenLabs only when the user asks for it. First run
`narrate check script.md --timing --tts elevenlabs`. It works without a key,
so you can quote the cost before the user sets one up. Then tell the user how
many characters the build will send, and build only after they agree; a build
needs `ELEVENLABS_API_KEY`. Speech is cached by its text and voice:
- rebuilding an unchanged script costs nothing;
- editing one paragraph re-synthesises only that paragraph;
- a draft that's still changing is the wrong time to use ElevenLabs.

## Traps

- **A narration line that starts with `(word:`** is taken for a stage
  direction and dropped, with a warning. Reword it.
- **Unsupported image formats:** pictures must be JPG, PNG or GIF. A `.webp`
  or `.svg` in image syntax is read aloud instead of shown. Convert it first.
- **Header colours:** the header is YAML, so quote a colour that starts with
  `#`: `canvas: "#202020"`.
- **Horizontal rules:** a `---` inside your content starts a new scene. A
  line starting with `>` is a subtitle, not narration.
- **Where outputs go:** the current folder, named after the script, unless
  `-o` says otherwise.
- **Folders:** keep the script and its media in one folder.
- **HTML scenes stay local:** anything they fetch from the network slows the
  capture and ties the build to the network.
- **Timing your frames:** when timing frames or checks, use the engine the
  video was built with. Kokoro and silent speech differ in length.
