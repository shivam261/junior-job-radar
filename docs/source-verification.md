# Source verification

A read-only connectivity audit was performed on 14 October 2026 against 88 registered employer sources. **61 recruiting feed endpoints responded with HTTP 200** during the audit. This is connectivity evidence, not complete collection evidence; the Companies view and Source activity show actual refresh outcomes.

Corrections made from employer pages and live feed responses include:

- Visa's official careers page now links to `visa.wd5.myworkdayjobs.com/Visa`; the registry uses that Workday board instead of the empty legacy SmartRecruiters feed.
- Razorpay's official careers page links to Greenhouse board `razorpaysoftwareprivatelimited`; the registry uses that exact token.
- ServiceNow uses its SmartRecruiters feed instead of the unavailable Workday configuration.
- Notion uses Ashby, and Plaid uses Greenhouse.
- Several inaccessible ATS configurations were replaced with their official employer careers URLs and treated as partial/unavailable HTML sources.

The JPMorgan candidate feed and its description endpoint were checked directly, including the required `expand=requisitionList` parameter and `ById` finder for details. Its software-keyword collection is deliberately marked partial.

## Repeat the audit

From the project root:

```bash
.venv/bin/python scripts/check_sources.py
```

This emits JSON lines with company, adapter, status, source URL, and source-reported job count. It does not write to SQLite or collect job descriptions. Feed addresses and access rules change; use refresh outcomes for current source health.

## Public source references

- Autodesk Workday careers: https://autodesk.wd1.myworkdayjobs.com/Ext
- Mastercard Workday careers: https://mastercard.wd1.myworkdayjobs.com/CorporateCareers
- Cisco Workday careers: https://cisco.wd5.myworkdayjobs.com/Cisco_Careers
- GE Vernova Workday careers: https://gevernova.wd5.myworkdayjobs.com/Vernova_ExternalSite
- Visa official careers: https://corporate.visa.com/en/careers.html
- Razorpay official careers: https://razorpay.com/careers/
- JPMorgan careers: https://jpmc.fa.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_1001/jobs
- Deutsche Bank careers: https://db.wd3.myworkdayjobs.com/DBWebsite
- HSBC public search: https://apply.careers.hsbc.com/search/?q=software
- Cognizant careers: https://careers.cognizant.com/india-en/jobs/
- Zomato/Eternal careers: https://www.zomato.com/careers
- Goldman Sachs careers: https://higher.gs.com/results?search=software

Some named employer sources do not expose readable current openings in this implementation. Their official links remain available, and failures/partial status are explicitly shown. No sample listings are counted as live collection results.

## End-to-end collection results

The initial full run checked all 88 sources. Targeted reruns verified additional source corrections. The resulting SQLite dataset contains **241 active live matches** (143 with explicit experience evidence). Current source outcomes: **63 connected**, **3 partial**, and **22 needing attention**. These counts are a snapshot; the live interface is authoritative for subsequent refreshes.

