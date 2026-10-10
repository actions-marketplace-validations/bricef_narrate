"""narrate studio in a real browser (#51): edit, save, and follow edits made elsewhere."""

import contextlib
import re
import threading
import time
from pathlib import Path

import httpx2
import pytest
from playwright.sync_api import expect, sync_playwright

from narrate.studio.server import create_app
from narrate.studio.server import server as studio_server


@pytest.fixture
def studio(tmp_path):
    script = tmp_path / "s.md"
    script.write_text("---\nvoice: Amy\n---\n\n![](photo.jpg)\n\nHello there.\n")
    server = studio_server(create_app(script), "127.0.0.1", 0)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started:
        assert time.monotonic() < deadline, "the studio didn't start"
        time.sleep(0.05)
    port = server.servers[0].sockets[0].getsockname()[1]
    yield script, f"http://127.0.0.1:{port}/"
    server.end_streams()
    server.should_exit = True
    thread.join(5)
    assert not thread.is_alive()


@pytest.fixture
def page():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        yield browser.new_page()
        browser.close()


def wait_for(condition, seconds: float = 5.0):
    deadline = time.monotonic() + seconds
    while not condition():
        assert time.monotonic() < deadline
        time.sleep(0.05)


def test_edit_save_and_follow_outside_edits(studio, page):
    script, url = studio
    page.goto(url)
    content = page.locator(".cm-content")
    expect(content).to_contain_text("Hello there.")
    expect(page.locator(".cm-narrate-header").first).to_be_visible()  # narrate's own highlighting
    expect(page.locator(".cm-narrate-media")).to_have_count(1)
    expect(page.get_by_test_id("status")).to_have_text("Saved")

    page.get_by_text("Hello there.").click()
    page.keyboard.press("End")
    page.keyboard.type(" Welcome.")
    expect(page.get_by_test_id("status")).to_have_text("Unsaved changes")
    page.keyboard.press("Control+s")
    expect(page.get_by_test_id("status")).to_have_text("Saved")
    wait_for(lambda: "Hello there. Welcome." in script.read_text())

    script.write_text(script.read_text().replace("Welcome.", "Edited in another editor."))
    expect(content).to_contain_text("Edited in another editor.")  # reloaded quietly: nothing unsaved
    expect(page.get_by_test_id("status")).to_have_text("Saved")


def test_an_outside_edit_with_unsaved_changes_asks(studio, page):
    script, url = studio
    page.goto(url)
    expect(page.locator(".cm-content")).to_contain_text("Hello there.")
    page.get_by_text("Hello there.").click()
    page.keyboard.type("Mine. ")
    script.write_text(script.read_text() + "\nTheirs.\n")
    expect(page.get_by_role("alert")).to_contain_text("changed on disk")
    page.get_by_role("button", name="Keep mine (overwrite the file)").click()
    wait_for(lambda: "Mine." in script.read_text() and "Theirs." not in script.read_text())
    expect(page.get_by_test_id("status")).to_have_text("Saved")


def test_a_refused_save_offers_to_overwrite(studio, page):
    script, url = studio
    page.goto(url)
    expect(page.locator(".cm-content")).to_contain_text("Hello there.")
    page.get_by_text("Hello there.").click()
    page.keyboard.type("Mine. ")
    # Changed on disk, and saved before the watcher's next look: the server refuses the save
    script.write_text(script.read_text() + "\nTheirs.\n")
    page.evaluate("document.activeElement.blur()")
    page.keyboard.press("Control+s")  # works away from the editor too
    alert = page.get_by_role("alert")
    expect(alert).to_contain_text("changed on disk")
    if "wasn't saved" in alert.inner_text():
        page.get_by_role("button", name="Keep mine and save").click()
    else:  # the watcher got there first
        page.get_by_role("button", name="Keep mine (overwrite the file)").click()
    wait_for(lambda: "Mine." in script.read_text() and "Theirs." not in script.read_text())


