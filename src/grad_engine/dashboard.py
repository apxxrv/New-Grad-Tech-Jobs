"""Generate a self-contained metrics + listings dashboard for GitHub Pages.

Writes docs/index.html with the run metrics, a run-history sparkline, and the
current open roles baked in (no external fetches, so it works the moment Pages
serves it). Filtering/search runs client-side in vanilla JS — the page stays a
single static file. Regenerated every run.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from html import escape
from pathlib import Path
from urllib.parse import urlsplit

from . import config, filters, grouping, h1b, paths, radar, trends


def _engine_panel(stats: dict, by_category: dict, history: list[dict]) -> str:
    """Operator metrics, deliberately collapsed and last.

    Real and worth publishing — they're the evidence the pipeline works — but
    they answer "is the engine healthy", not "where do I apply".
    """
    latency = stats.get("detection_latency") or {}
    lat = (
        f"{latency['median_minutes']:.0f} min median"
        + (f" · {latency['p95_minutes']:.0f} min p95" if latency.get("p95_minutes") else "")
        + f" (n={latency.get('sample_size', 0)})"
        if latency.get("median_minutes") is not None and latency.get("sample_size", 0) >= 5
        else "calibrating — needs more roles with exact source timestamps"
    )
    life = stats.get("posting_lifetime") or {}
    lifetime = (
        f"{life['median_days']:.0f} days (n={life.get('sample_size', 0)})"
        if life.get("median_days") is not None and life.get("sample_size", 0) >= 5
        else "calibrating"
    )
    partial = stats.get("snapshots_partial") or 0
    facts = [
        ("Boards polled",
         f"{stats.get('fetched_ok', 0):,} of {stats.get('companies_total', 0):,} returned "
         f"successfully ({int(stats.get('fetch_success_rate', 0) * 100)}% of those "
         f"attempted, {int(stats.get('fetch_success_rate_registry', 0) * 100)}% of the "
         "full registry)"),
        ("Complete snapshots",
         f"{stats.get('snapshots_complete', 0):,} boards returned a provably complete "
         f"list; {partial} were capped by the ATS and so were not allowed to close "
         "any role this run"),
        ("Detection latency", lat),
        ("Median posting lifetime", lifetime),
        ("Quarantined boards", str(stats.get("quarantined", 0))),
        ("New this run", str(stats.get("new_this_run", 0))),
        ("Run duration", f"{stats.get('duration_seconds', 0)}s"),
    ]
    rows = "".join(
        f"<tr><th>{escape(k)}</th><td>{escape(v)}</td></tr>" for k, v in facts
    )
    return f"""
  <details class="engine" id="engine">
    <summary><strong>Engine health</strong> — how this list was actually built</summary>
    <div class="tscroll"><table class="kv">{rows}</table></div>
    <div class="panels">
      <div><h3>Roles by source</h3>{_bars(stats.get("roles_by_source", {}))}</div>
      <div><h3>Roles by class year</h3>{_bars(stats.get("roles_by_cycle", {}))}</div>
      <div><h3>Roles by category</h3>{_bars(by_category)}</div>
      <div><h3>Sponsorship verdicts</h3>{_bars(stats.get("sponsorship_counts", {}))}</div>
    </div>
    {_sparkline(history)}
  </details>
