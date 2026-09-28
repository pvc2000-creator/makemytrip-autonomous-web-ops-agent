"""FastAPI entrypoint. Run: uvicorn backend.api.main:app --port 8000"""
import json
import logging
import os
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse
from pydantic import BaseModel, Field
from sqlalchemy import func

from agents.planner.planner import build_plan
from agents.planner.workflows import TOOLS, WORKFLOWS, catalog
from agents.reasoning_loop.reasoner import compare as compare_records
from agents.completion.completer import complete as complete_run
from agents.reasoning_loop.reasoner import Decision
from backend.auth.policy import current_role, policy, require
from backend.config import settings
from backend.database.models import (Comparison, ExtractedRecord, Feedback, Plan, Run, RunEvent, SessionLocal,
                                     Snapshot, Summary, Task, init_db, now)
from backend.jobs.live import hub
from backend.jobs.orchestrator import STATES, TERMINAL, active_runs, compute_next, start_scheduler, submit
from backend.services import llm
from extraction.parsers import parse
from extraction.schemas import SCHEMAS, get_schema
from extraction.validators import validate
from mock_sources.router import router as mock_router
from mock_sources.more_sites import router as more_router
from mock_sources.travel_site import router as travel_router

class _QuietPolling(logging.Filter):
    """Drop access-log lines for successful UI polling (GET /api/runs/..., /api/metrics). Errors still log."""
    def filter(self, record):
        msg = record.getMessage()
        quiet = ('"GET /api/runs', '"GET /api/metrics', '"GET /api/tasks', '"GET /api/live', '"GET /api/health')
        return not any(q in msg for q in quiet) or ('" 200' not in msg and '" 304' not in msg)


if os.getenv("LOG_POLLING", "false").lower() != "true":
    logging.getLogger("uvicorn.access").addFilter(_QuietPolling())

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
@asynccontextmanager
async def lifespan(_app):
    startup()
    yield


app = FastAPI(title="MakeMyTrip Autonomous Web Operations Agent", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=os.getenv("CORS_ORIGINS", "*").split(","),
                   allow_methods=["*"], allow_headers=["*"])
app.include_router(travel_router)
app.include_router(mock_router)
app.include_router(more_router)


@app.middleware("http")
async def trace_id(request: Request, call_next):
    tid = request.headers.get("x-trace-id") or uuid.uuid4().hex[:16]
    resp = await call_next(request)
    resp.headers["x-trace-id"] = tid
    return resp


# ------------------------------------------------------------------ schemas
class TaskIn(BaseModel):
    name: str = Field(min_length=3)
    template: str
    objective: str = Field(min_length=10)
    target_urls: list[str] = []
    inputs: dict = {}
    expected_fields: list[str] = []
    schedule: str = "once"
    completion_rules: dict = {}
    owner_team: str = "Growth"
    requires_approval: bool = False


class PlanIn(BaseModel):
    task_id: str


class RunOptions(BaseModel):
    headed: bool | None = None          # open a visible Chromium window on the machine running the backend
    speed: str | None = None            # fast | normal | slow
    step_mode: bool = False             # pause after every action


class RunIn(BaseModel):
    task_id: str
    plan_id: str | None = None
    options: RunOptions = RunOptions()


class ControlIn(BaseModel):
    action: str                         # pause | resume | step | stop


class InputIn(BaseModel):
    approve: bool
    note: str | None = None


class ApproveIn(BaseModel):
    approve: bool = True


class ExtractIn(BaseModel):
    schema_name: str
    url: str
    html: str | None = None
    snapshot_id: str | None = None


class CompareIn(BaseModel):
    run_id: str
    against_run_id: str | None = None


class CompleteIn(BaseModel):
    run_id: str


class FeedbackIn(BaseModel):
    run_id: str
    target_type: str
    target_id: str
    verdict: str
    correction: dict | None = None
    note: str | None = None


