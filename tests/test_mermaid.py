"""render:mermaid: Mermaid diagrams drawn in the build's Chromium (#40)."""

from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from narrate import media, mermaid
from narrate.build import Builder, BuildError
from narrate.cli import main
from narrate.render import RenderError
from narrate.script import Render, parse_file
from narrate.tts import SilentSynth


@pytest.fixture(autouse=True)
def own_cache(monkeypatch, tmp_path):
    monkeypatch.setenv("NARRATE_CACHE", str(tmp_path / "cache"))


def build(tmp_path: Path, text: str, name: str = "s") -> Path:
    script = tmp_path / f"{name}.md"
    script.write_text("---\nsize: 640x360\n---\n\n" + text)
    out = tmp_path / f"{name}.mp4"
    Builder(parse_file(script), SilentSynth(), log=lambda _: None).build(out)
    return out


def frame(video: Path, tmp_path: Path) -> np.ndarray:
    png = tmp_path / f"{video.stem}.png"
    media.extract_frame(video, 0.5, png)
    return np.asarray(Image.open(png).convert("RGB"), dtype=float)


def drawn_width(f: np.ndarray) -> int:
    """How wide the diagram is: the columns that differ from the background."""
    columns = np.where((np.abs(f - f[2, 2]).sum(axis=2) > 60).any(axis=0))[0]
    return int(columns[-1] - columns[0]) if len(columns) else 0


FLOW = "```render:mermaid\nflowchart LR\n  Script --> Parser --> Builder --> Video\n```\n\n(duration: 1)\n"


# -- mermaid.js -----------------------------------------------------------------

def test_mermaid_js_is_checked_against_the_pinned_digest(monkeypatch, tmp_path):
    real = mermaid.ensure().read_bytes()
    monkeypatch.delenv("NARRATE_MERMAID_JS", raising=False)
    monkeypatch.setenv("NARRATE_TOOLS", str(tmp_path))

    class Response:
        def __init__(self, data):
            self.data = data

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self):
            return self.data

    with pytest.raises(RenderError, match="checksum mismatch"):
        mermaid.ensure(log=lambda _: None, opener=lambda url: Response(b"not mermaid"))
    assert not mermaid.managed_script().exists()
    path = mermaid.ensure(log=lambda _: None, opener=lambda url: Response(real))
    assert path == mermaid.managed_script() and path.read_bytes() == real


def test_narrate_mermaid_js_points_at_another_copy(monkeypatch, tmp_path):
    monkeypatch.setenv("NARRATE_MERMAID_JS", str(tmp_path / "mermaid.min.js"))
    assert mermaid.ensure() == tmp_path / "mermaid.min.js"


# -- settings -------------------------------------------------------------------

def test_mermaid_frontmatter_passes_through_without_narrates_keys():
    block = Render("mermaid", "flowchart LR\n  A --> B",
                   {"title": "Flow", "config": {"flowchart": {"padding": 20}}, "background": "navy", "scale": 0.8})
    assert mermaid.diagram_text(block) == ("---\ntitle: Flow\nconfig:\n  flowchart:\n    padding: 20\n---\n"
                                           "flowchart LR\n  A --> B")
    assert mermaid.diagram_text(Render("mermaid", "pie\n  \"A\": 1", {"scale": 2})) == "pie\n  \"A\": 1"


@pytest.mark.parametrize("settings, problem", [
    ({"backround": "red"}, "doesn't take 'backround'"),
    ({"scale": 0}, "scale must be a positive number"),
    ({"scale": "big"}, "scale must be a positive number"),
    ({"config": "dark"}, "config must be a map"),
    ({"background": "nope"}, "nope"),
])
def test_bad_settings_are_reported(settings, problem):
    assert any(problem in p for p in mermaid.Mermaid().check(Render("mermaid", "flowchart LR\n  A", settings)))


# -- drawing --------------------------------------------------------------------

def test_a_diagram_fills_the_frame_on_the_themes_background(tmp_path):
    f = frame(build(tmp_path, FLOW), tmp_path)
    assert f[2, 2].mean() > 250  # the default theme's white
    assert 0.8 * 640 < drawn_width(f) <= 0.92 * 640  # fitted to 90% of the width
    cached = next((tmp_path / "cache" / "render" / "mermaid").glob("*.png"))
    assert Image.open(cached).size == (1280, 720)  # captured at twice the frame


def test_dark_backgrounds_get_mermaids_dark_theme(tmp_path):
    light = frame(build(tmp_path, "(theme: light)\n\n" + FLOW, "light"), tmp_path)
    navy = frame(build(tmp_path, "(canvas: navy)\n\n" + FLOW, "navy"), tmp_path)
    chosen = frame(build(tmp_path, FLOW.replace("mermaid\n", "mermaid\n---\nbackground: \"#ffeedd\"\n---\n"),
                         "chosen"), tmp_path)
    assert light[2, 2].mean() < 5 and light.max() > 200  # black, with light lines and text
    assert navy[2, 2][2] > 100 > navy[2, 2][0]
    assert tuple(chosen[2, 2].round()) == pytest.approx((255, 238, 221), abs=3)


def test_scale_shrinks_the_diagram(tmp_path):
    full = drawn_width(frame(build(tmp_path, FLOW, "full"), tmp_path))
    half = drawn_width(frame(build(tmp_path, FLOW.replace("mermaid\n", "mermaid\n---\nscale: 0.5\n---\n"), "half"),
                             tmp_path))
    assert half == pytest.approx(full / 2, rel=0.1)


def test_mermaid_config_reaches_mermaid(tmp_path):
    box = "```render:mermaid\n%s\nflowchart LR\n  A[Box]\n```\n\n(duration: 1)\n"
    plain = frame(build(tmp_path, box % "", "plain"), tmp_path)
    forest = frame(build(tmp_path, box % "---\nconfig:\n  theme: forest\n---", "forest"), tmp_path)
    r, g, b = plain[180, 100]  # inside the node, left of its label
    assert b > g  # the default theme's lavender
    r, g, b = forest[180, 100]
    assert g > b  # forest's green


def test_a_syntax_error_fails_the_build_at_the_block(tmp_path):
    with pytest.raises(BuildError, match="render:mermaid") as e:
        build(tmp_path, "Intro.\n\n```render:mermaid\nflowchart LR\n  A -->\n```\n")
    assert e.value.line == 7  # after the four header lines the helper adds
    assert not list((tmp_path / "cache" / "render" / "mermaid").glob("*"))  # nothing half-written


def test_check_runs_mermaids_parser(tmp_path, capsys):
    script = tmp_path / "s.md"
    script.write_text(FLOW + "\n---\n\n```render:mermaid\nflowchart LR\n  A -->\n```\n")
    assert main(["check", str(script)]) == 1
    err = capsys.readouterr().err
    assert "line 10: render:mermaid: Parse error" in err and "line 1:" not in err
    script.write_text(FLOW)
    assert main(["check", str(script)]) == 0
