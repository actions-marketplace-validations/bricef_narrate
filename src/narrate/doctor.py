"""Environment checks (`narrate doctor`) and actionable setup errors."""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from . import media


class SetupError(Exception):
    """Something outside the script is missing; the message says how to fix it."""


BROWSER_INSTALL = "uv run playwright install chromium"
BROWSER_DEPS = ("uv run playwright install-deps chromium (needs root); without root, see "
                "docs/building.md, Troubleshoot")

FONT_DIRS = [Path("/usr/share/fonts"), Path("/usr/local/share/fonts"), Path.home() / ".fonts",
             Path.home() / ".local/share/fonts", Path("/Library/Fonts"), Path("/System/Library/Fonts"),
             Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"]


def explain_browser_error(message: str) -> str:
    """Turn a Playwright launch failure into a one-line fix."""
    if "Executable doesn't exist" in message or "playwright install" in message.lower():
        return f"Chromium is not installed for Playwright. Fix: {BROWSER_INSTALL}"
    if "shared librar" in message or "missing dependencies" in message.lower():
        missing = sorted({part.split(":")[0].strip() for part in message.split("\n")
                          if ".so" in part and "error while loading" in part})
        detail = f" ({', '.join(missing)})" if missing else ""
        return f"Chromium can't start: system libraries are missing{detail}. Fix: {BROWSER_DEPS}"
    first = message.strip().splitlines()[0] if message.strip() else "unknown error"
    return f"Chromium failed to start: {first}"


def launch_chromium(playwright, args: list[str]):
    from playwright.sync_api import Error

    try:
        return playwright.chromium.launch(args=args)
    except Error as e:
        raise SetupError(explain_browser_error(str(e))) from None


@dataclass
class Check:
    name: str
    ok: bool
    detail: str
    fix: str = ""


def ffmpeg_version(banner: str) -> tuple[int, int] | None:
    """(major, minor) from `ffmpeg -version`; None for builds from git, which name a commit instead."""
    m = re.match(r"ffmpeg version n?(\d+)\.(\d+)", banner)
    return (int(m.group(1)), int(m.group(2))) if m else None


def check_ffmpeg() -> list[Check]:
    """The ffmpeg a build will use, picked in the same order as media.ffmpeg()."""
    source, exe = media.find_ffmpeg()
    if source == "download":
        # Not a fault: like the models, it downloads on the first build
        return [Check("ffmpeg", True, f"ffmpeg {media.FFMPEG_SERIES} downloads on the first build "
                      "(about 150 MB), or now with `narrate models`")]
    if source == "none":
        return [Check("ffmpeg", False, f"none on PATH, and {media.no_managed_ffmpeg()}", media.ffmpeg_fix())]
    if source == "NARRATE_FFMPEG" and media.ffmpeg_asset() is not None:
        fix = "unset NARRATE_FFMPEG to use narrate's own, or point it at a full ffmpeg build"
    else:
        fix = media.ffmpeg_fix()
    try:
        version = subprocess.run([exe, "-hide_banner", "-version"], capture_output=True, text=True).stdout
        filters = subprocess.run([exe, "-hide_banner", "-filters"], capture_output=True, text=True).stdout
        encoders = subprocess.run([exe, "-hide_banner", "-encoders"], capture_output=True, text=True).stdout
    except OSError as e:
        return [Check("ffmpeg", False, f"{exe} ({source}): {e.strerror or e}", fix)]
    banner = version.splitlines()[0] if version.strip() else "unknown version"
    found = ffmpeg_version(banner)
    # narrate is tested with the series it pins; 7.0 segfaults on transition graphs (#37)
    if found is not None and found < tuple(int(n) for n in media.FFMPEG_SERIES.split(".")):
        checks = [Check("ffmpeg", False, f"{banner} ({exe}) is older than {media.FFMPEG_SERIES}; "
                        "ffmpeg 7.0 crashes on some transitions", fix)]
    else:
        checks = [Check("ffmpeg", True, f"{banner} ({exe})")]
    needs = {"libx264 encoder": " libx264 " in encoders, "subtitles filter (libass)": " subtitles " in filters,
             "xfade filter": " xfade " in filters, "rubberband filter (pitch)": " rubberband " in filters}
    for name, ok in needs.items():
        checks.append(Check(f"ffmpeg {name}", ok, "present" if ok else "missing", "" if ok else fix))
    return checks


def check_chromium() -> Check:
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = launch_chromium(p, [])
            version = browser.version
            browser.close()
        return Check("chromium", True, f"headless Chromium {version}")
    except SetupError as e:
        detail, _, fix = str(e).partition(" Fix: ")
        return Check("chromium", False, detail, fix)


def find_font(*names: str) -> Path | None:
    for d in FONT_DIRS:
        if not d.is_dir():
            continue
        for name in names:
            hits = list(d.rglob(name))
            if hits:
                return hits[0]
    return None


def check_fonts() -> Check:
    font = find_font("DejaVuSans.ttf")
    if font:
        return Check("fonts", True, f"DejaVu Sans ({font})")
    return Check("fonts", False, "DejaVu Sans not found; slides and subtitles fall back to other fonts",
                 "install fonts-dejavu (or the DejaVu fonts for your OS)")


def check_kokoro() -> Check:
    from .tts import MODEL_FILES, model_dir

    missing = [f for f in MODEL_FILES if not (model_dir() / f).exists()]
    if missing:
        return Check("kokoro models", True, "download on the first Kokoro build (about 350 MB), "
                     "or now with `narrate models`")
    size = sum((model_dir() / f).stat().st_size for f in MODEL_FILES) / 1e6
    return Check("kokoro models", True, f"{model_dir()} ({size:.0f} MB)")


def check_stt() -> Check:
    from .stt import model_dir, model_name

    found = any(model_dir().rglob("model.bin")) if model_dir().is_dir() else False
    detail = (f"faster-whisper {model_name()} downloaded" if found
              else f"faster-whisper {model_name()} downloads when a recording first needs subtitles")
    return Check("speech-to-text", True, detail)


def check_mermaid() -> Check:
    from . import mermaid

    if env := os.environ.get("NARRATE_MERMAID_JS"):
        found = Path(env).is_file()
        return Check("mermaid.js", found, env if found else f"{env} (NARRATE_MERMAID_JS) doesn't exist",
                     "" if found else "point NARRATE_MERMAID_JS at mermaid.min.js, or unset it")
    if mermaid.managed_script().exists():
        return Check("mermaid.js", True, f"{mermaid.MERMAID_VERSION} ({mermaid.managed_script()})")
    return Check("mermaid.js", True, f"{mermaid.MERMAID_VERSION} downloads the first time a script uses "
                 "render:mermaid (about 5 MB), or now with `narrate models`")


def check_elevenlabs() -> Check:
    key = os.environ.get("ELEVENLABS_API_KEY", "")
    if not key:
        return Check("elevenlabs key", True, "not set (optional; --tts auto uses Kokoro)")
    if not key.startswith("sk_"):
        return Check("elevenlabs key", False, "ELEVENLABS_API_KEY doesn't look like an ElevenLabs key (sk_…)",
                     "check the value in .env")
    return Check("elevenlabs key", True, "set (--tts auto uses ElevenLabs)")


def run_checks() -> list[Check]:
    return [*check_ffmpeg(), check_chromium(), check_fonts(), check_kokoro(), check_stt(), check_mermaid(),
            check_elevenlabs()]
