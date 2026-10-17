"""Short-lived negative description verdicts, separate from real job history.

Upstream enriches each matched internship once. The new-grad description
fallback also reads candidates that are NOT entry level; remembering those
reads avoids paying for the same rejected posting on every run. Never cache a
failed/empty detail fetch. Recheck daily, and immediately after a title, cohort
configuration, or description-classifier version change.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta

from . import filters, paths
from .models import Job

_TTL = timedelta(hours=24)


def _fresh(record: dict, now: datetime) -> bool:
    try:
        checked = datetime.fromisoformat(record["checked_at"].replace("Z", "+00:00"))
        return checked.tzinfo is not None and timedelta(0) <= now - checked < _TTL
    except (KeyError, ValueError, TypeError, AttributeError):
        return False


def rejected(job: Job, checks: dict, cycles: list[str],
             now: datetime | None = None) -> bool:
    record = checks.get(job.id) or {}
    return (
        record.get("version") == filters.DESCRIPTION_ENTRY_VERSION
        and record.get("title") == job.title
        and record.get("cycles") == sorted(cycles)
        and _fresh(record, now or datetime.now(UTC))
    )


def remember(job: Job, checks: dict, cycles: list[str],
             now: datetime | None = None) -> None:
    """Called only after a nonempty posting failed the entry-level check."""
    checks[job.id] = {
        "title": job.title,
        "cycles": sorted(cycles),
        "version": filters.DESCRIPTION_ENTRY_VERSION,
        "checked_at": (now or datetime.now(UTC)).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def load() -> dict:
    if not os.path.exists(paths.ENTRY_CHECKS_PATH):
        return {}
    with open(paths.ENTRY_CHECKS_PATH, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict) or any(
        not isinstance(k, str) or not isinstance(v, dict) for k, v in data.items()
    ):
        raise ValueError("entry checks must be an object of verdict records")
    return data


def save(checks: dict) -> None:
    # Expired verdicts need no history. This cache must not turn thousands of
    # rejected senior roles into fake new-grad posting/lifetime statistics.
    now = datetime.now(UTC)
    fresh = {jid: r for jid, r in checks.items() if _fresh(r, now)}
    os.makedirs(os.path.dirname(paths.ENTRY_CHECKS_PATH), exist_ok=True)
    tmp = f"{paths.ENTRY_CHECKS_PATH}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(fresh, f, indent=2, ensure_ascii=False, sort_keys=True)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, paths.ENTRY_CHECKS_PATH)
