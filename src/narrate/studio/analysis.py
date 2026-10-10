"""What the studio shows about a script as it's typed (#52): problems, scenes and timing.

The editor's text is analysed without saving it. Timing comes from narrate's
own planner with an EstimatingSynth: speech already in the chosen engine's
cache gives exact lengths, and the rest are estimated from the text, so
nothing is synthesised or spent (design D9, D10). A scene that can't be
planned is reported and skipped, so one bad line doesn't blank the outline.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from .. import render
from ..build import SR, Builder, BuildError, ScenePlan, merge_groups
from ..config import ConfigError, Settings
from ..script import Media, Narration, Render, Scene, ScriptError, Slide, parse
from ..tts import EstimatingSynth

_LINE = re.compile(r"^line (\d+): (.*)$", re.S)
PEAK_RATE = 50  # waveform min/max pairs per second (#60)
MAX_SHOWINGS = 200  # a quickly looping sequence is listed this far, not to the end of a long scene


def _problem(line: int | None, message: str, severity: str = "error") -> dict:
    return {"line": line or 1, "severity": severity, "message": message}


def _warning(text: str) -> dict:
    m = _LINE.match(text)
    return _problem(int(m.group(1)), m.group(2), "warning") if m else _problem(1, text.removeprefix("header: "),
                                                                            "warning")


def _title(scene: Scene) -> str:
    """A few words naming the scene: its first picture, else its first slide, else its first words."""
    for block in scene.blocks:
        if isinstance(block, Media) and block.kind != "audio":
            return f"render:{block.render.name}" if block.render else Path(block.path).name
    for block in scene.blocks:
        if isinstance(block, Slide):
            return next((line.strip(" #*") for line in block.text.splitlines() if line.strip()), "slide")[:40]
    for block in scene.blocks:
        if isinstance(block, Narration):
            words = re.sub(r"<[^>]+>", "", block.text).split()
            return " ".join(words[:6]) + ("…" if len(words) > 6 else "")
    return "pause"


def _name(block: Media) -> str:
    return f"render:{block.render.name}" if block.render else Path(block.path).name


def _showings(plan: ScenePlan, names: dict[int, str], missing: set[int]) -> list[dict]:
    """When each picture, clip or page is on screen in the scene, laid out as the preview and a build do."""
    out: list[dict] = []
    pieces, repeat = plan.layout.pieces, plan.layout.repeat
    if not plan.visuals or not pieces:
        return out
    offset = 0.0
    while offset < plan.duration - 1e-6 and len(out) < MAX_SHOWINGS:
        for v, piece in zip(plan.visuals, pieces):
            # Without a loop, the last one stays until the scene ends
            length = plan.duration - offset if (v is plan.visuals[-1] and not repeat) else min(piece, plan.duration - offset)
            if length <= 1e-6:
                break
            kind = {"video": "clip", "page": "page"}.get(v.kind, "render" if v.render and v.path is None else "picture")
            if v.line in missing:
                kind = "missing"  # timed with a stand-in
            out.append({"line": v.line, "kind": kind, "name": names.get(v.line, kind), "motion": v.motion,
                        "start": round(offset, 3), "length": round(length, 3)})
            offset += length
        if not repeat or sum(pieces) <= 0:
            break
    return out


def _slides(plan: ScenePlan, scene: Scene) -> list[dict]:
    """When each slide shows: slides share the scene's time equally, in order."""
    blocks = [b for b in scene.blocks if isinstance(b, Slide)]
    if not plan.slides or len(blocks) != len(plan.slides):
        return []
    share = plan.duration / len(blocks)
    return [{"line": b.line, "kind": "slide", "name": _title(Scene(0, 0, [b])), "motion": None,
             "start": round(k * share, 3), "length": round(share, 3)} for k, b in enumerate(blocks)]


def sound_id(audio: np.ndarray) -> str:
    return hashlib.blake2b(audio.tobytes(), digest_size=8).hexdigest()


