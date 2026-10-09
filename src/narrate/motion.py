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


def _align(width: float, height: float, bounds: Rect, position: str) -> Rect:
    """A width×height rect placed inside bounds by position (centred on the free axis)."""
    bx, by, bw, bh = bounds
    x = {"left": bx, "top-left": bx, "right": bx + bw - width}.get(position, bx + (bw - width) / 2)
    y = {"top": by, "top-left": by, "bottom": by + bh - height}.get(position, by + (bh - height) / 2)
    return x, y, width, height


def cover_size(image_w: float, image_h: float, out_w: int, out_h: int) -> tuple[float, float]:
    """The largest rect of the output's aspect ratio that fits in the image."""
    scale = min(image_w / out_w, image_h / out_h)
    return out_w * scale, out_h * scale


def endpoints(motion: str, position: str, image_w: float, image_h: float, out_w: int, out_h: int,
              zoom: float | None = None) -> tuple[Rect, Rect]:
    """The first and last windows. `zoom` is how far the motion moves in (for a pan, how far it's zoomed)."""
    near = zoom or ZOOM
    pan = zoom or PAN_ZOOM
    image = (0.0, 0.0, image_w, image_h)
    cw, ch = cover_size(image_w, image_h, out_w, out_h)
    centred = _align(cw, ch, image, "center")
    placed = _align(cw, ch, image, position)
    if motion == "zoom":
        return placed, _align(cw / near, ch / near, placed, position)
    if motion == "zoomout":
        return _align(cw / near, ch / near, placed, position), placed
    if motion == "pan":
        return (_align(cw / pan, ch / pan, image, "center"),
                _align(cw / pan, ch / pan, image, position))
    if motion == "panzoom":
        return centred, _align(cw / near, ch / near, image, position)
    if motion == "panzoomout":
        return _align(cw / near, ch / near, image, "center"), placed
    raise ValueError(f"unknown motion {motion!r}")


def frames(path: Path, motion: str, position: str, width: int, height: int, count: int,
           zoom: float | None = None) -> Iterator[bytes]:
    """`count` RGB24 frames of the animated image at width×height."""
    with Image.open(path) as im:
        source = ImageOps.exif_transpose(im).convert("RGB")
    # One downscale up front keeps every per-frame resize cheap on big photos
    cw, _ = cover_size(source.width, source.height, width, height)
    shrink = min(1.0, width * max(OVERSAMPLE, zoom or ZOOM) / cw)  # keep detail for the deepest zoom
    if shrink < 1.0:
        source = source.resize((max(1, round(source.width * shrink)), max(1, round(source.height * shrink))),
                               Image.LANCZOS)
    start, end = endpoints(motion, position, source.width, source.height, width, height, zoom)
    for i in range(count):
        t = i / (count - 1) if count > 1 else 0.0
        x, y, w, h = (a + (b - a) * t for a, b in zip(start, end))
        yield source.resize((width, height), Image.BICUBIC, box=(x, y, x + w, y + h)).tobytes()
