# Internship & Graduate Pipeline — Phase 0 De-duplication Manifest

Generated: 2026-06-17. Cross-referenced against all source configs in `src/config/`.

Normalisation key: registrable domain + organisation name. ATS-hosted subdomains
(e.g. `careers-brookings.icims.com`) are matched to the org's canonical domain.

---

## EXISTING — already covered, skip

These sources overlap with current config; do not add to the new pipeline.

| Seed source | Existing entry | File | Status |
|---|---|---|---|
| W4MP / w4mpjobs | "W4MP" RSS at w4mpjobs.org/RSS.aspx | sources.yaml | enabled |
| CharityJob | "CharityJob" dedicated scraper | sources.yaml | enabled |
| EuroBrussels | "EuroBrussels" dedicated scraper | sources-brussels.yaml | enabled |
| EURACTIV Jobs | "EURACTIV JobSite" + "EurActiv Jobs" RSS | sources-pan-eu.yaml, sources-brussels.yaml | disabled (deferred) |
| EUJobs.co | "EUJobs.co" | sources-pan-eu.yaml | disabled (JS/React, deferred) |
| JobsIn.Brussels | "Jobs in Brussels" | sources-brussels.yaml | disabled (JS SPA) |
| Tom Manatos Jobs | "Tom Manatos Jobs" | sources-us.yaml | disabled (Cloudflare) |
| Brookings | "Brookings Institution Careers" iCIMS selector | sources-us.yaml | enabled |
| Carnegie Endowment | "Carnegie Endowment for International Peace Careers" ApplicantPro selector | sources-us.yaml | enabled |
| Heritage Foundation (main board) | "Heritage Foundation Careers" JazzHR selector at heritage.applytojob.com | sources-us.yaml | enabled |
| Chatham House | "Chatham House" + "Chatham House Internships" | sources.yaml | disabled (403) |
| NATO | "NATO Careers" + "NATO NCIA" | sources-brussels.yaml | disabled (404/403) |
| EU Commission Blue Book | "Commission Blue Book Traineeships" | sources-brussels.yaml | disabled (informational) |
| EP Schuman (apply4ep) | "APPLY4EP (European Parliament)" at apply4ep.gestmax.eu | sources-brussels.yaml | disabled (404) |
| EPSO / EU Careers | "EU Careers (EPSO)" | sources-brussels.yaml | disabled (JS portal) |
| UK Civil Service Fast Stream | "Civil Service Fast Stream" | sources.yaml | disabled (JS/React) |
| UK Parliament careers | "UK Parliament" | sources.yaml | disabled (403) |
| Working for an MP | Deduplicated to W4MP RSS feed | sources.yaml | — |
| USAJOBS | "USAJobs" + "USAJobs Fellowships" | sources-us.yaml | enabled |
| UN careers / Inspira | "UN Job Feed" RSS | sources.yaml | disabled |

---

## AMBIGUOUS — possible overlap; flag for manual review; leave disabled

These sources have an existing config entry, but the seed provides a different URL
(direct ATS board vs. main careers page) that may be functional where the existing
entry is blocked/404. Each requires a decision before enabling.

| Seed source | Seed URL | Existing entry | Issue |
|---|---|---|---|
| FTI Consulting | https://fticont.referrals.selectminds.com/ftistudentcareers/ | "FTI Consulting" at fticonsulting.com/careers (403, disabled) | Seed URL is the direct Taleo/SelectMinds student board — likely functional; decide whether to add alongside or replace. |
| Hanbury Strategy | https://hanburystrategy.teamtailor.com/jobs | "Hanbury Strategy" at hanburystrategy.com/careers (403, disabled) | Seed is the direct Teamtailor URL — likely accessible; decide whether to add as a separate ats_auto entry. |
| EP Schuman (ep-stages) | https://ep-stages.gestmax.eu/ | "APPLY4EP" at apply4ep.gestmax.eu (disabled 404) + "EP Schuman Traineeships" (informational) | ep-stages.gestmax.eu is a different Gestmax portal from apply4ep.gestmax.eu — not a duplicate, but same programme. Investigate whether ep-stages returns individual listings. |
| Heritage Foundation YLP | https://www.heritage.org/young-leaders-program | "Heritage Foundation Careers" at heritage.applytojob.com (JazzHR, enabled) | Seed references the Young Leaders Program specifically, which may use a different ATS (ApplicantStack) from the main JazzHR board. Verify before adding. |

