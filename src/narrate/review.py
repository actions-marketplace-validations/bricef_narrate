"""Contact sheets (#67): a built video's frames side by side, for reviewing it without watching it.

An LLM agent can't play a video, but it can look at a picture: one frame per
scene, labelled with its time and scene, shows layout, framing, slides,
callouts and subtitles at a glance. Frames come from narrate's own ffmpeg, so
this works wherever narrate does.
"""

from __future__ import annotations

import math
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from . import media
from .doctor import find_font

COLUMNS = 4
LABEL_HEIGHT = 24


def evenly(duration: float, count: int) -> list[float]:
    """`count` moments spread across the video, each in the middle of its share."""
    return [duration * (k + 0.5) / count for k in range(count)]


def every(duration: float, seconds: float) -> list[float]:
    """A moment in the middle of each `seconds` of the video."""
    count = max(1, math.ceil(duration / seconds))
    return [min(duration, (k + 0.5) * seconds) for k in range(count)]


def clock(seconds: float) -> str:
    return f"{int(seconds // 60)}:{seconds % 60:04.1f}"


def contact_sheet(video: Path, moments: list[tuple[float, str]], out: Path, width: int = 480) -> Path:
    """The frames at `moments` (time, label) in a grid, each `width` wide and labelled, written to `out`."""
    duration = media.probe(video).duration
    font_path = find_font("DejaVuSans.ttf")
    font = ImageFont.truetype(str(font_path), 14) if font_path else ImageFont.load_default()
    cells: list[Image.Image] = []
    with tempfile.TemporaryDirectory(prefix="narrate-frames-") as tmp:
        for k, (at, label) in enumerate(moments):
            png = media.extract_frame(video, min(max(0.0, at), max(0.0, duration - 1 / 30)), Path(tmp) / f"{k}.png")
            with Image.open(png) as im:
                frame = im.convert("RGB")
            frame = frame.resize((width, max(1, round(frame.height * width / frame.width))), Image.LANCZOS)
            cell = Image.new("RGB", (width, frame.height + LABEL_HEIGHT), (24, 26, 30))
            cell.paste(frame, (0, 0))
            ImageDraw.Draw(cell).text((8, frame.height + 4), f"{clock(at)}  {label}".strip(), fill=(230, 230, 230),
                                      font=font)
            cells.append(cell)
    columns = min(COLUMNS, len(cells))
    rows = math.ceil(len(cells) / columns)
    cw, ch = cells[0].size
    sheet = Image.new("RGB", (columns * cw + (columns - 1) * 4, rows * ch + (rows - 1) * 4), (0, 0, 0))
    for k, cell in enumerate(cells):
        sheet.paste(cell, ((k % columns) * (cw + 4), (k // columns) * (ch + 4)))
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out)
    return out
