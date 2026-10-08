"""Inspect and prune the speech and render caches (`narrate cache`).

Entries are .npy files under <cache>/tts/<engine>/, and rendered pictures
under <cache>/render/<renderer>/; a cache hit refreshes the
file's modification time, so pruning by age or size removes the least
recently used first. Entries used within `protect` seconds are never removed,
which keeps anything a running build depends on.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from pathlib import Path

from .tts import cache_dir


@dataclass
class Entry:
    path: Path
    engine: str
    size: int
    used: float  # mtime, refreshed on every cache hit


def parse_size(text: str) -> int:
    """`500M`, `2G`, `100k`, `1048576` -> bytes."""
    m = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*([kmgt]?)i?b?\s*", text.lower())
    if not m:
        raise ValueError(f"invalid size {text!r}")
    return int(float(m.group(1)) * 1024 ** "_kmgt".index(m.group(2) or "_"))


def human(size: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"


def entries(root: Path | None = None) -> list[Entry]:
    tts = (root or cache_dir()) / "tts"
    found = []
    for path in [*tts.glob("*/*.npy"), *tts.glob("*.npy")] if tts.is_dir() else []:
        stat = path.stat()
        # Files directly under tts/ predate per-engine folders
        engine = "legacy" if path.parent == tts else path.parent.name
        found.append(Entry(path, engine, stat.st_size, stat.st_mtime))
    # Render block outputs (<cache>/render/<renderer>/), refreshed on every hit too
    for path in ((root or cache_dir()) / "render").glob("*/*.png"):
        stat = path.stat()
        found.append(Entry(path, f"render:{path.parent.name}", stat.st_size, stat.st_mtime))
    return found


def summary(found: list[Entry]) -> dict[str, tuple[int, int]]:
    by_engine: dict[str, tuple[int, int]] = {}
    for e in found:
        count, size = by_engine.get(e.engine, (0, 0))
        by_engine[e.engine] = (count + 1, size + e.size)
    return by_engine


def prune(found: list[Entry], *, max_size: int | None = None, older_than: float | None = None,
          protect: float = 3600, now: float | None = None) -> list[Entry]:
    """Delete stale entries (oldest first) and return what was removed."""
    now = time.time() if now is None else now
    candidates = sorted((e for e in found if now - e.used > protect), key=lambda e: e.used)
    removed = [e for e in candidates if older_than is not None and now - e.used > older_than]
    kept_size = sum(e.size for e in found) - sum(e.size for e in removed)
    if max_size is not None:
        for e in candidates:
            if kept_size <= max_size:
                break
            if e not in removed:
                removed.append(e)
                kept_size -= e.size
    for e in removed:
        e.path.unlink(missing_ok=True)
    return removed
