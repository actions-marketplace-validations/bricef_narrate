"""Voices in the studio (#65): the catalogue, auditions, pins, and choosing a voice."""

import wave

import pytest
from starlette.testclient import TestClient

from narrate.studio.edits import EditError, apply, set_header, set_voice
from narrate.studio.server import create_app
from narrate.studio.voices import catalogue, characters, sample_script
from narrate.tts import SilentSynth


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))  # no user-level pins
    monkeypatch.setenv("NARRATE_CACHE", str(tmp_path / "cache"))
    (tmp_path / "voices.yaml").write_text("Narrator:\n  kokoro: bf_lily\n  elevenlabs: Lily\n")
    (tmp_path / "s.md").write_text("---\nvoice: George\nvoice-speed: 1.1\n---\n\nHello there.\n")
    return tmp_path


def test_the_catalogue_says_what_each_voice_becomes(project):
    listed = catalogue(SilentSynth(), project)
    groups = {}
    for v in listed["voices"]:
        groups.setdefault(v["group"], []).append(v)
    assert len(groups["kokoro"]) == 54 and len(groups["elevenlabs"]) == 18
    by_name = {(v["group"], v["name"]): v for v in listed["voices"]}
    assert by_name[("pinned", "narrator")]["resolves"] == "bf_lily"  # the pin, on this engine
    assert by_name[("elevenlabs", "George")]["resolves"] == "bm_george"  # matched by accent and gender
    assert by_name[("narakeet", "Amy")].items() >= {"lang": "en-gb", "gender": "f", "resolves": "bf_emma"}.items()
    assert listed["pins"] == {"narrator": {"kokoro": "bf_lily", "elevenlabs": "Lily"}} and listed["user_pins"] == {}


def test_an_audition_reads_the_sample_as_the_script_would():
    text = sample_script("---\nvoice: George\nvoice-speed: 1.1\n---\n\nThe script.\n", "Amy", "Hear me.\n\nNot this.")
    assert text == "---\nvoice: George\nvoice-speed: 1.1\n---\n\n(voice: Amy)\n\nHear me.\n"
    assert sample_script("No header.\n", "af_heart", "") == "(voice: af_heart)\n\nThis is how this voice reads your script.\n"
    with pytest.raises(ValueError):
        sample_script("", "Amy)\n\n(pause: 9", "x")


def test_an_audition_says_what_it_would_spend(project):
    class Uncached(SilentSynth):
        def synth(self, text, voice, speed, notes, only_cached=False):
            return None if only_cached else super().synth(text, voice, speed, notes)

    text = sample_script("", "Amy", "Twelve chars")
    assert characters(text, project / "s.md", Uncached()) == {"characters": 12, "cached": False}
    assert characters(text, project / "s.md", SilentSynth()) == {"characters": 0, "cached": True}


def test_the_endpoints(project):
    script_text = (project / "s.md").read_text()
    with TestClient(create_app(project / "s.md", "silent")) as client:
        listed = client.get("/api/voices").json()
        assert listed["engine"] == "silent" and "narrator" in listed["pins"]

        played = client.post("/api/voices/audition", json={"text": script_text, "voice": "Narrator", "sample": "Hi."}).json()
        with wave.open(str(client.app.state.session.scratch / played["url"].removeprefix("/scratch/"))) as w:
            assert w.getnframes() > 0
        assert client.post("/api/voices/audition", json={"text": script_text, "voice": "x)y", "sample": "Hi."}).status_code == 400

        saved = client.put("/api/voices/pins", json={"pins": {"Host": {"kokoro": "am_adam"}, "Empty": {"kokoro": ""}}})
        assert saved.status_code == 200
        assert "Host:\n  kokoro: am_adam" in (project / "voices.yaml").read_text()
        assert "Empty" not in (project / "voices.yaml").read_text()  # nothing to pin
        refused = client.put("/api/voices/pins", json={"pins": {"Host": {"kokoro": "nobody"}}})
        assert refused.status_code == 400 and refused.json()["error"].startswith("voices.yaml: Host maps to 'nobody'")
        assert "am_adam" in (project / "voices.yaml").read_text()  # left as it was


def test_choosing_a_voice_for_the_whole_script():
    assert apply("---\nvoice: George\n---\n\nHi.\n", set_header("---\nvoice: George\n---\n\nHi.\n", "voice", "Amy")) == \
        "---\nvoice: Amy\n---\n\nHi.\n"
    assert apply("---\nsize: 720p\n---\n\nHi.\n", set_header("---\nsize: 720p\n---\n\nHi.\n", "voice", "Amy")) == \
        "---\nsize: 720p\nvoice: Amy\n---\n\nHi.\n"
    assert apply("Hi.\n", set_header("Hi.\n", "voice", "Amy")) == "---\nvoice: Amy\n---\n\nHi.\n"


def test_choosing_a_voice_from_the_cursor():
    text = "One.\n\nTwo, and\nmore of two.\n\n---\n\n(voice: Amy)\n\nThree.\n"
    assert apply(text, set_voice(text, 4, "Brian")) == text.replace("Two, and", "(voice: Brian)\n\nTwo, and")
    assert apply(text, set_voice(text, 8, "Brian")) == text.replace("(voice: Amy)", "(voice: Brian)")
    with pytest.raises(EditError, match="scene break"):
        set_voice(text, 6, "Brian")


def test_a_paid_audition_is_priced_first(project):
    class Uncached(SilentSynth):
        name = "elevenlabs"

        def synth(self, text, voice, speed, notes, only_cached=False):
            return None if only_cached else super().synth(text, voice, speed, notes)

    with TestClient(create_app(project / "s.md", "silent")) as client:
        session = client.app.state.session
        session.engine, session._synth = "elevenlabs", Uncached()  # as if ElevenLabs, with nothing cached
        dry = client.post("/api/voices/audition", json={"text": "", "voice": "Lily", "sample": "Ten chars!", "dry": True})
        assert dry.json() == {"characters": 10, "cached": False}
