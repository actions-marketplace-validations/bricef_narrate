"""narrate: turn a Markdown script (Narakeet's format) into a narrated video."""

from __future__ import annotations

import argparse
import os
import sys
import time
from contextlib import contextmanager
from pathlib import Path

from . import media, project, render
from .build import Builder, BuildError
from .config import ConfigError, settings_from_header
from .doctor import SetupError, require_writable_cache, run_checks
from .voicemap import VoiceMapError
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


@contextmanager
def script_path(args: argparse.Namespace):
    """The script to build: the path given, or the one inside a project archive (.zip)."""
    path = Path(args.script)
    if path.suffix.lower() == ".zip":
        with project.unpacked(path, args.source) as script:
            yield script
    else:
        if args.source:
            raise project.ProjectError("--source applies to a project archive (.zip)")
        yield path


def cmd_build(args: argparse.Namespace) -> int:
    require_writable_cache()
    with script_path(args) as path:
        return _build(args, path)


SUBTITLE_CHOICES = ("none", "external", "embed", "overlay", "overlay-background", "tiktok")


def _output_options(parser: argparse.ArgumentParser) -> None:
    """What a build writes besides the video or audio, chosen per build (#58)."""
    parser.add_argument("--subtitles", choices=SUBTITLE_CHOICES, metavar="MODE",
                        help="subtitles for this build, over the script's own: " + ", ".join(SUBTITLE_CHOICES)
                        + " (every mode but none also writes .srt and .vtt)")
    parser.add_argument("--transcript", action="store_true",
                        help="also write what's spoken as plain text, <output>.transcript.txt")
    _usage_option(parser)


def _usage_option(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--usage", metavar="FILE",
                        help="write what this run spent to FILE, as JSON: speech characters and credits by model, "
                             "what the cache saved, renders drawn, CPU time")


def _write_usage(path: str | None, started: float, synth=None, **more) -> None:
    """What a run spent (#81), for cost reports: the speech engine's usage, what else it did, and its time,
    CPU time included (its own and its finished child processes': ffmpeg, Chromium)."""
    if not path:
        return
    import json
    import resource

    own, children = resource.getrusage(resource.RUSAGE_SELF), resource.getrusage(resource.RUSAGE_CHILDREN)
    usage = {"speech": synth.usage.report() if hasattr(synth, "usage") else None, **more,
             "wall_seconds": round(time.monotonic() - started, 3),
             "cpu_seconds": round(own.ru_utime + own.ru_stime + children.ru_utime + children.ru_stime, 3)}
    Path(path).write_text(json.dumps(usage, indent=2) + "\n")


def parse_scenes(spec: str) -> list[int]:
    """Scene numbers from "3", "3-5" or "2,4" (and mixes such as "1-2,5"), in order."""
    scenes: list[int] = []
    for part in spec.replace(" ", "").split(","):
        first, dash, last = part.partition("-")
        if not first.isdigit() or (dash and not last.isdigit()) or int(first) < 1:
            raise argparse.ArgumentTypeError(f"scenes are numbers such as 3, 3-5 or 2,4, not {spec!r}")
        a, b = int(first), int(last) if dash else int(first)
        if b < a:
            raise argparse.ArgumentTypeError(f"{part} counts down: write {b}-{a}")
        scenes += [n for n in range(a, b + 1) if n not in scenes]
    return scenes


def scenes_name(scenes: list[int]) -> str:
    """How an excerpt's file is named: scene-3, scenes-3-5, scenes-2_4."""
    ordered = sorted(scenes)
    if len(ordered) == 1:
        return f"scene-{ordered[0]}"
    if ordered == list(range(ordered[0], ordered[-1] + 1)):
        return f"scenes-{ordered[0]}-{ordered[-1]}"
    return "scenes-" + "_".join(map(str, ordered))


