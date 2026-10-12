"""narrate as an internal HTTP API (#79): files by content, jobs that run the CLI, their outputs."""

import functools
import hashlib
import http.server
import io
import json
import threading
import time
import zipfile
from pathlib import Path

import pytest
from PIL import Image
from starlette.testclient import TestClient

from narrate import cli, media
from narrate.service import options as job_options
from narrate.service.server import create_app
from narrate.service.store import Store

SCRIPT = """---
size: 320x180
subtitles: overlay
---

![](photo.png)

A first paragraph, over the photo.

---

```md
# A slide
```

The slide's own words.

---

![](scenes/numbers.html)

And an animated page.
"""

PAGE = """<!doctype html><link rel="stylesheet" href="common.css">
<div class="box" style="animation-delay: var(--cue-1, .2s)"></div>"""
CSS = """html, body { margin: 0; width: 320px; height: 180px; background: #000; }
.box { position: absolute; left: 20px; top: 20px; width: 40px; height: 40px; background: #0f0; opacity: 0;
       animation: show .2s linear forwards; } @keyframes show { to { opacity: 1; } }"""


def png(colour: str) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (640, 360), colour).save(out, "PNG")
    return out.getvalue()


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def project_files() -> dict[str, bytes]:
    return {"intro.md": SCRIPT.encode(), "photo.png": png("red"), "scenes/numbers.html": PAGE.encode(),
            "scenes/common.css": CSS.encode()}


def upload(client: TestClient, files: dict[str, bytes]) -> dict:
    """Upload what the service lacks; the project's manifest."""
    manifest = {path: sha(data) for path, data in files.items()}
    missing = client.post("/v1/files/missing", json={"hashes": list(manifest.values())}).json()["missing"]
    for path, data in files.items():
        if sha(data) in missing:
            assert client.put(f"/v1/files/{sha(data)}", content=data).status_code == 201
    return manifest


def follow(client: TestClient, job_id: str) -> list[dict]:
    """The job's events, to the end."""
    seen = []
    with client.stream("GET", f"/v1/jobs/{job_id}/events") as response:
        for line in response.iter_lines():
            if line.startswith("data:"):
                seen.append(json.loads(line[5:]))
    return seen


def wait(client: TestClient, job_id: str, state: str, seconds: float = 60) -> dict:
    deadline = time.monotonic() + seconds
    while (job := client.get(f"/v1/jobs/{job_id}").json())["state"] != state:
        assert time.monotonic() < deadline, job
        time.sleep(0.1)
    return job


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("NARRATE_CACHE", str(tmp_path / "cache"))
    with TestClient(create_app(tmp_path / "data", "silent")) as c:
        yield c


def test_build_a_project_follow_it_and_fetch_its_outputs(client, tmp_path):
    files = project_files()
    manifest = upload(client, files)
    started = client.post("/v1/jobs", json={"kind": "build", "project": {"script": "intro.md", "files": manifest},
                                            "options": {"subtitles": "external", "transcript": True}})
    assert started.status_code == 202 and started.json()["state"] == "queued"
    job_id = started.json()["id"]
    seen = follow(client, job_id)
    assert seen[-1]["state"] == "done" and seen[-1]["errors"] == []
    assert any(e["progress"] and e["progress"].get("of") == 3 for e in seen)  # scene by scene
    outputs = seen[-1]["outputs"]
    assert set(outputs) == {"video", "poster", "srt", "vtt", "transcript"}
    video = tmp_path / "got.mp4"
    video.write_bytes(client.get(outputs["video"]).content)
    assert media.probe(video).duration > 3
    assert "The slide's own words." in client.get(outputs["transcript"]).text
    assert "A first paragraph" in client.get(outputs["srt"]).text
    # The job is listed, newest first, and keeps what it was asked
    [listed] = client.get("/v1/jobs").json()["jobs"]
    assert listed["id"] == job_id and listed["request"]["options"]["transcript"] is True

    # An edit: only the script is new, so only the script is uploaded
    files["intro.md"] = SCRIPT.replace("over the photo", "over the red photo").encode()
    edited = {path: sha(data) for path, data in files.items()}
    missing = client.post("/v1/files/missing", json={"hashes": list(edited.values())}).json()["missing"]
    assert missing == [sha(files["intro.md"])]


