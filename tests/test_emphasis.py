import numpy as np
import pytest

from narrate.build import Builder
from narrate.script import parse
from narrate.tts import SAMPLE_RATE, SilentSynth


class ToneSynth(SilentSynth):
    """A steady 220 Hz tone lasting 1 s at speed 1, so prosody changes are measurable."""

    name = "tone"

    def synth(self, text, voice, speed, notes):
        n = int(SAMPLE_RATE / speed)
        return (0.2 * np.sin(2 * np.pi * 220 * np.arange(n) / SAMPLE_RATE)).astype(np.float32)


def measure(audio):
    spectrum = np.abs(np.fft.rfft(audio * np.hanning(len(audio))))
    hz = float(np.fft.rfftfreq(len(audio), 1 / SAMPLE_RATE)[spectrum.argmax()])
    return len(audio) / SAMPLE_RATE, hz, float(np.sqrt(np.mean(audio**2)))


def paragraph_audio(text: str):
    script = parse(text)
    builder = Builder(script, ToneSynth(), log=lambda _: None)
    audio = builder.plan_scene(script.scenes[0], None).audio
    voiced = np.flatnonzero(np.abs(audio) > 1e-4)
    return audio[voiced[0]:voiced[-1] + 1]


def test_strong_emphasis_is_slower_higher_and_louder():
    plain = measure(paragraph_audio("Plain words.\n"))
    strong = measure(paragraph_audio("**Strong words.**\n"))
    assert strong[0] == pytest.approx(plain[0] / 0.92, rel=0.03)
    assert strong[1] == pytest.approx(plain[1] * 2 ** (1.5 / 12), rel=0.02)
    assert 20 * np.log10(strong[2] / plain[2]) == pytest.approx(3.0, abs=0.5)


def test_voice_emphasis_applies_to_following_paragraphs():
    reduced = measure(paragraph_audio("(voice-emphasis: reduced)\n\nQuiet words.\n"))
    plain = measure(paragraph_audio("Quiet words.\n"))
    assert reduced[2] < plain[2] and reduced[0] < plain[0]
