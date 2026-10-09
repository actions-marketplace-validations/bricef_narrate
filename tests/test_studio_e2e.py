"""narrate studio in a real browser (#51): edit, save, and follow edits made elsewhere."""

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
