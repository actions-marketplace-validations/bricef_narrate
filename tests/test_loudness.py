import subprocess

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


# -- loudness target for the finished mix (#48) ------------------------------------

def _tone(tmp_path, volume=0.05):
    media.run(["-f", "lavfi", "-i", f"sine=frequency=330:duration=3,volume={volume}", str(tmp_path / "tone.wav")])


def _build_with(tmp_path, header: str, body: str, out: str):
    from narrate.build import Builder
    from narrate.script import parse_file
    from narrate.tts import SilentSynth

    script = tmp_path / "s.md"
    script.write_text(f"---\nsize: 320x180\n{header}---\n\n{body}")
    builder = Builder(parse_file(script), SilentSynth(), log=lambda _: None)
    return builder.build_audio(tmp_path / out) if out.endswith(".wav") else builder.build(tmp_path / out)


def test_loudness_takes_lufs_or_a_preset():
    from narrate.config import ConfigError, parse_loudness

    assert (parse_loudness("-16"), parse_loudness("web"), parse_loudness("broadcast"), parse_loudness("-14 LUFS")) \
        == (-16.0, -16.0, -23.0, -14.0)
    with pytest.raises(ConfigError):
        parse_loudness("0")


@pytest.mark.parametrize("setting, target", [("-16", -16.0), ("broadcast", -23.0)])
def test_the_finished_mix_meets_the_target(tmp_path, setting, target):
    _tone(tmp_path)
    before = media.loudness(media.decode_audio(tmp_path / "tone.wav", 24000), 24000)
    result = _build_with(tmp_path, f"loudness: {setting}\n", "(audio: tone.wav)\n", "out.wav")
    sound = media.decode_audio(result.video, 24000)
    assert before < -28  # a quiet recording, brought up
    assert media.loudness(sound, 24000) == pytest.approx(target, abs=0.5)
    assert float(np.abs(sound).max()) < 10 ** (-1 / 20)  # peaks below -1 dBFS


def test_video_builds_keep_48_khz_aac_at_the_target(tmp_path):
    _tone(tmp_path)
    video = _build_with(tmp_path, "loudness: -16\n", "(audio: tone.wav)\n", "out.mp4").video
    info = subprocess.run([media.ffmpeg(), "-hide_banner", "-i", str(video)], capture_output=True, text=True).stderr
    assert "48000 Hz" in info  # loudnorm runs at 192 kHz; the mix comes back to its own rate
    assert media.loudness(media.decode_audio(video, 24000), 24000) == pytest.approx(-16, abs=0.7)


def test_silence_is_left_alone(tmp_path):
    result = _build_with(tmp_path, "loudness: -16\n", "Some narration.\n", "out.wav")  # SilentSynth: silence
    assert float(np.abs(media.decode_audio(result.video, 24000)).max()) == 0.0
