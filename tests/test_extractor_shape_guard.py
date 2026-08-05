"""Shape-guard tests for ATS extractors.

Covers:
  - PinpointExtractor parses the flat (non-JSON:API) format that ODI now returns.
  - PinpointExtractor still parses the JSON:API format (no regression).
  - PinpointExtractor accepts a bare list response without the {"data":[...]} wrapper.
  - Shape guard fires (WARNING + alert event) when raw > 0, yield 0.
  - Shape guard stays silent when raw == 0, yield 0 (empty board).
  - Partial-yield INFO fires when yield < 50 % of raw.

No network access: httpx.AsyncClient.get is patched with recorded fixtures or
inline payloads.  _shape_events is cleared before and after each scenario.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from src.scrapers.ats_extractors import api_extractors
from src.scrapers.ats_extractors.api_extractors import BaseATSExtractor, PinpointExtractor

FIXTURES = Path(__file__).parent / "fixtures" / "ats"


def _json_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


class _FakeResponse:
    """Minimal stand-in for httpx.Response (status_code, raise_for_status, json)."""

    def __init__(self, *, status_code: int = 200, json_data=None):
        self.status_code = status_code
        self._json_data = json_data

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("error", request=None, response=self)  # type: ignore[arg-type]

    def json(self):
        return self._json_data


PINPOINT_SOURCE = {
    "name": "ODI",
    "org_static": "ODI",
    "category": "think-tanks",
    "country": "uk",
    "identifier": {"account": "odi"},
}

# ── Flat-format fixture (the live ODI shape as of 2026-08-05) ─────────────────
# Items sit directly in data[]; no "attributes" sub-object, no "links" key.
# date key is deadline_at; location is a dict with "name" and "city".
FLAT_FIXTURE: dict = {
    "data": [
        {
            "id": "474551",
            "title": "Journals and Digital Content Coordinator",
            "description": "<p>ODI Global is looking for a <strong>Journals and Digital Content Coordinator</strong> to join our team.</p>",
            "url": "https://careers.odi.org/en/postings/bf66111a-4f68-4a1a-8375-27e7e5412670",
            "path": "/en/postings/bf66111a-4f68-4a1a-8375-27e7e5412670",
            "location": {"id": "35242", "city": "London", "name": "London, UK", "postal_code": "", "province": "United Kingdom"},
            "deadline_at": "2026-08-16T23:59:59+01:00",
        },
        {
            "id": "536084",
            "title": "Financial Controls and Reporting Manager",
            "description": "<p>We are seeking a <strong>Financial Controls and Reporting Manager</strong>.</p>",
            "url": "https://careers.odi.org/en/postings/c1d2e3f4-1234-5678-abcd-ef1234567890",
            "path": "/en/postings/c1d2e3f4-1234-5678-abcd-ef1234567890",
            "location": {"id": "35242", "city": "London", "name": "London, UK"},
            "deadline_at": "2026-09-01T23:59:59+01:00",
        },
        {
            "id": "536122",
            "title": "Portfolio Finance Manager",
            "description": "<p>Join ODI as a <strong>Portfolio Finance Manager</strong>.</p>",
            "url": "https://careers.odi.org/en/postings/d4e5f6a7-4321-8765-dcba-fedcba987654",
            "path": "/en/postings/d4e5f6a7-4321-8765-dcba-fedcba987654",
            "location": {"id": "35242", "city": "London", "name": "London, UK"},
            "deadline_at": None,
        },
    ]
}


# ── 1. Pinpoint flat format ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_pinpoint_flat_fixture_yields_jobs():
    """PinpointExtractor parses the flat (non-JSON:API) format ODI now returns."""
    resp = _FakeResponse(status_code=200, json_data=FLAT_FIXTURE)
    api_extractors._shape_events.clear()
    with patch.object(httpx.AsyncClient, "get", AsyncMock(return_value=resp)):
        jobs = await PinpointExtractor().extract(PINPOINT_SOURCE)

    assert len(jobs) == 3, f"expected 3 jobs from flat fixture, got {len(jobs)}"

    coord = next(j for j in jobs if "Journals" in j.title)
    assert coord.title == "Journals and Digital Content Coordinator"
    assert coord.url == "https://careers.odi.org/en/postings/bf66111a-4f68-4a1a-8375-27e7e5412670"
    assert coord.location == "London, UK"
    assert "Journals and Digital Content Coordinator" in coord.description
    assert coord.description_source == "api"
    assert coord.closing_date == "2026-08-16T23:59:59+01:00"
    # Flat format exposes no published_at / posted_at
    assert coord.posted_date is None

    fin = next(j for j in jobs if "Financial" in j.title)
    assert fin.closing_date == "2026-09-01T23:59:59+01:00"

    pfm = next(j for j in jobs if "Portfolio" in j.title)
    assert pfm.closing_date is None  # deadline_at is null in fixture

    # Guard must not fire when all items yielded successfully
    assert api_extractors._shape_events == []
    api_extractors._shape_events.clear()


# ── 2. JSON:API regression ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_pinpoint_jsonapi_fixture_no_regression():
    """PinpointExtractor still handles the original JSON:API format (no regression)."""
    payload = _json_fixture("pinpoint_odi.json")
    resp = _FakeResponse(status_code=200, json_data=payload)
    api_extractors._shape_events.clear()
    with patch.object(httpx.AsyncClient, "get", AsyncMock(return_value=resp)):
        jobs = await PinpointExtractor().extract(PINPOINT_SOURCE)

    assert len(jobs) == 2

    ra = next(j for j in jobs if j.title == "Research Associate")
    assert ra.url == "https://odi.pinpointhq.com/postings/38472-research-associate"
    assert ra.location == "London, UK"
    assert ra.closing_date == "2026-08-15T23:59:00.000Z"
    assert ra.posted_date == "2026-07-01T09:00:00.000Z"
    assert "Open Data Institute" in ra.description
    assert ra.description_source == "api"

    de = next(j for j in jobs if j.title == "Data Engineer")
    assert de.closing_date is None
    assert de.description.strip()

    # Guard must not fire
    assert api_extractors._shape_events == []
    api_extractors._shape_events.clear()


# ── 3. Bare list response ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_pinpoint_accepts_bare_list_response():
    """PinpointExtractor handles a bare list [...] without the {"data":[...]} wrapper."""
    payload = [
        {
            "id": "100",
            "title": "Policy Analyst",
            "description": "<p>Policy analysis role at a leading think tank.</p>",
            "url": "https://example.pinpointhq.com/postings/100-policy-analyst",
        }
    ]
    source = {
        "name": "Example Org",
        "org_static": "Example Org",
        "category": "think-tanks",
        "country": "uk",
        "identifier": {"account": "example"},
    }
    resp = _FakeResponse(status_code=200, json_data=payload)
    api_extractors._shape_events.clear()
    with patch.object(httpx.AsyncClient, "get", AsyncMock(return_value=resp)):
        jobs = await PinpointExtractor().extract(source)

    assert len(jobs) == 1
    assert jobs[0].title == "Policy Analyst"
    assert jobs[0].url == "https://example.pinpointhq.com/postings/100-policy-analyst"
    assert "Policy analysis" in jobs[0].description
    assert jobs[0].description_source == "api"
    assert api_extractors._shape_events == []
    api_extractors._shape_events.clear()


# ── 4. Guard fires: raw > 0, yield 0 ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_shape_guard_fires_on_zero_yield_from_nonempty_raw(caplog):
    """Guard fires when API returns N items but all fail field validation (shape break)."""
    # Items without a "title" field simulate a renamed field (shape break)
    payload = {
        "data": [
            {"id": "1", "heading": "Policy Analyst"},
            {"id": "2", "heading": "Research Director"},
        ]
    }
    source = {
        "name": "Broken Org",
        "org_static": "Broken Org",
        "category": "think-tanks",
        "country": "uk",
        "identifier": {"account": "broken"},
    }
    resp = _FakeResponse(status_code=200, json_data=payload)
    api_extractors._shape_events.clear()
    with caplog.at_level(logging.WARNING, logger="src.scrapers.ats_extractors.api_extractors"):
        with patch.object(httpx.AsyncClient, "get", AsyncMock(return_value=resp)):
            jobs = await PinpointExtractor().extract(source)

    assert len(jobs) == 0
    assert len(api_extractors._shape_events) == 1, "guard must emit exactly one event"
    event = api_extractors._shape_events[0]
    assert event["source"] == "Broken Org"
    assert event["platform"] == "pinpoint"
    assert event["identifier"] == "broken"
    assert event["raw_count"] == 2
    assert event["yield_count"] == 0
    assert "shape_mismatch" in event["message"]

    warning_records = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert any("shape mismatch" in r.message.lower() for r in warning_records), \
        "expected WARNING log mentioning shape mismatch"

    api_extractors._shape_events.clear()


# ── 5. Guard silent: empty board ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_shape_guard_silent_on_empty_board(caplog):
    """Guard must not fire when the board genuinely has no postings."""
    payload = {"data": []}
    source = {
        "name": "Quiet Org",
        "org_static": "Quiet Org",
        "category": "think-tanks",
        "country": "uk",
        "identifier": {"account": "quiet"},
    }
    resp = _FakeResponse(status_code=200, json_data=payload)
    api_extractors._shape_events.clear()
    with caplog.at_level(logging.DEBUG, logger="src.scrapers.ats_extractors.api_extractors"):
        with patch.object(httpx.AsyncClient, "get", AsyncMock(return_value=resp)):
            jobs = await PinpointExtractor().extract(source)

    assert jobs == []
    assert api_extractors._shape_events == [], "empty board must not emit a shape event"

    mismatch_warnings = [
        r for r in caplog.records
        if r.levelno >= logging.WARNING and "shape mismatch" in r.message.lower()
    ]
    assert mismatch_warnings == [], "empty board must not log a shape mismatch warning"
    api_extractors._shape_events.clear()


# ── 6. Guard method directly: partial yield warns at INFO ─────────────────────

def test_shape_guard_info_on_partial_yield(caplog):
    """Partial yield (< 50 % of raw) emits an INFO log but no alert event."""
    api_extractors._shape_events.clear()
    extractor = BaseATSExtractor()
    with caplog.at_level(logging.DEBUG, logger="src.scrapers.ats_extractors.api_extractors"):
        extractor._check_shape_guard(
            source_name="Test Org",
            platform="testplatform",
            identifier="testid",
            raw_count=10,
            yield_count=4,  # 40 % — below the 50 % threshold
        )

    # No alert event — partial yield is a warning at INFO, not an actionable alert
    assert api_extractors._shape_events == [], "partial yield must not add an alert event"

    info_records = [r for r in caplog.records if r.levelno == logging.INFO and "partial" in r.message.lower()]
    assert info_records, "expected an INFO log mentioning partial yield"
    api_extractors._shape_events.clear()


def test_shape_guard_silent_above_50_pct(caplog):
    """Yield at or above 50 % of raw emits no log and no event."""
    api_extractors._shape_events.clear()
    extractor = BaseATSExtractor()
    with caplog.at_level(logging.DEBUG, logger="src.scrapers.ats_extractors.api_extractors"):
        extractor._check_shape_guard(
            source_name="Test Org",
            platform="testplatform",
            identifier="testid",
            raw_count=10,
            yield_count=5,  # exactly 50 % — at threshold, not below it
        )

    assert api_extractors._shape_events == []
    # No mismatch warnings
    mismatch = [r for r in caplog.records if "mismatch" in r.message.lower() or "partial" in r.message.lower()]
    assert mismatch == []
    api_extractors._shape_events.clear()


def test_shape_guard_fires_via_method_directly(caplog):
    """_check_shape_guard adds an event when raw > 0 and yield == 0."""
    api_extractors._shape_events.clear()
    extractor = BaseATSExtractor()
    with caplog.at_level(logging.WARNING, logger="src.scrapers.ats_extractors.api_extractors"):
        extractor._check_shape_guard(
            source_name="Test Source",
            platform="greenhouse",
            identifier="test-token",
            raw_count=5,
            yield_count=0,
        )

    assert len(api_extractors._shape_events) == 1
    ev = api_extractors._shape_events[0]
    assert ev["raw_count"] == 5
    assert ev["yield_count"] == 0
    assert ev["platform"] == "greenhouse"
    assert ev["source"] == "Test Source"

    warnings = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert warnings, "expected at least one WARNING"
    api_extractors._shape_events.clear()
