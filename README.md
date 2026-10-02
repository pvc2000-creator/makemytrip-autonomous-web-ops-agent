# MakeMyTrip Autonomous Web Operations Agent

A governed browser-agent platform that turns recurring web monitoring (competitor offers, hotel
pricing, campaign pages, partner updates, travel demand signals) into auditable workflows:

**task intake → agent planning → (plan approval) → controlled browser execution → structured
extraction → snapshot comparison → reasoning loop → completion (summary, alerts, export, review)**

> **Deployed application:** `https://mmt-web-ops-agent-g2bj.onrender.com/` (add after deploying; see *Deploy*)
> **Interactive demo (no backend needed):** open `frontend/index.html` directly; it detects that no
> API is reachable and runs the same pipeline in the browser against bundled sample sources.
> **Demonstration video:** `<Google Drive link, "Anyone with the link can view">`

![Live browser view](docs/screenshots/01_live_browser_booking.png)

## Run it on Windows (10 or 11)

1. Install **Python 3.10 or newer** from python.org. On the first installer screen tick **"Add python.exe to PATH"**.
2. Unzip this folder somewhere without special permissions, e.g. `C:\Users\<you>\web-ops-agent`.
3. Double-click **`setup_windows.bat`**. It creates a virtual environment, installs packages, downloads
   Chromium for the agent, and creates `.env`. Takes a few minutes the first time.
4. Double-click **`start_windows.bat`**. The console opens at http://127.0.0.1:8000. Close that window to stop.

`reset_data_windows.bat` clears run history, snapshots and frames if you want a clean demo.

macOS / Linux: `python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt &&
python -m playwright install chromium && uvicorn backend.api.main:app --port 8000`.

## Watching the agent work

- **Live browsers** (sidebar) shows every running workflow with its latest browser frame.
- Open a run and the **Live browser** tab streams what Chromium is doing: the page, the URL, an orange
  box around the element the agent is about to click or type into, and a caption of the action. The step
  list on the right ticks off in real time. After the run, drag the slider to replay every frame.
- **Controls**: Pause, Resume, Step one action, Stop run.
- **Run options** (shown when you click Run now / Start): speed (fast, normal, slow), step-through mode,
  and **"Also open a visible Chrome window on this computer"** to watch the real browser window on your
  laptop. Set `BROWSER_HEADED=true` in `.env` to make that the default.
- When a transaction reaches its approval step, an **approval card** appears in the live view and the run
  shows up in the **Review queue**. Approve and the agent continues; decline and it stops before the
  irreversible step.

## Workflow types

| Type | Kind | Demo website | What the agent does in the browser |
|---|---|---|---|
| Flight booking | Transaction | SkyRoam Travel | Types origin/destination/date, searches, filters non-stop, sorts, records fares, picks the cheapest, fills traveller details, unticks pre-ticked insurance, reads the total, **asks you to approve**, confirms and reads the reference |
| Hotel booking | Transaction | SkyRoam Travel | Filters free cancellation, sorts by price, picks the cheapest hotel and then the cheapest room, fills guest details, unticks the airport-pickup add-on, **asks you to approve**, confirms |
| Flight fare search | Monitor | SkyRoam Travel | Fills the search form, applies filters, records every fare, compares with the last run |
| Hotel search and filter | Monitor | SkyRoam Travel | Ticks free cancellation, sorts by price, reads every results page |
| Train seat availability | Monitor | IndiRail Express | Searches a route and class; records AVL / RAC / waitlist and fare per train |
| Activities and tours | Monitor | Explorely | Filters by category, sorts by price, reads every page of experiences |
| Hotel reviews watch | Monitor | StayVerdict | Sorts newest first, reads review pages, flags new and negative reviews |
| Travel advisory watch | Monitor | TravelSafe | Tracks advisory levels, summaries and visa rules per country |
| Competitor offers | Monitor | TripNova, SkyRoam | Reads holiday packages, prices, promotions and validity |
| Hotel pricing | Monitor | StayBay Hotels | Nightly rates and availability (the Goa page is redesigned every third day) |
| Campaign page | Monitor | SkyRoam campaigns | Headline, offer copy, CTA and placement |
| Partner updates | Monitor | PartnerHub | Supplier notices |
| Travel trends | Monitor | Wanderlytics | Destination demand index and events |
| Catalogue scan | Monitor | books.toscrape.com (real, public) | Opens a category and reads listings across pages (needs internet) |
| Custom steps | Either | Any allowlisted site | Your own JSON step list |

### Demo websites

Open **http://127.0.0.1:8000/mock** (or *Demo websites ↗* in the console sidebar) to browse all ten bundled sites
yourself: SkyRoam Travel, TripNova Holidays, StayBay Hotels, PartnerHub, Wanderlytics, IndiRail Express,
Explorely, StayVerdict and TravelSafe, plus SkyRoam campaign pages. Each has its own brand, a cookie
banner, realistic layouts and illustrations, and data that moves when you press *Move market forward a day*
on the dashboard, so repeated runs have real changes to detect. All brands, airlines, hotels, reviews
and advisories are fictional; nothing is charged. Illustrations are generated SVG, so everything works offline.

### Custom steps

```json
[
  {"tool": "navigate", "target": "http://127.0.0.1:8000/mock/travel/hotels?city=jaipur", "purpose": "Open results"},
  {"tool": "dismiss_popups", "args": {"selectors": ["#accept-cookies"]}, "purpose": "Accept cookies"},
  {"tool": "select", "args": {"selector": "#sort", "value": "rating"}, "purpose": "Sort by rating"},
  {"tool": "paginate", "args": {"schema": "hotel_listings", "next_selector": ".pagination a.next", "max_pages": 2}, "purpose": "Read pages"}
]
```