def test_the_event_stream_announces_outside_edits(studio):
    script, url = studio
    with httpx2.stream("GET", url + "api/events", timeout=5) as stream:
        lines = stream.iter_lines()
        assert next(lines) == "event: hello"
        next(lines), next(lines)  # its data, and the blank line ending the event
        script.write_text("Changed.\n")
        assert next(lines) == "event: script-changed"
        assert '"type": "script-changed"' in next(lines)


# -- live analysis (#52) ------------------------------------------------------------

def test_scenes_timing_and_problems_follow_the_text(tmp_path, page):
    from narrate.studio.server import create_app as make

    (tmp_path / "photo.jpg").write_bytes(b"")  # exists; the analysis only checks for the file
    script = tmp_path / "s.md"
    script.write_text("![](photo.jpg)\n\nThe first scene.\n\n---\n\nThe second scene, a little longer.\n")
    server = studio_server(make(script, "silent"), "127.0.0.1", 0)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    while not server.started:
        time.sleep(0.05)
    try:
        page.goto(f"http://127.0.0.1:{server.servers[0].sockets[0].getsockname()[1]}/")
        outline = page.get_by_role("navigation", name="scenes")
        expect(outline.locator("li")).to_have_count(2)
        expect(outline).to_contain_text("photo.jpg")
        expect(page.locator(".cm-narrate-scene-label")).to_have_count(2)
        expect(page.locator(".cm-narrate-length")).to_have_count(2)
        total = page.get_by_test_id("total").inner_text()

        page.locator(".cm-line:not(.cm-narrate-scene)", has_text="The second scene").click(position={"x": 4, "y": 4})
        page.keyboard.press("End")
        page.keyboard.type(" And now it goes on for quite a while longer than it did before.")
        expect(page.get_by_test_id("total")).not_to_have_text(total)  # re-timed as you type
        expect(outline.locator("li.current")).to_contain_text("2")  # the scene with the cursor

        page.keyboard.press("Enter")
        page.keyboard.press("Enter")
        page.keyboard.type("![](nowhere.png)")
        expect(page.locator(".cm-lint-marker-error")).to_have_count(1)  # the missing file, in the gutter
        expect(outline).to_contain_text("1 problem to fix")  # once, though the scene can't find its picture
        expect(outline.locator("li").nth(1)).to_contain_text("nowhere.png")
        expect(outline.locator("li").nth(1)).not_to_contain_text("?")  # still timed, with a stand-in

        outline.locator("li").first.get_by_role("button").click()
        expect(outline.locator("li.current")).to_contain_text("1")  # the cursor jumped to scene 1
    finally:
        server.end_streams()
        server.should_exit = True
        thread.join(5)


# -- frame preview (#53) --------------------------------------------------------------

def test_the_preview_follows_the_cursor(tmp_path, page):
    from PIL import Image

    from narrate.studio.server import create_app as make

    for name, colour in (("red.png", "red"), ("blue.png", "blue")):
        Image.new("RGB", (640, 360), colour).save(tmp_path / name)
    script = tmp_path / "s.md"
    script.write_text("![](red.png)\n\nThe red scene.\n\n---\n\n![](blue.png)\n\nThe blue scene.\n")
    server = studio_server(make(script, "silent"), "127.0.0.1", 0)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    while not server.started:
        time.sleep(0.05)
    try:
        page.goto(f"http://127.0.0.1:{server.servers[0].sockets[0].getsockname()[1]}/")
        picture = page.frame_locator("iframe[title=frame]").locator("img.media")
        expect(picture).to_have_attribute("src", "/files/red.png")
        page.locator(".cm-line:not(.cm-narrate-scene)", has_text="The blue scene").click(position={"x": 4, "y": 4})
        expect(picture).to_have_attribute("src", "/files/blue.png")
        expect(page.get_by_test_id("moment")).to_contain_text("scene 2")
    finally:
        server.end_streams()
        server.should_exit = True
        thread.join(5)


# -- narration playback (#54) ------------------------------------------------------------

