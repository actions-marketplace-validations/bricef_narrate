import pytest

from narrate.build import Builder
from narrate.script import parse
from narrate.ssml import ssml_runs
from narrate.tts import SilentSynth

EXAMPLE = """<speak>
  <emphasis level="strong">This is an important announcement</emphasis>
  <prosody rate="slow" pitch="-2st">Can you hear me now?</prosody>
  <say-as interpret-as="verbatim">abcdefg</say-as>
</speak>"""


def test_narakeet_example_becomes_three_runs():
    strong, slow, spelled = ssml_runs(EXAMPLE, "en-us", set())
    assert (strong.text, strong.emphasis) == ("This is an important announcement", "strong")
    assert (slow.rate, slow.pitch) == (0.8, pytest.approx(2 ** (-2 / 12)))
    assert spelled.text.startswith("ay, bee, see")


def test_breaks_languages_aliases_and_phonemes():
    runs = ssml_runs('<speak>Hello <break time="1.5s"/> the word <lang xml:lang="de">See</lang> and '
                     '<sub alias="World Wide Web">WWW</sub> say <phoneme alphabet="ipa" ph="təˈmeɪtoʊ">tomato</phoneme>'
                     '</speak>', "en-us", set())
    assert runs[0].text == "Hello"
    assert runs[1].pause == 1.5
    assert runs[1].text == (("the word", None), ("See", "de"), ("and World Wide Web say", None), ("təˈmeɪtoʊ", "ipa"))


def test_prosody_volume_and_percentages():
    (run,) = ssml_runs('<speak><prosody rate="150%" volume="+6dB" pitch="+10%">Loud and fast</prosody></speak>',
                       "en-us", set())
    assert (run.rate, run.gain, run.pitch) == (1.5, 6.0, pytest.approx(1.1))


def test_unknown_tags_keep_their_text_and_are_noted():
    notes: set[str] = set()
    (run,) = ssml_runs('<speak><amazon:effect name="whispered">quietly</amazon:effect> said</speak>', "en-us", notes)
    assert run.text == "quietly said" and any("amazon:effect" in n for n in notes)


def test_an_emphasis_level_ssml_doesnt_have_is_read_as_moderate(tmp_path):
    """#78: it stopped the build with a KeyError."""
    notes: set[str] = set()
    runs = ssml_runs('<speak>A <emphasis level="X-Strong">big</emphasis> one.</speak>', "en", notes)
    assert [r.emphasis for r in runs] == ["none", "moderate", "none"]
    assert notes == {'SSML <emphasis level="x-strong"> (read as moderate)'}
    text = '<speak>A <emphasis level="x-strong">big</emphasis> one.</speak>\n'
    builder = Builder(parse(text, tmp_path / "s.md"), SilentSynth(), log=lambda _: None)
    [plan] = builder.plans(builder.script.scenes, tmp_path)  # spoken, with the moderate bundle
    assert plan.duration > 0 and 'SSML <emphasis level="x-strong"> (read as moderate)' in builder.notes


def test_every_emphasis_level_has_a_sound():
    from narrate.build import EMPHASIS
    from narrate.text import EMPHASIS_LEVELS

    assert set(EMPHASIS) == set(EMPHASIS_LEVELS)


def test_malformed_ssml_falls_back_to_plain_text_with_a_warning():
    script = parse("<speak>broken <prosody rate='slow'>tag</speak>\n")
    builder = Builder(script, SilentSynth(), log=lambda _: None)
    plan = builder.plan_scene(script.scenes[0], None)
    assert len(plan.audio) > 0 and any("well-formed" in w for w in script.warnings)
