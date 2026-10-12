"""What the studio shows about a script as it's typed (#52): problems, scenes and timing.

The editor's text is analysed without saving it. Timing comes from narrate's
own planner with an EstimatingSynth: speech already in the chosen engine's
cache gives exact lengths, and the rest are estimated from the text, so
nothing is synthesised or spent (design D9, D10). A scene that can't be
planned is reported and skipped, so one bad line doesn't blank the outline.
"""

from __future__ import annotations

import dataclasses
import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from .. import media, motion, render
from ..build import SR, Builder, BuildError, ScenePlan, merge_groups
from ..config import ConfigError, Settings, parse_overlay
from ..script import ANIMATED_SIZES, SIZES, Directive, Media, Narration, Render, Scene, ScriptError, Slide, parse
from ..text import MARK_RE
from ..tts import EstimatingSynth
from .edits import units

_LINE = re.compile(r"^line (\d+): (.*)$", re.S)


def _mark_places(text: str, scenes: list[Scene]) -> dict[int, dict[str, dict]]:
    """Where each scene's SSML marks are written (#75), so a cue on the timeline leads to its word:
    each <mark/>'s line, column and length (in the editor's units), by scene and name."""
    places: dict[int, dict[str, dict]] = {}
    for n, line in enumerate(text.split("\n"), 1):
        for m in MARK_RE.finditer(line):
            scene = next((s.index for s in reversed(scenes) if s.line <= n), None)
            if scene is not None:
                places.setdefault(scene, {}).setdefault(m["name"], {
                    "line": n, "column": units(line, m.start()), "length": units(line, m.end()) - units(line, m.start())})
    return places
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


def _options(block: Media) -> dict:
    """A picture's or clip's options as written on its line (the inspector shows and edits these, #62)."""
    segment = None
    if block.segment:
        segment = block.segment[0] + (f"-{block.segment[1]}" if block.segment[1] else "")
    pct = lambda v: f"{v * 100:.4g}%"  # noqa: E731
    window = lambda w: None if w is None else f"{pct(w[0])} {pct(w[1])}" + (f" {w[2]:g}" if w[2] != 1 else "")  # noqa: E731
    return {"fit": block.size if block.size in SIZES else None,
            "motion": block.size if block.size in ANIMATED_SIZES else None,
            "position": f"{pct(block.focus[0])} {pct(block.focus[1])}" if block.focus else block.position,
            "zoom": block.zoom, "sync": block.sync, "segment": segment,
            "volume": "mute" if block.volume == 0 else block.volume,
            "from": window(block.windows[0]) if block.windows else None,
            "to": window(block.windows[1]) if block.windows else None}


_sizes: dict[tuple[Path, int], tuple[int, int] | None] = {}


def _picture_size(path: Path) -> tuple[int, int] | None:
    """A picture's own size, read from its header (cached by modification time)."""
    try:
        key = (path, path.stat().st_mtime_ns)
    except OSError:
        return None
    if key not in _sizes:
        from PIL import Image

        try:
            with Image.open(path) as im:
                _sizes[key] = im.size
        except OSError:
            _sizes[key] = None
    return _sizes[key]


def _media_entry(line: int, kind: str, block: Media, options: dict, base: Path, settings: Settings) -> dict:
    """What the inspector needs about one picture, clip, page or render block."""
    path = block.path
    entry = {"line": line, "kind": kind, "file": path, "options": options, "size": None, "length": None,
             "windows": None, "crop": None, "focus": None}
    file = base / path if path else None
    w, h = settings.width, settings.height
    if kind == "picture" and file and file.is_file():
        entry["size"] = size = _picture_size(file)
        if size:
            position = block.position or "center"
            point = (block.focus[0] * size[0], block.focus[1] * size[1]) if block.focus else None
            crop = motion._align(*motion.cover_size(*size, w, h), (0.0, 0.0, *size), position, point)
            entry["crop"] = [round(v, 1) for v in crop]  # a still's cover framing
            entry["focus"] = list(block.focus) if block.focus else [(crop[0] + crop[2] / 2) / size[0],
                                                                       (crop[1] + crop[3] / 2) / size[1]]
            if options["motion"] or block.windows:
                zoom = options["zoom"] or settings.image_zoom
                start, end = motion.endpoints(options["motion"], position, *size, w, h, zoom, block.focus,
                                              block.windows)
                entry["windows"] = [[round(v, 1) for v in start], [round(v, 1) for v in end]]
    elif kind == "clip" and file and file.is_file():
        try:
            info = media.probe(file)
            entry["size"], entry["length"] = [info.width, info.height], round(info.duration, 3)
        except Exception:  # noqa: BLE001 - an unreadable clip is reported by the planner
            pass
    return entry


def _callouts(scene: Scene) -> list[dict]:
    """A scene's callouts, as written, for drawing and editing on the preview (#64)."""
    out = []
    for block in scene.blocks:
        if not (isinstance(block, Directive) and block.key == "callout" and isinstance(block.value, dict)):
            continue
        props = {str(k).lower(): str(v) for k, v in block.value.items()}
        entry: dict = {"line": block.line, "type": props.get("type", "circle").lower(),
                       "style": "mask" if props.get("style", "").lower() == "mask" else None}
        try:
            keys = ("cx", "cy") if entry["type"] == "circle" else ("left", "top", "right", "bottom")
            entry.update({k: float(props[k]) for k in keys})
            if entry["type"] == "circle":
                entry["size"] = float(props.get("size", 100))
            entry["alpha"] = float(props.get("alpha", 0.5))
        except (KeyError, ValueError):
            continue  # the planner reports it
        out.append(entry)
    return out


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
    # Each picture and clip as written, before stand-ins replace missing ones
    written = {b.line: ("render" if b.render else {"image": "picture", "video": "clip", "html": "page"}.get(b.kind, b.kind),
                        dataclasses.replace(b), _options(b))
               for scene in parsed.scenes for b in scene.blocks if isinstance(b, Media) and b.kind != "audio"}
    problems: list[dict] = []
    missing: set[int] = set()
    for block in (b for scene in parsed.scenes for b in scene.blocks):
        if isinstance(block, Directive) and block.key == "overlay":  # a scene's overlay page (#59)
            try:
                overlay = parse_overlay(block.value)
            except ConfigError as e:
                problems.append(_problem(block.line, str(e)))
            else:
                if overlay is not None and not (parsed.base_dir / overlay.file).is_file():
                    problems.append(_problem(block.line, f"file not found: {overlay.file}"))
            continue
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
        problems += [_problem(1, f"file not found: {spec.file}") for spec in builder.settings.overlays
                     if not (parsed.base_dir / spec.file).is_file()]  # the header's overlay pages (#59)
    except BuildError as e:
        problems.append(_problem(e.line, str(e)))
        return Analysis({"id": text_id(text), "problems": problems + [_warning(w) for w in parsed.warnings],
                         "scenes": [], "duration": None, "missing": None}, text=text)

    scenes: list[dict] = []
    kept: dict[int, ScenePlan] = {}
    places = _mark_places(text, parsed.scenes)
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
                     "callouts": _callouts(scene),
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
                entry["mark_places"] = {name: place for name, place in places.get(scene.index, {}).items()
                                        if name in plan.marks}
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
        "media": {str(line): _media_entry(line, kind, block, options, parsed.base_dir, builder.settings)
                  for line, (kind, block, options) in written.items()},
        "defaults": {"fit": builder.settings.asset_resize, "zoom": builder.settings.image_zoom},
    }, kept, builder.settings, text, sounds)
