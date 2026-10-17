"""Eightfold AI career sites (Qualcomm, Microsoft, John Deere, Netflix, ...).

Eightfold serves two public JSON search APIs on each tenant's careers host:

- PCSX, `/api/pcsx/search` — the current one. Most tenants have moved to it
  and now answer the old API with HTTP 403 "Not authorized for PCSX". Pages
  are fixed at 10 results (`num` is ignored) and carry no description; the
  enrichment step fetches `/api/pcsx/position_details` once per kept role.
- v2, `/api/apply/v2/jobs` — the original. Netflix still serves only this one
  (its PCSX answers 403 "PCSX is not enabled"). Pages of 100, with the
  description and creation timestamp inline.

`"api"` in the registry picks which to try first (default PCSX). A 403 falls
back to the other API once, so a tenant that migrates keeps working before
anyone edits the registry.

PCSX search narrows server-side with the tenant's own facets, sent as
`filter_<facet>=<value>`. Facet names and values differ per tenant (Qualcomm
and Microsoft: seniority=Entry; John Deere: seniority=1), so they live in the
registry entry. A tenant without a usable facet falls back to keyword search.
The facets are AI-inferred and noisy; our own title filters still decide.

Rate limits: PCSX answers HTTP 429 "Please try again later" (no Retry-After)
once roughly 60-100 requests land in a few seconds, and the limit is shared
across tenants from one IP. Pages are fetched one at a time with a short gap,
and each page gets extra `Net` retries (exponential backoff, Retry-After
honoured when sent), which is enough to ride out a burst.

Company entry shape:
    {"name": "Qualcomm", "slug": "qualcomm", "ats": "eightfold",
     "host": "careers.qualcomm.com", "domain": "qualcomm.com",
     "filters": {"seniority": "Entry"}}
    {"name": "Netflix", "slug": "netflix", "ats": "eightfold", "api": "v2",
     "host": "explore.jobs.netflix.net", "domain": "netflix.com"}
Optional: "query" (keyword; default "new grad" when no filters are set),
"location" (default "United States", since the board is US-only; "" searches
worldwide).
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import httpx

from ..models import (
    INCOMPLETE_CAPPED,
    INCOMPLETE_MALFORMED,
    Fetch,
    Job,
    clean_listing,
    source_board_key,
)
from ..net import Net

_V2_PAGE = 100
_V2_MAX = 300  # safety cap; "new grad" on one tenant never legitimately needs more

_PCSX_PAGE = 10  # fixed by the server
_PCSX_MAX_PAGES = 40  # 400 results; Qualcomm's US entry-level list is ~230
_PCSX_PAGE_GAP = 0.5  # seconds between pages of one tenant
_PCSX_RETRIES = 5  # backoff 1+2+4+8+16s covers the ~10s a 429 burst needs

_KEYWORD = "new grad"
_LOCATION = "United States"

_BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/126.0 Safari/537.36",
    "Accept": "application/json",
}


def _posted(unix_ts) -> str | None:
    try:
        ts = int(unix_ts)
    except (TypeError, ValueError):
        return None
    if ts <= 0:
        return None
    return datetime.fromtimestamp(ts, UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _location(position: dict) -> str:
    locations = position.get("locations")
    if isinstance(locations, list) and locations:
        return "; ".join(str(x).replace(",", ", ") for x in locations[:4])
    return str(position.get("location") or "—").replace(",", ", ") or "—"


def _pcsx_location(position: dict) -> str:
    """The long form ("Bengaluru, Karnataka, India") over the standardized one.

    `standardizedLocations` ends in a 2-letter country code, and our region
    filter reads "Bengaluru, KA, IN" as Indiana and "Cork, CO, IE" as Colorado.
    The long form spells the country out. US entries go first so the 4-entry
    cap can't hide the US half of a multi-country posting.
    """
    raw = position.get("locations")
    if not isinstance(raw, list) or not raw:
        raw = position.get("standardizedLocations")
    if not isinstance(raw, list) or not raw:
        return "—"
    # John Deere sends "Horicon, WI,Wisconsin,United States": tidy the commas.
    names = [", ".join(part.strip() for part in str(x).split(",") if part.strip())
             for x in raw if str(x).strip()]
    names.sort(key=lambda n: "United States" not in n)
    return "; ".join(names[:4]) or "—"


def _job(company: dict, external, title, location, url, posted, description) -> Job:
    slug = company["slug"]
    return Job(
        id=f"eightfold:{slug}:{external}",
        source="eightfold",
        company=company["name"],
        company_slug=slug,
        title=(title or "").strip(),
        location=location,
        url=url,
        posted_at=posted,
        description=description,
        board_key=source_board_key(company, "eightfold", slug),
    )


async def _fetch_v2(company: dict, net: Net) -> Fetch:
    host = company["host"]
    url = f"https://{host}/api/apply/v2/jobs"

    jobs: list[Job] = []
    complete = False
    incomplete_reason: str | None = None
    start = 0
    while start < _V2_MAX:
        params = {
            "domain": company.get("domain", ""),
            "query": company.get("query", _KEYWORD),
            "num": _V2_PAGE,
            "start": start,
            "sort_by": "timestamp",
        }
        data = await net.get_json(url, params=params, headers=_BROWSER_HEADERS)
        positions = clean_listing(data, "positions")
        if positions is None:
            incomplete_reason = INCOMPLETE_MALFORMED
            break  # malformed 200 / error envelope: not an empty tenant
        for p in positions:
            external = p.get("id") or p.get("ats_job_id") or p.get("display_job_id")
            jobs.append(_job(
                company, external, p.get("name"), _location(p),
                p.get("canonicalPositionUrl") or f"https://{host}/careers",
                _posted(p.get("t_create")), p.get("job_description") or None,
            ))
        start += _V2_PAGE
        if len(positions) < _V2_PAGE:
            complete = True  # a short page is the end of the list
            break
        # A FULL page only proves the end when the server's own total says so.
        # `int(data.get("count") or 0)` used to make a missing count read as 0,
        # so `start >= 0` was trivially true and a truncated response looked
        # complete — which is what lets a capped page close live roles.
        total = data.get("count")
        if isinstance(total, int) and start >= total:
            complete = True
            break
    if not complete and incomplete_reason is None:
        incomplete_reason = INCOMPLETE_CAPPED
    return Fetch(jobs, complete=complete, incomplete_reason=incomplete_reason)


def _pcsx_positions(data) -> tuple[list | None, int | None]:
    """(positions, total) from a PCSX page, or (None, None) when malformed.

    A healthy PCSX page carries `"error": {"message": "", "body": ""}` — a
    truthy dict — so the error check reads the message, not the container.
    """
    if not isinstance(data, dict):
        return None, None
    error = data.get("error")
    if isinstance(error, dict):
        if error.get("message") or error.get("body"):
            return None, None
    elif error:
        return None, None
    if data.get("status") not in (None, 200):
        return None, None
    inner = data.get("data")
    positions = clean_listing(inner, "positions")
    if positions is None:
        return None, None
    total = inner.get("count")
    return positions, total if isinstance(total, int) else None


async def _fetch_pcsx(company: dict, net: Net) -> Fetch:
    host = company["host"]
    url = f"https://{host}/api/pcsx/search"
    filters = company.get("filters") or {}
    params: dict = {
        "domain": company.get("domain", ""),
        "query": company.get("query", "" if filters else _KEYWORD),
        "location": company.get("location", _LOCATION),
        "sort_by": "timestamp",
    }
    for facet, value in filters.items():
        params[f"filter_{facet}"] = value  # a list value repeats the parameter

    jobs: list[Job] = []
    seen: set[str] = set()
    complete = False
    incomplete_reason: str | None = None
    for page in range(_PCSX_MAX_PAGES):
        if page:
            await asyncio.sleep(_PCSX_PAGE_GAP)
        start = page * _PCSX_PAGE
        data = await net.get_json(
            url, params={**params, "start": start}, headers=_BROWSER_HEADERS,
            retries=_PCSX_RETRIES,
        )
        positions, total = _pcsx_positions(data)
        if positions is None:
            incomplete_reason = INCOMPLETE_MALFORMED
            break
        for p in positions:
            external = p.get("id") or p.get("atsJobId") or p.get("displayJobId")
            # Sorted by newest first, so a role posted mid-run pushes the
            # previous page's last row onto the next page. Keep one copy.
            if str(external) in seen:
                continue
            seen.add(str(external))
            path = p.get("positionUrl") or f"/careers/job/{external}"
            jobs.append(_job(
                company, external, p.get("name"), _pcsx_location(p),
                f"https://{host}{path}" if path.startswith("/") else path,
                _posted(p.get("postedTs") or p.get("creationTs")), None,
            ))
        if len(positions) < _PCSX_PAGE:
            complete = True
            break
        # Same rule as v2: a full page is the end only when the total says so.
        if total is not None and start + _PCSX_PAGE >= total:
            complete = True
            break
    if not complete and incomplete_reason is None:
        incomplete_reason = INCOMPLETE_CAPPED
    return Fetch(jobs, complete=complete, incomplete_reason=incomplete_reason)


_APIS = {"pcsx": _fetch_pcsx, "v2": _fetch_v2}


async def fetch(company: dict, net: Net) -> Fetch:
    first = "v2" if company.get("api") == "v2" else "pcsx"
    other = "pcsx" if first == "v2" else "v2"
    try:
        return await _APIS[first](company, net)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code != 403:
            raise
        # The tenant moved to (or hasn't yet moved to) PCSX. If the other API
        # also refuses, its error is the one reported to health.
        return await _APIS[other](company, net)
