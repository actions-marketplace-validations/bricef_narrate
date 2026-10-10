"""Building part of a video (#61): `narrate build --scenes`, exactly as those scenes are in the whole."""

import argparse
import wave

import numpy as np
import pytest
from PIL import Image

from narrate import media
from narrate.build import Builder, BuildError
from narrate.cli import parse_scenes, scenes_name
from narrate.script import parse
from narrate.tts import SilentSynth

SCRIPT = """---
size: 320x180
fade-in: 0.5
fade-out: 0.5
transition: crossfade 0.5
background: music.wav 0.5
---

![](red.png)

(duration: 2)

---

![zoom](pattern.png)

The second scene speaks for a while, long enough for the zoom to travel.

---

![](blue.png)

(duration: 2)
"""


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.setenv("NARRATE_CACHE", str(tmp_path / "cache"))
    Image.new("RGB", (640, 360), "red").save(tmp_path / "red.png")
    Image.new("RGB", (640, 360), "blue").save(tmp_path / "blue.png")
    x, y = np.meshgrid(np.arange(640), np.arange(360))
    pattern = np.stack([(x * 255 // 639), (y * 255 // 359), ((x // 40 + y // 40) % 2) * 255], axis=-1)
    Image.fromarray(pattern.astype(np.uint8)).save(tmp_path / "pattern.png")
    # A rising tone, so where the music is matters
    media.run(["-f", "lavfi", "-i", "aevalsrc=0.4*sin(2*PI*(200+40*t)*t):s=24000:d=20", str(tmp_path / "music.wav")])
    (tmp_path / "s.md").write_text(SCRIPT)
    return tmp_path


class Counting(SilentSynth):
    """Silent speech that remembers what was synthesised (cache lookups don't count, and always miss)."""

    def __init__(self):
        self.spoken = []

    def synth(self, text, voice, speed, notes, only_cached=False):
        if only_cached:
            return None
        self.spoken.append(text)
        return super().synth(text, voice, speed, notes)


def build(project, name, scenes=None, synth=None, text=SCRIPT):
    script = parse(text, project / "s.md")
    builder = Builder(script, synth or SilentSynth(), log=lambda _: None, scenes=scenes)
    work = project / f"work-{name}"
    result = builder.build(project / f"{name}.mp4", workdir=work)
    with wave.open(str(work / "audio.wav")) as w:
        audio = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2")
    return result, audio


def frame_at(video, t, out):
    media.extract_frame(video, t, out)
    return np.asarray(Image.open(out).convert("RGB"), dtype=float)


def test_a_scene_is_rendered_as_it_is_in_the_whole_video(project):
    whole, whole_audio = build(project, "whole")
    part, part_audio = build(project, "part", scenes=[2])
    start = 2.0  # scene 1 lasts exactly 2 s
    assert part.duration == pytest.approx(whole.duration - 4.0, abs=1 / 30)
    # The same frames once the whole video's transition into it is over (the excerpt has none)
    for t in (0.8, part.duration - 0.2):
        ours = frame_at(part.video, t, project / "ours.png")
        theirs = frame_at(whole.video, start + t, project / "theirs.png")
        assert np.abs(ours - theirs).mean() < 3, t
    # The music as it plays under scene 2 in the whole video, not from its beginning
    lo = round(start * 24000)
    assert len(part_audio) == pytest.approx(len(whole_audio) - 4 * 24000, abs=1)
    assert np.abs(part_audio.astype(int) - whole_audio[lo:lo + len(part_audio)]).max() <= 1
    assert "no transition into scene 2: nothing comes before it in this render" in part.notes


def test_fades_apply_only_where_the_video_starts_and_ends(project):
    first, _ = build(project, "first", scenes=[1])
    assert frame_at(first.video, 0, project / "a.png").mean() < 10  # fades in from black
    assert frame_at(first.video, first.duration - 1 / 30, project / "b.png")[..., 0].mean() > 200  # still red
    middle, _ = build(project, "middle", scenes=[2])
    assert frame_at(middle.video, 0, project / "c.png").mean() > 60  # no fade, and no transition from black


def test_only_the_scenes_rendered_are_synthesised(project):
    synth = Counting()
    build(project, "spoken", scenes=[1], synth=synth, text=SCRIPT.replace("(duration: 2)\n\n---", "Scene one.\n\n---", 1))
    assert synth.spoken == ["Scene one."]


def test_merged_scenes_render_together(project):
    text = "Alone.\n\n---\n\n(narration-mode: merge)\n\nOne narration\n\n---\n\nacross two scenes.\n\n(narration-mode: normal)\n"
    script = parse(text, project / "s.md")
    builder = Builder(script, SilentSynth(), log=lambda _: None, scenes=[3])
    assert builder.selected == {2, 3}
    assert "scenes merged into one narration are rendered together" in builder.notes


def test_a_problem_elsewhere_doesnt_stop_a_scene(project):
    text = SCRIPT.replace("![](blue.png)", "![](nowhere.png)")
    part, _ = build(project, "fine", scenes=[1], text=text)
    assert part.video.exists()
    with pytest.raises(BuildError, match="nowhere.png"):
        build(project, "broken", text=text)


def test_scene_numbers_are_checked(project):
    with pytest.raises(BuildError, match="no scene 9: the script has 3"):
        Builder(parse(SCRIPT, project / "s.md"), SilentSynth(), scenes=[2, 9])


def test_scene_lists():
    assert parse_scenes("3") == [3]
    assert parse_scenes("3-5") == [3, 4, 5]
    assert parse_scenes("2,4") == [2, 4]
    assert parse_scenes("1-2, 5") == [1, 2, 5]
    for bad in ("", "0", "a", "5-3", "2-"):
        with pytest.raises(argparse.ArgumentTypeError):
            parse_scenes(bad)
    assert [scenes_name(s) for s in ([3], [3, 4, 5], [4, 2])] == ["scene-3", "scenes-3-5", "scenes-2_4"]
