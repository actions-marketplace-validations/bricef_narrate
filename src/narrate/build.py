"""Build a video from a parsed script: plan each scene, render segments, mux.

Timing follows spec §4: a scene's narration track (speech, pauses, recorded
audio) is laid out first, then the scene's duration is derived from it and from
any video's sync mode. The global timeline is kept in whole frames, so every
scene's audio is cut to exactly its frames' length and audio and video never
drift apart.
"""

from __future__ import annotations

import shutil
import sys
import tempfile
import wave
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import numpy as np

from . import media, subtitles
from .config import (
    BUILTIN_MUSIC, FPS, ConfigError, Settings, SubtitleConfig, parse_color, parse_number, parse_speed,
    parse_time, parse_volume, settings_from_header,
)
from .doctor import find_font
from .frames import FrameRenderer, FrameSpec, SlideSpec
from .script import ANIMATED_SIZES, POSITIONS, SIZES, Directive, Media, Narration, Quote, Script, Slide
from .subtitles import Cue
from .text import ELLIPSIS_PAUSE, speech_parts, ssml_text, subtitle_text
from .tts import SAMPLE_RATE, Synth, Voice

SR = SAMPLE_RATE
PARAGRAPH_PAUSE = {"normal": 0.4, "fragment": 0.1}
DEFAULT_STILL_SECONDS = 1.0
MAX_PAUSE_UNTIL = 600.0
TARGETS = {  # x264 preset, crf, faststart
    "offline": ("medium", 16, False),
    "online": ("medium", 18, True),
    "self-hosted": ("slow", 23, True),
}
UNSUPPORTED = {
    "voice-pitch": "voice-pitch (ignored)",
    "voice-emphasis": "voice-emphasis (ignored)",
}


class BuildError(Exception):
    def __init__(self, message: str, line: int | None = None):
        super().__init__(message)
        self.line = line


@dataclass
class Visual:
    kind: str  # "still" | "video"
    path: Path | None = None
    fit: str = "cover"
    position: str = "center"
    sync: str = "freeze"
    start: float = 0.0
    length: float = 0.0
    volume: float = 1.0
    has_audio: bool = False
    frames: int = 0


@dataclass
class ScenePlan:
    index: int
    visuals: list[Visual]
    spec: FrameSpec  # slide, callouts, theme: shared by every visual of the scene
    audio: np.ndarray
    duration: float
    cues: list[Cue] = field(default_factory=list)


@dataclass
class BuildResult:
    video: Path
    poster: Path
    subtitle_files: list[Path]
    duration: float
    notes: list[str]


class AudioTrack:
    """A scene's narration sequence: segments played back to back."""

    def __init__(self) -> None:
        self.chunks: list[np.ndarray] = []
        self.length = 0  # samples

    @property
    def seconds(self) -> float:
        return self.length / SR

    def add(self, samples: np.ndarray) -> None:
        self.chunks.append(samples.astype(np.float32, copy=False))
        self.length += len(samples)

    def silence(self, seconds: float) -> None:
        if seconds > 0:
            self.add(np.zeros(int(round(seconds * SR)), dtype=np.float32))

    def until(self, seconds: float) -> None:
        self.silence(seconds - self.seconds)

    def samples(self) -> np.ndarray:
        return np.concatenate(self.chunks) if self.chunks else np.zeros(0, dtype=np.float32)


