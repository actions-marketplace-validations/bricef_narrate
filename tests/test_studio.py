"""narrate studio's server (#51): the script, saving, conflicts, project files, events."""

import os

import pytest
from starlette.testclient import TestClient

from narrate.studio.server import Session, create_app, version_of


@pytest.fixture
def project(tmp_path):
    (tmp_path / "s.md").write_text("Hello.\n")
    (tmp_path / "photo.jpg").write_bytes(b"jpeg")
    (tmp_path / ".env").write_text("ELEVENLABS_API_KEY=sk_secret\n")
    (tmp_path / ".narrate" / "generated" / "web").mkdir(parents=True)
    (tmp_path / ".narrate" / "generated" / "web" / "capture.png").write_bytes(b"png")
    return tmp_path


@pytest.fixture
def client(project):
    with TestClient(create_app(project / "s.md")) as c:
        yield c


def test_the_script_loads_and_saves(client, project):
    script = client.get("/api/script").json()
    assert (script["name"], script["text"]) == ("s.md", "Hello.\n")
    saved = client.put("/api/script", json={"text": "Hello again.\n", "version": script["version"]})
    assert saved.status_code == 200 and saved.json()["version"] == version_of(project / "s.md")
    assert (project / "s.md").read_text() == "Hello again.\n"


def test_a_save_over_a_newer_file_is_refused(client, project):
    loaded = client.get("/api/script").json()["version"]
    (project / "s.md").write_text("Changed elsewhere, and longer.\n")
    refused = client.put("/api/script", json={"text": "Mine.\n", "version": loaded})
    assert refused.status_code == 409
    assert (project / "s.md").read_text() == "Changed elsewhere, and longer.\n"


def test_saving_keeps_windows_line_endings_and_the_files_mode(client, project):
    (project / "s.md").write_bytes(b"One.\r\n\r\nTwo.\r\n")
    os.chmod(project / "s.md", 0o640)
    script = client.get("/api/script").json()
    assert script["text"] == "One.\n\nTwo.\n"
    client.put("/api/script", json={"text": "One.\n\nThree.\n", "version": script["version"]})
    assert (project / "s.md").read_bytes() == b"One.\r\n\r\nThree.\r\n"
    assert (project / "s.md").stat().st_mode & 0o777 == 0o640
    assert not list(project.glob(".s.md.*.tmp"))


def test_a_new_script_is_created_on_first_save(tmp_path):
    with TestClient(create_app(tmp_path / "new.md")) as c:
        script = c.get("/api/script").json()
        assert (script["text"], script["version"]) == ("", "missing")
        assert c.put("/api/script", json={"text": "Hi.\n", "version": "missing"}).status_code == 200
    assert (tmp_path / "new.md").read_text() == "Hi.\n"


def test_project_files_are_served_but_nothing_outside_or_hidden(client, project):
    assert client.get("/files/photo.jpg").content == b"jpeg"
    assert client.get("/files/.narrate/generated/web/capture.png").content == b"png"  # narrate's own folder
    for path in ("/files/.env", "/files/../etc/passwd", "/files/%2e%2e/%2e%2e/etc/passwd", "/files/missing.png",
                 "/files/.narrate/../.env"):
        assert client.get(path).status_code == 404, path


def test_outside_edits_are_noticed_but_our_own_saves_are_not(project):
    session = Session(project / "s.md")
    assert session.poll() is None
    session.save("Saved here.\n", session.version)
    assert session.poll() is None
    (project / "s.md").write_text("Edited elsewhere.\n")
    event = session.poll()
    assert event == {"type": "script-changed", "version": version_of(project / "s.md")}
    assert session.poll() is None


def test_the_app_and_its_vendored_libraries_are_served(client):
    assert '<script type="module" src="/static/app.js">' in client.get("/").text
    for path in ("/static/app.js", "/static/editor.js", "/static/style.css", "/static/vendor/htm-preact.js",
                 "/static/vendor/codemirror.js"):
        assert client.get(path).status_code == 200, path
