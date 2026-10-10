"""Free framing (#63): a focal point, and pan/zoom between any two windows."""

import numpy as np
import pytest
from PIL import Image

from narrate import media
from narrate.build import Builder
from narrate.motion import alignment, endpoints, window_rect
from narrate.script import parse
from narrate.tts import SilentSynth


def test_a_window_is_a_centre_and_a_zoom():
    rect, moved = window_rect((0.5, 0.5, 1.0), 2000, 1000, 1280, 720)
    assert rect == pytest.approx((111.11, 0, 1777.78, 1000), abs=0.01) and not moved  # the plain cover framing
    rect, moved = window_rect((0.25, 0.4, 2.0), 2000, 1000, 1280, 720)
    assert rect == pytest.approx((500 - 444.44, 400 - 250, 888.89, 500), abs=0.01) and not moved
    rect, moved = window_rect((0.98, 0.5, 2.0), 2000, 1000, 1280, 720)
    assert rect[0] + rect[2] == pytest.approx(2000) and moved  # moved in from past the edge


def test_windows_give_both_ends_outright():
    start, end = endpoints(None, "center", 2000, 1000, 1280, 720, windows=((0.25, 0.4, 2.0), (0.75, 0.6, 1.5)))
    assert start == pytest.approx(window_rect((0.25, 0.4, 2.0), 2000, 1000, 1280, 720)[0])
    assert end == pytest.approx(window_rect((0.75, 0.6, 1.5), 2000, 1000, 1280, 720)[0])
    start, end = endpoints(None, "center", 2000, 1000, 1280, 720, windows=(None, (0.75, 0.6, 1.5)))
    assert start == pytest.approx((111.11, 0, 1777.78, 1000), abs=0.01)  # left out: the plain framing


def test_a_focal_point_is_where_zoom_and_pan_head():
    # 4000x1000 into 16:9: room for the crop, and the zoom inside it, to centre on x = 2400
    start, end = endpoints("zoom", "center", 4000, 1000, 1280, 720, focus=(0.6, 0.5))
    assert start[0] + start[2] / 2 == pytest.approx(2400) and end[0] + end[2] / 2 == pytest.approx(2400)
    # Too near the edge to centre: as near as the picture, then the first window, allow
    start, end = endpoints("zoom", "center", 2000, 1000, 1280, 720, focus=(0.8, 0.3))
    assert start[0] + start[2] == pytest.approx(2000)
    assert end[0] + end[2] == pytest.approx(start[0] + start[2]) and end[1] == 0
    start, end = endpoints("pan", "center", 4000, 1000, 1280, 720, focus=(0.6, 0.5))
    assert end[0] + end[2] / 2 == pytest.approx(2400)  # a pan ends on it


def test_alignment_keeps_the_focal_point_central():
    # 4000x1000 into 16:9: a 1777.8-wide crop, centred on a point at 60% (x = 2400)
    ax, ay = alignment((0.6, 0.5), 4000, 1000, 1280, 720, "cover")
    assert ax * (4000 - 1777.78) + 1777.78 / 2 == pytest.approx(2400, abs=0.1) and ay == 0.5
    assert alignment((0.99, 0.5), 4000, 1000, 1280, 720, "cover")[0] == 1.0  # as far as the picture allows
    assert alignment((0.3, 0.7), 4000, 1000, 1280, 720, "contain") == (0.3, 0.7)


def test_the_script_says_it_in_percent():
    script = parse("(image:\n  file: a.png\n  position: 70% 25%\n  from: 50% 50%\n  to: 72% 30% 2.5)\n")
    block = script.scenes[0].blocks[0]
    assert block.focus == (0.7, 0.25) and block.position is None
    assert block.windows == ((0.5, 0.5, 1.0), (0.72, 0.3, 2.5))
    bad = parse("(image: {file: a.png, position: 120% 5%, to: 50% 50% 0.5})\n")
    assert bad.scenes[0].blocks[0].focus is None and bad.scenes[0].blocks[0].windows is None
    assert sum("ignored" in w for w in bad.warnings) == 2


@pytest.fixture
def picture(tmp_path):
    """A 1200x400 picture whose every column and row is its own colour, so crops can be told apart."""
    x, y = np.meshgrid(np.arange(1200), np.arange(400))
    Image.fromarray(np.stack([x * 255 // 1199, y * 255 // 399, (x // 30 % 2) * 255], -1).astype(np.uint8)).save(
        tmp_path / "wide.png")
    return tmp_path


def frames_of(project, text, *moments):
    script = parse(text, project / "s.md")
    result = Builder(script, SilentSynth(), log=lambda _: None).build(project / "out.mp4")
    out = []
    for k, t in enumerate(moments):
        media.extract_frame(result.video, min(t, result.duration - 1 / 30), project / f"f{k}.png")
        out.append(np.asarray(Image.open(project / f"f{k}.png").convert("RGB"), dtype=float))
    return result, out


def expected(project, rect, size=(320, 180)):
    x, y, w, h = rect
    with Image.open(project / "wide.png") as im:
        return np.asarray(im.convert("RGB").resize(size, Image.BICUBIC, box=(x, y, x + w, y + h)), dtype=float)


def test_a_still_is_cropped_around_its_focal_point(picture):
    _, [frame] = frames_of(picture, "---\nsize: 320x180\n---\n\n(image: {file: wide.png, position: 70% 50%})\n\n"
                                    "(duration: 1)\n", 0.5)
    cw = 400 * 16 / 9  # the crop's width in the picture
    x = 0.7 * 1200 - cw / 2
    assert np.abs(frame - expected(picture, (x, 0, cw, 400))).mean() < 6


def test_a_clip_is_cropped_around_its_focal_point(picture):
    media.run(["-loop", "1", "-i", str(picture / "wide.png"), "-t", "2", "-r", "30", "-pix_fmt", "yuv420p",
               "-c:v", "libx264", str(picture / "wide.mp4")])
    _, [frame] = frames_of(picture, "---\nsize: 320x180\n---\n\n(video: {file: wide.mp4, position: 30% 50%})\n", 0.5)
    cw = 400 * 16 / 9
    x = 0.3 * 1200 - cw / 2
    assert np.abs(frame - expected(picture, (x, 0, cw, 400))).mean() < 8


def test_a_picture_moves_between_its_windows(picture):
    text = ("---\nsize: 320x180\n---\n\n(image:\n  file: wide.png\n  from: 20% 50% 1.5\n  to: 80% 40% 2)\n\n"
            "(duration: 2)\n")
    result, (first, last) = frames_of(picture, text, 0, 2)
    for frame, window in ((first, (0.2, 0.5, 1.5)), (last, (0.8, 0.4, 2.0))):
        rect, _ = window_rect(window, 1200, 400, 320, 180)
        assert np.abs(frame - expected(picture, rect)).mean() < 6, window
    assert not any("moved in" in n for n in result.notes)


def test_a_window_past_the_edge_is_moved_in_with_a_note(picture):
    result, _ = frames_of(picture, "---\nsize: 320x180\n---\n\n(image: {file: wide.png, to: 99% 50% 2})\n\n"
                                   "(duration: 1)\n")
    assert any("moved in" in n for n in result.notes)