def test_a_paragraph_plays_from_its_button(tmp_path, page):
    from narrate.studio.server import create_app as make

    script = tmp_path / "s.md"
    script.write_text("A first paragraph, long enough to take a few seconds to read aloud.\n\n"
                      "And a second one, which also takes a little while to say.\n")
    server = studio_server(make(script, "silent"), "127.0.0.1", 0)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    while not server.started:
        time.sleep(0.05)
    try:
        page.goto(f"http://127.0.0.1:{server.servers[0].sockets[0].getsockname()[1]}/")
        buttons = page.locator(".cm-narrate-length[role=button]")
        expect(buttons).to_have_count(2)
        buttons.nth(1).dispatch_event("mousedown")
        expect(page.get_by_test_id("playback")).to_contain_text("Playing scene 1")
        page.get_by_role("button", name="■ Stop").click()
        expect(page.get_by_role("button", name="▶ Play scene")).to_be_visible()
        expect(page.get_by_label("speech engine")).to_have_value("silent")
    finally:
        server.end_streams()
        server.should_exit = True
        thread.join(5)


# -- builds (#55) ----------------------------------------------------------------------

def test_build_and_watch(tmp_path, page, monkeypatch):
    from narrate.studio.server import create_app as make

    monkeypatch.setenv("NARRATE_CACHE", str(tmp_path / "cache"))
    script = tmp_path / "s.md"
    script.write_text("---\nsize: 320x180\n---\n\nBuilt from the studio.\n")
    server = studio_server(make(script, "silent"), "127.0.0.1", 0)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    while not server.started:
        time.sleep(0.05)
    try:
        page.goto(f"http://127.0.0.1:{server.servers[0].sockets[0].getsockname()[1]}/")
        expect(page.locator(".cm-content")).to_contain_text("Built from the studio.")
        page.get_by_text("Built from the studio.").first.click()
        page.keyboard.press("End")
        page.keyboard.type(" Edited first.")
        page.get_by_role("button", name="Build video").click()
        video = page.get_by_test_id("video")
        expect(video).to_be_visible(timeout=60000)  # the Video tab opens when it's done
        assert "Edited first." in script.read_text()  # the build saved the script first
        assert script.with_suffix(".mp4").exists()
        expect(page.get_by_test_id("build")).to_contain_text("Built")
    finally:
        server.end_streams()
        server.should_exit = True
        thread.join(5)


# -- timeline (#60) ---------------------------------------------------------------------

@contextlib.contextmanager
def running(script: Path, engine: str = "silent"):
    """The studio on `script`, serving at the URL it yields."""
    server = studio_server(create_app(script, engine), "127.0.0.1", 0)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    while not server.started:
        time.sleep(0.05)
    try:
        yield f"http://127.0.0.1:{server.servers[0].sockets[0].getsockname()[1]}/"
    finally:
        server.end_streams()
        server.should_exit = True
        thread.join(5)


def test_the_timeline_seeks_and_follows_the_cursor(tmp_path, page):
    script = tmp_path / "s.md"
    text = ("A first paragraph, long enough to take a few seconds.\n\nA second paragraph.\n\n---\n\n"
            "The second scene, which is a good deal longer than either paragraph of the first scene.\n")
    script.write_text(text)
    with running(script) as url:
        report = httpx2.post(url + "api/analyse", json={"text": text}).json()
        one, two = report["scenes"]
        page.goto(url)
        scenes = page.locator(".tl-scene")
        expect(scenes).to_have_count(2)
        widths = [scenes.nth(k).bounding_box()["width"] for k in (0, 1)]
        assert widths[0] / widths[1] == pytest.approx(one["duration"] / two["duration"], rel=0.02)

        # Clicking in the second scene shows that moment, with the cursor on the paragraph playing then
        box = scenes.nth(1).bounding_box()
        page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] - 10)
        expect(page.get_by_test_id("moment")).to_contain_text("scene 2")
        expect(page.locator(".cm-activeLine")).to_contain_text("The second scene")
        at = page.get_by_test_id("playhead").inner_text()
        page.keyboard.press("Shift+ArrowRight")  # a second later
        expect(page.get_by_test_id("playhead")).not_to_have_text(at)

        # Moving the cursor moves the playhead to that paragraph
        page.locator(".cm-line:not(.cm-narrate-scene)", has_text="A second paragraph").click(position={"x": 4, "y": 4})
        start = one["paragraphs"][1]["start"]
        expect(page.get_by_test_id("playhead")).to_have_text(f"{start:.1f} s / {report['duration']:.1f} s")
        expect(page.get_by_test_id("moment")).to_contain_text("scene 1")


