from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.enrichment.readability_enricher import enrich_description, enrich_jobs
from src.models.job import Job

SAMPLE_JOB_HTML = """
<html>
<head><title>Policy Analyst — Chatham House</title></head>
<body>
  <nav>Navigation menu here</nav>
  <main>
    <h1>Policy Analyst</h1>
    <p>Chatham House is seeking an experienced Policy Analyst to join our Europe Programme.
    The successful candidate will conduct original research, write policy briefs, and engage
    with senior policymakers across the UK and EU. You will have a strong academic background
    in European politics or international relations, with excellent written and verbal
    communication skills. This is a full-time permanent role based in London.</p>
    <p>Salary: £38,000 – £45,000 depending on experience. 25 days annual leave plus bank holidays.
    Flexible and hybrid working arrangements available. Closing date: 30 May 2026.</p>
  </main>
  <footer>Footer content here</footer>
</body>
</html>
"""


def _make_mock_response(html: str, status_code: int = 200):
    mock = MagicMock()
    mock.status_code = status_code
    mock.text = html
    return mock


@pytest.mark.asyncio
async def test_enrich_description_returns_text():
    mock_resp = _make_mock_response(SAMPLE_JOB_HTML)
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.get = AsyncMock(return_value=mock_resp)

    with patch("src.enrichment.readability_enricher.httpx.AsyncClient", return_value=mock_client):
        result = await enrich_description("https://example.com/jobs/1")

    assert result is not None
    assert len(result) > 50
    assert "Policy Analyst" in result or "Chatham House" in result


@pytest.mark.asyncio
async def test_enrich_description_skips_substantive_existing():
    existing = "x" * 250
    result = await enrich_description("https://example.com/jobs/1", existing_description=existing)
    assert result == existing


@pytest.mark.asyncio
async def test_enrich_description_returns_none_on_http_error():
    mock_resp = _make_mock_response("", status_code=404)
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.get = AsyncMock(return_value=mock_resp)

    with patch("src.enrichment.readability_enricher.httpx.AsyncClient", return_value=mock_client):
        result = await enrich_description("https://example.com/jobs/1")

    assert result is None


@pytest.mark.asyncio
async def test_enrich_description_returns_none_on_exception():
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.get = AsyncMock(side_effect=Exception("Connection refused"))

    with patch("src.enrichment.readability_enricher.httpx.AsyncClient", return_value=mock_client):
        result = await enrich_description("https://example.com/jobs/1")

    assert result is None


@pytest.mark.asyncio
async def test_enrich_description_truncates_long_content():
    long_html = f"<html><body><main><p>{'word ' * 2000}</p></main></body></html>"
    mock_resp = _make_mock_response(long_html)
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.get = AsyncMock(return_value=mock_resp)

    with patch("src.enrichment.readability_enricher.httpx.AsyncClient", return_value=mock_client):
        result = await enrich_description("https://example.com/jobs/1")

    assert result is not None
    assert len(result) <= 5000


@pytest.mark.asyncio
async def test_enrich_jobs_updates_thin_descriptions():
    jobs = [
        Job(title="Policy Lead", url="https://example.com/jobs/1",
            organisation="Org", description="Short", source_name="test"),
    ]

    mock_resp = _make_mock_response(SAMPLE_JOB_HTML)
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.get = AsyncMock(return_value=mock_resp)

    with patch("src.enrichment.readability_enricher.httpx.AsyncClient", return_value=mock_client):
        with patch("src.enrichment.readability_enricher.asyncio.sleep", new_callable=AsyncMock):
            result = await enrich_jobs(jobs, concurrency=1, delay=0)

    assert len(result[0].description) > 50


@pytest.mark.asyncio
async def test_enrich_jobs_skips_substantive_descriptions():
    long_desc = "x" * 300
    jobs = [
        Job(title="Policy Lead", url="https://example.com/jobs/1",
            organisation="Org", description=long_desc, source_name="test"),
    ]

    with patch("src.enrichment.readability_enricher.httpx.AsyncClient") as mock_cls:
        result = await enrich_jobs(jobs, concurrency=1, delay=0)

    # httpx.AsyncClient should never have been instantiated
    mock_cls.assert_not_called()
    assert result[0].description == long_desc
