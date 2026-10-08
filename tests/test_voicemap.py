import pytest

from narrate import voicemap
from narrate.build import Builder
from narrate.cli import main
from narrate.script import parse
from narrate.tts import SilentSynth


@pytest.fixture
def config(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    return tmp_path


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def test_project_file_overrides_user_file_by_name(config):
    write(config / "config" / "narrate" / "voices.yaml", "Brian:\n  kokoro: bm_daniel\n  elevenlabs: Daniel\n")
    write(config / "proj" / "voices.yaml", "Brian:\n  kokoro: bm_lewis\n")
    mapping = voicemap.load(config / "proj")
    assert mapping == {"brian": {"kokoro": "bm_lewis", "elevenlabs": "Daniel"}}
    assert voicemap.apply(mapping, "Brian/en-GB", "elevenlabs") == "Daniel/en-GB"
    assert voicemap.apply(mapping, "Brian", "silent") == "bm_lewis"
    assert voicemap.apply(mapping, "Amy", "kokoro") == "Amy"


def test_invalid_entries_are_reported(config):
    write(config / "proj" / "voices.yaml", "Brian:\n  kokoro: not_a_voice\n")
    with pytest.raises(voicemap.VoiceMapError, match="not a Kokoro voice"):
        voicemap.load(config / "proj")
    write(config / "proj" / "voices.yaml", "Brian:\n  polly: Brian\n")
    with pytest.raises(voicemap.VoiceMapError, match="unknown engine"):
        voicemap.load(config / "proj")


def test_builder_uses_the_mapping(config):
    write(config / "proj" / "voices.yaml", "Narrator:\n  kokoro: am_onyx\n")
    script = parse("(voice: Narrator)\n\nHello.\n", config / "proj" / "s.md")
    builder = Builder(script, SilentSynth(), log=lambda _: None)
    assert builder._voice("Narrator", None).id == "am_onyx"
    assert not any("Narrator" in n for n in builder.notes)  # pinned, not approximated


def test_voices_command_shows_pins(config, capsys):
    write(config / "proj" / "voices.yaml", "Narrator:\n  kokoro: am_onyx\n")
    write(config / "proj" / "s.md", "Hello\n")
    assert main(["voices", str(config / "proj" / "s.md")]) == 0
    assert "narrator     kokoro: am_onyx" in capsys.readouterr().out
