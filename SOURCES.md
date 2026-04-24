# Pol-Intel Feed Sources

Reference table for all configured sources. Authoritative config is in `src/config/sources.yaml` (UK), `src/config/sources-brussels.yaml` (Brussels), and `src/config/sources-us.yaml` (US). This file documents what was tried and why disabled sources are disabled — so they are not rediscovered unnecessarily.

---

## United Kingdom

### Enabled

| Source | Category | Scraper | Notes |
|--------|----------|---------|-------|
| Civil Service Jobs | government | dedicated | ALTCHA-protected individual pages; enrichment disabled. Official API-style URL |
| NICS | government | dedicated | Northern Ireland Civil Service |
| LGA Jobs | government | dedicated | Local Government Association careers portal |
| National Audit Office | government | selector | Static WordPress list page |
| CharityJob | ngos | dedicated | Keyword-filtered: policy, advocacy, public affairs |
| TUC | ngos | selector | Full selector including location and closing-date fields |
| Amnesty International UK | ngos | selector | |
| jobs.ac.uk | general | dedicated | Custom scraper for politics/government subject area |
| W4MP | general | rss_feed | Full job descriptions in RSS; enrichment disabled |
| UN Job Feed | general | rss_feed | Organisation extracted from description via regex |
| IPPR | think-tanks | selector | Currently no vacancies; page structure confirmed |
| Policy Exchange | think-tanks | selector | Elementor post grid |
| Onward | think-tanks | selector | |
| NEF | think-tanks | selector | New Economics Foundation |
| Demos | think-tanks | selector | |
| Liberal Democrats | political-parties | selector | |
| SNP | political-parties | selector | NationBuilder; returns 0 when no live vacancies |
| Green Party | political-parties | selector | Includes location and closing-date selectors |
| Co-operative Party | political-parties | selector | |
| Ellwood Atfield | public-affairs | selector | Public affairs recruitment firm |

### Disabled

