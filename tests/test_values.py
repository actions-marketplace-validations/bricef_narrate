import pytest

from narrate.config import ConfigError, parse_color, parse_size, parse_speed, parse_subtitles, parse_time
from narrate.subtitles import narration_cues, spread, split_text, to_srt, to_vtt
from narrate.text import speech_parts, spell, subtitle_text


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


def test_speech_parts_strip_markup_spell_and_split_on_ellipsis():
    notes: set[str] = set()
    parts = speech_parts("My name is **Bond**… James `SAR` [tomato]{ipa}.", "en-us", notes)
    assert parts == ["My name is Bond", "James ess, ay, ar tomato."]
    assert any("ipa" in n for n in notes)


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
