"""Subtitle outputs chosen at build time (#58): --subtitles, files from every mode, and a transcript."""

import re
import subprocess
import sys
import wave

import numpy as np
import pytest
from PIL import Image

from narrate import media, stt
from narrate.build import Builder, BuildError
from narrate.script import parse
from narrate.tts import SilentSynth

PHRASES = [[(0.0, 0.4, "Welcome"), (0.4, 0.6, "to"), (0.6, 1.1, "London.")],
           [(1.5, 1.8, "This"), (1.8, 2.3, "recording"), (2.3, 2.5, "was"), (2.5, 3.0, "captioned.")]]


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.setenv("NARRATE_CACHE", str(tmp_path / "cache"))
    Image.new("RGB", (320, 180), "black").save(tmp_path / "black.png")
    with wave.open(str(tmp_path / "talk.wav"), "wb") as w:
        w.setnchannels(1), w.setsampwidth(2), w.setframerate(24000)
        w.writeframes(np.zeros(24000 * 3, dtype="<i2").tobytes())
    return tmp_path


def build(project, text, name="out", audio=False, **options):
    builder = Builder(parse(text, project / "s.md"), SilentSynth(), log=lambda _: None, **options)
    work = project / f"work-{name}"
    if audio:
        return builder.build_audio(project / f"{name}.mp3", workdir=work), work
    return builder.build(project / f"{name}.mp4", workdir=work), work


def bright(video, project, t=0.5):
    """How much of the frame's lower part is lit: burned-in captions on a black picture."""
    media.extract_frame(video, t, project / "frame.png")
    pixels = np.asarray(Image.open(project / "frame.png").convert("L"), dtype=float)
    return float((pixels[90:] > 128).mean())


def srt_cues(path):
    return re.findall(r"(\d\d:\d\d:\d\d,\d\d\d) --> (\d\d:\d\d:\d\d,\d\d\d)\n(.+)", path.read_text())


ONE_SCENE = "---\nsize: 320x180\n{header}---\n\n![](black.png)\n\nA caption to read over the black picture.\n"


def test_the_build_chooses_files_over_a_burned_in_header(project):
    text = ONE_SCENE.format(header="subtitles: overlay\n")
    burned, _ = build(project, text, "burned")
    files, _ = build(project, text, "files", subtitles="external")
    assert bright(burned.video, project) > 0.002  # the header's captions, burned in
    assert bright(files.video, project) == 0  # nothing burned in: the build said external
    assert media.probe(files.video).has_subtitles is False
    assert srt_cues(project / "files.srt")[0][2] == "A caption to read over the black picture."
    assert (project / "files.vtt").exists() and files.subtitle_files == [project / "files.srt", project / "files.vtt"]


def test_the_build_burns_in_where_the_header_has_none(project):
    text = ONE_SCENE.format(header="")
    plain, _ = build(project, text, "plain")
    burned, _ = build(project, text, "burned", subtitles="overlay")
    assert bright(plain.video, project) == 0 and not (project / "plain.srt").exists()
    assert bright(burned.video, project) > 0.002
    assert (project / "burned.srt").exists()  # burned in, and the file to upload elsewhere


def test_the_header_keeps_its_style(project):
    text = ONE_SCENE.format(header="subtitles:\n  mode: overlay\n  break: 20\n")
    short, _ = build(project, text, "short", subtitles="external")
    assert bright(short.video, project) == 0  # the build's mode
    assert all(len(cue[2]) <= 20 for cue in srt_cues(project / "short.srt")) and len(srt_cues(project / "short.srt")) > 1


def test_burned_in_captions_and_their_files_agree(project):
    _, work = build(project, ONE_SCENE.format(header="subtitles: overlay-background\n").replace(
        "A caption", "A caption long enough to make two cues, and then some more words beyond that, much more than"
        " a single cue can hold at once on its own"), "both")
    burned = re.findall(r"Dialogue: \d+,(\d+:\d\d:\d\d\.\d\d),(\d+:\d\d:\d\d\.\d\d),[^,]*,[^,]*,\d+,\d+,\d+,[^,]*,(.*)",
                        (work / "captions.ass").read_text())
    cues = srt_cues(project / "both.srt")
    assert len(cues) == len(burned) > 1

    def seconds(stamp):
        h, m, s = stamp.replace(",", ".").split(":")
        return int(h) * 3600 + int(m) * 60 + float(s)

    for (a, b, text), (c, d, ass_text) in zip(cues, burned):
        assert abs(seconds(a) - seconds(c)) < 0.011 and abs(seconds(b) - seconds(d)) < 0.011
        assert re.sub(r"\{[^}]*\}|\\N", " ", ass_text).split() == text.split()


