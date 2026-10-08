import numpy as np
import pytest
from PIL import Image

from narrate import media
from narrate.build import Builder, BuildError
from narrate.cli import main
from narrate.narakeet_cli import main as narakeet
from narrate.script import parse_file
from narrate.tts import SAMPLE_RATE, SilentSynth

SCRIPT = "---\nbackground: ukulele-1 2\nsubtitles: external\n---\n\nHello there.\n\n(pause: 1)\n\n---\n\n![](pic.png)\n\nSecond part.\n"


class ToneSynth(SilentSynth):
    name = "tone"

    def synth(self, text, voice, speed, notes):
        n = len(super().synth(text, voice, speed, notes))
        return (0.3 * np.sin(2 * np.pi * 220 * np.arange(n) / SAMPLE_RATE)).astype(np.float32)


@pytest.fixture
def script(tmp_path):
    Image.new("RGB", (64, 36), "teal").save(tmp_path / "pic.png")
    (tmp_path / "s.md").write_text(SCRIPT)
    return tmp_path / "s.md"


def expected_seconds():
    chars = SilentSynth.seconds_per_char
    return (len("Hello there.") * chars + 0.4 + 1.0) + (len("Second part.") * chars + 0.4)


def test_audio_build_mixes_narration_pauses_and_music(script, tmp_path):
    result = Builder(parse_file(script), ToneSynth(), log=lambda _: None).build_audio(tmp_path / "out.mp3")
    assert result.duration == pytest.approx(expected_seconds(), abs=0.05)
    assert media.probe(result.video).duration == pytest.approx(result.duration, abs=0.1)
    assert media.loudness(media.decode_audio(result.video, SAMPLE_RATE), SAMPLE_RATE) > -40
    assert any("ignored in audio output" in n for n in result.notes)
    assert "Second part." in (tmp_path / "out.srt").read_text()


@pytest.mark.parametrize("suffix", [".wav", ".m4a", ".ogg", ".flac"])
def test_audio_formats(script, tmp_path, suffix):
    result = Builder(parse_file(script), SilentSynth(), log=lambda _: None).build_audio(tmp_path / f"out{suffix}")
    info = media.probe(result.video)
    assert info.has_audio and not info.has_video
    assert info.duration == pytest.approx(expected_seconds(), abs=0.1)


def test_unknown_format_is_refused(script, tmp_path):
    with pytest.raises(BuildError, match="unsupported audio format"):
        Builder(parse_file(script), SilentSynth(), log=lambda _: None).build_audio(tmp_path / "out.xyz")


def test_audio_command_and_narakeet_audio_projects(script, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert main(["audio", str(script), "--tts", "silent", "-q"]) == 0
    assert (tmp_path / "s.mp3").exists()
    assert narakeet(["--repository-type", "local-dir", "--repository", str(tmp_path), "--source", "s.md",
                     "--project-type", "audio", "--tts", "silent"]) == 0
    assert media.probe(tmp_path / "result.mp3").has_audio
