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
    monkeypatch.setattr(cli, "make_synth", lambda engine, model=None: PartlyCached())
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


def test_an_engine_that_cannot_start_says_so(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    monkeypatch.chdir(tmp_path)  # no .env here
    (tmp_path / "s.md").write_text(SCRIPT)
    assert cli.main(["check", str(tmp_path / "s.md"), "--timing", "--tts", "elevenlabs"]) == 2
    assert "ELEVENLABS_API_KEY" in capsys.readouterr().err


def test_plain_check_is_unchanged(script, capsys):
    assert cli.main(["check", str(script)]) == 0
    assert capsys.readouterr().out.strip() == f"{script}: 2 scenes, 2 blocks, 0 warnings, 0 missing files"
