# UK Source Expansion — Verification Results

Generated: 2026-09-29 04:27 UTC

## Summary table

| Source | Platform | Robots | HTTP | Challenge | Raw | Filtered | Elapsed |
|--------|----------|--------|------|-----------|-----|----------|---------|
| Ofcom | workday | ✓ allow | 200 | no | 5 | 3 | 12.6s |
| FCA | workday | ✓ allow | 200 | no | 12 | 7 | 11.4s |
| FCA Early Careers | workday | ✓ allow | 200 | no | 0 | 0 | 1.1s |
| ICO | workday | ✓ allow | 200 | no | 1 | 0 | 10.7s |
| Wellcome | workday | ✓ allow | 200 | no | 13 | 5 | 10.0s |
| Innovate UK | workday | ✓ allow | 200 | no | 1 | 0 | 9.6s |
| FTI Consulting | workday | ✓ allow | 200 | no | 212 | 12 | 11.9s |
| Bank of England | oracle_hcm | ✓ allow | 200 | no | 21 | 9 | 8.4s |
| UKRI | oracle_hcm | ✓ allow | 200 | no | 37 | 6 | 7.7s |
| Scottish Government † | oracle_hcm | ✓ allow | 200 | no | 27 | 27 | 7.7s |
| ECFR | personio | ✓ allow | 200 | no | 2 | 0 | 4.2s |
| E3G | bamboohr | ✗ disallow | 200 | no | 2 | 1 | 5.7s |
| Chatham House | teamtailor | ✓ allow | 200 | no | 3 | 3 | 3.3s |
| Portland Communications | teamtailor | ✓ allow | 404 | no | 0 | 0 | 3.2s |
| Hanbury Strategy | teamtailor | ✓ allow | 200 | no | 3 | 3 | 3.2s |
| Green Alliance | teamtailor | ✓ allow | 200 | no | 0 | 0 | 2.3s |
| FGS Global | greenhouse | ✓ allow | 200 | no | 9 | 0 | 2.0s |
| Labour PLP | greenhouse | ✓ allow | 200 | no | 0 | 0 | 0.1s |
| Teneo | greenhouse | ✓ allow | 200 | no | 40 | 1 | 0.2s |
| Burson (Global) | greenhouse | ✓ allow | 200 | no | 189 | 8 | 0.7s |
| Burson (Buchanan) | greenhouse | ✓ allow | 200 | no | 0 | 0 | 0.1s |
| PubAffairs Bruxelles † | selector | ✓ allow | 200 | no | 0 | 0 | 1.8s |
| Scottish Parliament | selector | ✗ disallow | 200 | no | 0 | 0 | 1.2s |
| Senedd | selector | ✓ allow | 200 | no | 0 | 0 | 1.0s |
| Greater London Authority | selector | ✗ disallow | 403 | ⚠ YES | 0 | 0 | 0.1s |

† verify_only — do not add to sources.yaml without explicit approval.

## Sample titles

### Ofcom
*Ofcom regulatory body — mixed board; title filter required.*

**Raw (5 total) — first 5:**
- Senior Associate, Technical Advisor | 5 Locations
- Senior Associate, Online Safety Policy Development | 5 Locations
- Senior Regulatory Affairs Manager (Consumer, Infrastructure and Connectivity) | Edinburgh
- Group Director, Enforcement | 3 Locations
- Senior Associate, Technology Policy | 2 Locations

**Filtered out (sample — check for false negatives):**
- Senior Associate, Technical Advisor | 5 Locations
- Group Director, Enforcement | 3 Locations

### FCA
*FCA main careers board — mixed board; title filter required. Two Workday sites: FCA_Careers + FCA_earlycareers.*

**Raw (12 total) — first 5:**
- People Data & Reporting Analyst | 3 Locations
- Senior Benchmarks Supervision Associate | London
- Lead Financial Promotion Supervisor | London
- HR Systems Associate | 3 Locations
- Strategic Assessment Intelligence Analyst – FTC until 31/03/28 | 3 Locations

**Filtered out (sample — check for false negatives):**
- HR Systems Associate | 3 Locations
- Lawyer- Retail Investment Services | 3 Locations
- Product Owner - Graph Analytics | 3 Locations
- Personal Assistant to the Head of Department | 3 Locations
- Head of Department: AI & Technology Security Operations | London

### FCA Early Careers
*FCA early careers / graduate board — same tenant as FCA main, separate site.*

No jobs returned.

### ICO
*Information Commissioner's Office — mixed board; title filter required.*

**Raw (1 total) — first 5:**
- Principal Technology Adviser - Identity and Trust | 5 Locations

**Filtered out (sample — check for false negatives):**
- Principal Technology Adviser - Identity and Trust | 5 Locations

