"""Eightfold PCSX search: paging, rate limits, field mapping, 403 fallback.

Payloads come from tests/fixtures/eightfold_pcsx.json, trimmed from live
Qualcomm and Microsoft responses.
"""

import asyncio
import copy
import json
import os

import httpx
import pytest

from grad_engine import enrich, filters, net, pipeline
from grad_engine.connectors import eightfold
from grad_engine.models import INCOMPLETE_CAPPED, INCOMPLETE_MALFORMED, Fetch, Job

with open(os.path.join(os.path.dirname(__file__), "fixtures", "eightfold_pcsx.json")) as f:
    FIXTURE = json.load(f)

QUALCOMM = {"name": "Qualcomm", "slug": "qualcomm", "ats": "eightfold",
            "host": "careers.qualcomm.com", "domain": "qualcomm.com",
            "filters": {"seniority": "Entry"}}
NETFLIX = {"name": "Netflix", "slug": "netflix", "ats": "eightfold", "api": "v2",
           "host": "explore.jobs.netflix.net", "domain": "netflix.com"}


@pytest.fixture(autouse=True)
def _no_page_gap(monkeypatch):
    monkeypatch.setattr(eightfold, "_PCSX_PAGE_GAP", 0)


def _position(i: int) -> dict:
    p = copy.deepcopy(FIXTURE["page"]["data"]["positions"][1])
    p["id"] = 1000 + i
    p["positionUrl"] = f"/careers/job/{1000 + i}"
    p["name"] = f"Software Engineer {i}"
    return p


def _page(positions: list[dict], count: int | None) -> dict:
    page = copy.deepcopy(FIXTURE["page"])
    page["data"]["positions"] = positions
    if count is None:
        page["data"].pop("count")
    else:
        page["data"]["count"] = count
    return page


def _status_error(url: str, status: int) -> httpx.HTTPStatusError:
    request = httpx.Request("GET", url)
    response = httpx.Response(status, request=request)
    return httpx.HTTPStatusError(f"{status}", request=request, response=response)


class ScriptedNet:
    """Answers each GET from `route(url, params)`; records every call."""

    def __init__(self, route):
        self.route = route
        self.calls: list[tuple[str, dict]] = []

    async def get_json(self, url, params=None, **kwargs):
        self.calls.append((url, dict(params or {}), kwargs))
        answer = self.route(url, params or {})
        if isinstance(answer, Exception):
            raise answer
        return answer


def _run(coro) -> Fetch:
    return Fetch.of(asyncio.run(coro))


class TestPagination:
    def test_pages_until_a_short_page_and_sends_the_facet_filter(self):
        rows = [_position(i) for i in range(23)]

        def route(url, params):
            start = params["start"]
            return _page(rows[start:start + 10], count=None)

        fake = ScriptedNet(route)
        result = _run(eightfold.fetch(QUALCOMM, fake))

        assert len(result.jobs) == 23
        assert result.complete is True
        assert [p["start"] for _, p, _ in fake.calls] == [0, 10, 20]
        url, params, kwargs = fake.calls[0]
        assert url == "https://careers.qualcomm.com/api/pcsx/search"
        assert params["filter_seniority"] == "Entry"
        assert params["query"] == ""  # the facet narrows; no keyword needed
        assert params["location"] == "United States"
        assert params["domain"] == "qualcomm.com"
        assert kwargs["retries"] == eightfold._PCSX_RETRIES

    def test_full_last_page_is_complete_when_the_total_says_so(self):
        rows = [_position(i) for i in range(20)]
        fake = ScriptedNet(lambda url, p: _page(rows[p["start"]:p["start"] + 10], count=20))
        result = _run(eightfold.fetch(QUALCOMM, fake))
        assert len(result.jobs) == 20 and result.complete is True
        assert len(fake.calls) == 2  # no wasted request for an empty third page

    def test_full_page_without_a_total_keeps_paging(self):
        rows = [_position(i) for i in range(10)]
        fake = ScriptedNet(lambda url, p: _page(rows[p["start"]:p["start"] + 10], count=None))
        result = _run(eightfold.fetch(QUALCOMM, fake))
        assert len(fake.calls) == 2 and result.complete is True

    def test_page_cap_marks_the_snapshot_incomplete(self, monkeypatch):
        monkeypatch.setattr(eightfold, "_PCSX_MAX_PAGES", 2)
        fake = ScriptedNet(lambda url, p: _page(
            [_position(p["start"] + i) for i in range(10)], count=500))
        result = _run(eightfold.fetch(QUALCOMM, fake))
        assert len(result.jobs) == 20
        assert result.complete is False
        assert result.incomplete_reason == INCOMPLETE_CAPPED

    def test_a_row_repeated_across_pages_is_kept_once(self):
        # A role posted mid-run pushes page 1's last row onto page 2.
        first = [_position(i) for i in range(10)]
        second = [_position(9), _position(10)]
        fake = ScriptedNet(lambda url, p: _page(first if p["start"] == 0 else second, None))
        result = _run(eightfold.fetch(QUALCOMM, fake))
        assert [j.id for j in result.jobs].count("eightfold:qualcomm:1009") == 1
        assert len(result.jobs) == 11

    def test_no_facet_falls_back_to_keyword_search(self):
        company = {k: v for k, v in QUALCOMM.items() if k != "filters"}
        fake = ScriptedNet(lambda url, p: _page([], count=0))
        _run(eightfold.fetch(company, fake))
        params = fake.calls[0][1]
        assert params["query"] == "new grad"
        assert not any(k.startswith("filter_") for k in params)


