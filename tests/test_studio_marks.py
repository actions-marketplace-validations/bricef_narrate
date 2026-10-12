"""Timing marks placed by selecting a word (#75): an HTML scene can time something to that word."""

import re
from pathlib import Path

import pytest
from playwright.sync_api import expect

from narrate.script import Narration, parse
from narrate.ssml import ssml_runs
from narrate.studio.analysis import run
from narrate.studio.edits import EditError, apply, for_editor, index_of, insert_mark
from narrate.text import MARK_RE, speech_runs, ssml_text, subtitle_text
from narrate.tts import SilentSynth

from test_studio_e2e import page, running  # noqa: F401 - the browser fixture

# Every kind of markup narration has, plain and in SSML
PLAIN = [
    "Five hundred pull requests merged by the fleet.",
    "Say *this* now, and **that** later... then ~~quietly~~ stop.",
    "Read `SAR` aloud, the [tomato]{ipa} way, and [Bahnhof]{de} too; see [the docs](https://example.com).",
    "Wait… then go: it's twenty-six, a well-known café, A&B <b>bold</b>.",
    "гвозд^ики and _underlined_ words, snake_case kept.",
]
SSML = [
    '<speak>Five hundred <emphasis level="strong">merged</emphasis> by the fleet.</speak>',
    '<speak>Read <say-as interpret-as="characters">SAR</say-as> and <sub alias="quiet tube">quietube</sub>, '
    '<phoneme alphabet="ipa" ph="təˈmeɪtoʊ">tomato</phoneme>.<break time="1s"/> Then <lang xml:lang="de">Bahnhof</lang>.</speak>',
]


def flat(runs) -> list:
    """What's said, word by word, with each word's language or phonetics and emphasis, and every pause: the
    same however the runs are split where there's no pause, as a mark splits them."""
    out = []
    for r in runs:
        if r.pause:
            out.append(("pause", r.pause))
        for text, tag in ([(r.text, None)] if isinstance(r.text, str) else r.text):
            out += [(word, tag, r.emphasis, r.rate, r.pitch, r.gain) for word in text.split()]
    return out


def spoken(text: str, ssml: bool):
    return ssml_runs(text, "en", set()) if ssml else speech_runs(text, "en", set())


@pytest.mark.parametrize("text, ssml", [(t, False) for t in PLAIN] + [(t, True) for t in SSML])
def test_a_mark_before_any_word_changes_nothing_but_where_the_speech_splits(text, ssml):
    script = text + "\n"
    blocks = len([b for s in parse(script, Path("s.md")).scenes for b in s.blocks])
    for at in range(len(text) + 1):
        change = insert_mark(script, at)
        marked = apply(script, change)
        paragraph = marked.rstrip("\n")
        name = change["insert"][len('<mark name="'):-len('"/>')]
        assert marked[change["select"]["anchor"]:change["select"]["head"]] == name
        # It still parses into the same blocks, says the same words in the same way, and shows the same subtitle
        assert len([b for s in parse(marked, Path("s.md")).scenes for b in s.blocks]) == blocks
        runs = spoken(paragraph, ssml)
        assert flat(runs) == flat(spoken(text, ssml)), (at, paragraph)
        caption = (lambda t: subtitle_text(ssml_text(t) if ssml else t))
        assert caption(paragraph) == caption(text), (at, paragraph)
        # The speech splits at the mark: one run carries it, with words, not a silent run after them
        [carrier] = [r for r in runs if name in r.marks]
        assert carrier.text


@pytest.mark.parametrize("text", ['Wait… — <mark name="a"/>then go.', 'The fleet <mark name="b"/>.',
                                  '( <mark name="c"/>fleet ) arrives.', '<mark name="d"/>Up front.'])
def test_marks_written_by_hand_next_to_punctuation_keep_it_where_it_was(text):
    assert flat(speech_runs(text, "en", set())) == flat(speech_runs(MARK_RE.sub("", text), "en", set()))
    assert sum(len(r.marks) for r in speech_runs(text, "en", set())) == 1


def test_the_mark_goes_before_the_word_at_the_cursor():
    text = "Merged by the fleet, in July.\n"
    for at in (14, 16, 19):  # at the word's start, inside it, at its end
        assert apply(text, insert_mark(text, at)) == 'Merged by the <mark name="fleet"/>fleet, in July.\n'
    # Between words, the next one
    assert apply(text, insert_mark(text, 20)).startswith('Merged by the fleet, <mark name="in"/>in')


