"""ffmpeg helpers: locate the binary, probe media, decode audio, grab frames."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from functools import cache
from pathlib import Path

import numpy as np
from PIL import Image


class MediaError(Exception):
    pass


@cache
def ffmpeg() -> str:
    """$NARRATE_FFMPEG, else ffmpeg on PATH, else the static build bundled with imageio-ffmpeg."""
    if env := os.environ.get("NARRATE_FFMPEG"):
        return env
    if found := shutil.which("ffmpeg"):
        return found
    import imageio_ffmpeg

    return imageio_ffmpeg.get_ffmpeg_exe()


def run(args: list[str], *, input: bytes | None = None) -> bytes:
    proc = subprocess.run(
        [ffmpeg(), "-hide_banner", "-nostdin", "-y", *args],
        input=input, capture_output=True,
    )
    if proc.returncode != 0:
        tail = proc.stderr.decode(errors="replace").strip().splitlines()[-12:]
        raise MediaError("ffmpeg failed:\n  " + "\n  ".join(tail))
    return proc.stdout


@dataclass
class Probe:
    duration: float
    width: int | None
    height: int | None
    has_video: bool
    has_audio: bool
    has_subtitles: bool


@cache
def probe(path: Path) -> Probe:
    if path.suffix.lower() == ".gif":
        return _probe_gif(path)
    proc = subprocess.run([ffmpeg(), "-hide_banner", "-i", str(path)], capture_output=True)
    info = proc.stderr.decode(errors="replace")
    m = re.search(r"Duration: (\d+):(\d+):(\d+(?:\.\d+)?)", info)
    if not m:
        raise MediaError(f"cannot read duration of {path}")
    duration = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
    video = re.search(r"Stream #.*Video: .*?(\d{2,5})x(\d{2,5})", info)
    return Probe(
        duration=duration,
        width=int(video.group(1)) if video else None,
        height=int(video.group(2)) if video else None,
        has_video=bool(video),
        has_audio="Audio:" in info,
        has_subtitles="Subtitle:" in info,
    )


def _probe_gif(path: Path) -> Probe:
    with Image.open(path) as im:
        frames = getattr(im, "n_frames", 1)
        total = 0
        for i in range(frames):
            im.seek(i)
            total += im.info.get("duration", 100) or 100
        return Probe(total / 1000 if frames > 1 else 0.0, im.width, im.height, True, False, False)


def is_animated_gif(path: Path) -> bool:
    if path.suffix.lower() != ".gif":
        return False
    with Image.open(path) as im:
        return getattr(im, "n_frames", 1) > 1


def _atempo_chain(factor: float) -> list[str]:
    filters = []
    while factor > 2.0:
        filters.append("atempo=2.0")
        factor /= 2.0
    while factor < 0.5:
        filters.append("atempo=0.5")
        factor /= 0.5
    filters.append(f"atempo={factor:.6f}")
    return filters


def decode_audio(
    path: Path, sample_rate: int, *, start: float = 0.0, duration: float | None = None,
    tempo: float = 1.0,
) -> np.ndarray:
    """Mono float32 samples of `path` (optionally a segment, optionally sped up)."""
    args = []
    if start:
        args += ["-ss", f"{start:.3f}"]
    if duration is not None:
        args += ["-t", f"{duration:.3f}"]
    args += ["-i", str(path), "-vn", "-ac", "1", "-ar", str(sample_rate)]
    if abs(tempo - 1.0) > 1e-3:
        args += ["-filter:a", ",".join(_atempo_chain(tempo))]
    out = run([*args, "-f", "f32le", "-"])
    return np.frombuffer(out, dtype=np.float32).copy()


def extract_frame(path: Path, at: float, out_png: Path) -> Path:
    run(["-ss", f"{max(0.0, at):.3f}", "-i", str(path), "-frames:v", "1", str(out_png)])
    if not out_png.exists():
        # Seeking past the last frame yields nothing: take the final frame instead
        run(["-sseof", "-0.5", "-i", str(path), "-update", "1", str(out_png)])
    return out_png