Tools: `navigate, dismiss_popups, wait_for, click (selector or text), fill, select, check, uncheck,
press, scroll, extract, paginate, pick_best, capture, assert_text, screenshot, approval`.
Values can use `{{placeholders}}` from workflow inputs or earlier `capture` steps. To target another
website, add its hostname to `DOMAIN_ALLOWLIST` in `.env` after confirming its terms allow automation.

## What is implemented

| Requirement (from the brief) | Where |
|---|---|
| Task intake with validation, templates, inputs, schedules | `backend/api/main.py`, `agents/planner/workflows.py` |
| Planner with whitelisted tools, risks, stop conditions; optional LLM refinement | `agents/planner/` |
| Plan approval for sensitive workflows; in-run human approval for transactions | `POST /api/plans/{id}/approve`, `POST /api/runs/{id}/input` |
| Job state machine with visible states and audit log | `backend/jobs/orchestrator.py` |
| Real browser automation with live frames, highlights, pause/step/stop | `agents/browser_execution/runner.py`, `backend/jobs/live.py` |
| Allowlist on every navigation (including link clicks), rate limits, page cap, sensitive-field guard | `backend/auth/policy.py`, runner |
| Schema-driven extraction with fallback selectors and confidence | `extraction/` |
| Snapshot comparison, reasoning loop with reruns and review routing | `agents/reasoning_loop/reasoner.py` |
| Completion: grounded summary, booking outcome, owner routing, alerts, CSV | `agents/completion/completer.py` |
| Reviewer feedback; operations dashboard; live wall | `/api/feedback`, `/api/metrics`, `/api/live` |
| Tests: extraction, reasoning, policy, API end to end, real-browser flight and hotel booking, decline, pause/stop, every demo site | `tests/` (32 tests) |

## Architecture

![Approval before confirming](docs/screenshots/02_approval_before_confirm.png)

```
UI (frontend/index.html) ──REST──▶ FastAPI (backend/api)
                                     │  tasks · plans · runs · extract · compare · complete · feedback · metrics
                                     ▼
                        Orchestrator (backend/jobs)  ── thread pool + scheduler
                          │ state machine, audit events, trace ids
     ┌────────────┬───────┴─────────┬────────────────┬──────────────────┐
  Planner      Browser worker     Extraction        Reasoning loop     Completion
  (agents/     (Playwright|HTTP,  (schemas,         (compare, classify, (summary, owner,
   planner)     policy gate)       parsers,          rerun, review)      alerts, CSV)
                                   normalizers,
                                   validators)
                                     ▼
                  SQLAlchemy store (SQLite / Postgres / Supabase) + snapshot storage
```

Details: `docs/architecture.md`. API: `docs/api_reference.md`. Prompts: `docs/prompt_templates.md`.

## Models and cost

The product works fully without an LLM: planning, extraction, comparison and summaries are
deterministic and grounded in extracted records. With `ANTHROPIC_API_KEY` set, the planner can add
risks and reprioritise URLs (restricted to whitelisted tools and task URLs; invalid output is
discarded) and the completion writer rewrites the headline and "why it matters". Numbers, evidence
and owners always come from data. Per-run model spend is tracked and shown on the dashboard.

## About the bundled sources

`mock_sources/` serves realistic competitor, hotel, campaign, partner and trend pages on the
service's own host, driven by a market clock. They exist so the platform can be demonstrated and
tested end to end without scraping third-party sites. Production sources are added through
`DOMAIN_ALLOWLIST` after source-governance approval; prefer partner/internal APIs where available.

## Troubleshooting on Windows

| Symptom | Fix |
|---|---|
| `python` is not recognized | Reinstall Python and tick "Add python.exe to PATH", or install from the Microsoft Store |
| Live view says no frames / "Chromium is not installed" | Run `.venv\Scripts\python -m playwright install chromium` in this folder |
| Port 8000 already in use | Close the other server, or edit `start_windows.bat` and `PUBLIC_BASE_URL` in `.env` to use 8010 |
| Windows Defender Firewall prompt | Allow on private networks; the server only listens on 127.0.0.1 |
| books.toscrape.com run fails | Needs internet access; corporate proxies may block it |
| Old runs look wrong after upgrading | Run `reset_data_windows.bat` (the database also migrates itself automatically) |

## Known limitations

- Only 3 browsers run at once by default (`MAX_CONCURRENT_RUNS`); the rest queue.
- The scheduler runs in-process; for multiple API replicas move it to a single worker or a queue
  (Celery/RQ/Arq) with a lock.
- Authentication uses static bearer tokens (plus an `x-role` header for the demo UI). Replace with
  SSO/JWT before exposing beyond an internal network.
- Snapshot retention is not yet pruned automatically; add a retention job per `browser_policy.md`.
- Vector memory (pgvector/Qdrant) is not required for the three core workflows and is not wired in;
  snapshots and records are stored relationally with stable entity keys for comparison.

## Repository layout

```
backend/        api/ (FastAPI), jobs/ (orchestrator, scheduler), auth/ (RBAC, browser policy),
                database/ (models), services/ (LLM client), config.py
agents/         planner/, browser_execution/, reasoning_loop/, completion/
extraction/     schemas/, parsers/, normalizers/, validators/
mock_sources/   safe demo sources with edge cases
frontend/       index.html (operations console; live or demo mode)
data/           sample_task_templates.json, sample_extraction_schema.json, sample_watchlists.csv, sample_snapshots/
docs/           architecture, api_reference, browser_policy, demonstration_flow, prompt_templates, screenshots/
tests/          extraction_tests/, edge_cases/, functional_tests/, browser_tests/
deployment/     docker/Dockerfile, vercel_notes.md, environment_setup.md
```
