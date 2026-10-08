import numpy as np
import pytest

from narrate import media, music
from narrate.build import Builder
from narrate.script import parse_file
from narrate.tts import SilentSynth


@pytest.fixture(scope="module")
def rendered(tmp_path_factory):
    import os

    tools = tmp_path_factory.mktemp("tools")
    old = os.environ.get("NARRATE_TOOLS")
    os.environ["NARRATE_TOOLS"] = str(tools)
    try:
        # ffmpeg itself stays where it is: resolve it before switching tools dirs
        yield {name: music.track(name) for name in music.TRACKS}
    finally:
        if old is None:
            os.environ.pop("NARRATE_TOOLS")
        else:
            os.environ["NARRATE_TOOLS"] = old


@pytest.mark.parametrize("name", music.TRACKS)
def test_tracks_render_as_quiet_loops(rendered, name):
    audio = media.decode_audio(rendered[name], music.SR)
    assert len(audio) / music.SR > 15
    assert media.loudness(audio, music.SR) == pytest.approx(music.LEVEL_LUFS, abs=1.0)


def test_rendering_is_deterministic():
    assert np.array_equal(music.ukulele_1(), music.ukulele_1())


def test_user_recordings_take_precedence(tmp_path, monkeypatch):
    own = tmp_path / "corporate-1.mp3"
    own.write_bytes(b"not really an mp3")
    monkeypatch.setenv("NARRATE_MUSIC_DIR", str(tmp_path))
    assert music.track("corporate-1") == own


def test_builtin_track_plays_under_a_script(tmp_path):
    script = tmp_path / "s.md"
    script.write_text("---\nsize: 320x180\nbackground: ukulele-1 fade-in\n---\n\n```\nHi\n```\n\n(duration: 3)\n")
    result = Builder(parse_file(script), SilentSynth(), log=lambda _: None).build(tmp_path / "out.mp4")
    assert not any("ukulele" in n for n in result.notes)
    audio = media.decode_audio(result.video, music.SR)
    assert float(np.sqrt(np.mean(audio[-music.SR:] ** 2))) > 0.003  # music is audible
