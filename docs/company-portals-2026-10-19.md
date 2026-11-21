# Company portal verification — 19 October 2026

The registry now contains **100 companies**, up from 88. Read-only checks of all 100 sources found **84 valid first-page job feeds**, **14 reachable portals for which the listing audit does not verify extraction**, and **2 portals unavailable to this client**. These are listing checks, not guarantees of complete collection. The timestamped [JSON-lines audit](career-portal-audit-2026-10-19.jsonl) records each portal and feed separately. Additional [full-collection summaries](career-collection-check-2026-10-19.json) include successful SAP and Siemens HTML collection.

96 portals returned successful HTTP responses; Dell returned HTTP 403, Confluent HTTP 429, Rubrik HTTP 403, and Asana redirected to a URL rejected by the public HTTPS validator. Rubrik and Asana's separate public job feeds still worked. Restricted requests do not establish that the browser portal is offline.

## Corrected sources

| Company | Current source | Verified behavior |
| --- | --- | --- |
| BrowserStack | [Workday External](https://browserstack.wd3.myworkdayjobs.com/External) | Listing and full collection work using the Workday adapter. |
| Postman | [Workday careers](https://postman.wd108.myworkdayjobs.com/careers) | The official careers page names this board; listing and full collection work. |
| PhonePe | [SmartRecruiters PHONEPELIMITED](https://careers.smartrecruiters.com/PHONEPELIMITED) | All 108 public rows agree with the official [PhonePe jobs data](https://www.phonepe.com/apollo/job-postings/latest.json); full collection works. |
| Swiggy | [SmartRecruiters SWIGGY](https://careers.smartrecruiters.com/SWIGGY) | All 198 rows agree with the new [official careers portal](https://careers.swiggy.in/); full collection works. |
| SAP | [careers.sap.com search](https://careers.sap.com/search/?q=software) | Replaces the blocked jobs.sap.com search. Search and descriptions work; full HTML collection found 5 matches and reports partial coverage. |
| Siemens | [Current external search](https://jobs.siemens.com/en_US/externaljobs/SearchJobs/?search=software) | Replaces the careers redirect. Collector follows actual Next links and reads the current title, description, and location fields. Full check found 11 matches; bounded HTML coverage is partial. |
| Qualcomm | [India careers](https://careers.qualcomm.com/careers?location=India) | New Eightfold adapter reads search and full descriptions. Stable timestamp ordering avoids overlaps in the distance sort. Full check read 601 rows and found 3 matches. India scope is partial. |
| Ericsson | [India careers](https://jobs.ericsson.com/careers?start=0&location=India&sort_by=distance&filter_include_remote=1&filter_include_relocation=0) | New Eightfold adapter read 102 rows and full candidate descriptions. No software roles met the current 0–2 year filter. The supplied selected-job `pid` is omitted so the link opens search. India scope is partial. |
| IBM | [Requested India careers search](https://www.ibm.com/in-en/careers/search) | HTTP 200; job search is populated by JavaScript. Manual check is explicitly shown until a dedicated adapter is available. |
| Goldman Sachs | [Requested Analyst / India / software search](https://higher.gs.com/results?EXPERIENCE_LEVEL=Analyst&LOCATION=Bengaluru%7CMumbai%7CHyderabad&page=1&search=software&sort=RELEVANCE) | New public GraphQL adapter preserves the exact Analyst, Bengaluru/Mumbai/Hyderabad, and software filters. Live collection read 3 roles and found 1 match, with a verified public detail link. Filtered scope is partial. |

BrowserStack, Postman, PhonePe, and Swiggy completed their full collector checks with zero roles matching the conservative early-career software filter. That is a successful collection outcome, not a broken portal.

## Added companies

| Company | Official job source | Collection check |
| --- | --- | --- |
| Amazon | [India software search](https://www.amazon.jobs/en/search?base_query=software&normalized_country_code%5B%5D=IND) | New search adapter read 1,056 rows across 11 pages, including basic/preferred qualifications; 28 matches. Filtered coverage is partial. |
| Google | [India careers search](https://www.google.com/about/careers/applications/jobs/results/?location=India) | New embedded-data adapter read 20 postings and found 2 matches. Google's robots rules restrict pagination; first-page coverage is explicitly partial. |
| Swish | [Official LinkedIn careers link](https://www.linkedin.com/company/justswish/jobs/) | The [official Swish site](https://justswish.in/) points here. No supported public feed was found; manual check is explicit and the collector does not scrape LinkedIn. |
| ION Group | [Lever ion](https://jobs.lever.co/ion) | Complete collection, 82 postings, 2 matching roles. |
| Sprinto | [Lever Sprinto](https://jobs.lever.co/Sprinto) | Complete collection, 34 postings. |
| Zeta | [Lever zeta](https://jobs.lever.co/zeta) | Complete collection, 24 postings. |
| Mindtickle | [Lever mindtickle](https://jobs.lever.co/mindtickle) | Complete collection, 20 postings. |
| Druva | [Greenhouse druva](https://job-boards.greenhouse.io/druva) | Complete collection, 34 postings. |
| Harness | [Greenhouse harnessinc](https://job-boards.greenhouse.io/harnessinc) | Complete collection, 67 postings. |
| YugabyteDB | [Greenhouse yugabyte](https://job-boards.greenhouse.io/yugabyte) | Complete collection, 16 postings. |
| Glean | [Greenhouse gleanwork](https://job-boards.greenhouse.io/gleanwork) | Complete collection, 134 postings, 1 matching role. |
| SingleStore | [Greenhouse singlestore](https://job-boards.greenhouse.io/singlestore) | Complete collection, 44 postings, 8 matching roles. |

The midsize boards all included India engineering openings during verification. Counts above are global public board counts unless a country scope is stated. Roles still pass through the existing software-title and 0–2 year filters; registration does not promise a matching vacancy in every location.

## Verification and use

All checks are read-only and do not update the application's jobs, bookmarks, preferences, or refresh statuses. Restart the backend to load the new registry and corrected source settings; its normal refresh then collects the enabled companies. Existing enabled/paused choices and saved jobs are preserved.

The robots parser now uses the most specific path rule, with Allow winning equivalent rules, plus wildcard/end-anchor handling. This permits the paths explicitly allowed by Ericsson and Qualcomm while respecting Google's pagination restriction. Goldman collection uses its public API and permitted role-detail URLs; it does not crawl the restricted results route. See [RFC 9309](https://www.rfc-editor.org/rfc/rfc9309.html#section-2.2.2).

Repeat the portal/listing audit from the project root:

```bash
.venv/bin/python scripts/check_sources.py --report /tmp/career-source-audit.jsonl
.venv/bin/python scripts/check_sources.py --company browserstack --company "ION Group"
```

Validation passed: **173 backend tests** and the frontend production build. Tests cover feed pagination, full qualifications, partial-result retention, failed/malformed details, robots allow exceptions/restrictions, invalid feed schemas, corrected company configuration, and preserving jobs/bookmarks/preferences across registry updates.
