"""What each request costs (#81): usage reported by the CLI, priced by the service, reported over periods."""

import json
import urllib.request
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from narrate import cli, tts
from narrate.service import costs
from narrate.service.costs import Prices, PricesError
from narrate.service.server import create_app
from narrate.service.store import Store

from test_service import png, upload, wait  # noqa: F401

SCRIPT = "---\nsize: 320x180\n---\n\nThe first paragraph.\n\nThe *second* one.\n"


class FakeElevenLabs:
    """ElevenLabs' text-to-speech, answered here: no request leaves the machine, nothing is spent. Saying
    "second" reports a `character-cost` of three a character, so a test can tell billed credits from narrate's
    estimate; everything else leaves narrate to estimate."""

    def __init__(self):
        self.sent: list[dict] = []

    def __call__(self, request, timeout=None):
        assert request.full_url.startswith("https://api.elevenlabs.io/v1/text-to-speech/"), request.full_url
        body = json.loads(request.data)
        self.sent.append(body)
        headers = {"character-cost": str(3 * len(body["text"]))} if body["text"] == "second" else {}

        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def read(self):
                return b"\x00\x00" * 2400  # 0.1 s of silence, as 16-bit PCM

        response = Response()
        response.headers = headers
        return response


@pytest.fixture
def eleven(monkeypatch, tmp_path):
    monkeypatch.setenv("NARRATE_CACHE", str(tmp_path / "cache"))
    monkeypatch.setenv("ELEVENLABS_API_KEY", "not-a-real-key")
    fake = FakeElevenLabs()
    monkeypatch.setattr(urllib.request, "urlopen", fake)
    return fake


def run_audio(tmp_path: Path, text: str, name: str, *extra: str) -> dict:
    script = tmp_path / "s.md"
    script.write_text(text)
    usage = tmp_path / f"{name}.json"
    assert cli.main(["audio", str(script), "--tts", "elevenlabs", "-o", str(tmp_path / f"{name}.wav"), "-q",
                     "--usage", str(usage), *extra]) == 0
    return json.loads(usage.read_text())


def test_a_build_reports_what_it_sent_and_what_the_cache_saved(eleven, tmp_path):
    first = run_audio(tmp_path, SCRIPT, "first")
    runs = ["The first paragraph.", "The", "second", "one."]  # emphasis splits the second paragraph
    assert sorted(b["text"] for b in eleven.sent) == sorted(runs)
    [(model, used)] = first["speech"]["models"].items()
    assert first["speech"]["engine"] == "elevenlabs" and model == "eleven_multilingual_v2"
    assert used["characters"] == sum(map(len, runs)) and used["requests"] == 4 and used["cached_characters"] == 0
    # As billed for "second", and estimated at the model's 1 credit a character for the rest
    assert used["credits"] == 3 * len("second") + len("The first paragraph.") + len("The") + len("one.")
    assert used["estimated_requests"] == 3
    assert first["audio_seconds"] > 0 and first["cpu_seconds"] > 0 and first["wall_seconds"] > 0

    # Again: everything from the cache, nothing sent
    again = run_audio(tmp_path, SCRIPT, "again")["speech"]["models"]["eleven_multilingual_v2"]
    assert (again["characters"], again["requests"], again["cached_characters"]) == (0, 0, sum(map(len, runs)))
    assert len(eleven.sent) == 4

    # An edit: only the edited paragraph is sent
    edited = run_audio(tmp_path, SCRIPT.replace("first paragraph", "opening paragraph"), "edited")
    used = edited["speech"]["models"]["eleven_multilingual_v2"]
    assert used["characters"] == len("The opening paragraph.") and used["cached_characters"] == 3 + 6 + 4


def test_credits_follow_the_model_when_elevenlabs_doesnt_say(eleven, tmp_path):
    used = run_audio(tmp_path, "One paragraph only.\n", "flash", "--tts-model", "eleven_flash_v2_5")
    entry = used["speech"]["models"]["eleven_flash_v2_5"]
    assert entry["credits"] == len("One paragraph only.") * 0.5  # flash costs half a credit a character
    assert entry["estimated_requests"] == 1 and eleven.sent[0]["model_id"] == "eleven_flash_v2_5"


def test_every_command_that_works_reports_its_time(tmp_path, monkeypatch):
    monkeypatch.setenv("NARRATE_CACHE", str(tmp_path / "cache"))
    script = tmp_path / "s.md"
    script.write_text("---\nsize: 320x180\n---\n\nHello.\n")
    assert cli.main(["build", str(script), "--tts", "silent", "-q", "--usage", str(tmp_path / "b.json"),
                     "-o", str(tmp_path / "s.mp4")]) == 0
    built = json.loads((tmp_path / "b.json").read_text())
    assert built["speech"] is None and built["video_seconds"] > 0 and built["rendered"] == {}
    assert cli.main(["frames", str(tmp_path / "s.mp4"), "--count", "2", "-o", str(tmp_path / "f.png"),
                     "--usage", str(tmp_path / "f.json")]) == 0
    assert json.loads((tmp_path / "f.json").read_text())["cpu_seconds"] > 0