# ------------------------------------------------------------------ serializers
def ser(obj, *fields):
    out = {}
    for f in fields:
        v = getattr(obj, f)
        out[f] = v.isoformat() if isinstance(v, datetime) else v
    return out


TASK_F = ("id", "name", "template", "objective", "target_urls", "expected_fields", "schedule", "completion_rules",
          "owner_team", "requires_approval", "active", "next_run_at", "created_at", "inputs")
PLAN_F = ("id", "task_id", "steps", "tools", "extraction_schema", "risks", "stop_conditions", "planner", "status",
          "approved_by", "created_at")
RUN_F = ("id", "task_id", "plan_id", "state", "trigger", "trace_id", "pages_visited", "retries", "cost_usd", "error",
         "needs_review", "started_at", "finished_at", "created_at", "options", "outcome")


# ------------------------------------------------------------------ helpers
def validate_task(t: TaskIn):
    problems = []
    wf = WORKFLOWS.get(t.template)
    if not wf:
        problems.append(f"Unknown workflow type '{t.template}'. Use one of: {', '.join(WORKFLOWS)}")
    else:
        if not t.target_urls:
            t.target_urls = [u.replace("{BASE}", settings.public_base_url) for u in wf.get("default_urls", [])]
        if not t.target_urls and t.template != "custom":
            problems.append("Add at least one source URL")
        if t.template == "custom":
            steps = t.inputs.get("steps")
            if not isinstance(steps, list) or not steps:
                problems.append("Custom workflows need inputs.steps: a list of {tool, target?, args, purpose}")
            else:
                bad = [s.get("tool") for s in steps if s.get("tool") not in TOOLS]
                if bad:
                    problems.append(f"Unknown tools: {', '.join(map(str, bad))}")
                t.target_urls = t.target_urls or [s["target"] for s in steps if s.get("tool") == "navigate" and s.get("target")]
        if wf["kind"] == "transaction" and t.schedule != "once":
            problems.append("Transactions (like bookings) can only run on demand, never on a schedule")
    blocked = [u for u in t.target_urls if not policy.is_allowed(u)]
    if blocked:
        problems.append(f"Not on the domain allowlist: {', '.join(blocked)}")
    if t.schedule not in ("once", "hourly", "daily", "weekly", "campaign", "every_5_min"):
        problems.append("Schedule must be once, hourly, daily, weekly, campaign or every_5_min")
    if problems:
        raise HTTPException(422, {"message": "Task needs more detail before planning", "problems": problems})


def _new_plan(db, task):
    try:
        plan_out, cost = build_plan(task)
    except ValueError as e:
        raise HTTPException(422, str(e))
    plan = Plan(task_id=task.id, steps=[s.model_dump() for s in plan_out.steps], tools=plan_out.tools,
                extraction_schema=plan_out.extraction_schema, risks=plan_out.risks,
                stop_conditions=plan_out.stop_conditions, planner=plan_out.planner,
                status="draft" if task.requires_approval else "approved",
                approved_by=None if task.requires_approval else "auto (non-sensitive)")
    db.add(plan)
    db.commit()
    return plan


def start_run(task_id: str, plan_id: str | None = None, trigger="manual", options: dict | None = None):
    with SessionLocal() as db:
        task = db.get(Task, task_id)
        if not task:
            raise HTTPException(404, "Task not found")
        running = db.query(Run).filter(Run.task_id == task_id, Run.state.notin_(list(TERMINAL) + ["awaiting_approval"])).first()
        if running:
            raise HTTPException(409, f"Run {running.id} is already in progress for this task")
        plan = db.get(Plan, plan_id) if plan_id else (
            db.query(Plan).filter(Plan.task_id == task_id).order_by(Plan.created_at.desc()).first())
        if not plan or plan.status == "rejected":
            plan = _new_plan(db, task)
        opts = {"headed": settings.default_headed, "speed": settings.default_speed, "step_mode": False}
        opts.update({k: v for k, v in (options or {}).items() if v is not None})
        run = Run(task_id=task_id, plan_id=plan.id, trigger=trigger, state="task_intake", options=opts)
        db.add(run)
        db.commit()
        db.add(RunEvent(run_id=run.id, kind="state", message="State -> task_intake"))
        db.add(RunEvent(run_id=run.id, kind="state", message=f"State -> plan_generated ({plan.planner} planner, {plan.status})"))
        run.state = "plan_generated"
        db.commit()
        rid = run.id
    submit(rid)
    return rid


