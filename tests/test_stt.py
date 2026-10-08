import numpy as np
import pytest

from narrate import stt
from narrate.build import Builder
from narrate.script import parse_file
from narrate.tts import SilentSynth

PHRASES = [[(0.0, 0.4, "Welcome"), (0.4, 0.6, "to"), (0.6, 1.1, "London.")],
           [(1.5, 1.8, "This"), (1.8, 2.3, "recording"), (2.3, 2.5, "was"), (2.5, 3.0, "captioned.")]]


def test_captions_follow_words_and_phrases():
    assert stt.captions(PHRASES, 135) == [(0.0, 1.1, "Welcome to London."), (1.5, 3.0, "This recording was captioned.")]
    assert stt.captions(PHRASES[1:], 16) == [(1.5, 2.3, "This recording"), (2.3, 3.0, "was captioned.")]


def test_recordings_are_captioned_where_they_play(tmp_path, monkeypatch):
    import wave

    with wave.open(str(tmp_path / "talk.wav"), "wb") as w:
        w.setnchannels(1), w.setsampwidth(2), w.setframerate(24000)
        w.writeframes(np.zeros(24000 * 3, dtype="<i2").tobytes())
    monkeypatch.setattr(stt, "transcribe", lambda path, language=None: PHRASES)
    script = tmp_path / "s.md"
    script.write_text("---\nsubtitles: external\n---\n\nFirst some speech.\n\n(audio: talk.wav)\n")
    parsed = parse_file(script)
    plan = Builder(parsed, SilentSynth(), log=lambda _: None).plan_scene(parsed.scenes[0], tmp_path)
    speech = len("First some speech.") * SilentSynth.seconds_per_char + 0.4
    texts = [(round(c.start, 2), c.text) for c in plan.cues]
    assert texts[0][1] == "First some speech."
    assert texts[1] == (round(speech, 2), "Welcome to London.")
    assert texts[2][1] == "This recording was captioned."


@pytest.mark.stt
def test_transcribes_real_speech(tmp_path, monkeypatch):
    import wave

    from narrate.tts import MODEL_FILES, KokoroSynth, kokoro_resolve, model_dir

    if not (model_dir() / MODEL_FILES[0]).exists():
        pytest.skip("Kokoro model files not downloaded")
    audio = KokoroSynth().synth("Welcome to London, this was recorded earlier.", kokoro_resolve("bm_george", None, set()),
                                1.0, set())
    with wave.open(str(tmp_path / "talk.wav"), "wb") as w:
        w.setnchannels(1), w.setsampwidth(2), w.setframerate(24000)
        w.writeframes((np.clip(audio, -1, 1) * 32767).astype("<i2").tobytes())
    monkeypatch.setenv("NARRATE_CACHE", str(tmp_path / "cache"))
    words = [w.lower().strip(".,") for phrase in stt.transcribe(tmp_path / "talk.wav") for _, _, w in phrase]
    assert {"welcome", "london", "recorded"} <= set(words)
