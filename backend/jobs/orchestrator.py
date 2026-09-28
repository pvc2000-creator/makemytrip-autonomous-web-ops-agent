"""Job orchestrator: one state machine per run.

task_intake -> plan_generated -> [awaiting_approval] -> browser_execution (<-> awaiting_input)
            -> extraction -> comparison -> reasoning (may re-browse empty sources once)
            -> completion -> completed | pending_review | failed | stopped
"""
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

from agents.browser_execution.runner import ActionRunner, BrowserError
from agents.completion.completer import complete
from agents.planner.workflows import WORKFLOWS
from agents.reasoning_loop.reasoner import reason
from backend.config import settings
from backend.database.models import (Comparison, ExtractedRecord, Plan, Run, RunEvent, SessionLocal,
                                     Snapshot, Summary, Task, now)
from backend.jobs.live import StopRequested, hub
from extraction.parsers import parse
from extraction.schemas import SCHEMAS, get_schema
from extraction.validators import validate

STATES = ["task_intake", "plan_generated", "awaiting_approval", "browser_execution", "awaiting_input", "extraction",
          "comparison", "reasoning", "completion", "completed", "pending_review", "failed", "stopped"]
TERMINAL = {"completed", "pending_review", "failed", "stopped"}
KEEP_VARS = ("chosen_hotel", "chosen_room", "chosen_hotel_price", "chosen_room_price", "guest_name", "city", "nights", "chosen_option", "chosen_price", "options_compared", "total", "total_value", "booking_ref",
             "approved", "records_extracted", "traveller_name", "origin", "destination", "date", "passengers")

_pool = ThreadPoolExecutor(max_workers=settings.max_concurrent_runs, thread_name_prefix="run")
_active: set[str] = set()
_lock = threading.Lock()


def log_event(run_id, kind, message, data=None):
    with SessionLocal() as db:
        db.add(RunEvent(run_id=run_id, kind=kind, message=message, data=data or {}))
        db.commit()


def set_state(run_id, state, **fields):
    with SessionLocal() as db:
        run = db.get(Run, run_id)
        run.state = state
        for k, v in fields.items():
            setattr(run, k, v)
        db.commit()
    log_event(run_id, "state", f"State -> {state}")


def records_of(db, run_id):
    return [{"entity_key": r.entity_key, "entity": r.entity, "fields": r.fields, "source_url": r.source_url,
             "confidence": r.confidence} for r in db.query(ExtractedRecord).filter(ExtractedRecord.run_id == run_id)]


def prior_records(db, task_id, exclude_run_id):
    prev = (db.query(Run).filter(Run.task_id == task_id, Run.id != exclude_run_id,
                                 Run.state.in_(["completed", "pending_review"]))
            .order_by(Run.created_at.desc()).first())
    if not prev:
        return [], None
    return records_of(db, prev.id), prev.id


def submit(run_id: str):
    with _lock:
        if run_id in _active:
            return
        _active.add(run_id)
    _pool.submit(_execute_safe, run_id)


def active_runs():
    with _lock:
        return set(_active)


def _execute_safe(run_id):
    try:
        execute(run_id)
    except StopRequested:
        log_event(run_id, "control", "Run stopped by user")
        set_state(run_id, "stopped", error="Stopped by user", finished_at=now())
    except BrowserError as e:
        log_event(run_id, "error", f"{e.category}: {e}", {"category": e.category})
        set_state(run_id, "failed", error=f"{e.category}: {e}", finished_at=now())
    except Exception as e:
        log_event(run_id, "error", f"Unhandled error: {e}", {"trace": traceback.format_exc()[-1500:]})
        set_state(run_id, "failed", error=str(e), finished_at=now())
    finally:
        hub.finish(run_id)
        with _lock:
            _active.discard(run_id)


