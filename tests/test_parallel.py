import hashlib
import threading
import time

import numpy as np
from PIL import Image

from narrate.build import Builder
from narrate.script import parse_file
from narrate.tts import Prefetching, SilentSynth, Voice


class SlowSynth(SilentSynth):
    """Silent speech that takes a while, like a network request, and counts overlap."""

    name = "slow"
    concurrency = 4

    def __init__(self):
        self.active = self.peak = self.calls = 0
        self.lock = threading.Lock()

    def synth(self, text, voice, speed, notes):
        with self.lock:
            self.active += 1
            self.calls += 1
            self.peak = max(self.peak, self.active)
        time.sleep(0.15)
        with self.lock:
            self.active -= 1
        return super().synth(text, voice, speed, notes)


def test_prefetching_overlaps_requests_and_serves_each_once():
    backend = SlowSynth()
    voice = Voice("af_heart", "en-us")
    requests = [(f"paragraph {i}", voice, 1.0) for i in range(8)] + [("paragraph 0", voice, 1.0)]
    started = time.monotonic()
    wrapped = Prefetching(backend, requests, set())
    results = [wrapped.synth(text, v, speed, set()) for text, v, speed in requests]
    wrapped.close()
    assert time.monotonic() - started < 0.15 * 8 / 2  # well under the serial 1.2 s
    assert backend.peak > 1 and backend.calls == 8  # duplicate requests synthesised once
    assert all(isinstance(r, np.ndarray) for r in results)


def test_build_prefetches_with_a_concurrent_backend(tmp_path):
    Image.new("RGB", (320, 180), "teal").save(tmp_path / "bg.png")
    script = tmp_path / "s.md"
    script.write_text("---\nsize: 320x180\n---\n\n" + "\n\n---\n\n".join(
        f"![](bg.png)\n\nScene {i} narration." for i in range(6)) + "\n")
    backend = SlowSynth()
    Builder(parse_file(script), backend, log=lambda _: None).build(tmp_path / "out.mp4")
    assert backend.peak > 1 and backend.calls == 6


def md5(path):
    return hashlib.md5(path.read_bytes()).hexdigest()


def test_parallel_build_is_byte_identical_to_sequential(tmp_path):
    Image.new("RGB", (320, 180), "orange").save(tmp_path / "bg.png")
    script = tmp_path / "s.md"
    script.write_text("---\nsize: 320x180\ntransition: crossfade 0.3\n---\n\n![zoom](bg.png)\n\nOne.\n\n---\n\n"
                      "```md\n# Two\n```\n\nTwo.\n\n---\n\n![](bg.png)\n\n> caption\n\n(duration: 1)\n")
    outputs = []
    for jobs in (1, 4):
        out = tmp_path / f"jobs{jobs}.mp4"
        Builder(parse_file(script), SilentSynth(), log=lambda _: None, jobs=jobs).build(out)
        outputs.append(md5(out))
    assert outputs[0] == outputs[1]
