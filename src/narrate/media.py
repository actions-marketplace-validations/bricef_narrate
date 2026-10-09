"""ffmpeg helpers: locate the binary, probe media, decode audio, grab frames."""

from __future__ import annotations

import hashlib
import os
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import threading
import urllib.request
from collections.abc import Iterable
from dataclasses import dataclass
from functools import cache
from pathlib import Path

import numpy as np
from PIL import Image


class MediaError(Exception):
    pass


# narrate uses a current static ffmpeg rather than whatever is installed: the
# 7.0.x builds segfault intermittently on many-input filter graphs (#37). BtbN
# prunes dated builds, so the release series is pinned and each download is
# checked against the release's published SHA-256; once fetched it is kept.
FFMPEG_SERIES = "9.0"
FFMPEG_RELEASE = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/"
_fetch_lock = threading.Lock()


def ffmpeg_asset(machine: str | None = None, system: str | None = None) -> str | None:
    arch = {"x86_64": "linux64", "amd64": "linux64", "aarch64": "linuxarm64",
            "arm64": "linuxarm64"}.get((machine or platform.machine()).lower())
    if (system or sys.platform) != "linux" or arch is None:
        return None
    return f"ffmpeg-n{FFMPEG_SERIES}-latest-{arch}-gpl-{FFMPEG_SERIES}.tar.xz"


def managed_ffmpeg() -> Path:
    """Where narrate keeps its own ffmpeg (it may not be downloaded yet)."""
    from .tts import tools_dir

    return tools_dir() / "ffmpeg" / f"n{FFMPEG_SERIES}" / "ffmpeg"


def ensure_ffmpeg(log=lambda msg: print(msg, file=sys.stderr), opener=urllib.request.urlopen) -> Path:
    exe = managed_ffmpeg()
    with _fetch_lock:
        if exe.exists():
            return exe
        asset = ffmpeg_asset()
        if asset is None:
            raise MediaError(f"no managed ffmpeg for {sys.platform}/{platform.machine()}; set NARRATE_FFMPEG")
        log(f"downloading ffmpeg {FFMPEG_SERIES} (first use only, about 150 MB) …")
        with opener(FFMPEG_RELEASE + "checksums.sha256") as resp:
            sums = resp.read().decode()
        expected = next((line.split()[0] for line in sums.splitlines() if line.strip().endswith(asset)), None)
        if expected is None:
            raise MediaError(f"{asset} is not listed in the release checksums")
        exe.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=exe.parent) as tmp:
            archive = Path(tmp) / asset
            digest = hashlib.sha256()
            with opener(FFMPEG_RELEASE + asset) as resp, open(archive, "wb") as out:
                while chunk := resp.read(1 << 20):
                    digest.update(chunk)
                    out.write(chunk)
            if digest.hexdigest() != expected:
                raise MediaError(f"checksum mismatch for {asset}; download discarded")
            with tarfile.open(archive, "r:xz") as tar:
                member = next((m for m in tar.getmembers() if m.isfile() and m.name.endswith("/bin/ffmpeg")), None)
                if member is None:
                    raise MediaError(f"{asset} has no bin/ffmpeg")
                part = exe.with_suffix(".part")
                with tar.extractfile(member) as src, open(part, "wb") as dst:
                    shutil.copyfileobj(src, dst)
            part.chmod(0o755)
            part.rename(exe)
        return exe


@cache
def ffmpeg() -> str:
    """$NARRATE_FFMPEG, else narrate's managed ffmpeg (downloaded on first use)."""
    if env := os.environ.get("NARRATE_FFMPEG"):
        return env
    try:
        return str(ensure_ffmpeg())
    except (OSError, MediaError) as e:
        found = shutil.which("ffmpeg")
        if found is None:
            raise MediaError(f"ffmpeg {FFMPEG_SERIES} is unavailable ({e}); set NARRATE_FFMPEG") from None
        print(f"warning: couldn't fetch ffmpeg {FFMPEG_SERIES} ({e}); using {found}", file=sys.stderr)
        return found


def run(args: list[str], *, input: bytes | None = None) -> bytes:
    proc = subprocess.run(
        [ffmpeg(), "-hide_banner", "-nostdin", "-y", *args],
        input=input, capture_output=True,
    )
    if proc.returncode != 0:
        tail = proc.stderr.decode(errors="replace").strip().splitlines()[-12:]
        raise MediaError("ffmpeg failed:\n  " + "\n  ".join(tail))
    return proc.stdout


