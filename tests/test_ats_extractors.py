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
    GreenhouseAPIExtractor,
    PersonioAPIExtractor,
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