| Source | Category | Scraper | Notes |
|--------|----------|---------|-------|
| myjobscotland | government | dedicated | Signal too low — overwhelmingly council operational roles (cleaners, catering) |
| Third Sector Jobs | ngos | dedicated | ToS prohibits scraping |
| Bond Jobs | ngos | dedicated | Salesforce Aura SPA — requires authenticated Playwright session |
| Guardian Jobs | ngos | dedicated | 403 blocked by Madgex WAF |
| Escape the City | ngos | dedicated | Algolia/Vue SPA — requires API key from live browser session |
| Oxfam GB | ngos | selector | eArcu ATS renders listings in JS — no static HTML job list |
| HEPI | think-tanks | selector | Selector too broad (hits staff profiles); no current vacancies to verify against |
| Centre for Policy Studies | think-tanks | selector | Job listings link to mailto: addresses — no scrapeable URLs |
| Theos | think-tanks | selector | 404 at all known careers paths |
| Plaid Cymru | political-parties | selector | Volunteer sign-up page only — no structured job listings |
| IoD | trade-associations | selector | JS-rendered via authenticated hirefulcms.com API — job links are placeholders |
| jobs.ac.uk International | fellowships | rss_feed | RSS URL redirects to homepage; covered by dedicated jobs.ac.uk scraper |
| jobs.ac.uk Sustainability | ngos | rss_feed | RSS URL redirects to homepage; covered by dedicated jobs.ac.uk scraper |
| FCA | government | ats_auto | Workday ATS — extractor not yet implemented |
| ICO | government | ats_auto | Workday ATS — extractor not yet implemented |
| ECFR London | think-tanks | ats_auto | Personio ATS — extractor not yet implemented |
| ODI | think-tanks | ats_auto | Pinpoint ATS — extractor not yet implemented |
| E3G | think-tanks | ats_auto | BambooHR ATS — extractor not yet implemented |
| SEC Newgate | public-affairs | ats_auto | BambooHR ATS — extractor not yet implemented |
| Civil Service Fast Stream | government | generic | JS/React SPA — not scrapeable without Playwright |
| FCDO | government | generic | Redirects to Civil Service Jobs — already covered |
| HM Treasury | government | generic | Redirects to Civil Service Jobs — already covered |
| Cabinet Office | government | generic | Redirects to Civil Service Jobs — already covered |
| Home Office | government | generic | Redirects to Civil Service Jobs — already covered |
| Ministry of Defence | government | generic | Redirects to Civil Service Jobs — already covered |
| Ministry of Justice | government | generic | Redirects to Civil Service Jobs — already covered |
| Department for Education | government | generic | Redirects to Civil Service Jobs — already covered |
| DHSC | government | generic | Redirects to Civil Service Jobs — already covered |
| CMA | government | generic | Redirects to Civil Service Jobs — already covered |
| NCA | government | generic | Redirects to Civil Service Jobs — already covered |
| SIS/MI6 | government | generic | SSL TLSv1 protocol error |
| MI5 | government | generic | 403 blocked |
| GCHQ | government | generic | 403/404 |
| UK Parliament | government | generic | 403 blocked |
| House of Lords | government | generic | 403 blocked |
| Hansard Society | government | generic | 403/404 |
| Scottish Government | government | generic | 404 — careers page not found |
| Scottish Parliament | government | generic | Redirects to WebITrent ATS (no extractor) |
| Welsh Government | government | generic | 403/404 |
| Senedd Cymru | government | generic | 404 — URL changed |
| NI Assembly | government | generic | Redirects to niarecruitment.org ATS (no extractor) |
| GLA | government | generic | 403/404 |
| NHS England | government | generic | 403/404 |
| Ofcom | government | generic | 403/404 |
| Ofgem | government | generic | 404 — URL changed |
| Ofwat | government | generic | 403 blocked |
| Electoral Commission | government | generic | 403 blocked |
| EHRC | government | generic | 403/404 |
| Chatham House | think-tanks | generic | 403 blocked |
| IISS | think-tanks | generic | 404 — careers page moved |
| RUSI | think-tanks | generic | 403/404 |
| IFS | think-tanks | generic | 403/404 |
| Tony Blair Institute | think-tanks | generic | Salesforce/JS-rendered SPA |
| Institute for Government | think-tanks | generic | 403/404 |
| Resolution Foundation | think-tanks | generic | 404 |
| NIESR | think-tanks | generic | URL redirects to a news article |
| IEA | think-tanks | generic | 403/404 |
| Adam Smith Institute | think-tanks | generic | 404 |
| TaxPayers' Alliance | think-tanks | generic | 403/404 |
| Centre for Social Justice | think-tanks | generic | 404 |
| Fabian Society | think-tanks | generic | URL returns a JPEG image — no careers page found |
| SMF | think-tanks | generic | 403/404 |
| Smith Institute | think-tanks | generic | SSL hostname mismatch |
| CER | think-tanks | generic | 404 |
| UK in a Changing Europe | think-tanks | generic | 403/404 |
| Centre for Cities | think-tanks | generic | 404 |
| Centre for London | think-tanks | generic | 403/404 |
| New Local | think-tanks | generic | 404 |
| CLES | think-tanks | generic | 404 |
| Green Alliance | think-tanks | generic | 403/404 |
| IIED | think-tanks | generic | URL redirects to search page — no vacancies listing |
| King's Fund | think-tanks | generic | 403/404 |
| Health Foundation | think-tanks | generic | 403 blocked |
| Nuffield Trust | think-tanks | generic | 404 |
| EPI (UK) | think-tanks | generic | 403/404 |
| BFPG | think-tanks | generic | 403/404 |
| JRF | think-tanks | generic | 404 |
| IDS | think-tanks | generic | 404 |
| Constitution Unit | think-tanks | generic | 403/404 |
| IWA | think-tanks | generic | 404 |
| Reform Scotland | think-tanks | generic | Site rebranded to Enlighten Scotland — no jobs found |
| Conservative Party | political-parties | generic | 403/404 |
| Labour Party | political-parties | generic | SSL TLSv1 protocol error |
| FGS Global | public-affairs | generic | 404 — URL not found |
| Hanbury Strategy | public-affairs | generic | 403 blocked |
| Portland Communications | public-affairs | generic | 403/404 |
| APCO Worldwide | public-affairs | generic | 404 — no working careers URL found |
| Burson | public-affairs | generic | Next.js SPA — job list not in initial HTML |
| FTI Consulting | public-affairs | generic | 403/404 |
| Teneo | public-affairs | generic | React SPA — job list not in initial HTML |
| WA Communications | public-affairs | generic | 403/404 |
| Cicero/AMO | public-affairs | generic | SSL cert expired; site rebranded to H+A Global |
| NatCen Social Research | ngos | generic | 403/404 |
| Save the Children UK | ngos | generic | 403/404 |
| ODI Fellowship | fellowships | generic | Informational programme page — no individual listings |
| Chatham House Internships | fellowships | generic | 403 blocked |
| CBI | trade-associations | generic | 403/404 |
| FSB | trade-associations | generic | 403/404 |
| STUC | trade-associations | generic | 404 |
| PoliticsHome | general | generic | News site — no jobs board |

