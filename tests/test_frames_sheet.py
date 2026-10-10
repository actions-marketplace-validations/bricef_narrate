"""`narrate frames` (#67): a contact sheet for reviewing a video without watching it."""

import pytest
from PIL import Image

from narrate import cli, media
from narrate.review import LABEL_HEIGHT


@pytest.fixture
def clip(tmp_path):
    """Six seconds: red, then green, then blue, two seconds each."""
    path = tmp_path / "rgb.mp4"
    media.run(["-f", "lavfi", "-i", "nullsrc=s=160x90:d=6:r=30,format=rgb24,"
               "geq=r='if(lt(T,2),255,0)':g='if(between(T,2,4),255,0)':b='if(gte(T,4),255,0)'",
               "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path)])
    return path


def colours(sheet: Image.Image, cells: int, width: int = 160, height: int = 90) -> list[str]:
    """The main colour of each cell, read in its middle."""
    out = []
    for k in range(cells):
        x, y = (k % 4) * (width + 4) + width // 2, (k // 4) * (height + LABEL_HEIGHT + 4) + height // 2
        r, g, b = sheet.convert("RGB").getpixel((x, y))
        out.append(max((("red", r), ("green", g), ("blue", b)), key=lambda c: c[1])[0])
    return out


def test_frames_spread_evenly_by_default(clip, tmp_path, capsys):
    assert cli.main(["frames", str(clip), "--count", "3", "--width", "160"]) == 0
    printed = capsys.readouterr().out.split()
    sheet = Image.open(tmp_path / "rgb-frames.png")
    assert sheet.size == (3 * 160 + 2 * 4, 90 + LABEL_HEIGHT)
    assert colours(sheet, 3) == ["red", "green", "blue"]  # at 1 s, 3 s and 5 s
    assert printed[:3] == ["0:01.0", "0:03.0", "0:05.0"] and printed[-1].endswith("rgb-frames.png")


def test_frames_at_chosen_moments_and_every_few_seconds(clip, tmp_path):
    assert cli.main(["frames", str(clip), "--at", "4.5,0.5", "--width", "160", "-o", str(tmp_path / "at.png")]) == 0
    assert colours(Image.open(tmp_path / "at.png"), 2) == ["blue", "red"]
    assert cli.main(["frames", str(clip), "--every", "1", "--width", "160", "-o", str(tmp_path / "every.png")]) == 0
    sheet = Image.open(tmp_path / "every.png")
    assert sheet.size == (4 * 160 + 3 * 4, 2 * (90 + LABEL_HEIGHT) + 4)  # six frames: two rows of up to four
    assert colours(sheet, 6) == ["red", "red", "green", "green", "blue", "blue"]


def test_one_frame_per_scene_from_the_script(clip, tmp_path, capsys):
    script = tmp_path / "s.md"
    script.write_text("".join(f"{'---' if k else ''}\n\n```\nScene {k + 1}\n```\n\n(duration: 2)\n\n" for k in range(3)))
    assert cli.main(["frames", str(clip), "--script", str(script), "--tts", "silent", "--width", "160"]) == 0
    out = capsys.readouterr()
    assert "0:01.0  scene 1 · Scene 1" in out.out and "0:05.0  scene 3 · Scene 3" in out.out
    assert colours(Image.open(tmp_path / "rgb-frames.png"), 3) == ["red", "green", "blue"]
    assert "note:" not in out.err  # the script's timing matches the video


def test_a_missing_video_is_an_error(tmp_path, capsys):
    assert cli.main(["frames", str(tmp_path / "nothing.mp4")]) == 2
    assert "not found" in capsys.readouterr().err
