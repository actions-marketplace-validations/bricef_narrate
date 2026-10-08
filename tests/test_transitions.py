import re
import subprocess
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from narrate import media
from narrate.build import Builder, transition_graph
from narrate.config import TRANSITIONS, ConfigError, parse_transition
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