---

## Brussels / EU

### Enabled

| Source | Category | Scraper | Notes |
|--------|----------|---------|-------|
| EuroBrussels | eu-affairs | dedicated | Main Brussels-focused job aggregator |
| EU Training Jobs | eu-affairs | dedicated | Aggregates EU institution vacancies including EPSO; enrichment disabled (detail pages return only copyright footer) |
| European External Action Service | eu-institutions | selector | `div.node--type-vacancy` cards |
| European Policy Centre (EPC) | think-tanks | selector | `.vacancy-item` cards |
| College of Europe Careers | fellowships | selector | Drupal views listing |

### Disabled

| Source | Category | Scraper | Notes |
|--------|----------|---------|-------|
| EU Careers (EPSO) | eu-institutions | dedicated | JS-rendered portal; covered by EU Training Jobs |
| APPLY4EP (European Parliament) | eu-institutions | dedicated | /search/offers returns 404; covered by EU Training Jobs |
| Jobs in Brussels | eu-affairs | dedicated | JS-rendered SPA — no accessible API endpoint |
| Council of the EU | eu-institutions | generic | 403 blocked |
| NATO Careers | international-orgs | generic | 404 — URL not found |
| NATO NCIA | international-orgs | generic | 403 blocked |
| Bruegel | think-tanks | generic | 404 — URL not found |
| CEPS | think-tanks | selector | No current vacancies; page is informational only |
| Carnegie Europe | think-tanks | selector | 404 — redirects to carnegieendowment.org/europe/about/jobs which is also 404 |
| Friends of Europe | think-tanks | generic | 404 — URL not found |
| ECFR | think-tanks | selector | Personio ATS — extractor not yet implemented |
| Egmont Institute | think-tanks | generic | 404 — URL not found |
| Transparency International EU | ngos | generic | 404 — URL not found |
| International Crisis Group | ngos | generic | 403 blocked |
| European Environmental Bureau | ngos | generic | 404 — URL not found |
| Commission Blue Book Traineeships | fellowships | selector | Informational homepage only; application requires account registration |
| EP Schuman Traineeships | fellowships | selector | Informational page only; fixed annual application windows, not individual listings |
| Council Traineeships | fellowships | generic | 403 blocked |
| EurActiv Jobs | eu-affairs | rss_feed | RSS feed contains career-advice articles only, not job listings |

---

## United States

### Enabled

| Source | Category | Scraper | Partisan Lean | Notes |
|--------|----------|---------|---------------|-------|
| USAJobs Fellowships | us-fellowships | dedicated | nonpartisan | Keyword API mode: PMF, policy/congressional/government fellowships, Pathways internships. Runs before main USAJobs to win category dedup. Requires USAJOBS_API_KEY + USAJOBS_USER_AGENT |
| USAJobs | us-federal | dedicated | nonpartisan | Series-code mode (0110, 0130, 0131, 0301, 0340, 0343, 1035) + keyword post-filter. Cap 500/run. Requires USAJOBS_API_KEY + USAJOBS_USER_AGENT |
| House Employment Bulletin | us-congress | dedicated | unknown | Consumes dwillis/house-jobs JSON (MIT). Fetches 4 most recent HVAPS PDFs converted to structured JSON by Derek Willis. Staleness alert if upstream not updated in >14 days. GITHUB_TOKEN optional (<5 calls/run) |
| Idealist | us-ngos | dedicated | nonpartisan | Major nonprofit/NGO aggregator. JS-rendered — requires Playwright. Currently enabled but returns 0 without Playwright |
| Political Job Hunt | us-campaigns | dedicated | unknown | Political Wire job board. Sitemap-driven; JSON-LD on individual pages backfills org/location/closing date via enricher |
| LobbyingJobs.com | us-government-affairs | dedicated | unknown | Dedicated lobbying/government-relations board |
| Brookings Institution Careers | us-think-tanks | selector | centre-left | iCIMS portal |
| Council on Foreign Relations Careers | us-think-tanks | selector | nonpartisan | iCIMS portal |
| American Enterprise Institute Careers | us-think-tanks | selector | right | iCIMS portal |
| Heritage Foundation Careers | us-think-tanks | selector | right | JazzHR (applytojob.com) board |
| Carnegie Endowment for International Peace | us-think-tanks | selector | nonpartisan | isolved Talent Acquisition ATS; same structure as JazzHR |
| Hoover Institution Careers | us-think-tanks | selector | right | Stanford centralised careers portal (Taleo). macOS LibreSSL causes TLS error; works on Ubuntu/CI |
| Wilson Center Careers | us-think-tanks | selector | nonpartisan | Currently no vacancies; federal roles route to USAJobs externally |
| New America Careers | us-think-tanks | selector | centre-left | JazzHR board |
| Third Way Careers | us-think-tanks | selector | centre-left | Recruitee ATS; styled-component class names may change after platform updates |
| Public Affairs Council Jobs | us-government-affairs | selector | nonpartisan | Multi-employer board — org extracted per-listing, not org_static |
| Foundation List | us-ngos | rss_feed | nonpartisan | Active nonprofit job aggregator RSS feed |

