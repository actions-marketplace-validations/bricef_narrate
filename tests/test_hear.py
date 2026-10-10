"""`narrate hear` (#70): what speech-to-text hears, against what the script says."""

import json

import pytest

from narrate import cli, review, stt

SCRIPT = """---
size: 320x180
---

Welcome to quietube, built on yt-dlp.

It lists five hundred and thirty-one videos.

---

<speak>Today it's <emphasis>quiet</emphasis>.</speak>
"""


@pytest.fixture
def heard(monkeypatch, tmp_path):
    """Stub speech-to-text: hear(text) makes the media file 'say' text, one word every half second."""
    media = tmp_path / "video.mp4"
    media.write_bytes(b"not really a video")
    (tmp_path / "s.md").write_text(SCRIPT)

    def hear(text: str):
        words = [(round(k * 0.5, 3), round(k * 0.5 + 0.4, 3), w) for k, w in enumerate(text.split())]
        monkeypatch.setattr(stt, "transcribe", lambda path, language=None: [words])
        return media, tmp_path / "s.md"

    return hear


def run(capsys, *args):
    code = cli.main(["hear", *map(str, args)])
    return code, capsys.readouterr().out


def test_lenient_where_speech_to_text_is(heard, capsys):
    media, script = heard("Welcome to QuietTube, built on YTDLP. It lists 531 videos. To day it's quiet.")
    code, out = run(capsys, media, "--script", script)
    assert code == 0
    assert out.splitlines()[0] == f"{script}: 15 of 15 words heard as written (100%)"
    assert "no differences" in out


def test_differences_say_where_and_when(heard, capsys):
    media, script = heard("Welcome to quiet roob, built on it DLP. It lists 531 videos. Today it's quiet. Thanks for watching.")
    code, out = run(capsys, media, "--script", script)
    lines = out.splitlines()
    assert lines[0] == f"{script}: 13 of 15 words heard as written (87%)"
    assert '   0:01.0  scene 1, line 5: wrote "quietube,", heard "quiet roob,"' in lines
    assert '   0:03.0  scene 1, line 5: wrote "yt-dlp.", heard "it DLP."' in lines
    assert '   0:07.5  heard "Thanks for watching.", not in the script (a recording, or noise)' in lines


def test_words_not_heard(heard, capsys):
    media, script = heard("Welcome to quietube, built on yt-dlp. Today it's quiet.")
    report = json.loads(run(capsys, media, "--script", script, "--json")[1])
    assert report["words"] == 15 and report["heard_as_written"] == 9
    [missing] = report["differences"]
    assert missing == {"kind": "not heard", "wrote": "It lists five hundred and thirty-one videos.", "heard": "",
                       "scene": 1, "line": 7, "at": None}


def test_numbers_split_at_their_separator_are_one(heard, capsys):
    media, script = heard("x")
    script.write_text("We have 1,000 users and 18,400 lists.\n")
    media, _ = heard("We have 1 ,000 users and 18 ,400 lists.")
    assert "6 of 6 words heard as written (100%)" in run(capsys, media, "--script", script)[1]
    assert review.tokens("1") + review.tokens(",000") != review.tokens("1,000")  # what the joining prevents


def test_without_a_script_it_prints_what_it_hears(heard, capsys):
    media, _ = heard("Hello there.")
    code, out = run(capsys, media)
    assert code == 0 and out.strip() == "0:00.0  Hello there."


def test_spoken_numbers():
    assert review.number_words(531) == ["five", "hundred", "thirty", "one"]
    assert review.number_words(18400) == ["eighteen", "thousand", "four", "hundred"]
    assert review.tokens("92%") == ["ninety", "two", "percent"]
    assert review.tokens("Five hundred and thirty-one") == review.tokens("531")
    assert review.tokens("2.5") == ["two", "point", "five"]


def test_a_missing_file_is_an_error(tmp_path, capsys):
    assert cli.main(["hear", str(tmp_path / "nothing.mp4")]) == 2
    assert "not found" in capsys.readouterr().err