# ------------------------------------------------------------------ lifecycle
def startup():
    os.makedirs(settings.snapshot_dir, exist_ok=True)
    init_db()
    seed()
    start_scheduler(lambda tid, trigger: _safe_start(tid, trigger))


def _safe_start(tid, trigger):
    try:
        start_run(tid, trigger=trigger)
    except HTTPException:
        pass


def seed():
    path = os.path.join(ROOT, "data", "sample_task_templates.json")
    with open(path, encoding="utf-8") as f:
        templates = json.load(f)
    with SessionLocal() as db:
        have = {n for (n,) in db.query(Task.name).all()}
        for t in templates:
            if t["name"] in have:
                continue
            t = dict(t)
            t["target_urls"] = [u.replace("{BASE}", settings.public_base_url) for u in t["target_urls"]]
            db.add(Task(**t, next_run_at=compute_next(t["schedule"])))
        db.commit()


# ------------------------------------------------------------------ tasks & templates
@app.get("/api/health")
def health():
    import sys
    try:
        import playwright  # noqa: F401
        pw = True
    except ImportError:
        pw = False
    return {"ok": True, "llm": llm.available(), "browser_engine": settings.browser_engine, "playwright": pw,
            "platform": sys.platform, "default_headed": settings.default_headed, "default_speed": settings.default_speed,
            "allowlist": settings.domain_allowlist, "states": STATES, "active_runs": len(active_runs())}


@app.get("/api/templates")
def templates():
    return [{"name": s.name, "fields": list(s.fields), "compare_fields": s.compare_fields,
             "entity_fields": s.entity_fields} for s in SCHEMAS.values()]


@app.get("/api/workflows")
def workflows():
    out = []
    for w in catalog():
        sch = SCHEMAS.get(w.get("schema") or "")
        out.append({**w, "default_urls": [u.replace("{BASE}", settings.public_base_url) for u in w.get("default_urls", [])],
                    "fields": list(sch.fields) if sch else []})
    return out


@app.get("/api/tools")
def tools():
    return TOOLS


@app.post("/api/tasks", status_code=201)
def create_task(body: TaskIn, role: str = Depends(current_role)):
    require(role, "task:write")
    validate_task(body)
    with SessionLocal() as db:
        t = Task(**body.model_dump(), created_by=role, next_run_at=compute_next(body.schedule))
        if not t.expected_fields:
            sch = SCHEMAS.get(WORKFLOWS[body.template].get("schema") or "")
            t.expected_fields = list(sch.fields) if sch else []
        db.add(t)
        db.commit()
        return ser(t, *TASK_F)


@app.get("/api/tasks")
def list_tasks():
    with SessionLocal() as db:
        out = []
        for t in db.query(Task).order_by(Task.created_at).all():
            d = ser(t, *TASK_F)
            last = db.query(Run).filter(Run.task_id == t.id).order_by(Run.created_at.desc()).first()
            d["last_run"] = ser(last, *RUN_F) if last else None
            d["run_count"] = db.query(Run).filter(Run.task_id == t.id).count()
            out.append(d)
        return out


@app.patch("/api/tasks/{task_id}")
def update_task(task_id: str, body: dict, role: str = Depends(current_role)):
    require(role, "task:write")
    with SessionLocal() as db:
        t = db.get(Task, task_id)
        if not t:
            raise HTTPException(404, "Task not found")
        for k in ("schedule", "active", "requires_approval", "owner_team", "objective", "inputs"):
            if k in body:
                setattr(t, k, body[k])
        if "schedule" in body:
            t.next_run_at = compute_next(t.schedule)
        db.commit()
        return ser(t, *TASK_F)