### Wellcome
*Wellcome Trust — global health research funder; mixed board; title filter required.*

**Raw (13 total) — first 5:**
- Operations Risk & Controls Analyst | London
- Programme Manager | London
- Funding Manager, Directed Activities | London
- Research Manager, Capacity & Field Development | London
- Brand Manager | London

**Filtered out (sample — check for false negatives):**
- Programme Manager | London
- Funding Manager, Directed Activities | London
- Brand Manager | London
- Senior Manager, Tools, Technology & AI | London
- Assistant Property Asset Manager | London

### Innovate UK
*Innovate UK public careers board. NOT iukukri (internal portal). Mixed board; title filter required.*

**Raw (1 total) — first 5:**
- Finance Business Partner | Swindon

**Filtered out (sample — check for false negatives):**
- Finance Business Partner | Swindon

### FTI Consulting
*FTI Consulting public careers board (dc=wd108). NOT the private internal site. Location filter to London/UK; title filter required.*

**Raw (212 total) — first 5:**
- Manager, Continual Service Improvement | 3 Locations
- Analyst, Strategy and Transformation | Washington, DC
- Intern, Consultant Cyber Threat Intelligence (CTI) & Investigation numérique (DFIR) | Paris, France
- Senior Consultant, Public Affairs - Industrials | Washington, DC
- Consultant, Public Affairs - Industrials | Washington, DC

**Filtered out (sample — check for false negatives):**
- Manager, Continual Service Improvement | 3 Locations
- Analyst, Strategy and Transformation | Washington, DC
- Intern, Consultant Cyber Threat Intelligence (CTI) & Investigation numérique (DFIR) | Paris, France
- Senior Consultant, Public Affairs - Industrials | Washington, DC
- Consultant, Public Affairs - Industrials | Washington, DC

### Bank of England
*Bank of England Oracle HCM. Host: eoff.fa.em1.ukg.oraclecloud.com site=CX_1001. Mixed board; title filter required.*

**Raw (21 total) — first 5:**
- Technical Specialist (cyber related), Operational Risk and Resilience, R&CGI Operational Risk and Resilience Team - Insurance Directorate | Leeds, United Kingdom
- Manager, Specialist Financial Risk, Specialist Supervision Division, Capital Assessment Team - UKDT | Leeds, United Kingdom
- Technical Product Manager (Messaging & Integration) | Leeds, United Kingdom
- Fabric Maintenance Technician - London Sites | London, United Kingdom
- Lead Security Architect in SECURITY ARCHITECTURE | London, United Kingdom

**Filtered out (sample — check for false negatives):**
- Technical Specialist (cyber related), Operational Risk and Resilience, R&CGI Operational Risk and Resilience Team - Insurance Directorate | Leeds, United Kingdom
- Technical Product Manager (Messaging & Integration) | Leeds, United Kingdom
- Fabric Maintenance Technician - London Sites | London, United Kingdom
- Lead Security Architect in SECURITY ARCHITECTURE | London, United Kingdom
- Security Protection Officer in Security Ops - London | London, United Kingdom

### UKRI
*UKRI Oracle HCM (evzn tenant). Mixed board; title filter required.*

**Raw (37 total) — first 5:**
- Workplace Investigations Senior Manager | Swindon, Wiltshire, United Kingdom
- Content Designer | Swindon, Wiltshire, United Kingdom
- MRC Postdoctoral Research Scientist | Greater London, United Kingdom
- MRC Postdoctoral Research Scientist | London, Greater London, United Kingdom
- Research Technician | London, Greater London, United Kingdom

**Filtered out (sample — check for false negatives):**
- Workplace Investigations Senior Manager | Swindon, Wiltshire, United Kingdom
- Content Designer | Swindon, Wiltshire, United Kingdom
- Investigator Scientist | Cell Biology | Dr Marta Shahbazi | LMB 2929 | Cambridge, Cambridgeshire, United Kingdom
- Senior Finance Specialist | Swindon, Wiltshire, United Kingdom
- Finance Manager - Corporate Finance | Swindon, Wiltshire, United Kingdom

### Scottish Government
*Scottish Government Oracle HCM (evxn tenant). VERIFY ONLY — do not add to sources.yaml until explicit ruling.*

**Raw (27 total) — first 5:**
- Finance Business Partner | United Kingdom
- Organisational Design and Development Manager - Social Security Scotland | Dundee, United Kingdom
- Product Lead (Fixed Term Appointment) | Glasgow, United Kingdom
- Appointment of a Member to the Board of Children’s Hearings Scotland | United Kingdom
- Central Correspondence Unit Officer | Edinburgh, United Kingdom

### ECFR
*ECFR Personio board. Global board — London location filter required. Separate UK entry from the existing pan-eu source.*