def _build(args: argparse.Namespace, path: Path) -> int:
    script = parse_file(path)
    default = path.with_suffix(".mp4").name
    if args.scenes:  # never over the whole video
        default = f"{path.stem}-{scenes_name(args.scenes)}.mp4"
    out = Path(args.output or default)
    log = (lambda msg: None) if args.quiet else (lambda msg: print(msg, file=sys.stderr))
    started = time.monotonic()
    synth = make_synth(args.tts, args.tts_model)
    log(f"speech: {synth.name}" + (f" ({synth.model})" if hasattr(synth, "model") else ""))
    builder = Builder(script, synth, log=log, jobs=args.jobs, regenerate=args.regenerate, scenes=args.scenes,
                      subtitles=args.subtitles, transcript=args.transcript)
    result = builder.build(out, workdir=Path(args.keep_work) if args.keep_work else None)
    _report(script, result.notes)
    _write_usage(args.usage, started, synth, rendered=builder.rendered, video_seconds=round(result.duration, 3))
    extras = ", ".join(str(p) for p in [result.poster, *result.subtitle_files, result.transcript] if p)
    print(f"{result.video} ({result.duration:.1f}s video, built in {time.monotonic() - started:.1f}s); {extras}")
    return 0


def cmd_audio(args: argparse.Namespace) -> int:
    require_writable_cache()
    with script_path(args) as path:
        script = parse_file(path)
        out = Path(args.output or path.with_suffix(".mp3").name)
        log = (lambda msg: None) if args.quiet else (lambda msg: print(msg, file=sys.stderr))
        started = time.monotonic()
        synth = make_synth(args.tts, args.tts_model)
        result = Builder(script, synth, log=log, jobs=args.jobs, subtitles=args.subtitles,
                         transcript=args.transcript).build_audio(out)
        _report(script, result.notes)
        _write_usage(args.usage, started, synth, audio_seconds=round(result.duration, 3))
        extras = "".join(f", {p}" for p in [*result.subtitle_files, result.transcript] if p)
        print(f"{result.video} ({result.duration:.1f}s audio, built in {time.monotonic() - started:.1f}s){extras}")
    return 0


def cmd_callouts(args: argparse.Namespace) -> int:
    from .config import parse_size
    from .designer import designer_page

    source = Path(args.file)
    if not source.is_file():
        print(f"error: {source} not found", file=sys.stderr)
        return 2
    width, height = parse_size(args.size)
    out = Path(args.output or f"{source.stem}-callouts.html")
    designer_page(source, out, width=width, height=height, fit=args.fit, position=args.position, at=args.at)
    print(out.resolve().as_uri())
    if args.open:
        import webbrowser

        webbrowser.open(out.resolve().as_uri())
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    with script_path(args) as path:
        if args.timing or args.json:
            return _check_timing(path, args.tts, args.tts_model, args.json)
        return _check(path)


ENGINE_NAMES = {"kokoro": "Kokoro", "elevenlabs": "ElevenLabs", "silent": "silent"}


def timing(path: Path, engine: str = "auto", model: str | None = None) -> dict:
    """The script's timing and what synthesis would still cost with `engine`, its problems included,
    as the studio analyses it (#66): speech already cached is exact, the rest estimated from the text,
    and nothing is synthesised."""
    from .studio.analysis import analyse

    synth = make_synth(engine, model, planning=True)  # ElevenLabs is priced without a key (#71)
    text = path.read_bytes().decode("utf-8-sig").replace("\r\n", "\n")
    report = {**analyse(text, path, synth), "engine": synth.name}
    if synth.name == "elevenlabs" and not getattr(synth, "key", None):
        report["notes"] = [*report.get("notes", []), "no ELEVENLABS_API_KEY: timed and priced from the cache and "
                           "estimates; building with ElevenLabs needs the key"]
    return report


def _clock(seconds: float) -> str:
    return f"{int(seconds // 60)}:{seconds % 60:04.1f}"


