"""Live ElevenLabs checks: opt in with `just test -m elevenlabs` (spends a few characters of credit)."""

import os
from pathlib import Path

import numpy as np
import pytest

from narrate.cli import load_dotenv
from narrate.tts import SAMPLE_RATE, ElevenLabsSynth

pytestmark = pytest.mark.elevenlabs

load_dotenv(Path(__file__).parent.parent)
if not os.environ.get("ELEVENLABS_API_KEY"):
    pytest.skip("ELEVENLABS_API_KEY is not set", allow_module_level=True)


@pytest.fixture
def synth(tmp_path, monkeypatch):
    monkeypatch.setenv("NARRATE_CACHE", str(tmp_path))  # empty cache: every call goes to the API
    return ElevenLabsSynth()


def test_synthesises_pcm_at_the_pipeline_rate(synth):
    notes: set[str] = set()
    audio = synth.synth("Hi.", synth.resolve("George", None, notes), 1.0, notes)
    assert audio.dtype == np.float32 and SAMPLE_RATE == 24000
    assert 0.2 < len(audio) / SAMPLE_RATE < 3.0
    assert float(np.abs(audio).max()) > 0.01  # speech, not silence


def test_reports_api_errors_clearly(synth):
    with pytest.raises(RuntimeError, match="ElevenLabs request failed"):
        synth.synth("Hi.", synth.resolve("ZZZZZZZZZZZZZZZZZZZZ", None, set()), 1.0, set())


def test_default_model_takes_language_hints(synth):
    notes: set[str] = set()
    audio = synth.synth("Hallo.", synth.resolve("George", "de", notes), 1.0, notes)
    assert len(audio) > 0 and not any("language hints" in n for n in notes)


def test_phonetic_span_is_voiced(synth):
    notes: set[str] = set()
    audio = synth.synth((("Say", None), ("təˈmeɪtoʊ", "ipa")), synth.resolve("George", None, notes), 1.0, notes)
    assert len(audio) / SAMPLE_RATE > 0.5 and float(np.abs(audio).max()) > 0.01


def test_v4_speaks_without_a_speed_setting(tmp_path, monkeypatch):
    monkeypatch.setenv("NARRATE_CACHE", str(tmp_path))
    synth = ElevenLabsSynth("eleven_v4")
    notes: set[str] = set()
    audio = synth.synth("Hi there.", synth.resolve("George", None, notes), 1.0, notes)
    assert synth.speed_range == (1.0, 1.0) and float(np.abs(audio).max()) > 0.01
