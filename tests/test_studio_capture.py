"""Retaking render:web captures from the studio (#77)."""

import functools
import http.server
import json
import re
import threading

import numpy as np
import pytest
from PIL import Image
from playwright.sync_api import expect

from narrate import render
from narrate.script import Render
from narrate.studio.analysis import run
from narrate.studio.preview import Files
from narrate.tts import SilentSynth

from test_studio_e2e import page, running, wait_for  # noqa: F401 - the browser fixture

PAGE = "<!doctype html><style>html, body {{ margin: 0; height: 100%; background: {} }}</style>"


@pytest.fixture
def site(tmp_path):
    """A local web page to capture, served over HTTP."""
    root = tmp_path / "site"
    root.mkdir()
    (root / "page.html").write_text(PAGE.format("#00ff00"))

    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=str(root)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield root / "page.html", f"http://127.0.0.1:{server.server_address[1]}/page.html"
    server.shutdown()


def script_for(url: str) -> str:
    return f"---\nsize: 320x180\n---\n\n```render:web\n{url}\n```\n\nA page.\n"


def test_the_analysis_says_whether_a_capture_is_kept_and_when_it_was_taken(tmp_path):
    url = "https://example.com/"
    capture = lambda: run(script_for(url), tmp_path / "s.md", SilentSynth()).report["media"]["5"]["capture"]  # noqa: E731
    assert capture() == {"url": url, "stored": False, "made": None}
    kept = render.location(Render("web", url, {}), render.Context(320, 180, "default", None, project=tmp_path))
    kept.parent.mkdir(parents=True)
    Image.new("RGB", (320, 180), "green").save(kept)
    assert capture() == {"url": url, "stored": True, "made": None}  # kept, though when isn't recorded
    kept.with_suffix(".json").write_text(json.dumps({"made": "2026-10-12T10:00:00+00:00"}))
    assert capture()["made"] == "2026-10-12T10:00:00+00:00"
    # A picture narrate draws afresh has no capture to retake
    assert run("```render:placeholder\nSoon\n```\n", tmp_path / "s.md", SilentSynth()).report["media"]["1"]["capture"] is None


def test_a_stored_output_is_addressed_by_its_version(tmp_path):
    kept = tmp_path / ".narrate" / "generated" / "web" / "x.png"
    kept.parent.mkdir(parents=True)
    kept.write_bytes(b"png")
    files = Files(tmp_path, tmp_path / "scratch", "k")
    assert re.fullmatch(r"/pages/k/\.narrate/generated/web/x\.png\?v=\d+", files.url(kept))
    (tmp_path / "photo.png").write_bytes(b"png")
    assert files.url(tmp_path / "photo.png") == "/pages/k/photo.png"


def colour_of(path) -> tuple[int, ...]:
    return tuple(int(v) for v in np.asarray(Image.open(path).convert("RGB"))[50, 50])


def test_capture_then_retake_a_web_page(tmp_path, site, page, monkeypatch):  # noqa: F811
    source, url = site
    monkeypatch.setenv("NARRATE_ALLOW_LOCAL_NETWORK", "1")  # the site is on this machine; the studio's builds inherit it
    project = tmp_path / "project"
    project.mkdir()
    script = project / "s.md"
    script.write_text(script_for(url))
    kept = render.location(Render("web", url, {}), render.Context(320, 180, "default", None, project=project))
    with running(script) as studio:
        page.goto(studio)
        page.locator(".cm-line", has_text="render:web").click()
        row = page.get_by_test_id("capture")
        expect(row).to_contain_text("not taken yet")
        expect(row).to_contain_text(url)
        row.get_by_role("button", name="Capture now").click()
        expect(page.get_by_test_id("scene-render")).to_contain_text("rendered", timeout=60000)
        assert colour_of(kept) == pytest.approx((0, 255, 0), abs=10)
        assert json.loads(kept.with_suffix(".json").read_text())["body"] == url
        page.get_by_role("tab", name="Frame").click()  # the render played in the Scene tab
        expect(row).to_contain_text("taken")
        shown = page.frame_locator("iframe[title=frame]").locator("img.media")
        expect(shown).to_have_attribute("src", re.compile(r"^/pages/[\w-]+/\.narrate/generated/web/.*\?v=\d+$"))
        first = shown.get_attribute("src")

        # The page changes: retaking replaces the capture, and the preview shows the new one
        source.write_text(PAGE.format("#0000ff"))
        row.get_by_role("button", name="Retake capture").click()
        wait_for(lambda: colour_of(kept) == pytest.approx((0, 0, 255), abs=10), 60)
        expect(page.get_by_test_id("scene-render")).to_contain_text("rendered", timeout=60000)
        page.get_by_role("tab", name="Frame").click()
        expect(shown).not_to_have_attribute("src", first)
        expect(row.get_by_role("button", name="Retake capture")).to_be_enabled()
