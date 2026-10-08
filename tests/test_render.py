"""Render blocks (```render:NAME): parsing, checking, placement, caching (#39)."""

from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from narrate import media, render
from narrate.build import Builder, BuildError
from narrate.cache import entries
from narrate.cli import main
from narrate.script import Media, ScriptError, parse, parse_file
from narrate.tts import SilentSynth


@pytest.fixture(autouse=True)
def own_cache(monkeypatch, tmp_path):
    monkeypatch.setenv("NARRATE_CACHE", str(tmp_path / "cache"))


def block(text: str) -> Media:
    blocks = parse(text).scenes[0].blocks
    assert isinstance(blocks[0], Media)
    return blocks[0]


def build(tmp_path: Path, text: str, name: str = "s"):
    script = tmp_path / f"{name}.md"
    script.write_text(text)
    out = tmp_path / f"{name}.mp4"
    return Builder(parse_file(script), SilentSynth(), log=lambda _: None).build(out), out


def frame(video: Path, t: float, tmp_path: Path) -> np.ndarray:
    png = tmp_path / f"frame-{t}.png"
    media.extract_frame(video, t, png)
    return np.asarray(Image.open(png).convert("RGB"), dtype=float)


# -- parsing --------------------------------------------------------------------

def test_a_render_block_is_a_media_block_not_a_slide():
    m = block("```render:Placeholder\nA chart goes here\n```\n")
    assert (m.kind, m.path, m.render.name, m.render.body) == ("image", "", "placeholder", "A chart goes here")


def test_words_after_the_name_are_placement_tokens():
    m = block("```render:placeholder panzoom left\nx\n```\n")
    assert (m.size, m.position) == ("panzoom", "left")


def test_frontmatter_splits_into_placement_and_renderer_settings():
    m = block("```render:mermaid contain\n---\nsize: cover\nPosition: top\ntitle: Flow\ndisplayMode: compact\n"
              "config:\n  flowchart: {padding: 20, htmlLabels: false}\n---\nflowchart LR\n  A --> B\n```\n")
    assert (m.size, m.position) == ("cover", "top")  # frontmatter wins over the token
    # Typed YAML, key case kept: these pass through to the renderer as written
    assert m.render.settings == {"title": "Flow", "displayMode": "compact",
                                 "config": {"flowchart": {"padding": 20, "htmlLabels": False}}}
    assert m.render.body == "flowchart LR\n  A --> B"


@pytest.mark.parametrize("text, message", [
    ("```render:\nx\n```\n", "needs a renderer"),
    ("```render:placeholder\n---\nbackground: red\nx\n```\n", "not closed"),
    ("```render:placeholder\n---\nbackground: [red\n---\nx\n```\n", "invalid YAML"),
    ("```render:placeholder\n---\n- red\n---\nx\n```\n", "must be a map"),
])
def test_malformed_render_blocks_name_their_line(text, message):
    with pytest.raises(ScriptError, match=message):
        parse("intro\n\n" + text)


def test_a_render_block_inside_another_fence_is_slide_text():
    blocks = parse("````md\n```render:placeholder\nx\n```\n````\n").scenes[0].blocks
    assert blocks[0].lang == "md" and "render:placeholder" in blocks[0].text


# -- checking -------------------------------------------------------------------

def test_check_reports_unknown_renderers_and_settings(tmp_path, capsys):
    script = tmp_path / "s.md"
    script.write_text("```render:sketch\nx\n```\n\n---\n\n```render:placeholder\n---\nbackgound: red\n---\n```\n\n"
                      "---\n\n```render:placeholder\n---\ncolor: notacolour\n---\n```\n")
    assert main(["check", str(script)]) == 1
    err = capsys.readouterr().err
    assert "line 1: unknown renderer render:sketch (known: " in err and "render:placeholder" in err
    assert "line 7: render:placeholder doesn't take 'backgound'" in err
    assert "line 15:" in err and "notacolour" in err


def test_check_passes_good_render_blocks_without_looking_for_a_file(tmp_path, capsys):
    script = tmp_path / "s.md"
    script.write_text("```render:placeholder\n---\nbackground: navy\n---\nA chart\n```\n")
    assert main(["check", str(script)]) == 0
    assert "0 missing files" in capsys.readouterr().out


def test_unknown_renderer_fails_the_build_at_its_line(tmp_path):
    with pytest.raises(BuildError, match="unknown renderer render:sketch") as e:
        build(tmp_path, "Hello.\n\n```render:sketch\nx\n```\n")
    assert e.value.line == 3


# -- placement ------------------------------------------------------------------

def test_output_is_placed_and_timed_like_a_picture(tmp_path):
    result, out = build(tmp_path, "---\nsize: 320x180\n---\n\n```render:placeholder\n---\nbackground: red\n---\n```\n\n"
                                  "(duration: 2)\n\n---\n\n```render:placeholder\n---\nbackground: blue\n---\n```\n")
    assert result.duration == pytest.approx(3.0, abs=0.05)  # 2 s, then a picture's 1 s
    first, second = frame(out, 1.0, tmp_path), frame(out, 2.5, tmp_path)
    assert first[5, 160][0] > 200 > first[5, 160][2]
    assert second[5, 160][2] > 200 > second[5, 160][0]


def test_callouts_and_slides_apply_over_the_output(tmp_path):
    _, out = build(tmp_path, "---\nsize: 320x180\n---\n\n```render:placeholder\n---\nbackground: white\n"
                             "color: white\n---\n```\n\n(callout:\n  cx: 160\n  cy: 90\n  size: 40\n  alpha: 0.8)\n\n"
                             "(duration: 1)\n")
    f = frame(out, 0.5, tmp_path)
    assert f[90, 160].mean() > 200 and f[10, 10].mean() < 100  # bright inside the circle, shaded outside


def test_audio_builds_plan_render_blocks_without_rendering(tmp_path, monkeypatch):
    monkeypatch.setattr(render.Placeholder, "render", lambda *a: pytest.fail("rendered"))
    script = tmp_path / "s.md"
    script.write_text("```render:placeholder\nx\n```\n\nSome narration.\n")
    result = Builder(parse_file(script), SilentSynth(), log=lambda _: None).build_audio(tmp_path / "s.wav")
    assert result.duration > 0


# -- caching --------------------------------------------------------------------

def test_unchanged_blocks_are_rendered_once(tmp_path, monkeypatch):
    calls = []
    original = render.Placeholder.render
    monkeypatch.setattr(render.Placeholder, "render",
                        lambda self, b, ctx, out: (calls.append(b.body), original(self, b, ctx, out)))
    text = "---\nsize: 320x180\n---\n\n```render:placeholder\nA chart\n```\n"
    build(tmp_path, text)
    build(tmp_path, text, "again")
    assert calls == ["A chart"]
    build(tmp_path, text.replace("A chart", "A table"), "changed")
    assert calls == ["A chart", "A table"]
    rendered = [e for e in entries() if e.engine == "render:placeholder"]
    assert len(rendered) == 2  # listed (and prunable) by `narrate cache`


def test_the_scenes_theme_is_part_of_the_cache_key(tmp_path, monkeypatch):
    seen = []
    original = render.Placeholder.render
    monkeypatch.setattr(render.Placeholder, "render",
                        lambda self, b, ctx, out: (seen.append((ctx.theme, ctx.canvas)), original(self, b, ctx, out)))
    build(tmp_path, "---\nsize: 320x180\n---\n\n```render:placeholder\nx\n```\n\n---\n\n(theme: light)\n\n"
                    "(canvas: navy)\n\n```render:placeholder\nx\n```\n")
    assert seen == [("default", None), ("light", "#000080")]
