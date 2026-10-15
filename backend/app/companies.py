"""Editable source registry. URLs are public employer/ATS career sources.
A configured source is not a claim of complete or verified coverage.
"""
import re


def wd(name, host, tenant, site, sector="Technology"):
    return dict(name=name, adapter="workday", url=f"https://{host}/{site}",
                config=dict(host=host, tenant=tenant, site=site), sector=sector)


def board(name, adapter, token, sector="Technology"):
    root = {"greenhouse": "https://job-boards.greenhouse.io/", "lever": "https://jobs.lever.co/",
            "smartrecruiters": "https://careers.smartrecruiters.com/", "ashby": "https://jobs.ashbyhq.com/"}[adapter]
    return dict(name=name, adapter=adapter, url=root + token, config=dict(token=token), sector=sector)


def page(name, url, sector="Technology", **config):
    return dict(name=name, adapter="html", url=url, config=config, sector=sector)


COMPANIES = [
    wd("Autodesk", "autodesk.wd1.myworkdayjobs.com", "autodesk", "Ext"),
    wd("Mastercard", "mastercard.wd1.myworkdayjobs.com", "mastercard", "CorporateCareers", "Finance"),
    page("Zomato", "https://www.zomato.com/careers", "Consumer tech"),
    wd("Cisco", "cisco.wd5.myworkdayjobs.com", "cisco", "Cisco_Careers"),
    page("Cognizant", "https://careers.cognizant.com/india-en/jobs/?keyword=software", "IT services"),
    wd("GE Vernova", "gevernova.wd5.myworkdayjobs.com", "gevernova", "Vernova_ExternalSite", "Industrial tech"),
    wd("Visa", "visa.wd5.myworkdayjobs.com", "visa", "Visa", "Finance"),
    dict(name="JPMorgan Chase", adapter="oracle", url="https://jpmc.fa.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_1001/jobs", config=dict(host="jpmc.fa.oraclecloud.com", site="CX_1001"), sector="Finance"),
    page("Goldman Sachs", "https://higher.gs.com/results?search=software", "Finance"),
    wd("Deutsche Bank", "db.wd3.myworkdayjobs.com", "db", "DBWebsite", "Finance"),
    page("HSBC", "https://apply.careers.hsbc.com/search/?q=software", "Finance", pagination="startrow", page_size=25),
    # Additional employers: publicly accessible ATS boards whenever available.
    wd("Adobe", "adobe.wd5.myworkdayjobs.com", "adobe", "external_experienced"),
    wd("NVIDIA", "nvidia.wd5.myworkdayjobs.com", "nvidia", "NVIDIAExternalCareerSite"),
    wd("Salesforce", "salesforce.wd12.myworkdayjobs.com", "salesforce", "External_Career_Site"),
    wd("PayPal", "paypal.wd1.myworkdayjobs.com", "paypal", "jobs", "Finance"),
    wd("Walmart", "walmart.wd504.myworkdayjobs.com", "walmart", "WalmartExternal", "Consumer tech"),
    wd("Workday", "workday.wd5.myworkdayjobs.com", "workday", "Workday"),
    board("ServiceNow", "smartrecruiters", "ServiceNow"),
    wd("Intel", "intel.wd1.myworkdayjobs.com", "intel", "External"),
    page("Qualcomm", "https://careers.qualcomm.com/careers"),
    page("AMD", "https://careers.amd.com/careers-home/jobs"),
    wd("Broadcom", "broadcom.wd1.myworkdayjobs.com", "broadcom", "External_Career"),
    page("Dell", "https://jobs.dell.com/en/search-jobs/software"),
    wd("HP", "hp.wd5.myworkdayjobs.com", "hp", "ExternalCareerSite"),
    wd("HPE", "hpe.wd5.myworkdayjobs.com", "hpe", "Jobsathpe"),
    wd("Red Hat", "redhat.wd5.myworkdayjobs.com", "redhat", "Jobs"),
    page("IBM", "https://www.ibm.com/careers/search"),
    wd("Accenture", "accenture.wd103.myworkdayjobs.com", "accenture", "AccentureCareers", "IT services"),
    wd("Wells Fargo", "wf.wd1.myworkdayjobs.com", "wf", "WellsFargoJobs", "Finance"),
    wd("Bank of America", "ghr.wd1.myworkdayjobs.com", "ghr", "Lateral-US", "Finance"),
    wd("BlackRock", "blackrock.wd1.myworkdayjobs.com", "blackrock", "BlackRock_Professional", "Finance"),
    wd("Morgan Stanley", "ms.wd5.myworkdayjobs.com", "ms", "External", "Finance"),
    wd("Barclays", "barclays.wd3.myworkdayjobs.com", "barclays", "external_career_site_barclays", "Finance"),
    wd("Citi", "citi.wd5.myworkdayjobs.com", "citi", "2", "Finance"),
    wd("Fidelity", "fmr.wd1.myworkdayjobs.com", "fmr", "FidelityCareers", "Finance"),
    wd("Nasdaq", "nasdaq.wd1.myworkdayjobs.com", "nasdaq", "Global_External_Site", "Finance"),
    wd("Expedia Group", "expedia.wd108.myworkdayjobs.com", "expedia", "search", "Consumer tech"),
    page("Intuit", "https://jobs.intuit.com/search-jobs/software", "Finance"),
    page("SAP", "https://jobs.sap.com/search/?q=software", pagination="startrow", page_size=25),
    page("Siemens", "https://jobs.siemens.com/careers", "Industrial tech"),
    page("Ericsson", "https://jobs.ericsson.com/careers"),
    page("Nokia", "https://careers.nokia.com/en/sites/CX/jobs"),
    board("Razorpay", "greenhouse", "razorpaysoftwareprivatelimited", "Finance"),
    board("Stripe", "greenhouse", "stripe", "Finance"),
    dict(name="Atlassian",adapter="atlassian",url="https://www.atlassian.com/company/careers/all-jobs",config={},sector="Technology"),
    board("Airbnb", "greenhouse", "airbnb", "Consumer tech"),
    board("Databricks", "greenhouse", "databricks"),
    board("MongoDB", "greenhouse", "mongodb"),
    board("Cloudflare", "greenhouse", "cloudflare"),
    board("Twilio", "greenhouse", "twilio"),
    board("Rubrik", "greenhouse", "rubrik"),
    page("Nutanix", "https://careers.nutanix.com/en/jobs/"),
    board("Okta", "greenhouse", "okta"),
    board("Datadog", "greenhouse", "datadog"),
    board("Elastic", "greenhouse", "elastic"),
    board("GitLab", "greenhouse", "gitlab"),
    board("Figma", "greenhouse", "figma"),
    board("Notion", "ashby", "notion"),
    board("Coinbase", "greenhouse", "coinbase", "Finance"),
    page("PhonePe", "https://www.phonepe.com/careers/job-openings/", "Finance"),
    board("Groww", "greenhouse", "groww", "Finance"),
    board("Meesho", "lever", "meesho", "Consumer tech"),
    page("Swiggy", "https://careers.swiggy.com/", "Consumer tech"),
    board("Spotify", "lever", "spotify", "Consumer tech"),
    board("Palantir", "lever", "palantir"),
    page("Plaid", "https://plaid.com/careers/openings/", "Finance"),
    board("CRED", "lever", "cred", "Finance"),
    board("Bosch", "smartrecruiters", "BoschGroup", "Industrial tech"),
    board("Freshworks", "smartrecruiters", "Freshworks"),
    board("OpenAI", "ashby", "openai"),
    board("Perplexity", "ashby", "perplexity"),
    board("Linear", "ashby", "linear"),
    page("Postman", "https://www.postman.com/company/careers/"),
    page("BrowserStack", "https://www.browserstack.com/careers"),
    page("Confluent", "https://careers.confluent.io/jobs"),
    board("Asana", "greenhouse", "asana"),
    board("Dropbox", "greenhouse", "dropbox"),
    board("Pinterest", "greenhouse", "pinterest", "Consumer tech"),
    board("Reddit", "greenhouse", "reddit", "Consumer tech"),
    page("HubSpot", "https://www.hubspot.com/careers/jobs"),
    board("Coursera", "greenhouse", "coursera", "Consumer tech"),
    board("Duolingo", "greenhouse", "duolingo", "Consumer tech"),
    page("Amplitude", "https://amplitude.com/careers"),
    board("Mixpanel", "greenhouse", "mixpanel"),
    board("SentinelOne", "greenhouse", "sentinellabs"),
    board("Zscaler", "greenhouse", "zscaler"),
    board("Samsara", "greenhouse", "samsara"),
    board("Gusto", "greenhouse", "gusto", "Finance"),
]
for company in COMPANIES:
    company["id"] = re.sub(r"[^a-z0-9]+", "-", company["name"].lower()).strip("-")
