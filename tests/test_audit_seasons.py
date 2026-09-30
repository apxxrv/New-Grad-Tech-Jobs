"""Season audit must preserve evidence and fail closed on retrieval outages."""

from __future__ import annotations

import sys

import pytest

import tools.audit_seasons as audit


def _record(jid: str = "greenhouse:acme:1") -> dict:
    return {
        "id": jid, "source": "greenhouse", "company": "Acme",
        "company_slug": "acme", "title": "Software Engineer, New Grad", "location": "US",
        "url": "https://x/1", "season": "Class of 2027",
        "seasons": ["Class of 2027"], "season_inferred": True, "is_open": True,
    }


def _setup(monkeypatch, tmp_path, data, results):
    companies = tmp_path / "companies.json"
    companies.write_text("[]", encoding="utf-8")
    monkeypatch.setattr(audit.paths, "COMPANIES_PATH", str(companies))
    monkeypatch.setattr(audit.paths, "JOBS_PATH", str(tmp_path / "jobs.json"))
    monkeypatch.setattr(audit.config, "load_config", lambda: {})
    monkeypatch.setattr(audit.config, "cycles", lambda _cfg: ["Class of 2027", "Class of 2026"])
    monkeypatch.setattr(audit.store, "load", lambda _path: data)
    monkeypatch.setattr(audit.store, "now_iso", lambda: "2026-08-06T14:00:00Z")

    async def fake_texts(_jobs, _companies):
        return results

    monkeypatch.setattr(audit, "_texts_for", fake_texts)
    saved = {}
    monkeypatch.setattr(audit.store, "save", lambda _path, rows: saved.update(rows))
    return saved


def test_moved_cycle_updates_primary_and_full_season_set(monkeypatch, tmp_path):
    rec = _record()
    data = {rec["id"]: rec}
    saved = _setup(monkeypatch, tmp_path, data, {
        rec["id"]: audit.TextResult("OK", "This role is for the Class of 2026."),
    })
    monkeypatch.setattr(sys, "argv", ["audit_seasons.py", "--apply"])
    audit.main()
    assert saved[rec["id"]]["season"] == "Class of 2026"
    assert saved[rec["id"]]["seasons"] == ["Class of 2026"]
    assert saved[rec["id"]]["season_audit_verdict"] == "moved"


def test_multi_cycle_text_confirms_primary_and_preserves_every_cycle(
    monkeypatch, tmp_path,
):
    rec = _record()
    data = {rec["id"]: rec}
    saved = _setup(monkeypatch, tmp_path, data, {
        rec["id"]: audit.TextResult(
            "OK", "Open to candidates graduating between December 2026 and June 2027.",
        ),
    })
    monkeypatch.setattr(sys, "argv", ["audit_seasons.py", "--apply"])

    audit.main()

    assert saved[rec["id"]]["season"] == "Class of 2027"
    assert saved[rec["id"]]["seasons"] == ["Class of 2027", "Class of 2026"]
    assert saved[rec["id"]]["season_inferred"] is False


def test_off_cycle_closure_records_reason_and_evidence(monkeypatch, tmp_path):
    rec = _record()
    data = {rec["id"]: rec}
    saved = _setup(monkeypatch, tmp_path, data, {
        rec["id"]: audit.TextResult("OK", "Class of 2028 new grad program"),
    })
    monkeypatch.setattr(sys, "argv", ["audit_seasons.py", "--apply"])
    audit.main()
    row = saved[rec["id"]]
    assert row["is_open"] is False
    assert row["closed_reason"] == "out-of-scope"
    assert row["seasons"] == ["Class of 2028"]
    assert row["season_audit_verdict"] == "off-cycle"


def test_fetch_outage_fails_coverage_guard_without_saving(monkeypatch, tmp_path):
    rec = _record()
    saved = _setup(monkeypatch, tmp_path, {rec["id"]: rec}, {
        rec["id"]: audit.TextResult("FETCH-FAILED", error="TimeoutError"),
    })
    monkeypatch.setattr(sys, "argv", ["audit_seasons.py", "--apply"])
    with pytest.raises(SystemExit, match="2"):
        audit.main()
    assert saved == {}


def test_no_text_and_no_signal_are_distinct_verdicts(monkeypatch, tmp_path, capsys):
    no_text = _record("greenhouse:acme:no-text")
    no_signal = _record("greenhouse:acme:no-signal")
    data = {r["id"]: r for r in (no_text, no_signal)}
    _setup(monkeypatch, tmp_path, data, {
        no_text["id"]: audit.TextResult("NO-TEXT"),
        no_signal["id"]: audit.TextResult("OK", "Generic internship posting"),
    })
    monkeypatch.setattr(sys, "argv", ["audit_seasons.py"])
    audit.main()
    output = capsys.readouterr().out
    assert "NO-TEXT (1)" in output
    assert "NO-SIGNAL (1)" in output
