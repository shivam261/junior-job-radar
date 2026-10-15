# Launchpad

A personal job-discovery application for early-career software engineers. Built with **FastAPI, React + TypeScript, and SQLite**. Search jobs directly collected from public company career sources, understand why each one matched, save a shortlist, and open the original employer posting to apply.

The source registry includes **88 companies**: Autodesk, Mastercard, Zomato, Cisco, Cognizant, GE Vernova, Visa, JPMorgan Chase, Goldman Sachs, Deutsche Bank, HSBC, and 77 additional employers. Registration does not imply that every source is accessible or complete. The Companies screen shows the actual outcome of each refresh.

## Run locally

Requires Python 3.10+ and Node.js 20.19+ (or Node.js 22.12+).

From the project root:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.lock
cd frontend
npm ci
npm run build
cd ../backend
python -m app.demo
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open **http://127.0.0.1:8000**. API documentation is at **http://127.0.0.1:8000/docs**.

The backend serves the built frontend, starts a live refresh, and checks enabled companies every six hours while it remains running. The first collection can take several minutes. It processes all enabled sources and job details with bounded concurrency. Results appear as each company finishes. The collection does not run while the application is stopped.

`python -m app.demo` creates optional, clearly labeled demo fixtures in a separate data scope. It is safe to run again. Demo mode must be explicitly selected in the interface and never substitutes for live results. Demo links open company careers pages, because example vacancies do not have real job URLs.

### Frontend development

After installing the dependencies:

```bash
./scripts/dev.sh
```

Open http://127.0.0.1:5173. Vite forwards `/api` to FastAPI on port 8000. Stop any existing server using those ports before running the development script. For frontend development without automatic collection:

```bash
AUTO_REFRESH=false ./scripts/dev.sh
```

### Tests and production build

```bash
cd backend
../.venv/bin/python -m pytest -q
cd ../frontend
npm run build
```

Backend tests cover experience classification, feed parsing and pagination, original URLs, source failures, bookmark persistence, demo isolation, refresh concurrency, source settings, and retiring jobs only after complete successful snapshots.

## Features

- Search titles, skills, descriptions, and company names; filter by location, companies, experience confidence, and work arrangement.
- India is the initial location filter and a visible quick filter. It recognizes Indian city aliases plus India/IND/IN country names and codes; choose Worldwide or Anywhere to search globally.
- Separate confirmed experience matches from potential graduate/junior matches.
- Save and unsave jobs with persistent SQLite bookmarks.
- Read plain-text descriptions and the evidence used by the experience matcher.
- Open original employer job URLs in a new tab.
- Add a company by name and public HTTPS careers URL; automatically detect its recruiting platform, save it in SQLite, and queue a refresh.
- Enable/pause companies and refresh a single company or the entire directory.
- View source coverage, errors, last successful checks, and refresh history.
- Responsive mobile navigation and filters, keyboard focus states, and accessible details dialogs.
- No API keys or third-party paid services required.

## How collection works

**Workday, Greenhouse, Lever, SmartRecruiters, Ashby, and Oracle candidate feeds**, plus Atlassian’s embedded board and public detail pages, use dedicated adapters. HTML careers pages use robots-aware crawling of public job links and visible structured descriptions. The normalizer stores plain text, location, source job ID, original URL, skills, work arrangement, dates when provided, and match evidence.

A title must indicate software development. Senior, staff, principal, lead, manager, architect, and Engineer III/IV titles are excluded. Explicit numeric experience requirements must stay within the conservative 0–2 year window; a `1+` or `2+` minimum qualifies, while a `2–5` range is excluded. Requirements above two years anywhere in the relevant description exclude the role. Graduate, junior, intern, associate, or Engineer I titles without explicit years are **possible matches**, not confirmed eligibility. General software engineer titles without experience evidence are excluded.

This conservative approach can miss qualified jobs, including descriptions using spelled-out experience requirements, alternative education/experience pathways, or unfamiliar role titles. It does not decide work authorization or other application eligibility. Always review the original posting.

