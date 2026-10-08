import numpy as np
import pytest

from narrate import media
from narrate.build import LOUDNESS_TARGET, apply_gain
from narrate.tts import SAMPLE_RATE


def speechlike(level: float, seconds: float = 3.0, seed: int = 0) -> np.ndarray:
    """Noise in syllable-length bursts at a given amplitude, a rough stand-in for a voice."""
    rng = np.random.default_rng(seed)
    n = int(seconds * SAMPLE_RATE)
    envelope = (np.sin(np.arange(n) / SAMPLE_RATE * 2 * np.pi * 3) > -0.2).astype(np.float32)
    return (rng.standard_normal(n) * level * envelope).astype(np.float32)


def test_loudness_measures_and_short_clips_are_unmeasurable():
    loud, quiet = speechlike(0.2), speechlike(0.02)
    assert media.loudness(loud, SAMPLE_RATE) - media.loudness(quiet, SAMPLE_RATE) == pytest.approx(20, abs=0.5)
    assert media.loudness(speechlike(0.2, seconds=0.2), SAMPLE_RATE) is None
    assert media.loudness(np.zeros(SAMPLE_RATE, dtype=np.float32), SAMPLE_RATE) is None


def test_three_voices_normalise_within_one_lu():
    voices = [speechlike(level, seed=i) for i, level in enumerate((0.3, 0.05, 0.012))]
    levels = [media.loudness(apply_gain(v, "normalized"), SAMPLE_RATE) for v in voices]
    assert all(level == pytest.approx(LOUDNESS_TARGET, abs=1.0) for level in levels)
    assert max(levels) - min(levels) < 1.0


def test_short_clips_fall_back_to_rms():
    short = speechlike(0.3, seconds=0.25)
    out = apply_gain(short, "normalized")
    assert float(np.sqrt(np.mean(out**2))) == pytest.approx(10 ** (LOUDNESS_TARGET / 20), rel=0.01)


@pytest.mark.kokoro
def test_kokoro_dialogue_normalises_within_one_lu():
    from narrate.tts import MODEL_FILES, KokoroSynth, kokoro_resolve, model_dir

    if not (model_dir() / MODEL_FILES[0]).exists():
        pytest.skip("Kokoro model files not downloaded")
    synth = KokoroSynth()
    lines = [("bf_emma", "Welcome to the programme, I'm your host."),
             ("am_onyx", "Thank you, it's lovely to be back on the show."),
             ("af_sky", "My question is about dividing by zero, and why it is so hard.")]
    levels = [media.loudness(apply_gain(synth.synth(text, kokoro_resolve(v, None, set()), 1.0, set()), "normalized"),
                             SAMPLE_RATE) for v, text in lines]
    assert max(levels) - min(levels) < 1.0