def test_a_script_sent_inline_a_zip_and_narration_alone(client, tmp_path):
    inline = client.post("/v1/jobs", json={"kind": "audio", "options": {"format": "wav"},
                                           "project": {"script": "hi.md", "text": "Hello there.\n"}}).json()
    done = wait(client, inline["id"], "done")
    assert set(done["outputs"]) == {"audio"} and done["outputs"]["audio"].endswith("/hi.wav")
    assert client.get(done["outputs"]["audio"]).content[:4] == b"RIFF"

    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as z:
        for path, data in project_files().items():
            z.writestr(f"project/{path}", data)
    data = archive.getvalue()
    client.put(f"/v1/files/{sha(data)}", content=data)
    zipped = client.post("/v1/jobs", json={"kind": "build", "project": {"zip": sha(data)}}).json()
    done = wait(client, zipped["id"], "done")
    assert done["outputs"]["video"].endswith("/intro.mp4")


@pytest.mark.parametrize("project, message", [
    ({"script": "../intro.md", "text": "Hi."}, "no '..'"),
    ({"script": "/etc/intro.md", "text": "Hi."}, "relative"),
    ({"script": "intro.md", "text": "Hi.", "files": {".env": "0" * 64}}, "hidden files"),
    ({"script": "intro.png", "text": "Hi."}, "isn't a script"),
    ({"script": "intro.md"}, "neither in files nor sent as text"),
    ({"script": "intro.md", "files": {"intro.md": "nothex"}}, "not a SHA-256"),
])
def test_projects_that_cant_be_laid_out_are_refused(client, project, message):
    refused = client.post("/v1/jobs", json={"kind": "build", "project": project})
    assert refused.status_code == 400 and message in refused.json()["error"]


def test_files_must_be_uploaded_first_and_match_their_hash(client):
    absent = sha(b"not uploaded")
    refused = client.post("/v1/jobs", json={"kind": "build", "project": {"script": "a.md", "files": {"a.md": absent}}})
    assert refused.status_code == 400 and refused.json()["missing"] == [absent]
    wrong = client.put(f"/v1/files/{absent}", content=b"something else")
    assert wrong.status_code == 400 and "SHA-256" in wrong.json()["error"]
    assert client.post("/v1/files/missing", json={"hashes": [absent]}).json() == {"missing": [absent]}
    assert client.put(f"/v1/files/{sha(b'x')}", content=b"x").status_code == 201
    assert client.put(f"/v1/files/{sha(b'x')}", content=b"x").status_code == 200  # kept already


@pytest.mark.parametrize("body, message", [
    ({"kind": "render"}, "kind must be one of"),
    ({"options": {"scenes": 3}}, "scenes must be a string"),
    ({"options": {"tts": "espeak"}}, "tts must be one of"),
    ({"kind": "audio", "options": {"regenerate": True}}, "audio jobs don't take 'regenerate'"),
    ({"options": {"frobnicate": True}}, "don't take 'frobnicate'"),
])
def test_options_a_job_doesnt_take_are_refused(client, body, message):
    refused = client.post("/v1/jobs", json={"project": {"script": "a.md", "text": "Hi."}, **body})
    assert refused.status_code == 400 and message in refused.json()["error"]


def test_a_failed_build_says_why_with_its_line(client):
    job = client.post("/v1/jobs", json={"project": {"script": "a.md", "text": "Hi.\n\n![](nowhere.png)\n"}}).json()
    failed = wait(client, job["id"], "failed")
    assert failed["errors"] and failed["errors"][0]["line"] == 3 and "nowhere.png" in failed["errors"][0]["message"]