### Disabled

| Source | Category | Scraper | Partisan Lean | Notes |
|--------|----------|---------|---------------|-------|
| Tom Manatos Jobs | us-congress | dedicated | unknown | Cloudflare challenge: 403 locally, HTTP 200 + JS challenge page in CI → 0 jobs. Needs Playwright + Cloudflare solver |
| Center for American Progress Careers | us-think-tanks | selector | left | 403 — blanket bot-blocking across entire domain. ~13 jobs confirmed via Google index. No external ATS endpoint found |
| Urban Institute Careers | us-think-tanks | selector | centre-left | Workday ATS — extractor not yet implemented |
| RAND Corporation Careers | us-think-tanks | selector | nonpartisan | Workday ATS — extractor not yet implemented |
| Cato Institute Careers | us-think-tanks | selector | right | JS-rendered widget — no static HTML job list; no ATS URL found |
| Bipartisan Policy Center Careers | us-think-tanks | selector | centre | JS-rendered or no current listings; no ATS detected |
| Truman National Security Project | us-fellowships | selector | centre-left | Paylocity ATS — extractor not yet implemented |
| DemocraticGAIN / GainPower Career Center | us-campaigns | selector | left | 403 — actively blocks all automated access on all paths |
| PPIA Fellowship | us-fellowships | selector | nonpartisan | Not a job board — educational programme site, no individual listings |
| Rangel Fellowship | us-fellowships | selector | nonpartisan | Not a job board; 2026 cycle postponed. Remove from sources |
| Economic Policy Institute Careers | us-think-tanks | selector | left | 403 — entire domain blocks automated requests |
| Center on Budget and Policy Priorities | us-think-tanks | selector | left | 403 — entire domain blocks automated requests |

---

## Known Gaps

| Gap | Reason | Status |
|-----|--------|--------|
| **Senate employment** | Senate Employment Office HTML is 403-blocked. No maintained equivalent of `dwillis/house-jobs` exists. `c0nnortb/senate_employment` is abandoned (1 commit). | Next-session priority. Would require a maintained upstream scraper or direct Senate Employment Office contact |
| **Workday-hosted organisations** | Workday renders job listings entirely in JS. Pipeline has no Workday extractor. Affects Urban Institute, RAND, FCA, ICO, and others. | Add extractor to `src/scrapers/ats_extractors.py` |
| **Tom Manatos Jobs** | Protected by Cloudflare challenge. HTTP 200 in CI but JS challenge page served; no job cards parsed. | Re-enable once Playwright + Cloudflare solver added to pipeline |
| **Idealist** | JS-rendered. Dedicated scraper exists but requires Playwright. | Re-enable once Playwright added to pipeline and CI workflow |
| **BambooHR / Personio / Pinpoint / Paylocity** | ATS-auto detects these platforms but no extractors exist. Affects E3G, SEC Newgate (BambooHR), ECFR (Personio), ODI (Pinpoint), Truman (Paylocity). | Add extractors to `src/scrapers/ats_extractors.py` |
| **Brad Traverse / OPA Jobs** | Paid subscription required. No free tier or public feed. | Consider direct partnership if Capitol Hill coverage needs expansion |
| **403-blocked think tanks (UK)** | Large number of major UK think tanks (Chatham House, RUSI, IFS, IfG, King's Fund, etc.) block all automated requests. | Requires either a partner feed arrangement or monitoring for ATS subdomains |
