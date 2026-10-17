# Techniques: tools, APIs, and non-obvious tricks this repo uses, one line each

## Already in the engine
- Python 3 + httpx async client, pytest test suite, ruff lint; a GitHub Actions cron runs the update every 30 minutes.
- 12 ATS (applicant tracking system) connectors read public job APIs directly: Greenhouse, Lever, Ashby, SmartRecruiters, Workday, Oracle, Rippling, Workable, Breezy, Recruitee, Eightfold, Amazon.
- Workday CXS API: POST /wday/cxs/{tenant}/{site}/jobs, 20 postings per page, searched with "new grad", "early career", "entry level", "graduate".
- Oracle Recruiting Cloud REST API (recruitingCEJobRequisitions) per tenant host and site number, same four keywords.
- Workable v3 search API is called with no retries, so a provider-wide 429 fails one board fast instead of stalling the sweep.
- Concurrency caps: 32 requests at once overall, 8 per host, so one big tenant cannot hog the run.
- Site-aware board keys (ats:slug:site) so a full read of one Workday or Oracle site never closes a role on another site.
- Two-miss closure: a role closes only after it is missing from two complete snapshots in a row; capped or failed reads never close anything.
- Circuit breaker per board: 3 failures in a row quarantines it for 6h, doubling up to a 72h cap; one success resets it.
- Outbox after publish: an update run queues new role ids per channel (Discord, Telegram), and alerts only go out after the commit is pushed, so a failed push never announces roles missing from the site.
- Atomic file writes (write to .tmp, fsync, os.replace) for the registry, store, and stats.
- Sponsorship classifier reads posting text once per role and stamps a classifier version, so rule changes re-read old roles exactly once.

## Changes
- Registry gap fill (Oct 2026): compared five public new-grad lists against our board, re-checked each missing company with our own connectors, and added 68 boards; 11 open roles passed our filters on day one. Removed a duplicate JPMorgan Oracle site that returned the same 515 requisitions as the other.