**Raw (2 total) — first 5:**
- Speculative Application | Berlin
- Working Student – European Security Programme (m/f/d) | Berlin

**Filtered out (sample — check for false negatives):**
- Speculative Application | Berlin
- Working Student – European Security Programme (m/f/d) | Berlin

### E3G
*E3G BambooHR board. Global board — London location filter required.*

**Raw (2 total) — first 5:**
- Associate Director, Clean Economy, London, Brussels or Berlin | London, Greater London
- Senior Researcher, EU Energy Transition (Internal Opportunity) | Brussels, Brussels

**Filtered out (sample — check for false negatives):**
- Senior Researcher, EU Energy Transition (Internal Opportunity) | Brussels, Brussels

### Chatham House
*Chatham House custom TeamTailor domain careers.chathamhouse.org. Do not scrape chathamhouse.org main site.*

**Raw (3 total) — first 5:**
- CRM Administrator | London
- Research Fellow (West Africa) - Africa Programme | London
- HR Operations Officer - Maternity cover | London

### Portland Communications
*Portland Communications TeamTailor board.*

No jobs returned.

### Hanbury Strategy
*Hanbury Strategy TeamTailor board.*

**Raw (3 total) — first 5:**
- EU Financial Services Public Affairs Traineeship | Bruxelles
- Financial Services Executive | London
- Account Director (Public Affairs & Communications) | Sydney

### Green Alliance
*Green Alliance TeamTailor board.*

No jobs returned.

### FGS Global
*FGS Global Greenhouse board. Location filter to London/UK.*

**Raw (9 total) — first 5:**
- Accountant | Hong Kong
- Associate Director, Strategic Communications | Washington, District of Columbia, United States
- Associate Global Public Affairs - The Hague | Continental Europe
- Billing Associate | Washington, District of Columbia, United States
- Finance Graduate Associate | Hong Kong

**Filtered out (sample — check for false negatives):**
- Accountant | Hong Kong
- Associate Director, Strategic Communications | Washington, District of Columbia, United States
- Associate Global Public Affairs - The Hague | Continental Europe
- Billing Associate | Washington, District of Columbia, United States
- Finance Graduate Associate | Hong Kong

### Labour PLP
*Labour PLP Greenhouse board.*

No jobs returned.

### Teneo
*Teneo Greenhouse board. Mixed board — London location filter + title filter required.*

**Raw (40 total) — first 5:**
- Accountant | Hong Kong, China
- Associate Consultant(e) | Paris, France
- Associate Consultant - Financial Advisory | Hong Kong, China
- Associate Consultant, Financial Communications - Industrials | London, United Kingdom
- Associate Director / Director, Financial Advisory | Riyadh, Saudi Arabia

**Filtered out (sample — check for false negatives):**
- Accountant | Hong Kong, China
- Associate Consultant(e) | Paris, France
- Associate Consultant - Financial Advisory | Hong Kong, China
- Associate Director / Director, Financial Advisory | Riyadh, Saudi Arabia
- Associate, Strategy & Communications | Hong Kong, China

### Burson (Global)
*Burson global Greenhouse board. Mixed board — London location filter + title filter required. Two boards: bursonglobalcareers and bursonbuchanan (separate source entry).*

**Raw (189 total) — first 5:**
- Account Director | Jakarta, Jakarta, Indonesia
- Account Director, Consumer Brand, Nutrition & Wellness - Burson | New York, New York, United States
- Account Director, Corporate & Public Affairs (Health Policy) | Washington, District of Columbia, United States
- Account Director, Digital - Health & Wellness | New York, New York, United States
- Account Director, Earned Media, Consumer Brand - Burson | New York, New York, United States

**Filtered out (sample — check for false negatives):**
- Account Director | Jakarta, Jakarta, Indonesia
- Account Director, Consumer Brand, Nutrition & Wellness - Burson | New York, New York, United States
- Account Director, Corporate & Public Affairs (Health Policy) | Washington, District of Columbia, United States
- Account Director, Digital - Health & Wellness | New York, New York, United States
- Account Director, Earned Media, Consumer Brand - Burson | New York, New York, United States

### Burson (Buchanan)
*Burson Buchanan Greenhouse board. UK-focused; location filter precautionary.*

No jobs returned.

### PubAffairs Bruxelles
*VERIFY ONLY pending ToS ruling. Public affairs job board.*

No jobs returned.

### Scottish Parliament
*Scottish Parliament career search. Scrape listing page only; do not scrape WebITrent system.*

No jobs returned.

### Senedd
*Senedd Welsh Parliament jobs board.*

No jobs returned.

### Greater London Authority
*GLA vacancies page at london.gov.uk. NOT gla.gov.uk (Gangmasters and Labour Abuse Authority). Mixed board; title filter required.*

No jobs returned.
