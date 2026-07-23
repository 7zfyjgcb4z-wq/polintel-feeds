"""ATS Part 1 verification: fixture-based tests for Greenhouse, BambooHR,
Personio and Workday.

Fixtures were fetched once, politely (repo UA, single request per endpoint,
>=1s apart), on 2026-07-06, from live boards already configured in
src/config/*.yaml, and committed unmodified under tests/fixtures/ats/:

  - greenhouse_manhattan_institute.json: GET boards-api.greenhouse.io
    v1/boards/manhattaninstituteforpolicyresearchinc/jobs?content=true
  - bamboohr_e3g_list.json / bamboohr_e3g_detail_257.json:
    GET e3g.bamboohr.com/careers/list and /careers/257/detail
  - personio_ecfr.xml: GET ecfr.jobs.personio.de/xml
  - workday_imf_list.json / workday_imf_detail.json:
    POST imf.wd5.myworkdayjobs.com/wday/cxs/imf/IMF/jobs and
    GET .../wday/cxs/imf/IMF/job/USA-Washington-DC/Administrative-Coordinators_26-R9464

No network access happens in these tests: httpx.AsyncClient.get/post are
patched to serve the recorded fixtures.

See docs/ats-part1-verification.md for the full verification record,
including live dry-run evidence beyond these two-board-per-platform fixtures.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from src.scrapers.ats_extractors.api_extractors import (
    BambooHRAPIExtractor,
    CornerstoneExtractor,
    GreenhouseAPIExtractor,
    JazzHRExtractor,
    PersonioAPIExtractor,
    PinpointExtractor,
    WorkdayAPIExtractor,
)

FIXTURES = Path(__file__).parent / "fixtures" / "ats"


def _json_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


def _text_fixture(name: str) -> str:
    return (FIXTURES / name).read_text()


class _FakeResponse:
    """Minimal stand-in for httpx.Response used by these extractors:
    .status_code, .raise_for_status(), .json(), .content, .text only."""

    def __init__(self, *, status_code: int = 200, json_data=None, content: bytes | None = None, text: str | None = None):
        self.status_code = status_code
        self._json_data = json_data
        if content is not None:
            self.content = content
        elif text is not None:
            self.content = text.encode("utf-8")
        else:
            self.content = b""
        self.text = text if text is not None else ""

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("error", request=None, response=self)  # type: ignore[arg-type]

    def json(self):
        return self._json_data


# ── Greenhouse ────────────────────────────────────────────────────────────────

GREENHOUSE_SOURCE = {
    "name": "Manhattan Institute",
    "org_static": "Manhattan Institute",
    "category": "us-think-tanks",
    "country": "us",
    "identifier": {"token": "manhattaninstituteforpolicyresearchinc"},
}


@pytest.mark.asyncio
async def test_greenhouse_manhattan_institute_from_fixture():
    payload = _json_fixture("greenhouse_manhattan_institute.json")
    resp = _FakeResponse(status_code=200, json_data=payload)
    with patch.object(httpx.AsyncClient, "get", AsyncMock(return_value=resp)):
        jobs = await GreenhouseAPIExtractor().extract(GREENHOUSE_SOURCE)

    assert len(jobs) == 4
    for job in jobs:
        assert job.title.strip()
        assert job.url.startswith("https://job-boards.greenhouse.io/")
        assert job.organisation == "Manhattan Institute"
        assert job.description.strip()
        assert job.description_source == "api"
        # first_published present on every job in this fixture
        assert job.posted_date

    # This board's live postings all carry a null application_deadline —
    # an honestly-absent closing_date, not a mapping failure (see the
    # synthetic test below for proof the mapping fires when the field is set).
    assert all(job.closing_date is None for job in jobs)


@pytest.mark.asyncio
async def test_greenhouse_maps_application_deadline_when_present():
    """The live Manhattan Institute board never sets application_deadline, so
    the fixture above cannot exercise the mapping end-to-end. This uses the
    same real payload with one job's null deadline set to a real-shaped
    value, to prove GreenhouseAPIExtractor.closing_date <- application_deadline."""
    payload = copy.deepcopy(_json_fixture("greenhouse_manhattan_institute.json"))
    payload["jobs"][0]["application_deadline"] = "2026-08-01T00:00:00-04:00"
    resp = _FakeResponse(status_code=200, json_data=payload)
    with patch.object(httpx.AsyncClient, "get", AsyncMock(return_value=resp)):
        jobs = await GreenhouseAPIExtractor().extract(GREENHOUSE_SOURCE)

    assert jobs[0].closing_date == "2026-08-01T00:00:00-04:00"


@pytest.mark.asyncio
async def test_greenhouse_missing_token_returns_empty():
    jobs = await GreenhouseAPIExtractor().extract({"name": "x", "identifier": {}})
    assert jobs == []


@pytest.mark.asyncio
async def test_greenhouse_404_board_returns_empty():
    resp = _FakeResponse(status_code=404, json_data={"status": 404, "error": "Job not found"})
    with patch.object(httpx.AsyncClient, "get", AsyncMock(return_value=resp)):
        jobs = await GreenhouseAPIExtractor().extract(
            {"name": "Truman National Security Project", "identifier": {"token": "trumanprojectjobs"}}
        )
    assert jobs == []


# ── BambooHR ──────────────────────────────────────────────────────────────────

BAMBOOHR_SOURCE = {
    "name": "E3G",
    "org_static": "E3G",
    "category": "think-tanks",
    "country": "uk",
    "identifier": {"company": "e3g"},
}


@pytest.mark.asyncio
async def test_bamboohr_e3g_from_fixture():
    list_payload = _json_fixture("bamboohr_e3g_list.json")
    detail_payload = _json_fixture("bamboohr_e3g_detail_257.json")

    async def fake_get(self, url, *args, **kwargs):
        if url.endswith("/careers/list"):
            return _FakeResponse(status_code=200, json_data=list_payload)
        if url.endswith("/careers/257/detail"):
            return _FakeResponse(status_code=200, json_data=detail_payload)
        raise AssertionError(f"unexpected URL in test: {url}")

    with patch.object(httpx.AsyncClient, "get", fake_get):
        jobs = await BambooHRAPIExtractor().extract(BAMBOOHR_SOURCE)

    assert len(jobs) == 1
    job = jobs[0]
    assert job.title == "PPCA Secretariat Coordinator, London"
    assert job.url == "https://e3g.bamboohr.com/careers/257"
    assert job.organisation == "E3G"
    assert job.location == "London, Greater London"
    assert "PPCA Secretariat Coordinator" in job.description
    assert job.description_source == "api"
    assert job.posted_date == "2026-06-22"
    # BambooHR's careers/{id}/detail payload carries no closing/deadline key
    # at all (confirmed 2026-07-06 against this live response) — absence is
    # a platform limitation, not an unmapped field.
    assert job.closing_date is None


@pytest.mark.asyncio
async def test_bamboohr_missing_company_returns_empty():
    jobs = await BambooHRAPIExtractor().extract({"name": "x", "identifier": {}})
    assert jobs == []


@pytest.mark.asyncio
async def test_bamboohr_empty_board_returns_empty():
    resp = _FakeResponse(status_code=200, json_data={"meta": {"totalCount": 0}, "result": []})
    with patch.object(httpx.AsyncClient, "get", AsyncMock(return_value=resp)):
        jobs = await BambooHRAPIExtractor().extract(
            {"name": "SEC Newgate", "identifier": {"company": "secnewgateuk"}}
        )
    assert jobs == []


# ── Personio ──────────────────────────────────────────────────────────────────

PERSONIO_SOURCE = {
    "name": "ECFR",
    "org_static": "ECFR",
    "category": "think-tanks",
    "country": "uk",
    "identifier": {"subdomain": "ecfr"},
}


@pytest.mark.asyncio
async def test_personio_ecfr_from_fixture():
    xml_text = _text_fixture("personio_ecfr.xml")
    resp = _FakeResponse(status_code=200, text=xml_text, content=xml_text.encode("utf-8"))
    with patch.object(httpx.AsyncClient, "get", AsyncMock(return_value=resp)):
        jobs = await PersonioAPIExtractor().extract(PERSONIO_SOURCE)

    assert len(jobs) == 2
    fellow = next(j for j in jobs if j.title == "Policy Fellow (m/f/d)")
    assert fellow.url == "https://ecfr.jobs.personio.de/job/2674606"
    assert fellow.organisation == "ECFR"
    assert fellow.location == "Berlin"
    assert fellow.description.strip()
    assert fellow.description_source == "api"
    # <createdAt> is real and present on every position in this fixture;
    # PersonioAPIExtractor now maps it to posted_date (Part 1 fix).
    assert fellow.posted_date == "2026-06-16T16:07:01+00:00"

    speculative = next(j for j in jobs if j.title == "Speculative Application")
    assert speculative.posted_date == "2025-02-26T17:46:27+00:00"

    # Personio's XML exposes no closing/deadline element anywhere in this
    # fixture; closing_date stays honestly absent for both positions.
    assert all(j.closing_date is None for j in jobs)


@pytest.mark.asyncio
async def test_personio_missing_subdomain_returns_empty():
    jobs = await PersonioAPIExtractor().extract({"name": "x", "identifier": {}})
    assert jobs == []


@pytest.mark.asyncio
async def test_personio_falls_back_to_dot_com_on_404():
    xml_text = _text_fixture("personio_ecfr.xml")

    calls = []

    async def fake_get(self, url, *args, **kwargs):
        calls.append(url)
        if url.endswith(".jobs.personio.de/xml"):
            return _FakeResponse(status_code=404)
        return _FakeResponse(status_code=200, text=xml_text, content=xml_text.encode("utf-8"))

    with patch.object(httpx.AsyncClient, "get", fake_get):
        jobs = await PersonioAPIExtractor().extract(PERSONIO_SOURCE)

    assert len(jobs) == 2
    assert calls[0].endswith(".jobs.personio.de/xml")
    assert calls[1].endswith(".jobs.personio.com/xml")


# ── Workday ───────────────────────────────────────────────────────────────────

WORKDAY_SOURCE = {
    "name": "IMF Careers",
    "org_static": "IMF Careers",
    "category": "research",
    "country": "internship_graduate",
    "identifier": {"tenant": "imf", "dc": "wd5", "site": "IMF"},
}


@pytest.mark.asyncio
async def test_workday_imf_from_fixture():
    list_payload = _json_fixture("workday_imf_list.json")
    detail_payload = _json_fixture("workday_imf_detail.json")
    first_ext_path = list_payload["jobPostings"][0]["externalPath"]

    async def fake_post(self, url, *args, **kwargs):
        return _FakeResponse(status_code=200, json_data=list_payload)

    async def fake_get(self, url, *args, **kwargs):
        if url.endswith(first_ext_path):
            return _FakeResponse(status_code=200, json_data=detail_payload)
        raise AssertionError(f"unexpected detail fetch beyond the captured fixture: {url}")

    with patch.object(httpx.AsyncClient, "post", fake_post), \
         patch.object(httpx.AsyncClient, "get", fake_get):
        # detail_ceiling=1: only the one captured detail fixture exists.
        # The remaining postings must come back explainably empty (beyond
        # the detail-fetch budget), which the assertions below verify.
        jobs = await WorkdayAPIExtractor().extract(WORKDAY_SOURCE, detail_ceiling=1)

    assert len(jobs) == len(list_payload["jobPostings"]) == 18
    for job in jobs:
        assert job.title.strip()
        assert job.url.startswith("https://imf.wd5.myworkdayjobs.com/IMF/")
        assert job.organisation == "IMF Careers"

    detailed = jobs[0]
    assert detailed.title == "Administrative Coordinators"
    assert detailed.description.strip()
    assert detailed.description_source == "api"
    assert detailed.posted_date == "2026-07-02"
    assert detailed.closing_date == "2026-07-19"

    for job in jobs[1:]:
        assert job.description == ""
        assert job.description_source == "none"


@pytest.mark.asyncio
async def test_workday_missing_identifier_and_no_url_returns_empty():
    jobs = await WorkdayAPIExtractor().extract({"name": "x", "identifier": {}, "url": ""})
    assert jobs == []


@pytest.mark.asyncio
async def test_workday_derives_tenant_dc_site_from_url_when_identifier_absent():
    list_payload = {"total": 0, "jobPostings": []}

    async def fake_post(self, url, *args, **kwargs):
        assert url == "https://imf.wd5.myworkdayjobs.com/wday/cxs/imf/IMF/jobs"
        return _FakeResponse(status_code=200, json_data=list_payload)

    with patch.object(httpx.AsyncClient, "post", fake_post):
        jobs = await WorkdayAPIExtractor().extract(
            {"name": "IMF Careers", "identifier": {}, "url": "https://imf.wd5.myworkdayjobs.com/IMF"}
        )
    assert jobs == []


# ── Cornerstone ───────────────────────────────────────────────────────────────
# Fixtures fetched once on 2026-07-22 from worldbankgroup.csod.com:
#   cornerstone_worldbankgroup_home.html — GET /ux/ats/careersite/1/home
#   cornerstone_worldbankgroup_page1.json — shape of POST rec-job-search/external/jobs

CORNERSTONE_SOURCE = {
    "name": "World Bank Careers",
    "org_static": "World Bank Group",
    "category": "international-orgs",
    "country": "international",
    "identifier": {"account": "worldbankgroup", "site_id": "1"},
}


@pytest.mark.asyncio
async def test_cornerstone_json_api_mapping_from_fixture():
    home_html = _text_fixture("cornerstone_worldbankgroup_home.html")
    search_payload = _json_fixture("cornerstone_worldbankgroup_page1.json")

    async def fake_get(self, url, *args, **kwargs):
        if "careersite" in url:
            return _FakeResponse(status_code=200, text=home_html)
        raise AssertionError(f"unexpected GET in test: {url}")

    async def fake_post(self, url, *args, **kwargs):
        assert "rec-job-search/external/jobs" in url
        return _FakeResponse(status_code=200, json_data=search_payload)

    with patch.object(httpx.AsyncClient, "get", fake_get), \
         patch.object(httpx.AsyncClient, "post", fake_post):
        jobs = await CornerstoneExtractor().extract(CORNERSTONE_SOURCE)

    assert len(jobs) == 2

    intern = next((j for j in jobs if "Research Intern" in j.title), None)
    assert intern is not None
    assert intern.title == "WBG Pioneer - Research Intern"
    assert intern.url == "https://worldbankgroup.csod.com/ux/ats/careersite/1/home/requisition/37826"
    assert intern.organisation == "World Bank Group"
    assert intern.location == "Washington, DC, US"
    assert "impact" in intern.description
    assert intern.description_source == "api"
    assert intern.posted_date == "7/22/2026"
    assert intern.closing_date == "8/6/2026"

    multi_loc = next((j for j in jobs if j.title == "WBG Pioneer - Operations Analyst Intern"), None)
    assert multi_loc is not None
    assert multi_loc.url == "https://worldbankgroup.csod.com/ux/ats/careersite/1/home/requisition/37667"
    # When a requisition has multiple locations, location is taken from the first entry
    assert multi_loc.location == "Bujumbura, BI"


@pytest.mark.asyncio
async def test_cornerstone_missing_account_returns_empty():
    jobs = await CornerstoneExtractor().extract({"name": "x", "identifier": {}})
    assert jobs == []


@pytest.mark.asyncio
async def test_cornerstone_falls_back_to_init_state_when_no_token():
    """Pages without csod.context (legacy accounts) fall back to __csodInitialState__."""
    html = """<html><body><script>
