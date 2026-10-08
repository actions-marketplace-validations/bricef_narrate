import pytest

from narrate.text import speech_runs, stress_marks, subtitle_text


def test_caret_before_a_cyrillic_vowel_becomes_an_acute_accent():
    assert stress_marks("гвозд^ики") == "гвозди́ки"
    assert stress_marks("гв^оздики") == "гво́здики"
    assert stress_marks("2^10 and x^y") == "210 and xy"  # not stress marks: removed as before


def test_runs_carry_the_stress_and_subtitles_drop_it():
    (run,) = speech_runs("Купите гвозд^ики.", "ru", set())
    assert "и́" in run.text
    assert subtitle_text("Купите гвозд^ики.") == "Купите гвоздики."


@pytest.mark.kokoro
def test_espeak_moves_the_stress_for_kokoro():
    from narrate.tts import MODEL_FILES, KokoroSynth, model_dir

    if not (model_dir() / MODEL_FILES[0]).exists():
        pytest.skip("Kokoro model files not downloaded")
    tokenizer = KokoroSynth()._engine().tokenizer
    plain, marked = tokenizer.phonemize("гвоздики", "ru"), tokenizer.phonemize(stress_marks("гвозд^ики"), "ru")
    assert plain != marked and "ˈi" in marked
