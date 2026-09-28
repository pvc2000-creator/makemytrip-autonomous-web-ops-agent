# Architecture

## Run lifecycle

Every run is a job with an explicit state, persisted in `runs.state` and mirrored as `state` events
in `run_events`:

```
task_intake → plan_generated → [awaiting_approval] → browser_execution → extraction
            → comparison → reasoning ──(one rerun of empty sources)──▶ browser_execution
            → completion → completed | pending_review | failed
```

`awaiting_approval` appears only when the task has `requires_approval=true`. A reviewer or admin
approving the plan resumes every run waiting on it; rejecting fails them with a visible reason.

## Components

**API (`backend/api/main.py`).** FastAPI app. Validates intake (known template, allowlisted URLs,
valid schedule), creates plans and runs, serves run detail, metrics, snapshots, CSV exports, and the
console at `/`. Every response carries an `x-trace-id` header; each run also has its own `trace_id`.

**Orchestrator (`backend/jobs/orchestrator.py`).** Runs jobs on a thread pool (4 workers), one active
run per task. Writes an audit event for every state change, browser action, extraction result,
warning, routing decision and reviewer action. Also hosts the scheduler, which starts due recurring
tasks every 15 seconds.

**Planner (`agents/planner/planner.py`).** Builds a deterministic plan per URL
(navigate → dismiss pop-ups → wait for content → screenshot → capture HTML → extract), followed by
compare → summarize → route. Adds template-specific risks and stop conditions. With an API key, an
LLM may add risks and reorder URLs, but only within the whitelisted tool set and the task's own URLs;
anything else is discarded and the template plan is kept.

**Browser worker (`agents/browser_execution/worker.py`).** Playwright/Chromium when available,
otherwise httpx. Every visit passes the `BrowserPolicy` gate first. Retries use exponential back-off
and only for retryable failures (timeouts, 5xx, 429). Captures HTML to `SNAPSHOT_DIR`, plus a
full-page screenshot under Playwright.

**Extraction (`extraction/`).** Schemas define container and field selectors with fallbacks. The
parser scores confidence (fallback container −0.25, fallback field −0.10, missing required field
−0.30, normalizer warning −0.10), normalizes prices/dates/availability/locations, removes duplicates
and computes a stable `entity_key` from the schema's entity fields so records line up across runs
even after a redesign. Validators apply plausibility bounds and stale-offer checks.

**Reasoning loop (`agents/reasoning_loop/reasoner.py`).** Compares against the latest successful run
of the same task. Classifies each difference as material, noise (below threshold), formatting
(same value, different presentation) or missing data. Requests a single rerun for sources that had
data before and returned none; if still empty, their "removals" become missing data rather than false
withdrawals. Routes to review on low confidence, layout drift, failed sources or ≥10% price moves.

**Completion (`agents/completion/completer.py`).** Produces the summary (headline, what changed, why
it matters, evidence with source and confidence, owner, actions, record mix), alerts for the
dashboard/alert/review queues, and a CSV export.

## Data model

| Table | Holds |
|---|---|
| tasks | Workflow definition: template, objective, URLs, fields, schedule, owner, approval flag |
| plans | Steps, tools, schema, risks, stop conditions, planner type, approval status |
| runs | State, trigger, trace id, pages, retries, cost, error, review flag, timings |
| run_events | Append-only audit log |
| snapshots | URL, title, HTTP status, content hash, HTML path, screenshot path |
| extracted_records | Entity key, fields, snippet, source, confidence, validation notes |
| comparisons | Change type, classification, field, before/after, delta, confidence |
| summaries | Headline, structured body, alerts, export path |
| feedback | Reviewer verdicts on records and summaries |

SQLite (WAL mode) locally; any SQLAlchemy URL in production (Postgres/Supabase).

## Scaling path

Move the orchestrator's thread pool to a queue (Celery, RQ, Arq) with browser workers as separate
processes; run the scheduler as a single leader; store snapshots in object storage; add pgvector for
semantic memory of past findings once workflows need it.