# ------------------------------------------------------------------ plans
@app.post("/api/plans", status_code=201)
def create_plan(body: PlanIn, role: str = Depends(current_role)):
    require(role, "plan:write")
    with SessionLocal() as db:
        task = db.get(Task, body.task_id)
        if not task:
            raise HTTPException(404, "Task not found")
        return ser(_new_plan(db, task), *PLAN_F)


@app.get("/api/plans/{plan_id}")
def get_plan(plan_id: str):
    with SessionLocal() as db:
        p = db.get(Plan, plan_id)
        if not p:
            raise HTTPException(404, "Plan not found")
        return ser(p, *PLAN_F)


@app.post("/api/plans/{plan_id}/approve")
def approve_plan(plan_id: str, body: ApproveIn, role: str = Depends(current_role)):
    require(role, "plan:approve")
    with SessionLocal() as db:
        p = db.get(Plan, plan_id)
        if not p:
            raise HTTPException(404, "Plan not found")
        p.status = "approved" if body.approve else "rejected"
        p.approved_by = role
        waiting = db.query(Run).filter(Run.plan_id == plan_id, Run.state == "awaiting_approval").all()
        for r in waiting:
            if body.approve:
                r.state = "plan_generated"
            else:
                r.state, r.error, r.finished_at = "failed", "Plan rejected by reviewer", now()
            db.add(RunEvent(run_id=r.id, kind="policy", message=f"Plan {p.status} by {role}"))
        db.commit()
        ids = [r.id for r in waiting]
    if body.approve:
        for rid in ids:
            submit(rid)
    return {"plan_id": plan_id, "status": "approved" if body.approve else "rejected", "resumed_runs": ids}


# ------------------------------------------------------------------ runs
@app.post("/api/runs", status_code=202)
def create_run(body: RunIn, role: str = Depends(current_role)):
    require(role, "run:write")
    return {"run_id": start_run(body.task_id, body.plan_id, options=body.options.model_dump())}


@app.get("/api/runs")
def list_runs(task_id: str | None = None, limit: int = 50):
    with SessionLocal() as db:
        q = db.query(Run)
        if task_id:
            q = q.filter(Run.task_id == task_id)
        out = []
        for r in q.order_by(Run.created_at.desc()).limit(limit):
            d = ser(r, *RUN_F)
            d["task_name"] = r.task.name
            s = db.query(Summary).filter(Summary.run_id == r.id).first()
            d["headline"] = s.headline if s else None
            out.append(d)
        return out


@app.get("/api/runs/{run_id}")
def get_run(run_id: str, since_event: int = 0):
    with SessionLocal() as db:
        r = db.get(Run, run_id)
        if not r:
            raise HTTPException(404, "Run not found")
        d = ser(r, *RUN_F)
        d["task"] = ser(r.task, *TASK_F)
        d["plan"] = ser(db.get(Plan, r.plan_id), *PLAN_F) if r.plan_id else None
        d["events"] = [{"id": e.id, "kind": e.kind, "message": e.message, "data": e.data, "at": e.at.isoformat()}
                       for e in db.query(RunEvent).filter(RunEvent.run_id == run_id, RunEvent.id > since_event)
                       .order_by(RunEvent.id)]
        d["snapshots"] = [ser(s, "id", "url", "page_title", "http_status", "content_hash", "captured_at")
                          | {"has_screenshot": bool(s.screenshot_path)}
                          for s in db.query(Snapshot).filter(Snapshot.run_id == run_id)]
        d["records"] = [ser(x, "id", "entity_key", "entity", "fields", "snippet", "source_url", "confidence",
                            "validation_notes", "snapshot_id", "captured_at")
                        for x in db.query(ExtractedRecord).filter(ExtractedRecord.run_id == run_id)]
        d["comparisons"] = [ser(c, "id", "entity_key", "entity", "change_type", "classification", "field", "before",
                                "after", "delta_pct", "source_url", "confidence")
                            for c in db.query(Comparison).filter(Comparison.run_id == run_id)]
        s = db.query(Summary).filter(Summary.run_id == run_id).first()
        d["summary"] = ser(s, "id", "headline", "body", "generator", "alerts", "created_at") if s else None
        d["feedback"] = [ser(f, "id", "target_type", "target_id", "verdict", "correction", "note", "reviewer", "created_at")
                         for f in db.query(Feedback).filter(Feedback.run_id == run_id)]
        return d