def _check_timing(path: Path, engine: str, model: str | None, as_json: bool) -> int:
    import json

    report = timing(path, engine, model)
    errors = [p for p in report["problems"] if p["severity"] == "error"]
    if as_json:
        print(json.dumps(report, indent=2))
        return 1 if errors else 0
    for p in report["problems"]:
        print(f"{p['severity']}: {path}: line {p['line']}: {p['message']}", file=sys.stderr)
    for note in report.get("notes", []):
        print(f"note: {note}", file=sys.stderr)
    name = ENGINE_NAMES.get(report["engine"], report["engine"])
    scenes = report["scenes"]
    total = report["duration"]
    print(f"{path}: {len(scenes)} scenes, " + (f"{total:.1f}s with {name}" if total is not None else "can't be timed"))
    estimated = False
    for scene in scenes:
        if scene["duration"] is None:
            print(f"  {scene['index']:>3}  {'':>7}       ?   {scene['title']} (can't be timed: see the errors)")
            continue
        mark = "≈" if any(p["estimated"] for p in scene["paragraphs"]) else " "
        estimated = estimated or mark == "≈"
        print(f"  {scene['index']:>3}  {_clock(scene['start']):>7}  {mark}{scene['duration']:5.1f}s  {scene['title']}")
    missing = report["missing"]
    if missing:
        cost = "free" if report["engine"] in ("kokoro", "silent") else "spends ElevenLabs credits"
        print(f"to synthesise: {missing['paragraphs']} paragraphs, {missing['characters']} characters ({name}: {cost})"
              if missing["paragraphs"] else "to synthesise: nothing, all speech is cached")
    if estimated:
        print("≈ estimated from the text: exact once the speech is synthesised (a build, or the studio)")
    return 1 if errors else 0


def _check(path: Path) -> int:
    from .config import parse_overlay
    from .script import Directive

    script = parse_file(path)
    settings = settings_from_header(script.header, script.warnings)
    media_blocks = [b for scene in script.scenes for b in scene.blocks if isinstance(b, Media)]
    missing = [f"line {b.line}: file not found: {b.path}"
               for b in media_blocks if not b.render and not (script.base_dir / b.path).is_file()]
    # Overlay pages (#59): the header's, and each scene's
    overlays = [(1, spec) for spec in settings.overlays]
    for b in (b for scene in script.scenes for b in scene.blocks):
        if isinstance(b, Directive) and b.key == "overlay":
            try:
                spec = parse_overlay(b.value)
            except ConfigError as e:
                missing.append(f"line {b.line}: {e}")
                continue
            if spec is not None:
                overlays.append((b.line, spec))
    missing += [f"line {line}: file not found: {spec.file}" for line, spec in overlays
                if not (script.base_dir / spec.file).is_file()]
    rendered = [b for b in media_blocks if b.render]
    problems = [f"line {b.line}: {p}" for b, found in zip(rendered, render.check(rendered)) for p in found]
    _report(script, [])
    for m in missing + problems:
        print(f"error: {script.path}: {m}", file=sys.stderr)
    blocks = sum(len(s.blocks) for s in script.scenes)
    print(f"{script.path}: {len(script.scenes)} scenes, {blocks} blocks, "
          f"{len(script.warnings)} warnings, {len(missing)} missing files"
          + (f", {len(problems)} render block problems" if problems else ""))
    return 1 if missing or problems else 0


def cmd_frames(args: argparse.Namespace) -> int:
    from . import review

    started = time.monotonic()
    video = Path(args.video)
    if not video.is_file():
        print(f"error: {video} not found", file=sys.stderr)
        return 2
    duration = media.probe(video).duration
    if args.script:
        # One frame in the middle of each scene, timed as `check --timing` times it
        report = timing(Path(args.script), args.tts, args.tts_model)
        moments = [(s["start"] + s["duration"] / 2, f"scene {s['index']} · {s['title']}")
                   for s in report["scenes"] if s["duration"]]
        if report["duration"] and abs(report["duration"] - duration) > 0.5:
            print(f"note: the script times to {report['duration']:.1f}s but the video is {duration:.1f}s: "
                  f"time it with the engine the video was built with (--tts)", file=sys.stderr)
    elif args.at:
        moments = [(float(t), "") for t in args.at.split(",") if t.strip()]
    elif args.every:
        moments = [(t, "") for t in review.every(duration, args.every)]
    else:
        moments = [(t, "") for t in review.evenly(duration, args.count)]
    if not moments:
        print("error: no moments to show", file=sys.stderr)
        return 2
    out = Path(args.output or video.with_name(f"{video.stem}-frames.png"))
    review.contact_sheet(video, moments, out, args.width)
    for at, label in moments:
        print(f"{review.clock(at):>7}  {label}".rstrip())
    print(out)
    _write_usage(args.usage, started)
    return 0