> **Action required before proceeding**: confirm FTI and Hanbury Strategy decisions. EP Schuman ep-stages.gestmax.eu should be investigated — if it returns individual traineeship listings it is a NEW entry. Heritage YLP may be a second source entry alongside the existing careers board.

---

## NEW — not present, proceed to add

Only these sources enter the build. Organised by ingestion class.

### Class A — dedicated boards (custom parser, add to CURATED_SOURCES)

| Source | URL | Region | Compliance posture | Notes |
|---|---|---|---|---|
| PubAffairs Networking | https://www.publicaffairsnetworking.com/public-affairs-jobs.php | UK/EU | Green — editorial board, open access | PHP static listing page. Includes GraduateForward postings. |
| Traverse Jobs | https://www.traversejobs.com | US | Amber — verify ToS; subscription wall may block full access | Subscription platform; intern/grad category. DEFERRED pending access investigation. |
| Roll Call Jobs | https://www.rcjobs.com | US | Amber — verify ToS; YourMembership platform | YourMembership SaaS board. Investigate static HTML availability. |
| ConservativeJobs.com | https://conservativejobs.com | US | Green — open job board | Proprietary platform; intern-heavy. Investigate HTML structure. |
| Daybook | https://www.daybook.com | US | Amber — membership model | Subscription wall likely. DEFERRED. |

### Class B — ATS-backed single-org (route via ats_auto)

| Source | Careers URL | Region | ATS | ATS extractor status | Notes |
|---|---|---|---|---|---|
| FleishmanHillard EU | https://fleishmanhillard.eu/careers/ | EU | Greenhouse (primary) | Covered | Detect ATS from page and route. |
| World Bank | https://www.worldbank.org/ext/en/careers | international | Cornerstone (csod.com) | EXTEND (new extractor needed) | csod detection + extractor needed. |
| Ipsos | https://www.ipsos.com/en/careers | UK/international | Oracle Recruiting Cloud | Covered (oracle_hcm extractor exists) | Needs api_host/site identifier discovery. |
| OECD | https://www.oecd.org/en/about/careers/internships.html | international | SmartRecruiters | Covered | Needs company_id identifier discovery. |
| IMF | https://www.imf.org/en/about/recruitment | international | Workday | Covered | Needs tenant/dc/site discovery. |
| WTO | https://www.wto.org/english/thewto_e/vacan_e/ | international | Workday | Covered | Needs tenant/dc/site discovery. |
| Oxera | https://careers.oxera.com/jobs | UK/EU | auto-discover | To investigate | Auto-discovery candidate. |
| YouGov | https://jobs.yougov.com/early-careers | UK | auto-discover | To investigate | Auto-discovery candidate. |
| Savanta | https://savanta.com/about/careers/ | UK | auto-discover | To investigate | Auto-discovery candidate. |
| Survation | https://www.survation.com/careers/ | UK | auto-discover | To investigate | Auto-discovery candidate. |
| Public First | https://www.publicfirst.co.uk/jobs.html | UK | auto-discover | To investigate | Auto-discovery candidate. |

### Class C — institutional portals (RSS/API first, scheduled fetch last resort)

| Source | URL | Region | Mechanism | Cycle | Notes |
|---|---|---|---|---|---|
| CHCI | https://chci.org/programs/congressional-internship-program/ | US | SurveyMonkey Apply | Seasonal (spring/fall) | Application portal, not a job board. No programmatic feed. DEFERRED — list as informational. |
| CBCF | https://www.cbcfinc.org/programs/internships/ | US | AcademicWorks | Seasonal | Application portal. No programmatic feed. DEFERRED — list as informational. |

---

## Expansion seeds — auto-discover only (do not hand-add)

