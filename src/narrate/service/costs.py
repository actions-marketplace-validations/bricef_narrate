"""What each job cost (#81): its usage, priced, and reports over any period.

A job's usage is the CLI's own report (`--usage`). The service prices it with
the rates it was started with (`narrate serve --prices prices.yaml`) and keeps
those rates with the job, so a later change doesn't rewrite what earlier jobs
cost. Usage is kept as long as the job records are: indefinitely.

    currency: USD
    elevenlabs_per_1000_credits: 0.30   # what your plan charges
    cpu_per_hour: 0.05                  # what the machine's time is worth, if anything
"""

from __future__ import annotations

import csv
import io
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import yaml


class PricesError(ValueError):
    pass


@dataclass(frozen=True)
class Prices:
    currency: str = "USD"
    elevenlabs_per_1000_credits: float = 0.0
    cpu_per_hour: float = 0.0

    @classmethod
    def load(cls, path: Path) -> Prices:
        try:
            data = yaml.safe_load(path.read_text()) or {}
        except (OSError, yaml.YAMLError) as e:
            raise PricesError(f"can't read prices from {path}: {e}") from None
        if not isinstance(data, dict):
            raise PricesError(f"{path}: prices are a map, such as elevenlabs_per_1000_credits: 0.30")
        unknown = set(data) - {"currency", "elevenlabs_per_1000_credits", "cpu_per_hour"}
        if unknown:
            raise PricesError(f"{path}: unknown prices: {', '.join(sorted(unknown))}")
        values = {}
        for key in ("elevenlabs_per_1000_credits", "cpu_per_hour"):
            value = data.get(key, 0)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
                raise PricesError(f"{path}: {key} must be a number, 0 or more")
            values[key] = float(value)
        return cls(str(data.get("currency", "USD")), **values)


def credits(usage: dict) -> float:
    speech = usage.get("speech") or {}
    return sum(m.get("credits", 0.0) for m in (speech.get("models") or {}).values())


def price(usage: dict, prices: Prices | None) -> dict | None:
    """A job's cost: its ElevenLabs credits and CPU time at `prices`, with the prices themselves."""
    if prices is None:
        return None
    speech = credits(usage) / 1000 * prices.elevenlabs_per_1000_credits
    compute = (usage.get("cpu_seconds") or 0.0) / 3600 * prices.cpu_per_hour
    return {"currency": prices.currency, "speech": round(speech, 6), "compute": round(compute, 6),
            "total": round(speech + compute, 6), "prices": asdict(prices)}


# What a usage report sums, per job and in total
NUMBERS = ("characters", "cached_characters", "requests", "credits", "rendered", "media_seconds", "wall_seconds",
           "cpu_seconds", "cost_speech", "cost_compute", "cost_total")


def _row(job: dict) -> dict:
    usage = job.get("usage") or {}
    models = ((usage.get("speech") or {}).get("models") or {}).values()
    cost = usage.get("cost") or {}
    return {
        "job": job["id"], "kind": job["kind"], "state": job["state"],
        "created": datetime.fromtimestamp(job["created"], timezone.utc).isoformat(timespec="seconds"),
        "engine": (usage.get("speech") or {}).get("engine") or job["request"]["options"].get("tts") or "",
        "characters": sum(m.get("characters", 0) for m in models),
        "cached_characters": sum(m.get("cached_characters", 0) for m in models),
        "requests": sum(m.get("requests", 0) for m in models),
        "credits": round(credits(usage), 3),
        "rendered": sum((usage.get("rendered") or {}).values()),
        "media_seconds": usage.get("video_seconds") or usage.get("audio_seconds")
        or (usage.get("speech_to_text") or {}).get("seconds") or 0.0,
        "wall_seconds": usage.get("wall_seconds") or 0.0, "cpu_seconds": usage.get("cpu_seconds") or 0.0,
        "cost_speech": cost.get("speech", 0.0), "cost_compute": cost.get("compute", 0.0),
        "cost_total": cost.get("total", 0.0), "currency": cost.get("currency", ""),
    }


def _sum(rows: list[dict]) -> dict:
    return {key: round(sum(r[key] for r in rows), 6) for key in NUMBERS}


def report(jobs: list[dict], by: str) -> dict:
    """Usage and cost of `jobs`, a row each (`by` "job") or a row per day (`by` "day"), with totals."""
    rows = [_row(j) for j in jobs]
    if by == "day":
        days: dict[str, list[dict]] = {}
        for r in rows:
            days.setdefault(r["created"][:10], []).append(r)
        rows = [{"day": day, "jobs": len(group), **_sum(group)} for day, group in sorted(days.items())]
    return {"by": by, "rows": rows, "totals": {"jobs": len(jobs), **_sum([_row(j) for j in jobs])}}


def as_csv(result: dict) -> str:
    out = io.StringIO()
    rows = result["rows"]
    fields = list(rows[0]) if rows else (["day", "jobs", *NUMBERS] if result["by"] == "day" else ["job", *NUMBERS])
    writer = csv.DictWriter(out, fieldnames=fields, extrasaction="ignore", lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    writer.writerow({fields[0]: "total", **result["totals"]})
    return out.getvalue()


def period(since: str | None, until: str | None) -> tuple[float, float]:
    """The times a report covers: from the start of day `since` to the end of day `until` (UTC), both
    optional, as in 2026-10-01."""
    def day(value: str, name: str) -> datetime:
        try:
            return datetime.combine(date.fromisoformat(value), datetime.min.time(), timezone.utc)
        except ValueError:
            raise ValueError(f"{name} must be a date, as in 2026-10-01") from None

    start = day(since, "since").timestamp() if since else 0.0
    end = (day(until, "until") + timedelta(days=1)).timestamp() if until else float("inf")
    return start, end