@pytest.mark.parametrize("text, at, expected", [
    ("Read `SAR` aloud.", 7, 'Read <mark name="sar"/>`SAR` aloud.'),  # not inside code: it would be spelled
    ("The [tomato]{ipa} way.", 6, 'The <mark name="tomato"/>[tomato]{ipa} way.'),
    ("See [the docs](https://x.y) now.", 18, 'See [the docs](https://x.y) <mark name="now"/>now.'),  # not the address
    ("Say *the fleet* now.", 10, 'Say *the <mark name="fleet"/>fleet* now.'),  # inside emphasis is fine
    ('<speak>A <sub alias="x">word</sub> here.</speak>', 26, '<speak>A <mark name="word"/><sub alias="x">word</sub> here.</speak>'),
    ('<speak>A <emphasis>big</emphasis> one.</speak>', 20, '<speak>A <emphasis><mark name="big"/>big</emphasis> one.</speak>'),
    ("Five 500 Café crème.", 5, 'Five <mark name="mark-500"/>500 Café crème.'),
    ("Five 500 Café crème.", 10, 'Five 500 <mark name="cafe"/>Café crème.'),
])
def test_where_a_mark_goes_and_what_its_called(text, at, expected):
    assert apply(text + "\n", insert_mark(text + "\n", at)) == expected + "\n"


def test_names_stay_unique_in_their_scene():
    text = 'One <mark name="fleet"/>fleet, then the fleet.\n\n---\n\nThe fleet.\n'
    assert '<mark name="fleet-2"/>fleet.' in apply(text, insert_mark(text, text.index("fleet.")))
    assert '<mark name="fleet"/>fleet.\n' in apply(text, insert_mark(text, text.rindex("fleet")))  # another scene
    assert '<mark name="here"/>' in apply(text, insert_mark(text, 4, name="here"))
    with pytest.raises(EditError, match="not a mark name"):
        insert_mark(text, 4, name="2")


@pytest.mark.parametrize("text, line", [
    ("---\nvoice: Amy\n---\n\nHi.\n", 2),
    ("![](photo.jpg)\n\nHi.\n", 1),
    ("(pause: 1)\n\nHi.\n", 1),
    ("> A quote.\n\nHi.\n", 1),
    ("```\nA slide.\n```\n\nHi.\n", 2),
    ("Hi.\n\n\nThere.\n", 3),
])
def test_marks_go_in_narration_only(text, line):
    at = sum(len(row) + 1 for row in text.split("\n")[:line - 1])
    with pytest.raises(EditError, match="narration"):
        insert_mark(text, at)


def test_positions_are_the_editors_utf16_units():
    text = "🚀 Launch day.\n\nThe fleet 🚀 arrives.\n"
    at = text.index("arrives")
    unit = at + 2  # two rockets before it, each two units in the editor
    assert index_of(text, unit) == at
    change = for_editor(text, insert_mark(text, at))
    assert change["from"] == unit and change["insert"] == '<mark name="arrives"/>'
    assert change["select"] == {"anchor": unit + len('<mark name="'), "head": unit + len('<mark name="arrives')}


def test_the_analysis_says_where_each_mark_is_written(tmp_path):
    text = "Hi.\n\n<speak>Five 🚀 hundred. <mark name='fleet'/>A fleet.</speak>\n\n---\n\nThe <mark name=\"x\"/>two.\n"
    scenes = run(text, tmp_path / "s.md", SilentSynth()).report["scenes"]
    # Columns count as the editor does, in UTF-16 units: the rocket is two
    assert scenes[0]["mark_places"] == {"fleet": {"line": 3, "column": 24, "length": 20}}
    assert scenes[1]["mark_places"] == {"x": {"line": 7, "column": 4, "length": 16}}  # plain narration too


# -- in the browser -------------------------------------------------------------------------------------

def test_add_a_mark_from_the_cursor_and_find_it_from_the_timeline(tmp_path, page):  # noqa: F811
    script = tmp_path / "s.md"
    script.write_text("A first paragraph, to start with.\n\nFive hundred pull requests merged by the fleet.\n")
    with running(script) as url:
        page.goto(url)
        page.locator(".cm-line", has_text="merged by the fleet").click()
        page.keyboard.press("End")
        page.keyboard.press("Control+ArrowLeft")  # the cursor before "fleet"
        page.get_by_role("button", name="Add mark").click()
        content = page.locator(".cm-content")
        expect(content).to_contain_text('Five hundred pull requests merged by the <mark name="fleet"/>fleet.')
        flag = page.locator(".tl-mark-name", has_text="fleet")
        expect(flag).to_be_visible()
        page.keyboard.type("arrival")  # the name was selected: typing renames it
        expect(content).to_contain_text('<mark name="arrival"/>fleet.')
        flag = page.locator(".tl-mark-name", has_text="arrival")
        expect(flag).to_be_visible()

        # Alt-M marks another word
        page.locator(".cm-line", has_text="A first paragraph").click()
        page.keyboard.press("Home")
        page.keyboard.press("Control+ArrowRight")
        page.keyboard.press("Control+ArrowRight")  # the end of "first": the word the cursor touches
        page.keyboard.press("Alt+m")
        expect(content).to_contain_text('A <mark name="first"/>first paragraph, to start with.')
        expect(page.locator(".tl-mark-name")).to_have_count(2)

        # The flag leads back to its word, at its moment
        at = re.search(r"at ([\d.]+ s)", flag.get_attribute("title")).group(1)
        flag.click()
        expect(page.locator(".cm-activeLine")).to_contain_text('<mark name="arrival"/>')
        expect(page.get_by_test_id("playhead")).to_have_text(re.compile(rf"^{re.escape(at)} / "))
