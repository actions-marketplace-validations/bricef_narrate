from pathlib import Path

import pytest

from narrate.script import Directive, Media, Narration, Quote, ScriptError, Slide, parse, parse_file

EXAMPLES = Path(__file__).parent.parent / "reference" / "examples"


def blocks(text: str, scene: int = 0):
    return parse(text).scenes[scene].blocks


def test_header_is_yaml_and_scalars_stay_strings():
    s = parse("---\nsize: 720p\nnarration-language: no\ncanvas: \"#00FF76\"\n---\n\nHello\n")
    assert s.header == {"size": "720p", "narration-language": "no", "canvas": "#00FF76"}
    assert [type(b) for b in s.scenes[0].blocks] == [Narration]


def test_unclosed_header_is_an_error():
    with pytest.raises(ScriptError):
        parse("---\nsize: 720p\n")


def test_scenes_split_on_dashes_but_not_inside_fences():
    s = parse("one\n\n---\n\n```yml\n---\nvoice: x\n---\n```\n\n----\n\nthree\n")
    assert len(s.scenes) == 3
    assert s.scenes[1].blocks == [Slide(lang="yml", text="---\nvoice: x\n---", line=5)]


def test_comments_are_removed_before_directives_are_recognised():
    s = parse("![](a.jpg)\n\n<!--\n\n(audio: file.mp3)\n\n-->\n\nWelcome\n")
    assert [type(b) for b in s.scenes[0].blocks] == [Media, Narration]


def test_a_line_wholly_commented_does_not_split_a_paragraph():
    assert blocks("first part\n<!-- note -->\nsecond part\n") == [
        Narration(text="first part second part", line=1)
    ]


def test_stacked_single_line_directives():
    bs = blocks("(canvas: sienna)\n(duration: 1)\n(transition: circle 0.5)\n\n```md\n# circle\n```\n")
    assert [(b.key, b.value) for b in bs if isinstance(b, Directive)] == [
        ("canvas", "sienna"), ("duration", "1"), ("transition", "circle 0.5"),
    ]


def test_directive_straight_after_a_fence():
    bs = blocks("```md\n## narakeet.com\n```\n(pause: 3)\n")
    assert isinstance(bs[0], Slide) and bs[1] == Directive("pause", "3", 4)


def test_multiline_directive_is_a_yaml_map():
    bs = blocks("(callout:\n  type: rectangle\n  left: 450\n  top: 0\n  right: 770\n  bottom: 130)\n")
    assert bs == [Directive("callout", {"type": "rectangle", "left": "450", "top": "0",
                                        "right": "770", "bottom": "130"}, 1)]


def test_parenthetical_narration_is_not_a_directive():
    bs = blocks("(As it happens: nobody knew) and the story goes on.\n")
    assert [type(b) for b in bs] == [Narration]


def test_unknown_lowercase_directive_is_ignored_with_a_warning():
    s = parse("(sparkle: lots)\n\nHello\n")
    assert [type(b) for b in s.scenes[0].blocks] == [Narration]
    assert any("sparkle" in w for w in s.warnings)


def test_spaced_key_typo_is_accepted():
    s = parse("(narration mode: fragment)\n")
    assert s.scenes[0].blocks == [Directive("narration-mode", "fragment", 1)]


def test_media_alt_tokens():
    (m,) = blocks("![00-08 match](screen.mp4)\n")
    assert (m.kind, m.segment, m.sync) == ("video", ("00", "08"), "match")
    (m,) = blocks("![cover top-left](a.png)\n")
    assert (m.kind, m.size, m.position) == ("image", "cover", "top-left")
    (m,) = blocks("![end](clip.mov)\n")
    assert m.segment == ("end", None)
    (m,) = blocks("![mute](clip.mp4)\n")
    assert m.volume == 0.0


def test_media_directive_form_allows_spaced_segments():
    (m,) = blocks("(video:\n  file: birds.mp4\n  segment: 00:02 - end\n  volume: 0.5)\n")
    assert (m.path, m.segment, m.volume) == ("birds.mp4", ("00:02", "end"), 0.5)


def test_quotes_and_empty_quote():
    assert blocks("> first\n> second\n\n>\n") == [Quote("first\nsecond", 1), Quote("", 4)]


def test_ssml_paragraph():
    (b,) = blocks("<speak>\n  <prosody rate=\"slow\">Hi</prosody>\n</speak>\n")
    assert b.ssml and "<prosody" in b.text


@pytest.mark.skipif(not EXAMPLES.is_dir(), reason="run scripts/fetch-narakeet-reference.sh first")
def test_every_narakeet_example_parses_without_warnings():
    scripts = [p for p in EXAMPLES.rglob("*") if p.suffix in (".md", ".txt") and "script" in p.parts or p.name == "video.md"]
    assert len(scripts) >= 20
    for path in scripts:
        script = parse_file(path)
        assert script.scenes, path
        assert script.warnings == [], (path, script.warnings)


@pytest.mark.skipif(not EXAMPLES.is_dir(), reason="run scripts/fetch-narakeet-reference.sh first")
def test_narakeet_example_structure():
    types = parse_file(EXAMPLES / "transition-types" / "script" / "source.md")
    assert len(types.scenes) == 25
    assert sum(isinstance(b, Directive) for s in types.scenes for b in s.blocks) == 73
    voices = parse_file(EXAMPLES / "voices" / "script" / "source.md")
    assert len(voices.scenes) == 5
