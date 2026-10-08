"""Slide geometry measured against Narakeet's slides render (spec §17, narrate #20)."""

import numpy as np
import pytest
from PIL import Image

from narrate.frames import FrameRenderer, FrameSpec, SlideSpec


def bands(png, threshold=128):
    dark = np.asarray(Image.open(png).convert("L"), dtype=int) < threshold
    rows, start = [], None
    for y, any_dark in enumerate(dark.any(axis=1)):
        if any_dark and start is None:
            start = y
        elif not any_dark and start is not None:
            rows.append((start, y - start))
            start = None
    return rows


@pytest.fixture(scope="module")
def frames(tmp_path_factory):
    out = tmp_path_factory.mktemp("look")
    slides = {
        "plain": SlideSpec("", "Hi there!"),
        "md": SlideSpec("md", "# Heading 1\n## Heading 2\n\n* bullets are left-aligned\n* bullet 2\n  * sub-bullet"),
        "code": SlideSpec("css", ".container {\n  align-items: center;\n  display: flex;\n}"),
    }
    with FrameRenderer(1280, 720, out) as renderer:
        return {name: renderer.render(FrameSpec(slide=slide), out / f"{name}.png") for name, slide in slides.items()}


def test_plain_slide_is_bold_and_twice_the_base_size(frames):
    ((top, height),) = bands(frames["plain"])
    assert height == pytest.approx(73, rel=0.12)  # Narakeet: 73 px for "Hi there!"
    assert top + height / 2 == pytest.approx(360, abs=15)


def test_markdown_slide_matches_narakeet_lines(frames):
    lines = bands(frames["md"])
    assert len(lines) == 5  # H1, H2, two bullets and the nested sub-bullet on its own line
    assert lines[0][1] == pytest.approx(93, rel=0.15) and lines[1][1] == pytest.approx(70, rel=0.15)


def test_code_slide_uses_a_one_em_monospace(frames):
    lines = bands(frames["code"], threshold=160)
    pitches = [b[0] - a[0] for a, b in zip(lines, lines[1:])]
    assert np.median(pitches) == pytest.approx(57, abs=5)  # Narakeet: 57 px line pitch
