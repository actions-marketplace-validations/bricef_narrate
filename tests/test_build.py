"""End-to-end builds with the silent speech backend (timing-only, no models or network)."""

from pathlib import Path

import pytest
from PIL import Image

from narrate import media
from narrate.build import Builder, Visual, _video_duration
from narrate.config import FPS
from narrate.script import parse, parse_file
from narrate.tts import SilentSynth

EXAMPLES = Path(__file__).parent.parent / "reference" / "examples"
CHAR = SilentSynth.seconds_per_char


@pytest.fixture
def project(tmp_path):
    Image.new("RGB", (640, 360), "steelblue").save(tmp_path / "blue.png")
    media.run(["-f", "lavfi", "-i", "testsrc2=size=320x180:rate=30", "-f", "lavfi",
               "-i", "sine=frequency=440", "-t", "2", "-c:v", "libx264", "-pix_fmt", "yuv420p",
               "-c:a", "aac", "-shortest", str(tmp_path / "clip.mp4")])
    return tmp_path


def build(project: Path, text: str, name: str = "out"):
    script_path = project / f"{name}.md"
    script_path.write_text(text)
    builder = Builder(parse_file(script_path), SilentSynth(), log=lambda _: None)
    return builder.build(project / f"{name}.mp4", workdir=project / f"work-{name}")


def frames(seconds: float) -> float:
    return round(seconds * FPS) / FPS


@pytest.mark.parametrize("sync, audio, expected", [
    ("freeze", 1.0, 2.0), ("freeze", 3.0, 3.0), ("match", 3.0, 3.0), ("trim", 1.0, 1.0),
    ("trim", 3.0, 2.0), ("loop", 3.0, 3.0), ("trim-or-loop", 1.0, 1.0), ("loop-audio", 1.0, 2.0),
    ("freeze", 0.0, 2.0),
])
def test_video_sync_durations(sync, audio, expected):
    assert _video_duration(Visual("video", sync=sync, length=2.0), audio, None) == expected


def test_scene_timing_rules(project, tmp_path):
    script = parse(
        "---\nsize: 320x180\n---\n"
        "```\nslide only\n```\n\n---\n"           # 1: text slide with no audio -> 1 s
        "![](blue.png)\n\n(duration: 2.5)\n\n---\n"  # 2: duration
        "Hello there.\n\n(pause-until: 3)\n\n---\n"  # 3: pause-until from scene start
        "![](clip.mp4)\n\nHi.\n\n---\n"           # 4: 2 s clip, short narration, freeze
        "![trim](clip.mp4)\n\n" + "Long words here. " * 6 + "\n",  # 5: trim to the clip
        project / "s.md",
    )
    builder = Builder(script, SilentSynth(), log=lambda _: None)
    durations = [builder.plan_scene(s, tmp_path).duration for s in script.scenes]
    assert durations == pytest.approx([1.0, 2.5, 3.0, 2.0, 2.0], abs=1e-3)


def test_build_end_to_end(project):
    result = build(project, (
        "---\nsize: 320x180\nsubtitles: embed\n---\n\n"
        "![contain](blue.png)\n\nHello there.\n\n---\n\n"
        "```md\n# Title\n* point\n```\n\n(duration: 1)\n\n---\n\n"
        "![](clip.mp4)\n\n(callout:\n  cx: 160\n  cy: 90)\n\n---\n\n"
        "(pause: 0.5)\n\n> caption only\n"
    ))
    hello = len("Hello there.") * CHAR + 0.4
    expected = frames(hello) + 1.0 + 2.0 + 0.5
    assert result.duration == pytest.approx(expected, abs=2 / FPS)
    info = media.probe(result.video)
    assert (info.width, info.height, info.has_audio, info.has_subtitles) == (320, 180, True, True)
    assert info.duration == pytest.approx(result.duration, abs=0.05)
    srt = (project / "out.srt").read_text()
    assert "Hello there." in srt and "caption only" in srt
    assert (project / "out.vtt").exists() and result.poster.exists()


def test_burned_captions_and_custom_font_render(project):
    font = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")
    if not font.exists():
        pytest.skip("needs a TrueType font to copy into the project")
    (project / "bold.ttf").write_bytes(font.read_bytes())
    result = build(project, (
        "---\nsize: 320x180\nsubtitles:\n  mode: overlay\n  font: bold.ttf\n  position: top\n---\n\n"
        "![](blue.png)\n\nCaptioned narration.\n"
    ), name="burn")
    assert media.probe(result.video).has_subtitles is False
    assert not (project / "burn.srt").exists()


@pytest.mark.skipif(not (EXAMPLES / "slides" / "result.mp4").exists(),
                    reason="run scripts/fetch-narakeet-reference.sh --media first")
def test_matches_narakeet_timing_for_the_slides_example(tmp_path):
    """No narration in this example, so timing depends only on the format rules."""
    script = parse_file(EXAMPLES / "slides" / "script" / "source.md")
    result = Builder(script, SilentSynth(), log=lambda _: None).build(tmp_path / "slides.mp4")
    narakeet = media.probe(EXAMPLES / "slides" / "result.mp4").duration
    assert result.duration == pytest.approx(narakeet, abs=0.1)