@app.get("/api/runs/{run_id}/export.csv")
def export_csv(run_id: str):
    with SessionLocal() as db:
        s = db.query(Summary).filter(Summary.run_id == run_id).first()
        if not s or not s.export_path or not os.path.exists(s.export_path):
            raise HTTPException(404, "No export for this run yet")
        return FileResponse(s.export_path, media_type="text/csv", filename=f"{run_id}.csv")


@app.get("/api/snapshots/{snapshot_id}/html", response_class=PlainTextResponse)
def snapshot_html(snapshot_id: str):
    with SessionLocal() as db:
        s = db.get(Snapshot, snapshot_id)
        if not s:
            raise HTTPException(404, "Snapshot not found")
        with open(s.html_path, encoding="utf-8") as f:
            return f.read()


@app.get("/api/snapshots/{snapshot_id}/screenshot")
def snapshot_shot(snapshot_id: str):
    with SessionLocal() as db:
        s = db.get(Snapshot, snapshot_id)
        if not s or not s.screenshot_path:
            raise HTTPException(404, "No screenshot (HTTP engine does not capture screenshots)")
        return FileResponse(s.screenshot_path, media_type="image/png")


# ------------------------------------------------------------------ standalone pipeline stages
@app.post("/api/extract")
def extract(body: ExtractIn):
    schema = get_schema(body.schema_name)
    html = body.html
    if body.snapshot_id:
        with SessionLocal() as db:
            s = db.get(Snapshot, body.snapshot_id)
            if not s:
                raise HTTPException(404, "Snapshot not found")
            html = open(s.html_path, encoding="utf-8").read()
    if not html:
        raise HTTPException(422, "Provide html or snapshot_id")
    recs, warnings = parse(html, body.url, schema)
    return {"records": [r.model_dump() for r in validate(recs, schema.name)], "warnings": warnings}


def _compare_fields(task):
    sch = SCHEMAS.get(WORKFLOWS.get(task.template, {}).get("schema") or "")
    return sch.compare_fields if sch else []


def _records(db, run_id):
    return [{"entity_key": r.entity_key, "entity": r.entity, "fields": r.fields, "source_url": r.source_url,
             "confidence": r.confidence} for r in db.query(ExtractedRecord).filter(ExtractedRecord.run_id == run_id)]


@app.post("/api/compare")
def compare(body: CompareIn):
    with SessionLocal() as db:
        run = db.get(Run, body.run_id)
        if not run:
            raise HTTPException(404, "Run not found")
        other = body.against_run_id or getattr(db.query(Run).filter(
            Run.task_id == run.task_id, Run.created_at < run.created_at,
            Run.state.in_(["completed", "pending_review"])).order_by(Run.created_at.desc()).first(), "id", None)
        if not other:
            return {"against": None, "changes": [], "note": "No prior run to compare against"}
        changes = compare_records(_records(db, run.id), _records(db, other),
                                  _compare_fields(run.task), run.task.template)
        return {"against": other, "changes": [c.__dict__ for c in changes]}


