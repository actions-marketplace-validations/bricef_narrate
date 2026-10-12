"""Running the service's jobs (#79, #80): the CLI in a child process per job, a few at a time.

A job is laid out in its folder (projects.lay_out), run as `narrate build`,
`audio`, `frames` or `hear` (child.Child, as the studio's builds are), and its
outputs collected: the video or audio, poster, subtitle files, transcript, any
web captures taken, a contact sheet, or what `hear` found. Every change is saved to the job's record and announced to
whoever follows its events.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, unquote

from .. import project as zips
from ..child import Child
from . import options as job_options
from .costs import Prices, price
from .projects import ProjectError, lay_out
from .projects import parse as parse_project
from .store import FINAL, Store, is_sha256

# An output's name, by what its file ends in
_OUTPUTS = ((".transcript.txt", "transcript"), (".mp4", "video"), (".jpg", "poster"), (".srt", "srt"), (".vtt", "vtt"),
            ("frames.png", "sheet"), ("hear.json", "report"), *((f".{fmt}", "audio") for fmt in job_options.AUDIO_FORMATS))
GENERATED = ".narrate/generated"


def _when(seconds: float | None) -> str | None:
    return datetime.fromtimestamp(seconds, timezone.utc).isoformat(timespec="seconds") if seconds else None


def view(job: dict) -> dict:
    """A job as the API shows it."""
    return {**job, "created": _when(job["created"]), "started": _when(job["started"]),
            "finished": _when(job["finished"])}


class Runner:
    """Runs jobs `workers` at a time, with `engine` unless a job asks for another."""

    def __init__(self, store: Store, engine: str = "kokoro", workers: int = 1, prices: Prices | None = None):
        self.store = store
        self.engine = engine
        self.prices = prices
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

    def submit(self, kind: str, project: dict | None, options: dict, media: dict | None = None) -> dict:
        """A new job, queued. Raises OptionError or ProjectError (with what to upload) if it can't run.

        A build or audio job makes something from `project`. A frames or hear job looks at, or listens to,
        `media`: what an earlier job made ({"job": id}, which brings its script and engine), or an uploaded
        file ({"file": sha256, "name": "talk.mp4"}); a `project` gives it a script to compare with."""
        checked = job_options.check(kind, options)
        request: dict = {"options": checked}
        if kind in job_options.RENDERS:
            checked.setdefault("tts", self.engine)  # the engine it ran with, on record
        else:
            request["media"] = self._media(media)
        if project is not None or kind in job_options.RENDERS:
            parsed = parse_project(project)
            missing = self.store.missing(parsed.hashes())
            if missing:
                raise ProjectError(f"upload these files first: {', '.join(missing)}", missing)
            request["project"] = project
        job = self.store.new_job(kind, request)
        self.queue.put_nowait(job["id"])
        return job

    def _media(self, media) -> dict:
        """What a review job looks at, checked: a finished job's video or audio, or an uploaded file."""
        if not isinstance(media, dict):
            raise ProjectError('media must be {"job": id} or {"file": sha256, "name": …}')
        if "job" in media:
            source = self.store.job(str(media["job"]))
            if source is None or source["kind"] not in job_options.RENDERS:
                raise ProjectError(f"no build or audio job {media['job']!r}")
            if source["state"] != "done":
                raise ProjectError(f"job {source['id']} is {source['state']}: it has nothing to look at yet")
            return {"job": source["id"]}
        digest, name = media.get("file"), media.get("name") or "media"
        if not isinstance(digest, str) or not is_sha256(digest):
            raise ProjectError("media file must be the SHA-256 of an uploaded file")
        if not isinstance(name, str) or not re.fullmatch(r"[\w][\w .-]*", name):
            raise ProjectError(f"media name must be a plain file name, not {name!r}")
        missing = self.store.missing([digest])
        if missing:
            raise ProjectError(f"upload these files first: {', '.join(missing)}", missing)
        return {"file": digest, "name": name}

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
        job_id = job["id"]
        folder = self.store.folder(job_id)
        self._set(job_id, state="running", started=time.time(),
                  progress={"scene": 0, "of": None, "message": "starting"})
        out = folder / "out"
        out.mkdir(parents=True, exist_ok=True)
        spent = folder / "usage.json"
        try:
            args, output, printed = self._plan(job, folder, out)
            args += ["--usage", str(spent)]
        except ProjectError as e:
            self._set(job_id, state="failed", finished=time.time(), errors=[{"line": None, "message": str(e)}])
            return
        captures = folder / "project" / GENERATED
        before = _versions(captures)
        cwd = folder / "project" if (folder / "project").is_dir() else folder
        child = Child(args, cwd=cwd, on_progress=lambda p: self._set(job_id, progress=p))
        self.children[job_id] = child
        try:
            outcome = await child.run()
        finally:
            self.children.pop(job_id, None)
        if printed and outcome.code == 0:
            output.write_text(outcome.stdout + "\n", encoding="utf-8")
        outputs = self._outputs(job_id, out, captures, before)
        if outcome.cancelled:
            state = "cancelled"
        elif outcome.code == 0 and output.exists():
            state = "done"
        else:
            state = "failed"
        self._set(job_id, state=state, finished=time.time(), outputs=outputs, notes=outcome.notes,
                  errors=[] if state == "done" else outcome.errors, summary=outcome.summary,
                  usage=self._usage(spent))

    def _usage(self, spent: Path) -> dict | None:
        """What the job spent, as its command reported it, priced at the service's prices (#81)."""
        try:
            usage = json.loads(spent.read_text())
        except (OSError, ValueError):
            return None  # it stopped before it could say
        usage["cost"] = price(usage, self.prices)
        return usage

    def _plan(self, job: dict, folder: Path, out: Path) -> tuple[list[str], Path, bool]:
        """A job's command line, the output that says it worked, and whether that output is what the command
        prints (hear's report) rather than a file it writes."""
        kind, request = job["kind"], job["request"]
        options = dict(request["options"])
        script = lay_out(parse_project(request["project"]), self.store, folder / "project") \
            if request.get("project") is not None else None
        if kind in job_options.RENDERS:
            output = out / f"{script.stem}.{'mp4' if kind == 'build' else options.pop('format', 'mp3')}"
            return ([kind, str(script), "-o", str(output), "--tts", options.pop("tts", self.engine),
                     *job_options.arguments(kind, options)], output, False)
        media, source_script, source_tts = self._media_path(request["media"], folder)
        script = script or source_script
        with_script = ["--script", str(script)] if script else []
        if kind == "frames":
            output = out / "frames.png"
            engine = ["--tts", options.pop("tts", source_tts)] if script and (options.get("tts") or source_tts) else []
            return (["frames", str(media), "-o", str(output), *with_script, *engine,
                     *job_options.arguments(kind, options)], output, False)
        return (["hear", str(media), "--json", *with_script, *job_options.arguments(kind, options)],
                out / "hear.json", True)

    def _media_path(self, media: dict, folder: Path) -> tuple[Path, Path | None, str | None]:
        """The file a review job looks at; with an earlier job's, the script it was made from and its engine."""
        if "file" in media:
            target = folder / "media" / media["name"]
            target.parent.mkdir(parents=True, exist_ok=True)
            try:
                os.link(self.store.file(media["file"]), target)
            except OSError:
                shutil.copyfile(self.store.file(media["file"]), target)
            return target, None, None
        source = self.store.job(media["job"])
        made = source["outputs"].get("video") or source["outputs"].get("audio")
        path = self.output(source["id"], unquote(made.rsplit("/outputs/", 1)[1])) if made else None
        if path is None:
            raise ProjectError(f"job {source['id']} kept no video or audio")
        project = self.store.folder(source["id"]) / "project"
        written = source["request"]["project"].get("script")
        script = project / written if written else zips.find_script(project)
        return path, script if script.is_file() else None, source["request"]["options"].get("tts")

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

