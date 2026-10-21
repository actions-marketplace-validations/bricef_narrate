"""HTML scenes captured frame by frame (#44)."""

import hashlib
from pathlib import Path
from time import sleep

import numpy as np
import pytest
from PIL import Image

from narrate import media, pages
from narrate.build import Builder
from narrate.cli import main
from narrate.frames import FrameRenderer
from narrate.script import parse, parse_file
from narrate.tts import SilentSynth

BASE = "html, body { margin: 0; width: 100%; height: 100%; background: #000; }"


def page(tmp_path: Path, body: str, name: str = "scene.html", style: str = "") -> Path:
    path = tmp_path / name
    path.write_text(f"<!doctype html><style>{BASE}{style}</style><body>{body}</body>")
    return path


def build(tmp_path: Path, script: str, name: str = "s", audio: bool = False):
    path = tmp_path / f"{name}.md"
    path.write_text("---\nsize: 320x180\n---\n\n" + script)
    builder = Builder(parse_file(path), SilentSynth(), log=lambda _: None)
    if audio:
        return builder.build_audio(tmp_path / f"{name}.wav")
    return builder.build(tmp_path / f"{name}.mp4")


def frame(video: Path, t: float) -> np.ndarray:
    png = video.with_name(f"{video.stem}-{t:.3f}.png")
    media.extract_frame(video, t, png)
    return np.asarray(Image.open(png).convert("RGB"), dtype=float)


FADE_IN = (".box { position: absolute; inset: 0; background: #fff; opacity: 0;"
           " animation: show .5s linear 1s forwards; } @keyframes show { to { opacity: 1; } }")


# -- parsing --------------------------------------------------------------------

def test_html_files_and_the_html_direction_are_media():
    first, second = parse("![contain](a.html)\n\n(html: {file: b.htm, viewport: 1280x720})\n").scenes[0].blocks
    assert (first.kind, first.path, first.size) == ("html", "a.html", "contain")
    assert (second.kind, second.path, second.viewport) == ("html", "b.htm", "1280x720")


def test_check_reports_a_missing_page(tmp_path, capsys):
    (tmp_path / "s.md").write_text("![](nowhere.html)\n")
    assert main(["check", str(tmp_path / "s.md")]) == 1
    assert "file not found: nowhere.html" in capsys.readouterr().err


# -- timing ---------------------------------------------------------------------

def test_css_animations_play_on_the_scenes_clock(tmp_path):
    page(tmp_path, "<div class=box></div>", style=FADE_IN)
    out = build(tmp_path, "![](scene.html)\n\n(duration: 3)\n").video
    assert frame(out, 0.5).mean() < 5  # still in its 1 s delay
    assert frame(out, 1.25).mean() == pytest.approx(127, abs=25)  # half way through the fade
    assert frame(out, 2.0).mean() > 250


def test_javascript_timers_run_on_the_scenes_clock(tmp_path):
    page(tmp_path, "<script>setTimeout(() => document.body.style.background = '#f00', 1000)</script>")
    out = build(tmp_path, "![](scene.html)\n\n(duration: 2)\n").video
    assert frame(out, 0.8)[90, 160][0] < 5
    assert frame(out, 1.2)[90, 160][0] > 250


def test_infinite_animations_keep_running(tmp_path):
    page(tmp_path, "<div class=box></div>", style=".box { position: absolute; inset: 0; background: #fff;"
                                                  " animation: blink 1s step-end infinite; }"
                                                  " @keyframes blink { 50% { opacity: 0; } }")
    out = build(tmp_path, "![](scene.html)\n\n(duration: 2)\n").video
    assert [frame(out, t).mean() > 128 for t in (0.25, 0.75, 1.25, 1.75)] == [True, False, True, False]