### Coverage and freshness

- **Connected:** An adapter retrieved its complete visible feed snapshot within configured limits. This describes feed coverage, not a guarantee that every employer vacancy is public.
- **Partial coverage:** A keyword-scoped Oracle result, an HTML page, a pagination limit, or a Workday feed reaching its 2,000-result ceiling. Newly collected matches are updated; existing jobs are retained.
- **Needs attention:** The site moved, blocked requests, failed, or returned a format the adapter cannot read. Previously stored jobs stay available and their last-seen timestamps remain unchanged.
- **Not checked:** Collection has not completed for this source.

For a complete successful snapshot, previous jobs missing from the employer’s board are marked inactive with a removal date and reason. A posting still on the board whose requirements no longer qualify is separately labeled "No longer matches your experience filter." Failed and partial snapshots never retire jobs. Saved jobs keep their descriptions and bookmarks after retirement. The Saved jobs screen defaults to all saved roles and offers Open and Closed / archived filters. A returning role is reactivated without losing its bookmark. Sources may move to a new ATS and need their registry entry updated. Some sites require JavaScript or do not expose a public job feed; this application does not bypass login, robots restrictions, or CAPTCHA.

Greenhouse API reference: https://docs.greenhouse.io/job-board.html

Lever public postings API: https://github.com/lever/postings-api

SmartRecruiters reference: https://developers.smartrecruiters.com/docs/endpoints

See [architecture](docs/architecture.md) and [source verification](docs/source-verification.md) for implementation details and audit evidence.

## Add a company

Open **Companies → Add company**, enter its name, official public HTTPS careers URL, and industry, then select **Add & collect openings**. The company is persisted in SQLite, including after server restarts.

Direct Workday, Greenhouse, Lever, SmartRecruiters, Ashby, Oracle, and Atlassian URLs are recognized immediately. For a general careers page, the collector inspects its links, embedded recruiting URLs, and up to three same-site links to an openings page. Supported feeds use their dedicated adapter; other sites use the robots-aware general HTML collector. The company card reports detected source type, progress, collected matches, and any access limitation. Collection is queued after an ongoing refresh instead of being discarded. Duplicate company names or identical careers URLs are rejected.

Sites requiring login, CAPTCHA, unsupported JavaScript APIs, or restricted crawling may still need a dedicated adapter. A zero match count on a connected source means the conservative experience filter found no eligible roles; it does not mean collection failed. Custom URLs must be public HTTPS websites; private-network addresses and redirects to them are rejected.

## Configuration

Set environment variables before starting FastAPI. Example:

```bash
AUTO_REFRESH=false REFRESH_INTERVAL_SECONDS=21600 \
  python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

| Variable | Default | Purpose |
| --- | --- | --- |
| `DATABASE_PATH` | `backend/data/jobs.sqlite3` | Persistent SQLite file |
| `AUTO_REFRESH` | `true` | Refresh on startup and on schedule |
| `REFRESH_ON_STARTUP` | `true` | Start an immediate collection when the server starts |
| `REFRESH_INTERVAL_SECONDS` | `21600` | Scheduled interval; minimum 300 seconds |
| `MAX_SOURCE_PAGES` | `150` | Pagination safety ceiling per source |
| `CORS_ORIGINS` | localhost/127.0.0.1:5173 | Allowed frontend origins |

To change company sources, edit `backend/app/companies.py` and restart the backend. Existing bookmarks, enabled settings, and live jobs are retained. To refresh through the command line, stop the backend first and run:

```bash
cd backend
../.venv/bin/python -m app.refresh autodesk mastercard visa
```

Without company IDs, it refreshes all enabled companies. `scripts/check_sources.py` is a read-only connectivity check; it does not collect details or guarantee complete coverage.

This application is designed for **one local user and one backend process**. Run a single Uvicorn worker. Browsers connected to the same instance share bookmarks and source settings. The default bind address is loopback. A public/multi-user deployment would require authentication, per-user storage, and a dedicated scheduler/worker with a distributed lock.
