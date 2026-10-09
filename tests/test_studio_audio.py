"""Narration playback in the studio (#54): a scene's narration, synthesised for real."""

import wave
from pathlib import Path

import numpy as np
import pytest
from starlette.testclient import TestClient

from narrate.studio.analysis import analyse
from narrate.studio.audio import scene_audio
from narrate.studio.server import create_app
from narrate.tts import SilentSynth


class Tone(SilentSynth):
    """A pretend engine that 'speaks' a steady tone, a little longer than silence would last."""

    name = "tone"

    def synth(self, text, voice, speed, notes, only_cached=False):
        n = len(super().synth(text, voice, speed, notes))
        return (0.3 * np.sin(np.arange(n) * 2 * np.pi * 440 / 24000)).astype(np.float32)


def read_wav(path: Path) -> np.ndarray:
    with wave.open(str(path)) as w:
        assert (w.getnchannels(), w.getframerate()) == (1, 24000)
        return np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").astype(float) / 32768


def test_the_wav_holds_each_paragraph_where_it_is_planned(tmp_path):
    text = "First, a sentence of narration.\n\n(pause: 1)\n\nThen the second paragraph.\n"
    result = scene_audio(text, tmp_path / "s.md", Tone(), 1, tmp_path)
    sound = read_wav(tmp_path / result["url"].removeprefix("/scratch/"))
    first, second = result["paragraphs"]
    assert len(sound) / 24000 == pytest.approx(result["duration"], abs=0.01)
    loud = lambda a, b: np.abs(sound[int(a * 24000):int(b * 24000)]).mean()  # noqa: E731
    assert loud(first["start"], first["end"]) > 0.1
    assert loud(first["end"] + 0.05, second["start"] - 0.05) < 0.001  # the paragraph pause and the (pause: 1)
    assert loud(second["start"], second["end"]) > 0.1


def test_only_the_asked_for_scene_is_synthesised(tmp_path):
    spoken = []

    class Counting(Tone):
        def synth(self, text, voice, speed, notes, only_cached=False):
            spoken.append(text)
            return super().synth(text, voice, speed, notes)

    scene_audio("Scene one.\n\n---\n\nScene two.\n", tmp_path / "s.md", Counting(), 2, tmp_path)
    assert spoken == ["Scene two."]
    with pytest.raises(LookupError):
        scene_audio("Only one scene.\n", tmp_path / "s.md", Tone(), 3, tmp_path)


def test_the_analysis_counts_characters_per_scene(tmp_path):
    class Uncached(SilentSynth):
        def synth(self, text, voice, speed, notes, only_cached=False):
            return None if only_cached else super().synth(text, voice, speed, notes)

    scenes = analyse("Short.\n\n---\n\nA little longer.\n", tmp_path / "s.md", Uncached())["scenes"]
    assert [s["missing_chars"] for s in scenes] == [len("Short."), len("A little longer.")]


def test_the_endpoints(tmp_path, monkeypatch):
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    (tmp_path / "s.md").write_text("Hello there.\n")
    with TestClient(create_app(tmp_path / "s.md", "silent")) as client:
        assert client.post("/api/scenes/1/audio", json={"id": "stale"}).status_code == 409
        analysis = client.post("/api/analyse", json={"text": "Hello there.\n"}).json()
        track = client.post("/api/scenes/1/audio", json={"id": analysis["id"]}).json()
        assert client.get(track["url"]).headers["content-type"].startswith("audio/")
        assert track["paragraphs"][0]["line"] == 1

        refused = client.post("/api/engine", json={"engine": "elevenlabs"})
        assert refused.status_code == 400 and "ELEVENLABS_API_KEY" in refused.json()["error"]
        assert refused.json()["engine"] == "silent"  # unchanged
        assert client.post("/api/engine", json={"engine": "nonsense"}).status_code == 400
        assert client.post("/api/engine", json={"engine": "kokoro"}).json() == {"engine": "kokoro"}
        assert client.post("/api/analyse", json={"text": "Hi.\n"}).json()["engine"] == "kokoro"
