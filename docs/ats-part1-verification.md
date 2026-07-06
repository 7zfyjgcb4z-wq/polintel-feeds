# ATS Part 1 verification: Greenhouse, BambooHR, Personio, Workday

Date: 2026-07-06. Branch `feat/ats-part1-verification` off `main` (`13275de`). Scope: this is
Phase 0 / Brief 1 of `feeds-source-expansion-plan-2026-07-06.md` — the harness that gates the
~76 EU-national/internship-graduate sources currently `enabled: false` behind "GATED: disabled
until ATS extractor Part 1 verified".

## Pre-build verification (read-only, before any code was written)

### (a) Live Supabase `rss_sources` / `fetch-rss` ingestion of EU-national and pan-EU feeds

**Not verified — no live Supabase access in this session, and this is explicitly still an open
question in the vault as of today.** `STATUS.md`'s 2026-07-06 entry and assumption A1 in
`feeds-source-expansion-plan-2026-07-06.md` both flag the same unresolved conflict: the four
Stage 1 EU sources (Parlamentjobs.de, Politik-Kommunikation, Emplois Politiques, NEOS) show
`enabled: true` in the merged `polintel-feeds` configs, while `STATUS.md`'s "Live next actions"
still lists "Enable EU Stage 1 sources" as outstanding. Neither claim has been reconciled against
the live `rss_sources` table or `fetch_logs`. This repo has no Supabase credentials or read path
(by design — `polintel-feeds` never talks to Supabase), so it cannot be checked from here.

**Owner action needed:** run the read-only check the plan specifies — inspect `rss_sources` for
the `dach-*.xml` / `southern-*.xml` / etc. GitHub Pages URLs, and `fetch_logs` for recent
successful fetches of them — against Supabase project `cnyjrdbbzvidcbtrwacq`, and record the
answer in the vault (`notes/STATUS.md`, resolving assumption A1). This does not block Part 1
verification itself (a pure extractor/transport exercise with no Supabase dependency), but it
does block Brief 2 (Wave 1 enablement), whose precondition is "assumption A1 resolved."

### (b) Whether Stage 0 B2 and its acceptance test ran after 2026-07-03

**Ran on 2026-07-03, not after — verified from repo history, not "after" as literally asked.**
In the `blank-canvas` clone:

- `334537e` "stage0: deterministic description-quality scoring in fetch-rss" — committed
  2026-07-03T12:43:55+02:00.
- `624bb0c` "stage2: fetch-rss receives Stage 1 transport fields" — committed
  2026-07-03T13:18:09+02:00, thirty-five minutes later.

