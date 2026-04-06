# polintel-feeds

RSS feed generator for UK and Brussels/EU political and policy sector jobs. Scrapes government departments, EU institutions, think tanks, NGOs, political parties, public affairs firms, trade associations, and fellowship programmes daily. Feeds are published to GitHub Pages and consumed by the Pol-Intel platform.

## Feeds

Live feeds at `https://7zfyjgcb4z-wq.github.io/polintel-feeds/`:

### UK

| Feed | URL |
|------|-----|
| Government & Public Sector | `uk-government.xml` |
| Think Tanks | `uk-think-tanks.xml` |
| Political Parties | `uk-political-parties.xml` |
| Public Affairs & Lobbying | `uk-public-affairs.xml` |
| NGOs & Charities | `uk-ngos.xml` |
| Fellowships & Early Career | `uk-fellowships.xml` |
| Trade Associations | `uk-trade-associations.xml` |
| General | `uk-general.xml` |

### Brussels / EU

| Feed | URL |
|------|-----|
| EU Affairs (Brussels) | `brussels-eu-affairs.xml` |
| EU Institutions | `brussels-eu-institutions.xml` |
| Think Tanks (Brussels) | `brussels-think-tanks.xml` |
| NGOs (Brussels) | `brussels-ngos.xml` |
| International Organisations | `brussels-international-orgs.xml` |
| Fellowships (Brussels) | `brussels-fellowships.xml` |

Feed index: `https://7zfyjgcb4z-wq.github.io/polintel-feeds/`
Run status: `https://7zfyjgcb4z-wq.github.io/polintel-feeds/status.json`

## Architecture

```
src/
  cli.py                  # Click CLI: run, feeds, sources, test
  pipeline.py             # Orchestration: dedicated + generic scrapers → DB → feeds
  config/
    sources.yaml          # All sources: Tier 1 (dedicated) and Tier 2 (generic AI)
  scrapers/
    base.py               # BaseScraper ABC + fetch_with_retry utility
    generic.py            # Claude AI extractor for Tier 2 sources
    dedicated/            # Hand-written scrapers for Tier 1 sources
  db/
    store.py              # SQLite job store with dedup and page hash caching
  feed/
    generator.py          # RSS XML generation via feedgen, status.json
  models/
    job.py                # Job dataclass
```

**Tier 1 (dedicated scrapers):** Civil Service Jobs, CharityJob, myjobscotland, NICS, LGA Jobs, Third Sector Jobs, jobs.ac.uk — hand-written per-site scrapers that handle pagination, ALTCHA challenges, and APIs.

**Tier 2 (generic AI scrapers):** ~100 think tanks, government bodies, political parties, and NGOs scraped via Claude API. Content hash caching means the API is only called when a page changes. Sources are batched in thirds so ~33 run per day, keeping API costs low.

## Running locally

**Prerequisites:** Python 3.11+, `ANTHROPIC_API_KEY` environment variable (for Tier 2 scrapers).

```bash
# Set up
git clone https://github.com/7zfyjgcb4z-wq/polintel-feeds
cd polintel-feeds
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Run all scrapers (Tier 1 + Tier 2)
python3 -m src.cli run

# Run without Tier 2 AI scrapers (no API key needed)
python3 -m src.cli run --skip-ai

# Regenerate feeds from existing DB without scraping
python3 -m src.cli feeds

# List all configured sources
python3 -m src.cli sources

# Test a single source (dedicated)
python3 -m src.cli test --source "CharityJob"

# Test a single generic source (calls Claude API — ~1 API call)
python3 -m src.cli test --source "IPPR"

# Dry-run a generic source (fetches page, skips API call)
python3 -m src.cli test --source "IPPR" --dry-run
```

Output: `data/jobs.db` (SQLite), `feeds/uk-*.xml` (RSS), `feeds/status.json`.

## Adding a new source

**Tier 2 (generic, no code required):** Add an entry to `src/config/sources.yaml`:

```yaml
- name: "My Organisation"
  url: "https://example.org/jobs"
  category: "think-tanks"      # government | think-tanks | ngos | political-parties
                               # public-affairs | fellowships | trade-associations | general
  country: "uk"
  scraper: "generic"
  enabled: true
```

Test it: `python3 -m src.cli test --source "My Organisation" --dry-run`
Then live: `python3 -m src.cli test --source "My Organisation"`

**Tier 1 (dedicated, for complex sites):** Create `src/scrapers/dedicated/my_source.py` with a `Scraper(BaseScraper)` class implementing `async def scrape() -> list[Job]`. Add to `sources.yaml` with `scraper: "dedicated"` and `module: "my_source"`.

## Categories

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

## Scheduled runs

A GitHub Actions workflow (`scrape-uk.yml`) runs daily at 06:00 UTC. Results are committed back to the repo and served via GitHub Pages. Set `ANTHROPIC_API_KEY` in repository secrets to enable Tier 2 scrapers.