def test_every_build_captures_the_same_frames(tmp_path):
    page(tmp_path, '<div id=bar style="height:100%;background:#fff;width:0"></div><script>'
                   "const t0 = performance.now();"
                   "(function grow(now) { bar.style.width = Math.min(100, (now - t0) / 20) + '%';"
                   " requestAnimationFrame(grow); })(t0)</script>", style=FADE_IN)
    script = "![](scene.html)\n\n(duration: 2)\n"
    a, b = build(tmp_path, script, "a").video, build(tmp_path, script, "b").video
    for t in (0.4, 0.9, 1.5):
        assert hashlib.sha256(frame(a, t).tobytes()).digest() == hashlib.sha256(frame(b, t).tobytes()).digest()
    assert frame(a, 0.9)[:, :140].mean() > 200 > frame(a, 0.9)[:, 160:].mean()  # 45% across at 0.9 s


def test_a_slow_machine_starts_the_page_at_the_same_moment(tmp_path, monkeypatch):
    """Time spent before the clock paused reached the page, so a slow machine (a macOS runner)
    moved its animation frames, and two builds captured different frames (#93)."""
    path = page(tmp_path, "<script>t0 = performance.now(); requestAnimationFrame(now => first = now)</script>")
    with FrameRenderer(320, 180, tmp_path) as frames:
        pause_at = type(frames._page.clock).pause_at

        def slowly(clock, at):
            sleep(0.03)
            return pause_at(clock, at)

        monkeypatch.setattr(type(frames._page.clock), "pause_at", slowly)
        with frames.page(path, (320, 180)) as tab:
            tab.clock.run_for(40)
            assert tab.evaluate("[t0, first]") == [0, 16]


def test_a_page_with_nothing_else_lasts_as_long_as_its_animations(tmp_path):
    page(tmp_path, "<div class=box></div>", style=FADE_IN)
    page(tmp_path, "<p>static</p>", "static.html")
    assert build(tmp_path, "![](scene.html)\n", "animated").duration == pytest.approx(1.5, abs=0.04)
    assert build(tmp_path, "![](static.html)\n", "still").duration == pytest.approx(1.0, abs=0.04)


def test_narration_times_a_page_like_a_picture(tmp_path):
    page(tmp_path, "<div class=box></div>", style=FADE_IN.replace("linear 1s", "linear 30s"))
    result = build(tmp_path, "![](scene.html)\n\nA short line.\n")
    assert result.duration < 3  # the narration, not the 30 s animation


def test_audio_builds_measure_pages_too(tmp_path):
    page(tmp_path, "<div class=box></div>", style=FADE_IN)
    assert build(tmp_path, "![](scene.html)\n", audio=True).duration == pytest.approx(1.5, abs=0.04)


# -- capture --------------------------------------------------------------------

def test_capture_stops_once_a_page_without_scripts_has_settled(tmp_path):
    settling = page(tmp_path, "<div class=box></div>", style=FADE_IN.replace(".5s linear 1s", ".5s linear 0s"))
    scripted = page(tmp_path, "<div class=box></div><script></script>", "scripted.html",
                    style=FADE_IN.replace(".5s linear 1s", ".5s linear 0s"))
    counts = []
    with FrameRenderer(64, 36, tmp_path) as frames:
        for path in (settling, scripted):
            images = list(pages.capture(frames, path, (64, 36), 1.0, 60, 30, counts.append))
            assert len(images) == 60 and images[-1] == images[20]
    assert counts == [16, 60]  # settled at 0.5 s; a script could change the page at any time


def test_a_smaller_viewport_renders_at_a_higher_density(tmp_path):
    page(tmp_path, '<div style="width:80px;height:90px;background:#f00"></div>')  # designed for 160x90
    out = build(tmp_path, "(html: {file: scene.html, viewport: 160x90})\n\n(duration: 1)\n").video
    f = frame(out, 0.5)
    assert f[90, 150][0] > 250 and f[90, 170][0] < 5  # the red half fills 160 of 320 pixels


def test_callouts_and_slides_go_over_pages(tmp_path):
    page(tmp_path, "", style="body { background: #fff; }")
    out = build(tmp_path, "![](scene.html)\n\n(callout:\n  cx: 160\n  cy: 90\n  size: 40\n  alpha: 0.8)\n\n"
                          "(duration: 1)\n").video
    f = frame(out, 0.5)
    assert f[90, 160].mean() > 240 and f[10, 10].mean() < 80
