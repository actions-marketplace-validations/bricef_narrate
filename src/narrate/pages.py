"""HTML scenes (#44): pages animated with CSS or JavaScript, captured frame by frame.

A page is never recorded in real time. Its clock is paused before it loads
(frames.FrameRenderer.page), and for every frame narrate

1. advances the page's clock to the frame's time, which runs timers,
   requestAnimationFrame callbacks and Date forward exactly that far;
2. pauses every animation (CSS animations and transitions, Web Animations)
   and seeks it to the frame's time, counting from the frame it first
   appeared in, so animations that scripts start later line up too; SVG
   animations are seeked the same way;
3. takes a screenshot.

So every build captures the same frames, at whatever speed the machine
manages. A page without scripts can't change once its last finite animation
has finished, so from then on the last frame is reused instead of captured.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .frames import FrameRenderer

# Seek every animation to time t (seconds); report whether the page has settled
_SEEK_JS = """t => {
  let settled = document.scripts.length === 0;
  for (const a of document.getAnimations()) {
    if (a.__narrateStart === undefined) a.__narrateStart = t;
    a.pause();
    a.currentTime = (t - a.__narrateStart) * 1000;
    const end = a.effect ? a.effect.getComputedTiming().endTime : Infinity;
    if (!(a.currentTime >= end)) settled = false;  // still running, or infinite
  }
  for (const svg of document.querySelectorAll('svg')) {
    if (svg.pauseAnimations) { svg.pauseAnimations(); svg.setCurrentTime(t); }
    if (svg.querySelector('animate, animateTransform, animateMotion, set')) settled = false;
  }
  return settled;
}"""

# When the page's last finite animation ends, in seconds from load (0 if none)
_END_JS = """() => {
  let end = 0;
  for (const a of document.getAnimations()) {
    const t = a.effect && a.effect.getComputedTiming();
    if (t && Number.isFinite(t.endTime)) end = Math.max(end, t.endTime);
  }
  return end / 1000;
}"""


def _ms(frame: int, fps: int) -> int:
    return round(frame * 1000 / fps)


_lengths: dict[tuple, float] = {}


def natural_length(frames: FrameRenderer, path: Path, viewport: tuple[int, int]) -> float:
    """How long the page's finite animations take to play out, in seconds.

    Remembered per file version, so the speech prefetch's planning pass and
    the build's own don't load the page twice."""
    stat = path.stat()
    key = (str(path.resolve()), stat.st_mtime_ns, stat.st_size, viewport)
    if key not in _lengths:
        with frames.page(path, viewport) as page:
            _lengths[key] = float(page.evaluate(_END_JS))
    return _lengths[key]


def cue_script(duration: float, cues: dict[str, float], params: dict[str, str] | None = None,
               scenes: list[dict] | None = None) -> str:
    """What a page learns about the narration (#45), set before its own scripts run.

    CSS custom properties on the root element: --narrate-duration (how long
    the page is on screen) and --cue-N / --cue-NAME (when the scene's Nth
    narration block, or an SSML mark, starts, from the page's start); and the
    same numbers, in seconds, as window.narrate for scripts. An overlay (#59)
    also gets its parameters (window.narrate.params) and, over the whole
    video, each scene's start and length (window.narrate.scenes, --scene-N)."""
    data: dict = {"duration": round(duration, 4), "cues": {k: round(t, 4) for k, t in cues.items()},
                  "params": params or {}}
    props = {"--narrate-duration": f"{duration:.4f}s", **{f"--cue-{k}": f"{t:.4f}s" for k, t in cues.items()}}
    if scenes is not None:
        data["scenes"] = scenes
        props.update({f"--scene-{sc['index']}": f"{sc['start']:.4f}s" for sc in scenes})
    return f"""window.narrate = Object.freeze({json.dumps(data)});
(() => {{
  const props = {json.dumps(props)};
  const apply = () => {{ for (const [k, v] of Object.entries(props)) document.documentElement.style.setProperty(k, v); }};
  if (document.documentElement) apply();
  else new MutationObserver((_, seen) => {{ if (document.documentElement) {{ apply(); seen.disconnect(); }} }})
    .observe(document, {{childList: true}});
}})();"""


def capture(frames: FrameRenderer, path: Path, viewport: tuple[int, int], scale: float, count: int, fps: int,
            stats: Callable[[int], None] | None = None, init_script: str | None = None,
            transparent: bool = False, start: float = 0.0) -> Iterator[bytes]:
    """`count` PNG frames of the page at `fps`, starting from the moment it loaded.

    `stats` is told how many frames were actually captured (the rest reused);
    `init_script` runs before the page's own (cue_script). `transparent` keeps
    the page's own transparency, for overlays (#59). `start` is the page's time
    at the first frame: a video overlay in a build of some scenes picks up its
    clock where those scenes fall in the whole video."""
    captured = 0
    with frames.page(path, viewport, scale, init_script) as page:
        last = b""
        settled = False
        if start > 0:
            page.evaluate(_SEEK_JS, 0.0)  # animations already running started with the page, not now
            page.clock.run_for(round(start * 1000))
        for i in range(count):
            if not settled:
                if i:
                    page.clock.run_for(_ms(i, fps) - _ms(i - 1, fps))
                settled = page.evaluate(_SEEK_JS, start + i / fps)
                last = page.screenshot(type="png", omit_background=transparent)
                captured += 1
            yield last
    if stats:
        stats(captured)