Stage 2 edits the same file as Stage 0 and is documented (`notes/feeds-build-status-2026-07-03.md`)
as deployed and re-verified same day ("Stage 2 — RE-VERIFIED 2026-07-03, Gate C CLOSED. Deployed
11:16 UTC"), which is only possible if Stage 0's B2 UPDATE, deploy and acceptance test had already
landed. The build-status note's own Stage 0 section confirms the unblock happened same-day:
"RESOLVED (2026-07-03): keep the row flagged ... Stage 0 is unblocked: run B2 + deploy + acceptance
test," immediately followed by the Stage 2 deploy record forty-odd minutes later in wall-clock
commit time. So: **B2 and the acceptance test ran on 2026-07-03, before Stage 2's same-day deploy,
not on a later date.** No evidence of any re-run since. This satisfies the plan's assumption A2 in
substance (Stage 0 confirmed closed before Wave 1) even though it did not literally happen "after"
2026-07-03.

### (c) Whether `origin/feature/location-extractor` still exists

**Confirmed deleted.** `git ls-remote --heads origin | grep location-extractor` returns nothing,
both before this branch was created and again after fast-forwarding local `main` to
`origin/main` (`13275de`). The vault's `feeds-build-status-2026-07-03.md` still listed deletion as
"[Pending]" as of 2026-07-03, and `feeds-source-expansion-plan-2026-07-06.md` (assumption A3) was
still treating this as unconfirmed on 2026-07-06 — the ref has evidently been deleted since. No
action taken here (nothing to merge or rebase onto; it doesn't exist).

---

## Method

For each of Greenhouse, BambooHR, Personio and Workday: fetched one real API response per
platform, once, politely (repo `User-Agent`, ≥1s between requests), from boards already present
and `enabled: true` in `src/config/*.yaml`. Committed unmodified as fixtures under
`tests/fixtures/ats/`. Wrote `tests/test_ats_extractors.py` against those fixtures (no network in
the test suite — `httpx.AsyncClient.get`/`.post` are patched). Separately ran live dry runs, and
regenerated a local feed from live-fixture data through the real `generate_feeds()` pipeline to
validate XML end to end.

## Per-platform verdict

### Greenhouse — VERIFIED, one defect found and fixed

Configured boards (`src/config/sources-us.yaml`): Truman National Security Project
(`trumanprojectjobs`), Manhattan Institute (`manhattaninstituteforpolicyresearchinc`). Both
attempted live:

- **Manhattan Institute: live, healthy.** `GET boards-api.greenhouse.io/v1/boards/manhattaninstituteforpolicyresearchinc/jobs?content=true`
  → 200, 4 jobs. 100% non-empty title/url/organisation/location/description; `description_source`
  100% `api`; description length 3,083–4,914 chars (median 4,071). `posted_date` 100% present
  (`first_published`). `closing_date` 0% (see defect below).
- **Truman National Security Project: dead board, confirmed 404.** `curl` direct: `404`, body
  `{"status":404,"error":"Job not found"}`. The extractor's own 404-handling fired correctly
  (logs a warning, returns `[]`, does not crash) — this is a config data-freshness issue (a stale
  token on an `enabled: true` source), not an extractor defect. Flagging for the owner/Brief 2;
  **no config YAML touched here**, per scope.

**Defect found and fixed:** the Greenhouse jobs API exposes `application_deadline` on every job
object (confirmed present as a key in the captured fixture, `null` on all four Manhattan Institute
postings), but `GreenhouseAPIExtractor` never read it, so `closing_date` was always `None`
regardless of what the platform reported. Fixed in `api_extractors.py`
(`closing_date = item.get("application_deadline")`, passed into the `Job(...)` call). Because the
live fixture's own deadlines are all null, `tests/test_ats_extractors.py` proves the mapping with
a second test that reuses the real payload with one job's `application_deadline` set to a
real-shaped value — the fixture test above already proves everything else end-to-end from
unmodified live data.

### BambooHR — VERIFIED

Configured boards (`sources-us.yaml`, `sources.yaml`): CNAS (`cnas`), E3G (`e3g`), SEC Newgate
(`secnewgateuk`). All three attempted live:

- **CNAS: 4 jobs**, 100% fields populated, `description_source` 100% `api`, description
  5,003–6,672 chars.
- **E3G: 1 job** ("PPCA Secretariat Coordinator, London"), fields fully populated, description
  7,386 chars real prose, `posted_date` = `2026-06-22` (`datePosted` from the detail endpoint).
  **This is the committed fixture** (`bamboohr_e3g_list.json` + `bamboohr_e3g_detail_257.json`).
- **SEC Newgate: honest zero.** `GET .../careers/list` → `200`, `{"meta":{"totalCount":0},"result":[]}`.
  Genuinely empty board, not an error — confirmed by direct `curl`.

`closing_date` is 0% across all three boards: the BambooHR detail payload's key set
(`jobOpeningShareUrl, jobOpeningName, jobOpeningStatus, jobCategoryId, departmentId,
departmentLabel, employmentStatusLabel, location, atsLocation, description, compensation,
datePosted, minimumExperience, locationType, seekPromoted`) carries no closing/deadline field at
all — an honest platform limitation, not an unmapped field. No code change needed or made.

### Personio — VERIFIED, one defect found and fixed

Configured boards (`sources-brussels.yaml`/`sources.yaml`, `sources-dach.yaml`): ECFR (`ecfr`),
NEOS (`neos`). Both attempted live:

- **ECFR: 2 jobs** ("Policy Fellow (m/f/d)", "Speculative Application"), 100% title/url/org/desc,
  location 100% (`Berlin`), description 113–7,906 chars. **This is the committed fixture**
  (`personio_ecfr.xml`).
- **NEOS: 12 jobs**, all fields populated, description 1,373–3,493 chars (median 2,677).

**Defect found and fixed:** the Personio XML feed carries a real `<createdAt>` timestamp on every
`<position>` (confirmed non-null on both ECFR positions: `2026-06-16T16:07:01+00:00` and
`2025-02-26T17:46:27+00:00`), but `PersonioAPIExtractor` never read it, so `posted_date` was always
`None` (confirmed 0% across both live boards before the fix). Fixed in `api_extractors.py`
(`position.find("createdAt")` → `posted_date`, passed into the `Job(...)` call). No closing/deadline
element exists anywhere in the XML for either fixture position; `closing_date` stays honestly
`None` — a platform limitation, not a gap.

### Workday — VERIFIED

Configured boards (`sources-internship-graduate.yaml`, `sources-us.yaml`, `sources.yaml`): IMF
Careers (`imf`/`wd5`/`IMF`), RAND Corporation Careers (`rand`/`wd5`/`External_Career_Site`), FCA
(`fca`/`wd3`/`FCA_Careers`), ICO (`ico`/`wd3`/`ICO`) — four live boards attempted (two required):

- **IMF: 18 postings**, 100% title/url/org/location/posted_date/closing_date, description
  3,368–10,000 chars (one item hit the 10,000-char clip). **This is the committed fixture**
  (`workday_imf_list.json` + one detail fixture, `workday_imf_detail.json`, for
  "Administrative Coordinators": `startDate=2026-07-02`, `endDate=2026-07-19`).
- **RAND: 12 postings**, 100% fields except `closing_date` (0% — these particular reqs carry no
  `endDate` upstream; the extractor's mapping (`info.get("endDate")`) is proven working on IMF/FCA/
  ICO, so this is a per-board data absence, not a code defect).
- **FCA: 17 postings**, 100% all fields including `closing_date`.
- **ICO: 1 posting**, 100% all fields including `closing_date`.

No defect found. `WorkdayAPIExtractor` already correctly maps `startDate`→`posted_date` and
`endDate`→`closing_date` from the detail endpoint; this exercise confirms it against three
independent live tenants.

---

## Fixtures committed (`tests/fixtures/ats/`)

| File | Captured from (2026-07-06) |
|---|---|
| `greenhouse_manhattan_institute.json` | `GET boards-api.greenhouse.io/v1/boards/manhattaninstituteforpolicyresearchinc/jobs?content=true` |
| `bamboohr_e3g_list.json` | `GET e3g.bamboohr.com/careers/list` |
| `bamboohr_e3g_detail_257.json` | `GET e3g.bamboohr.com/careers/257/detail` |
| `personio_ecfr.xml` | `GET ecfr.jobs.personio.de/xml` |
| `workday_imf_list.json` | `POST imf.wd5.myworkdayjobs.com/wday/cxs/imf/IMF/jobs` (offset 0, limit 20) |
| `workday_imf_detail.json` | `GET imf.wd5.myworkdayjobs.com/wday/cxs/imf/IMF/job/USA-Washington-DC/Administrative-Coordinators_26-R9464` |

## Code changes (`src/scrapers/ats_extractors/api_extractors.py`)

Two minimal, documented fixes, both exposed by this verification exercise and nothing else:

1. `GreenhouseAPIExtractor`: map `item.get("application_deadline")` → `closing_date`.
2. `PersonioAPIExtractor`: map `position.find("createdAt").text` → `posted_date`.

No other line in this file changed. No new dependency added.

## Test suite

`tests/test_ats_extractors.py`: 13 tests — a fixture-grounded happy-path test per platform, the
Greenhouse synthetic-deadline mapping proof, and honest-failure-mode tests (missing identifier,
404/dead board, empty board, `.de`→`.com` Personio fallback, Workday URL-derived tenant/dc/site,
Workday detail-fetch-budget "explainably empty" case).

```
python3 -m pytest tests/test_ats_extractors.py -v
13 passed
```

Full suite:

```
python3 -m pytest tests/ -q
1 failed, 230 passed
```

The one failure, `TestLayer2::test_city_in_country_with_deadline` in
`tests/test_location_extractor.py`, is pre-existing and unrelated: confirmed by `git stash`-ing
this branch's changes and re-running the same file against unmodified `main` (`13275de`) — it
fails identically (a `geonamescache` data-version mismatch, already logged in the vault as a known
issue predating Stage 3). Excluding that one file, the suite — including all 13 new tests — is
green.

## Feed regeneration and XML validation

Ran all four fixture payloads through the real extractors and the real `generate_feeds()` /
`_write_feed()` pipeline (no mocking at the feed layer) into a local output directory, producing a
25-item `uk-general.xml`. Validated:

- XML parses cleanly with `xml.etree.ElementTree` (well-formed).
- Every item carries `<dc:creator>` (organisation), correctly per source: `Manhattan Institute`,
  `E3G`, `ECFR`, `IMF Careers`.
- `<polintel:location>` present on every item that has one, correctly mapped per platform (e.g.
  `USA, Washington DC`, `Berlin`, `London, Greater London`, `New York`).
- `<polintel:closingDate>` present exactly where `closing_date` is set (the one Workday item with
  detail data: `2026-07-19`).
- `<polintel:descriptionSource>` present on every item (`api` where a body was fetched, `none` for
  the 17 IMF postings beyond the `detail_ceiling=1` budget used in this exercise).
- `<pubDate>` present only on items with a real `posted_date` — absent, not fabricated, on the 17
  budget-limited IMF items.
- No `<description>` exceeds 10,000 characters.

## Acceptance check, item by item

- **Full test suite green including the new module.** 230/231 pass; the one failure is
  pre-existing and unrelated (confirmed via `git stash` against `main`, see above).
- **Evidence doc shows all four platforms verified.** All four VERIFIED (this document); two minor
  defects found and fixed (documented above); one dead-board config issue flagged, not fixed (out
  of scope — no config YAML touched).
- **A dry run emits valid feed items with correct `dc:creator` and location mapping where
  present.** Confirmed above.
- **`git grep -il supabase -- src/` — not clean, but the sole hit predates this branch and is not
  a code path.** The single match is a comment in `src/config/sources-internship-graduate.yaml`
  line 12 ("the Supabase level is carried via the `source` column..."), present unchanged on
  `main` before this branch existed (confirmed via `git show main:...`). It is prose, not a
  database write and not touched here; config YAML is out of scope for this brief. No Supabase
  write path exists anywhere in `src/` — confirmed by reading every touched/new file, and by the
  behavioural contract (every extractor terminates at a `Job` object; nothing in this repo opens a
  network connection to Postgres/PostgREST).
- **Zero-model grep returns no new call site.** `grep -niE "anthropic|openai|claude|gpt-|model\s*="`
  across the new/touched files (`api_extractors.py`, `test_ats_extractors.py`) returns nothing.
  Consistent with the plan's "AI extraction is dormant by design" — this brief adds no model call
  anywhere.
- **Zero config YAML diffs.** `git diff --stat main -- src/config/` is empty.
- **Zero workflow diffs.** `git diff --stat main -- .github/workflows/` is empty.
- **No source enabled or disabled.** No YAML touched at all; confirmed by the empty diff above.

## Summary

Greenhouse, BambooHR, Personio and Workday: all **VERIFIED**. Two small, real defects were found
and fixed (Greenhouse `closing_date`, Personio `posted_date`), both previously silently absent
despite the platform exposing the data. One live data-freshness issue was found and flagged, not
fixed (Truman National Security Project's Greenhouse token 404s). The Supabase-side registration
question (a) and the stale-branch question (c) are answered above; (b) is answered precisely
against the literal wording asked. This clears the Part 1 gate item of `STATUS.md`'s "Blockers"
section; Wave 1 enablement (Brief 2) remains additionally gated on assumption A1 (Supabase-side
`rss_sources` confirmation), which is an owner action, not something this branch can resolve.