def fit_length(samples: np.ndarray, n: int, *, tile: bool = False) -> np.ndarray:
    if len(samples) >= n:
        return samples[:n]
    if tile and len(samples):
        return np.tile(samples, -(-n // len(samples)))[:n]
    return np.concatenate([samples, np.zeros(n - len(samples), dtype=np.float32)])


def apply_gain(samples: np.ndarray, volume: float | str) -> np.ndarray:
    if volume == "normalized":
        rms = float(np.sqrt(np.mean(samples**2))) if len(samples) else 0.0
        return samples * (0.1 / rms) if rms > 1e-6 else samples
    return samples * (10 ** (float(volume) / 20)) if volume else samples


class Builder:
    def __init__(self, script: Script, synth: Synth, *, log: Callable[[str], None] | None = None):
        self.script = script
        self.synth = synth
        self.log = log or (lambda msg: print(msg, file=sys.stderr))
        self.notes: set[str] = set()
        try:
            self.settings: Settings = settings_from_header(script.header, script.warnings)
        except ConfigError as e:
            raise BuildError(str(e)) from None
        self.mode = "normal"  # narration-mode persists across scenes
        if self.settings.voice_pitch:
            self.notes.add(UNSUPPORTED["voice-pitch"])
        if self.settings.transition and self.settings.transition.split()[0].lower() != "none":
            self.notes.add("transitions (scenes cut instead)")
        self._voices: dict[tuple[str | None, str | None], Voice] = {}

    # -- helpers -------------------------------------------------------------

    def _path(self, name: str, line: int) -> Path:
        path = (self.script.base_dir / name).resolve()
        if not path.is_file():
            raise BuildError(f"file not found: {name}", line)
        return path

    def _voice(self, name: str | None, lang: str | None) -> Voice:
        key = (name, lang)
        if key not in self._voices:
            self._voices[key] = self.synth.resolve(name, lang.lower() if lang else None, self.notes)
        return self._voices[key]

    def _theme(self, value: str, line: int) -> str:
        if value.lower().endswith(".css"):
            return str(self._path(value, line))
        if value.lower() not in ("default", "light"):
            raise BuildError(f"unknown theme {value!r}", line)
        return value.lower()

    # -- planning ------------------------------------------------------------

    def plan_scene(self, scene, workdir: Path) -> ScenePlan:
        s = self.settings
        voice_name, lang = s.voice, s.narration_language
        speed, volume = s.voice_speed, s.voice_volume
        image_size: str | None = None
        image_position: str | None = None
        duration: float | None = None
        spec = FrameSpec(canvas=s.canvas, theme=self._theme(s.theme, 0) if s.theme else "default")
        track = AudioTrack()
        sources: list[Media] = []
        slides: list[Slide] = []
        quotes: list[str] = []
        narration_spans: list[tuple[float, float, str]] = []

        for block in scene.blocks:
            try:
                if isinstance(block, Directive):
                    key, value = block.key, block.value
                    if key == "voice":
                        voice_name = str(value)
                    elif key == "voice-speed":
                        speed = parse_speed(value)
                    elif key == "voice-volume":
                        volume = parse_volume(value)
                    elif key == "narration-language":
                        lang = None if str(value).lower() == "default" else str(value)
                    elif key == "narration-mode":
                        mode = str(value).lower()
                        if mode == "merge":
                            self.notes.add("narration-mode: merge (treated as normal)")
                            mode = "normal"
                        if mode not in PARAGRAPH_PAUSE:
                            raise ConfigError(f"invalid narration-mode {value!r}")
                        self.mode = mode
                    elif key == "pause":
                        track.silence(parse_number(value, "pause"))
                    elif key == "pause-until":
                        track.until(min(parse_time(value), MAX_PAUSE_UNTIL))
                    elif key == "duration":
                        duration = parse_number(value, "duration")
                    elif key == "canvas":
                        spec.canvas = parse_color(value, "canvas")
                    elif key == "theme":
                        spec.theme = self._theme(str(value), block.line)
                    elif key == "font-size":
                        spec.font_size = int(parse_number(value, "font-size"))
                    elif key == "image-size":
                        image_size = _choice(value, SIZES | ANIMATED_SIZES, "image-size")
                    elif key == "image-position":
                        image_position = _choice(value, POSITIONS, "image-position")
                    elif key == "callout":
                        if not isinstance(value, dict):
                            raise ConfigError("callout needs properties such as cx/cy")
                        spec.callouts.append(dict(value))
                    elif key == "transition":
                        if str(value).split()[0].lower() != "none":
                            self.notes.add("transitions (scenes cut instead)")
                    elif key in UNSUPPORTED:
                        self.notes.add(UNSUPPORTED[key])
                elif isinstance(block, Media):
                    if block.kind == "audio":
                        path = self._path(block.path, block.line)
                        track.add(media.decode_audio(path, SR))
                    else:
                        if block.size is None and image_size and block.kind == "image":
                            block.size = image_size
                        if block.position is None and image_position:
                            block.position = image_position
                        sources.append(block)
                elif isinstance(block, Slide):
                    slides.append(block)
                elif isinstance(block, Quote):
                    quotes.append(block.text)
                elif isinstance(block, Narration):
                    voice = self._voice(voice_name, lang)
                    if block.ssml:
                        self.notes.add("SSML (tags stripped, text read plainly)")
                        parts = [ssml_text(block.text)]
                    else:
                        parts = speech_parts(block.text, voice.lang or "en", self.notes)
                    start = track.seconds
                    for i, part in enumerate(parts):
                        if i:
                            track.silence(ELLIPSIS_PAUSE)
                        track.add(apply_gain(self.synth.synth(part, voice, speed, self.notes), volume))
                    if parts:
                        caption = subtitle_text(ssml_text(block.text) if block.ssml else block.text)
                        narration_spans.append((start, track.seconds, caption))
                        track.silence(PARAGRAPH_PAUSE[self.mode])
            except ConfigError as e:
                raise BuildError(str(e), block.line) from None

        if len(slides) > 1:
            self.notes.add("several slides in one scene (only the first is shown)")
        if slides:
            spec.slide = SlideSpec(lang=slides[0].lang, text=slides[0].text)

        visuals = [self._visual(m, workdir) for m in sources]
        videos = [v for v in visuals if v.kind == "video"]
        if videos and len(visuals) > 1:
            self.notes.add("a video mixed with other images/videos in one scene (only the first video is shown)")
            visuals = videos[:1]

        narration = track.samples()
        a = track.seconds
        if videos:
            video = visuals[0]
            d = _video_duration(video, a, duration)
        elif a > 0:
            d = max(a, duration or 0.0)
        else:
            d = duration if duration is not None else DEFAULT_STILL_SECONDS
        d = max(d, 1 / FPS)

        n = int(round(d * SR))
        if videos and visuals[0].sync == "loop-audio":
            audio = fit_length(narration, n, tile=True)
        else:
            audio = fit_length(narration, n)
        if videos and visuals[0].has_audio and visuals[0].volume:
            audio = audio + self._clip_audio(visuals[0], d, n)

        if quotes:
            texts = [q for q in quotes if q]
            cues = subtitles.spread(0.0, d, texts) if texts else []
        elif s.subtitles.mode != "none":
            cues = [c for start, end, text in narration_spans
                    for c in subtitles.narration_cues(start, end, text, s.subtitles.break_chars)]
        else:
            cues = []
        return ScenePlan(scene.index, visuals, spec, audio, d, cues)

    def _visual(self, m: Media, workdir: Path) -> Visual:
        path = self._path(m.path, m.line)
        size = m.size or self.settings.asset_resize
        if size in ANIMATED_SIZES:
            self.notes.add("pan/zoom image animation (shown static)")
            size = "cover"
        position = m.position or "center"
        if m.kind == "image" and not media.is_animated_gif(path):
            return Visual("still", path, size, position)
        info = media.probe(path)
        if m.segment and m.segment[1] is None:
            at = {"start": 0.0, "end": max(0.0, info.duration - 0.1)}.get(m.segment[0])
            frame = workdir / f"still-{m.line}.png"
            media.extract_frame(path, parse_time(m.segment[0]) if at is None else at, frame)
            return Visual("still", frame, size, position)
        start, end = 0.0, info.duration
        if m.segment:
            a, b = m.segment
            start = 0.0 if a == "start" else parse_time(a)
            end = info.duration if b == "end" else min(info.duration, parse_time(b))
        if end <= start:
            raise BuildError(f"empty video segment in {m.path}", m.line)
        default_sync = "loop" if path.suffix.lower() == ".gif" else "freeze"
        return Visual(
            "video", path, size, position, sync=m.sync or default_sync, start=start,
            length=end - start, volume=1.0 if m.volume is None else m.volume,
            has_audio=info.has_audio,
        )

    def _clip_audio(self, v: Visual, d: float, n: int) -> np.ndarray:
        tempo = v.length / d if v.sync == "match" else 1.0
        clip = media.decode_audio(v.path, SR, start=v.start, duration=v.length, tempo=tempo)
        clip = fit_length(clip, n, tile=v.sync in ("loop", "trim-or-loop"))
        return clip * v.volume

    # -- rendering -----------------------------------------------------------

    def build(self, out: Path, *, workdir: Path | None = None) -> BuildResult:
        own_workdir = workdir is None
        work = Path(tempfile.mkdtemp(prefix="narrate-")) if own_workdir else workdir
        work.mkdir(parents=True, exist_ok=True)
        try:
            return self._build(out, work)
        finally:
            if own_workdir:
                shutil.rmtree(work, ignore_errors=True)

    def _build(self, out: Path, work: Path) -> BuildResult:
        s = self.settings
        scenes = self.script.scenes
        if not scenes:
            raise BuildError("the script has no scenes")
        plans: list[ScenePlan] = []
        for scene in scenes:
            self.log(f"scene {scene.index}/{len(scenes)}: narration")
            plans.append(self.plan_scene(scene, work))

        segments: list[Path] = []
        audio_parts: list[np.ndarray] = []
        cues: list[Cue] = []
        scene_samples: list[int] = []
        frame = 0
        with FrameRenderer(s.width, s.height, work) as renderer:
            for plan in plans:
                self.log(f"scene {plan.index}/{len(plans)}: video")
                start_f = frame
                end_f = max(start_f + 1, int(round(start_f + plan.duration * FPS)))
                frames = end_f - start_f
                samples = int(round(end_f * SR / FPS)) - int(round(start_f * SR / FPS))
                audio_parts.append(fit_length(plan.audio, samples))
                scene_samples.append(samples)
                offset = start_f / FPS
                cues += [Cue(c.start + offset, min(c.end, frames / FPS) + offset, c.text) for c in plan.cues]
                segments += self._render_scene(plan, frames, renderer, work)
                frame = end_f

        total = frame / FPS
        audio = np.concatenate(audio_parts)
        if s.background:
            audio = audio + self._music(len(audio), scene_samples)
        peak = float(np.abs(audio).max()) if len(audio) else 0.0
        if peak > 0.99:
            audio = audio * (0.99 / peak)
        wav = work / "audio.wav"
        _write_wav(wav, audio)

        self.log("muxing")
        out.parent.mkdir(parents=True, exist_ok=True)
        subtitle_files = self._mux(out, segments, wav, cues, work)
        poster = out.with_suffix(".jpg")
        media.extract_frame(out, _poster_time(s.poster_time, total), poster)
        return BuildResult(out, poster, subtitle_files, total, sorted(self.notes))

    def _render_scene(self, plan: ScenePlan, frames: int, renderer: FrameRenderer, work: Path) -> list[Path]:
        base = work / f"scene-{plan.index:03d}"
        if not plan.visuals:
            png = renderer.render(plan.spec, base.with_suffix(".png"))
            return [_encode_still(png, frames, base.with_suffix(".mp4"))]
        if plan.visuals[0].kind == "video":
            v = plan.visuals[0]
            overlay = None
            if plan.spec.slide or plan.spec.callouts:
                spec = FrameSpec(**{**plan.spec.__dict__, "over_video": True})
                overlay = renderer.render(spec, base.with_name(base.name + "-overlay.png"))
            return [self._encode_video(v, plan, frames, overlay, base.with_suffix(".mp4"))]
        segments = []
        count = len(plan.visuals)
        for i, v in enumerate(plan.visuals):
            share = frames // count + (1 if i < frames % count else 0)
            if share <= 0:
                continue
            spec = FrameSpec(**{**plan.spec.__dict__, "image": v.path, "fit": v.fit, "position": v.position})
            png = renderer.render(spec, base.with_name(f"{base.name}-{i}.png"))
            segments.append(_encode_still(png, share, base.with_name(f"{base.name}-{i}.mp4")))
        return segments

    def _encode_video(self, v: Visual, plan: ScenePlan, frames: int, overlay: Path | None, out: Path) -> Path:
        w, h = self.settings.width, self.settings.height
        resize = [*_resize_filters(v.fit, v.position, w, h, plan.spec.canvas or "#000000"), "setsar=1"]
        segment = ["-ss", f"{v.start:.3f}", "-t", f"{v.length:.3f}", "-i", str(v.path)]
        if v.sync in ("loop", "trim-or-loop"):
            # Encode one pass of the segment at output size, then loop that file
            # from disk: ffmpeg's loop filter holds every frame in memory
            once = out.with_name(out.stem + "-once.mp4")
            media.run([*segment, "-vf", ",".join(["setpts=PTS-STARTPTS", f"fps={FPS}", *resize]),
                       "-frames:v", str(max(1, round(v.length * FPS))), "-an", *_SEGMENT_CODEC, str(once)])
            args = ["-stream_loop", "-1", "-i", str(once)]
            chain = ["setpts=PTS-STARTPTS"]
        else:
            args = segment
            chain = ["setpts=PTS-STARTPTS"]
            if v.sync == "match":
                chain.append(f"setpts=PTS/{v.length / plan.duration:.6f}")
            chain += [f"fps={FPS}", *resize,
                      f"tpad=stop_mode=clone:stop_duration={plan.duration + 1:.3f}"]
        graph = f"[0:v]{','.join(chain)}[base]"
        if overlay:
            args += ["-loop", "1", "-framerate", str(FPS), "-i", str(overlay)]
            graph += ";[base][1:v]overlay=0:0:format=auto[v]"
        else:
            graph += ";[base]null[v]"
        media.run([*args, "-filter_complex", graph, "-map", "[v]", "-frames:v", str(frames),
                   "-an", *_SEGMENT_CODEC, str(out)])
        return out

    def _music(self, total: int, scene_samples: list[int]) -> np.ndarray:
        bg = self.settings.background
        candidate = self.script.base_dir / bg.source
        if not candidate.is_file():
            if bg.source in BUILTIN_MUSIC:
                self.notes.add(f"built-in background track {bg.source!r} (not bundled; no music)")
                return np.zeros(total, dtype=np.float32)
            raise BuildError(f"background file not found: {bg.source}")
        music = fit_length(media.decode_audio(candidate, SR), total, tile=True) * bg.volume
        if bg.fade_in and scene_samples:
            n = min(scene_samples[0], total)
            music[:n] *= np.linspace(0.0, 1.0, n, dtype=np.float32)
        if bg.fade_out and scene_samples:
            n = min(scene_samples[-1], total)
            music[total - n:] *= np.linspace(1.0, 0.0, n, dtype=np.float32)
        return music

    def _mux(self, out: Path, segments: list[Path], wav: Path, cues: list[Cue], work: Path) -> list[Path]:
        s = self.settings
        listing = work / "segments.txt"
        listing.write_text("".join(f"file '{p.as_posix()}'\n" for p in segments))
        preset, crf, faststart = TARGETS[s.target]
        args = ["-f", "concat", "-safe", "0", "-i", str(listing), "-i", str(wav)]
        maps = ["-map", "0:v", "-map", "1:a"]
        codecs = ["-c:v", "libx264", "-preset", preset, "-crf", str(crf), "-pix_fmt", "yuv420p",
                  "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2"]
        files: list[Path] = []
        if s.subtitles.files and cues:
            srt, vtt = out.with_suffix(".srt"), out.with_suffix(".vtt")
            srt.write_text(subtitles.to_srt(cues), encoding="utf-8")
            vtt.write_text(subtitles.to_vtt(cues), encoding="utf-8")
            files = [srt, vtt]
            if s.subtitles.mode == "embed":
                args += ["-i", str(srt)]
                maps += ["-map", "2:s"]
                codecs += ["-c:s", "mov_text", "-metadata:s:s:0", "language=eng"]
        # Block-quote captions are explicit content: burn them in unless the
        # mode writes them to files instead
        burn = cues and (s.subtitles.burned or s.subtitles.mode == "none")
        if burn:
            codecs += ["-vf", self._subtitle_filter(cues, work)]
        if faststart:
            codecs += ["-movflags", "+faststart"]
        media.run([*args, *maps, *codecs, str(out)])
        return files

    def _subtitle_filter(self, cues: list[Cue], work: Path) -> str:
        s = self.settings
        cfg = s.subtitles if s.subtitles.burned else SubtitleConfig(mode="overlay")
        fonts = work / "fonts"
        fonts.mkdir(exist_ok=True)
        font_name = "DejaVu Sans"
        for name in ("DejaVuSans.ttf", "DejaVuSans-Bold.ttf"):
            if (found := find_font(name)) is not None:
                shutil.copy(found, fonts / name)
        if cfg.font:
            font_path = self._path(cfg.font, 0)
            shutil.copy(font_path, fonts / font_path.name)
            font_name = _font_family(font_path)
        ass = work / "captions.ass"
        ass.write_text(subtitles.to_ass(cues, cfg, s.width, s.height, font_name), encoding="utf-8")
        return f"subtitles=filename='{ass.as_posix()}':fontsdir='{fonts.as_posix()}'"


_SEGMENT_CODEC = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "12", "-pix_fmt", "yuv420p",
                  "-r", str(FPS), "-video_track_timescale", "15360"]


def _choice(value: Any, allowed: set[str], what: str) -> str:
    text = str(value).strip().lower()
    if text not in allowed:
        raise ConfigError(f"invalid {what} {value!r}")
    return text


def _video_duration(v: Visual, a: float, duration: float | None) -> float:
    """Scene length for a video scene (spec §4.2 sync table)."""
    length = v.length
    if a <= 0:
        return duration if duration is not None else length
    sync = v.sync
    if sync == "match" or sync == "trim-or-loop":
        d = a
    elif sync == "trim":
        d = min(length, a)
    else:  # freeze, loop, loop-audio
        d = max(length, a)
    return max(d, duration or 0.0)


def _resize_filters(fit: str, position: str, w: int, h: int, canvas: str) -> list[str]:
    if fit == "fit":
        return [f"scale={w}:{h}"]
    if fit == "contain":
        return [f"scale={w}:{h}:force_original_aspect_ratio=decrease",
                f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color={canvas}"]
    x = {"left": "0", "top-left": "0", "right": "iw-ow"}.get(position, "(iw-ow)/2")
    y = {"top": "0", "top-left": "0", "bottom": "ih-oh"}.get(position, "(ih-oh)/2")
    return [f"scale={w}:{h}:force_original_aspect_ratio=increase", f"crop={w}:{h}:{x}:{y}"]


def _encode_still(png: Path, frames: int, out: Path) -> Path:
    media.run(["-loop", "1", "-framerate", str(FPS), "-i", str(png), "-frames:v", str(frames),
               "-vf", "format=yuv420p,setsar=1", "-tune", "stillimage", *_SEGMENT_CODEC, str(out)])
    return out


def _write_wav(path: Path, audio: np.ndarray) -> None:
    pcm = (np.clip(audio, -1.0, 1.0) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())


def _poster_time(value: str, total: float) -> float:
    text = value.strip().lower()
    last = max(0.0, total - 1 / FPS)
    if text == "start":
        return 0.0
    if text == "end":
        return last
    if text.endswith("%"):
        return min(last, total * float(text[:-1]) / 100)
    return min(last, parse_time(text))


def _font_family(path: Path) -> str:
    from PIL import ImageFont

    return ImageFont.truetype(str(path), 10).getname()[0]
