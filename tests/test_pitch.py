import numpy as np
import pytest

from narrate import media
from narrate.build import Builder
from narrate.config import ConfigError, parse_pitch
from narrate.script import parse
from narrate.tts import SAMPLE_RATE, SilentSynth


def peak_hz(samples: np.ndarray) -> float:
    spectrum = np.abs(np.fft.rfft(samples * np.hanning(len(samples))))
    return float(np.fft.rfftfreq(len(samples), 1 / SAMPLE_RATE)[spectrum.argmax()])


def tone(hz: float, seconds: float = 1.0) -> np.ndarray:
    return (0.4 * np.sin(2 * np.pi * hz * np.arange(int(seconds * SAMPLE_RATE)) / SAMPLE_RATE)).astype(np.float32)


def test_parse_pitch():
    assert parse_pitch("normal") == 1.0
    assert parse_pitch("high") == pytest.approx(2 ** (2 / 12))
    assert parse_pitch("100") == pytest.approx(2.0) and parse_pitch("-100") == pytest.approx(0.5)
    with pytest.raises(ConfigError):
        parse_pitch("200")


def test_pitch_shift_moves_frequency_and_keeps_length():
    shifted = media.pitch_shift(tone(220), SAMPLE_RATE, 2.0)
    assert len(shifted) == pytest.approx(SAMPLE_RATE, rel=0.01)
    assert peak_hz(shifted) == pytest.approx(440, rel=0.03)


class ToneSynth(SilentSynth):
    name = "tone"

    def synth(self, text, voice, speed, notes):
        return tone(220)


def test_voice_pitch_directive_applies_to_following_narration():
    script = parse("Normal.\n\n(voice-pitch: 100)\n\nHigher.\n")
    builder = Builder(script, ToneSynth(), log=lambda _: None)
    plan = builder.plan_scene(script.scenes[0], None)
    first, second = plan.audio[:SAMPLE_RATE], plan.audio[int(1.4 * SAMPLE_RATE):int(2.4 * SAMPLE_RATE)]
    assert peak_hz(first) == pytest.approx(220, rel=0.03)
    assert peak_hz(second) == pytest.approx(440, rel=0.03)
    assert not any("pitch" in n for n in builder.notes)
