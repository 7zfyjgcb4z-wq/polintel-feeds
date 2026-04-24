# polintel-feeds

RSS feed generator for UK, Brussels/EU, and US political and policy sector jobs. Scrapes government departments, EU institutions, congressional offices, think tanks, NGOs, political parties, public affairs firms, trade associations, and fellowship programmes daily. Feeds are published to GitHub Pages and consumed by the Pol-Intel platform.

## Feeds

Live feeds at `https://7zfyjgcb4z-wq.github.io/polintel-feeds/`:

### UK

| Feed | File |
|------|------|
| Government & Public Sector | `uk-government.xml` |
| Think Tanks | `uk-think-tanks.xml` |
| Political Parties | `uk-political-parties.xml` |
| Public Affairs & Lobbying | `uk-public-affairs.xml` |
| NGOs & Charities | `uk-ngos.xml` |
| Fellowships & Early Career | `uk-fellowships.xml` |
| Trade Associations | `uk-trade-associations.xml` |
| General | `uk-general.xml` |

### Brussels / EU

| Feed | File |
|------|------|
| EU Affairs | `brussels-eu-affairs.xml` |
| EU Institutions | `brussels-eu-institutions.xml` |
| Think Tanks | `brussels-think-tanks.xml` |
| NGOs | `brussels-ngos.xml` |
| International Organisations | `brussels-international-orgs.xml` |
| Fellowships | `brussels-fellowships.xml` |

### United States

| Feed | File |
|------|------|
| Federal Government | `us-us-federal.xml` |
| Congress & Capitol Hill | `us-us-congress.xml` |
| Think Tanks | `us-us-think-tanks.xml` |
| Government Affairs & Lobbying | `us-us-government-affairs.xml` |
| NGOs & Advocacy | `us-us-ngos.xml` |
| Policy Fellowships | `us-us-fellowships.xml` |
| Campaigns & Political Parties | `us-us-campaigns.xml` |

Feed index: `https://7zfyjgcb4z-wq.github.io/polintel-feeds/`  
Run status: `https://7zfyjgcb4z-wq.github.io/polintel-feeds/status.json`  
Health alerts: `https://7zfyjgcb4z-wq.github.io/polintel-feeds/alerts.json`

## Architecture

```
src/
  cli.py                      # Click CLI: run, feeds, sources, test
  pipeline.py                 # Orchestration: scrapers → DB → feeds → alerts
  config/
    sources.yaml              # UK sources
    sources-brussels.yaml     # Brussels/EU sources
    sources-us.yaml           # US sources
    categories.yaml           # Category keyword rules
  scrapers/
    base.py                   # BaseScraper ABC + fetch_with_retry utility
    dedicated/                # Hand-written Tier 1 scrapers
    selector_scraper.py       # CSS-selector Tier 2 scraper
    rss_feed_scraper.py       # RSS/Atom Tier 2 scraper
    ats_detector.py           # ATS platform detection
    ats_extractors.py         # ATS-specific extractors
  db/
    store.py                  # SQLite job store with dedup, stale/purge thresholds
  enrichment/
    readability_enricher.py   # Fetches job pages, extracts description + JSON-LD metadata
  feed/
    generator.py              # RSS XML generation, status.json, alerts.json
  models/
    job.py                    # Job dataclass
```

**Tier 1 (dedicated scrapers):** Hand-written per-source scrapers handling APIs, pagination, ALTCHA challenges, sitemaps, and third-party data feeds. New sources requiring custom logic go here.

**Tier 2 (selector / RSS / ATS-auto):** Zero-API scrapers driven entirely by source config in the YAML. Add a new selector source without writing any Python.

**Enrichment:** After scraping, jobs with descriptions shorter than 200 characters have their job page fetched. The readability library extracts the main content; any `JobPosting` JSON-LD on the page is also parsed to backfill `organisation`, `location`, and `closing_date` where absent.

**Staleness alerts:** `feeds/alerts.json` is generated after each run. It reports sources that returned zero results after previously returning jobs, sources that have failed three consecutive runs, and upstream data sources (e.g. the House Employment Bulletin feed) that have not been updated within their expected cadence.

## RSS extension: partisan_lean (US feeds only)

US job items include an optional `<polintel:partisanLean>` element indicating the ideological lean of the hiring organisation, where known.

```xml
<rss xmlns:polintel="https://pol-intel.com/rss-ext/1.0">
  <channel>
    <item>
      <title>Senior Policy Analyst</title>
      <polintel:partisanLean>centre-left</polintel:partisanLean>
    </item>
  </channel>
</rss>
```

**Namespace URI:** `https://pol-intel.com/rss-ext/1.0`  
**Element:** `polintel:partisanLean`  
**Values:** `left` · `centre-left` · `centre` · `centre-right` · `right` · `nonpartisan` · `unknown`

UK and Brussels feeds do not include this element. The field is omitted entirely rather than emitted as empty when the lean is unknown.

## Environment variables

