"""Political Job Hunt: description and organisation come from JSON-LD at ingest."""
from src.models.job import Job
from src.scrapers.dedicated.political_job_hunt import apply_job_ld

LD_HTML = '''<script type="application/ld+json">{"@context":"https://schema.org","@type":"JobPosting",
"title":"Government Affairs Manager","hiringOrganization":{"@type":"Organization","name":"Acme Energy"},
"description":"<p>Lead our state government affairs programme.</p><p>You will brief legislators and track bills across the region.</p>",
"validThrough":"2026-11-30T00:00:00Z"}</script>'''


def _job() -> Job:
    return Job(title="Government Affairs Manager", url="https://www.politicaljobhunt.com/jobs/government-affairs-manager-ab12cd34",
               organisation="Political Job Hunt", description="", source_name="Political Job Hunt")


def test_ld_fills_description_and_org():
    from src.enrichment.readability_enricher import parse_job_ld
    job = _job()
    assert apply_job_ld(job, parse_job_ld(LD_HTML)) is True
    assert job.organisation == "Acme Energy"
    assert "brief legislators" in job.description and "<p>" not in job.description
    assert job.description_source == "structured"
    assert job.closing_date == "2026-11-30"


def test_no_ld_leaves_description_empty_and_org_placeholder():
    from src.enrichment.readability_enricher import parse_job_ld
    job = _job()
    assert apply_job_ld(job, parse_job_ld("<html><body>no structured data</body></html>")) is False
    assert job.description == ""
    assert job.description_source == "none"
    assert job.organisation == "Political Job Hunt"


def test_short_ld_description_is_not_accepted():
    job = _job()
    assert apply_job_ld(job, {"organisation": "Acme", "description": "<p>See site.</p>"}) is False
    assert job.description == ""
    assert job.organisation == "Acme"   # org is still taken; it is independent of the body


def test_real_org_is_not_overwritten():
    job = _job(); job.organisation = "Already Real Org"
    apply_job_ld(job, {"organisation": "Other", "description": None})
    assert job.organisation == "Already Real Org"


def _scraper(known=()):
    from src.scrapers.dedicated.political_job_hunt import Scraper
    s = Scraper({"name": "Political Job Hunt", "url": "https://www.politicaljobhunt.com"})
    s.known_urls = set(known)
    return s


def _run_read(monkeypatch, scraper, jobs, budget=240.0):
    import asyncio
    import types
    from src.scrapers.dedicated import political_job_hunt as m
    fetched = []

    async def fake_fetch(client, url, retries=3):
        fetched.append(url)
        return types.SimpleNamespace(text=LD_HTML)

    async def no_sleep(_):
        return None

    monkeypatch.setattr(m, "fetch_with_retry", fake_fetch)
    monkeypatch.setattr(m.asyncio, "sleep", no_sleep)
    monkeypatch.setattr(m, "DETAIL_BUDGET_SECONDS", budget)
    asyncio.run(scraper._read_job_ld(jobs))
    return fetched


def test_known_urls_are_not_fetched(monkeypatch):
    a, b = _job(), _job()
    b.url += "-new"
    fetched = _run_read(monkeypatch, _scraper(known=[a.url]), [a, b])
    assert fetched == [b.url]
    assert a.description == "" and b.description


def test_time_budget_stops_fetching(monkeypatch):
    jobs = [_job() for _ in range(3)]
    fetched = _run_read(monkeypatch, _scraper(), jobs, budget=0.0)
    assert fetched == []
    assert all(j.description == "" for j in jobs)