def cmd_hear(args: argparse.Namespace) -> int:
    import json

    from . import review

    from . import stt

    started = time.monotonic()
    source = Path(args.media)
    if not source.is_file():
        print(f"error: {source} not found", file=sys.stderr)
        return 2

    def spent() -> None:
        if args.usage:
            _write_usage(args.usage, started, speech_to_text={"model": stt.model_name(),
                                                              "seconds": round(media.probe(source).duration, 3)})
    language = args.language
    if args.script and not language:  # the script's own narration language, if it sets one
        lang = parse_file(Path(args.script)).header.get("narration-language")
        language = str(lang).split("-")[0].lower() if lang else None
    try:
        heard = review.heard_words(source, language)
    except ImportError:
        print("error: narrate hear needs faster-whisper (narrate's speech-to-text); see narrate doctor", file=sys.stderr)
        return 2
    if not args.script:  # just what's heard, with when
        for phrase in stt.transcribe(source, language):
            print(f"{review.clock(phrase[0][0]):>7}  {' '.join(w for _, _, w in phrase)}")
        spent()
        return 0
    report = review.compare(review.written_words(Path(args.script)), heard)
    spent()
    if args.json:
        print(json.dumps(report, indent=2))
        return 0
    words, good = report["words"], report["heard_as_written"]
    print(f"{args.script}: {good} of {words} words heard as written ({round(100 * good / words) if words else 100}%)")
    for d in report["differences"]:
        at = f"{review.clock(d['at']):>7}" if d["at"] is not None else " " * 7
        where = f"scene {d['scene']}, line {d['line']}: " if d["line"] else ""
        if d["kind"] == "different":
            print(f"  {at}  {where}wrote \"{d['wrote']}\", heard \"{d['heard']}\"")
        elif d["kind"] == "not heard":
            print(f"  {at}  {where}wrote \"{d['wrote']}\", not heard")
        else:
            print(f"  {at}  heard \"{d['heard']}\", not in the script (a recording, or noise)")
    if not report["differences"]:
        print("  no differences")
    else:
        print("speech-to-text makes mistakes of its own: a difference is worth a listen, not proof")
    return 0


def cmd_studio(args: argparse.Namespace) -> int:
    from .studio.server import serve

    script = Path(args.script)
    if script.suffix.lower() not in (".md", ".mkd", ".txt"):
        print(f"error: {script} isn't a script (.md, .mkd or .txt)", file=sys.stderr)
        return 2
    if not script.parent.resolve().is_dir():
        print(f"error: no folder {script.parent}", file=sys.stderr)
        return 2
    serve(script, args.host, args.port, args.open, args.tts)
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    from .service.costs import Prices, PricesError
    from .service.server import serve
    from .service.store import default_root

    try:
        prices = Prices.load(Path(args.prices)) if args.prices else None
    except PricesError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    serve(Path(args.data) if args.data else default_root(), args.host, args.port, args.tts, args.workers, prices)
    return 0


