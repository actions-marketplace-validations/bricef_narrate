"""render:web: web pages captured as pictures, stored in the project (#50)."""

import base64
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from narrate import media
from narrate.build import Builder, BuildError
from narrate.cli import main
from narrate.script import Render, parse_file
from narrate.tts import SilentSynth
from narrate.web import Web

PAGE = b"""<!doctype html><style>
html, body { margin: 0; background: #fff; }
@media (prefers-color-scheme: dark) { html, body { background: #000; } }
#banner { height: 60px; background: #f00; }
#card { width: 100px; height: 50px; background: #00f; margin: 10px; }
#far { margin-top: 3000px; height: 400px; background: #0f0; }
</style><div id=banner></div><div id=card></div><div id=far>Far down</div>"""


class Site:
    """A local web server: /page.html, a Basic-auth /private.html, and 404s for the rest."""

    def __init__(self):
        self.requests = 0
        site = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                site.requests += 1
                if self.path == "/private.html":
                    wanted = "Basic " + base64.b64encode(b"ada:secret").decode()
                    if self.headers.get("Authorization") != wanted:
                        self.send_response(401)
                        self.send_header("WWW-Authenticate", 'Basic realm="test"')
                        self.end_headers()
                        return
                if self.path not in ("/page.html", "/private.html"):
                    self.send_error(404)
                    return
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.wfile.write(PAGE)

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_port}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def stop(self):
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture
def site():
    s = Site()
    yield s
    s.stop()


@pytest.fixture(autouse=True)
def own_cache(monkeypatch, tmp_path):
    monkeypatch.setenv("NARRATE_CACHE", str(tmp_path / "cache"))


def build(tmp_path: Path, block: str, regenerate: bool = False, name: str = "s") -> Path:
    script = tmp_path / f"{name}.md"
    script.write_text(f"---\nsize: 320x180\n---\n\n{block}\n\n(duration: 1)\n")
    out = tmp_path / f"{name}.mp4"
    # The site stands in for one on the web, but it's on this machine: allowed (test_network.py)
    Builder(parse_file(script), SilentSynth(), log=lambda _: None, regenerate=regenerate, local_network=True).build(out)
    return out


def frame(video: Path) -> np.ndarray:
    png = video.with_suffix(".png")
    media.extract_frame(video, 0.5, png)
    return np.asarray(Image.open(png).convert("RGB"), dtype=float)


def stored(tmp_path: Path) -> list[Path]:
    return sorted((tmp_path / ".narrate" / "generated" / "web").glob("*.png"))


def web(settings: str) -> str:
    return f"```render:web\n---\n{settings}\n---\n```"


# -- checking -------------------------------------------------------------------

@pytest.mark.parametrize("settings, problem", [
    ({}, "needs a url"),
    ({"url": "ftp://example.com/x"}, "http or https"),
    ({"url": "https://example.com", "scale": 9}, "scale"),
    ({"url": "https://example.com", "color-scheme": "sepia"}, "color-scheme"),
    ({"url": "https://example.com", "wait": "forever"}, "wait"),
    ({"url": "https://example.com", "auth": "user:pass"}, "environment variable"),
    ({"url": "https://example.com", "viewport": "huge"}, "viewport"),
])
def test_bad_settings_are_reported_without_fetching(settings, problem):
    assert any(problem in p for p in Web().check(Render("web", "", settings)))


def test_a_bare_url_in_the_body_works():
    assert Web().check(Render("web", "https://example.com/docs", {})) == []


def test_check_never_fetches(tmp_path, site, capsys):
    (tmp_path / "s.md").write_text(web(f"url: {site.url}/page.html"))
    assert main(["check", str(tmp_path / "s.md")]) == 0 and site.requests == 0


# -- capturing -------------------------------------------------------------------

def test_a_capture_is_placed_like_a_picture(tmp_path, site):
    f = frame(build(tmp_path, web(f"url: {site.url}/page.html\nscale: 1\ncolor-scheme: dark\nhide: '#banner'\n"
                                  "css: '#card { background: #0f0 }'")))
    assert f[150, 300].mean() < 10  # the dark scheme's background
    assert f[:, :, 0].max() < 100  # the red banner hidden
    assert f[30, 50][1] > 200 > f[30, 50][2]  # the card, recoloured by the injected CSS, where the banner was


def test_scroll_to_and_selector(tmp_path, site):
    f = frame(build(tmp_path, web(f"url: {site.url}/page.html\nscale: 1\nscroll-to: Far down"), name="far"))
    assert f[90, 160][1] > 200 > f[90, 160][0]  # the green block 3000 px down
    build(tmp_path, web(f"url: {site.url}/page.html\nselector: '#card'"), name="card")
    sizes = {Image.open(p).size for p in stored(tmp_path)}
    assert (200, 100) in sizes  # the card alone, at the default scale of 2


def test_captures_are_stored_and_reused_until_regenerated(tmp_path, site):
    block = web(f"url: {site.url}/page.html\nscale: 1")
    build(tmp_path, block)
    first = stored(tmp_path)
    sidecar = json.loads(first[0].with_suffix(".json").read_text())
    assert sidecar["renderer"] == "web" and sidecar["settings"]["url"].endswith("/page.html") and sidecar["made"]
    asked = site.requests
    build(tmp_path, block, name="again")
    assert site.requests == asked and stored(tmp_path) == first  # reused, no fetch
    build(tmp_path, block, regenerate=True, name="fresh")
    assert site.requests > asked  # taken again


def test_stored_captures_build_offline(tmp_path):
    offline = Site()
    block = web(f"url: {offline.url}/page.html\nscale: 1")
    build(tmp_path, block)
    offline.stop()
    assert frame(build(tmp_path, block, name="offline"))[150, 300].mean() > 245  # the stored capture


def test_basic_auth_comes_from_the_environment(tmp_path, site, monkeypatch):
    block = web(f"url: {site.url}/private.html\nscale: 1\nauth: NARRATE_TEST_AUTH")
    with pytest.raises(BuildError, match="set NARRATE_TEST_AUTH"):
        build(tmp_path, block)
    monkeypatch.setenv("NARRATE_TEST_AUTH", "ada:secret")
    build(tmp_path, block, name="authed")
    assert "secret" not in stored(tmp_path)[0].with_suffix(".json").read_text()  # the name, never the secret


def test_http_errors_fail_at_the_block(tmp_path, site):
    with pytest.raises(BuildError, match="answered 404") as e:
        build(tmp_path, web(f"url: {site.url}/missing.html"))
    assert e.value.line == 5
