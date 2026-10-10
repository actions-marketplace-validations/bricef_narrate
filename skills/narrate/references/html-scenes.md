# Animated HTML scenes

An HTML scene is a local web page used as a scene's picture. narrate loads it in headless Chromium
and captures it frame by frame on the video's own clock, so CSS animations, SVG animations,
JavaScript timers, `requestAnimationFrame` and `Date` all advance exactly one frame at a time.
Every build gives the same video, however fast the machine. Read this before writing one.

## When to use one

Use an HTML scene when something should appear or move **in step with the words**. Typical uses:
- a title sequence;
- numbers that land as they're said;
- a terminal command that types itself;
- a diagram that builds node by node;
- a before/after comparison;
- a list that reveals point by point.

For a static picture, a slide or a Mermaid diagram is less work. Use those when nothing needs to
move.

## A scene from start to finish

`scene.md`:

````markdown
---
size: 720p
canvas: "#0d1117"
---

![](scenes/numbers.html)

<speak>Five hundred pull requests merged. <mark name="fleet"/>A hundred and fifty of them by the fleet.</speak>

And the first one landed in July.
````

`scenes/numbers.html`:

```html
<!doctype html>
<link rel="stylesheet" href="common.css">
<style>
  .big { font-size: 120px; font-weight: 700; line-height: 1; }
  .lbl { font-size: 28px; color: var(--mute); }
</style>
<body><div class="wrap grid">
  <div class="up" style="animation-delay: var(--cue-1, .4s)"><div class="big">500</div><div class="lbl">pull requests merged</div></div>
  <div class="up" style="animation-delay: var(--cue-fleet, 2s)"><div class="big accent">150</div><div class="lbl">by the fleet</div></div>
  <div class="up" style="animation-delay: var(--cue-2, 3.6s)"><div class="big">Jul</div><div class="lbl">the first one</div></div>
</div></body>
```

