import re
import subprocess
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from narrate import media
from narrate.build import Builder, transition_graph
from narrate.config import EXTRA_TRANSITIONS, TRANSITIONS, ConfigError, parse_transition, settings_from_header
from narrate.script import parse_file
from narrate.tts import SilentSynth

EXAMPLES = Path(__file__).parent.parent / "reference" / "examples"


def test_parse_transition_forms():
    assert parse_transition("wipe 0.5") == ("wipe", 0.5)
    assert parse_transition("crossfade") == ("crossfade", 0.2)
    assert parse_transition("1", default_type="slide-left") == ("slide-left", 1.0)
    assert parse_transition("none") is None
    with pytest.raises(ConfigError):
        parse_transition("spin 1")


def test_every_narakeet_transition_exists_in_ffmpeg():
    help_text = subprocess.run([media.ffmpeg(), "-hide_banner", "-h", "filter=xfade"],
                               capture_output=True, text=True).stdout
    # Enum values are listed as "     <name>   <number>   ..FV....... <description>"
    available = set(re.findall(r"^\s+(\w+)\s+-?\d+\s+\.\.F", help_text, re.M))
    assert {"fade", "wiperight", "revealright"} <= available
    assert len(TRANSITIONS) == 26  # 27 names in the docs, less `none`
    assert set(TRANSITIONS.values()) <= available
    assert set(EXTRA_TRANSITIONS.values()) <= available | {"custom"}  # narrate's own (#46)
    assert "custom" in available


def test_transition_starts_at_the_cut_and_keeps_the_length():
    graph = transition_graph([30, 30, 30], [None, ("crossfade", 0.4), None])
    # As in Narakeet: the first scene holds its last frame for 12 frames while
    # the second fades in over its own first 0.4 s, from the cut at 1.0 s
    assert "tpad=stop_mode=clone:stop_duration=0.400000,settb=AVTB[p0]" in graph
    assert "[1:v]fps=30,settb=AVTB[p1]" in graph
    assert "xfade=transition=fade:duration=0.400000:offset=1.000000" in graph
    assert "[x1][p2]concat=n=2" in graph


def test_transition_is_clamped_to_the_incoming_scene():
    graph = transition_graph([60, 10], [None, ("wipe", 2.0)])
    assert "duration=0.333333" in graph  # the 10-frame incoming scene


def colour(path: Path, name: str) -> Path:
    Image.new("RGB", (320, 180), name).save(path)
    return path


def test_crossfade_end_to_end(tmp_path):
    colour(tmp_path / "red.png", "red")
    colour(tmp_path / "blue.png", "blue")
    script = tmp_path / "s.md"
    script.write_text("---\nsize: 320x180\ntransition: crossfade 0.4\n---\n\n![](red.png)\n\n(duration: 1)\n\n"
                      "---\n\n![](blue.png)\n\n(duration: 1)\n")
    result = Builder(parse_file(script), SilentSynth(), log=lambda _: None).build(tmp_path / "out.mp4")
    assert result.duration == pytest.approx(2.0, abs=1 / 30)
    assert media.probe(result.video).duration == pytest.approx(2.0, abs=0.05)

    def rgb(t):
        png = tmp_path / f"{t}.png"
        media.extract_frame(result.video, t, png)
        return np.asarray(Image.open(png).convert("RGB"), dtype=float)[90, 160]

    assert rgb(0.5)[0] > 200 and rgb(1.5)[2] > 200
    assert rgb(0.95)[0] > 200  # red right up to the cut
    r, _, b = rgb(1.2)
    assert 60 < r < 200 and 60 < b < 200  # mid-blend 0.2 s after the cut


def test_transition_into_the_first_scene_is_ignored_with_a_warning(tmp_path):
    colour(tmp_path / "red.png", "red")
    script = tmp_path / "s.md"
    script.write_text("(transition: wipe 0.5)\n\n![](red.png)\n\n(duration: 1)\n")
    parsed = parse_file(script)
    Builder(parsed, SilentSynth(), log=lambda _: None).build(tmp_path / "out.mp4")
    assert any("first scene" in w for w in parsed.warnings)


def test_cuts_and_transitions_mix(tmp_path):
    """A transition after a plain cut used to fail: concat and xfade timebases differed (#38)."""
    for name in ("red", "green", "blue"):
        colour(tmp_path / f"{name}.png", name)
    script = tmp_path / "s.md"
    script.write_text("---\nsize: 320x180\n---\n\n![](red.png)\n\n(duration: 1)\n\n---\n\n![](green.png)\n\n"
                      "(duration: 1)\n\n---\n\n(transition: wipe 0.4)\n\n![](blue.png)\n\n(duration: 1)\n\n---\n\n"
                      "![](red.png)\n\n(duration: 1)\n")
    result = Builder(parse_file(script), SilentSynth(), log=lambda _: None).build(tmp_path / "out.mp4")
    assert media.probe(result.video).duration == pytest.approx(4.0, abs=0.05)


# -- narrate's fades (#46) -------------------------------------------------------

def _brightness(video: Path, t: float) -> float:
    png = video.with_name(f"{video.stem}-{t:.3f}.png")
    media.extract_frame(video, t, png)
    return float(np.asarray(Image.open(png).convert("L"), dtype=float).mean())


def _build(tmp_path: Path, text: str, name: str = "s", audio: bool = False):
    script = tmp_path / f"{name}.md"
    script.write_text(text)
    builder = Builder(parse_file(script), SilentSynth(), log=lambda _: None)
    return builder.build_audio(tmp_path / f"{name}.wav") if audio else builder.build(tmp_path / f"{name}.mp4")


def test_fade_black_dips_through_black_and_keeps_the_length(tmp_path):
    result = _build(tmp_path, "---\nsize: 320x180\ntransition: fade-black 0.6\n---\n\n(canvas: white)\n\n"
                              "(duration: 1)\n\n---\n\n(canvas: white)\n\n(duration: 1)\n")
    assert result.duration == pytest.approx(2.0, abs=0.04)
    levels = [_brightness(result.video, t) for t in (0.95, 1.15, 1.3, 1.45, 1.65)]
    assert levels[0] > 250 and levels[-1] > 250  # before the cut, and after the 0.6 s dip
    assert levels[2] < 15 < levels[1] < 250 and 15 < levels[3] < 250  # darkest half way, from the cut at 1.0 s
    assert abs(levels[1] - levels[3]) < 40  # out and in at the same pace


def test_fade_in_and_out_go_to_black_and_take_the_sound_with_them(tmp_path):
    header = "---\nsize: 320x180\nfade-in: 0.5\nfade-out: 0.5\n---\n\n"
    video = _build(tmp_path, header + "(canvas: white)\n\n(duration: 2)\n").video
    assert _brightness(video, 0.0) < 10 and _brightness(video, 1.0) > 250 and _brightness(video, 1.97) < 30

    media.run(["-f", "lavfi", "-i", "sine=frequency=440:duration=2", str(tmp_path / "tone.wav")])
    result = _build(tmp_path, header + "(audio: tone.wav)\n", "sound", audio=True)
    sound = media.decode_audio(result.video, 24000)
    start, middle, end = (np.abs(sound[a:a + 1200]).mean() for a in (0, 24000, len(sound) - 1200))
    assert start < middle / 5 and end < middle / 5


def test_fades_must_not_be_negative():
    with pytest.raises(ConfigError, match="fade-in"):
        settings_from_header({"fade-in": "-1"}, [])