def test_cancel_a_running_job(client):
    page = "<!doctype html><script>requestAnimationFrame(function f() { requestAnimationFrame(f); });</script>"
    files = {"slow.md": b"---\nsize: 320x180\n---\n\n![](slow.html)\n\n(duration: 60)\n", "slow.html": page.encode()}
    job = client.post("/v1/jobs", json={"project": {"script": "slow.md", "files": upload(client, files)}}).json()
    wait(client, job["id"], "running")
    time.sleep(1)
    assert client.post(f"/v1/jobs/{job['id']}/cancel").status_code == 200
    assert wait(client, job["id"], "cancelled", 20)["finished"]
    # A queued job is cancelled at once; cancelling a finished one changes nothing
    assert client.post("/v1/jobs/j_nothing/cancel").status_code == 404


def test_a_restart_fails_jobs_that_were_running_and_runs_queued_ones(tmp_path, monkeypatch):
    monkeypatch.setenv("NARRATE_CACHE", str(tmp_path / "cache"))
    store = Store(tmp_path / "data")
    running = store.new_job("build", {"project": {"script": "a.md", "text": "Hi."}, "options": {}})
    store.update(running["id"], state="running")
    queued = store.new_job("build", {"project": {"script": "b.md", "text": "Hello.\n"}, "options": {}})
    store.db.close()
    with TestClient(create_app(tmp_path / "data", "silent")) as client:
        failed = client.get(f"/v1/jobs/{running['id']}").json()
        assert failed["state"] == "failed" and "interrupted" in failed["errors"][0]["message"]
        assert wait(client, queued["id"], "done")["outputs"]["video"].endswith("/b.mp4")


def test_web_captures_come_back_as_outputs(client, tmp_path):
    root = tmp_path / "site"
    root.mkdir()
    (root / "page.html").write_text("<!doctype html><style>body { background: #00f }</style>")

    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass

    site = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=str(root)))
    threading.Thread(target=site.serve_forever, daemon=True).start()
    try:
        text = f"---\nsize: 320x180\n---\n\n```render:web\nhttp://127.0.0.1:{site.server_address[1]}/page.html\n```\n\nA page.\n"
        job = client.post("/v1/jobs", json={"project": {"script": "web.md", "text": text}}).json()
        done = wait(client, job["id"], "done")
    finally:
        site.shutdown()
    [(path, address)] = [(p, a) for p, a in done["outputs"]["captures"].items() if p.endswith(".png")]
    assert path.startswith(".narrate/generated/web/")
    picture = Image.open(io.BytesIO(client.get(address).content)).convert("RGB")
    assert picture.getpixel((10, 10)) == pytest.approx((0, 0, 255), abs=10)


def test_every_option_is_a_flag_the_cli_takes():
    commands = {name: p for name, p in cli.parser()._subparsers._group_actions[0].choices.items()}
    for name, option in job_options.OPTIONS.items():
        for kind in option.kinds:
            flags = {f: a for a in commands[kind]._actions for f in a.option_strings}
            if option.flag is None:
                continue
            assert option.flag in flags, (name, kind)
            action = flags[option.flag]
            assert (action.nargs == 0) == (option.type is bool), name
            if action.choices:
                assert set(option.choices) == set(action.choices), name


def test_the_openapi_document_describes_the_options(client):
    doc = client.get("/v1/openapi.json").json()
    assert doc["openapi"].startswith("3.1")
    [build, audio] = doc["components"]["schemas"]["JobRequest"]["oneOf"]
    assert set(build["properties"]["options"]["properties"]) == {n for n, o in job_options.OPTIONS.items()
                                                                   if "build" in o.kinds}
    assert audio["properties"]["options"]["properties"]["format"]["enum"] == list(job_options.AUDIO_FORMATS)
    assert client.get("/v1").json()["openapi"] == "/v1/openapi.json"


def test_narrate_serve_is_a_command():
    args = cli.parser().parse_args(["serve", "--port", "9000", "--workers", "2", "--data", "/tmp/x"])
    assert (args.port, args.workers, args.data, args.tts, args.host) == (9000, 2, "/tmp/x", "kokoro", "127.0.0.1")
    assert Path(args.data).name == "x"