def peaks(audio: np.ndarray, rate: int = PEAK_RATE) -> list[int]:
    """The waveform's lowest and highest sample in each 1/rate s, as pairs of whole numbers from -100 to 100."""
    size = SR // rate
    n = -(-len(audio) // size)
    padded = np.zeros(n * size, dtype=np.float32)
    padded[:len(audio)] = audio
    blocks = padded.reshape(n, size)
    lo = np.clip(np.round(blocks.min(axis=1) * 100), -100, 100).astype(int)
    hi = np.clip(np.round(blocks.max(axis=1) * 100), -100, 100).astype(int)
    return np.column_stack([lo, hi]).ravel().tolist()


@dataclass
class Analysis:
    """The report the studio shows, and the plans behind it (the preview composes frames from them)."""

    report: dict
    plans: dict[int, ScenePlan] = field(default_factory=dict)  # by scene index
    settings: Settings | None = None
    text: str = ""  # what was analysed (narration playback synthesises from it)
    sounds: dict[str, np.ndarray] = field(default_factory=dict)  # each scene's sound by sound_id, for waveforms


def text_id(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def analyse(text: str, script: Path, synth: Any) -> dict:
    """Problems, scenes and timing for `text`, as if saved at `script`. `synth` is the engine to time with."""
    return run(text, script, synth).report


def run(text: str, script: Path, synth: Any) -> Analysis:
    """analyse(), keeping the scene plans for previews."""
    try:
        parsed = parse(text, script)
    except ScriptError as e:
        return Analysis({"id": text_id(text), "problems": [_problem(e.line, str(e))], "scenes": [], "duration": None,
                         "missing": None}, text=text)
    titles = {scene.index: _title(scene) for scene in parsed.scenes}  # before any stand-ins replace pictures
    names = {b.line: _name(b) for scene in parsed.scenes for b in scene.blocks if isinstance(b, Media)}
    problems: list[dict] = []
    missing: set[int] = set()
    for block in (b for scene in parsed.scenes for b in scene.blocks):
        if isinstance(block, Media) and block.render:
            # The quick checks only: deeper validation (Mermaid's parser) starts Chromium, too slow per keystroke
            try:
                problems += [_problem(block.line, p) for p in render.renderer(block.render.name).check(block.render)]
            except render.RenderError as e:
                problems.append(_problem(block.line, str(e)))
        elif isinstance(block, Media) and not (parsed.base_dir / block.path).is_file():
            problems.append(_problem(block.line, f"file not found: {block.path}"))
            if block.kind in ("image", "video", "html"):
                # Time the scene anyway, with a stand-in picture (a missing clip's length is unknown)
                block.kind, block.path, block.render = "image", "", Render("placeholder", "", {})
                missing.add(block.line)
    estimator = EstimatingSynth(synth)
    try:
        builder = Builder(parsed, estimator, log=lambda _: None, measure_pages=False)
    except BuildError as e:
        problems.append(_problem(e.line, str(e)))
        return Analysis({"id": text_id(text), "problems": problems + [_warning(w) for w in parsed.warnings],
                         "scenes": [], "duration": None, "missing": None}, text=text)

    scenes: list[dict] = []
    kept: dict[int, ScenePlan] = {}
    sounds: dict[str, np.ndarray] = {}
    start = 0.0
    for group in merge_groups(parsed.scenes):
        missing_before = estimator.missing_chars
        try:
            plans = list(builder.plans(group, script.parent))
        except (BuildError, ConfigError) as e:
            problem = _problem(getattr(e, "line", None) or group[0].line, str(e))
            if not any(p["line"] == problem["line"] and p["message"] == problem["message"] for p in problems):
                problems.append(problem)
            plans = [None] * len(group)
        except Exception as e:  # noqa: BLE001 - a preview never takes the studio down
            problems.append(_problem(group[0].line, f"couldn't time this scene: {e}"))
            plans = [None] * len(group)
        for scene, plan in zip(group, plans):
            entry = {"index": scene.index, "line": scene.line, "title": titles[scene.index], "start": round(start, 3),
                     "duration": None, "paragraphs": [], "visuals": [], "slides": [], "transition": None, "marks": {},
                     "estimated": False, "sound": None,
                     # characters the engine would still be sent for this scene (merged scenes share one count)
                     "missing_chars": estimator.missing_chars - missing_before}
            if plan is not None:
                kept[scene.index] = plan
                entry["duration"] = round(plan.duration, 3)
                entry["paragraphs"] = [{"line": p.line, "start": round(p.start, 3), "end": round(p.end, 3),
                                        "estimated": p.estimated} for p in plan.paragraphs]
                entry["visuals"] = _showings(plan, names, missing)
                entry["slides"] = _slides(plan, scene)
                entry["transition"] = {"type": plan.transition[0], "seconds": plan.transition[1]} if plan.transition else None
                entry["marks"] = {name: round(t, 3) for name, t in plan.marks.items()}
                entry["estimated"] = any(p.estimated for p in plan.paragraphs)
                if len(plan.audio):
                    entry["sound"] = sound_id(plan.audio)
                    sounds[entry["sound"]] = plan.audio
                start += plan.duration
            scenes.append(entry)
    builder.close()
    problems += [_warning(w) for w in parsed.warnings]
    return Analysis({
        "id": text_id(text),
        "size": [builder.settings.width, builder.settings.height],
        "problems": sorted(problems, key=lambda p: p["line"]),
        "scenes": scenes,
        "duration": round(start, 3),
        "missing": {"paragraphs": estimator.estimates, "characters": estimator.missing_chars},
        "notes": sorted(builder.notes),
    }, kept, builder.settings, text, sounds)