def execute(run_id: str):
    with SessionLocal() as db:
        run = db.get(Run, run_id)
        task = db.get(Task, run.task_id)
        plan = db.get(Plan, run.plan_id)
        options = dict(run.options or {})
    if plan.status != "approved":
        set_state(run_id, "awaiting_approval")
        log_event(run_id, "policy", "Plan requires approval before the browser starts")
        return
    wf = WORKFLOWS.get(task.template, {"kind": "monitor"})
    options["kind"] = wf["kind"]
    schema_name = plan.extraction_schema
    schema = get_schema(schema_name) if schema_name in SCHEMAS else None
    hub.start(run_id, plan.steps, options)
    set_state(run_id, "browser_execution", started_at=now())
    log_event(run_id, "tool", f"Executing approved plan {plan.id} ({len(plan.steps)} steps, {wf['kind']} workflow)")

    page_warnings: dict[str, list[str]] = {}

    def store_capture(url, html, title, status, shot, use_schema):
        pending, n = [], 0
        with SessionLocal() as db:
            snap = Snapshot(run_id=run_id, task_id=task.id, url=url, page_title=title, http_status=status,
                            html_path=_save_html(run_id, html), screenshot_path=shot,
                            content_hash=__import__("hashlib").sha1(html.encode()).hexdigest())
            db.add(snap)
            db.flush()
            if use_schema and use_schema in SCHEMAS:
                sch = get_schema(use_schema)
                parsed, warnings = parse(html, url, sch)
                parsed = validate(parsed, sch.name)
                page_warnings.setdefault(url, []).extend(warnings)
                pending += [("warning", f"Extraction: {w}", {"url": url}) for w in warnings]
                existing = {r.entity_key for r in db.query(ExtractedRecord).filter(ExtractedRecord.run_id == run_id)}
                for r in parsed:
                    if r.entity_key in existing:
                        continue
                    db.add(ExtractedRecord(run_id=run_id, task_id=task.id, snapshot_id=snap.id, entity_key=r.entity_key,
                                           entity=r.entity, fields=r.fields, snippet=r.snippet, source_url=r.source_url,
                                           confidence=r.confidence, validation_notes=r.validation_notes))
                    n += 1
                pending.append(("extract", f"Extracted {n} record(s) from {url}",
                                {"url": url, "count": n, "low_confidence": sum(1 for r in parsed if r.confidence < settings.min_confidence)}))
            db.commit()
        for kind, msg, data in pending:
            log_event(run_id, kind, msg, data)
        return n

    post_idx = {s["tool"]: i for i, s in enumerate(plan.steps) if s["tool"] in ("compare", "summarize", "route")}

    with ActionRunner(run_id, task, plan.steps, schema_name, options, lambda k, m, d=None: log_event(run_id, k, m, d),
                      lambda st: set_state(run_id, st), store_capture) as runner:
        result = runner.run()
        with SessionLocal() as db:
            r = db.get(Run, run_id)
            r.pages_visited = runner.pages
            r.outcome = {k: v for k, v in result["vars"].items() if k in KEEP_VARS}
            if result["declined"] is not None:
                r.outcome["declined"] = result["declined"]
            db.commit()

        failures = result["failures"]
        if wf["kind"] == "transaction" and failures and result["declined"] is None:
            first = next(iter(failures.values()))
            set_state(run_id, "failed", error=f"Stopped at '{first['step']}': {first['category']}: {first['message']}", finished_at=now())
            return
        wants_data = any(s["tool"] in ("extract", "paginate") for s in plan.steps)
        if not result["captures"] and wf["kind"] == "monitor" and (failures or wants_data):
            set_state(run_id, "failed", error=("All sources failed: " + "; ".join(
                f"{u} ({f['category']}: {f['message']})" for u, f in failures.items())) if failures else "No pages were captured",
                finished_at=now())
            return

        set_state(run_id, "extraction")
        with SessionLocal() as db:
            current = records_of(db, run_id)
        log_event(run_id, "extract", f"{len(current)} record(s) extracted from {len(result['captures'])} page(s)")

        set_state(run_id, "comparison")
        hub.step_status(run_id, post_idx.get("compare", -1), "running")
        with SessionLocal() as db:
            prior, prior_run = prior_records(db, task.id, run_id)
        log_event(run_id, "tool", f"Comparing against {'run ' + prior_run if prior_run else 'no prior snapshot (baseline)'}")

        set_state(run_id, "reasoning")
        compare_fields = schema.compare_fields if schema else []
        decision = reason(current, prior, compare_fields, task.template, page_warnings, attempted_rerun=False)
        if decision.needs_rerun_urls and wf["kind"] == "monitor":
            log_event(run_id, "tool", f"Reasoning loop: {len(decision.needs_rerun_urls)} source(s) returned nothing "
                                      "but had data last run; re-browsing once", {"urls": decision.needs_rerun_urls})
            set_state(run_id, "browser_execution")
            runner.revisit(decision.needs_rerun_urls)
            with SessionLocal() as db:
                current = records_of(db, run_id)
            set_state(run_id, "reasoning")
            decision = reason(current, prior, compare_fields, task.template, page_warnings, attempted_rerun=True)
        elif decision.needs_rerun_urls:
            decision.needs_rerun_urls = []
    hub.step_status(run_id, post_idx.get("compare", -1), "done")

    if failures:
        decision.needs_review = True
        decision.review_reasons.append(f"{len(failures)} source(s) or step(s) failed: " +
                                       ", ".join(sorted({f['category'] for f in failures.values()})))
    for reason_text in decision.review_reasons:
        log_event(run_id, "warning", f"Review flag: {reason_text}")
    with SessionLocal() as db:
        for c in decision.changes:
            db.add(Comparison(run_id=run_id, entity_key=c.entity_key, entity=c.entity, change_type=c.change_type,
                              classification=c.classification, field=c.field, before=_jsonable(c.before),
                              after=_jsonable(c.after), delta_pct=c.delta_pct, source_url=c.source_url, confidence=c.confidence))
        db.commit()
    log_event(run_id, "tool", f"{len(decision.changes)} change(s): " + ", ".join(
        f"{k}={sum(1 for c in decision.changes if c.classification == k)}" for k in ("material", "noise", "formatting", "missing_data")))

    set_state(run_id, "completion")
    hub.step_status(run_id, post_idx.get("summarize", -1), "running")
    with SessionLocal() as db:
        run = db.get(Run, run_id)
        out = complete(run, task, decision.changes, decision, current, outcome=run.outcome or {}, kind=wf["kind"])
        db.add(Summary(run_id=run_id, headline=out["headline"], body=out["body"], generator=out["generator"],
                       alerts=out["alerts"], export_path=out["export_path"]))
        cost = out["cost_usd"] + (run.cost_usd or 0)
        db.commit()
    hub.step_status(run_id, post_idx.get("summarize", -1), "done")
    for a in out["alerts"]:
        log_event(run_id, "tool", f"Routed to {a['channel']} ({a['team']})", a)
    hub.step_status(run_id, post_idx.get("route", -1), "done")
    final = "pending_review" if decision.needs_review else "completed"
    hub.update(run_id, caption=out["headline"])
    set_state(run_id, final, needs_review=decision.needs_review, finished_at=now(), cost_usd=round(cost, 5))


