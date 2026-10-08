import numpy as np
import pytest
from PIL import Image

from narrate import media
from narrate.build import Builder, merge_groups
from narrate.config import FPS
from narrate.script import parse, parse_file
from narrate.tts import SAMPLE_RATE, SilentSynth

SCRIPT = """---
size: 320x180
---

(narration-mode: merge)

Time flies when you're having fun, and this sentence runs across three pictures.

![](red.png)

---

![](green.png)

---

![](blue.png)

(narration-mode: normal)

---

![](red.png)

A separate scene.
"""


class ToneSynth(SilentSynth):
    name = "tone"

    def synth(self, text, voice, speed, notes):
        n = len(super().synth(text, voice, speed, notes))
        return (0.2 * np.sin(2 * np.pi * 330 * np.arange(n) / SAMPLE_RATE)).astype(np.float32)


@pytest.fixture
def project(tmp_path):
    for colour in ("red", "green", "blue"):
        Image.new("RGB", (320, 180), colour).save(tmp_path / f"{colour}.png")
    (tmp_path / "s.md").write_text(SCRIPT)
    return tmp_path


def test_groups_run_from_merge_to_normal(project):
    groups = merge_groups(parse_file(project / "s.md").scenes)
    assert [len(g) for g in groups] == [3, 1]


def test_merged_scenes_share_one_continuous_narration(project):
    script = parse_file(project / "s.md")
    builder = Builder(script, ToneSynth(), log=lambda _: None)
    plans = list(builder.plans(script.scenes, project))
    merged = plans[:3]
    voiced = builder.plan_scene(script.scenes[0].__class__(1, 1, [b for b in script.scenes[0].blocks
                                                                   if type(b).__name__ == "Narration"]), project)
    assert sum(p.duration for p in merged) == pytest.approx(voiced.duration, abs=1 / FPS)
    assert all(p.duration == pytest.approx(merged[0].duration, abs=1 / FPS) for p in merged)
    joined = np.concatenate([p.audio for p in merged])
    assert np.allclose(joined[:len(voiced.audio) - 1000], voiced.audio[:len(voiced.audio) - 1000])


def test_merged_scenes_render_in_turn(project):
    script = parse_file(project / "s.md")
    builder = Builder(script, SilentSynth(), log=lambda _: None)
    third = next(builder.plans(script.scenes, project)).duration
    result = Builder(parse_file(project / "s.md"), SilentSynth(), log=lambda _: None).build(project / "out.mp4")

    def colour(t):
        png = project / f"{t:.2f}.png"
        media.extract_frame(result.video, t, png)
        return np.argmax(Image.open(png).convert("RGB").getpixel((160, 90)))

    assert [colour(third * k + third / 2) for k in range(3)] == [0, 1, 2]
