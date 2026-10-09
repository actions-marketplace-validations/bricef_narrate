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


def capture(frames: FrameRenderer, path: Path, viewport: tuple[int, int], scale: float, count: int, fps: int,
            stats: Callable[[int], None] | None = None) -> Iterator[bytes]:
    """`count` PNG frames of the page at `fps`, starting from the moment it loaded.

    `stats` is told how many frames were actually captured (the rest reused)."""
    captured = 0
    with frames.page(path, viewport, scale) as page:
        last = b""
        settled = False
        for i in range(count):
            if not settled:
                if i:
                    page.clock.run_for(_ms(i, fps) - _ms(i - 1, fps))
                settled = page.evaluate(_SEEK_JS, i / fps)
                last = page.screenshot(type="png")
                captured += 1
            yield last
    if stats:
        stats(captured)