def encode_frames(frames: Iterable[bytes], width: int, height: int, fps: int, args: list[str], out: Path) -> Path:
    """Encode raw RGB24 frames streamed to ffmpeg's stdin (input 0); `args` holds any further inputs and outputs."""
    return encode_stream(frames, ["-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{width}x{height}", "-r", str(fps)],
                         args, out)


def encode_images(images: Iterable[bytes], fps: int, args: list[str], out: Path) -> Path:
    """Encode PNG images streamed to ffmpeg's stdin (input 0), one per frame."""
    return encode_stream(images, ["-f", "image2pipe", "-framerate", str(fps), "-c:v", "png"], args, out)


def encode_stream(chunks: Iterable[bytes], input_args: list[str], args: list[str], out: Path) -> Path:
    """Feed `chunks` to ffmpeg's stdin as input 0, described by `input_args`."""
    with tempfile.TemporaryFile() as errors:
        proc = subprocess.Popen(
            [ffmpeg(), "-hide_banner", "-y", "-loglevel", "error", *input_args, "-i", "-", *args, str(out)],
            stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=errors,
        )
        try:
            for chunk in chunks:
                proc.stdin.write(chunk)
        except BrokenPipeError:
            pass  # ffmpeg stopped reading (enough frames, or an error reported below)
        finally:
            proc.stdin.close()
        if proc.wait() != 0:
            errors.seek(0)
            tail = errors.read().decode(errors="replace").strip().splitlines()[-12:]
            raise MediaError("ffmpeg failed:\n  " + "\n  ".join(tail))
    return out


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


def loudness(samples: np.ndarray, sample_rate: int) -> float | None:
    """Integrated loudness in LUFS (ITU-R BS.1770 via ffmpeg's ebur128), or None if too short to gate."""
    if len(samples) < int(0.4 * sample_rate):
        return None  # shorter than one 400 ms gating block
    proc = subprocess.run(
        [ffmpeg(), "-hide_banner", "-nostats", "-f", "f32le", "-ar", str(sample_rate), "-ac", "1", "-i", "-",
         "-af", "ebur128=framelog=quiet", "-f", "null", "-"],
        input=np.asarray(samples, dtype="<f4").tobytes(), capture_output=True,
    )
    m = re.search(r"Integrated loudness:\s*I:\s*(-?[\d.]+|-inf) LUFS", proc.stderr.decode(errors="replace"))
    if proc.returncode != 0 or not m or m.group(1) == "-inf" or float(m.group(1)) <= -70:
        return None
    return float(m.group(1))


def time_stretch(samples: np.ndarray, sample_rate: int, tempo: float) -> np.ndarray:
    """Speed mono float32 audio up (tempo > 1) or slow it down without changing its pitch."""
    out = run(["-f", "f32le", "-ar", str(sample_rate), "-ac", "1", "-i", "-",
               "-filter:a", ",".join(_atempo_chain(tempo)), "-f", "f32le", "-"],
              input=np.asarray(samples, dtype="<f4").tobytes())
    return np.frombuffer(out, dtype=np.float32).copy()


def pitch_shift(samples: np.ndarray, sample_rate: int, ratio: float) -> np.ndarray:
    """Raise (ratio > 1) or lower mono float32 audio's pitch, keeping its duration (rubberband)."""
    out = run(["-f", "f32le", "-ar", str(sample_rate), "-ac", "1", "-i", "-",
               "-filter:a", f"rubberband=pitch={ratio:.6f}", "-f", "f32le", "-"],
              input=np.asarray(samples, dtype="<f4").tobytes())
    return np.frombuffer(out, dtype=np.float32).copy()


def extract_frame(path: Path, at: float, out_png: Path) -> Path:
    run(["-ss", f"{max(0.0, at):.3f}", "-i", str(path), "-frames:v", "1", str(out_png)])
    if not out_png.exists():
        # Seeking past the last frame yields nothing: take the final frame instead
        run(["-sseof", "-0.5", "-i", str(path), "-update", "1", str(out_png)])
    return out_png