| Variable | Required for | Description |
|----------|-------------|-------------|
| `ANTHROPIC_API_KEY` | UK Tier 2 generic scrapers | Claude API key for AI-based extraction. Not needed if running `--skip-ai`. |
| `USAJOBS_API_KEY` | US federal jobs (`us-us-federal.xml`, `us-us-fellowships.xml`) | Free API key from [developer.usajobs.gov](https://developer.usajobs.gov/APIRequest/Index). |
| `USAJOBS_USER_AGENT` | US federal jobs | Registrant email address, passed as the USAJobs API `User-Agent`. |
| `GITHUB_TOKEN` | US Congress feed (`us-us-congress.xml`) | Passed to the GitHub API when fetching `dwillis/house-jobs` JSON. Available automatically in GitHub Actions; optional locally (unauthenticated calls are sufficient for the small number of requests made). |

## Running locally

**Prerequisites:** Python 3.11+.

```bash
git clone https://github.com/7zfyjgcb4z-wq/polintel-feeds
cd polintel-feeds
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Run UK scrapers
python3 -m src.cli run --country uk

# Run Brussels scrapers
python3 -m src.cli run --country brussels

# Run US scrapers (requires USAJOBS_API_KEY + USAJOBS_USER_AGENT)
python3 -m src.cli run --country us

# Regenerate feeds from existing DB without scraping
python3 -m src.cli feeds

# List all configured sources for a region
python3 -m src.cli sources --country us

# Test a single source
python3 -m src.cli test --source "CharityJob"
```

Output: `data/jobs.db` (SQLite), `feeds/` (RSS XML files), `feeds/status.json`, `feeds/alerts.json`.

## Adding a new source

**Tier 2 — selector (no code required):** Add an entry to the relevant `sources-<region>.yaml`:

```yaml
- name: "My Organisation"
  url: "https://example.org/jobs"
  category: "think-tanks"
  country: "us"                 # uk | brussels | us
  scraper: "selector"
  selectors:
    job_card: "li.job-item"
    title: "h2 a"
    link: "h2 a"
  org_static: "My Organisation"
  enabled: true
```

**Tier 1 — dedicated (for APIs, sitemaps, complex logic):** Create `src/scrapers/dedicated/my_source.py` with a `Scraper(BaseScraper)` class implementing `async def scrape() -> list[Job]`. Add to the YAML with `scraper: dedicated` and `module: my_source`.

## Categories

### UK

| Slug | Description |
|------|-------------|
| `government` | Government departments, agencies, regulators, devolved governments |
| `think-tanks` | Policy research institutes and think tanks |
| `political-parties` | UK political parties |
| `public-affairs` | Public affairs, lobbying, and strategic communications firms |
| `ngos` | NGOs, charities, and civil society organisations |
| `fellowships` | Fellowships, internships, and early career programmes |
| `trade-associations` | Trade bodies and employer associations |
| `general` | General political/policy sector job boards |

### Brussels / EU

| Slug | Description |
|------|-------------|
| `eu-institutions` | EU institutions and agencies (Commission, Parliament, Council) |
| `eu-affairs` | EU affairs, public affairs, and Brussels-based consultancies |
| `think-tanks` | Brussels-based think tanks and policy institutes |
| `ngos` | Brussels-based NGOs and civil society |
| `fellowships` | EU traineeships and policy fellowships |
| `international-orgs` | NATO, OECD, and other intergovernmental organisations |

### United States

| Slug | Description |
|------|-------------|
| `us-federal` | Federal government jobs via USAJobs API |
| `us-congress` | Congressional member and committee office jobs (HVAPS bulletin) |
| `us-think-tanks` | Washington DC think tanks and policy institutes |
| `us-government-affairs` | Government affairs, lobbying, and public affairs firms |
| `us-ngos` | US NGOs, nonprofits, and advocacy organisations |
| `us-fellowships` | Federal fellowship and internship programmes (PMF, Pathways, etc.) |
| `us-campaigns` | Political campaigns, party organisations, and electoral roles |

## Scheduled runs

| Workflow | Schedule | Region |
|----------|----------|--------|
| `scrape-uk.yml` | 06:00 UTC daily | UK |
| `scrape-brussels.yml` | 08:00 UTC daily | Brussels/EU |
| `scrape-us.yml` | 13:00 UTC daily | United States |

Results are committed back to the repository with `[skip ci]` in the message and served via GitHub Pages. Each run generates an updated `status.json` and `alerts.json`.

**Required secrets (GitHub repository settings → Secrets):**

| Secret | Used by |
|--------|---------|
| `ANTHROPIC_API_KEY` | `scrape-uk.yml` |
| `USAJOBS_API_KEY` | `scrape-us.yml` |
| `USAJOBS_USER_AGENT` | `scrape-us.yml` |

`GITHUB_TOKEN` is provided automatically by GitHub Actions and does not need to be set as a secret.

## Known gaps

| Gap | Reason | Workaround / next step |
|-----|--------|------------------------|
| **Senate employment** | Senate Employment Office HTML blocks automated access (403). No maintained open-source scraper exists; one known project (`c0nnortb/senate_employment`) is abandoned. | Next-session priority. Would require either a maintained upstream equivalent of `dwillis/house-jobs`, or direct contact with the Senate Employment Office for a data feed. |
| **Workday-hosted organisations** | Workday renders job listings entirely in JavaScript. The ATS auto-detector identifies Workday but the pipeline has no Workday extractor. Affected US sites include Urban Institute, RAND, and others. | Add a Workday extractor to `src/scrapers/ats_extractors.py`. Several UK sources face the same blocker. |
| **Tom Manatos Jobs** | Protected by Cloudflare challenge mode. Returns HTTP 200 in CI but serves a JavaScript challenge page; no job cards are parsed. Browser headers alone are insufficient. | Re-enable once Playwright + a Cloudflare solver (e.g. `unblock-origin`) is added to the pipeline. See `sources-us.yaml` for the disabled entry. |
| **Idealist** | Job listings are JavaScript-rendered. A dedicated scraper module exists (`src/scrapers/dedicated/idealist.py`) but requires Playwright to function. Currently disabled. | Re-enable once Playwright is added to the pipeline and CI workflow. |
| **Brad Traverse / OPA Jobs** | Paid subscription required. No free tier or public feed identified. | Consider direct partnership or subscription if Capitol Hill coverage needs to be expanded. |