"""


def _bars(counter: dict) -> str:
    if not counter:
        return "<p class='muted'>none</p>"
    top = max(counter.values())
    rows = []
    for name, n in sorted(counter.items(), key=lambda kv: -kv[1]):
        pct = int(n / top * 100) if top else 0
        rows.append(
            f'<div class="bar"><span class="bname">{escape(str(name))}</span>'
            f'<span class="btrack"><span class="bfill" style="width:{pct}%"></span></span>'
            f'<span class="bval">{n}</span></div>'
        )
    return "".join(rows)


def _history_points(limit: int = 120) -> list[dict]:
    points = []
    try:
        with open(paths.HISTORY_PATH, encoding="utf-8") as f:
            for line in f.read().splitlines()[-limit:]:
                try:
                    points.append(json.loads(line))
                except ValueError:
                    continue
    except OSError:
        pass
    return points


def _sparkline(points: list[dict]) -> str:
    """Inline SVG of open-role count across recent runs. No JS, no deps."""
    values = [p.get("open", 0) for p in points]
    if len(values) < 2:
        return "<p class='muted'>History chart appears after a few more runs.</p>"
    w, h, pad = 640, 80, 4
    lo, hi = min(values), max(values)
    span = (hi - lo) or 1
    step = (w - 2 * pad) / (len(values) - 1)
    coords = [
        f"{pad + i * step:.1f},{h - pad - (v - lo) / span * (h - 2 * pad):.1f}"
        for i, v in enumerate(values)
    ]
    first_ts = (points[0].get("ts") or "")[:10]
    return (
        f'<svg viewBox="0 0 {w} {h}" preserveAspectRatio="none" class="spark" role="img" '
        f'aria-label="Open roles per run">'
        f'<polyline fill="none" stroke="var(--accent)" stroke-width="2" points="{" ".join(coords)}"/>'
        "</svg>"
        f'<p class="muted spark-caption">Open roles per run since {escape(first_ts)} — '
        f"now {values[-1]}, peak {hi}.</p>"
    )


_UI = Path(__file__).with_name("ui")


def _icon(name: str) -> str:
    """Vendored Bootstrap icons; embedded so Pages needs no external assets."""
    return (_UI / "icons" / f"{name}.svg").read_text(encoding="utf-8").replace(
        "<svg ", '<svg aria-hidden="true" focusable="false" '
    )


def _job_url(value: str) -> str:
    """Job feeds are external input: only ordinary web application links."""
    try:
        parsed = urlsplit(value)
        return value if parsed.scheme in {"https", "http"} and parsed.netloc else ""
    except ValueError:
        return ""


def _rows(open_jobs: list[dict]) -> str:
    rows = []
    bookmark, arrow = _icon("bookmark"), _icon("arrow-up-right")
    for r in open_jobs:
        company, title = r.get("company") or "", r.get("title") or ""
        location, salary = r.get("location") or "Location not stated", r.get("salary") or ""
        posted = (r.get("posted_at") or "")[:10]
        try:
            date_label = datetime.strptime(posted, "%Y-%m-%d").strftime("%b %d, %Y")
        except ValueError:
            date_label = "Not stated"
        url = _job_url(r.get("url") or "")
        role = (f'<a class="rt" href="{escape(url)}" target="_blank" rel="noopener">'
                f'{escape(title)}<span class="sr-only"> (opens employer site in a new tab)</span></a>'
                if url else f'<span class="rt">{escape(title)}</span>')
        apply = (f'<a class="apply" href="{escape(url)}" target="_blank" rel="noopener" '
                 f'aria-label="Apply for {escape(title)} at {escape(company)} (opens in a new tab)">'
                 f'Apply {arrow}</a>' if url else '<span class="muted">Link unavailable</span>')
        jid = r.get("id") or ""
        save = (f'<button class="star" type="button" data-id="{escape(jid)}" '
                f'aria-pressed="false" aria-label="Save {escape(title)} at {escape(company)}">'
                f'{bookmark}<span class="save-label">Save</span></button>')
        seasons = r.get("seasons") or [r.get("season", "")]
        year = "Not stated" if r.get("season_inferred") else " · ".join(seasons)
        sponsor = r.get("sponsorship", "unknown")
        sponsor_text = {
            "offers": "Posting offers sponsorship",
            "no-sponsorship": "Posting restricts sponsorship",
            "citizens-only": "Posting requires citizenship",
        }.get(sponsor, "")
        proven = "1" if h1b.badge(h1b.approvals_for(company)) else "0"
        skills = [v for v in (r.get("skills") or []) if v][:6]
        metadata = " · ".join(skills)
        if sponsor_text:
            metadata = " · ".join(filter(None, [metadata, sponsor_text]))
        openings = r.get("openings") or 1
        extra = ""
        if openings > 1:
            links = "".join(
                f'<a href="{escape(u)}" target="_blank" rel="noopener">Opening {i + 2}'
                '<span class="sr-only"> (opens in a new tab)</span></a>'
                for i, raw in enumerate(r.get("opening_urls") or [])
                if (u := _job_url(raw))
            )
            extra = (f'<details class="opening-links"><summary>{openings} openings</summary>'
                     f'<p class="muted">Apply opens the first listing. Other applications:</p>{links}</details>')
        haystack = " ".join([company, title, location, r.get("category") or "", year, salary] + skills).lower()
        export = [company, title, year, r.get("category") or "", location, salary, posted, url]
        urls = [u for raw in [url, *(r.get("opening_urls") or [])] if (u := _job_url(raw))]
        rows.append(
            f'<tr data-id="{escape(jid)}" '
            f'data-cycle="{escape(r.get("season", ""))}" '
            f'data-cycles="{escape("|".join(seasons))}" '
            f'data-category="{escape(r.get("category", ""))}" '
            f'data-company="{escape(company)}" data-title="{escape(title)}" '
            f'data-sponsor="{escape(sponsor)}" data-h1b="{proven}" '
            f'data-remote="{int(filters.is_remote(location, title))}" '
            f'data-program="{escape(filters.program_type(title))}" '
            f'data-posted="{escape(posted)}" '
            f'data-inferred="{int(bool(r.get("season_inferred")))}" '
            f'data-openings="{openings}" '
            f'data-ids="{escape("|".join(r.get("opening_ids") or [jid]))}" '
            f'data-export="{escape(json.dumps(export))}" data-urls="{escape(json.dumps(urls))}" '
            f'data-text="{escape(haystack)}">'
            f'<td class="job-main">{role}<div class="company">{escape(company)}'
            f' <span class="location">{escape(location)}</span></div>'
            f'<div class="skills">{escape(metadata)}</div>{extra}</td>'
            f'<td class="job-facts"><span class="field-label">Class year</span>{escape(year)}'
            + (f'<span class="salary"><span class="field-label">Pay</span>{escape(salary)}</span>' if salary else '')
            + f'</td><td class="job-date"><span class="field-label">Posted</span>'
            f'<time datetime="{escape(posted)}">{escape(date_label)}</time></td>'
            f'<td class="job-actions">{save}{apply}</td></tr>'
        )
    return "".join(rows)


def _options(values: list[str]) -> str:
    return "".join(f'<option value="{escape(v)}">{escape(v)}</option>' for v in values)


_CF_TITLE = {
    "verified": "The employer's own posted date, read from their careers API. We may have discovered the role after it went live — the date is theirs, not our discovery time.",
    "window": "Hand-verified typical opening month for this company (month-level, not a promise of the day).",
    "rolling": "This company posts year-round / on a rolling basis — worth checking anytime.",
}


def _radar_rows(rows: list[dict]) -> str:
    out = []
    for r in rows:
        url = _job_url(r.get("url") or "")
        if r["status"] == "open":
            status = (f'<a href="{escape(url)}" target="_blank" rel="noopener">open now</a>'
                      if url else "open now")
        elif r["status"] == "dropped":
            status = '<span class="muted">dropped</span>'
        else:
            status = '<span class="muted">waiting</span>'
        conf = r.get("confidence", "estimated")
        cf = (f'<span class="cf cf-{conf}" title="{escape(_CF_TITLE.get(conf, ""))}">'
              f'{escape(radar.confidence_note(r))}</span>')
        out.append(
            f'<tr data-text="{escape(r["company"].lower())}">'
            f"<td>{escape(r['company'])}</td>"
            f"<td>{escape(radar.pretty_last(r))}</td>"
            f"<td>{escape(radar.pretty_expected(r))}</td>"
            f"<td>{cf}</td>"
            f"<td>{status}</td></tr>"
        )
    return "".join(out)


def _radar_section(store_data: dict, cfg: dict, data_as_of: datetime | None = None) -> str:
    cycle = config.cycles(cfg)[0]
    rows = radar.rows(store_data, cycle, today=data_as_of.date() if data_as_of else None)
    if not rows:
        return ""
    return f"""
  <h2 id="radar">Drop Radar — when companies usually open new grad hiring
    (<span id="rcount">{len(rows)}</span>)</h2>
  <p class="muted" style="margin:0 0 8px">When each company usually opens — every
  date either read from the employer's own API or hand-checked.
  <span class="cf cf-verified">from the API</span> = the employer's own
  posted date, read from their careers API; <span class="cf cf-window">typical window</span> =
  hand-checked opening month for a marquee name;
  <span class="cf cf-rolling">rolling</span> = posts year-round.
  "waiting" = not seen in our tracked feeds yet.</p>
  <p style="margin:0 0 10px"><a href="radar.ics" class="ics">Subscribe in your
    calendar</a> <span class="muted" style="font-size:12px">— add every expected
    drop date to Google/Apple Calendar and get a reminder a week before.</span></p>
  <div class="radar-search"><label for="rq">Search hiring calendar</label><input id="rq" type="search"
    placeholder="Search the radar — is your target company on it?" autocomplete="off"></div>
  <div class="tscroll">
  <table><thead><tr><th>Company</th><th>Typical opening</th><th>Expected</th>
  <th>Confidence</th><th>Status</th>
  </tr></thead><tbody id="rrows">{_radar_rows(rows)}</tbody></table>
  </div>
