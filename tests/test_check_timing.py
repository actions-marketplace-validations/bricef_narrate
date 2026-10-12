"""`narrate check --timing` (#66): scene lengths and what synthesis would cost, before building."""

import json

import pytest

from narrate import cli
from narrate.studio.analysis import analyse
from narrate.tts import SilentSynth

SCRIPT = "---\nsize: 320x180\n---\n\nSpoken already.\n\n---\n\nNot spoken yet, so estimated.\n"


class PartlyCached(SilentSynth):
    """Silent speech with only some of it 'in the cache'."""

    name = "kokoro"

    def synth(self, text, voice, speed, notes, only_cached=False):
        if only_cached and "already" not in text:
            return None
        return super().synth(text, voice, speed, notes)


@pytest.fixture
def script(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "make_synth", lambda engine, model=None, planning=False: PartlyCached())
    path = tmp_path / "s.md"
    path.write_text(SCRIPT)
    return path


def test_the_table_says_each_scene_and_what_is_left_to_synthesise(script, capsys):
    assert cli.main(["check", str(script), "--timing"]) == 0
    out = capsys.readouterr().out.splitlines()
    report = analyse(SCRIPT, script, PartlyCached())  # what the studio would say
    one, two = report["scenes"]
    assert out[0] == f"{script}: 2 scenes, {report['duration']:.1f}s with Kokoro"
    assert out[1] == f"    1   0:00.0   {one['duration']:5.1f}s  Spoken already."
    assert out[2].startswith("    2   0:0") and f"≈{two['duration']:5.1f}s" in out[2]  # estimated
    assert out[3] == f"to synthesise: 1 paragraphs, {len('Not spoken yet, so estimated.')} characters (Kokoro: free)"
    assert out[4].startswith("≈ estimated from the text")


def test_bad_values_are_errors_with_their_lines(script, capsys):
    script.write_text(SCRIPT.replace("Not spoken yet", "(duration: soon)\n\nNot spoken yet"))
    assert cli.main(["check", str(script), "--timing"]) == 1
    err = capsys.readouterr().err
    assert f"error: {script}: line 9: invalid duration" in err


def test_json_is_the_studio_report(script, capsys):
    assert cli.main(["check", str(script), "--json"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["engine"] == "kokoro"
    assert report["missing"] == {"paragraphs": 1, "characters": len("Not spoken yet, so estimated.")}
    assert [s["index"] for s in report["scenes"]] == [1, 2] and report["duration"] > 0


def test_plain_check_is_unchanged(script, capsys):
    assert cli.main(["check", str(script)]) == 0
    assert capsys.readouterr().out.strip() == f"{script}: 2 scenes, 2 blocks, 0 warnings, 0 missing files"


# -- ElevenLabs priced without a key (#71) ----------------------------------------------------

@pytest.fixture
def keyless(tmp_path, monkeypatch):
    """No ElevenLabs key anywhere, and any network call fails the test."""
    import urllib.request

    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    monkeypatch.chdir(tmp_path)  # no .env here
    monkeypatch.setenv("NARRATE_CACHE", str(tmp_path / "cache"))

    def no_network(*args, **kwargs):
        raise AssertionError("no network call without a key")

    monkeypatch.setattr(urllib.request, "urlopen", no_network)
    path = tmp_path / "s.md"
    path.write_text("---\nvoice: Lily\n---\n\nAlready spoken.\n\n---\n\n(voice: Somebody Unknown)\n\nNot spoken yet.\n")
    return path


def test_elevenlabs_is_priced_without_a_key(keyless, capsys):
    import numpy as np

    from narrate.tts import ElevenLabsSynth, make_synth

    # One paragraph is in ElevenLabs' cache already: it's exact, and costs nothing more
    engine = make_synth("elevenlabs", planning=True)
    voice = engine.resolve("Lily", None, set())
    cached = engine._cache.path(engine.model, "Already spoken.", voice.id, voice.lang, 1.0)
    np.save(cached, np.zeros(24000, dtype=np.float32))

    assert cli.main(["check", str(keyless), "--timing", "--tts", "elevenlabs"]) == 0
    out = capsys.readouterr()
    assert f"to synthesise: 1 paragraphs, {len('Not spoken yet.')} characters (ElevenLabs: spends ElevenLabs credits)" \
        in out.out
    assert "note: no ELEVENLABS_API_KEY: timed and priced from the cache and estimates" in out.err
    assert cli.main(["check", str(keyless), "--json", "--tts", "elevenlabs"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["engine"] == "elevenlabs" and report["missing"]["characters"] == len("Not spoken yet.")
    with pytest.raises(RuntimeError, match="ELEVENLABS_API_KEY is not set"):  # planning never synthesises
        engine.synth("Not spoken yet.", voice, 1.0, set())
    with pytest.raises(RuntimeError, match="ELEVENLABS_API_KEY is not set"):  # and building needs the key
        ElevenLabsSynth()


@pytest.mark.parametrize("command", ["build", "audio"])
def test_building_with_elevenlabs_still_needs_the_key(keyless, capsys, command):
    assert cli.main([command, str(keyless), "--tts", "elevenlabs"]) == 2
    assert "ELEVENLABS_API_KEY is not set" in capsys.readouterr().err


def test_frames_time_scenes_with_elevenlabs_without_a_key(keyless, tmp_path, capsys):
    from narrate import media

    clip = tmp_path / "clip.mp4"
    media.run(["-f", "lavfi", "-i", "color=c=teal:s=160x90:d=2:r=30", "-pix_fmt", "yuv420p", str(clip)])
    script = tmp_path / "two.md"
    script.write_text("```\nOne\n```\n\n(duration: 1)\n\n---\n\n```\nTwo\n```\n\n(duration: 1)\n")
    assert cli.main(["frames", str(clip), "--script", str(script), "--tts", "elevenlabs", "--width", "160"]) == 0
    assert "scene 2 · Two" in capsys.readouterr().out