@app.post("/api/complete")
def complete(body: CompleteIn, role: str = Depends(current_role)):
    """Regenerate the completion output (summary, alerts, export) for a finished run."""
    require(role, "run:write")
    res = compare(CompareIn(run_id=body.run_id))
    from agents.reasoning_loop.reasoner import Change
    with SessionLocal() as db:
        run = db.get(Run, body.run_id)
        changes = [Change(**c) for c in res["changes"]]
        decision = Decision(changes=changes, is_baseline=res["against"] is None, needs_review=run.needs_review)
        out = complete_run(run, run.task, changes, decision, _records(db, run.id))
        s = db.query(Summary).filter(Summary.run_id == run.id).first() or Summary(run_id=run.id)
        s.headline, s.body, s.generator, s.alerts, s.export_path = (out["headline"], out["body"], out["generator"],
                                                                    out["alerts"], out["export_path"])
        db.add(s)
        db.commit()
        return {"headline": s.headline, "body": s.body, "alerts": s.alerts}


# ------------------------------------------------------------------ live view & controls
@app.get("/api/runs/{run_id}/live")
def live(run_id: str, since: int = 0):
    st = hub.state(run_id, since)
    with SessionLocal() as db:
        r = db.get(Run, run_id)
        if not r:
            raise HTTPException(404, "Run not found")
        base = {"run_id": run_id, "state": r.state, "outcome": r.outcome or {}}
    if not st:
        return {**base, "seq": 0, "frames": [], "steps": [], "caption": None, "url": None, "control": None, "live": False}
    return {**base, **st}


@app.get("/api/runs/{run_id}/frames/{seq}.jpg")
def frame(run_id: str, seq: int):
    path = hub.frame_path(run_id, seq)
    if not os.path.exists(path):
        raise HTTPException(404, "Frame not found")
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "max-age=86400"})


@app.post("/api/runs/{run_id}/control")
def control(run_id: str, body: ControlIn, role: str = Depends(current_role)):
    require(role, "run:write")
    ctl = hub.control(run_id)
    if not ctl:
        raise HTTPException(409, "This run is not running in a browser right now")
    try:
        ctl.command(body.action)
    except ValueError as e:
        raise HTTPException(422, str(e))
    with SessionLocal() as db:
        db.add(RunEvent(run_id=run_id, kind="control", message=f"{body.action.title()} requested by {role}"))
        db.commit()
    return {"run_id": run_id, **ctl.snapshot()}


@app.post("/api/runs/{run_id}/input")
def respond(run_id: str, body: InputIn, role: str = Depends(current_role)):
    require(role, "plan:approve")
    ctl = hub.control(run_id)
    if not ctl:
        raise HTTPException(409, "This run is not running in a browser right now")
    try:
        ctl.respond(body.approve, body.note)
    except ValueError as e:
        raise HTTPException(409, str(e))
    with SessionLocal() as db:
        db.add(RunEvent(run_id=run_id, kind="review", message=f"{'Approved' if body.approve else 'Declined'} by {role}" +
                        (f": {body.note}" if body.note else "")))
        db.commit()
    return {"run_id": run_id, "approved": body.approve}


@app.get("/api/live")
def live_wall():
    with SessionLocal() as db:
        since = datetime.now(timezone.utc) - timedelta(minutes=10)
        runs = db.query(Run).filter((Run.state.notin_(list(TERMINAL))) | (Run.finished_at >= since)).order_by(Run.created_at.desc()).limit(24).all()
        out = []
        for r in runs:
            st = hub.state(r.id, since=10**9) or {}
            cap = st.get("caption")
            if r.state in ("task_intake", "plan_generated"):
                cap = f"Queued: waiting for a free browser slot ({settings.max_concurrent_runs} run at once)"
            elif r.state == "awaiting_approval":
                cap = "Waiting for plan approval"
            out.append({"run_id": r.id, "task_name": r.task.name, "template": r.task.template, "state": r.state,
                        "seq": st.get("seq", 0), "caption": cap, "url": st.get("url"),
                        "control": st.get("control"), "options": r.options or {}, "outcome": r.outcome or {},
                        "created_at": r.created_at.isoformat()})
        out.sort(key=lambda x: (x["state"] in TERMINAL, x["state"] in ("task_intake", "plan_generated")))
        return out


