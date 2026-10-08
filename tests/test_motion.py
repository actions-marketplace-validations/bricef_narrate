from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageDraw

from narrate import media
from narrate.build import Builder
from narrate.motion import PAN_ZOOM, ZOOM, endpoints, frames
from narrate.script import parse_file
from narrate.tts import SilentSynth


def test_zoom_starts_at_cover_and_ends_zoomed_on_the_position():
    start, end = endpoints("zoom", "top", 2000, 1000, 1280, 720)
    assert start == pytest.approx((111.11, 0.0, 1777.78, 1000.0), abs=0.01)
    assert end[2] == pytest.approx(start[2] / ZOOM) and end[1] == 0.0  # anchored to the top


def test_pan_travels_from_the_centre_to_the_edge():
    start, end = endpoints("pan", "left", 2000, 1000, 1280, 720)
    assert start[0] > 0 and end[0] == 0.0
    assert start[2] == end[2] == pytest.approx(1777.78 / PAN_ZOOM, abs=0.01)


def test_panzoomout_ends_on_the_placed_cover():
    start, end = endpoints("panzoomout", "right", 2000, 1000, 1280, 720)
    assert end == pytest.approx((2000 - 1777.78, 0.0, 1777.78, 1000.0), abs=0.01)
    assert start[2] == pytest.approx(1777.78 / ZOOM, abs=0.01)


def disc_image(path: Path) -> Path:
    im = Image.new("RGB", (1280, 720), "white")
    ImageDraw.Draw(im).ellipse((540, 260, 740, 460), fill="black")
    im.save(path)
    return path


def test_frames_zoom_smoothly(tmp_path):
    areas = [int((np.frombuffer(f, np.uint8).reshape(180, 320, 3)[..., 0] < 128).sum())
             for f in frames(disc_image(tmp_path / "disc.png"), "zoom", "center", 320, 180, 30)]
    assert all(b >= a for a, b in zip(areas, areas[1:]))  # never steps back: no jitter
    assert areas[-1] / areas[0] == pytest.approx(ZOOM**2, rel=0.08)


def test_slide_over_an_animated_image_renders(tmp_path):
    disc_image(tmp_path / "disc.png")
    script = tmp_path / "s.md"
    script.write_text("---\nsize: 320x180\n---\n\n![panzoom right](disc.png)\n\n```\nStill text\n```\n\n(duration: 1)\n")
    result = Builder(parse_file(script), SilentSynth(), log=lambda _: None).build(tmp_path / "out.mp4")
    assert result.duration == pytest.approx(1.0, abs=1 / 30)
    assert "pan/zoom" not in " ".join(result.notes)
    assert media.probe(result.video).width == 320
