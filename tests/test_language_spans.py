import numpy as np
import pytest

from narrate import tts
from narrate.text import JOIN_PAUSE, speech_runs, speech_text, subtitle_text
from narrate.tts import ElevenLabsSynth, SilentSynth, Voice


def test_language_spans_become_segments():
    (run,) = speech_runs("The German word [See]{de} and the English word See.", "en-gb", set())
    assert run.text == (("The German word", None), ("See", "de"), ("and the English word See.", None))
    assert speech_text(run.text) == "The German word See and the English word See."
    assert subtitle_text("The German word [See]{de-DE}.") == "The German word See."


def test_phonetic_styles_become_segments_and_unknown_ones_are_noted():
    (run,) = speech_runs('Say [t@"meIt@U]{x-sampa} please.', "en-us", set())
    assert run.text == (("Say", None), ('t@"meIt@U', "x-sampa"), ("please.", None))
    notes: set[str] = set()
    (run,) = speech_runs("Say [tomato]{whisper} please.", "en-us", notes)
    assert run.text == "Say tomato please." and any("whisper" in n for n in notes)


def test_an_ellipsis_inside_a_span_does_not_leak_markers():
    runs = speech_runs("Hello [Wie geht's… dir]{de} friend.", "en-us", set())
    assert all("" not in speech_text(r.text) and "" not in speech_text(r.text) for r in runs)


def test_elevenlabs_sends_each_segment_with_its_language(monkeypatch, tmp_path):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "test-key")
    monkeypatch.setenv("NARRATE_CACHE", str(tmp_path))
    synth = ElevenLabsSynth()
    calls = []
    monkeypatch.setattr(synth, "_post", lambda v, body: calls.append(body) or np.zeros(2400, "<i2").tobytes())
    audio = synth.synth((("Buongiorno", None), ("Amy", "en")), Voice("x" * 20, "it"), 1.0, set())
    assert [(c["text"], c.get("language_code")) for c in calls] == [("Buongiorno", "it"), ("Amy", "en")]
    assert len(audio) == 2 * 2400 + int(tts.JOIN_SECONDS * tts.SAMPLE_RATE)


def test_silent_times_the_whole_sentence():
    whole = SilentSynth().synth("Buongiorno Amy", Voice("af_heart", "it"), 1.0, set())
    split = SilentSynth().synth((("Buongiorno", None), ("Amy", "en")), Voice("af_heart", "it"), 1.0, set())
    assert len(whole) == len(split)


@pytest.mark.kokoro
def test_kokoro_reads_the_span_in_its_language(monkeypatch, tmp_path):
    monkeypatch.setenv("NARRATE_CACHE", str(tmp_path))  # synthesise for real, not from the cache
    from narrate.tts import MODEL_FILES, KokoroSynth, kokoro_resolve, model_dir

    if not (model_dir() / MODEL_FILES[0]).exists():
        pytest.skip("Kokoro model files not downloaded")
    synth = KokoroSynth()
    spoken = []
    real_create = synth._engine().create
    monkeypatch.setattr(synth._engine(), "create", lambda phonemes, **kw: spoken.append(phonemes) or real_create(phonemes, **kw))
    voice = kokoro_resolve("bm_george", None, set())
    audio = synth.synth((("The German word", None), ("See", "de"), ("sounds like this.", None)), voice, 1.0, set())
    assert len(audio) > 0 and "zˈeː" in spoken[-1] and "sˈiː" not in spoken[-1]


def test_tags_leave_no_space_before_punctuation():
    """#69: a tag separates words, but "quietube</sub>:" captions as "quietube:"."""
    from narrate.text import ssml_text, subtitle_text

    caption = lambda s: subtitle_text(ssml_text(s))  # noqa: E731 - as the builder captions SSML
    assert caption('<speak><sub alias="quiet tube">quietube</sub>: a quiet feed.</speak>') == "quietube: a quiet feed."
    assert caption("<speak>Say <emphasis>this</emphasis>, then stop.</speak>") == "Say this, then stop."
    assert caption("<speak>(<sub alias='see'>c</sub>) and <emphasis>Bob</emphasis>'s</speak>") == "(c) and Bob's"
    # Between words a tag is still a space, and the text's own spaces stay
    assert caption('<speak>One.<break time="1s"/>Two. <mark name="x"/>Three ?</speak>') == "One. Two. Three ?"


def test_emphasis_after_a_span_is_paused_as_after_any_words():
    """A span's run ends in a segment, not a string: what it ends with is still read (it raised before #75)."""
    runs = speech_runs("Say [See]{de} and *this*.", "en", set())
    assert [r.emphasis for r in runs] == ["none", "moderate"] and runs[1].pause == JOIN_PAUSE
