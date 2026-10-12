"""What the service keeps (#79), all in its data folder:

- `files/`: uploaded files, named by their SHA-256, read-only;
- `jobs/<id>/`: each job's project (`project/`) and outputs (`out/`);
- `narrate.db`: job records, in SQLite.

Nothing expires on its own (docs/design/service.md).
"""

from __future__ import annotations

import json
import os
import secrets
import sqlite3
import time
from collections.abc import Iterable
from pathlib import Path

SHA256 = frozenset("0123456789abcdef")
FINAL = ("done", "failed", "cancelled")
_COLUMNS = ("id", "kind", "state", "created", "started", "finished", "request", "progress", "outputs", "notes",
            "errors", "summary", "usage")
_JSON = {"request", "progress", "outputs", "notes", "errors", "usage"}  # held as JSON text
_SCHEMA = """CREATE TABLE IF NOT EXISTS jobs (
  id TEXT PRIMARY KEY, kind TEXT, state TEXT, created REAL, started REAL, finished REAL,
  request TEXT, progress TEXT, outputs TEXT, notes TEXT, errors TEXT, summary TEXT, usage TEXT)"""


def is_sha256(value: str) -> bool:
    return len(value) == 64 and set(value) <= SHA256


def default_root() -> Path:
    base = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    return Path(base) / "narrate" / "service"


class HashMismatch(ValueError):
    """An upload's content doesn't have the hash it was sent as."""


class Store:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.files = self.root / "files"
        self.jobs_dir = self.root / "jobs"
        for d in (self.files, self.jobs_dir, self.files / "incoming"):
            d.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.root / "narrate.db", check_same_thread=False, isolation_level=None)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute(_SCHEMA)
        self.db.execute("CREATE INDEX IF NOT EXISTS jobs_created ON jobs (created)")

    # -- files ----------------------------------------------------------------------------------

    def file(self, sha256: str) -> Path:
        return self.files / sha256

    def missing(self, hashes: Iterable[str]) -> list[str]:
        return sorted({h for h in hashes if not self.file(h).is_file()})

    def incoming(self) -> Path:
        """Where an upload is written while it arrives, before keep() checks and keeps it."""
        return self.files / "incoming" / secrets.token_hex(8)

    def keep(self, sha256: str, part: Path, actual: str) -> bool:
        """Keep an upload written to `part`, whose content's SHA-256 is `actual`, as the file `sha256`.
        False if it was kept already. Either way `part` is gone afterwards."""
        try:
            if actual != sha256:
                raise HashMismatch(f"the content's SHA-256 is {actual}, not {sha256}")
            if self.file(sha256).is_file():
                return False
            part.chmod(0o444)  # jobs link to it: nothing may change it in place
            part.replace(self.file(sha256))
            return True
        finally:
            part.unlink(missing_ok=True)

    # -- jobs -----------------------------------------------------------------------------------

    def new_job(self, kind: str, request: dict) -> dict:
        now = time.time()
        job = {"id": f"j_{int(now * 1000):x}{secrets.token_hex(3)}", "kind": kind, "state": "queued", "created": now,
               "started": None, "finished": None, "request": request, "progress": None, "outputs": {}, "notes": [],
               "errors": [], "summary": "", "usage": None}
        self.db.execute(f"INSERT INTO jobs ({', '.join(_COLUMNS)}) VALUES ({', '.join('?' * len(_COLUMNS))})",
                        [self._column(c, job[c]) for c in _COLUMNS])
        return job

    def update(self, job_id: str, **fields) -> None:
        self.db.execute(f"UPDATE jobs SET {', '.join(f'{c} = ?' for c in fields)} WHERE id = ?",
                        [*(self._column(c, v) for c, v in fields.items()), job_id])

    def job(self, job_id: str) -> dict | None:
        row = self.db.execute(f"SELECT {', '.join(_COLUMNS)} FROM jobs WHERE id = ?", [job_id]).fetchone()
        return self._job(row) if row else None

    def jobs(self, limit: int = 50, state: str | None = None) -> list[dict]:
        where, args = ("WHERE state = ?", [state]) if state else ("", [])
        rows = self.db.execute(f"SELECT {', '.join(_COLUMNS)} FROM jobs {where} ORDER BY created DESC LIMIT ?",
                               [*args, limit]).fetchall()
        return [self._job(r) for r in rows]

    def between(self, start: float, end: float) -> list[dict]:
        """Jobs made from `start` up to `end` (seconds since the epoch), oldest first."""
        rows = self.db.execute(f"SELECT {', '.join(_COLUMNS)} FROM jobs WHERE created >= ? AND created < ? "
                               "ORDER BY created", [start, min(end, 1e18)]).fetchall()
        return [self._job(r) for r in rows]

    def waiting(self) -> list[str]:
        """Queued jobs, oldest first: they run when the service starts again."""
        return [r[0] for r in self.db.execute("SELECT id FROM jobs WHERE state = 'queued' ORDER BY created")]

    def interrupt(self) -> list[str]:
        """Jobs left running when the service stopped: they can't be resumed, so they failed."""
        ids = [r[0] for r in self.db.execute("SELECT id FROM jobs WHERE state = 'running'")]
        for job_id in ids:
            self.update(job_id, state="failed", finished=time.time(),
                        errors=[{"line": None, "message": "interrupted: the service stopped while it ran"}])
        return ids

    def folder(self, job_id: str) -> Path:
        return self.jobs_dir / job_id

    @staticmethod
    def _column(name: str, value):
        return json.dumps(value) if name in _JSON else value

    @staticmethod
    def _job(row) -> dict:
        return {c: (json.loads(v) if c in _JSON and v is not None else v) for c, v in zip(_COLUMNS, row)}
