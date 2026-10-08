"""Command line: narrate build | check | voices | models | doctor."""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

from . import media
from .build import Builder, BuildError
from .config import ConfigError, settings_from_header
from .doctor import SetupError, run_checks
from .script import Media, ScriptError, parse_file
from .tts import ELEVENLABS_VOICES, KOKORO_VOICES, NARAKEET_PROFILES, ensure_models, make_synth


def load_dotenv(*dirs: Path) -> None:
    """Read KEY=VALUE lines from .env files; variables already set win."""
    for d in dirs:
        env = d / ".env"
        if not env.is_file():
            continue
        for line in env.read_text().splitlines():
            key, sep, value = line.strip().partition("=")
            if sep and key and not key.startswith("#"):
                os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def _report(script, notes: list[str]) -> None:
    for w in script.warnings:
        print(f"warning: {script.path}: {w}", file=sys.stderr)
    for note in notes:
        print(f"note: {note}", file=sys.stderr)


def cmd_build(args: argparse.Namespace) -> int:
    script = parse_file(args.script)
    out = Path(args.output or Path(args.script).with_suffix(".mp4").name)
    log = (lambda msg: None) if args.quiet else (lambda msg: print(msg, file=sys.stderr))
    started = time.monotonic()
    synth = make_synth(args.tts, args.tts_model)
    log(f"speech: {synth.name}" + (f" ({synth.model})" if hasattr(synth, "model") else ""))
    builder = Builder(script, synth, log=log, jobs=args.jobs)
    result = builder.build(out, workdir=Path(args.keep_work) if args.keep_work else None)
    _report(script, result.notes)
    extras = ", ".join(str(p) for p in [result.poster, *result.subtitle_files])
    print(f"{result.video} ({result.duration:.1f}s video, built in {time.monotonic() - started:.1f}s); {extras}")
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    script = parse_file(args.script)
    settings_from_header(script.header, script.warnings)
    missing = [
        f"line {b.line}: file not found: {b.path}"
        for scene in script.scenes for b in scene.blocks
        if isinstance(b, Media) and not (script.base_dir / b.path).is_file()
    ]
    _report(script, [])
    for m in missing:
        print(f"error: {script.path}: {m}", file=sys.stderr)
    blocks = sum(len(s.blocks) for s in script.scenes)
    print(f"{script.path}: {len(script.scenes)} scenes, {blocks} blocks, "
          f"{len(script.warnings)} warnings, {len(missing)} missing files")
    return 1 if missing else 0


def cmd_voices(args: argparse.Namespace) -> int:
    print("Kokoro (--tts kokoro):", " ".join(KOKORO_VOICES))
    print("\nElevenLabs (--tts elevenlabs; a raw voice id also works):")
    for name, (voice_id, (lang, gender)) in ELEVENLABS_VOICES.items():
        print(f"  {name.title():10} {voice_id}  {lang} {gender}")
    print("\nNarakeet names map to a voice of the same language and gender:")
    print("  " + " ".join(sorted(NARAKEET_PROFILES)))
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    failed = 0
    for check in run_checks():
        mark = "ok  " if check.ok else "FAIL"
        print(f"{mark} {check.name}: {check.detail}")
        if not check.ok:
            failed += 1
            print(f"     fix: {check.fix}")
    print("all checks passed" if not failed else f"{failed} check(s) failed")
    return 1 if failed else 0


def cmd_models(args: argparse.Namespace) -> int:
    print(ensure_models())
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="narrate", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    build = sub.add_parser("build", help="render a script to MP4")
    build.add_argument("script")
    build.add_argument("-o", "--output", help="output .mp4 (default: <script name>.mp4 here)")
    build.add_argument("--tts", choices=["auto", "kokoro", "elevenlabs", "silent"], default="auto",
                       help="speech engine (default auto: ElevenLabs when ELEVENLABS_API_KEY is set, "
                            "else Kokoro); 'silent' renders timing-only silence for quick previews")
    build.add_argument("--tts-model", help="ElevenLabs model id (default eleven_multilingual_v2)")
    build.add_argument("--keep-work", metavar="DIR", help="keep intermediate files in DIR")
    build.add_argument("-j", "--jobs", type=int, help="parallel encodes (default: up to 4, or $NARRATE_JOBS)")
    build.add_argument("-q", "--quiet", action="store_true")
    build.set_defaults(func=cmd_build)

    check = sub.add_parser("check", help="parse a script and check its files, without rendering")
    check.add_argument("script")
    check.set_defaults(func=cmd_check)

    sub.add_parser("voices", help="list voices").set_defaults(func=cmd_voices)
    sub.add_parser("models", help="download the Kokoro model files").set_defaults(func=cmd_models)
    sub.add_parser("doctor", help="check ffmpeg, Chromium, fonts, models and keys").set_defaults(func=cmd_doctor)

    args = parser.parse_args(argv)
    load_dotenv(Path.cwd(), *([Path(args.script).resolve().parent] if getattr(args, "script", None) else []))
    try:
        return args.func(args)
    except (ScriptError, BuildError) as e:
        where = f":{e.line}" if getattr(e, "line", None) else ""
        print(f"error: {getattr(args, 'script', '')}{where}: {e}", file=sys.stderr)
        return 2
    except SetupError as e:
        print(f"setup problem: {e}", file=sys.stderr)
        return 3
    except (ConfigError, media.MediaError, RuntimeError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
