"""A project's own pages can't act as the studio (#93, design D17). HTML scenes, overlays and slides
run sandboxed, each in an origin of its own: they can't change anything through the API or read its
answers, while the page's own files load as in a build."""

import json
import re
from urllib.parse import urlsplit

import httpx2
import pytest
from PIL import ImageFont
from playwright.sync_api import expect
from starlette.testclient import TestClient

from narrate.studio.server import create_app

from test_studio_e2e import page, running  # noqa: F401 - the browser fixture

# What a page from someone else's project might try, and what it reports: a change it can send
# without asking first is "sent" (it can't see the answer), one the browser must ask about first is
# "refused", and an answer it can read is "read …". `own` adds the page's own files.
PROBE = """(async () => {
  const sent = (url, options) => fetch(url, options).then((r) => r.type === "opaque" ? "sent" : `read ${r.status}`,
                                                           () => "refused");
  const read = (url) => fetch(url).then((r) => r.text()).then((t) => `read ${t.slice(0, 40)}`, () => "unreadable");
  const results = {
    save: await sent("/api/script", {method: "PUT", headers: {"Content-Type": "application/json"},
                                      body: JSON.stringify({text: "Taken.\\n", version: "any"})}),
    engine: await sent("/api/engine", {method: "POST", mode: "no-cors", body: JSON.stringify({engine: "kokoro"})}),
    audition: await sent("/api/voices/audition", {method: "POST", mode: "no-cors",
                                                  body: JSON.stringify({text: "Hi.", voice: "Amy"})}),
    build: await sent("/api/build", {method: "POST", mode: "no-cors"}),
    script: await read("/api/script"),
    voices: await read("/api/voices"),
    builds: await read("/api/build"),
    events: await new Promise((done) => {
      const stream = new EventSource("/api/events");
      stream.addEventListener("hello", () => { stream.close(); done("read"); });
      stream.onerror = () => { stream.close(); done("unreadable"); };
    }),
    app: window === parent ? null : (() => { try { return parent.document.title; } catch { return "unreadable"; } })(),
  };
  if (%(own)s) {
    results.data = await fetch("data.json").then((r) => r.json(), (e) => String(e));
    results.module = await import("./answer.js").then((m) => m.answer, (e) => String(e));
    results.font = await new FontFace("Probe", "url(probe.ttf)").load().then(() => "loaded", (e) => String(e));
  }
  document.documentElement.dataset.probe = JSON.stringify(results);
})();"""

PAGE = ("<!doctype html><html><head><title>probe</title></head><body><p>A page.</p>\n"
        f"<script>{PROBE % {'own': 'true'}}</script></body></html>")
REFUSED = {"save": "refused", "engine": "sent", "audition": "sent", "build": "sent", "script": "unreadable",
           "voices": "unreadable", "builds": "unreadable", "events": "unreadable", "app": "unreadable"}
OWN = {"data": {"answer": 42}, "module": 42, "font": "loaded"}
ANY = re.compile(".")
CHANGES = {"/api/engine", "/api/voices/audition", "/api/build"}  # the changes "sent": refused by the server


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.setenv("NARRATE_CACHE", str(tmp_path / "cache"))
    (tmp_path / "probe.html").write_text(PAGE)
    (tmp_path / "data.json").write_text('{"answer": 42}')
    (tmp_path / "answer.js").write_text("export const answer = 42;\n")
    (tmp_path / "probe.ttf").write_bytes(ImageFont.load_default(10).font_bytes)  # Pillow's own font
    (tmp_path / ".env").write_text("ELEVENLABS_API_KEY=sk_secret\n")
    return tmp_path


# -- what the studio sends ---------------------------------------------------------------------------

