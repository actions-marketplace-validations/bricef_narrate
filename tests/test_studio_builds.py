"""Builds from the studio (#55): `narrate build` in a child process, with progress, cancel and errors."""

import time

import pytest
from starlette.testclient import TestClient

from narrate.studio.server import create_app


@pytest.fixture
def studio(tmp_path, monkeypatch):
    monkeypatch.setenv("NARRATE_CACHE", str(tmp_path / "cache"))
    script = tmp_path / "s.md"
    script.write_text("---\nsize: 320x180\n---\n\nThe first scene.\n\n---\n\nThe second scene.\n")
    with TestClient(create_app(script, "silent", hosts=["testserver"])) as client:
        yield script, client


def wait(client, states=("done", "failed", "cancelled"), seconds=120):
    deadline = time.monotonic() + seconds
    while True:
        status = client.get("/api/build").json()
        if status["state"] in states:
            return status
        assert time.monotonic() < deadline, status
        time.sleep(0.2)


def test_a_build_writes_the_video_beside_the_script(studio):
    script, client = studio
    assert client.get("/api/build").json() == {"state": "idle"}
    started = client.post("/api/build")
    assert started.status_code == 202
    assert client.post("/api/build").status_code == 409  # one at a time
    done = wait(client)
    assert done["state"] == "done", done
    assert script.with_suffix(".mp4").exists() and script.with_suffix(".jpg").exists()
    assert done["video"].startswith("/files/s.mp4?v=")
    assert client.get(done["video"]).headers["content-type"] == "video/mp4"
    assert "s.mp4" in done["summary"]


def test_progress_comes_scene_by_scene(studio):
    script, client = studio
    seen = set()
    client.post("/api/build")
    deadline = time.monotonic() + 120
    while (status := client.get("/api/build").json())["state"] not in ("done", "failed"):
        if status.get("of"):
            seen.add((status["scene"], status["of"]))
        assert time.monotonic() < deadline
        time.sleep(0.02)
    assert status["state"] == "done"
    assert seen <= {(1, 2), (2, 2)} and seen  # scene k of 2, as the CLI reports it


def test_a_build_can_be_cancelled(studio):
    script, client = studio
    script.write_text("---\nsize: 320x180\n---\n\n" + "\n---\n\n".join(f"Scene {n}.\n\n(duration: 3)\n" for n in range(8)))
    client.post("/api/build")
    assert client.post("/api/build/cancel").json() == {"state": "cancelling"}
    assert wait(client)["state"] == "cancelled"
    assert client.post("/api/build/cancel").status_code == 409  # nothing running now


def test_a_failed_build_reports_the_line(studio):
    script, client = studio
    script.write_text("Fine.\n\n---\n\n![](missing.png)\n\nNot fine.\n")
    failed = wait(client) if client.post("/api/build").status_code == 202 else None
    assert failed["state"] == "failed"
    assert failed["errors"] == [{"line": 5, "message": "file not found: missing.png"}]


def wait_scene(client, seconds=120):
    deadline = time.monotonic() + seconds
    while (status := client.get("/api/scenes/render").json())["state"] not in ("done", "failed", "cancelled"):
        assert time.monotonic() < deadline, status
        time.sleep(0.2)
    return status


def test_a_scene_renders_into_scratch_and_is_reused(studio):
    script, client = studio
    assert client.get("/api/scenes/render").json() == {"state": "idle"}
    started = client.post("/api/scenes/2/render")
    assert started.status_code == 202 and started.json()["scene"] == 2
    done = wait_scene(client)
    assert done["state"] == "done" and done["scene"] == 2, done
    assert done["video"].startswith("/scratch/scene-2-")
    assert client.get(done["video"]).headers["content-type"] == "video/mp4"
    assert not script.with_suffix(".mp4").exists()  # never the real video
    assert "no transition" not in " ".join(done["notes"])  # nothing to drop: the script has none

    again = client.post("/api/scenes/2/render")
    assert again.status_code == 200 and again.json()["video"].split("?")[0] == done["video"].split("?")[0]

    script.write_text(script.read_text().replace("The second scene.", "The second scene, changed."))
    assert client.post("/api/scenes/2/render").status_code == 202  # a new text renders again
    assert wait_scene(client)["state"] == "done"
    assert client.post("/api/scenes/render/cancel").status_code == 409  # nothing running now
