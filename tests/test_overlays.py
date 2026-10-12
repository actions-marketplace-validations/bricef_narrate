"""HTML overlays (#59): web pages laid over a scene, or over the whole video on its own clock."""

import numpy as np
import pytest
from PIL import Image

from narrate import cli, media
from narrate.build import Builder
from narrate.config import ConfigError, parse_overlay, parse_overlays
from narrate.script import parse
from narrate.tts import SilentSynth

W, H = 320, 180

# A box sliding right at 100 px a second, on the page's clock: where it is says what time the page thinks it is
SLIDER = """<!doctype html><style>html,body{margin:0;width:100%;height:100%}
#box{position:absolute;top:20px;left:0;width:20px;height:20px;background:#00ff00;animation:go 3s linear forwards}
@keyframes go{to{left:300px}}</style><div id="box"></div>"""

# Never changes: a magenta block in the bottom-left corner
STILL = """<!doctype html><style>html,body{margin:0;width:100%;height:100%}
.s{position:absolute;left:0;bottom:0;width:40px;height:20px;background:#ff00ff}</style><div class="s"></div>"""

# Its colour comes from a parameter; it appears when the second paragraph starts
CUED = """<!doctype html><style>html,body{margin:0;width:100%;height:100%}
#b{position:absolute;right:0;top:0;width:30px;height:30px;opacity:0;animation:show .01s linear forwards;
animation-delay:var(--cue-2, 9s)}@keyframes show{to{opacity:1}}</style><div id="b"></div>
<script>document.getElementById("b").style.background = window.narrate.params.colour</script>"""


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.setenv("NARRATE_CACHE", str(tmp_path / "cache"))
    for name, colour in (("red.png", "red"), ("blue.png", "blue"), ("grey.png", "grey")):
        Image.new("RGB", (640, 360), colour).save(tmp_path / name)
    (tmp_path / "slider.html").write_text(SLIDER)
    (tmp_path / "still.html").write_text(STILL)
    (tmp_path / "cued.html").write_text(CUED)
    return tmp_path


def build(project, text, name="out", **kwargs):
    logs = []
    script = parse(text, project / "s.md")
    result = Builder(script, SilentSynth(), log=logs.append, **kwargs).build(project / f"{name}.mp4")
    return result, logs


def frame(video, t, project):
    out = project / f"f-{t:.2f}.png"
    media.extract_frame(video, t, out)
    return np.asarray(Image.open(out).convert("RGB"), dtype=int)


def green_left(pixels) -> int | None:
    """Where the slider's box starts across, in the row it slides along, or None if it isn't there."""
    row = pixels[30]
    green = np.where((row[:, 1] > 200) & (row[:, 0] < 80) & (row[:, 2] < 80))[0]
    return int(green[0]) if len(green) else None


def test_the_forms_an_overlay_takes():
    assert parse_overlay("legend.html").file == "legend.html"
    assert parse_overlay("none") is None
    spec = parse_overlay({"file": "lower.html", "name": "Ada", "role": "Lead", "viewport": "1280x720"})
    assert (spec.params, spec.viewport) == ({"name": "Ada", "role": "Lead"}, (1280, 720))
    [ticker, logo] = parse_overlays([{"file": "ticker.html", "scenes": "2-5"}, "logo.html"])
    assert ticker.scenes == (2, 5) and logo.scenes is None
    for bad, message in (("photo.png", "web page"), ({"name": "x"}, "needs a file"), ("none", "belongs in a scene")):
        with pytest.raises(ConfigError, match=message):
            parse_overlays(bad)
    with pytest.raises(ConfigError, match="scene or a range"):
        parse_overlays({"file": "t.html", "scenes": "5-2"})


