import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from grad_engine import entry_checks, filters, paths
from grad_engine.models import Job

CYCLES = ["Class of 2027", "Class of 2026"]


def _job(**extra):
    fields = dict(id="greenhouse:acme:1", source="greenhouse", company="Acme",
                  company_slug="acme", title="Software Engineer", location="Austin, TX",
                  url="https://example.com/1")
    fields.update(extra)
    return Job(**fields)


def test_verdict_survives_a_save_and_load_without_entering_job_history():
    checks = {}
    entry_checks.remember(_job(), checks, CYCLES)
    entry_checks.save(checks)
    assert entry_checks.rejected(_job(), entry_checks.load(), CYCLES)
    assert not Path(paths.JOBS_PATH).exists()
    assert "description" not in json.dumps(checks)


def test_rejection_expires_after_24_hours():
    now = datetime(2026, 10, 17, 12, tzinfo=UTC)
    checks = {}
    entry_checks.remember(_job(), checks, CYCLES, now=now)
    assert entry_checks.rejected(_job(), checks, CYCLES, now=now + timedelta(hours=23))
    assert not entry_checks.rejected(_job(), checks, CYCLES, now=now + timedelta(hours=24))
    assert not entry_checks.rejected(_job(), checks, CYCLES, now=now - timedelta(seconds=1))


def test_title_cohort_or_classifier_changes_invalidate_the_cache(monkeypatch):
    checks = {}
    entry_checks.remember(_job(), checks, CYCLES)
    assert not entry_checks.rejected(_job(title="Backend Software Engineer"), checks, CYCLES)
    assert not entry_checks.rejected(_job(), checks, ["Class of 2028"])
    assert entry_checks.rejected(_job(), checks, list(reversed(CYCLES)))
    monkeypatch.setattr(filters, "DESCRIPTION_ENTRY_VERSION", filters.DESCRIPTION_ENTRY_VERSION + 1)
    assert not entry_checks.rejected(_job(), checks, CYCLES)


def test_save_prunes_expired_verdicts():
    checks = {}
    entry_checks.remember(_job(), checks, CYCLES, now=datetime.now(UTC) - timedelta(days=2))
    entry_checks.save(checks)
    assert entry_checks.load() == {}


def test_malformed_timestamp_is_not_a_cached_rejection():
    checks = {}
    entry_checks.remember(_job(), checks, CYCLES)
    for timestamp in [None, "not-a-date", "2026-10-17T12:00:00"]:
        checks[_job().id]["checked_at"] = timestamp
        assert not entry_checks.rejected(_job(), checks, CYCLES)


def test_corrupt_cache_is_not_silently_overwritten():
    with open(paths.ENTRY_CHECKS_PATH, "w", encoding="utf-8") as f:
        f.write("[]")
    with pytest.raises(ValueError):
        entry_checks.load()
    assert open(paths.ENTRY_CHECKS_PATH, encoding="utf-8").read() == "[]"


def test_missing_cache_is_a_cold_start():
    assert entry_checks.load() == {}
