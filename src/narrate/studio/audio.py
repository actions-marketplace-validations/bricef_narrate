"""Narration playback in the studio (#54): one scene's narration, synthesised for real.

The scene is planned again with the session's own engine, from the text the
analysis saw, so what plays is the narration track a build would use, clip
sound included (design D9). Speech lands in the usual cache, so playing it
again, building, and the next analysis's timing all reuse it.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from ..build import Builder, _write_wav, merge_groups
from ..script import parse


def scene_audio(text: str, script: Path, synth: Any, index: int, scratch: Path) -> dict:
    """Synthesise scene `index` of `text`; a WAV in `scratch`, and when each paragraph starts in it."""
    parsed = parse(text, script)
    group = next((g for g in merge_groups(parsed.scenes) if any(s.index == index for s in g)), None)
    if group is None:
        raise LookupError(f"there's no scene {index}")
    builder = Builder(parsed, synth, log=lambda _: None, measure_pages=False)
    try:
        plan = next(p for s, p in zip(group, builder.plans(group, script.parent)) if s.index == index)
    finally:
        builder.close()
    name = f"scene-{index}-{hashlib.sha256(f'{synth.name}:{text}'.encode()).hexdigest()[:16]}.wav"
    _write_wav(scratch / name, plan.audio)
    return {
        "url": f"/scratch/{name}",
        "duration": round(plan.duration, 3),
        "paragraphs": [{"line": p.line, "start": round(p.start, 3), "end": round(p.end, 3)} for p in plan.paragraphs],
        "notes": sorted(builder.notes),
    }
