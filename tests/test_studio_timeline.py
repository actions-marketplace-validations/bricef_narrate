"""The studio's timeline (#60): what's on screen when, transitions, cues, and the narration's waveform."""

import numpy as np
import pytest
from PIL import Image
from starlette.testclient import TestClient

from narrate.studio.analysis import PEAK_RATE, peaks, run
from narrate.studio.server import create_app
from narrate.tts import SilentSynth

SCRIPT = """---
size: 320x180
transition: crossfade 0.5
---

![zoom](a.png)

![](b.png)

First paragraph here.

<speak>Second <mark name="door"/> paragraph.</speak>

---

![](missing.png)

```render:placeholder
A product shot
```

Scene two talks.

---

```
A slide
```

```
Another
```

Scene three has slides.
"""


@pytest.fixture
def project(tmp_path):
    for name, colour in (("a.png", "red"), ("b.png", "blue")):
        Image.new("RGB", (640, 360), colour).save(tmp_path / name)
    return tmp_path


def scenes(project, text=SCRIPT):
    return run(text, project / "s.md", SilentSynth()).report["scenes"]


def test_each_scene_lists_what_is_on_screen_when(project):
    one, two, three = scenes(project)
    a, b = one["visuals"]
    assert (a["line"], a["kind"], a["name"], a["motion"]) == (6, "picture", "a.png", "zoom")
    assert (b["line"], b["kind"], b["name"], b["motion"]) == (8, "picture", "b.png", None)
    assert a["start"] == 0 and b["start"] == pytest.approx(a["length"], abs=1e-3)
    assert b["start"] + b["length"] == pytest.approx(one["duration"], abs=2e-3)  # the last stays to the end
    assert [(v["kind"], v["name"]) for v in two["visuals"]] == [("missing", "missing.png"), ("render", "render:placeholder")]
    assert [(s["line"], s["name"]) for s in three["slides"]] == [(26, "A slide"), (30, "Another")]
    assert three["slides"][1]["start"] == pytest.approx(three["duration"] / 2, abs=1e-3)


def test_transitions_and_cues(project):
    one, two, _ = scenes(project)
    assert one["transition"] is None  # nothing comes before the first scene
    assert two["transition"] == {"type": "crossfade", "seconds": 0.5}
    first, second = one["paragraphs"]
    assert one["marks"]["1"] == first["start"] and one["marks"]["2"] == second["start"]
    assert second["start"] < one["marks"]["door"] < second["end"]  # an SSML <mark>, where it's spoken


def test_sound_ids_follow_the_sound(project):
    before = [s["sound"] for s in scenes(project)]
    assert before == [s["sound"] for s in scenes(project)]  # the same text sounds the same
    after = [s["sound"] for s in scenes(project, SCRIPT.replace("Scene two talks.", "Scene two talks for longer."))]
    assert after[0] == before[0] and after[2] == before[2] and after[1] != before[1]


def test_peaks_are_the_lowest_and_highest_samples():
    sr = 24000
    audio = np.zeros(sr, dtype=np.float32)
    audio[sr // 2:] = 0.5 * np.sin(np.arange(sr // 2) * 2 * np.pi * 440 / sr)
    values = peaks(audio)
    assert len(values) == 2 * PEAK_RATE
    lows, highs = values[0::2], values[1::2]
    assert set(lows[:PEAK_RATE // 2] + highs[:PEAK_RATE // 2]) == {0}  # the silent half
    assert min(lows[PEAK_RATE // 2:]) == -50 and max(highs[PEAK_RATE // 2:]) == 50


def test_the_peaks_endpoint(project):
    (project / "s.md").write_text(SCRIPT)
    with TestClient(create_app(project / "s.md", "silent")) as client:
        assert client.get("/api/peaks/0123456789abcdef").status_code == 404
        analysis = client.post("/api/analyse", json={"text": SCRIPT}).json()
        scene = analysis["scenes"][0]
        answer = client.get(f"/api/peaks/{scene['sound']}")
        assert answer.status_code == 200 and "immutable" in answer.headers["cache-control"]
        body = answer.json()
        assert body["rate"] == PEAK_RATE
        assert len(body["peaks"]) == 2 * -(-round(scene["duration"] * 24000) // (24000 // PEAK_RATE))
