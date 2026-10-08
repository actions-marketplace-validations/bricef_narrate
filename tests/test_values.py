import pytest

from narrate.config import ConfigError, parse_color, parse_size, parse_speed, parse_subtitles, parse_time
from narrate.subtitles import narration_cues, spread, split_text, to_srt, to_vtt
from narrate.text import ELLIPSIS_PAUSE, SENTENCE_PAUSE, speech_runs, spell, subtitle_text


@pytest.mark.parametrize("value, seconds", [
    ("12", 12.0), ("2.5", 2.5), ("01:20", 80.0), ("01:20.5", 80.5), ("1:02:03", 3723.0), (4, 4.0),
])
def test_parse_time(value, seconds):
    assert parse_time(value) == seconds


def test_parse_time_rejects_garbage():
    with pytest.raises(ConfigError):
        parse_time("soon")


def test_sizes_presets_custom_and_even():
    assert parse_size("720p") == (1280, 720)
    assert parse_size("1080p-portait") == parse_size("1080p-portrait") == (1080, 1920)
    assert parse_size("801x601") == (802, 602)


def test_colours():
    assert parse_color("sienna") == "#a0522d"
    assert parse_color("#FF000099") == "#ff000099"
    with pytest.raises(ConfigError):
        parse_color("not-a-colour")


def test_speed_presets_and_range():
    assert parse_speed("slow") < 1 < parse_speed("fast")
    with pytest.raises(ConfigError):
        parse_speed("3")


def test_subtitle_modes_and_map():
    assert parse_subtitles("auto").mode == "overlay"
    assert parse_subtitles("overlay-background").background
    cfg = parse_subtitles({"mode": "overlay", "break": "30", "color": "red", "position": "middle"})
    assert (cfg.break_chars, cfg.color, cfg.position) == (30, "#ff0000", "middle")
    with pytest.raises(ConfigError):
        parse_subtitles({"break": "30"})


def test_speech_runs_spell_split_on_ellipsis_and_carry_emphasis():
    notes: set[str] = set()
    runs = speech_runs("My name is Bond… James `SAR` [tomato]{ipa}.", "en-us", notes)
    assert [(r.text, r.pause) for r in runs] == [("My name is Bond", 0.0), ("James ess, ay, ar tomato.", ELLIPSIS_PAUSE)]
    assert any("ipa" in n for n in notes)


def test_emphasis_markup_splits_into_runs():
    text = ("This is my usual voice. *This is more important.* **This is really important.** "
            "~~This is not so much.~~ This is my normal voice again.")
    runs = speech_runs(text, "en-us", set())
    assert [r.emphasis for r in runs] == ["none", "moderate", "strong", "reduced", "none"]
    assert all(r.pause == SENTENCE_PAUSE for r in runs[1:])


def test_snake_case_is_not_emphasis():
    (run,) = speech_runs("Set my_variable_name to two.", "en-us", set())
    assert run.text == "Set my_variable_name to two." and run.emphasis == "none"


def test_spell_symbols_and_non_english():
    assert spell("a?", "en-gb") == "ay, question mark"
    assert spell("abc", "de") == "a, b, c"


def test_subtitle_text_keeps_words_not_markup():
    assert subtitle_text("Read `SAR` and **this** [See]{de}.") == "Read SAR and this See."


def test_split_and_spread():
    assert split_text("one two three four", 9) == ["one two", "three", "four"]
    cues = spread(0.0, 10.0, ["aaaa", "a"])
    assert [round(c.end, 1) for c in cues] == [8.0, 10.0]
    assert len(narration_cues(1.0, 5.0, "word " * 60, 135)) == 3


def test_srt_and_vtt_format():
    cues = spread(0.0, 1.5, ["hello"])
    assert to_srt(cues) == "1\n00:00:00,000 --> 00:00:01,500\nhello\n\n"
    assert to_vtt(cues).startswith("WEBVTT\n\n00:00:00.000 --> 00:00:01.500\nhello")