def cmd_voices(args: argparse.Namespace) -> int:
    print("Kokoro (--tts kokoro):", " ".join(KOKORO_VOICES))
    print("\nElevenLabs (--tts elevenlabs; a raw voice id also works):")
    for name, (voice_id, (lang, gender)) in ELEVENLABS_VOICES.items():
        print(f"  {name.title():10} {voice_id}  {lang} {gender}")
    print("\nNarakeet names map to a voice of the same language and gender:")
    print("  " + " ".join(sorted(NARAKEET_PROFILES)))
    from . import voicemap

    mapping = voicemap.load(Path(args.script).resolve().parent if args.script else None)
    print(f"\nPinned in voices.yaml ({voicemap.user_file()}"
          + (f" and next to {args.script}" if args.script else "") + "):")
    if not mapping:
        print("  (none)")
    for name, engines in sorted(mapping.items()):
        print(f"  {name:12} " + ", ".join(f"{engine}: {voice}" for engine, voice in engines.items()))
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


def cmd_cache(args: argparse.Namespace) -> int:
    from . import cache
    from .tts import cache_dir

    found = cache.entries()
    if args.prune:
        if args.max_size is None and args.older_than is None:
            print("error: --prune needs --max-size and/or --older-than", file=sys.stderr)
            return 2
        removed = cache.prune(
            found,
            max_size=cache.parse_size(args.max_size) if args.max_size else None,
            older_than=args.older_than * 86400 if args.older_than is not None else None,
            protect=args.keep_recent * 60,
        )
        print(f"removed {len(removed)} entries ({cache.human(sum(e.size for e in removed))})")
        found = cache.entries()
    print(f"cache: {cache_dir()} (speech in tts/, render blocks in render/)")
    for engine, (count, size) in sorted(cache.summary(found).items()):
        print(f"  {engine:18} {count:6} entries  {cache.human(size):>9}")
    print(f"  {'total':18} {len(found):6} entries  {cache.human(sum(e.size for e in found)):>9}")
    return 0


def cmd_models(args: argparse.Namespace) -> int:
    print(ensure_models())
    if not os.environ.get("NARRATE_FFMPEG"):  # the container image brings its own
        print(media.ensure_ffmpeg())
    from . import mermaid, stt

    print(stt.ensure_model())
    print(mermaid.ensure())
    return 0


