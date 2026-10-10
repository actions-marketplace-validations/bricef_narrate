"""Pan/zoom ("Ken Burns") image animation, spec §5.3.

Each motion is a pair of rectangles in source-image pixels, the window shown
in the first and last frames, interpolated linearly. Frames are cut with
Pillow's resize, which takes fractional source boxes, so the motion is
sub-pixel smooth (ffmpeg's zoompan rounds to whole pixels and jitters).
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from PIL import Image, ImageOps

MOTIONS = {"zoom", "zoomout", "pan", "panzoom", "panzoomout"}
ZOOM = 1.25  # how far zoom/zoomout/panzoom/panzoomout move in, unless a picture says (#49)
PAN_ZOOM = 1.15  # fixed zoom for pan, leaving room to travel; a picture's zoom replaces it
OVERSAMPLE = 1.5  # source pixels per output pixel kept after the one-off downscale

Rect = tuple[float, float, float, float]  # x, y, width, height
Focus = tuple[float, float]  # a point in the picture, as fractions of its width and height (#63)
Window = tuple[float, float, float]  # a window's centre (fractions) and zoom, 1 being the cover framing


def _align(width: float, height: float, bounds: Rect, position: str, point: tuple[float, float] | None = None) -> Rect:
    """A width×height rect placed inside bounds by position (centred on the free axis), or centred on
    `point` (in the same pixels) as far as the bounds allow."""
    bx, by, bw, bh = bounds
    if point is not None:
        x = min(max(point[0] - width / 2, bx), bx + bw - width)
        y = min(max(point[1] - height / 2, by), by + bh - height)
        return x, y, width, height
    x = {"left": bx, "top-left": bx, "right": bx + bw - width}.get(position, bx + (bw - width) / 2)
    y = {"top": by, "top-left": by, "bottom": by + bh - height}.get(position, by + (bh - height) / 2)
    return x, y, width, height


def cover_size(image_w: float, image_h: float, out_w: int, out_h: int) -> tuple[float, float]:
    """The largest rect of the output's aspect ratio that fits in the image."""
    scale = min(image_w / out_w, image_h / out_h)
    return out_w * scale, out_h * scale


def window_rect(window: Window, image_w: float, image_h: float, out_w: int, out_h: int) -> tuple[Rect, bool]:
    """A window as a rect in the picture's pixels, and whether it had to be moved in to stay inside it."""
    cw, ch = cover_size(image_w, image_h, out_w, out_h)
    w, h = cw / window[2], ch / window[2]
    x0, y0 = window[0] * image_w - w / 2, window[1] * image_h - h / 2
    x, y = min(max(x0, 0.0), image_w - w), min(max(y0, 0.0), image_h - h)
    return (x, y, w, h), abs(x - x0) > 0.5 or abs(y - y0) > 0.5


def alignment(focus: Focus, image_w: float, image_h: float, out_w: int, out_h: int, fit: str) -> Focus:
    """Where a still crop sits, as CSS object-position fractions, to keep `focus` as near the middle of
    the frame as the picture allows. With contain, the focal point is the alignment itself."""
    if fit == "contain":
        return focus
    if fit == "fit":
        return 0.5, 0.5
    cw, ch = cover_size(image_w, image_h, out_w, out_h)

    def axis(f: float, size: float, window: float) -> float:
        return 0.5 if size - window < 0.5 else min(1.0, max(0.0, (f * size - window / 2) / (size - window)))

    return axis(focus[0], image_w, cw), axis(focus[1], image_h, ch)


def endpoints(motion: str | None, position: str, image_w: float, image_h: float, out_w: int, out_h: int,
              zoom: float | None = None, focus: Focus | None = None,
              windows: tuple[Window | None, Window | None] | None = None) -> tuple[Rect, Rect]:
    """The first and last windows. `zoom` is how far the motion moves in (for a pan, how far it's zoomed);
    a `focus` replaces the position as the point it heads for; `windows` give both ends outright (#63),
    either left out being the plain framing."""
    near = zoom or ZOOM
    pan = zoom or PAN_ZOOM
    image = (0.0, 0.0, image_w, image_h)
    point = (focus[0] * image_w, focus[1] * image_h) if focus else None
    cw, ch = cover_size(image_w, image_h, out_w, out_h)
    centred = _align(cw, ch, image, "center")
    placed = _align(cw, ch, image, position, point)
    if windows is not None:
        start, end = (window_rect(w, image_w, image_h, out_w, out_h)[0] if w else placed for w in windows)
        return start, end
    if motion == "zoom":
        return placed, _align(cw / near, ch / near, placed, position, point)
    if motion == "zoomout":
        return _align(cw / near, ch / near, placed, position, point), placed
    if motion == "pan":
        return (_align(cw / pan, ch / pan, image, "center"),
                _align(cw / pan, ch / pan, image, position, point))
    if motion == "panzoom":
        return centred, _align(cw / near, ch / near, image, position, point)
    if motion == "panzoomout":
        return _align(cw / near, ch / near, image, "center"), placed
    raise ValueError(f"unknown motion {motion!r}")


def frames(path: Path, motion: str | None, position: str, width: int, height: int, count: int,
           zoom: float | None = None, focus: Focus | None = None,
           windows: tuple[Window | None, Window | None] | None = None) -> Iterator[bytes]:
    """`count` RGB24 frames of the animated image at width×height."""
    with Image.open(path) as im:
        source = ImageOps.exif_transpose(im).convert("RGB")
    # One downscale up front keeps every per-frame resize cheap on big photos
    cw, _ = cover_size(source.width, source.height, width, height)
    deepest = max([w[2] for w in windows or () if w] + [zoom or ZOOM])
    shrink = min(1.0, width * max(OVERSAMPLE, deepest) / cw)  # keep detail for the deepest zoom
    if shrink < 1.0:
        source = source.resize((max(1, round(source.width * shrink)), max(1, round(source.height * shrink))),
                               Image.LANCZOS)
    start, end = endpoints(motion, position, source.width, source.height, width, height, zoom, focus, windows)
    for i in range(count):
        t = i / (count - 1) if count > 1 else 0.0
        x, y, w, h = (a + (b - a) * t for a, b in zip(start, end))
        yield source.resize((width, height), Image.BICUBIC, box=(x, y, x + w, y + h)).tobytes()
