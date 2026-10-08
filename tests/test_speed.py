import numpy as np
import pytest

from narrate import media
from narrate.build import Builder
from narrate.script import parse
from narrate.tts import SAMPLE_RATE, SilentSynth, Voice


def test_time_stretch_keeps_pitch_and_scales_length():
    t = np.arange(SAMPLE_RATE) / SAMPLE_RATE
    tone = (0.5 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
    slow = media.time_stretch(tone, SAMPLE_RATE, 0.5)
    assert len(slow) == pytest.approx(2 * len(tone), rel=0.02)
    spectrum = np.abs(np.fft.rfft(slow))
    assert np.fft.rfftfreq(len(slow), 1 / SAMPLE_RATE)[spectrum.argmax()] == pytest.approx(440, abs=5)


class NarrowSynth(SilentSynth):
    """An engine that only renders speeds 0.7-1.2 (like ElevenLabs), with a steady tone."""

    name = "narrow"
    speed_range = (0.7, 1.2)

    def __init__(self):
        self.speeds = []

    def synth(self, text, voice, speed, notes):
        self.speeds.append(speed)
        n = int(SAMPLE_RATE * 2.0 / speed)
        return (0.3 * np.sin(2 * np.pi * 220 * np.arange(n) / SAMPLE_RATE)).astype(np.float32)


@pytest.mark.parametrize("speed, native", [(0.4, 0.7), (1.8, 1.2), (1.0, 1.0)])
def test_speeds_beyond_the_engine_are_stretched(speed, native):
    synth = NarrowSynth()
    builder = Builder(parse("x"), synth, log=lambda _: None)
    audio = builder._speak("text", Voice("v", None), speed)
    assert synth.speeds == [native]
    assert len(audio) / SAMPLE_RATE == pytest.approx(2.0 / speed, rel=0.02)


@pytest.mark.kokoro
@pytest.mark.parametrize("speed", [0.4, 1.8])
def test_kokoro_extreme_speeds_within_five_percent(speed):
    from narrate.tts import KokoroSynth, kokoro_resolve, model_dir, MODEL_FILES

    if not (model_dir() / MODEL_FILES[0]).exists():
        pytest.skip("Kokoro model files not downloaded")
    builder = Builder(parse("x"), KokoroSynth(), log=lambda _: None)
    voice = kokoro_resolve("bm_george", None, set())
    text = "Each paragraph of text becomes narration, and every scene lasts as long as its voice-over."
    ratio = len(builder._speak(text, voice, speed)) / len(builder._speak(text, voice, 1.0))
    assert ratio == pytest.approx(1 / speed, rel=0.05)