def test_a_scene_overlay_lies_over_its_scene_only(project):
    text = ("---\nsize: 320x180\n---\n\n![](red.png)\n\n(overlay: still.html)\n\n(duration: 1)\n\n---\n\n"
            "![](blue.png)\n\n(duration: 1)\n")
    result, logs = build(project, text)
    first, second = frame(result.video, 0.5, project), frame(result.video, 1.5, project)
    assert tuple(first[H - 10, 10]) == pytest.approx((255, 0, 255), abs=40)  # the page's block
    assert tuple(first[60, 160]) == pytest.approx((255, 0, 0), abs=40)  # the picture shows through elsewhere
    assert tuple(second[H - 10, 10]) == pytest.approx((0, 0, 255), abs=40)  # gone in the next scene
    assert not any("still.html: overlay captured" in line for line in logs)  # a still page is one picture


def test_parameters_and_cues_reach_the_page(project):
    text = ("---\nsize: 320x180\n---\n\n![](grey.png)\n\n(overlay: {file: cued.html, colour: \"#ffff00\"})\n\n"
            "A first paragraph, long enough to take a little while.\n\nThe second one.\n")
    result, _ = build(project, text)
    from narrate.studio.analysis import analyse

    second = analyse(text, project / "s.md", SilentSynth())["scenes"][0]["paragraphs"][1]["start"]
    before, after = frame(result.video, second - 0.3, project), frame(result.video, second + 0.3, project)
    assert tuple(before[10, W - 10]) == pytest.approx((128, 128, 128), abs=40)  # not yet
    assert tuple(after[10, W - 10]) == pytest.approx((255, 255, 0), abs=40)  # in the parameter's colour


def test_a_video_overlay_runs_on_through_cuts_and_transitions(project):
    text = ("---\nsize: 320x180\noverlay: slider.html\ntransition: crossfade 0.5\n---\n\n![](red.png)\n\n(duration: 1)\n\n"
            "---\n\n![](blue.png)\n\n(duration: 1)\n\n---\n\n(overlay: none)\n\n![](grey.png)\n\n(duration: 1)\n")
    result, _ = build(project, text)
    for t in (0.5, 1.2, 1.7):  # 1.2 is mid-crossfade: the overlay sits above it, solid
        left = green_left(frame(result.video, t, project))
        assert left == pytest.approx(100 * t, abs=6), t  # the page's clock is the video's
    assert green_left(frame(result.video, 2.5, project)) is None  # (overlay: none) hides it


def test_a_build_of_some_scenes_keeps_the_video_clock(project):
    text = ("---\nsize: 320x180\noverlay: slider.html\n---\n\n![](red.png)\n\n(duration: 1)\n\n---\n\n"
            "![](blue.png)\n\n(duration: 1)\n")
    result, _ = build(project, text, name="part", scenes=[2])
    assert green_left(frame(result.video, 0.5, project)) == pytest.approx(150, abs=6)  # 1.5 s into the video


def test_a_header_overlay_can_cover_some_scenes(project):
    text = ("---\nsize: 320x180\noverlay: {file: still.html, scenes: 2}\n---\n\n![](red.png)\n\n(duration: 1)\n\n"
            "---\n\n![](blue.png)\n\n(duration: 1)\n\n---\n\n![](grey.png)\n\n(duration: 1)\n")
    result, _ = build(project, text)
    shown = [tuple(frame(result.video, t, project)[H - 10, 10]) for t in (0.5, 1.5, 2.5)]
    assert shown[1] == pytest.approx((255, 0, 255), abs=40)
    assert shown[0] != pytest.approx((255, 0, 255), abs=40) and shown[2] != pytest.approx((255, 0, 255), abs=40)


def test_check_reports_missing_overlay_pages(project, capsys):
    (project / "s.md").write_text("---\noverlay: nowhere.html\n---\n\n(overlay: gone.html)\n\nHi.\n")
    assert cli.main(["check", str(project / "s.md")]) == 1
    err = capsys.readouterr().err
    assert "line 1: file not found: nowhere.html" in err and "line 5: file not found: gone.html" in err
