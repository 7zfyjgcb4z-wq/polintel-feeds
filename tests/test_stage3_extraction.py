"""Golden-file tests for the Stage 3 shared extraction mechanisms.

Fixtures were fetched once, politely (repo UA, 1.5s apart), on 2026-07-03 and
saved under tests/fixtures/. No network access happens in these tests.

Fixture swaps from the spec's default URLs:
  - greenparty_job.html: the spec's default URL
    (.../work-for-us/campaign-organiser-north-lancashire/) no longer serves a
    job; captured instead from the first div.job-card link on the list page
    (https://greenparty.org.uk/get-involved/work-for-us/supporter-care-manager/).
  - pac_job.html, eurobrussels_expired.html, eurobrussels_live.html,
    paylocity_jswall.html: fetched from the spec's default URLs unchanged.
    eurobrussels_live.html captures
    /job_display/292473/Policy_Strategist_Economist_ESM_European_Stability_Mechanism_Luxembourg_Luxembourg.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from src.enrichment.readability_enricher import enrich_jobs
from src.models.job import Job

FIXTURES = Path(__file__).parent / "fixtures"

PAC_CFG = {
    "content_scope": "article.pa_jobs",
    "labelled_fields": {
        "organisation": "Organization",
        "location": "Location",
        "posted_date": "Date Posted",
        "posted_date_format": "%m/%d/%Y",
    },
}
GREEN_PARTY_CFG = {
    "content_scope": "div.entry-content",
    "labelled_fields": {
        "closing_date": "Closing Date",
        "closing_date_format": "%d %b %Y",
    },
}
EUROBRUSSELS_CFG = {"org_from_page": True}


def _load(name: str) -> str:
    return (FIXTURES / name).read_text()


async def _enrich_one_job(job: Job, source_cfg: dict, fixture: str) -> Job:
    with patch(
        "src.enrichment.readability_enricher._fetch_html",
        AsyncMock(return_value=_load(fixture)),
    ):
        await enrich_jobs([job], source_configs={job.source_name: source_cfg}, delay=0)
    return job


@pytest.mark.asyncio
async def test_pac_labelled_fields_and_consent_strip():
    job = Job(
        title="Manager, Government Relations",
        url="https://pac.org/job/manager-government-relations-21",
        organisation="Public Affairs Council Jobs",
        description="",
        source_name="Public Affairs Council Jobs",
        category="us-government-affairs",
        country="us",
    )
    await _enrich_one_job(job, PAC_CFG, "pac_job.html")

    assert "To provide the best experiences" not in job.description
    assert "International Dairy Foods Association" in job.description
    assert job.organisation == "International Dairy Foods Association (IDFA)"
    assert job.location == "Washington, DC"
    assert job.posted_date == "2026-04-23"
    assert job.description_source == "structured"


@pytest.mark.asyncio
async def test_green_party_consent_strip_and_closing_date():
    job = Job(
        title="Supporter Care Manager",
        url="https://greenparty.org.uk/get-involved/work-for-us/supporter-care-manager/",
        organisation="Green Party of England and Wales",
        description="",
        source_name="Green Party",
        category="political-parties",
        country="uk",
    )
    await _enrich_one_job(job, GREEN_PARTY_CFG, "greenparty_job.html")

    assert "To provide the best experiences" not in job.description
    assert "About This Role" in job.description
    assert job.closing_date == "2026-06-18"


@pytest.mark.asyncio
async def test_eurobrussels_expired_page_is_dropped():
    job = Job(
        title="Senior Policy Adviser",
        url="https://www.eurobrussels.com/job_display/289254/Senior_Policy_Adviser_EUROPEX_Association_of_European_Energy_Exchanges_Brussels_Belgium",
        organisation="EuroBrussels",
        description="",
        source_name="EuroBrussels",
        category="eu-affairs",
        country="brussels",
    )
    await _enrich_one_job(job, EUROBRUSSELS_CFG, "eurobrussels_expired.html")

    assert job._dead_page is True
    # Pipeline drop filter (src/pipeline.py) applied directly here.
    survivors = [j for j in [job] if not getattr(j, "_dead_page", False)]
    assert survivors == []


@pytest.mark.asyncio
async def test_eurobrussels_live_page_org_location_deadline():
    job = Job(
        title="Policy Strategist/Economist",
        url="https://www.eurobrussels.com/job_display/292473/Policy_Strategist_Economist_ESM_European_Stability_Mechanism_Luxembourg_Luxembourg",
        organisation="EuroBrussels",
        description="",
        source_name="EuroBrussels",
        category="eu-affairs",
        country="brussels",
    )
    await _enrich_one_job(job, EUROBRUSSELS_CFG, "eurobrussels_live.html")

    assert job.organisation == "ESM - European Stability Mechanism"
    assert "_" not in job.organisation
    assert job.location
    assert job.closing_date is not None
    assert re_matches_iso_date(job.closing_date)


@pytest.mark.asyncio
async def test_paylocity_js_wall_body_refused():
    job = Job(
        title="Some Job",
        url="https://recruiting.paylocity.com/recruiting/jobs/All/43d988e3-6446-4a25-8e28-28602ea60858/careers",
        organisation="Some Employer",
        description="",
        source_name="Some Paylocity Source",
        category="us-government-affairs",
        country="us",
    )
    await _enrich_one_job(job, {}, "paylocity_jswall.html")

    assert job.description == ""
    assert job.description_source == "none"
    assert getattr(job, "_dead_page", False) is False


@pytest.mark.asyncio
async def test_fail_loud_never_returns_page_chrome_as_body():
    job = Job(
        title="Some Job",
        url="https://recruiting.paylocity.com/recruiting/jobs/All/43d988e3-6446-4a25-8e28-28602ea60858/careers",
        organisation="Some Employer",
        description="",
        source_name="Some Paylocity Source",
        category="us-government-affairs",
        country="us",
    )
    await _enrich_one_job(job, {}, "paylocity_jswall.html")

    assert "enable javascript" not in job.description.lower()
    assert job.description == ""


def re_matches_iso_date(value: str) -> bool:
    import re

    return bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", value))
