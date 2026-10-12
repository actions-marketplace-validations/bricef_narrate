"""Running the service's jobs (#79): the CLI in a child process per job, a few at a time.

A job is laid out in its folder (projects.lay_out), run as `narrate build` or
`narrate audio` (child.Child, as the studio's builds are), and its outputs
collected: the video or audio, poster, subtitle files, transcript, and any web
captures taken. Every change is saved to the job's record and announced to
whoever follows its events.
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

from ..child import Child
from . import options as job_options
from .projects import ProjectError, lay_out
from .projects import parse as parse_project
from .store import FINAL, Store

# An output's name, by what its file ends in
_OUTPUTS = ((".transcript.txt", "transcript"), (".mp4", "video"), (".jpg", "poster"), (".srt", "srt"), (".vtt", "vtt"),
            *((f".{fmt}", "audio") for fmt in job_options.AUDIO_FORMATS))
GENERATED = ".narrate/generated"


def _when(seconds: float | None) -> str | None:
    return datetime.fromtimestamp(seconds, timezone.utc).isoformat(timespec="seconds") if seconds else None


def view(job: dict) -> dict:
    """A job as the API shows it."""
    return {**job, "created": _when(job["created"]), "started": _when(job["started"]),
            "finished": _when(job["finished"])}


class Runner:
    """Runs jobs `workers` at a time, with `engine` unless a job asks for another."""

    def __init__(self, store: Store, engine: str = "kokoro", workers: int = 1):
        self.store = store
        self.engine = engine
        self.workers = max(1, workers)
        self.queue: asyncio.Queue[str] = asyncio.Queue()
        self.children: dict[str, Child] = {}
        self.listeners: dict[str, set[asyncio.Queue]] = {}
        self.tasks: list[asyncio.Task] = []

    # -- the service's life ---------------------------------------------------------------------

    async def start(self) -> None:
        self.store.interrupt()  # left running by a service that stopped
        for job_id in self.store.waiting():
            self.queue.put_nowait(job_id)
        self.tasks = [asyncio.create_task(self._work()) for _ in range(self.workers)]

    async def stop(self) -> None:
        for child in self.children.values():
            if child.process is not None and child.process.returncode is None:
                child.process.terminate()
        for task in self.tasks:
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)
        self.store.interrupt()
        self.end_streams()

    def end_streams(self) -> None:
        for queues in self.listeners.values():
            for q in queues:
                q.put_nowait(None)

    # -- jobs -----------------------------------------------------------------------------------

    def submit(self, kind: str, project: dict, options: dict) -> dict:
        """A new job, queued. Raises OptionError or ProjectError (with what to upload) if it can't run."""
        checked = job_options.check(kind, options)
        parsed = parse_project(project)
        missing = self.store.missing(parsed.hashes())
        if missing:
            raise ProjectError(f"upload these files first: {', '.join(missing)}", missing)
        job = self.store.new_job(kind, {"project": project, "options": checked})
        self.queue.put_nowait(job["id"])
        return job

    def cancel(self, job_id: str) -> dict | None:
        job = self.store.job(job_id)
        if job is None or job["state"] in FINAL:
            return job
        if job["state"] == "queued":
            self._set(job_id, state="cancelled", finished=time.time())
        elif job_id in self.children:
            self.children[job_id].cancel()
        return self.store.job(job_id)

    def listen(self, job_id: str) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self.listeners.setdefault(job_id, set()).add(q)
        return q

    def unlisten(self, job_id: str, q: asyncio.Queue) -> None:
        self.listeners.get(job_id, set()).discard(q)

    def _set(self, job_id: str, **fields) -> None:
        self.store.update(job_id, **fields)
        job = self.store.job(job_id)
        for q in self.listeners.get(job_id, ()):
            q.put_nowait(view(job))

    async def _work(self) -> None:
        while True:
            job_id = await self.queue.get()
            job = self.store.job(job_id)
            if job is not None and job["state"] == "queued":
                await self._run(job)

    async def _run(self, job: dict) -> None:
        job_id, kind = job["id"], job["kind"]
        options = dict(job["request"]["options"])
        folder = self.store.folder(job_id)
        self._set(job_id, state="running", started=time.time(),
                  progress={"scene": 0, "of": None, "message": "starting"})
        try:
            project = parse_project(job["request"]["project"])
            target = lay_out(project, self.store, folder / "project")
        except ProjectError as e:
            self._set(job_id, state="failed", finished=time.time(), errors=[{"line": None, "message": str(e)}])
            return
        out = folder / "out"
        out.mkdir(parents=True, exist_ok=True)
        output = out / f"{target.stem}.{'mp4' if kind == 'build' else options.pop('format', 'mp3')}"
        args = [kind, str(target), "-o", str(output), "--tts", options.pop("tts", self.engine),
                *job_options.arguments(kind, options)]
        captures = folder / "project" / GENERATED
        before = _versions(captures)
        child = Child(args, cwd=folder / "project", on_progress=lambda p: self._set(job_id, progress=p))
        self.children[job_id] = child
        try:
            outcome = await child.run()
        finally:
            self.children.pop(job_id, None)
        outputs = self._outputs(job_id, out, captures, before)
        if outcome.cancelled:
            state = "cancelled"
        elif outcome.code == 0 and output.exists():
            state = "done"
        else:
            state = "failed"
        self._set(job_id, state=state, finished=time.time(), outputs=outputs, notes=outcome.notes,
                  errors=[] if state == "done" else outcome.errors, summary=outcome.summary)

    def _outputs(self, job_id: str, out: Path, captures: Path, before: dict[str, tuple]) -> dict:
        """The job's outputs, by name, as addresses: the files it wrote, and the web captures it took (by
        their path in the project, so a client can keep them there)."""
        found: dict = {}
        for path in sorted(out.iterdir()):
            name = next((n for suffix, n in _OUTPUTS if path.name.endswith(suffix)), None)
            if name and path.is_file():
                found[name] = output_url(job_id, path.name)
        taken = {p: v for p, v in _versions(captures).items() if before.get(p) != v}
        if taken:
            found["captures"] = {f"{GENERATED}/{p}": output_url(job_id, f"{GENERATED}/{p}") for p in sorted(taken)}
        return found

    def output(self, job_id: str, name: str) -> Path | None:
        """An output's file, by the name in its address; None if there's no such output."""
        folder = self.store.folder(job_id)
        base = folder / "project" if name.startswith(GENERATED + "/") else folder / "out"
        path = (base / name).resolve()
        return path if path.is_relative_to(folder.resolve()) and path.is_file() else None


def output_url(job_id: str, name: str) -> str:
    return f"/v1/jobs/{job_id}/outputs/{quote(name)}"


def _versions(folder: Path) -> dict[str, tuple]:
    """Each file under `folder` (relative path) with its size and modification time."""
    if not folder.is_dir():
        return {}
    return {p.relative_to(folder).as_posix(): (p.stat().st_size, p.stat().st_mtime_ns)
            for p in folder.rglob("*") if p.is_file()}