def test_project_files_are_sandboxed_and_only_the_preview_can_read_them(project):
    script = project / "s.md"
    script.write_text("![](probe.html)\n\nHello.\n")
    with TestClient(create_app(script, "silent", hosts=["testserver"])) as client:
        key = client.app.state.session.key
        page = client.get(f"/pages/{key}/probe.html")
        assert page.headers["content-security-policy"] == "sandbox allow-scripts"
        # Read by its sandbox, whose origin is "null"; the key keeps other sites' sandboxes out
        assert page.headers["access-control-allow-origin"] == "null" and "x-frame-options" not in page.headers
        assert client.get(f"/pages/{key}/data.json").headers["access-control-allow-origin"] == "null"
        for wrong in ("/pages/probe.html", "/pages/x/probe.html", f"/pages/{key[:-1]}/probe.html", f"/pages/{key}/.env",
                      f"/pages/{key}/..%2Fs.md"):
            assert client.get(wrong).status_code == 404, wrong
        # Opened by the app, or by hand, files and scratch files are sandboxed too, and no other origin reads them
        files = client.get("/files/probe.html")
        assert files.headers["content-security-policy"] == "sandbox" and "access-control-allow-origin" not in files.headers
        (client.app.state.session.scratch / "still.png").write_bytes(b"png")
        assert client.get("/scratch/still.png").headers["content-security-policy"] == "sandbox"
        # The app and its API can only be framed by the studio itself
        for path in ("/", "/api/script", "/static/app.js"):
            answer = client.get(path)
            assert answer.headers["content-security-policy"] == "frame-ancestors 'self'", path
            assert answer.headers["x-frame-options"] == "SAMEORIGIN", path


# -- in the browser ----------------------------------------------------------------------------------

def changes_seen(page) -> list[tuple[str, int]]:  # noqa: F811
    """The changes the page under test sends, with the studio's answers, as they arrive."""
    seen = []

    def answered(response) -> None:
        path = urlsplit(response.url).path
        if response.request.method == "POST" and path in CHANGES:
            seen.append((path, response.status))

    page.on("response", answered)
    return seen


def untouched(url: str, script, text: str) -> None:
    """Nothing changed: the script, the engine, the builds."""
    assert script.read_text() == text
    assert httpx2.get(url + "api/build").json() == {"state": "idle"}
    assert httpx2.post(url + "api/analyse", json={"text": text}).json()["engine"] == "silent"


@pytest.mark.parametrize("text, title", [("![](probe.html)\n\nHello.\n", "frame"),
                                         ("---\noverlay: probe.html\n---\n\nHello.\n", "overlay")])
def test_a_page_cant_use_the_studio_but_loads_its_own_files(project, page, text, title):  # noqa: F811
    script = project / "s.md"
    script.write_text(text)
    seen = changes_seen(page)
    with running(script) as url:
        page.goto(url)
        page.locator(".cm-line", has_text="Hello.").click()  # past the header, in the scene
        shown = page.frame_locator(f"iframe[title={title}]").locator("html")
        expect(shown).to_have_attribute("data-probe", ANY, timeout=10000)
        assert json.loads(shown.get_attribute("data-probe")) == {**REFUSED, **OWN}
        assert sorted(seen) == [(c, 403) for c in sorted(CHANGES)]
        untouched(url, script, text)

        # Opened by itself, outside the studio, the page is still sandboxed
        address = page.locator(f"iframe[title={title}]").get_attribute("src")
        seen.clear()
        page.goto(url + address.lstrip("/"))
        expect(page.locator("html")).to_have_attribute("data-probe", ANY, timeout=10000)
        assert json.loads(page.locator("html").get_attribute("data-probe")) == {**REFUSED, "app": None, **OWN}
        assert sorted(seen) == [(c, 403) for c in sorted(CHANGES)]
        untouched(url, script, text)


def test_a_slide_cant_use_the_studio(project, page):  # noqa: F811
    """A Markdown slide may carry HTML, scripts included: the frame it's composed in is sandboxed too."""
    script = project / "s.md"
    text = f"```md\n# A slide\n\n<script type=\"module\">\n{PROBE % {'own': 'false'}}\n</script>\n```\n\nHello.\n"
    script.write_text(text)
    seen = changes_seen(page)
    with running(script) as url:
        page.goto(url)
        shown = page.frame_locator("iframe[title=frame]").locator("html")
        expect(shown).to_have_attribute("data-probe", ANY, timeout=10000)
        assert json.loads(shown.get_attribute("data-probe")) == REFUSED
        assert sorted(seen) == [(c, 403) for c in sorted(CHANGES)]
        untouched(url, script, text)


def test_only_a_web_address_is_linked_from_the_inspector(tmp_path, page):  # noqa: F811
    """A capture's address comes from the script: a javascript: one, followed, would run as the studio."""
    script = tmp_path / "s.md"
    script.write_text("```render:web\n---\nurl: javascript:document.title='taken'\n---\n```\n\nA page.\n")
    with running(script) as url:
        page.goto(url)
        page.locator(".cm-line", has_text="render:web").click()
        row = page.get_by_test_id("capture")
        expect(row).to_contain_text("from javascript:document.title='taken'")
        expect(row.locator("a")).to_have_count(0)
