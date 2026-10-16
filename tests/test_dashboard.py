"""Static dashboard contracts for freshness, saves, and double opt-in."""

from grad_engine import config, dashboard, paths


def test_dashboard_uses_fetch_time_and_prunes_ghost_saves(monkeypatch):
    # The signup form only renders when Supabase public keys are configured.
    # They live in data/config.json in production; the test supplies its own so
    # the contract holds regardless of what the committed config carries.
    cfg = {
        **config.load_config(),
        "supabase_url": "https://test.supabase.co",
        "supabase_publishable_key": "sb_publishable_test",
    }
    monkeypatch.setattr(config, "load_config", lambda: cfg)
    store = {
        "a": {
            "id": "a", "company": "Acme", "title": "SWE New Grad",
            "season": "Class of 2027", "seasons": ["Class of 2027"],
            "season_inferred": False, "category": "Software",
            "location": "Austin, TX", "url": "https://x/1", "is_open": True,
            "posted_at": "2026-08-05T00:00:00Z",
            "first_seen_at": "2026-08-05T01:00:00Z",
            "sponsorship": "unknown", "skills": [], "source": "greenhouse",
        }
    }
    stats = {
        "generated_at": "2026-08-06T14:08:27Z", "companies_total": 1,
        "companies_by_source": {"greenhouse": 1}, "open_total": 1,
    }
    dashboard.generate(store, stats)
    html = open(paths.DASHBOARD_PATH, encoding="utf-8").read()
    assert "Data as of Aug 06, 2026 at 14:08 UTC" in html
    assert "if (!currentIds[id]) delete saved[id]" in html
    assert "/rest/v1/rpc/request_email_subscription" in html
    confirm = open(f"{paths.DOCS_DIR}/confirm.html", encoding="utf-8").read()
    assert "/rest/v1/rpc/confirm_email_subscription" in confirm
    assert "go.addEventListener('click'" in confirm


def _opening(jid, **extra):
    rec = {
        "id": jid, "company": "Copart", "title": "Software Engineer I",
        "season": "Class of 2027", "seasons": ["Class of 2027"],
        "season_inferred": False, "category": "Software",
        "location": "Dallas, TX - Headquarters", "url": f"https://x/{jid}",
        "is_open": True, "posted_at": "2026-08-05T00:00:00Z",
        "first_seen_at": "2026-08-05T01:00:00Z",
        "sponsorship": "unknown", "skills": [], "source": "workday",
    }
    rec.update(extra)
    return rec


def _render(store):
    dashboard.generate(store, {
        "generated_at": "2026-08-07T21:35:57Z", "companies_total": 1,
        "companies_by_source": {"workday": 1}, "open_total": len(store),
    })
    return open(paths.DASHBOARD_PATH, encoding="utf-8").read()


def test_identical_requisitions_render_as_one_row():
    html = _render({str(i): _opening(str(i)) for i in range(8)})
    assert html.count("<tr data-id=") == 1
    assert "8 openings" in html


def test_a_grouped_row_still_links_every_requisition():
    html = _render({str(i): _opening(str(i)) for i in range(3)})
    for jid in ("0", "1", "2"):
        assert f"https://x/{jid}" in html


def test_a_grouped_row_carries_its_opening_count_for_the_filter_maths():
    # The visible count is a count of JOBS, so the filter script sums this
    # attribute rather than counting rows.
    html = _render({str(i): _opening(str(i)) for i in range(3)})
    assert 'data-openings="3"' in html
    assert "parseInt(tr.dataset.openings || '1', 10)" in html


def test_distinct_roles_are_not_folded_together():
    html = _render({
        "a": _opening("a"),
        "b": _opening("b", title="Database Engineer I"),
    })
    assert html.count("<tr data-id=") == 2
    assert '<details class="opening-links">' not in html


def test_a_star_on_an_absorbed_requisition_moves_to_the_surviving_row():
    # Folding three rows into one must not delete a reader's saved role. The
    # pruning step ("remove ids no longer in the artifact") would have done
    # exactly that to any sibling id, silently.
    html = _render({str(i): _opening(str(i)) for i in range(3)})
    assert 'data-ids="0|1|2"' in html
    assert "if (saved[ids[i]]) { saved[tr.dataset.id] = saved[ids[i]]; break; }" in html
    # And every one of those ids still counts as present.
    assert "ids.forEach(function (id) { currentIds[id] = true; });" in html


def test_every_grouped_application_is_reachable_even_with_more_than_seven_openings():
    from html.parser import HTMLParser

    class Links(HTMLParser):
        def __init__(self):
            super().__init__()
            self.links = []

        def handle_starttag(self, tag, attrs):
            if tag == "a":
                self.links.append(dict(attrs))

    html = _render({str(i): _opening(str(i)) for i in range(12)})
    parser = Links()
    parser.feed(html)
    for i in range(12):
        matches = [a for a in parser.links if a.get("href") == f"https://x/{i}"]
        assert matches
        assert all(a.get("target") == "_blank" and "noopener" in a.get("rel", "")
                   for a in matches)
    assert 'class="rt" href="https://x/0"' in html
    assert 'class="apply" href="https://x/0"' in html


def test_dashboard_keeps_complete_location_salary_and_export_fields():
    import json
    from html.parser import HTMLParser

    class Rows(HTMLParser):
        def __init__(self):
            super().__init__()
            self.records = []

        def handle_starttag(self, tag, attrs):
            attrs = dict(attrs)
            if tag == "tr" and "data-export" in attrs:
                self.records.append(attrs)

    location = "San Francisco, California; New York, New York; Austin, Texas"
    salary = "$100,000–$150,000 per year plus equity and annual bonus"
    url = 'https://example.com/apply?job=12&source=board'
    html = _render({"a": _opening("a", company='A & B', location=location,
                                  salary=salary, url=url)})
    parser = Rows()
    parser.feed(html)
    record = json.loads(parser.records[0]["data-export"])
    assert record == ['A & B', 'Software Engineer I', 'Class of 2027', 'Software',
                      location, salary, '2026-08-05', url]
    assert json.loads(parser.records[0]["data-urls"]) == [url]
    assert location in html and salary in html


def test_dashboard_rejects_executable_job_urls_and_escapes_feed_text():
    html = _render({"a": _opening("a", title='<script>alert(1)</script>',
                                  url='javascript:alert(1)')})
    assert 'href="javascript:' not in html
    assert '<script>alert(1)</script>' not in html
    assert 'Link unavailable' in html


def test_newest_first_orders_grouped_rows_by_the_date_shown():
    html = _render({
        'a': _opening('a', posted_at='2026-08-01T00:00:00Z'),
        'b': _opening('b', posted_at='2026-08-06T00:00:00Z'),
        'c': _opening('c', title='Another role', posted_at='2026-08-04T00:00:00Z'),
    })
    assert html.index('<tr data-id="c"') < html.index('<tr data-id="a"')
