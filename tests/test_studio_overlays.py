"""Overlays in the studio's preview (#74): pages laid over the frame as a build lays them, each on its own clock."""

import io
import json
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import parse_qs, urlsplit

import numpy as np
import pytest
from PIL import Image
from playwright.sync_api import expect, sync_playwright

from narrate import media
from narrate.build import Builder
from narrate.script import parse
from narrate.studio.analysis import run
from narrate.studio.preview import Files, frame
from narrate.tts import SilentSynth

from test_studio_e2e import running

# A box sliding right at 100 px a second, on the page's clock; a still magenta block in the bottom-left corner
SLIDER = """<!doctype html><style>html,body{margin:0;width:100%;height:100%}
#box{position:absolute;top:20px;left:0;width:20px;height:20px;background:#00ff00;animation:go 3s linear forwards}
@keyframes go{to{left:300px}}</style><div id="box"></div>"""
STILL = """<!doctype html><style>html,body{margin:0;width:100%;height:100%}
.s{position:absolute;left:0;bottom:0;width:40px;height:20px;background:#ff00ff}</style><div class="s"></div>"""

SCRIPT = ("---\nsize: 320x180\noverlay: slider.html\n---\n\n![](red.png)\n\n(overlay: still.html)\n\n(duration: 1)\n\n"
          "---\n\n![](blue.png)\n\n(duration: 1)\n\n---\n\n(overlay: none)\n\n![](grey.png)\n\n(duration: 1)\n")


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.setenv("NARRATE_CACHE", str(tmp_path / "cache"))
    for name, colour in (("red.png", "red"), ("blue.png", "blue"), ("grey.png", "grey")):
        Image.new("RGB", (640, 360), colour).save(tmp_path / name)
    (tmp_path / "slider.html").write_text(SLIDER)
    (tmp_path / "still.html").write_text(STILL)
    (tmp_path / "scratch").mkdir()
    return tmp_path


def overlays(project, text: str, scene: int, t: float) -> tuple[list[dict], object]:
    analysis = run(text, project / "s.md", SilentSynth())
    shown = frame(analysis.plans[scene], t, analysis.settings, Files(project, project / "scratch"), analysis.plans)
    return shown["overlays"], analysis


def narration(overlay: dict) -> dict:
    return json.loads(parse_qs(urlsplit(overlay["url"]).query)["narrate"][0])


def test_the_scenes_overlays_then_the_videos_each_on_its_clock(project):
    text = ("---\nsize: 320x180\noverlay: slider.html\n---\n\n![](red.png)\n\n(duration: 1.5)\n\n---\n\n![](blue.png)\n\n"
            "(overlay: {file: still.html, viewport: 640x640, colour: blue})\n\nA few words to speak.\n")
    [own, video], analysis = overlays(project, text, 2, 0.4)
    assert own["url"].startswith("/pages/still.html?") and video["url"].startswith("/pages/slider.html?")
    # The scene's: its clock, cues and parameters, laid out at its viewport and centred
    assert (own["start"], own["time"]) == (0.0, 0.4)
    assert narration(own)["cues"] == pytest.approx(analysis.plans[2].marks, abs=1e-3)
    assert narration(own)["params"] == {"colour": "blue"}
    assert own["size"] == [640, 640] and own["box"] == {"left": 70.0, "top": 0.0, "scale_x": 180 / 640, "scale_y": 180 / 640}
    # The video's: the whole video's clock, with each scene's start, on whole frames
    assert video["start"] == -1.5 and video["time"] == pytest.approx(1.9)
    told = narration(video)
    assert [s["start"] for s in told["scenes"]] == [0.0, 1.5] and told["cues"] == {}
    assert told["duration"] == pytest.approx(1.5 + analysis.plans[2].duration, abs=1 / 30)
    assert video["box"] == {"left": 0.0, "top": 0.0, "scale_x": 1.0, "scale_y": 1.0}
    # Its address is the same in every scene, so the page runs on through the cut
    assert overlays(project, text, 1, 0.2)[0][0]["url"] == video["url"]


