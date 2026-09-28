# API reference

Base URL: the API host (e.g. `http://127.0.0.1:8000`). JSON in and out.

**Auth.** `Authorization: Bearer <token>` using the `API_TOKENS` mapping. Without a token the demo
console sends `x-role: admin|creator|reviewer`. Permissions: creator (task, plan, run write), reviewer
(plan approve, feedback), admin (all), service (run write).

| Method | Path | Purpose |
|---|---|---|
| GET | /api/health | Status, LLM on/off, browser engine, allowlist, states |
| GET | /api/templates | Extraction schemas and their fields |
| GET | /api/tools | Tool vocabulary the planner may use |
| POST | /api/tasks | Create a workflow (validated) |
| GET | /api/tasks | List workflows with last run |
| PATCH | /api/tasks/{id} | Update schedule, active, approval flag, owner, objective |
| POST | /api/plans | Generate a plan for a task |
| GET | /api/plans/{id} | Get a plan |
| POST | /api/plans/{id}/approve | `{approve: bool}`; resumes or fails waiting runs |
| POST | /api/runs | Start a run `{task_id, plan_id?, options?: {speed, headed, step_mode}}` → `{run_id}` (202) |
| GET | /api/runs | List runs (`?task_id=`) |
| GET | /api/runs/{id} | Full run: state, plan, events, snapshots, records, comparisons, summary, feedback |
| GET | /api/runs/{id}/export.csv | Change export |
| GET | /api/snapshots/{id}/html | Captured HTML |
| GET | /api/snapshots/{id}/screenshot | Screenshot (Playwright engine) |
| POST | /api/extract | Run a schema on `html` or `snapshot_id` |
| POST | /api/compare | Compare a run with its predecessor or `against_run_id` |
| POST | /api/complete | Regenerate summary, alerts and export for a run |
| POST | /api/feedback | `{run_id, target_type, target_id, verdict, correction?, note?}` |
| GET | /api/workflows | Workflow types with kind, inputs, default URLs and fields |
| GET | /api/runs/{id}/live?since=N | Live state: frames after N, step statuses, caption, URL, control state, pending approval |
| GET | /api/runs/{id}/frames/{seq}.jpg | One browser frame |
| POST | /api/runs/{id}/control | `{action: pause|resume|step|stop}` |
| POST | /api/runs/{id}/input | `{approve: bool, note?}` answers an approval step (reviewer/admin) |
| GET | /api/live | Active and recently finished runs for the live wall |
| GET | /api/metrics | Completion rate, review backlog, confidence, source health, failures, spend |
| GET/POST | /mock/state, /mock/advance | Demo market clock |

## Examples

```bash
# create a workflow
curl -X POST localhost:8000/api/tasks -H 'Authorization: Bearer creator-token' -H 'content-type: application/json' -d '{
  "name":"Goa hotel watch","template":"hotel_pricing",
  "objective":"Track Goa hotel rates 14 days out and flag moves over 3%",
  "target_urls":["http://127.0.0.1:8000/mock/hotels/goa"],"schedule":"daily","requires_approval":true}'

# start a run, then poll it
curl -X POST localhost:8000/api/runs -H 'Authorization: Bearer creator-token' -H 'content-type: application/json' -d '{"task_id":"task_..."}'
curl localhost:8000/api/runs/run_...
```

## Errors

| Status | Meaning |
|---|---|
| 401 | Unknown bearer token |
| 403 | Role lacks the permission (message names it) |
| 404 | Task, plan, run or snapshot not found |
| 409 | A run for this task is already in progress |
| 422 | Intake validation failed; `detail.problems` lists each issue |

Run-level failures are not HTTP errors: the run ends in `failed` with `error`, and each source
failure is an `error` event with a `category`: `policy_restriction`, `browser_blocked`,
`rate_limited_by_source`, `timeout`, `source_unavailable`, `engine_unavailable`.
