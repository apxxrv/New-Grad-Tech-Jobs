"""TikTok and ByteDance careers sites: one shared job API, two brands.

lifeattiktok.com and joinbytedance.com (jobs.bytedance.com redirects there)
are the same Next.js app over the same public JSON API, which the page calls
straight from the browser with no token or cookie. Only three things differ
per brand: the API host, the `origin` header, and a `website-path` header that
picks the brand's job pool. The company entry names its brand
(`"brand": "tiktok"`), defaulting to the slug.

Two POST endpoints:
  /config/job/filters   the site's own filter menu, including every city it
                        hires in, each tagged with its country
  /search/job/posts     the job search, paginated by limit/offset with a total
                        `count`

Both filters we need run on the server. `recruitment_id_list: ["201"]` is the
campus "Regular" type, i.e. graduate roles. Its sibling "202" is campus
interns, and "2" is the two together; experienced hires are "1".
`location_code_list` only takes city codes (the US country code returns
nothing), so each run first reads the city list and sends every US city.

The API returns no posted date, and neither does the job page. The job id is
a timestamp id, though: its top 32 bits are the Unix second the posting was
created. Checked against public lists, that lands within a few days of their
"date posted", so we use it as the day the role was posted.
"""

from __future__ import annotations

from datetime import UTC, datetime

from ..models import (
    INCOMPLETE_CAPPED,
    INCOMPLETE_MALFORMED,
    INCOMPLETE_STALLED,
    Fetch,
    Job,
    clean_listing,
    source_board_key,
)
from ..net import Net

BRANDS = {
    "tiktok": {
        "api": "https://api.lifeattiktok.com/api/v1/public/supplier",
        "origin": "https://lifeattiktok.com",
        "website_path": "tiktok",
        "job_url": "https://lifeattiktok.com/search/{id}",
    },
    "bytedance": {
        "api": "https://jobs.bytedance.com/api/v1/public/supplier",
        "origin": "https://joinbytedance.com",
        "website_path": "en",
        "job_url": "https://joinbytedance.com/search/{id}",
    },
}

_CAMPUS_GRADUATE = "201"  # campus "Regular" (graduate) recruitment type
_US = "CN_6"              # the API's country code for the United States
_PAGE_SIZE = 100
_MAX_JOBS = 2000          # US campus graduate roles run in the low hundreds

# Ids before 2015 or in the future mean the id is not the timestamp we think.
_EARLIEST_ID_TIME = datetime(2015, 1, 1, tzinfo=UTC).timestamp()


def _headers(brand: dict) -> dict:
    return {
        "Accept": "application/json",
        "accept-language": "en-US",
        "origin": brand["origin"],
        "website-path": brand["website_path"],
    }


def _ok(payload) -> dict | None:
    """The `data` object of a healthy response, or None.

    A healthy reply is `{"code": 0, "data": {...}, "error": null}`. Any other
    code is the API's error envelope, still sent with HTTP 200.
    """
    if not isinstance(payload, dict) or payload.get("code") != 0 or payload.get("error"):
        return None
    data = payload.get("data")
    return data if isinstance(data, dict) else None


def _country(node: dict | None) -> dict | None:
    """The top of a city -> state -> country chain."""
    while isinstance(node, dict) and isinstance(node.get("parent"), dict):
        node = node["parent"]
    return node if isinstance(node, dict) else None


def _us_city_codes(filters: dict) -> list[str]:
    cities = filters.get("city_list")
    if not isinstance(cities, list):
        return []
    codes = []
    for city in cities:
        if not isinstance(city, dict) or not city.get("code"):
            continue
        if (_country(city) or {}).get("code") == _US:
            codes.append(str(city["code"]))
    return sorted(set(codes))


def _location(city: dict | None) -> str:
    """'San Jose, California, USA' from the API's nested city record."""
    names = []
    node = city
    while isinstance(node, dict):
        name = (node.get("en_name") or node.get("i18n_name") or "").strip()
        if name:
            names.append(name)
        node = node.get("parent")
    if not names:
        return "—"
    if (_country(city) or {}).get("code") == _US:
        names[-1] = "USA"
    # Washington D.C. comes back as "Washington D.C., District of Columbia".
    return ", ".join(dict.fromkeys(names))


def _posted(job_id: str) -> str | None:
    """The creation day encoded in the id's top 32 bits, at midnight UTC."""
    try:
        seconds = int(job_id) >> 32
    except (TypeError, ValueError):
        return None
    if not _EARLIEST_ID_TIME <= seconds <= datetime.now(UTC).timestamp() + 86400:
        return None
    return datetime.fromtimestamp(seconds, UTC).strftime("%Y-%m-%dT00:00:00Z")


def _job(raw: dict, company: dict, slug: str, brand: dict) -> Job:
    job_id = str(raw.get("id") or "").strip()
    description = "\n\n".join(
        str(raw.get(k) or "").strip() for k in ("description", "requirement")
    ).strip()
    posted = _posted(job_id)
    return Job(
        id=f"bytedance:{slug}:{job_id}",
        source="bytedance",
        company=company.get("name") or slug,
        company_slug=slug,
        title=(raw.get("title") or "").strip(),
        location=_location(raw.get("city_info")),
        url=brand["job_url"].format(id=job_id) if job_id else "",
        posted_at=posted,
        posted_at_source="date_only" if posted else None,
        description=description or None,
        board_key=source_board_key(company, "bytedance", slug),
        requisition_id=str(raw.get("code") or "").strip() or None,
    )


async def fetch(company: dict, net: Net) -> Fetch:
    slug = company.get("slug") or "tiktok"
    brand_name = company.get("brand") or slug
    brand = BRANDS.get(brand_name)
    if brand is None:
        raise ValueError(f"unknown bytedance brand {brand_name!r}")
    headers = _headers(brand)

    filters = _ok(await net.post_json(
        brand["api"] + "/config/job/filters", json={}, headers=headers,
    ))
    cities = _us_city_codes(filters) if filters is not None else []
    if not cities:
        # Searching with no city codes would return the whole world.
        return Fetch([], complete=False, incomplete_reason=INCOMPLETE_MALFORMED)

    jobs: list[Job] = []
    complete = False
    incomplete_reason: str | None = None
    for offset in range(0, _MAX_JOBS, _PAGE_SIZE):
        body = {
            "keyword": "",
            "recruitment_id_list": [_CAMPUS_GRADUATE],
            "location_code_list": cities,
            "job_category_id_list": [],
            "subject_id_list": [],
            "tag_id_list": [],
            "limit": _PAGE_SIZE,
            "offset": offset,
        }
        data = _ok(await net.post_json(
            brand["api"] + "/search/job/posts", json=body, headers=headers,
        ))
        results = clean_listing(data, "job_post_list") if data is not None else None
        total = data.get("count") if data is not None else None
        if results is None or not isinstance(total, int):
            incomplete_reason = INCOMPLETE_MALFORMED
            break
        jobs.extend(_job(raw, company, slug, brand) for raw in results)
        if offset + len(results) >= total:
            complete = True
            break
        if not results:
            # The server says there is more but handed back nothing.
            incomplete_reason = INCOMPLETE_STALLED
            break
    if not complete and incomplete_reason is None:
        incomplete_reason = INCOMPLETE_CAPPED
    return Fetch(jobs, complete=complete, incomplete_reason=incomplete_reason)