The following organisations appear in expansion seed lists. Those already in existing
config are noted. The rest are auto-discovery candidates: feed their careers URLs to
`ats_auto` detection and only register where an ATS or RSS feed is found.

**UK public affairs firms** (expansion seeds):
Portland (disabled, 403 in sources.yaml), Hanover (not in config), APCO (disabled 404),
Lexington (not in config), Headland (not in config), WA Communications (disabled 403),
Global Counsel (not in config), Pagefield (not in config), Cicero/AMO (disabled SSL),
MHP Group (not in config), SEC Newgate (enabled, BambooHR — EXISTING), Brevia (not in config),
Cratus (not in config), Madano (not in config), Dentons Global Advisors (not in config).

**Brussels consultancies**: Kreab, Penta, Grayling, Weber Shandwick, BCW, Edelman, Interel,
FIPRA, Rud Pedersen, Cambre, SEC Newgate EU, Political Intelligence, Publyon,
Schuman Associates, RPP Group, Milltown Partners, Bernstein Group, DR2 Consultants,
GPlus, Kekst CNC — none currently in config. Auto-discover candidates.

**UK think tanks** (expansion seeds):
IPPR (enabled selector), Institute for Government (disabled 403), Resolution Foundation (disabled 404),
NIESR (disabled 404), Demos (enabled selector), Onward (enabled selector), Policy Exchange (enabled selector),
Centre for Social Justice (disabled 404), Fabian Society (disabled 404), RUSI (disabled 403),
ODI (disabled Cloudflare), Nesta (disabled JS), King's Fund (disabled 403), Nuffield Trust (disabled 404),
Tony Blair Institute (disabled JS/Salesforce).

**EU think tanks**: Bruegel (disabled 404), CEPS (disabled), EPC (enabled selector),
Friends of Europe (disabled 404), Carnegie Europe (disabled 404), ECFR (enabled Personio),
E3G (enabled BambooHR), Jacques Delors Institute (not in config), Egmont (disabled 404),
CERRE (not in config).

**US think tanks**:
RAND (enabled Workday), CSIS (disabled 403), Cato (disabled JS), CAP (disabled 403),
Atlantic Council (enabled selector), Wilson Center (enabled selector), CFR (enabled iCIMS selector),
Urban Institute (disabled Cloudflare), AEI (enabled iCIMS selector), Hudson (enabled Paylocity),
New America (enabled JazzHR), Bipartisan Policy Center (disabled JS), German Marshall Fund (enabled Paylocity).

**Corporate gov-rel**: Microsoft EGA, Google Public Policy, Amazon International Public Policy,
Airbus, Toyota Motor Europe — none in config. Auto-discover candidates.

---

---

## Retirement candidates (out of scope for this pipeline; note for separate cleanup)

These sources are in existing config files, are permanently blocked or dead, and generate
health-monitor noise on every run. Retirement means removing the entry entirely (not just
`enabled: false`). Scheduled for a separate sources-cleanup pass; do not touch here.

| Source | File | Reason |
|---|---|---|
| FTI Consulting (main careers page) | sources.yaml | fticonsulting.com/careers has returned 403/404 since 2026-03-27. The student board (fticont.referrals.selectminds.com/ftistudentcareers/) is now tracked as a separate internship_graduate entry. The blocked main-page entry generates recurring health-monitor noise with no prospect of recovery. |
| APPLY4EP (apply4ep.gestmax.eu) | sources-brussels.yaml | /search/offers has been 404 since before 2026-06-13. Dedicated EP recruitment through this portal appears discontinued. Schuman traineeships are now at ep-stages.gestmax.eu (separate portal). Retired in comment 2026-06-17; remove entirely in cleanup. |

---

## Compliance posture summary

- **Green**: PubAffairs Networking, ConservativeJobs.com, all ATS-backed single-orgs (robots.txt permissive, ATS API access)
- **Amber**: Traverse Jobs, Roll Call Jobs, Daybook — subscription/membership model; verify ToS before enabling; leave disabled
- **Red** (excluded outright): LinkedIn, Indeed, Glassdoor, Guardian Jobs — per hard constraint; discovery-only
