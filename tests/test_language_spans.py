import numpy as np
import pytest

from narrate import tts
from narrate.text import speech_runs, speech_text, subtitle_text
from narrate.tts import ElevenLabsSynth, SilentSynth, Voice


def test_language_spans_become_segments():
    (run,) = speech_runs("The German word [See]{de} and the English word See.", "en-gb", set())
    assert run.text == (("The German word", None), ("See", "de"), ("and the English word See.", None))
    assert speech_text(run.text) == "The German word See and the English word See."
    assert subtitle_text("The German word [See]{de-DE}.") == "The German word See."


def test_styles_are_not_languages_and_unknown_ones_are_noted():
    notes: set[str] = set()
    (run,) = speech_runs("Say [tomato]{x-sampa} please.", "en-us", notes)
    assert run.text == "Say tomato please." and any("x-sampa" in n for n in notes)


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
def test_kokoro_reads_the_span_in_its_language(monkeypatch):
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
