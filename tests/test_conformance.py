"""Conformance with Narakeet's own renders (`just reference` fetches them).

Each example project includes the result.mp4 Narakeet rendered from it. The
examples without narration are deterministic, so their timing depends only on
the format rules: narrate should match their length and look. Where Narakeet's
render departs from its own documentation, the difference is pinned here and
explained in spec §17.
"""

from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from narrate import media
from narrate.build import Builder
from narrate.script import parse_file
from narrate.tts import SilentSynth

EXAMPLES = Path(__file__).parent.parent / "reference" / "examples"
pytestmark = [pytest.mark.conformance, pytest.mark.skipif(not (EXAMPLES / "slides" / "result.mp4").exists(),
                                reason="run `just reference` (scripts/fetch-narakeet-reference.sh --media) first")]

# example: (Narakeet's length if it departs from the rules, else None, max frame difference)
FAITHFUL = {
    "slides": 8.0,
    "transition-types": 3.0,
    "video-sizing": 10.0,
    "video-volume": 10.0,
}


class Render:
    def __init__(self, name: str, out: Path):
        script = next((EXAMPLES / name / "script").glob("*.md"))
        builder = Builder(parse_file(script), SilentSynth(), log=lambda _: None)
        plans = list(builder.plans(parse_file(script).scenes, out))
        self.bounds = np.cumsum([0.0] + [p.duration for p in plans])
        self.video = Builder(parse_file(script), SilentSynth(), log=lambda _: None).build(out / f"{name}.mp4").video
        self.reference = EXAMPLES / name / "result.mp4"
        self.out = out

    def frame(self, video: Path, t: float) -> np.ndarray:
        png = self.out / f"frame-{video.stem}-{t:.3f}.png"
        media.extract_frame(video, t, png)
        return np.asarray(Image.open(png).convert("L").resize((64, 36)), dtype=float)

    def settled(self, fraction: float = 0.75) -> list[float]:
        """A point in each scene after any incoming transition has finished."""
        return [a + fraction * (b - a) for a, b in zip(self.bounds, self.bounds[1:])]


@pytest.fixture(scope="module")
def render(tmp_path_factory):
    cache: dict[str, Render] = {}

    def get(name: str) -> Render:
        if name not in cache:
            cache[name] = Render(name, tmp_path_factory.mktemp(name))
        return cache[name]

    return get


@pytest.mark.parametrize("name", FAITHFUL)
def test_length_matches_narakeet(render, name):
    r = render(name)
    assert media.probe(r.video).duration == pytest.approx(media.probe(r.reference).duration, abs=0.1)


@pytest.mark.parametrize("name, limit", FAITHFUL.items())
def test_scenes_look_like_narakeet(render, name, limit):
    r = render(name)
    diffs = [np.abs(r.frame(r.video, t) - r.frame(r.reference, t)).mean() for t in r.settled()]
    assert max(diffs) < limit, [round(d, 1) for d in diffs]


def test_image_sizing_looks_like_narakeet_at_its_own_pace(render):
    """Narakeet pads these slide-and-pause scenes to 2.52 s (spec §17); compare each scene's image fit."""
    r = render("image-sizing")
    ours = [r.frame(r.video, t) for t in r.settled()]
    theirs = [r.frame(r.reference, 2.52 * k + 0.75 * 2.52) for k in range(len(ours))]
    diffs = [np.abs(a - b).mean() for a, b in zip(ours, theirs)]
    assert max(diffs) < 8.0, [round(d, 1) for d in diffs]


def test_slide_css_theming_looks_like_narakeet(render):
    """Themes, fonts and backdrops match; Narakeet's render is 0.47 s longer (spec §17)."""
    r = render("slide-css-theming")
    diffs = [np.abs(r.frame(r.video, t) - r.frame(r.reference, t)).mean() for t in r.settled()]
    assert max(diffs) < 8.0, [round(d, 1) for d in diffs]


@pytest.mark.parametrize("name, ours, narakeet", [
    ("image-sizing", 10.0, 12.60),  # Narakeet pads scenes holding a text slide and a pause
    ("slide-css-theming", 8.5, 8.97),  # the same padding around slides
    ("transitions", 6.0, 8.05),  # Narakeet's clips overrun their segment ranges
])
def test_known_differences_are_pinned(render, name, ours, narakeet):
    r = render(name)
    assert media.probe(r.video).duration == pytest.approx(ours, abs=0.05)
    assert media.probe(r.reference).duration == pytest.approx(narakeet, abs=0.05)