| Company | Collector | Outcome | Last collected matches | Careers source |
| --- | --- | --- | ---: | --- |
| Accenture | workday | healthy | 0 | [Official careers](https://accenture.wd103.myworkdayjobs.com/AccentureCareers) |
| Adobe | workday | healthy | 0 | [Official careers](https://adobe.wd5.myworkdayjobs.com/external_experienced) |
| Airbnb | greenhouse | healthy | 1 | [Official careers](https://job-boards.greenhouse.io/airbnb) |
| AMD | html | error | 0 | [Official careers](https://careers.amd.com/careers-home/jobs) |
| Amplitude | html | error | 0 | [Official careers](https://amplitude.com/careers) |
| Asana | greenhouse | healthy | 2 | [Official careers](https://job-boards.greenhouse.io/asana) |
| Atlassian | html | error | 0 | [Official careers](https://www.atlassian.com/company/careers/all-jobs) |
| Autodesk | workday | healthy | 0 | [Official careers](https://autodesk.wd1.myworkdayjobs.com/Ext) |
| Bank of America | workday | healthy | 0 | [Official careers](https://ghr.wd1.myworkdayjobs.com/Lateral-US) |
| Barclays | workday | healthy | 0 | [Official careers](https://barclays.wd3.myworkdayjobs.com/external_career_site_barclays) |
| BlackRock | workday | healthy | 4 | [Official careers](https://blackrock.wd1.myworkdayjobs.com/BlackRock_Professional) |
| Bosch | smartrecruiters | healthy | 21 | [Official careers](https://careers.smartrecruiters.com/BoschGroup) |
| Broadcom | workday | healthy | 0 | [Official careers](https://broadcom.wd1.myworkdayjobs.com/External_Career) |
| BrowserStack | html | error | 0 | [Official careers](https://www.browserstack.com/careers) |
| Cisco | workday | healthy | 39 | [Official careers](https://cisco.wd5.myworkdayjobs.com/Cisco_Careers) |
| Citi | workday | healthy | 0 | [Official careers](https://citi.wd5.myworkdayjobs.com/2) |
| Cloudflare | greenhouse | healthy | 3 | [Official careers](https://job-boards.greenhouse.io/cloudflare) |
| Cognizant | html | error | 0 | [Official careers](https://careers.cognizant.com/india-en/jobs/?keyword=software) |
| Coinbase | greenhouse | healthy | 6 | [Official careers](https://job-boards.greenhouse.io/coinbase) |
| Confluent | html | error | 0 | [Official careers](https://careers.confluent.io/jobs) |
| Coursera | greenhouse | healthy | 0 | [Official careers](https://job-boards.greenhouse.io/coursera) |
| CRED | lever | healthy | 0 | [Official careers](https://jobs.lever.co/cred) |
| Databricks | greenhouse | healthy | 9 | [Official careers](https://job-boards.greenhouse.io/databricks) |
| Datadog | greenhouse | healthy | 3 | [Official careers](https://job-boards.greenhouse.io/datadog) |
| Dell | html | error | 0 | [Official careers](https://jobs.dell.com/en/search-jobs/software) |
| Deutsche Bank | workday | healthy | 0 | [Official careers](https://db.wd3.myworkdayjobs.com/DBWebsite) |
| Dropbox | greenhouse | healthy | 0 | [Official careers](https://job-boards.greenhouse.io/dropbox) |
| Duolingo | greenhouse | healthy | 0 | [Official careers](https://job-boards.greenhouse.io/duolingo) |
| Elastic | greenhouse | healthy | 3 | [Official careers](https://job-boards.greenhouse.io/elastic) |
| Ericsson | html | error | 0 | [Official careers](https://jobs.ericsson.com/careers) |
| Expedia Group | workday | healthy | 12 | [Official careers](https://expedia.wd108.myworkdayjobs.com/search) |
| Fidelity | workday | healthy | 0 | [Official careers](https://fmr.wd1.myworkdayjobs.com/FidelityCareers) |
| Figma | greenhouse | healthy | 3 | [Official careers](https://job-boards.greenhouse.io/figma) |
| Freshworks | smartrecruiters | healthy | 0 | [Official careers](https://careers.smartrecruiters.com/Freshworks) |
| GE Vernova | workday | partial | 4 | [Official careers](https://gevernova.wd5.myworkdayjobs.com/Vernova_ExternalSite) |
| GitLab | greenhouse | healthy | 0 | [Official careers](https://job-boards.greenhouse.io/gitlab) |
| Goldman Sachs | html | error | 0 | [Official careers](https://higher.gs.com/results?search=software) |
| Groww | greenhouse | healthy | 0 | [Official careers](https://job-boards.greenhouse.io/groww) |
| Gusto | greenhouse | healthy | 0 | [Official careers](https://job-boards.greenhouse.io/gusto) |
| HP | workday | healthy | 0 | [Official careers](https://hp.wd5.myworkdayjobs.com/ExternalCareerSite) |
| HPE | workday | healthy | 1 | [Official careers](https://hpe.wd5.myworkdayjobs.com/Jobsathpe) |
| HSBC | html | partial | 0 | [Official careers](https://apply.careers.hsbc.com/search/?q=software) |
| HubSpot | html | error | 0 | [Official careers](https://www.hubspot.com/careers/jobs) |
| IBM | html | error | 0 | [Official careers](https://www.ibm.com/careers/search) |
| Intel | workday | healthy | 0 | [Official careers](https://intel.wd1.myworkdayjobs.com/External) |
| Intuit | html | error | 0 | [Official careers](https://jobs.intuit.com/search-jobs/software) |
| JPMorgan Chase | oracle | partial | 26 | [Official careers](https://jpmc.fa.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_1001/jobs) |
| Linear | ashby | healthy | 0 | [Official careers](https://jobs.ashbyhq.com/linear) |
| Mastercard | workday | healthy | 0 | [Official careers](https://mastercard.wd1.myworkdayjobs.com/CorporateCareers) |
| Meesho | lever | healthy | 0 | [Official careers](https://jobs.lever.co/meesho) |
| Mixpanel | greenhouse | healthy | 0 | [Official careers](https://job-boards.greenhouse.io/mixpanel) |
| MongoDB | greenhouse | healthy | 1 | [Official careers](https://job-boards.greenhouse.io/mongodb) |
| Morgan Stanley | workday | healthy | 0 | [Official careers](https://ms.wd5.myworkdayjobs.com/External) |
| Nasdaq | workday | healthy | 0 | [Official careers](https://nasdaq.wd1.myworkdayjobs.com/Global_External_Site) |
| Nokia | html | error | 0 | [Official careers](https://careers.nokia.com/en/sites/CX/jobs) |
| Notion | ashby | healthy | 6 | [Official careers](https://jobs.ashbyhq.com/notion) |
| Nutanix | html | error | 0 | [Official careers](https://careers.nutanix.com/en/jobs/) |
| NVIDIA | workday | healthy | 4 | [Official careers](https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite) |
| Okta | greenhouse | healthy | 0 | [Official careers](https://job-boards.greenhouse.io/okta) |
| OpenAI | ashby | healthy | 1 | [Official careers](https://jobs.ashbyhq.com/openai) |
| Palantir | lever | healthy | 41 | [Official careers](https://jobs.lever.co/palantir) |
| PayPal | workday | healthy | 0 | [Official careers](https://paypal.wd1.myworkdayjobs.com/jobs) |
| Perplexity | ashby | healthy | 0 | [Official careers](https://jobs.ashbyhq.com/perplexity) |
| PhonePe | html | error | 0 | [Official careers](https://www.phonepe.com/careers/job-openings/) |
| Pinterest | greenhouse | healthy | 8 | [Official careers](https://job-boards.greenhouse.io/pinterest) |
| Plaid | html | error | 0 | [Official careers](https://plaid.com/careers/openings/) |
| Postman | html | error | 0 | [Official careers](https://www.postman.com/company/careers/) |
| Qualcomm | html | error | 0 | [Official careers](https://careers.qualcomm.com/careers) |
| Razorpay | greenhouse | healthy | 0 | [Official careers](https://job-boards.greenhouse.io/razorpaysoftwareprivatelimited) |
| Red Hat | workday | healthy | 3 | [Official careers](https://redhat.wd5.myworkdayjobs.com/Jobs) |
| Reddit | greenhouse | healthy | 1 | [Official careers](https://job-boards.greenhouse.io/reddit) |
| Rubrik | greenhouse | healthy | 4 | [Official careers](https://job-boards.greenhouse.io/rubrik) |
| Salesforce | workday | healthy | 0 | [Official careers](https://salesforce.wd12.myworkdayjobs.com/External_Career_Site) |
| Samsara | greenhouse | healthy | 0 | [Official careers](https://job-boards.greenhouse.io/samsara) |
| SAP | html | error | 0 | [Official careers](https://jobs.sap.com/search/?q=software) |
| SentinelOne | greenhouse | healthy | 0 | [Official careers](https://job-boards.greenhouse.io/sentinellabs) |
| ServiceNow | smartrecruiters | healthy | 5 | [Official careers](https://careers.smartrecruiters.com/ServiceNow) |
| Siemens | html | error | 0 | [Official careers](https://jobs.siemens.com/careers) |
| Spotify | lever | healthy | 0 | [Official careers](https://jobs.lever.co/spotify) |
| Stripe | greenhouse | healthy | 26 | [Official careers](https://job-boards.greenhouse.io/stripe) |
| Swiggy | html | error | 0 | [Official careers](https://careers.swiggy.com/) |
| Twilio | greenhouse | healthy | 3 | [Official careers](https://job-boards.greenhouse.io/twilio) |
| Visa | workday | healthy | 0 | [Official careers](https://visa.wd5.myworkdayjobs.com/Visa) |
| Walmart | workday | healthy | 1 | [Official careers](https://walmart.wd504.myworkdayjobs.com/WalmartExternal) |
| Wells Fargo | workday | healthy | 0 | [Official careers](https://wf.wd1.myworkdayjobs.com/WellsFargoJobs) |
| Workday | workday | healthy | 0 | [Official careers](https://workday.wd5.myworkdayjobs.com/Workday) |
| Zomato | html | error | 0 | [Official careers](https://www.zomato.com/careers) |
| Zscaler | greenhouse | healthy | 0 | [Official careers](https://job-boards.greenhouse.io/zscaler) |

## Atlassian repair — 15 October 2026

Atlassian now has a dedicated adapter. Its public careers board embeds the full posting list in `window._uniformPreloadedComposition`; the adapter reads the JSON value without executing JavaScript. It then checks individual official `/company/careers/details/{id}` pages and reads their visible role descriptions when JobPosting JSON-LD is absent. Nullable location fields fall back to the visible detail-page location.

The verified live refresh returned **5 matching jobs** and marked Atlassian connected. Those matches are outside India in this scan; choose Worldwide to see them. The previous table is a historical snapshot from the original run, before this repair.

The company-addition workflow was also tested against a real general careers page in an isolated database. It detected the employer’s Greenhouse board, saved the custom company, and completed the scheduled collection. Archived saved-job display was verified with an explicitly labeled demo fixture in that isolated instance.
