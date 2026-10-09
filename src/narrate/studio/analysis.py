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

from .. import render
from ..build import Builder, BuildError, ScenePlan, merge_groups
from ..config import ConfigError, Settings
from ..script import Media, Narration, Render, Scene, ScriptError, Slide, parse
from ..tts import EstimatingSynth

_LINE = re.compile(r"^line (\d+): (.*)$", re.S)


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


@dataclass
class Analysis:
    """The report the studio shows, and the plans behind it (the preview composes frames from them)."""

    report: dict
    plans: dict[int, ScenePlan] = field(default_factory=dict)  # by scene index
    settings: Settings | None = None
    text: str = ""  # what was analysed (narration playback synthesises from it)


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
    problems: list[dict] = []
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
    estimator = EstimatingSynth(synth)
    try:
        builder = Builder(parsed, estimator, log=lambda _: None, measure_pages=False)
    except BuildError as e:
        problems.append(_problem(e.line, str(e)))
        return Analysis({"id": text_id(text), "problems": problems + [_warning(w) for w in parsed.warnings],
                         "scenes": [], "duration": None, "missing": None}, text=text)

    scenes: list[dict] = []
    kept: dict[int, ScenePlan] = {}
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
                     "duration": None, "paragraphs": [],
                     # characters the engine would still be sent for this scene (merged scenes share one count)
                     "missing_chars": estimator.missing_chars - missing_before}
            if plan is not None:
                kept[scene.index] = plan
                entry["duration"] = round(plan.duration, 3)
                entry["paragraphs"] = [{"line": p.line, "start": round(p.start, 3), "end": round(p.end, 3),
                                        "estimated": p.estimated} for p in plan.paragraphs]
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
    }, kept, builder.settings, text)
