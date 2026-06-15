# polintel-feeds

RSS feed generator for UK, Brussels/EU, US, and EU national political and policy sector jobs. Scrapes government departments, EU institutions, congressional offices, think tanks, NGOs, political parties, public affairs firms, political foundations, trade associations, and fellowship programmes daily. Feeds are published to GitHub Pages and consumed by the Pol-Intel platform.

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

### EU National — DACH (configured, rollout in progress)

| Feed | File |
|------|------|
| National Politics (DE/AT) | `dach-national-politics.xml` |
| Public Affairs (DE/AT) | `dach-public-affairs.xml` |
| Think Tanks (DE/AT) | `dach-think-tanks.xml` |
| Political Foundations | `dach-foundations.xml` |
| Political Parties (DE/AT) | `dach-political-parties.xml` |
| Trade Associations (DE/AT) | `dach-trade-associations.xml` |

### EU National — Southern Europe (configured, rollout in progress)

| Feed | File |
|------|------|
| National Politics (FR/ES/IT/PT/GR) | `southern-national-politics.xml` |
| Think Tanks | `southern-think-tanks.xml` |
| Political Parties (FR/ES/IT) | `southern-political-parties.xml` |
| Public Affairs (FR/ES/IT) | `southern-public-affairs.xml` |
| Trade Associations (FR/ES/IT) | `southern-trade-associations.xml` |

### EU National — Benelux (configured, rollout in progress)

| Feed | File |
|------|------|
| Political Parties (NL) | `benelux-political-parties.xml` |
| National Politics (NL) | `benelux-national-politics.xml` |
| Think Tanks (NL) | `benelux-think-tanks.xml` |

### EU National — Nordics (configured, rollout in progress)

| Feed | File |
|------|------|
| Think Tanks (SE/DK/FI/NO) | `nordics-think-tanks.xml` |
| National Politics (SE/DK/FI) | `nordics-national-politics.xml` |

### EU National — CEE + Ireland (configured, rollout in progress)

| Feed | File |
|------|------|
| Think Tanks (IE/PL/CZ) | `cee-think-tanks.xml` |
| National Politics (IE/PL/CZ) | `cee-national-politics.xml` |

### Pan-European Backbone (configured, rollout in progress)

| Feed | File |
|------|------|
| EU Affairs | `pan-eu-eu-affairs.xml` |
| International Organisations | `pan-eu-international-orgs.xml` |

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
    sources-dach.yaml         # EU national: DACH (DE, AT)
    sources-southern.yaml     # EU national: Southern Europe (FR, ES, IT, PT, GR)
    sources-benelux.yaml      # EU national: Benelux (NL; BE deferred)
    sources-nordics.yaml      # EU national: Nordics (SE, DK, FI, NO)
    sources-cee.yaml          # EU national: CEE + Ireland (IE, PL, CZ + long tail)
    sources-pan-eu.yaml       # Pan-European backbone (not country-specific)
    categories.yaml           # Category keyword rules
  scrapers/
    base.py                   # BaseScraper ABC + fetch_with_retry utility
    dedicated/                # Hand-written Tier 1 scrapers
    selector_scraper.py       # CSS-selector Tier 2 scraper
    rss_feed_scraper.py       # RSS/Atom Tier 2 scraper
    ats_detector.py           # ATS platform detection
    ats_extractors/           # ATS-specific extractors (package: greenhouse, lever, teamtailor, applied, default stub)
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

**EU national sources** use `ats_auto` throughout — the runtime ATS detector probes each URL for a known platform (Greenhouse, Lever, Workday, Personio, TeamTailor, etc.) and routes to the matching extractor, falling back to generic AI extraction when no platform is recognised. Whole-of-government portals (Bund.de, Selor, PublicJobs.ie, etc.) are deliberately excluded; only dedicated political boards, think tanks, foundations, and curated party/parliament pages are in scope.

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

