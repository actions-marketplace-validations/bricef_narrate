"""The callout designer's directions land where they were drawn (narrate #29)."""

import numpy as np
import pytest
from PIL import Image

from narrate import media
from narrate.build import Builder
from narrate.designer import designer_page
from narrate.script import parse_file
from narrate.tts import SilentSynth


@pytest.fixture
def draw(tmp_path):
    """Draw on the designer page in a browser; return the direction it prints."""
    Image.new("RGB", (1280, 720), (128, 128, 128)).save(tmp_path / "grey.png")
    html = designer_page(tmp_path / "grey.png", tmp_path / "designer.html", width=1280, height=720)

    def run(start, end, rectangle=False):
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch()
            tab = browser.new_page(viewport={"width": 900, "height": 900})
            tab.goto(html.as_uri())
            if rectangle:
                tab.check("input[value=rectangle]")

            def screen(x, y):
                return tab.evaluate("""([x, y]) => { const svg = document.getElementById('svg');
                    const p = svg.createSVGPoint(); p.x = x; p.y = y;
                    const q = p.matrixTransform(svg.getScreenCTM()); return [q.x, q.y]; }""", [x, y])

            tab.mouse.move(*screen(*start))
            tab.mouse.down()
            tab.mouse.move(*screen(*end), steps=8)
            tab.mouse.up()
            direction = tab.input_value("#out")
            browser.close()
        return direction

    return run


def rendered(tmp_path, direction):
    script = tmp_path / "s.md"
    script.write_text(f"---\nsize: 720p\n---\n\n![](grey.png)\n\n{direction}\n\n(duration: 1)\n")
    video = Builder(parse_file(script), SilentSynth(), log=lambda _: None).build(tmp_path / "out.mp4").video
    media.extract_frame(video, 0.5, tmp_path / "frame.png")
    return np.asarray(Image.open(tmp_path / "frame.png").convert("L"), dtype=float)


def test_a_drawn_circle_lands_on_the_same_spot(draw, tmp_path):
    direction = draw((400, 300), (550, 300))
    assert "cx: 400" in direction and "cy: 300" in direction and "size: 150" in direction
    frame = rendered(tmp_path, direction)
    assert frame[300, 400] == pytest.approx(128, abs=8)   # centre: not shaded
    assert frame[300, 535] == pytest.approx(128, abs=8)   # just inside the edge
    assert frame[300, 570] == pytest.approx(64, abs=8)    # just outside: shaded by half


def test_a_drawn_rectangle_lands_on_the_same_spot(draw, tmp_path):
    direction = draw((100, 100), (500, 260), rectangle=True)
    assert "type: rectangle" in direction and "left: 100" in direction and "bottom: 260" in direction
    frame = rendered(tmp_path, direction)
    assert frame[180, 300] == pytest.approx(128, abs=8)
    assert frame[280, 300] == pytest.approx(64, abs=8)