# -- scene renders (#61) ----------------------------------------------------------------

def test_render_the_scene_at_the_cursor(tmp_path, page, monkeypatch):
    monkeypatch.setenv("NARRATE_CACHE", str(tmp_path / "cache"))
    script = tmp_path / "s.md"
    script.write_text("---\nsize: 320x180\n---\n\nThe first scene.\n\n---\n\nThe second scene.\n")
    with running(script) as url:
        page.goto(url)
        page.locator(".cm-line:not(.cm-narrate-scene)", has_text="The second scene").click(position={"x": 4, "y": 4})
        expect(page.get_by_test_id("moment")).to_contain_text("scene 2")
        page.get_by_role("button", name="Render scene").click()
        expect(page.get_by_test_id("scene-video")).to_be_visible(timeout=60000)
        expect(page.get_by_test_id("scene-render")).to_contain_text("Scene 2, rendered")
        assert page.get_by_test_id("scene-video").get_attribute("src").startswith("/scratch/scene-2-")


# -- picture inspector (#62) --------------------------------------------------------------

def test_the_inspector_edits_the_picture_at_the_cursor(tmp_path, page):
    from PIL import Image

    Image.new("RGB", (900, 180), "teal").save(tmp_path / "wide.png")  # wider than the frame: room to move sideways
    script = tmp_path / "s.md"
    script.write_text("---\nsize: 320x180\n---\n\n![](wide.png)\n\nA picture, framed from the studio.\n")
    with running(script) as url:
        page.goto(url)
        picture_line = page.locator(".cm-narrate-media")
        picture_line.click(position={"x": 4, "y": 4})
        inspector = page.get_by_test_id("inspector")
        expect(inspector).to_contain_text("wide.png")

        inspector.get_by_role("button", name="contain").click()
        expect(picture_line).to_have_text("![contain](wide.png)")
        inspector.get_by_role("button", name="cover").click()  # the default: the token goes again
        expect(picture_line).to_have_text("![](wide.png)")
        inspector.get_by_label("motion").select_option("panzoom")
        expect(picture_line).to_have_text("![panzoom](wide.png)")
        expect(inspector.locator(".windows svg rect")).to_have_count(2)  # the first and last windows
        expect(page.locator(".tl-visual.picture").first).to_have_attribute("title", re.compile("panzoom"))
        inspector.get_by_label("motion").select_option("")
        expect(picture_line).to_have_text("![](wide.png)")

        # Dragging the picture to the right shows its left side
        surface = page.get_by_test_id("drag-surface")
        box = surface.bounding_box()
        page.mouse.move(box["x"] + box["width"] * 0.5, box["y"] + box["height"] * 0.5)
        page.mouse.down()
        page.mouse.move(box["x"] + box["width"] * 0.85, box["y"] + box["height"] * 0.5, steps=5)
        expect(page.locator(".drag-hint")).to_have_text("left")
        page.mouse.up()
        expect(picture_line).to_have_text("![left](wide.png)")
        expect(page.frame_locator("iframe[title=frame]").locator("img.media")).to_have_css("object-position", re.compile(r"^0(px|%) 50%$"))

        page.locator(".cm-content").focus()
        page.keyboard.press("Control+z")
        expect(picture_line).to_have_text("![](wide.png)")  # each change is one undo