"""


def _signup_section(cfg: dict) -> str:
    """Privacy-preserving double-opt-in request through a narrow RPC."""
    endpoint = config.signup_endpoint(cfg)
    if not endpoint:
        return ""
    url, key = endpoint
    return f"""
  <div class="signup" id="subscribe">
    <h2>Daily email alerts</h2>
    <p class="muted" style="margin:4px 0 10px">One email a day, only when new
    grad roles actually appeared. Confirm by email first; address never shared.</p>
    <form id="subform">
      <label class="sr-only" for="subemail">Email address</label>
      <input id="subemail" type="email" required placeholder="you@school.edu" autocomplete="email">
      <button type="submit">Subscribe</button>
    </form>
    <p id="submsg" class="muted" role="status"></p>
  </div>
<script>
(function () {{
  var form = document.getElementById('subform'), email = document.getElementById('subemail'),
      msg = document.getElementById('submsg');
  form.addEventListener('submit', function (ev) {{
    ev.preventDefault();
    msg.textContent = 'Subscribing…';
    fetch({json.dumps(url)} + '/rest/v1/rpc/request_email_subscription', {{
      method: 'POST',
      headers: {{ 'apikey': {json.dumps(key)}, 'Content-Type': 'application/json' }},
      body: JSON.stringify({{ address: email.value.trim().toLowerCase() }})
    }}).then(function (r) {{
      if (r.ok) {{ msg.textContent = 'Check your inbox. If that address can subscribe, a confirmation link is on its way.'; form.reset(); }}
      else {{ msg.textContent = 'Hmm, that did not work — try again in a minute.'; }}
    }}).catch(function () {{ msg.textContent = 'Network error — try again in a minute.'; }});
  }});
}})();
</script>"""


def generate(store_data: dict, stats: dict) -> None:
    open_jobs = [r for r in store_data.values() if r.get("is_open")]
    open_jobs.sort(
        key=lambda r: ((r.get("posted_at") or "")[:10], (r.get("first_seen_at") or "")),
        reverse=True,
    )
    # One row per job, not per requisition. `open_jobs` stays the full list —
    # every count on this page is still a count of real openings — but the
    # table shows an employer's eight identical Dallas reqs as one row saying
    # "8 openings" instead of eight rows a reader has to scroll past.
    display_jobs = sorted(grouping.group(open_jobs),
                          key=lambda r: r.get("posted_at") or "", reverse=True)
    cfg = config.load_config()
    try:
        data_as_of_dt = datetime.strptime(
            (stats.get("fetched_at") or stats.get("generated_at") or "")[:19],
            "%Y-%m-%dT%H:%M:%S",
        ).replace(tzinfo=UTC)
    except ValueError:
        data_as_of_dt = datetime.now(UTC)
    data_as_of = data_as_of_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    updated = data_as_of_dt.strftime("%b %d, %Y at %H:%M UTC")
    if config.include_international(cfg):
        region = "US + International"
    elif config.want_us(cfg) and config.want_canada(cfg):
        region = "United States & Canada"
    elif config.want_us(cfg):
        region = "United States"
    elif config.want_canada(cfg):
        region = "Canada"
    else:
        region = "Worldwide"

    # Real class years first, "Not stated" pinned last — it's the absence of
    # a class year, so alphabetical order (which would sort it among the
    # "Class of" labels) would read as if it were one.
    cycles = sorted(
        {r.get("season", "") for r in open_jobs if r.get("season")},
        key=lambda s: (s == filters.NOT_STATED, s),
    )
    categories = sorted({r.get("category", "") for r in open_jobs if r.get("category")})
    repo = config.repo_slug()
    by_category: dict[str, int] = {}
    for r in open_jobs:
        cat = r.get("category") or "Other"
        by_category[cat] = by_category.get(cat, 0) + 1

    html_doc = f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>New Grad Tech Jobs - Live Dashboard</title>
<meta name="description" content="{escape(' & '.join(config.cycles(cfg)))} new grad tech jobs, refreshed every 30 minutes. Auto-detected visa sponsorship flags, proven H-1B sponsor badges, email alerts.">
<meta property="og:title" content="New Grad Tech Jobs - Live Dashboard">
<meta property="og:description" content="{len(open_jobs)} open new grad tech jobs, refreshed every 30 minutes. Visa-sponsorship flags + proven H-1B sponsor badges for international students.">
<meta property="og:type" content="website">
<meta name="twitter:card" content="summary">
<link rel="alternate" type="application/atom+xml" title="New grad roles" href="feed.xml">
<style>{(_UI / "dashboard.css").read_text(encoding="utf-8")}</style></head><body data-as-of="{escape(data_as_of)}">
<a class="skip" href="#roles">Skip to jobs</a>
<div class="wrap">
  <header class="top">
    <a class="brand" href="./">New Grad Tech Jobs</a>
    <nav aria-label="Main navigation">
      <a href="#roles" id="browse-nav" aria-current="page">Browse</a>
      <a href="#roles" id="saved-nav">Saved <span id="savedn">0</span></a>
    </nav>
    <a class="source-link" href="https://github.com/{escape(repo)}">GitHub</a>
  </header>
  <main>
  <section class="intro" aria-labelledby="intro-title">
    <h1 id="intro-title">Find your first role<span>.</span></h1>
    <p>{escape(region)} new grad and early career tech roles, straight from employers.</p>
    <p class="freshness">Data as of {escape(updated)} · {stats.get('companies_total', 0):,} boards tracked</p>
  </section>
  <section aria-label="Find jobs">
  <form class="filters" id="filters" role="search">
    <div class="primary-filters">
      <label class="search-field" for="q">Search roles, companies or skills
        <input id="q" type="search" placeholder="e.g. software engineer, Python, Stripe" autocomplete="off">
      </label>
      <label for="cycle">Class year
        <select id="cycle"><option value="">All class years</option>{_options(cycles)}</select>
      </label>
      <label for="cat">Category
        <select id="cat"><option value="">All categories</option>{_options(categories)}</select>
      </label>
      <button id="more-toggle" type="button" aria-expanded="false" aria-controls="more-filters">More filters <span id="filter-n"></span></button>
    </div>
    <div id="more-filters" class="fbody" hidden>
      <label for="age">Posted
        <select id="age"><option value="">Anytime</option><option value="2">Last 48 hours</option>
        <option value="7">Last 7 days</option><option value="30">Last 30 days</option></select>
      </label>
      <label for="spon">Sponsorship in posting
        <select id="spon"><option value="">Any status</option>
        <option value="no-restriction">No explicit restriction found</option>
        <option value="offers">Explicitly offers sponsorship</option>
        <option value="unknown">Not stated</option><option value="restricted">Explicitly restricted</option></select>
      </label>
      <label for="program">Program type
        <select id="program"><option value="">All programs</option>
        <option>New Grad</option><option>Early Career</option><option>Entry Level</option>
        <option>Rotational</option><option>Junior / Associate</option></select>
      </label>
      <label class="chk"><input id="remote" type="checkbox">Remote only</label>
      <label class="chk"><input id="h1b" type="checkbox">Past H-1B sponsors</label>
      <label class="chk"><input id="stated" type="checkbox">Employer-stated class year only</label>
      <p class="filter-help">“Not stated” means the employer hasn’t named a class year.
        H-1B history does not guarantee sponsorship for a particular role.</p>
    </div>
  </form>
  <div class="results-heading" id="roles" tabindex="-1">
    <h2><span id="count">{len(open_jobs)}</span> <span id="result-label">openings</span></h2>
    <div class="results-tools">
      <button id="reset" class="text-button" type="button" hidden>Clear filters</button>
      <label class="sr-only" for="sort">Sort jobs</label>
      <select id="sort"><option value="newest">Newest first</option><option value="company">Company A–Z</option><option value="oldest">Oldest first</option></select>
    </div>
  </div>
  <p class="sr-only" id="result-status" role="status" aria-live="polite"></p>
  <p class="saved-note" id="saved-note" hidden>Your shortlist is saved on this browser.
    Filters also apply to saved jobs. <button class="text-button" id="export" type="button">Export saved as CSV</button></p>
  <noscript><p>All jobs and application links are available below. Enable JavaScript to search, filter, or save roles.</p></noscript>
  <table class="job-list" aria-label="Job openings">
    <thead class="sr-only"><tr><th>Role and company</th><th>Class year and pay</th><th>Posted</th><th>Actions</th></tr></thead>
    <tbody id="rows">{_rows(display_jobs)}</tbody>
  </table>
  <div id="empty" class="empty" hidden><h3 id="empty-title">No roles match those filters.</h3>
    <p id="empty-help">Try a broader search or remove a filter.</p>
    <button type="button" id="reset2">Clear filters</button></div>
  <div class="list-footer"><p>Save roles to build your shortlist. Saved on this browser, no account needed.</p>
    <a href="#roles">Back to jobs</a></div>
  <p id="storage-status" class="muted" role="status"></p>
  </section>
  <details class="resources"><summary>Hiring calendar &amp; data</summary>
  {_signup_section(cfg)}
  {_radar_section(store_data, cfg, data_as_of_dt)}

  <h2>Roles posted per week</h2>
  <p class="muted" style="margin:0 0 8px">Real published dates across every role the
  engine has tracked — watch this spike when {escape(config.cycles(cfg)[0])}
  hiring opens up.</p>
  {trends.svg_bar_chart(trends.weekly_postings(store_data, now=data_as_of_dt))}

  {_engine_panel(stats, by_category, _history_points())}

  </details>
  </main>
  <footer>
  <nav class="footer-links" aria-label="Resources"><a href="feed.xml">RSS feed</a>
  <a href="new_grad_jobs.csv">Download all jobs</a><a href="api/jobs.json">JSON API</a>
  <a href="https://github.com/{escape(repo)}/blob/main/METHODOLOGY.md">How we find jobs</a>
  <a href="https://apoorv.dev">Made by Apoorv</a></nav>
  <p>Generated by the engine on each run across
  {len(stats.get("companies_by_source", {}))} ATS platforms. Sponsorship flags are
  auto-detected from posting text — treat them as a strong hint and verify on the
  posting itself. The past H-1B sponsor filter identifies employers with {h1b.BADGE_THRESHOLD}+ H-1B petitions
  ({escape(h1b.window_label() or "recent years")}, per the public
  <a href="https://www.uscis.gov/tools/reports-and-studies/h-1b-employer-data-hub">
  Employer Data Hub</a>). This is a history, not a promise of sponsorship for a role. Roles can close at any time; always confirm on the company's own site.</p></footer>
</div>
<script>{(_UI / "dashboard.js").read_text(encoding="utf-8")}</script>
</body></html>"""

    os.makedirs(paths.DOCS_DIR, exist_ok=True)
    with open(paths.DASHBOARD_PATH, "w", encoding="utf-8") as f:
        f.write(html_doc)

    _write_unsubscribe(cfg)
    _write_confirmation(cfg)


