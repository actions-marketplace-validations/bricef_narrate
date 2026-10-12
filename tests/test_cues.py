"""Narration cues for HTML scenes (#45): --cue-N, --cue-NAME, --narrate-duration, window.narrate."""

from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from narrate import media
from narrate.build import Builder
from narrate.script import parse_file
from narrate.ssml import ssml_runs
from narrate.tts import SilentSynth

BASE = "html, body { margin: 0; width: 100%; height: 100%; background: #000; }"
REVEAL = (".box { position: absolute; inset: 0; background: #fff; opacity: 0;"
          " animation: show .1s linear %s forwards; } @keyframes show { to { opacity: 1; } }")


def write(tmp_path: Path, script: str, page: str, name: str = "s") -> Path:
    (tmp_path / "scene.html").write_text(f"<!doctype html><style>{BASE}</style><body>{page}</body>")
    path = tmp_path / f"{name}.md"
    path.write_text("---\nsize: 320x180\n---\n\n" + script)
    return path


def plans(path: Path):
    return list(Builder(parse_file(path), SilentSynth(), log=lambda _: None).plans(parse_file(path).scenes, path.parent))


def build(path: Path) -> Path:
    out = path.with_suffix(".mp4")
    Builder(parse_file(path), SilentSynth(), log=lambda _: None).build(out)
    return out


def brightness(video: Path, t: float) -> float:
    png = video.with_name(f"{video.stem}-{t:.3f}.png")
    media.extract_frame(video, t, png)
    return float(np.asarray(Image.open(png).convert("L"), dtype=float).mean())


# -- marks and cue times -------------------------------------------------------

def test_a_mark_splits_the_speech_and_names_the_split():
    notes: set[str] = set()
    runs = ssml_runs('<speak>A hundred <mark name="fleet"/>by the fleet.<mark name="end"/></speak>', "en", notes)
    assert [(r.text, r.marks) for r in runs] == [("A hundred", ()), ("by the fleet.", ("fleet",)), ("", ("end",))]


@pytest.mark.parametrize("name", ["2", "two words", ""])
def test_unusable_mark_names_are_noted(name):
    notes: set[str] = set()
    runs = ssml_runs(f'<speak>One <mark name="{name}"/>two.</speak>', "en", notes)
    assert all(not r.marks for r in runs) and any("<mark" in n for n in notes)


def test_cues_time_each_block_and_mark(tmp_path):
    path = write(tmp_path, "![](scene.html)\n\nThe first paragraph is read out.\n\n(pause: 1)\n\n"
                           '<speak>Then the second, <mark name="fleet"/>with a mark.</speak>\n\n(audio: talk.wav)\n',
                 "")
    media.run(["-f", "lavfi", "-i", "sine=duration=1", str(tmp_path / "talk.wav")])
    marks = plans(path)[0].marks
    first = len("The first paragraph is read out.") * SilentSynth.seconds_per_char
    assert marks["1"] == 0.0
    assert marks["2"] == pytest.approx(first + 0.4 + 1.0, abs=0.01)  # after the paragraph pause and the pause
    assert marks["2"] < marks["fleet"] < marks["3"]  # the recording is the third block


def test_plain_narration_takes_marks_too(tmp_path):
    """#75: a mark in plain narration times the same moment as in SSML, and keeps the paragraph's markup."""
    plain = write(tmp_path, '![](scene.html)\n\nThen the second, *with* <mark name="fleet"/>a mark.\n', "", "plain")
    # The same speech in SSML: plain emphasis is paused as a join, 60 ms, on either side
    ssml = write(tmp_path, '![](scene.html)\n\n<speak>Then the second,<break time="60ms"/> <emphasis>with</emphasis>'
                           '<break time="60ms"/> <mark name="fleet"/>a mark.</speak>\n', "", "ssml")
    assert plans(plain)[0].marks["fleet"] == pytest.approx(plans(ssml)[0].marks["fleet"], abs=1e-6)
    [plan] = plans(plain)
    assert plan.spoken == ["Then the second, with a mark."]  # what's shown and transcribed has no mark


# -- in pages --------------------------------------------------------------------

def test_a_page_reveals_when_the_second_paragraph_starts(tmp_path):
    path = write(tmp_path, "![](scene.html)\n\nA first sentence, read out at length.\n\nAnd a second one.\n",
                 f"<style>{REVEAL % 'var(--cue-2)'}</style><div class=box></div>")
    cue = plans(path)[0].marks["2"]
    out = build(path)
    assert brightness(out, cue - 0.2) < 5
    assert brightness(out, cue + 0.3) > 250


def test_a_page_reveals_at_a_mark(tmp_path):
    path = write(tmp_path, "![](scene.html)\n\n"
                           '<speak>Five hundred and thirty-one merged. <mark name="fleet"/>A hundred and fifty-two '
                           "by the fleet.</speak>\n",
                 f"<style>{REVEAL % 'var(--cue-fleet)'}</style><div class=box></div>")
    cue = plans(path)[0].marks["fleet"]
    out = build(path)
    assert brightness(out, cue - 0.2) < 5 < 250 < brightness(out, cue + 0.3)


def test_narrate_duration_times_an_outro(tmp_path):
    path = write(tmp_path, "![](scene.html)\n\n(duration: 3)\n",
                 "<style>.box { position: absolute; inset: 0; background: #fff;"
                 " animation: hide .1s linear calc(var(--narrate-duration) - 1s) forwards; }"
                 " @keyframes hide { to { opacity: 0; } }</style><div class=box></div>")
    out = build(path)
    assert brightness(out, 1.5) > 250 and brightness(out, 2.6) < 5


def test_scripts_read_window_narrate(tmp_path):
    path = write(tmp_path, "![](scene.html)\n\nOne.\n\nTwo.\n\n(duration: 2)\n",
                 "<script>document.body.style.background ="
                 " narrate.duration === 2 && narrate.cues['2'] > 0 ? '#fff' : '#f00'</script>")
    assert brightness(build(path), 1.0) > 250


def test_cues_count_from_a_later_pages_start(tmp_path):
    (tmp_path / "first.html").write_text("<!doctype html><style>body { background: #00f; }</style>")
    path = write(tmp_path, "![](first.html)\n\n![](scene.html)\n\n"
                           "A long first paragraph that keeps going for quite a while yet.\n\nShort second.\n",
                 f"<style>{REVEAL % 'var(--cue-2)'}</style><div class=box></div>")
    plan = plans(path)[0]
    cue, page_start = plan.marks["2"], plan.layout.pieces[0]
    assert page_start < cue  # the reveal falls in the page's half of the scene
    out = build(path)
    assert brightness(out, cue - 0.2) < 5 and brightness(out, cue + 0.3) > 250  # scene time, not page time
