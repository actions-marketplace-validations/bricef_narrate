"""Running one of narrate's own commands in a child process and reading its progress.

The studio's builds and scene renders (studio/builds.py) and the service's
jobs (service/) run the CLI this way, rather than in-process. Playwright's
sync API can't run on an event loop, a separate process isolates Chromium and
ffmpeg, and it can be cancelled by stopping it (studio design D6).
"""

from __future__ import annotations

import asyncio
import os
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

PROGRESS = re.compile(r"^scene (\d+)/(\d+)$")
ERROR = re.compile(r"^error: .*?:(\d+): (.*)$")


@dataclass
class Outcome:
    """How a run ended: its exit code (None if it never started), the summary it printed, and the notes and
    errors it reported (errors with their script lines where it gave them)."""

    code: int | None
    summary: str = ""
    notes: list[str] = field(default_factory=list)
    errors: list[dict] = field(default_factory=list)
    cancelled: bool = False


class Child:
    """`python -m narrate ARGS` in `cwd`. `on_progress` hears {scene, of, message} as scenes are built, and
    {scene, of, message: "putting it together"} while the result is muxed."""

    def __init__(self, args: list[str], cwd: Path, on_progress: Callable[[dict], None] = lambda _: None,
                 env: dict[str, str] | None = None):
        self.args = args
        self.cwd = cwd
        self.on_progress = on_progress
        self.env = env
        self.process: asyncio.subprocess.Process | None = None
        self.cancelled = False

    async def run(self) -> Outcome:
        notes: list[str] = []
        errors: list[dict] = []
        tail: list[str] = []
        of = None
        try:
            self.process = await asyncio.create_subprocess_exec(
                sys.executable, "-m", "narrate", *self.args, cwd=self.cwd,
                env={**os.environ, **self.env} if self.env else None,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            if self.cancelled:  # cancelled while the process was starting
                self.process.terminate()
            async for raw in self.process.stderr:
                line = raw.decode(errors="replace").strip()
                if not line:
                    continue
                tail = (tail + [line])[-12:]
                if m := PROGRESS.match(line):
                    of = int(m.group(2))
                    self.on_progress({"scene": int(m.group(1)), "of": of, "message": line})
                elif line == "muxing":
                    self.on_progress({"scene": of, "of": of, "message": "putting it together"})
                elif line.startswith(("note: ", "warning: ")):
                    notes.append(line)
                elif m := ERROR.match(line):
                    errors.append({"line": int(m.group(1)), "message": m.group(2)})
                elif line.startswith(("error: ", "setup problem: ")):
                    errors.append({"line": None, "message": line.split(": ", 1)[1]})
            summary = (await self.process.stdout.read()).decode(errors="replace").strip()
            code = await self.process.wait()
        except Exception as e:  # noqa: BLE001 - reported like a failed run
            return Outcome(None, notes=notes, errors=[{"line": None, "message": f"couldn't run narrate: {e}"}])
        if code and not errors:
            errors = [{"line": None, "message": "\n".join(tail) or f"narrate stopped ({code})"}]
        return Outcome(code, summary.splitlines()[-1] if summary else "", notes, errors, self.cancelled)

    def cancel(self) -> None:
        # Recorded even before the process exists: run() stops it as soon as it does
        self.cancelled = True
        if self.process is not None and self.process.returncode is None:
            self.process.terminate()