def test_an_unknown_mode_is_refused(project):
    with pytest.raises(BuildError, match="invalid subtitles mode"):
        Builder(parse("Hi.\n", project / "s.md"), SilentSynth(), subtitles="sideways")


# -- the transcript ---------------------------------------------------------------------------

SCRIPT = """---
size: 320x180
---

![](black.png)

The *first* paragraph, with [markup]{en}.

<speak>The second paragraph, <break time="200ms"/> in SSML.</speak>

---

> The quote shows, but it isn't what's said.

What's said instead.

---

(audio: talk.wav)
"""

TRANSCRIPT = """The first paragraph, with markup.
The second paragraph, in SSML.

What's said instead.

Welcome to London. This recording was captioned.
"""


def test_a_transcript_holds_what_is_spoken(project, monkeypatch):
    calls = []
    monkeypatch.setattr(stt, "transcribe", lambda path, language=None: calls.append(path) or PHRASES)
    result, _ = build(project, SCRIPT, "talk", transcript=True)
    assert result.transcript == project / "talk.transcript.txt"
    assert result.transcript.read_text() == TRANSCRIPT
    # Captions and the transcript share one transcription of each recording
    calls.clear()
    build(project, SCRIPT, "both", transcript=True, subtitles="external")
    assert len(calls) == 1 and "Welcome to London." in (project / "both.srt").read_text()


def test_audio_builds_and_the_header_ask_for_it_too(project, monkeypatch):
    monkeypatch.setattr(stt, "transcribe", lambda path, language=None: PHRASES)
    result, _ = build(project, SCRIPT.replace("size: 320x180\n", "size: 320x180\ntranscript: true\n"), "talk", audio=True)
    assert result.transcript == project / "talk.transcript.txt" and result.transcript.read_text() == TRANSCRIPT
    plain, _ = build(project, SCRIPT, "plain", audio=True)
    assert plain.transcript is None and not (project / "plain.transcript.txt").exists()


def test_without_speech_to_text_the_transcript_says_so(project, monkeypatch):
    def missing(path, language=None):
        raise ModuleNotFoundError("No module named 'faster_whisper'")

    monkeypatch.setattr(stt, "transcribe", missing)
    result, _ = build(project, SCRIPT, "deaf", audio=True, transcript=True)
    assert result.transcript.read_text() == TRANSCRIPT.rsplit("\n\n", 1)[0] + "\n"  # the narration, without the recording
    assert "transcript of recorded audio (needs faster-whisper)" in result.notes

    def broken(path, language=None):
        raise RuntimeError("model download failed")

    monkeypatch.setattr(stt, "transcribe", broken)
    result, _ = build(project, SCRIPT, "offline", audio=True, transcript=True)
    assert any(n.startswith("transcript: couldn't transcribe talk.wav") for n in result.notes)


def test_merged_scenes_share_one_block(project):
    text = ("(narration-mode: merge)\n\nOne narration\n\n---\n\nacross two scenes.\n\n(narration-mode: normal)\n\n"
            "---\n\nThen alone.\n")
    result, _ = build(project, text, "merged", audio=True, transcript=True)
    assert result.transcript.read_text() == "One narration\nacross two scenes.\n\nThen alone.\n"


def test_the_command_line(project):
    (project / "s.md").write_text(ONE_SCENE.format(header="subtitles: overlay\n"))
    done = subprocess.run([sys.executable, "-m", "narrate", "build", "s.md", "--tts", "silent", "-q",
                           "--subtitles", "external", "--transcript"], cwd=project, capture_output=True, text=True)
    assert done.returncode == 0, done.stderr
    assert "s.transcript.txt" in done.stdout and "s.srt" in done.stdout
    assert (project / "s.transcript.txt").read_text() == "A caption to read over the black picture.\n"
    refused = subprocess.run([sys.executable, "-m", "narrate", "audio", "s.md", "--subtitles", "sideways"],
                             cwd=project, capture_output=True, text=True)
    assert refused.returncode == 2 and "invalid choice" in refused.stderr
