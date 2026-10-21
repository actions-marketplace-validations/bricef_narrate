"""The studio and the service answer only to their own host names, and refuse changes sent
from other sites' pages (#93)."""

import hashlib
from dataclasses import dataclass
from typing import Callable

import pytest
from starlette.testclient import TestClient

from narrate import cli
from narrate.hosts import allowed, split
from narrate.service import server as service_server
from narrate.studio import server as studio_server

DATA = b"a file for the service"
SHA = hashlib.sha256(DATA).hexdigest()


@dataclass
class Server:
    make: Callable  # hosts -> app
    read: str  # a route that only reads
    write: Callable  # (client, headers) -> response, from a request that changes something
    written: Callable  # app -> whether it did


@pytest.fixture(params=["studio", "service"])
def server(request, tmp_path, monkeypatch):
    monkeypatch.setenv("NARRATE_CACHE", str(tmp_path / "cache"))
    if request.param == "studio":
        script = tmp_path / "s.md"
        script.write_text("Hello.\n")

        def save(client, headers):
            version = studio_server.version_of(script)
            return client.put("/api/script", json={"text": "Changed.\n", "version": version}, headers=headers)

        return Server(lambda hosts: studio_server.create_app(script, "silent", hosts), "/api/script", save,
                      lambda app: script.read_text() == "Changed.\n")
    return Server(lambda hosts: service_server.create_app(tmp_path / "data", "silent", hosts=hosts), "/v1/jobs",
                  lambda client, headers: client.put(f"/v1/files/{SHA}", content=DATA, headers=headers),
                  lambda app: app.state.store.missing([SHA]) == [])


def test_a_request_to_another_host_name_is_refused(server):
    """As when a site points its own name at 127.0.0.1: its pages could otherwise read the answers."""
    app = server.make(allowed("127.0.0.1"))
    with TestClient(app, base_url="http://evil.example:8787") as client:
        assert client.get(server.read).status_code == 403
        assert client.get("/").status_code == 403
        assert server.write(client, {}).status_code == 403
        assert server.write(client, {"Origin": "http://evil.example:8787"}).status_code == 403
    assert not server.written(app)


@pytest.mark.parametrize("origin", ["https://evil.example", "http://evil.example:8787", "http://localhost:9999",
                                    "http://localhost", "null", "file://"])
def test_a_change_from_another_sites_page_is_refused(server, origin):
    app = server.make(allowed("127.0.0.1"))
    with TestClient(app, base_url="http://localhost:8787") as client:
        refused = server.write(client, {"Origin": origin})
        assert refused.status_code == 403 and "another site" in refused.json()["error"]
        # A read is answered, but without CORS headers the browser keeps it from the page
        read = client.get(server.read, headers={"Origin": origin})
        assert read.status_code == 200 and "access-control-allow-origin" not in read.headers
    assert not server.written(app)


@pytest.mark.parametrize("host", ["localhost:8787", "127.0.0.1:8787", "[::1]:8787", "localhost"])
def test_its_own_pages_and_programs_are_answered(server, host):
    app = server.make(allowed("127.0.0.1"))
    with TestClient(app, base_url=f"http://{host}") as client:
        assert client.get(server.read).status_code == 200
        assert server.write(client, {"Origin": f"http://{host}"}).status_code < 300  # a page of its own
        assert server.write(client, {}).status_code < 300  # a program, curl, narrate's CLI
        assert server.write(client, {"Origin": f"https://{host}"}).status_code < 300  # behind a proxy ending TLS
        port = ":8787" if host.endswith(":8787") else ""
        assert server.write(client, {"Origin": f"http://127.0.0.1{port}"}).status_code < 300  # another of its names
    assert server.written(app)


def test_other_sites_cant_frame_it(server):
    """Or they could show it under a page of their own and steer the user's clicks into it."""
    with TestClient(server.make(allowed("127.0.0.1")), base_url="http://localhost:8787") as client:
        for answer in (client.get("/"), client.get(server.read), client.get("/missing"),
                       server.write(client, {"Origin": "https://evil.example"})):
            assert answer.headers["content-security-policy"] == "frame-ancestors 'self'"
            assert answer.headers["x-frame-options"] == "SAMEORIGIN"


@pytest.mark.parametrize("bind, more, host, answered", [
    ("127.0.0.1", [], "localhost:8787", True),
    ("0.0.0.0", [], "localhost:8787", True),  # in Docker, published as -p 127.0.0.1:8787:8787
    ("0.0.0.0", [], "127.0.0.1:9000", True),  # published on another port
    ("0.0.0.0", [], "192.168.1.5:8787", False),
    ("192.168.1.5", [], "192.168.1.5:8787", True),
    ("buildbox.lan", [], "buildbox.lan:8788", True),
    ("::", [], "[::1]:8787", True),
    ("::", [], "[fe80::1]:8787", False),
    ("fe80::1", [], "[fe80::1]:8787", True),
    ("0.0.0.0", ["buildbox"], "buildbox:8788", True),
    ("0.0.0.0", ["BuildBox.lan:8788"], "buildbox.lan", True),
    ("0.0.0.0", ["fe80::1", "[fe80::2]"], "[fe80::2]:8788", True),
    ("0.0.0.0", ["buildbox"], "evil.example:8788", False),
])
def test_the_host_names_it_answers_to(server, bind, more, host, answered):
    app = server.make(allowed(bind, more))
    with TestClient(app, base_url=f"http://{host}") as client:
        assert client.get(server.read).status_code == (200 if answered else 403)
        if answered:
            assert server.write(client, {"Origin": f"http://{host}"}).status_code < 300


def test_names_are_compared_as_browsers_send_them():
    assert [split(h) for h in ("LOCALHOST:8787", "[::1]:8787", "::1", "[0:0::1]", "127.0.0.1", "a:b:c", "")] == \
        [("localhost", "8787"), ("[::1]", "8787"), ("[::1]", ""), ("[::1]", ""), ("127.0.0.1", ""), ("a:b:c", ""),
         ("", "")]
    assert allowed("0.0.0.0") == allowed("::") == ["localhost", "127.0.0.1", "[::1]"]
    assert allowed("::1", ["Narrate.lan"]) == ["localhost", "127.0.0.1", "[::1]", "narrate.lan"]


def test_the_commands_take_names_to_allow(tmp_path, monkeypatch):
    apps = {}

    def fake(name):
        class Server:
            def __init__(self, app, host, port):
                apps[name] = app

            def run(self):
                pass
        return Server

    monkeypatch.setattr(studio_server, "server", fake("studio"))
    monkeypatch.setattr(service_server, "server", fake("service"))
    assert cli.main(["studio", str(tmp_path / "s.md"), "--host", "0.0.0.0", "--allow-host", "studio.lan"]) == 0
    assert cli.main(["serve", "--data", str(tmp_path / "data"), "--host", "0.0.0.0",
                     "--allow-host", "narrate.lan", "--allow-host", "buildbox"]) == 0
    for name, path, host, status in [("studio", "/api/script", "studio.lan:8787", 200),
                                     ("studio", "/api/script", "localhost:8787", 200),
                                     ("studio", "/api/script", "buildbox:8787", 403),
                                     ("service", "/v1/jobs", "buildbox:8788", 200),
                                     ("service", "/v1/jobs", "narrate.lan:8788", 200),
                                     ("service", "/v1/jobs", "studio.lan:8788", 403)]:
        with TestClient(apps[name], base_url=f"http://{host}") as client:
            assert client.get(path).status_code == status, (name, host)
