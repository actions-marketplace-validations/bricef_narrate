import os
from pathlib import Path

import numpy as np
import pytest

from narrate import tts
from narrate.tts import ElevenLabsSynth, Voice, kokoro_resolve


@pytest.fixture(autouse=True)
def isolated_cache(tmp_path, monkeypatch):
    monkeypatch.setenv("NARRATE_CACHE", str(tmp_path / "cache"))


def test_kokoro_resolution():
    notes: set[str] = set()
    assert kokoro_resolve("bf_emma", None, notes) == Voice("bf_emma", "en-gb")
    assert kokoro_resolve("Sarah", None, notes).id == "af_sarah"  # same-named voice
    assert kokoro_resolve("Victoria", None, notes).id == "bf_emma"  # Narakeet name by profile
    assert kokoro_resolve("Monika", None, notes) == Voice("af_heart", "de")  # no German voice
    assert kokoro_resolve("xenobot/de-DE", None, notes).lang == "de"
    assert kokoro_resolve(None, "fr", notes) == Voice("af_heart", "fr-fr")


@pytest.fixture
def eleven(monkeypatch):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "test-key")
    synth = ElevenLabsSynth()
    calls = []

    def fake_post(voice_id, body):
        calls.append((voice_id, body))
        return (np.ones(2400, dtype="<i2") * 1000).tobytes()

    monkeypatch.setattr(synth, "_post", fake_post)
    return synth, calls


def test_elevenlabs_resolution(eleven):
    synth, _ = eleven
    notes: set[str] = set()
    assert synth.resolve("George", None, notes) == Voice("JBFqnCBsd6RMkjVDRZzb", None)
    assert synth.resolve("bf_emma", None, notes).id == tts.ELEVENLABS_VOICES["alice"][0]
    assert synth.resolve("Monika", None, notes) == Voice(tts.ELEVENLABS_VOICES["sarah"][0], "de")
    assert synth.resolve("AbCdEfGhIjKlMnOpQrSt", "fr-CA", notes) == Voice("AbCdEfGhIjKlMnOpQrSt", "fr")


def test_elevenlabs_request_body_speed_clamp_and_cache(eleven):
    synth, calls = eleven
    notes: set[str] = set()
    voice = Voice("JBFqnCBsd6RMkjVDRZzb", None)
    audio = synth.synth("Hello", voice, 2.0, notes)
    assert len(audio) == 2400 and audio.dtype == np.float32
    assert calls == [("JBFqnCBsd6RMkjVDRZzb",
                      {"text": "Hello", "model_id": "eleven_multilingual_v2", "voice_settings": {"speed": 1.2}})]
    assert any("clamped" in n for n in notes)
    synth.synth("Hello", voice, 2.0, notes)
    assert len(calls) == 1  # second call served from the cache


def test_elevenlabs_language_code_only_for_models_that_take_it(eleven, monkeypatch):
    synth, calls = eleven
    notes: set[str] = set()
    synth.synth("Hallo", Voice("x" * 20, "de"), 1.0, notes)
    assert "language_code" not in calls[-1][1]
    synth.model = "eleven_flash_v2_5"
    synth.synth("Hallo", Voice("x" * 20, "de"), 1.0, notes)
    assert calls[-1][1]["language_code"] == "de"


def test_auto_picks_elevenlabs_only_with_a_key(monkeypatch):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "k")
    assert tts.make_synth("auto").name == "elevenlabs"


@pytest.mark.kokoro
def test_kokoro_synthesis(monkeypatch):
    real = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "narrate/models/kokoro-v1.0"
    if not (real / tts.MODEL_FILES[0]).exists():
        pytest.skip("Kokoro model files not downloaded (narrate models)")
    monkeypatch.setattr(tts, "model_dir", lambda: real)
    synth = tts.KokoroSynth()
    audio = synth.synth("Welcome to London.", kokoro_resolve("bm_george", None, set()), 1.0, set())
    assert 0.5 < len(audio) / tts.SAMPLE_RATE < 5
    assert float(np.abs(audio).max()) > 0.05
