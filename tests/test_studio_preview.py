"""The studio's frame preview (#53): the frame at a moment, composed like a build's."""

import re
from pathlib import Path

import numpy as np
import pytest
from PIL import Image
from starlette.testclient import TestClient

from narrate import media, motion, render
from narrate.studio.analysis import run
from narrate.studio.preview import Files, frame
from narrate.studio.server import create_app
from narrate.tts import SilentSynth


@pytest.fixture
def project(tmp_path):
    for name, colour in (("red.png", "red"), ("blue.png", "blue")):
        Image.new("RGB", (640, 360), colour).save(tmp_path / name)
    media.run(["-f", "lavfi", "-i", "testsrc2=size=320x180:rate=30", "-t", "4", "-c:v", "libx264", "-pix_fmt",
               "yuv420p", str(tmp_path / "clip.mp4")])
    (tmp_path / "scene.html").write_text("<!doctype html><p>page</p>")
    return tmp_path


def shown(project: Path, text: str, scene: int, t: float, monkeypatch=None) -> dict:
    script = project / "s.md"
    analysis = run(text, script, SilentSynth())
    scratch = project / "scratch"
    scratch.mkdir(exist_ok=True)
    return frame(analysis.plans[scene], t, analysis.settings, Files(project, scratch))


def sources(page: dict) -> list[str]:
    return re.findall(r'src="([^"]+)"', page.get("html", ""))


def test_pictures_take_their_turns(project):
    text = "---\nsize: 320x180\n---\n\n![](red.png)\n\n![](blue.png)\n\n(duration: 2)\n"
    assert sources(shown(project, text, 1, 0.5)) == ["/files/red.png"]
    assert sources(shown(project, text, 1, 1.5)) == ["/files/blue.png"]


def test_slides_share_the_scene(project):
    text = "---\nsize: 320x180\n---\n\n```\nFirst\n```\n\n```\nSecond\n```\n\n(duration: 2)\n"
    assert "First" in shown(project, text, 1, 0.5)["html"] and "Second" in shown(project, text, 1, 1.5)["html"]


def test_a_clip_shows_its_frame_at_that_moment(project):
    page = shown(project, "---\nsize: 320x180\n---\n\n![](clip.mp4)\n", 1, 2.0)
    [still] = sources(page)
    assert still.startswith("/scratch/clip-")
    ours = np.asarray(Image.open(project / "scratch" / still.removeprefix("/scratch/")).convert("L"), dtype=float)
    media.extract_frame(project / "clip.mp4", 2.0, project / "expected.png")
    expected = np.asarray(Image.open(project / "expected.png").convert("L"), dtype=float)
    assert np.abs(ours - expected).mean() < 2


def test_a_zoom_shows_the_crop_it_has_reached(project):
    text = "---\nsize: 320x180\n---\n\n![zoom](red.png)\n\n(duration: 2)\n"
    start, end = motion.endpoints("zoom", "center", 640, 360, 320, 180)
    for t, rect in ((0.0, start), (2 - 1 / 30, end)):
        width = re.search(r"img\.media \{[^}]*width: ([\d.]+)px", shown(project, text, 1, t)["html"]).group(1)
        assert float(width) == pytest.approx(640 * 320 / rect[2], rel=0.02)  # image scaled so the window fills 320


def test_html_scenes_show_the_page_itself(project):
    assert shown(project, "![](scene.html)\n\n(duration: 1)\n", 1, 0.5) == {"kind": "page", "url": "/files/scene.html"}


def test_render_blocks_show_what_a_build_made(project, monkeypatch, tmp_path_factory):
    monkeypatch.setenv("NARRATE_CACHE", str(tmp_path_factory.mktemp("cache")))  # outside the project, as usual
    placeholder = shown(project, "```render:placeholder\nProduct shot\n```\n", 1, 0.5)
    assert "Product shot" in placeholder["html"]  # the card itself, drawn without a build
    text = "---\nsize: 320x180\n---\n\n```render:mermaid\nflowchart LR\n  A --> B\n```\n"
    assert "drawn when the video is built" in shown(project, text, 1, 0.5)["html"]
    # Once a build has drawn it, the preview shows the drawing
    from narrate.script import Render
    made = render.location(Render("mermaid", "flowchart LR\n  A --> B", {}),
                           render.Context(320, 180, "default", None, project=project))
    made.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (640, 360), "green").save(made)
    [image] = sources(shown(project, text, 1, 0.5))
    assert image.startswith("/scratch/")  # copied out of the cache to be served


def test_the_endpoint_needs_a_current_analysis(project):
    (project / "s.md").write_text("![](red.png)\n\n(duration: 1)\n")
    with TestClient(create_app(project / "s.md", "silent")) as client:
        stale = client.post("/api/frame", json={"id": "nothing", "scene": 1, "time": 0})
        assert stale.status_code == 409
        analysis = client.post("/api/analyse", json={"text": "![](clip.mp4)\n"}).json()
        page = client.post("/api/frame", json={"id": analysis["id"], "scene": 1, "time": 1.0}).json()
        [still] = sources(page)
        assert client.get(still).headers["content-type"] == "image/png"
        assert client.get("/scratch/../s.md").status_code == 404