class TestFieldMapping:
    def test_real_records_map_to_jobs(self):
        fake = ScriptedNet(lambda url, p: FIXTURE["page"])
        result = _run(eightfold.fetch(QUALCOMM, fake))
        soc, microwave, india = result.jobs

        assert soc.id == "eightfold:qualcomm:446717848714"
        assert soc.source == "eightfold"
        assert soc.company == "Qualcomm"
        assert soc.title == "SoC Power Validation Engineer"
        assert soc.url == "https://careers.qualcomm.com/careers/job/446717848714"
        assert soc.posted_at == "2026-10-16T00:00:00Z"  # postedTs, not creationTs
        assert soc.description is None  # enrichment fetches the text
        assert soc.board_key == "eightfold:qualcomm"
        # US first, capped at four; Markham (listed first) falls off the end.
        assert soc.location == (
            "San Diego, California, United States of America; "
            "Austin, Texas, United States of America; "
            "Folsom, California, United States of America; "
            "Hillsboro, Oregon, United States of America"
        )
        assert microwave.posted_at == "2026-10-16T22:54:05Z"  # real clock time
        assert microwave.location == "United States, Washington, Redmond"

    def test_long_form_location_keeps_india_out_of_the_us(self):
        # The standardized "Bengaluru, KA, IN" reads as Indiana to our filter.
        assert filters.is_united_states("Bengaluru, KA, IN")
        india = _run(eightfold.fetch(QUALCOMM, ScriptedNet(lambda u, p: FIXTURE["page"]))).jobs[2]
        assert india.location == "Bangalore, India"
        assert not filters.is_united_states(india.location)

    def test_standardized_locations_are_the_fallback(self):
        row = _position(1)
        row.pop("locations")
        job = _run(eightfold.fetch(QUALCOMM, ScriptedNet(lambda u, p: _page([row], 1)))).jobs[0]
        assert job.location == "Redmond, WA, US"

    def test_uneven_commas_are_tidied(self):
        # Live John Deere value.
        row = _position(1)
        row["locations"] = ["Horicon, WI,Wisconsin,United States"]
        job = _run(eightfold.fetch(QUALCOMM, ScriptedNet(lambda u, p: _page([row], 1)))).jobs[0]
        assert job.location == "Horicon, WI, Wisconsin, United States"


