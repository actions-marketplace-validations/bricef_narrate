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


# -- zoom amount (#49) -------------------------------------------------------------

def test_a_zoom_amount_replaces_the_defaults():
    start, end = endpoints("zoom", "center", 2560, 1440, 1280, 720, zoom=1.12)
    assert end[2] == pytest.approx(start[2] / 1.12)
    _, panned = endpoints("pan", "left", 2560, 1440, 1280, 720, zoom=1.05)
    assert panned[2] == pytest.approx(2560 / 1.05)


def test_frames_end_on_the_centre_of_the_zoom(tmp_path):
    # Concentric rings: the last frame of a 1.12 zoom shows the centre 1/1.12 of the picture
    image = Image.new("RGB", (640, 360), "black")
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 639, 359), outline="white", width=30)  # cropped away by any zoom past 1.1
    draw.rectangle((36, 30, 603, 329), outline="grey", width=10)  # inside 1.12's crop, outside 1.25's

    def last(zoom):
        image = list(frames(tmp_path / "rings.png", "zoom", "center", 320, 180, 10, zoom=zoom))[-1]
        return np.frombuffer(image, dtype=np.uint8).reshape(180, 320, 3)

    image.save(tmp_path / "rings.png")
    near, default = last(1.12), last(None)
    assert near[90, 0].max() < 60 and 100 < near[90, 1:8].max() < 160  # white gone, grey band at the edge
    assert default[90, :20].max() < 60  # the default 1.25 crops the band too
    first = np.frombuffer(next(frames(tmp_path / "rings.png", "zoom", "center", 320, 180, 10, zoom=1.12)),
                          dtype=np.uint8).reshape(180, 320, 3)
    assert first[90, 0].mean() > 200  # but shows at the start


def test_pictures_and_the_header_set_the_zoom(tmp_path):
    Image.new("RGB", (640, 360), "steelblue").save(tmp_path / "p.png")
    script = tmp_path / "s.md"
    script.write_text("---\nimage-zoom: 1.1\n---\n\n![zoom](p.png)\n\n(image: {file: p.png, size: zoom, zoom: 1.3})\n\n"
                      "![](p.png)\n\nNarration.\n")
    plan = next(Builder(parse_file(script), SilentSynth(), log=lambda _: None).plans(parse_file(script).scenes, tmp_path))
    assert [v.zoom for v in plan.visuals] == [1.1, 1.3, None]  # header default, the picture's own, no motion
