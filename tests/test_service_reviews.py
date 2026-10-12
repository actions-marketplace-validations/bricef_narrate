"""The internal API's checks, voices, auditions and reviews (#80)."""

import io
import json

import pytest
from PIL import Image

from test_service import client, png, project_files, sha, upload, wait  # noqa: F401 - the client fixture


def test_check_a_project_before_building_it(client):  # noqa: F811
    manifest = upload(client, {"intro.md": b"Hello there.\n\n![](nowhere.png)\n\n---\n\n![](photo.png)\n\nTwo.\n",
                               "photo.png": png("red")})
    report = client.post("/v1/check", json={"project": {"script": "intro.md", "files": manifest}}).json()
    assert report["engine"] == "silent"  # the service's own, unless the check names one
    assert [(p["line"], p["message"]) for p in report["problems"]] == [(3, "file not found: nowhere.png")]
    assert [s["index"] for s in report["scenes"]] == [1, 2] and report["duration"] > 0
    priced = client.post("/v1/check", json={"tts": "elevenlabs",
                                            "project": {"script": "intro.md", "files": manifest}}).json()
    assert priced["engine"] == "elevenlabs" and priced["missing"]["characters"] == len("Hello there.") + len("Two.")
    refused = client.post("/v1/check", json={"tts": "espeak", "project": {"script": "a.md", "text": "Hi."}})
    assert refused.status_code == 400 and "tts must be one of" in refused.json()["error"]
    absent = client.post("/v1/check", json={"project": {"script": "a.md", "files": {"a.md": sha(b"absent")}}})
    assert absent.status_code == 400 and absent.json()["missing"] == [sha(b"absent")]


def test_voices_say_what_each_becomes_on_an_engine(client):  # noqa: F811
    kokoro = client.get("/v1/voices", params={"tts": "kokoro"}).json()
    by_name = {v["name"]: v for v in kokoro["voices"]}
    assert kokoro["engine"] == "kokoro" and by_name["bf_emma"]["resolves"]
    assert client.get("/v1/voices", params={"tts": "espeak"}).status_code == 400


def test_an_audition_is_a_short_audio_job_waited_for(client):  # noqa: F811
    heard = client.post("/v1/auditions", json={"voice": "Amy", "text": "A sample of the narration."})
    assert heard.status_code == 200
    job = heard.json()
    assert job["state"] == "done" and job["kind"] == "audio" and job["request"]["options"]["tts"] == "silent"
    assert "(voice: Amy)" in job["request"]["project"]["text"]
    assert client.get(job["outputs"]["audio"]).content[:4] == b"RIFF"
    refused = client.post("/v1/auditions", json={"voice": "Amy; rm -rf"})
    assert refused.status_code == 400 and "not a voice name" in refused.json()["error"]


def test_a_contact_sheet_of_a_build(client):  # noqa: F811
    built = client.post("/v1/jobs", json={"project": {"script": "intro.md", "files": upload(client, project_files())}})
    wait(client, built.json()["id"], "done")
    # A frame from each scene, from the build's own script and engine
    sheet = client.post("/v1/jobs", json={"kind": "frames", "media": {"job": built.json()["id"]}}).json()
    done = wait(client, sheet["id"], "done")
    picture = Image.open(io.BytesIO(client.get(done["outputs"]["sheet"]).content))
    assert picture.width > 480 * 2  # three scenes, side by side
    # Or at moments of its own, of an uploaded video
    video = client.get(client.get(f"/v1/jobs/{built.json()['id']}").json()["outputs"]["video"]).content
    client.put(f"/v1/files/{sha(video)}", content=video)
    moments = client.post("/v1/jobs", json={"kind": "frames", "media": {"file": sha(video), "name": "intro.mp4"},
                                            "options": {"at": "0.5", "width": 200}}).json()
    picture = Image.open(io.BytesIO(client.get(wait(client, moments["id"], "done")["outputs"]["sheet"]).content))
    assert 200 <= picture.width < 480


@pytest.mark.parametrize("media, message", [
    ({"job": "j_nothing"}, "no build or audio job"),
    ({"file": "0" * 64}, "upload these files first"),
    ({"file": "0" * 64, "name": "../x.mp4"}, "plain file name"),
    ("intro.mp4", "media must be"),
])
def test_review_jobs_need_something_to_review(client, media, message):  # noqa: F811
    refused = client.post("/v1/jobs", json={"kind": "frames", "media": media})
    assert refused.status_code == 400 and message in refused.json()["error"]


@pytest.mark.stt
def test_hear_what_a_build_says(client):  # noqa: F811
    built = client.post("/v1/jobs", json={"project": {"script": "hi.md", "text": "Hello there, and welcome.\n"}}).json()
    wait(client, built["id"], "done")
    heard = client.post("/v1/jobs", json={"kind": "hear", "media": {"job": built["id"]},
                                          "options": {"language": "en"}}).json()
    done = wait(client, heard["id"], "done", 180)
    report = json.loads(client.get(done["outputs"]["report"]).content)
    # The silent engine says nothing, so every word of the script is missing
    assert report["differences"] and "Hello" in json.dumps(report)