def parser() -> argparse.ArgumentParser:
    """Every command, its arguments, and the function that runs it."""
    parser = argparse.ArgumentParser(
        prog="narrate", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="examples:\n"
               "  narrate build script.md                 render script.mp4 and its poster\n"
               "  narrate build script.md --tts silent    a quick preview, without speech\n"
               "  narrate check script.md                 find missing files and problems\n"
               "  narrate COMMAND --help                  a command's options\n\n"
               "guides: docs/writing-scripts.md and docs/building.md")
    sub = parser.add_subparsers(dest="command", required=True)

    build = sub.add_parser("build", help="render a script (or a .zip project) to MP4")
    build.add_argument("script", help="a .md/.txt script, or a .zip of the script and its assets")
    build.add_argument("--source", help="the script's path inside a .zip project (found if there is only one)")
    build.add_argument("-o", "--output", help="output .mp4 (default: <script name>.mp4 here)")
    build.add_argument("--tts", choices=["auto", "kokoro", "elevenlabs", "silent"], default="auto",
                       help="speech engine (default auto: ElevenLabs when ELEVENLABS_API_KEY is set, "
                            "else Kokoro); 'silent' renders timing-only silence for quick previews")
    build.add_argument("--tts-model", help="ElevenLabs model id (default eleven_multilingual_v2)")
    build.add_argument("--scenes", type=parse_scenes, metavar="N",
                       help="build only these scenes, as in 3, 3-5 or 2,4 (default output: <script>-scene-3.mp4)")
    _output_options(build)
    build.add_argument("--keep-work", metavar="DIR", help="keep intermediate files in DIR")
    build.add_argument("--regenerate", action="store_true",
                       help="take web captures (render:web) again instead of reusing the stored ones")
    build.add_argument("-j", "--jobs", type=int, help="parallel encodes (default: up to 4, or $NARRATE_JOBS)")
    build.add_argument("-q", "--quiet", action="store_true", help="print only warnings and errors")
    build.set_defaults(func=cmd_build)

    audio = sub.add_parser("audio", help="render only the narration, as an audio file")
    audio.add_argument("script", help="a .md/.txt script, or a .zip project")
    audio.add_argument("--source", help="the script's path inside a .zip project")
    audio.add_argument("-o", "--output", help="output file: .mp3 (default), .m4a, .ogg, .opus, .flac or .wav")
    audio.add_argument("--tts", choices=["auto", "kokoro", "elevenlabs", "silent"], default="auto",
                       help="speech engine (default auto: ElevenLabs when ELEVENLABS_API_KEY is set, else Kokoro)")
    audio.add_argument("--tts-model", help="ElevenLabs model id (default eleven_multilingual_v2)")
    _output_options(audio)
    audio.add_argument("-j", "--jobs", type=int, help="parallel work (default: up to 4, or $NARRATE_JOBS)")
    audio.add_argument("-q", "--quiet", action="store_true", help="print only warnings and errors")
    audio.set_defaults(func=cmd_audio)

    callouts = sub.add_parser("callouts", help="write a page for placing callouts on an image or video frame")
    callouts.add_argument("file", help="the image or video the callout goes on")
    callouts.add_argument("--size", default="720p", help="the script's video size (default 720p)")
    callouts.add_argument("--fit", choices=["cover", "contain", "fit"], default="cover",
                          help="how the script fits the image to the frame (default cover)")
    callouts.add_argument("--position", default="center", choices=["center", "top-left", "left", "right", "top", "bottom"],
                          help="which part a cover crop keeps (default center)")
    callouts.add_argument("--at", type=float, default=0.0, help="for a video: the moment to show, in seconds")
    callouts.add_argument("-o", "--output", help="the page to write (default: <file>-callouts.html here)")
    callouts.add_argument("--open", action="store_true", help="open the page in a browser")
    callouts.set_defaults(func=cmd_callouts)

    studio = sub.add_parser("studio", help="edit and preview a script in your browser")
    studio.add_argument("script", help="the .md script to edit (created on first save if it doesn't exist)")
    studio.add_argument("--host", default="127.0.0.1",
                        help="address to listen on (default 127.0.0.1; 0.0.0.0 for other machines, "
                             "with no access control)")
    studio.add_argument("--port", type=int, default=8787, help="port to listen on (default 8787)")
    studio.add_argument("--open", action="store_true", help="open the studio in a browser")
    studio.add_argument("--tts", choices=["auto", "kokoro", "elevenlabs", "silent"], default="kokoro",
                        help="speech engine for previews and builds (default kokoro, which is free)")
    studio.set_defaults(func=cmd_studio)

    serve = sub.add_parser("serve", help="serve narrate's capabilities over HTTP, for your own programs")
    serve.add_argument("--host", default="127.0.0.1",
                       help="address to listen on (default 127.0.0.1; 0.0.0.0 for other machines, "
                            "with no access control)")
    serve.add_argument("--port", type=int, default=8788, help="port to listen on (default 8788)")
    serve.add_argument("--data", metavar="DIR",
                       help="where to keep uploaded files, jobs and their records "
                            "(default $XDG_DATA_HOME/narrate/service, else ~/.local/share/narrate/service)")
    serve.add_argument("--workers", type=int, default=1, help="how many jobs run at once (default 1)")
    serve.add_argument("--tts", choices=["auto", "kokoro", "elevenlabs", "silent"], default="kokoro",
                       help="speech engine for jobs that don't name one (default kokoro, which is free)")
    serve.add_argument("--prices", metavar="FILE",
                       help="what speech and CPU time cost, to price each job: a YAML file with currency, "
                            "elevenlabs_per_1000_credits and cpu_per_hour")
    serve.set_defaults(func=cmd_serve)

    frames = sub.add_parser("frames", help="a contact sheet of a video's frames, to review it without watching it")
    frames.add_argument("video", help="a built video")
    frames.add_argument("-o", "--output", help="the sheet to write (default: <video>-frames.png beside it)")
    frames.add_argument("--script", help="one frame in the middle of each of this script's scenes, labelled")
    frames.add_argument("--tts", choices=["auto", "kokoro", "elevenlabs", "silent"], default="auto",
                        help="with --script: the engine the video was built with, to time its scenes")
    frames.add_argument("--tts-model", help="with --script: the ElevenLabs model it was built with")
    frames.add_argument("--at", help="frames at these seconds, as in 1.5,12,30")
    frames.add_argument("--every", type=float, metavar="SECONDS", help="a frame every SECONDS")
    frames.add_argument("--count", type=int, default=12, help="frames spread evenly across the video (default 12)")
    frames.add_argument("--width", type=int, default=480, help="each frame's width in pixels (default 480)")
    _usage_option(frames)
    frames.set_defaults(func=cmd_frames)

    hear = sub.add_parser("hear", help="what speech-to-text hears in a video, and where it differs from the script")
    hear.add_argument("media", help="a built video or audio file")
    hear.add_argument("--script", help="the script it was built from: report where the narration sounds different")
    hear.add_argument("--language", help="the narration's language, as in en or fr (default: the script's, else detected)")
    hear.add_argument("--json", action="store_true", help="the comparison as JSON, for programs")
    _usage_option(hear)
    hear.set_defaults(func=cmd_hear)

    check = sub.add_parser("check", help="parse a script and check its files, without rendering")
    check.add_argument("script", help="a .md/.txt script, or a .zip project")
    check.add_argument("--source", help="the script's path inside a .zip project")
    check.add_argument("--timing", action="store_true",
                       help="also plan it: each scene's length, the total, what synthesis would cost, and bad values")
    check.add_argument("--json", action="store_true", help="the --timing report as JSON, for programs")
    check.add_argument("--tts", choices=["auto", "kokoro", "elevenlabs", "silent"], default="auto",
                       help="the engine to time and price with (default auto, as for build)")
    check.add_argument("--tts-model", help="ElevenLabs model id (default eleven_multilingual_v2)")
    check.set_defaults(func=cmd_check)

    voices = sub.add_parser("voices", help="list voices, and any voices.yaml pins")
    voices.add_argument("script", nargs="?", help="also show the voices.yaml next to this script")
    voices.set_defaults(func=cmd_voices)
    sub.add_parser("models", help="download the Kokoro, speech-to-text, ffmpeg and mermaid.js files now, "
                   "instead of on first use").set_defaults(func=cmd_models)
    sub.add_parser("doctor", help="check ffmpeg, Chromium, fonts, models and keys").set_defaults(func=cmd_doctor)

    cache_cmd = sub.add_parser("cache", help="show the speech and render caches, or prune them")
    cache_cmd.add_argument("--prune", action="store_true", help="delete least-recently-used entries")
    cache_cmd.add_argument("--max-size", metavar="SIZE", help="prune down to SIZE, e.g. 500M or 2G")
    cache_cmd.add_argument("--older-than", type=float, metavar="DAYS", help="prune entries unused for DAYS")
    cache_cmd.add_argument("--keep-recent", type=float, default=60, metavar="MINUTES",
                           help="never prune entries used in the last MINUTES (default 60; protects running builds)")
    cache_cmd.set_defaults(func=cmd_cache)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    load_dotenv(Path.cwd(), *([Path(args.script).resolve().parent] if getattr(args, "script", None) else []))
    try:
        return args.func(args)
    except project.ProjectError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    except (ScriptError, BuildError) as e:
        where = f":{e.line}" if getattr(e, "line", None) else ""
        print(f"error: {getattr(args, 'script', '')}{where}: {e}", file=sys.stderr)
        return 2
    except SetupError as e:
        print(f"setup problem: {e}", file=sys.stderr)
        return 3
    except (ConfigError, media.MediaError, RuntimeError, VoiceMapError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