def test_overlays_a_scene_leaves_out(project):
    text = ("---\nsize: 320x180\noverlay: [{file: slider.html, scenes: 2}, still.html]\n---\n\n![](red.png)\n\n"
            "(overlay: gone.html)\n\n(duration: 1)\n\n---\n\n![](blue.png)\n\n(duration: 1)\n\n---\n\n"
            "(overlay: none)\n\n![](grey.png)\n\n(duration: 1)\n")
    pages = lambda scene: [urlsplit(o["url"]).path for o in overlays(project, text, scene, 0.5)[0]]  # noqa: E731
    assert pages(1) == ["/pages/still.html"]  # a missing page is left out; the slider covers scene 2 only
    assert pages(2) == ["/pages/slider.html", "/pages/still.html"]
    assert pages(3) == []  # (overlay: none)


# -- in the browser, against a build ---------------------------------------------------------------

@pytest.fixture
def dark_page():
    """The studio in its dark colour scheme, where a transparent page could be painted opaque."""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        yield browser.new_page(color_scheme="dark")
        browser.close()


def green_left(pixels) -> int | None:
    green = np.where((pixels[30, :, 1] > 200) & (pixels[30, :, 0] < 80) & (pixels[30, :, 2] < 80))[0]
    return int(green[0]) if len(green) else None


def screen(page) -> np.ndarray:
    """The preview's frame, scaled back to the video's 320×180."""
    png = page.locator(".preview .screen").screenshot()
    return np.asarray(Image.open(io.BytesIO(png)).convert("RGB").resize((320, 180)), dtype=int)


def test_overlays_lie_over_the_preview_as_over_the_video(project, dark_page):
    page = dark_page
    script = project / "s.md"
    script.write_text(SCRIPT)
    with ThreadPoolExecutor(1) as pool:  # a build of its own, beside the browser driving the studio
        video = pool.submit(lambda: Builder(parse(SCRIPT, script), SilentSynth()).build(project / "out.mp4")).result().video

    def built(frame_index: int) -> np.ndarray:
        out = project / f"built-{frame_index}.png"
        media.extract_frame(video, (frame_index - 0.25) / 30, out)
        return np.asarray(Image.open(out).convert("RGB"), dtype=int)

    with running(script) as url:
        page.goto(url)
        expect(page.locator(".tl-scene")).to_have_count(3)
        page.locator(".tl-scene").first.click()
        page.keyboard.press("Home")
        layers = page.get_by_test_id("overlay")
        expect(layers).to_have_count(2)  # the scene's, then the video's
        expect(page.frame_locator("iframe[title=overlay] >> nth=1").locator("html")).to_have_attribute(
            "data-narrate-frame", "0")
        pixels = screen(page)
        assert tuple(pixels[90, 160]) == pytest.approx((255, 0, 0), abs=60)  # the picture shows through
        assert tuple(pixels[172, 12]) == pytest.approx((255, 0, 255), abs=60)  # the scene's overlay
        assert tuple(pixels[30, 8]) == pytest.approx((0, 255, 0), abs=60)  # the video's, at its start
        slider = next(f for f in page.frames if "/pages/slider.html" in f.url)
        slider.evaluate("window.__stillHere = true")

        def at(frame_index: int):
            expect(page.frame_locator("iframe[title=overlay]").locator("html")).to_have_attribute(
                "data-narrate-frame", str(frame_index))
            left = slider.evaluate("document.getElementById('box').getBoundingClientRect().left")
            assert left == pytest.approx(green_left(built(frame_index)), abs=2), frame_index

        # The next scene: the scene's overlay has gone, the video's runs on, on the video's clock
        page.keyboard.press("Shift+ArrowRight")
        expect(page.get_by_test_id("moment")).to_contain_text("scene 2")
        expect(layers).to_have_count(1)
        at(30)
        for _ in range(15):
            page.keyboard.press("ArrowRight")
        at(45)
        assert slider.evaluate("window.__stillHere === true")  # the same page all along, not reloaded
        assert tuple(screen(page)[90, 160]) == pytest.approx((0, 0, 255), abs=60)

        # (overlay: none) hides the video's overlay
        page.keyboard.press("Shift+ArrowRight")
        expect(page.get_by_test_id("moment")).to_contain_text("scene 3")
        expect(layers).to_have_count(0)