def _write_unsubscribe(cfg: dict) -> None:
    """Unsubscribe target for digest emails (?t=<secret token>).

    Calls the security-definer RPC in Supabase: the token is the only
    credential, so the page needs nothing but the public key.

    The RPC fires on a CLICK, never on page load. Corporate mail security
    scanners fetch every link in an incoming email to check it — a page that
    unsubscribed on load meant those subscribers were silently removed by their
    own employer's spam filter, having never opened the mail. Requiring a real
    click is what keeps an automated fetch from being a destructive action.
    """
    endpoint = config.signup_endpoint(cfg)
    if not endpoint:
        return
    url, key = endpoint
    page = f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Unsubscribe - New Grad Tech Jobs</title>
<style>
  body {{ margin:0; background:#0d1117; color:#e6edf3;
          font:16px/1.6 -apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif; }}
  .box {{ max-width:520px; margin:18vh auto 0; padding:32px 24px; background:#161b22;
          border:1px solid #30363d; border-radius:12px; text-align:center; }}
  a {{ color:#2f81f7; }}
  button {{ background:#2f81f7; color:#fff; border:0; border-radius:8px;
            padding:11px 22px; font-size:15px; font-weight:600; cursor:pointer;
            margin-top:8px; }}
  button:hover {{ filter:brightness(1.1); }}
  button[disabled] {{ opacity:.6; cursor:default; }}
</style></head><body>
<div class="box">
  <h1 id="h">Unsubscribe?</h1>
  <p id="p">Confirm below and you'll stop receiving the daily digest.</p>
  <button id="go">Yes, unsubscribe me</button>
</div>
<script>
(function () {{
  var h = document.getElementById('h'), p = document.getElementById('p'),
      go = document.getElementById('go');
  var token = new URLSearchParams(location.search).get('t');
  if (!token) {{
    h.textContent = 'Missing link token';
    p.textContent = 'Use the unsubscribe link from one of our emails.';
    go.style.display = 'none';
    return;
  }}
  // Deliberately click-gated: mail security scanners fetch every link in an
  // email, and unsubscribing on page load let those scanners remove real
  // subscribers who never even opened the message.
  go.addEventListener('click', function () {{
    go.disabled = true;
    h.textContent = 'Unsubscribing…';
    p.textContent = 'One moment.';
    fetch({json.dumps(url)} + '/rest/v1/rpc/unsubscribe_email', {{
      method: 'POST',
      headers: {{ 'apikey': {json.dumps(key)}, 'Content-Type': 'application/json' }},
      body: JSON.stringify({{ token: token }})
    }}).then(function (r) {{
      go.style.display = 'none';
      if (r.ok) {{
        h.textContent = "You're unsubscribed";
        p.textContent = 'No more emails. You can re-subscribe on the dashboard anytime.';
      }} else {{
        h.textContent = 'Something went wrong';
        p.textContent = 'Try the link again in a minute.';
        go.style.display = ''; go.disabled = false;
      }}
    }}).catch(function () {{
      h.textContent = 'Network error';
      p.textContent = 'Try the link again in a minute.';
      go.disabled = false;
    }});
  }});
}})();
</script>
</body></html>"""
    with open(os.path.join(paths.DOCS_DIR, "unsubscribe.html"), "w", encoding="utf-8") as f:
        f.write(page)


def _write_confirmation(cfg: dict) -> None:
    """Click-gated double-opt-in target; scanners cannot confirm on page load."""
    endpoint = config.signup_endpoint(cfg)
    if not endpoint:
        return
    url, key = endpoint
    page = f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Confirm email alerts - New Grad Tech Jobs</title>
<style>
  body {{ margin:0; background:#0d1117; color:#e6edf3;
          font:16px/1.6 -apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif; }}
  .box {{ max-width:520px; margin:18vh auto 0; padding:32px 24px; background:#161b22;
          border:1px solid #30363d; border-radius:12px; text-align:center; }}
  button {{ background:#2f81f7; color:#fff; border:0; border-radius:8px;
            padding:11px 22px; font-size:15px; font-weight:600; cursor:pointer; }}
  button[disabled] {{ opacity:.6; cursor:default; }}
</style></head><body><div class="box">
  <h1 id="h">Confirm email alerts?</h1>
  <p id="p">Confirm below to join the daily new grad roles digest.</p>
  <button id="go">Confirm my email</button>
</div><script>
(function () {{
  var h=document.getElementById('h'), p=document.getElementById('p'),
      go=document.getElementById('go'), token=new URLSearchParams(location.search).get('t');
  if (!token) {{ h.textContent='Missing link token'; p.textContent='Use the link from your confirmation email.'; go.style.display='none'; return; }}
  go.addEventListener('click', function () {{
    go.disabled=true; h.textContent='Confirming…'; p.textContent='One moment.';
    fetch({json.dumps(url)} + '/rest/v1/rpc/confirm_email_subscription', {{
      method:'POST', headers:{{'apikey':{json.dumps(key)},'Content-Type':'application/json'}},
      body:JSON.stringify({{token:token}})
    }}).then(function (r) {{
      if (!r.ok) throw new Error('confirm failed');
      h.textContent="You're subscribed"; p.textContent='Your first digest arrives with the next batch of new roles.'; go.style.display='none';
    }}).catch(function () {{ h.textContent='Something went wrong'; p.textContent='Try the link again in a minute.'; go.disabled=false; }});
  }});
}})();
</script></body></html>"""
    with open(os.path.join(paths.DOCS_DIR, "confirm.html"), "w", encoding="utf-8") as f:
        f.write(page)