# Run EU national regions
python3 -m src.cli run --country dach
python3 -m src.cli run --country southern
python3 -m src.cli run --country benelux
python3 -m src.cli run --country nordics
python3 -m src.cli run --country cee
python3 -m src.cli run --country pan-eu

# Regenerate feeds from existing DB without scraping
python3 -m src.cli feeds

# List all configured sources for a region
python3 -m src.cli sources --country dach

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
| `general` | General UK political/policy sector job boards; excludes UN and international organisation listings (covered by dedicated feeds) |

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

### EU National (all regions)

| Slug | Used in | Description |
|------|---------|-------------|
| `national-politics` | dach, southern, benelux, nordics, cee | National parliaments, dedicated political job boards, party HQ roles |
| `public-affairs` | dach, southern | Public affairs, government relations, political communications firms |
| `think-tanks` | dach, southern, benelux, nordics, cee | National think tanks and foreign policy institutes |
| `foundations` | dach | German and Austrian political foundations (Stiftungen) |
| `political-parties` | dach, southern, benelux | National party organisations |
| `trade-associations` | dach, southern | National trade bodies with significant public affairs functions |
| `eu-affairs` | pan-eu | Pan-European EU affairs and public affairs job boards |
| `international-orgs` | pan-eu | Pan-European international organisation jobs |

## Scheduled runs

| Workflow | Schedule | Region |
|----------|----------|--------|
| `scrape-uk.yml` | 06:00 UTC daily | UK |
| `scrape-brussels.yml` | 08:00 UTC daily | Brussels/EU |
| `scrape-eu-national.yml` | 09:30 UTC daily | DACH + Southern + Benelux + Nordics + CEE |
| `scrape-pan-eu.yml` | 10:00 UTC daily | Pan-European backbone |
| `scrape-us.yml` | 13:00 UTC daily | United States |

Results are committed back to the repository with `[skip ci]` in the message and served via GitHub Pages. Each run generates an updated `status.json` and `alerts.json`.

**Required secrets (GitHub repository settings → Secrets):**

| Secret | Used by |
|--------|---------|
| `ANTHROPIC_API_KEY` | `scrape-uk.yml`, `scrape-eu-national.yml`, `scrape-pan-eu.yml` |
| `USAJOBS_API_KEY` | `scrape-us.yml` |
| `USAJOBS_USER_AGENT` | `scrape-us.yml` |

`GITHUB_TOKEN` is provided automatically by GitHub Actions and does not need to be set as a secret.

## Known gaps

| Gap | Reason | Workaround / next step |
|-----|--------|------------------------|
| **Senate employment** | Senate Employment Office HTML blocks automated access (403). No maintained open-source scraper exists; one known project (`c0nnortb/senate_employment`) is abandoned. | Next-session priority. Would require either a maintained upstream equivalent of `dwillis/house-jobs`, or direct contact with the Senate Employment Office for a data feed. |
| **Workday-hosted organisations** | Workday renders job listings entirely in JavaScript. The ATS auto-detector identifies Workday but the pipeline has no Workday extractor. Affected US sites include Urban Institute, RAND, and others. | Add a Workday extractor to `src/scrapers/ats_extractors/`. Several UK sources face the same blocker. |
| **Tom Manatos Jobs** | Protected by Cloudflare challenge mode. Returns HTTP 200 in CI but serves a JavaScript challenge page; no job cards are parsed. Browser headers alone are insufficient. | Re-enable once Playwright + a Cloudflare solver (e.g. `unblock-origin`) is added to the pipeline. See `sources-us.yaml` for the disabled entry. |
| **Idealist** | Job listings are JavaScript-rendered. A dedicated scraper module exists (`src/scrapers/dedicated/idealist.py`) but requires Playwright to function. Currently disabled. | Re-enable once Playwright is added to the pipeline and CI workflow. |
| **Brad Traverse / OPA Jobs** | Paid subscription required. No free tier or public feed identified. | Consider direct partnership or subscription if Capitol Hill coverage needs to be expanded. |