# ------------------------------------------------------------------ feedback
@app.post("/api/feedback", status_code=201)
def feedback(body: FeedbackIn, role: str = Depends(current_role)):
    require(role, "feedback:write")
    if body.verdict not in ("accepted", "rejected", "corrected"):
        raise HTTPException(422, "verdict must be accepted, rejected or corrected")
    with SessionLocal() as db:
        run = db.get(Run, body.run_id)
        if not run:
            raise HTTPException(404, "Run not found")
        fb = Feedback(**body.model_dump(), reviewer=role)
        db.add(fb)
        db.add(RunEvent(run_id=run.id, kind="review", message=f"Reviewer {body.verdict} {body.target_type} {body.target_id}"))
        if body.target_type == "summary" and body.verdict == "accepted" and run.state == "pending_review":
            run.state = "completed"
            db.add(RunEvent(run_id=run.id, kind="state", message="State -> completed (review signed off)"))
        db.commit()
        return ser(fb, "id", "run_id", "target_type", "target_id", "verdict", "note", "reviewer", "created_at")


# ------------------------------------------------------------------ dashboard metrics
@app.get("/api/metrics")
def metrics():
    with SessionLocal() as db:
        runs = db.query(Run).all()
        done = [r for r in runs if r.state in TERMINAL]
        ok = [r for r in done if r.state in ("completed", "pending_review")]
        recs = db.query(ExtractedRecord).all()
        fb = db.query(Feedback).filter(Feedback.target_type == "record").all()
        accepted = sum(1 for f in fb if f.verdict == "accepted")
        failures = {}
        for e in db.query(RunEvent).filter(RunEvent.kind == "error").all():
            cat = (e.data or {}).get("category", "other")
            failures[cat] = failures.get(cat, 0) + 1
        sources = {}
        for s in db.query(Snapshot).all():
            sources.setdefault(s.url, {"url": s.url, "captures": 0})["captures"] += 1
        for e in db.query(RunEvent).filter(RunEvent.kind == "error").all():
            u = (e.data or {}).get("url")
            if u:
                sources.setdefault(u, {"url": u, "captures": 0}).setdefault("failures", 0)
                sources[u]["failures"] = sources[u].get("failures", 0) + 1
        for e in db.query(RunEvent).filter(RunEvent.kind == "warning", RunEvent.message.like("Extraction: layout%")).all():
            u = (e.data or {}).get("url")
            if u:
                sources.setdefault(u, {"url": u, "captures": 0})
                sources[u]["layout_warnings"] = sources[u].get("layout_warnings", 0) + 1
        mats = db.query(Comparison).filter(Comparison.classification == "material").count()
        return {
            "runs_total": len(runs), "runs_finished": len(done),
            "completion_rate": round(len(ok) / len(done), 3) if done else None,
            "pending_review": sum(1 for r in runs if r.state == "pending_review"),
            "failed": sum(1 for r in runs if r.state == "failed"),
            "retries": sum(r.retries or 0 for r in runs),
            "avg_confidence": round(sum(r.confidence for r in recs) / len(recs), 3) if recs else None,
            "low_confidence_records": sum(1 for r in recs if r.confidence < settings.min_confidence),
            "reviewer_acceptance": round(accepted / len(fb), 3) if fb else None,
            "material_changes": mats,
            "cost_usd": round(sum(r.cost_usd or 0 for r in runs), 4),
            "failure_reasons": failures,
            "source_health": sorted(sources.values(), key=lambda s: -(s.get("failures", 0) + s.get("layout_warnings", 0))),
            "runs_by_day": _by_day(runs),
        }


def _by_day(runs):
    out = {}
    for r in runs:
        k = r.created_at.date().isoformat()
        o = out.setdefault(k, {"day": k, "completed": 0, "pending_review": 0, "failed": 0})
        if r.state in o:
            o[r.state] += 1
    return sorted(out.values(), key=lambda x: x["day"])


# ------------------------------------------------------------------ frontend
@app.get("/", response_class=HTMLResponse)
def index():
    with open(os.path.join(ROOT, "frontend", "index.html"), encoding="utf-8") as f:
        return f.read()
