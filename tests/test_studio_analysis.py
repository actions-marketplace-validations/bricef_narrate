"""The studio's live analysis (#52): problems with lines, scenes, timing, what's still to synthesise."""

from pathlib import Path

import numpy as np
import pytest
from starlette.testclient import TestClient

from narrate.build import Builder
from narrate.script import parse_file
from narrate.studio.analysis import analyse
from narrate.studio.server import create_app
from narrate.tts import EstimatingSynth, KokoroSynth, SilentSynth

DEMO = Path(__file__).parent.parent / "examples" / "demo" / "demo.md"


def test_timing_matches_a_builds_plan():
    with_silence = analyse(DEMO.read_text(), DEMO, SilentSynth())
    plans = list(Builder(parse_file(DEMO), SilentSynth(), log=lambda _: None).plans(parse_file(DEMO).scenes, DEMO.parent))
    assert [s["duration"] for s in with_silence["scenes"]] == [round(p.duration, 3) for p in plans]
    assert with_silence["duration"] == pytest.approx(sum(p.duration for p in plans), abs=0.01)
    assert with_silence["missing"] == {"paragraphs": 0, "characters": 0}  # silence is always "cached"
    first = with_silence["scenes"][1]
    assert (first["title"], first["paragraphs"][0]["line"]) == ("sunrise.png", 20)


class HalfCached(SilentSynth):
    """A pretend engine whose cache holds only the paragraphs mentioning a cat."""

    name = "pretend"

    def synth(self, text, voice, speed, notes, only_cached=False):
        if only_cached and "cat" not in str(text):
            return None
        return np.ones(24000, dtype=np.float32) * 0.1  # one second of 'speech'


def test_cached_speech_is_exact_and_the_rest_estimated(tmp_path):
    script = tmp_path / "s.md"
    text = "The cat sat.\n\nThe dog barked loudly.\n"
    result = analyse(text, script, HalfCached())
    cat, dog = result["scenes"][0]["paragraphs"]
    assert (cat["estimated"], dog["estimated"]) == (False, True)
    assert cat["end"] - cat["start"] == pytest.approx(1.0, abs=0.01)  # the cached 'speech'
    assert result["missing"] == {"paragraphs": 1, "characters": len("The dog barked loudly.")}


def test_problems_point_at_their_lines(tmp_path):
    script = tmp_path / "s.md"
    text = ("---\nvoice: Amy\n---\n\n![](missing.png)\n\nHello.\n\n(sparkle: lots)\n\n---\n\n"
            "```render:sketch\nx\n```\n\n---\n\n(voice-speed: 5)\n\nToo fast.\n\n---\n\nStill timed.\n")
    result = analyse(text, script, SilentSynth())
    found = {(p["line"], p["severity"]): p["message"] for p in result["problems"]}
    assert "file not found: missing.png" in found[(5, "error")]
    assert "unknown stage direction" in found[(9, "warning")]
    assert "unknown renderer render:sketch" in found[(13, "error")]
    assert "voice-speed 5" in found[(19, "error")]
    timed = {s["index"]: s["duration"] for s in result["scenes"]}
    assert timed[3] is None and timed[4] is not None  # the bad scene is skipped, the next still timed


def test_a_parse_error_is_reported_at_its_line(tmp_path):
    result = analyse("---\nvoice: Amy\n\nNo end to the header.\n", tmp_path / "s.md", SilentSynth())
    assert result["problems"][0]["line"] == 1 and "not closed" in result["problems"][0]["message"]
    assert result["scenes"] == []


def test_previewing_never_synthesises_or_downloads(tmp_path, monkeypatch):
    monkeypatch.setenv("NARRATE_CACHE", str(tmp_path / "cache"))
    monkeypatch.setenv("NARRATE_TOOLS", str(tmp_path / "tools"))
    result = analyse("Nothing is cached yet.\n\nNor this.\n", tmp_path / "s.md", KokoroSynth())
    assert result["missing"]["paragraphs"] == 2
    assert not (tmp_path / "tools" / "models").exists()  # Kokoro's model wasn't fetched to look in the cache
    assert all(p["estimated"] for p in result["scenes"][0]["paragraphs"])


def test_the_estimator_counts_what_isnt_cached():
    estimator = EstimatingSynth(HalfCached())
    voice = estimator.resolve(None, None, set())
    estimator.synth("A cat.", voice, 1.0, set())
    estimator.synth("A bird.", voice, 1.0, set())
    assert (estimator.estimates, estimator.missing_chars) == (1, len("A bird."))


def test_the_endpoint_analyses_unsaved_text(tmp_path):
    (tmp_path / "s.md").write_text("Saved text.\n")
    with TestClient(create_app(tmp_path / "s.md", "silent", hosts=["testserver"])) as client:
        body = client.post("/api/analyse", json={"text": "Unsaved.\n\n---\n\nTwo scenes now.\n"}).json()
    assert body["engine"] == "silent" and len(body["scenes"]) == 2
    assert (tmp_path / "s.md").read_text() == "Saved text.\n"


def test_an_engine_that_cant_start_is_reported(tmp_path, monkeypatch):
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    (tmp_path / "s.md").write_text("Hi.\n")
    with TestClient(create_app(tmp_path / "s.md", "elevenlabs", hosts=["testserver"])) as client:
        response = client.post("/api/analyse", json={"text": "Hi.\n"})
    assert response.status_code == 503 and "ELEVENLABS_API_KEY" in response.json()["error"]
