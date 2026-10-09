"""Builds from the studio (#55): `narrate build` in a child process, reported as it goes.

A build runs as its own process (design D6): Playwright and ffmpeg stay out
of the server, a build can be cancelled by stopping the process, and its log
lines say how far it has got. Progress, notes and errors go over the
session's event stream, and the last result is kept for a reloaded page.
"""

from __future__ import annotations

import asyncio
import re
import sys
from pathlib import Path
from urllib.parse import quote

PROGRESS = re.compile(r"^scene (\d+)/(\d+)$")
ERROR = re.compile(r"^error: .*?:(\d+): (.*)$")


class BuildRun:
    """One build of the session's script, with the session's speech engine."""

    def __init__(self, session):
        self.session = session
        self.process: asyncio.subprocess.Process | None = None
        self.cancelled = False
        self.status: dict = {"state": "starting"}

    @property
    def running(self) -> bool:
        return self.status["state"] in ("starting", "running")

    def update(self, **status) -> None:
        self.status = status
        self.session.publish({"type": "build", **status})

    async def run(self) -> None:
        script = self.session.script
        out = script.with_suffix(".mp4")
        command = [sys.executable, "-m", "narrate", "build", str(script), "--tts", self.session.engine, "-o", str(out)]
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
            version = out.stat().st_mtime_ns  # so the player doesn't show a cached older video
            name = quote(out.name)
            self.update(state="done", video=f"/files/{name}?v={version}",
                        poster=f"/files/{quote(out.with_suffix('.jpg').name)}?v={version}",
                        summary=summary.splitlines()[-1] if summary else "", notes=notes)
        else:
            self.update(state="failed", notes=notes,
                        errors=errors or [{"line": None, "message": "\n".join(tail) or f"the build stopped ({code})"}])

    def cancel(self) -> None:
        # Recorded even before the process exists: run() stops it as soon as it does
        self.cancelled = True
        if self.process is not None and self.process.returncode is None:
            self.process.terminate()
