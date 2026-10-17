# Contributing

The fastest way to help: **add companies.** More companies = more new grad roles.

## Add a company (one line)

1. Find the company's ATS token from their careers "Apply" URL:
   - `boards.greenhouse.io/`**`stripe`** → slug is `stripe`
   - `jobs.lever.co/`**`plaid`** → slug is `plaid`
   - `jobs.ashbyhq.com/`**`openai`** → slug is `openai`
2. Add an entry to [`data/candidates.json`](data/candidates.json):
   ```json
   {"name": "Stripe", "slug": "stripe"}
   ```
3. Re-validate and refresh locally:
   ```bash
   python run.py harvest   # detects which ATS the slug lives on
   python run.py update    # refreshes listings, README, and CSV
   ```
4. Open a pull request.

The harvester auto-detects the ATS (Greenhouse, Lever, Ashby, SmartRecruiters,
Rippling, Workable, Breezy, Recruitee), so you only need the name + slug.
Prefer not to run anything? [Open a company request](../../issues/new?template=add-company.yml) and paste the board URL.
Workday/Oracle tenants need a `wd`/`site` (or `host`/`site`) pair — easiest is
to run `python run.py discover` (it mines them from public datasets), or copy
the shape of an existing entry in `data/companies.json`.

## Run locally

```bash
python -m venv .venv
# Windows:        .\.venv\Scripts\activate
# macOS / Linux:  source .venv/bin/activate
pip install -r requirements.txt
python run.py all      # harvest + update
```

## Tuning what counts as a new grad role

All the classification (new grad / tech / class year / category) lives in one
file: [`src/grad_engine/filters.py`](src/grad_engine/filters.py). PRs that
improve precision/recall against real titles are very welcome.

When changing `description_entry_reason`, bump `DESCRIPTION_ENTRY_VERSION`
so negative verdicts in `data/entry_checks.json` are checked again. The cache
also expires after 24 hours; failed or empty detail requests remain retryable.

## Enabling native email on your own fork

Email credentials and subscriber lists do not come with the source code.
Without configuration, the dashboard and README offer RSS/Feedrabbit instead,
and `python run.py mailcheck` reports **disabled**, not healthy delivery.

To operate your own double-opt-in digest:

1. Set up your own Supabase project and review/apply [`db/schema.sql`](db/schema.sql).
   Keep its subscriber data private; do not reuse another repo's subscriber list.
2. Add `supabase_url` and `supabase_publishable_key` to `data/config.json`.
   Only the public client key belongs here, **never the service-role key**.
3. Configure GitHub Actions secrets `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`,
   `BREVO_API_KEY`, and `MAIL_FROM` (a sender verified with Brevo).
4. Confirm a subscription you own, refresh/deploy the list, then verify the
   notifier's delivery result and `data/mail_state.json`. Run `mailcheck` with
   the same credentials; a signup without a configured sender fails the check.

Keep the publish gate and live-Pages check before delivery. Do not run the
notifier against unpublished test fixtures. Feedrabbit is a separate service
and follows its own plan and delivery schedule.

## Improving the sponsorship flags

The 🇺🇸 / 🛂 flags come from
[`src/grad_engine/sponsorship.py`](src/grad_engine/sponsorship.py), which
matches phrases employers actually write. Found a posting it gets wrong? Add
the phrase to the right pattern **with a test** in
`tests/test_sponsorship.py` — precision matters more than recall here.