class TestEmptyAndErrors:
    def test_empty_result_is_a_complete_empty_board(self):
        result = _run(eightfold.fetch(QUALCOMM, ScriptedNet(lambda u, p: _page([], 0))))
        assert result.jobs == [] and result.complete is True

    def test_error_message_in_a_200_is_malformed(self):
        page = _page([], 0)
        page["error"] = {"message": "Something went wrong", "body": ""}
        result = _run(eightfold.fetch(QUALCOMM, ScriptedNet(lambda u, p: page)))
        assert result.complete is False
        assert result.incomplete_reason == INCOMPLETE_MALFORMED

    def test_403_on_pcsx_falls_back_to_v2(self):
        v2 = {"count": 1, "positions": [{
            "id": 790316547536, "name": "Software Engineer (L4)",
            "locations": ["Los Gatos,California,United States of America"],
            "t_create": 1782086400,
            "canonicalPositionUrl": "https://explore.jobs.netflix.net/careers/job/790316547536",
            "job_description": "<p>Text</p>",
        }]}

        def route(url, params):
            if "/api/pcsx/" in url:
                return _status_error(url, 403)
            return v2

        company = {k: v for k, v in NETFLIX.items() if k != "api"}
        fake = ScriptedNet(route)
        result = _run(eightfold.fetch(company, fake))
        assert [c[0].rsplit("/api/", 1)[1] for c in fake.calls] == ["pcsx/search", "apply/v2/jobs"]
        assert result.complete is True and len(result.jobs) == 1

    def test_403_on_v2_falls_back_to_pcsx(self):
        def route(url, params):
            if "/api/apply/v2/" in url:
                return _status_error(url, 403)
            return FIXTURE["page"]

        result = _run(eightfold.fetch({**QUALCOMM, "api": "v2"}, ScriptedNet(route)))
        assert len(result.jobs) == 3

    def test_403_on_both_apis_is_a_recorded_error_not_an_empty_board(self):
        fake = ScriptedNet(lambda url, p: _status_error(url, 403))
        company, result, error = asyncio.run(pipeline._fetch_one(QUALCOMM, fake))
        assert result.jobs == [] and result.complete is False
        assert error is not None and "403" in error

    def test_other_http_errors_do_not_trigger_the_fallback(self):
        fake = ScriptedNet(lambda url, p: _status_error(url, 500))
        with pytest.raises(httpx.HTTPStatusError):
            asyncio.run(eightfold.fetch(QUALCOMM, fake))
        assert len(fake.calls) == 1


class TestRateLimit:
    """429s go through net.Net's retry loop, which the connector widens."""

    def _net(self, handler, monkeypatch):
        sleeps: list[float] = []

        async def fake_sleep(seconds):
            sleeps.append(seconds)

        monkeypatch.setattr(net.asyncio, "sleep", fake_sleep)
        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        return net.Net(client, net.HostLimiter(4)), sleeps

    def test_429_is_retried_with_backoff_then_succeeds(self, monkeypatch):
        hits = {"n": 0}

        def handler(request):
            hits["n"] += 1
            if hits["n"] <= 3:
                return httpx.Response(429, text=FIXTURE["rate_limited_body"])
            return httpx.Response(200, json=FIXTURE["page"])

        client_net, sleeps = self._net(handler, monkeypatch)
        result = _run(eightfold.fetch(QUALCOMM, client_net))
        assert len(result.jobs) == 3
        assert hits["n"] == 4
        # Exponential backoff with jitter: ~1s, ~2s, ~4s.
        assert [int(s) for s in sleeps] == [1, 2, 4]

    def test_retry_after_is_honoured(self, monkeypatch):
        hits = {"n": 0}

        def handler(request):
            hits["n"] += 1
            if hits["n"] == 1:
                return httpx.Response(429, headers={"Retry-After": "12"})
            return httpx.Response(200, json=FIXTURE["page"])

        client_net, sleeps = self._net(handler, monkeypatch)
        _run(eightfold.fetch(QUALCOMM, client_net))
        assert sleeps == [12.0]

    def test_persistent_429_gives_up_and_raises(self, monkeypatch):
        def handler(request):
            return httpx.Response(429, text=FIXTURE["rate_limited_body"])

        client_net, sleeps = self._net(handler, monkeypatch)
        with pytest.raises(httpx.HTTPStatusError):
            asyncio.run(eightfold.fetch(QUALCOMM, client_net))
        assert len(sleeps) == eightfold._PCSX_RETRIES


class TestEnrichDetails:
    def test_pcsx_row_gets_its_description_from_position_details(self):
        job = Job(id="eightfold:qualcomm:446721490545", source="eightfold",
                  company="Qualcomm", company_slug="qualcomm",
                  title="Software Engineer", location="San Diego, CA",
                  url="https://careers.qualcomm.com/careers/job/446721490545")
        fake = ScriptedNet(lambda url, p: FIXTURE["position_details"])
        enriched, fetched = asyncio.run(enrich.enrich_jobs([job], {}, fake))
        url, params, _ = fake.calls[0]
        assert url == "https://careers.qualcomm.com/api/pcsx/position_details"
        assert params["position_id"] == "446721490545"
        assert fetched == 1 and enriched == {job.id}
        assert "Qualcomm Technologies" in job.description
