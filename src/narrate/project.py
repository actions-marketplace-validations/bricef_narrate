"""Projects packaged as ZIP archives (Narakeet's build input, spec §1, §12)."""

from __future__ import annotations

import shutil
import stat
import tempfile
import zipfile
from contextlib import contextmanager
from pathlib import Path, PurePosixPath

SCRIPT_SUFFIXES = {".md", ".mkd", ".txt"}
MAX_UNPACKED = 4 * 1024**3  # refuse archives that would expand past 4 GB


class ProjectError(Exception):
    pass


def _safe_members(archive: zipfile.ZipFile) -> list[zipfile.ZipInfo]:
    members, total = [], 0
    for info in archive.infolist():
        path = PurePosixPath(info.filename)
        if path.is_absolute() or ".." in path.parts or info.filename.startswith("\\") or ":" in path.parts[0]:
            raise ProjectError(f"unsafe path in archive: {info.filename}")
        if stat.S_ISLNK(info.external_attr >> 16):
            raise ProjectError(f"symbolic links are not supported in archives: {info.filename}")
        total += info.file_size
        if total > MAX_UNPACKED:
            raise ProjectError("archive expands to more than 4 GB")
        members.append(info)
    return members


def find_script(root: Path) -> Path:
    """The project's only script, or an error naming the candidates."""
    candidates = sorted(p for p in root.rglob("*")
                        if p.suffix.lower() in SCRIPT_SUFFIXES and p.is_file()
                        and not any(part.startswith(("__MACOSX", ".")) for part in p.relative_to(root).parts)
                        and "credits" not in p.relative_to(root).parts)
    if len(candidates) == 1:
        return candidates[0]
    names = ", ".join(str(p.relative_to(root)) for p in candidates) or "none"
    raise ProjectError(f"choose the script with --source (candidates: {names})")


@contextmanager
def unpacked(archive_path: Path, source: str | None = None):
    """Extract a project archive to a temporary directory; yield the main script's path."""
    try:
        archive = zipfile.ZipFile(archive_path)
    except (zipfile.BadZipFile, OSError) as e:
        raise ProjectError(f"cannot open {archive_path}: {e}") from None
    workdir = Path(tempfile.mkdtemp(prefix="narrate-project-"))
    try:
        with archive:
            for info in _safe_members(archive):
                archive.extract(info, workdir)
        if source:
            script = (workdir / source).resolve()
            if workdir.resolve() not in script.parents or not script.is_file():
                raise ProjectError(f"{source} is not in the archive")
        else:
            script = find_script(workdir)
        yield script
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
