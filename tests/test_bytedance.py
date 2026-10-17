"""TikTok / ByteDance connector tests, from trimmed real API responses (no network).

Fixtures were recorded from api.lifeattiktok.com on 2026-10-17:
  bytedance_filters.json  /config/job/filters, cut to two US cities and Munich
  bytedance_search.json   /search/job/posts, two campus graduate roles
"""

import asyncio
import copy
import json
import pathlib

import httpx
import pytest

from grad_engine import filters, pipeline
from grad_engine.connectors import bytedance
from grad_engine.models import INCOMPLETE_MALFORMED, INCOMPLETE_STALLED, Fetch

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
FILTERS = json.loads((FIXTURES / "bytedance_filters.json").read_text())
SEARCH = json.loads((FIXTURES / "bytedance_search.json").read_text())

TIKTOK = {"name": "TikTok", "slug": "tiktok", "ats": "bytedance", "brand": "tiktok"}
BYTEDANCE = {"name": "ByteDance", "slug": "bytedance", "ats": "bytedance", "brand": "bytedance"}


class RouteNet:
    """Answers the filters call with one payload and search calls from a queue."""

    def __init__(self, filters_payload, search_pages):
        self.filters_payload = filters_payload
        self.search_pages = list(search_pages)
        self.calls = []

    async def get_json(self, url, **kwargs):
        raise AssertionError("the connector only POSTs")

    async def post_json(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if url.endswith("/config/job/filters"):
            return self.filters_payload
        return self.search_pages.pop(0)

    def searches(self):
        return [kw["json"] for url, kw in self.calls if url.endswith("/search/job/posts")]


def _fetch(company, net) -> Fetch:
    return Fetch.of(asyncio.run(bytedance.fetch(company, net)))


def _page(posts, count):
    page = copy.deepcopy(SEARCH)
    page["data"]["job_post_list"] = posts
    page["data"]["count"] = count
    return page


def test_maps_every_field_from_a_real_response():
    result = _fetch(TIKTOK, RouteNet(FILTERS, [SEARCH]))

    assert result.complete is True
    first, second = result.jobs
    assert first.id == "bytedance:tiktok:7668206857737455877"
    assert first.source == "bytedance"
    assert first.company == "TikTok"
    assert first.title.startswith("Multimodal Generative AI Research Scientist")
    assert first.location == "Seattle, Washington, USA"
    assert first.url == "https://lifeattiktok.com/search/7668206857737455877"
    # No date field in the API: the id's top 32 bits are the creation second.
    assert first.posted_at == "2026-07-30T00:00:00Z"
    assert first.posted_at_source == "date_only"
    assert first.requisition_id == "A258115A"
    assert first.board_key == "bytedance:tiktok"
    assert "As a graduate" in first.description
    assert "Minimum Qualifications" in first.description
    assert second.location == "San Jose, California, USA"
    assert filters.is_united_states(second.location)


def test_asks_the_server_for_campus_graduate_roles_in_us_cities_only():
    net = RouteNet(FILTERS, [SEARCH])
    _fetch(TIKTOK, net)

    (body,) = net.searches()
    assert body["recruitment_id_list"] == ["201"]
    # San Jose and Seattle, not Munich.
    assert body["location_code_list"] == ["CT_1103355", "CT_157"]
    headers = net.calls[0][1]["headers"]
    assert headers["website-path"] == "tiktok"
    assert headers["origin"] == "https://lifeattiktok.com"


def test_bytedance_brand_uses_its_own_host_headers_and_links():
    net = RouteNet(FILTERS, [SEARCH])
    jobs = _fetch(BYTEDANCE, net).jobs

    url, kwargs = net.calls[0]
    assert url.startswith("https://jobs.bytedance.com/api/v1/public/supplier/")
    assert kwargs["headers"]["website-path"] == "en"
    assert kwargs["headers"]["origin"] == "https://joinbytedance.com"
    assert jobs[0].id.startswith("bytedance:bytedance:")
    assert jobs[0].url == "https://joinbytedance.com/search/7668206857737455877"


def test_unknown_brand_is_an_error_not_an_empty_board():
    with pytest.raises(ValueError):
        asyncio.run(bytedance.fetch({"slug": "lark", "brand": "lark"}, RouteNet(FILTERS, [])))


def test_paginates_until_the_server_count_is_reached(monkeypatch):
    monkeypatch.setattr(bytedance, "_PAGE_SIZE", 1)
    posts = SEARCH["data"]["job_post_list"]
    net = RouteNet(FILTERS, [_page(posts[:1], 2), _page(posts[1:], 2)])

    result = _fetch(TIKTOK, net)

    assert [b["offset"] for b in net.searches()] == [0, 1]
    assert [b["limit"] for b in net.searches()] == [1, 1]
    assert len(result.jobs) == 2
    assert result.complete is True


def test_hitting_the_page_cap_leaves_the_snapshot_incomplete(monkeypatch):
    monkeypatch.setattr(bytedance, "_PAGE_SIZE", 1)
    monkeypatch.setattr(bytedance, "_MAX_JOBS", 1)
    posts = SEARCH["data"]["job_post_list"]
    result = _fetch(TIKTOK, RouteNet(FILTERS, [_page(posts[:1], 2)]))
    assert len(result.jobs) == 1
    assert result.complete is False


def test_empty_page_short_of_the_count_is_a_stall():
    result = _fetch(TIKTOK, RouteNet(FILTERS, [_page([], 5)]))
    assert result.complete is False
    assert result.incomplete_reason == INCOMPLETE_STALLED


def test_empty_result_is_a_complete_empty_board():
    result = _fetch(TIKTOK, RouteNet(FILTERS, [_page([], 0)]))
    assert result.jobs == []
    assert result.complete is True


def test_error_envelope_is_malformed_not_empty():
    # The API's failure shape, still sent with HTTP 200.
    envelope = {"code": -9000002, "data": None, "message": "Server request failed"}
    result = _fetch(TIKTOK, RouteNet(FILTERS, [envelope]))
    assert result.jobs == []
    assert result.complete is False
    assert result.incomplete_reason == INCOMPLETE_MALFORMED


def test_no_us_cities_means_no_search_at_all():
    # An empty location list would search the whole world.
    no_us = copy.deepcopy(FILTERS)
    no_us["data"]["city_list"] = [
        c for c in no_us["data"]["city_list"] if c["code"] == "CT_226"
    ]
    net = RouteNet(no_us, [SEARCH])
    result = _fetch(TIKTOK, net)
    assert net.searches() == []
    assert result.complete is False
    assert result.incomplete_reason == INCOMPLETE_MALFORMED


def test_http_error_becomes_a_board_error_in_the_pipeline():
    class FailingNet(RouteNet):
        async def post_json(self, url, **kwargs):
            request = httpx.Request("POST", url)
            raise httpx.HTTPStatusError(
                "503", request=request, response=httpx.Response(503, request=request),
            )

    company, result, error = asyncio.run(
        pipeline._fetch_one(TIKTOK, FailingNet(FILTERS, []))
    )
    assert company is TIKTOK
    assert result.complete is False
    assert result.jobs == []
    assert error.startswith("HTTPStatusError")


def test_registered_with_the_pipeline_and_registry():
    from grad_engine import registry

    assert pipeline.CONNECTORS["bytedance"] is bytedance.fetch
    names = {c["name"]: c for c in registry.load() if c["ats"] == "bytedance"}
    assert names["TikTok"]["brand"] == "tiktok"
    assert names["ByteDance"]["brand"] == "bytedance"


def test_posted_date_ignores_ids_that_are_not_timestamps():
    assert bytedance._posted("12345") is None
    assert bytedance._posted("not-an-id") is None
    assert bytedance._posted("7695929967028750645") == "2026-10-12T00:00:00Z"