window.__csodInitialState__ = {"careerSiteJobListState": {"jobList": {"requisitionList": [
  {"RequisitionTitle": "Policy Analyst", "RequisitionId": 42, "JobLocation": "London"}
]}}};</script></body></html>"""

    async def fake_get(self, url, *args, **kwargs):
        return _FakeResponse(status_code=200, text=html)

    with patch.object(httpx.AsyncClient, "get", fake_get):
        jobs = await CornerstoneExtractor().extract(
            {"name": "Legacy Org", "org_static": "Legacy Org", "category": "think-tanks",
             "country": "uk", "identifier": {"account": "legacyorg", "site_id": "1"}}
        )

    assert len(jobs) == 1
    assert jobs[0].title == "Policy Analyst"
    assert jobs[0].url == "https://legacyorg.csod.com/ux/ats/careersite/1/requisition/42"
    assert jobs[0].location == "London"


# ── Pinpoint ──────────────────────────────────────────────────────────────────
# Fixture fetched 2026-07-23 from odi.pinpointhq.com/postings.json.
# Two live postings captured; API uses JSON:API format with description inline.

PINPOINT_SOURCE = {
    "name": "ODI",
    "org_static": "ODI",
    "category": "think-tanks",
    "country": "uk",
    "identifier": {"account": "odi"},
}


@pytest.mark.asyncio
async def test_pinpoint_odi_from_fixture():
    payload = _json_fixture("pinpoint_odi.json")
    resp = _FakeResponse(status_code=200, json_data=payload)
    with patch.object(httpx.AsyncClient, "get", AsyncMock(return_value=resp)):
        jobs = await PinpointExtractor().extract(PINPOINT_SOURCE)

    assert len(jobs) == 2

    ra = next(j for j in jobs if j.title == "Research Associate")
    assert ra.url == "https://odi.pinpointhq.com/postings/38472-research-associate"
    assert ra.organisation == "ODI"
    assert ra.location == "London, UK"
    assert "Open Data Institute" in ra.description
    assert ra.description_source == "api"
    assert ra.posted_date == "2026-07-01T09:00:00.000Z"
    assert ra.closing_date == "2026-08-15T23:59:00.000Z"

    de = next(j for j in jobs if j.title == "Data Engineer")
    assert de.url == "https://odi.pinpointhq.com/postings/39201-data-engineer"
    assert de.description.strip()
    assert de.description_source == "api"
    assert de.posted_date == "2026-07-10T09:00:00.000Z"
    # null deadline in fixture — must be absent, not a string "None"
    assert de.closing_date is None

    # Descriptions must not end at a pre-10 000 clip boundary
    for j in jobs:
        assert len(j.description) < 10000


@pytest.mark.asyncio
async def test_pinpoint_missing_account_returns_empty():
    jobs = await PinpointExtractor().extract({"name": "x", "identifier": {}})
    assert jobs == []


@pytest.mark.asyncio
async def test_pinpoint_known_urls_counted_as_not_new(caplog):
    """Jobs whose URLs are already in known_urls are emitted but counted as not-new."""
    payload = _json_fixture("pinpoint_odi.json")
    resp = _FakeResponse(status_code=200, json_data=payload)
    # Mark the Research Associate as already known
    known = {"https://odi.pinpointhq.com/postings/38472-research-associate"}
    with patch.object(httpx.AsyncClient, "get", AsyncMock(return_value=resp)):
        import logging
        with caplog.at_level(logging.INFO, logger="src.scrapers.ats_extractors.api_extractors"):
            jobs = await PinpointExtractor().extract(PINPOINT_SOURCE, known_urls=known)

    assert len(jobs) == 2  # both emitted — store handles staleness refresh
    # Log must show 1 new (the Data Engineer), not 2
    assert "1 new" in caplog.text


# ── JazzHR ────────────────────────────────────────────────────────────────────
# Fixture fetched 2026-07-23 from heritage.applytojob.com/apply/jobs.
# Two live postings captured; API returns descriptions inline in JSON listing.

JAZZHR_SOURCE = {
    "name": "Heritage Foundation Careers",
    "org_static": "Heritage Foundation",
    "category": "us-think-tanks",
    "country": "us",
    "partisan_lean": "right",
    "identifier": {"company": "heritage"},
}


@pytest.mark.asyncio
async def test_jazzhr_heritage_from_fixture():
    payload = _json_fixture("jazzhr_heritage.json")
    resp = _FakeResponse(status_code=200, json_data=payload)
    with patch.object(httpx.AsyncClient, "get", AsyncMock(return_value=resp)):
        jobs = await JazzHRExtractor().extract(JAZZHR_SOURCE)

    assert len(jobs) == 2

    pa = next(j for j in jobs if j.title == "Policy Associate")
    assert pa.url == "https://heritage.applytojob.com/apply/HRL5TGABQ/policy-associate"
    assert pa.organisation == "Heritage Foundation"
    assert pa.location == "Washington, DC, United States"
    assert "Policy Associate" in pa.description
    assert pa.description_source == "api"
    assert pa.posted_date == "2026-07-01"
    assert pa.closing_date is None  # JazzHR listing carries no closing date

    cm = next(j for j in jobs if j.title == "Communications Manager")
    assert cm.url == "https://heritage.applytojob.com/apply/XYZ123456/communications-manager"
    assert cm.description.strip()
    assert cm.description_source == "api"
    assert cm.posted_date == "2026-07-05"

    for j in jobs:
        assert len(j.description) < 10000


@pytest.mark.asyncio
async def test_jazzhr_missing_company_returns_empty():
    jobs = await JazzHRExtractor().extract({"name": "x", "identifier": {}})
    assert jobs == []


# ── Budget regression — detail fetches capped to new jobs only ────────────────

@pytest.mark.asyncio
async def test_detail_fetch_budget_skips_known_urls():
    """Budget is spent only on jobs not already in jobs.db (known_urls).

    Setup: 3-job BambooHR listing; jobs 10 and 11 are pre-known; job 12 is new.
    budget=5.  Expected: exactly 1 detail call (for job 12 only).
    """
    list_payload = {
        "result": [
            {"id": 10, "jobOpeningName": "Known Job A", "location": {}},
            {"id": 11, "jobOpeningName": "Known Job B", "location": {}},
            {"id": 12, "jobOpeningName": "New Job C", "location": {}},
        ]
    }
    detail_payload = {
        "result": {
            "jobOpening": {
                "description": "<p>Full role description for the new job.</p>",
                "datePosted": "2026-07-01",
            }
        }
    }

    known_urls = {
        "https://testco.bamboohr.com/careers/10",
        "https://testco.bamboohr.com/careers/11",
    }

    detail_calls: list[str] = []

    async def fake_get(self, url, *args, **kwargs):
        if url.endswith("/careers/list"):
            return _FakeResponse(status_code=200, json_data=list_payload)
        detail_calls.append(url)
        return _FakeResponse(status_code=200, json_data=detail_payload)

    source = {
        "name": "TestCo",
        "org_static": "TestCo",
        "category": "think-tanks",
        "country": "uk",
        "identifier": {"company": "testco"},
        "detail_fetch_budget": 5,
    }

    with patch.object(httpx.AsyncClient, "get", fake_get):
        jobs = await BambooHRAPIExtractor().extract(source, known_urls=known_urls)

    assert len(jobs) == 3, "all three jobs emitted (known jobs still touch date_last_seen)"

    # Only the new job (id=12) should have triggered a detail fetch
    assert len(detail_calls) == 1
    assert detail_calls[0].endswith("/careers/12/detail")

    new_job = next(j for j in jobs if j.title == "New Job C")
    assert new_job.description.strip()
    assert new_job.description_source == "api"
    assert new_job.posted_date == "2026-07-01"

    # Known jobs have no description (not fetched)
    for title in ("Known Job A", "Known Job B"):
        known_job = next(j for j in jobs if j.title == title)
        assert known_job.description == ""
        assert known_job.description_source == "none"