def test_prices_come_from_a_file(tmp_path):
    good = tmp_path / "prices.yaml"
    good.write_text("currency: GBP\nelevenlabs_per_1000_credits: 0.24\ncpu_per_hour: 0.05\n")
    assert Prices.load(good) == Prices("GBP", 0.24, 0.05)
    for text, message in (("elevenlabs_per_1000_credits: -1\n", "0 or more"), ("eleven: 1\n", "unknown prices"),
                          ("- 1\n", "a map")):
        bad = tmp_path / "bad.yaml"
        bad.write_text(text)
        with pytest.raises(PricesError, match=message):
            Prices.load(bad)
    usage = {"speech": {"engine": "elevenlabs", "models": {"m": {"credits": 2000.0}}}, "cpu_seconds": 7200}
    assert costs.price(usage, Prices("GBP", 0.24, 0.05)) == {
        "currency": "GBP", "speech": 0.48, "compute": 0.1, "total": 0.58,
        "prices": {"currency": "GBP", "elevenlabs_per_1000_credits": 0.24, "cpu_per_hour": 0.05}}
    assert costs.price(usage, None) is None


def test_a_job_is_priced_at_the_prices_it_ran_under(tmp_path, monkeypatch):
    monkeypatch.setenv("NARRATE_CACHE", str(tmp_path / "cache"))
    project = {"script": "a.md", "text": "---\nsize: 320x180\n---\n\nHello there.\n"}
    app = create_app(tmp_path / "data", "silent", prices=Prices("USD", 0.3, 3600.0), hosts=["testserver"])
    with TestClient(app) as client:
        first = wait(client, client.post("/v1/jobs", json={"project": project}).json()["id"], "done")
    usage = first["usage"]
    assert usage["cpu_seconds"] > 0 and usage["cost"]["compute"] == pytest.approx(usage["cpu_seconds"], rel=1e-3)
    assert usage["cost"]["prices"]["cpu_per_hour"] == 3600.0
    # The prices change: the first job's cost doesn't
    app = create_app(tmp_path / "data", "silent", prices=Prices("USD", 0.3, 0.0), hosts=["testserver"])
    with TestClient(app) as client:
        second = wait(client, client.post("/v1/jobs", json={"project": project}).json()["id"], "done")
        assert second["usage"]["cost"]["compute"] == 0
        assert client.get(f"/v1/jobs/{first['id']}").json()["usage"]["cost"] == usage["cost"]


def test_usage_reports_by_day_and_by_job(tmp_path):
    store = Store(tmp_path / "data")

    def job(day: str, characters: int, credits: float, total: float, cpu: float) -> str:
        made = store.new_job("build", {"project": {}, "options": {"tts": "elevenlabs"}})
        from datetime import datetime, timezone

        created = datetime.fromisoformat(f"{day}T12:00:00+00:00").astimezone(timezone.utc).timestamp()
        store.update(made["id"], state="done", created=created, usage={
            "speech": {"engine": "elevenlabs", "models": {"eleven_multilingual_v2": {
                "characters": characters, "requests": 1, "cached_characters": 5, "credits": credits}}},
            "video_seconds": 10.0, "wall_seconds": 4.0, "cpu_seconds": cpu,
            "cost": {"currency": "USD", "speech": total - 0.01, "compute": 0.01, "total": total}})
        return made["id"]

    a = job("2026-10-01", 100, 100.0, 0.04, 30.0)
    b = job("2026-10-01", 50, 50.0, 0.025, 10.0)
    c = job("2026-10-03", 10, 10.0, 0.013, 5.0)
    store.db.close()
    with TestClient(create_app(tmp_path / "data", "silent", hosts=["testserver"])) as client:
        days = client.get("/v1/usage", params={"by": "day"}).json()
        assert [(r["day"], r["jobs"], r["characters"], r["credits"]) for r in days["rows"]] == [
            ("2026-10-01", 2, 150, 150.0), ("2026-10-03", 1, 10, 10.0)]
        assert days["totals"]["jobs"] == 3 and days["totals"]["cost_total"] == pytest.approx(0.078)
        assert days["totals"]["cached_characters"] == 15 and days["totals"]["cpu_seconds"] == 45.0
        jobs = client.get("/v1/usage", params={"by": "job", "since": "2026-10-02"}).json()
        assert [r["job"] for r in jobs["rows"]] == [c] and jobs["rows"][0]["engine"] == "elevenlabs"
        until = client.get("/v1/usage", params={"by": "job", "until": "2026-10-01"}).json()
        assert [r["job"] for r in until["rows"]] == [a, b]
        sheet = client.get("/v1/usage", params={"by": "day", "format": "csv"})
        assert sheet.headers["content-type"].startswith("text/csv")
        lines = sheet.text.strip().splitlines()
        assert lines[0].startswith("day,jobs,characters") and lines[-1].startswith("total,3,160")
        assert client.get("/v1/usage", params={"since": "October"}).status_code == 400
        assert client.get("/v1/usage", params={"by": "week"}).status_code == 400


def test_a_paragraph_said_twice_is_sent_once_and_not_counted_as_saved(eleven, tmp_path, monkeypatch):
    # Without prefetching (one request at a time), the second time is the cache's, but it was made in this run
    monkeypatch.setattr(tts.ElevenLabsSynth, "concurrency", 1)
    used = run_audio(tmp_path, "Again and again.\n\nAgain and again.\n", "twice")
    entry = used["speech"]["models"]["eleven_multilingual_v2"]
    assert (entry["characters"], entry["requests"], entry["cached_characters"]) == (16, 1, 0)
    assert len(eleven.sent) == 1
