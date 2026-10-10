"""Builds from the studio (#55): `narrate build` in a child process, reported as it goes.

A build runs as its own process (design D6): Playwright and ffmpeg stay out
of the server, a build can be cancelled by stopping the process, and its log
lines say how far it has got. Progress, notes and errors go over the
session's event stream, and the last result is kept for a reloaded page.

A scene render (#61) is the same with `--scenes N`, written to the session's
scratch folder rather than next to the script.
"""

from __future__ import annotations

import asyncio
import hashlib
import re
import sys
from pathlib import Path
from urllib.parse import quote

from ..script import Media, ScriptError, parse

PROGRESS = re.compile(r"^scene (\d+)/(\d+)$")
ERROR = re.compile(r"^error: .*?:(\d+): (.*)$")


def fingerprint(script: Path, text: str, engine: str, scene: int) -> str:
    """Names a scene render of `text`: changes with the text, the engine, and the files it uses."""
    digest = hashlib.sha256(f"{engine}\0{scene}\0{text}".encode())
    try:
        parsed = parse(text, script)
    except ScriptError:
        parsed = None
    names = [b.path for sc in (parsed.scenes if parsed else []) for b in sc.blocks if isinstance(b, Media) and b.path]
    if parsed and isinstance(parsed.header.get("background"), str):
        names.append(parsed.header["background"].split()[0])
    for name in sorted(set(names)):
        path = script.parent / name
        if path.is_file():
            stat = path.stat()
            digest.update(f"\0{name}:{stat.st_mtime_ns}:{stat.st_size}".encode())
    return digest.hexdigest()[:16]


class BuildRun:
    """One build of the session's script, with the session's speech engine.

    By default the whole video, next to the script; with `out` and `args`, for
    example a scene render into scratch. `event` names its events on the stream,
    and `label` adds fields to every status (which scene, say)."""

    def __init__(self, session, out: Path | None = None, args: list[str] | None = None, event: str = "build",
                 label: dict | None = None):
        self.session = session
        self.out = out or session.script.with_suffix(".mp4")
        self.args = args or []
        self.event = event
        self.label = label or {}
        self.process: asyncio.subprocess.Process | None = None
        self.cancelled = False
        self.status: dict = {**self.label, "state": "starting"}

    @property
    def running(self) -> bool:
        return self.status["state"] in ("starting", "running")

    def update(self, **status) -> None:
        self.status = {**self.label, **status}
        self.session.publish({"type": self.event, **self.status})

    def url(self, path: Path) -> str:
        """Where the page loads a result from: the project's files, or the session's scratch folder."""
        version = path.stat().st_mtime_ns if path.exists() else 0  # so the player doesn't show an older one
        if path.is_relative_to(self.session.scratch):
            return f"/scratch/{quote(path.name)}?v={version}"
        return f"/files/{quote(path.relative_to(self.session.project).as_posix())}?v={version}"

    def done(self, summary: str = "", notes: list[str] | None = None) -> None:
        self.update(state="done", video=self.url(self.out), poster=self.url(self.out.with_suffix(".jpg")),
                    summary=summary, notes=notes or [])

    async def run(self) -> None:
        script = self.session.script
        out = self.out
        command = [sys.executable, "-m", "narrate", "build", str(script), "--tts", self.session.engine,
                   "-o", str(out), *self.args]
        notes: list[str] = []
        errors: list[dict] = []
        tail: list[str] = []
        try:
            self.process = await asyncio.create_subprocess_exec(
                *command, cwd=script.parent, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            if self.cancelled:  # cancelled while the process was starting
                self.process.terminate()
            else:
                self.update(state="running", scene=0, of=None, message="starting")
            async for raw in self.process.stderr:
                line = raw.decode(errors="replace").strip()
                if not line:
                    continue
                tail = (tail + [line])[-12:]
                if m := PROGRESS.match(line):
                    self.update(state="running", scene=int(m.group(1)), of=int(m.group(2)), message=line)
                elif line == "muxing":
                    self.update(state="running", scene=self.status.get("of"), of=self.status.get("of"),
                                message="putting it together")
                elif line.startswith(("note: ", "warning: ")):
                    notes.append(line)
                elif m := ERROR.match(line):
                    errors.append({"line": int(m.group(1)), "message": m.group(2)})
                elif line.startswith(("error: ", "setup problem: ")):
                    errors.append({"line": None, "message": line.split(": ", 1)[1]})
            summary = (await self.process.stdout.read()).decode(errors="replace").strip()
            code = await self.process.wait()
        except Exception as e:  # noqa: BLE001 - reported like a failed build
            self.update(state="failed", errors=[{"line": None, "message": f"couldn't run the build: {e}"}], notes=notes)
            return
        if self.cancelled:
            self.update(state="cancelled", notes=notes)
        elif code == 0 and out.exists():
            self.done(summary.splitlines()[-1] if summary else "", notes)
        else:
            self.update(state="failed", notes=notes,
                        errors=errors or [{"line": None, "message": "\n".join(tail) or f"the build stopped ({code})"}])

    def cancel(self) -> None:
        # Recorded even before the process exists: run() stops it as soon as it does
        self.cancelled = True
        if self.process is not None and self.process.returncode is None:
            self.process.terminate()
