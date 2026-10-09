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
    library = b'{"voices": [{"name": "Grandpa Joe - warm", "voice_id": "LIBRARYVOICE00000001"}]}'
    monkeypatch.setattr(synth, "_get", lambda url: library)
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


def test_elevenlabs_sends_language_hints(eleven):
    synth, calls = eleven
    synth.synth("Hallo", Voice("x" * 20, "de"), 1.0, set())
    assert calls[-1][1]["language_code"] == "de"


def test_elevenlabs_drops_the_hint_for_models_that_refuse_it(eleven, monkeypatch):
    synth, calls = eleven
    accepted = synth._post

    def picky(voice_id, body):
        if "language_code" in body:
            raise tts.LanguageRejected("language_code is not supported for this model")
        return accepted(voice_id, body)

    monkeypatch.setattr(synth, "_post", picky)
    notes: set[str] = set()
    assert len(synth.synth("Hallo", Voice("x" * 20, "de"), 1.0, notes)) == 2400
    assert synth.model in synth._ignores_language and any("language hints" in n for n in notes)
    synth.synth("Tschüss", Voice("x" * 20, "de"), 1.0, notes)  # remembered: no second refusal
    assert "language_code" not in calls[-1][1]


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


def test_elevenlabs_library_voices_by_name(eleven):
    synth, _ = eleven
    assert synth.resolve("grandpa joe", None, set()).id == "LIBRARYVOICE00000001"


def test_elevenlabs_without_voices_permission_skips_the_library(monkeypatch):
    import urllib.error

    monkeypatch.setenv("ELEVENLABS_API_KEY", "test-key")
    synth = ElevenLabsSynth()

    def denied(url):
        raise urllib.error.HTTPError(url, 401, "missing_permissions", {}, None)

    monkeypatch.setattr(synth, "_get", denied)
    notes: set[str] = set()
    assert synth.resolve("Somebody", None, notes).id == tts.ELEVENLABS_VOICES["george"][0]
    assert any("unknown" in n for n in notes)


def test_accents_fall_back_to_a_related_one():
    notes: set[str] = set()
    assert kokoro_resolve("Nicole", None, notes).id == "bf_emma"  # Australian -> British
    assert kokoro_resolve("Prabhat", None, notes).id == "bm_george"  # Indian English -> British


# -- models without a speed setting (#47) ------------------------------------------

@pytest.mark.parametrize("model, speeds", [("eleven_multilingual_v2", (0.7, 1.2)), ("eleven_v3", (1.0, 1.0)),
                                           ("eleven_v4", (1.0, 1.0)), ("eleven_v3_alpha", (1.0, 1.0))])
def test_v3_and_v4_have_no_native_speed(monkeypatch, model, speeds):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "test-key")
    assert ElevenLabsSynth(model).speed_range == speeds


def test_the_builder_stretches_v4_speech_instead_of_asking_for_a_speed(monkeypatch, tmp_path):
    from narrate.build import Builder
    from narrate.script import parse_file

    monkeypatch.setenv("ELEVENLABS_API_KEY", "test-key")
    monkeypatch.setenv("NARRATE_CACHE", str(tmp_path / "cache"))
    script = tmp_path / "s.md"
    script.write_text("---\nvoice: George\nvoice-speed: 1.2\n---\n\nHello there.\n")
    seconds = {}
    for model in ("eleven_multilingual_v2", "eleven_v4"):
        synth, bodies = ElevenLabsSynth(model), []
        monkeypatch.setattr(synth, "_post", lambda voice_id, body: (bodies.append(body),
                                                                    np.full(24000, 1000, "<i2").tobytes())[1])
        plan = next(Builder(parse_file(script), synth, log=lambda _: None).plans(parse_file(script).scenes, tmp_path))
        seconds[model] = plan.duration - 0.4  # less the paragraph pause
        speeds = [b.get("voice_settings", {}).get("speed") for b in bodies]
        assert speeds == ([1.2] if model == "eleven_multilingual_v2" else [None])
    assert seconds["eleven_multilingual_v2"] == pytest.approx(1.0, abs=0.02)  # the engine's own speed
    assert seconds["eleven_v4"] == pytest.approx(1 / 1.2, abs=0.02)  # stretched by narrate
