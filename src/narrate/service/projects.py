"""A project as a request gives it (#79), checked, and laid out in a job's folder.

Three forms:
- files by content: `{"script": "intro.md", "files": {"intro.md": "<sha256>", "team.jpg": "<sha256>"}}`;
- a script sent inline, with or without files: `{"script": "intro.md", "text": "…"}`;
- a ZIP, uploaded as a file: `{"zip": "<sha256>", "source": "intro.md"}` (`source` only if it holds
  more than one script), unpacked as `narrate build` unpacks one (project.extract).

Paths are relative, with no `..` and no hidden parts except narrate's own
`.narrate/`: a folder sent whole may hold secrets such as `.env`, which don't
belong in the store.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from .. import project as zips
from .store import Store, is_sha256

SCRIPT_SUFFIXES = (".md", ".mkd", ".txt")


class ProjectError(ValueError):
    """The project can't be laid out: a bad path, a missing file. `missing` lists files to upload first."""

    def __init__(self, message: str, missing: list[str] | None = None):
        super().__init__(message)
        self.missing = missing or []


@dataclass
class Project:
    script: str | None  # its path in the project; for a ZIP, `source` or the only script in it
    files: dict[str, str]  # path -> sha256
    text: str | None = None
    zip: str | None = None  # the ZIP's sha256
    source: str | None = None

    def hashes(self) -> set[str]:
        return {*self.files.values(), *([self.zip] if self.zip else [])}


def _path(path: Any) -> str:
    if not isinstance(path, str) or not path.strip():
        raise ProjectError("paths must be non-empty strings")
    pure = PurePosixPath(path)
    if pure.is_absolute() or "\\" in path or any(part in ("..", "") for part in path.split("/")):
        raise ProjectError(f"{path!r}: paths are relative, with no '..'")
    if any(part.startswith(".") for part in pure.parts) and pure.parts[0] != ".narrate":
        raise ProjectError(f"{path!r}: hidden files (.env, .git) aren't part of a project; leave them out")
    return pure.as_posix()


def parse(value: Any) -> Project:
    """The project a request describes, checked."""
    if not isinstance(value, dict):
        raise ProjectError("project must be an object")
    if "zip" in value:
        zip_hash, source = value["zip"], value.get("source")
        if not isinstance(zip_hash, str) or not is_sha256(zip_hash):
            raise ProjectError("zip must be the SHA-256 of an uploaded ZIP")
        if source is not None:
            source = _path(source)
        return Project(None, {}, zip=zip_hash, source=source)
    script = _path(value.get("script"))
    if not script.lower().endswith(SCRIPT_SUFFIXES):
        raise ProjectError(f"{script!r} isn't a script ({', '.join(SCRIPT_SUFFIXES)})")
    files = value.get("files") or {}
    if not isinstance(files, dict):
        raise ProjectError("files must map paths to SHA-256 hashes")
    checked: dict[str, str] = {}
    for path, digest in files.items():
        if not isinstance(digest, str) or not is_sha256(digest):
            raise ProjectError(f"{path!r}: not a SHA-256 hash: {digest!r}")
        checked[_path(path)] = digest
    text = value.get("text")
    if text is not None and not isinstance(text, str):
        raise ProjectError("text must be the script, as a string")
    if text is None and script not in checked:
        raise ProjectError(f"the script {script!r} is neither in files nor sent as text")
    return Project(script, checked, text=text)


def lay_out(project: Project, store: Store, folder: Path) -> Path:
    """Put the project's files in `folder`, and return the script to build.

    Files are linked from the store, which keeps them read-only; those under
    `.narrate/` are copied instead, since a build may rewrite them (a web
    capture's sidecar, say)."""
    missing = store.missing(project.hashes())
    if missing:
        raise ProjectError(f"upload these files first: {', '.join(missing)}", missing)
    folder.mkdir(parents=True, exist_ok=True)
    if project.zip:
        try:
            return zips.extract(store.file(project.zip), folder, project.source)
        except zips.ProjectError as e:
            raise ProjectError(str(e)) from None
    for path, digest in project.files.items():
        target = folder / path
        target.parent.mkdir(parents=True, exist_ok=True)
        if path.startswith(".narrate/"):
            shutil.copyfile(store.file(digest), target)
            target.chmod(0o644)
            continue
        try:
            os.link(store.file(digest), target)
        except OSError:  # another filesystem
            shutil.copyfile(store.file(digest), target)
    script = folder / project.script
    if project.text is not None:
        script.unlink(missing_ok=True)
        script.parent.mkdir(parents=True, exist_ok=True)
        script.write_text(project.text, encoding="utf-8")
    return script