`scenes/common.css` (share one across all of a video's scenes, so they look like one video):

```css
:root { --bg: #0d1117; --fg: #e6edf3; --mute: #8b949e; --acc: #58a6ff; }
* { box-sizing: border-box; }
html, body { margin: 0; width: 1280px; height: 720px; overflow: hidden;
             background: var(--bg); color: var(--fg); font-family: "DejaVu Sans", sans-serif; }
.wrap { position: absolute; inset: 0; padding: 72px 96px; display: flex; flex-direction: column; justify-content: center; }
.grid { display: grid; grid-template-columns: 1fr 1fr; gap: 60px; align-content: center; }
.accent { color: var(--acc); }
.up { opacity: 0; transform: translateY(14px); animation: up .5s ease-out forwards; }
@keyframes up { to { opacity: 1; transform: none; } }
```

## Timing to the narration: cues

narrate gives each page the scene's timing as CSS custom properties, in seconds from the page's
start:

| Property | When |
| --- | --- |
| `--cue-1`, `--cue-2`, … | each narration block (a paragraph, an SSML paragraph or a recording) starts |
| `--cue-NAME` | the voice reaches `<mark name="NAME"/>` inside a `<speak>` paragraph |
| `--narrate-duration` | how long the page is on screen |

- **Use them as animation delays:** `animation-delay: var(--cue-2, 1.2s)`. Always give a fallback.
  It keeps the page working when you open it in a browser, and documents the intended timing.
- **Words inside a paragraph:** a `<mark name="x"/>` where the word is said gives an exact cue for
  something to land on that word. Mark names use letters, digits, `-` and `_`, starting with a
  letter. Marks need a `<speak>…</speak>` paragraph.
- **Leaving:** `animation-delay: calc(var(--narrate-duration) - .5s)` starts an exit half a second
  before the scene ends.
- **Scripts:** the same numbers are in `window.narrate.cues` (`window.narrate.cues["2"]`,
  `window.narrate.cues.fleet`) and `window.narrate.duration`, set before your scripts run.
- **The page's own start:** cues count from when the page appears. That differs from the scene's
  start when another picture comes first in the scene.

## How long it lasts

- **With narration:** the scene lasts as long as its narration, as usual, and the page shows
  throughout. If the animation needs longer than the words, add `(duration: N)` (the longer of the
  two wins) or end the scene with `(pause: N)`.
- **Without narration or duration:** the scene lasts until the page's last finite animation ends.
  An animation that repeats forever, such as a blinking cursor, doesn't count.

## Size

- **Laid out at the video's size by default:** design the page for 1280×720 (for `720p`), or
  1920×1080 (for `1080p`), and set `html, body` to that size.
- **Designed at another size:** `(html: {file: scene.html, viewport: 1280x720})` lays it out at
  that size and draws it sharply at the video's size. `size: contain` or `cover`, and `position`,
  apply as for pictures when the shapes differ.

## Patterns that work

- **Reveal in order:**
  ```css
  .up { opacity: 0; transform: translateY(14px); animation: up .5s ease-out forwards; }
  ```
  Give each element its own delay (a cue, or fixed steps `.d1 { animation-delay: .4s }`, …).
- **Typing:**
  ```css
  .type { display: inline-block; white-space: nowrap; overflow: hidden; width: 0;
          animation: type 2.2s steps(46) .6s forwards; }
  @keyframes type { to { width: 46ch; } }
  ```
  Use a monospace font, and `steps(N)` with N as the text's length.
- **Counting up:** JavaScript is deterministic here:
  ```html
  <span id="n">0</span>
  <script>
    const el = document.getElementById("n"), target = 3200, start = (window.narrate?.cues?.["1"] ?? 0.4) * 1000;
    const t0 = performance.now();
    function tick(now) {
      const p = Math.min(1, Math.max(0, (now - t0 - start) / 1500));
      el.textContent = Math.round(target * (1 - (1 - p) ** 3)).toLocaleString();
      if (p < 1) requestAnimationFrame(tick);
    }
    requestAnimationFrame(tick);
  </script>
  ```
- **Diagrams that build:** inline SVG with each node and edge in its own group, revealed with the
  `.up` pattern or `stroke-dashoffset` animations.
- **Highlighting part of a screenshot:** `<img>` of a project file, with absolutely positioned boxes
  fading in. Or keep it a picture and use `(callout: …)`.

## Rules and limits

- **Local files only:**
  - Pictures, fonts, CSS and scripts come from the project folder, by relative path.
  - Nothing is fetched from the network: CDNs and web fonts slow the capture and make the build
    depend on the network.
  - Use system fonts that exist on the machine (DejaVu, Noto), or a font file with `@font-face`.
- **No `<video>` or `<audio>`:** they aren't captured or kept in time. Use a clip
  (`![](clip.mp4)`) as its own scene or picture instead.
- **Capture speed:** about twice real time. A page without scripts stops being captured once its
  animations end, so script-free pages build faster.
- **What works over it:** callouts, slides, subtitles and transitions all work over an HTML scene.
- **Merged scenes:** pages in merged scenes (`narration-mode: merge`) get no cues.

## Checking it

You can't watch it, so look at moments:
1. Build a silent preview: `narrate build script.md --tts silent -o preview.mp4`.
2. Look at the start, middle and end of the scene.
   - Find the scene's start and length with `narrate check script.md --timing --tts silent`.
   - Then take frames, for example for a scene from 12.0 to 19.5 s:
     `narrate frames preview.mp4 --at 12.3,14,16,19.2 -o scene4.png`.
   - Check that each element appears when its words come, and that nothing overlaps or overflows.
3. **Re-check after the real voice:** Kokoro's timing differs from the silent estimate. After a
   Kokoro build, take frames again with `--tts kokoro` timings.
4. **Opening the page in a browser** shows it with the fallback delays: a quick check of layout,
   not of timing.