def _save_html(run_id, html):
    import hashlib
    import os
    d = os.path.join(settings.snapshot_dir, run_id)
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, hashlib.sha1(html.encode()).hexdigest()[:12] + ".html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    return path


def _jsonable(v):
    if isinstance(v, (dict, list, str, int, float)) or v is None:
        return v
    return str(v)


# ----------------------------------------------------------------- scheduler
INTERVALS = {"hourly": 3600, "daily": 86400, "weekly": 604800, "campaign": 1800, "every_5_min": 300}


def compute_next(schedule: str, frm: datetime | None = None):
    secs = INTERVALS.get(schedule)
    return (frm or datetime.now(timezone.utc)) + timedelta(seconds=secs) if secs else None


def _scheduler_loop(start_run):
    while True:
        try:
            with SessionLocal() as db:
                due = db.query(Task).filter(Task.active.is_(True), Task.schedule != "once", Task.next_run_at.isnot(None)).all()
                for t in due:
                    if WORKFLOWS.get(t.template, {}).get("kind") == "transaction":
                        continue  # transactions never run unattended
                    nra = t.next_run_at if t.next_run_at.tzinfo else t.next_run_at.replace(tzinfo=timezone.utc)
                    if nra <= datetime.now(timezone.utc):
                        t.next_run_at = compute_next(t.schedule)
                        db.commit()
                        start_run(t.id, trigger="schedule")
        except Exception:
            traceback.print_exc()
        time.sleep(15)


def start_scheduler(start_run):
    if settings.scheduler_enabled:
        threading.Thread(target=_scheduler_loop, args=(start_run,), daemon=True, name="scheduler").start()
