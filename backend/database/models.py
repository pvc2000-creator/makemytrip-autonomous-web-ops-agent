"""Operational data model (matches section 6.3 'Data Assets Required')."""
from datetime import datetime, timezone
import uuid

from sqlalchemy import (JSON, Boolean, Column, DateTime, Float, ForeignKey, Integer,
                        String, Text, create_engine)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

from backend.config import settings

Base = declarative_base()


def now():
    return datetime.now(timezone.utc)


def uid(prefix: str):
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


class Task(Base):
    __tablename__ = "tasks"
    id = Column(String, primary_key=True, default=lambda: uid("task"))
    name = Column(String, nullable=False)
    template = Column(String, nullable=False)        # competitor_offers | hotel_pricing | campaign_page | partner_updates | travel_trends
    objective = Column(Text, nullable=False)
    target_urls = Column(JSON, default=list)
    expected_fields = Column(JSON, default=list)
    schedule = Column(String, default="once")        # once | hourly | daily | weekly | campaign
    completion_rules = Column(JSON, default=dict)
    owner_team = Column(String, default="Growth")
    inputs = Column(JSON, default=dict)              # workflow inputs (origin, destination, city, custom steps ...)
    requires_approval = Column(Boolean, default=False)
    active = Column(Boolean, default=True)
    next_run_at = Column(DateTime(timezone=True), nullable=True)
    created_by = Column(String, default="creator")
    created_at = Column(DateTime(timezone=True), default=now)
    runs = relationship("Run", back_populates="task", order_by="Run.created_at.desc()")


class Plan(Base):
    __tablename__ = "plans"
    id = Column(String, primary_key=True, default=lambda: uid("plan"))
    task_id = Column(String, ForeignKey("tasks.id"))
    steps = Column(JSON, default=list)
    tools = Column(JSON, default=list)
    extraction_schema = Column(String)
    risks = Column(JSON, default=list)
    stop_conditions = Column(JSON, default=list)
    planner = Column(String, default="template")     # template | llm
    status = Column(String, default="draft")         # draft | approved | rejected
    approved_by = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=now)


class Run(Base):
    __tablename__ = "runs"
    id = Column(String, primary_key=True, default=lambda: uid("run"))
    task_id = Column(String, ForeignKey("tasks.id"))
    plan_id = Column(String, ForeignKey("plans.id"), nullable=True)
    state = Column(String, default="task_intake")
    trigger = Column(String, default="manual")
    trace_id = Column(String, default=lambda: uuid.uuid4().hex)
    pages_visited = Column(Integer, default=0)
    retries = Column(Integer, default=0)
    cost_usd = Column(Float, default=0.0)
    error = Column(Text, nullable=True)
    needs_review = Column(Boolean, default=False)
    options = Column(JSON, default=dict)             # headed, speed, step_mode
    outcome = Column(JSON, default=dict)             # captured variables: booking_ref, total, chosen option ...
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=now)
    task = relationship("Task", back_populates="runs")
    events = relationship("RunEvent", order_by="RunEvent.id")


class RunEvent(Base):
    """Append-only audit log: every browser action, tool call, warning and state change."""
    __tablename__ = "run_events"
    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(String, ForeignKey("runs.id"), index=True)
    kind = Column(String)       # state | browser | tool | extract | warning | error | model | policy
    message = Column(Text)
    data = Column(JSON, default=dict)
    at = Column(DateTime(timezone=True), default=now)


class Snapshot(Base):
    __tablename__ = "snapshots"
    id = Column(String, primary_key=True, default=lambda: uid("snap"))
    run_id = Column(String, ForeignKey("runs.id"), index=True)
    task_id = Column(String, index=True)
    url = Column(String)
    page_title = Column(String)
    http_status = Column(Integer)
    html_path = Column(String)
    screenshot_path = Column(String, nullable=True)
    content_hash = Column(String)
    captured_at = Column(DateTime(timezone=True), default=now)


class ExtractedRecord(Base):
    __tablename__ = "extracted_records"
    id = Column(String, primary_key=True, default=lambda: uid("rec"))
    run_id = Column(String, ForeignKey("runs.id"), index=True)
    task_id = Column(String, index=True)
    snapshot_id = Column(String)
    entity_key = Column(String, index=True)   # stable identity across runs
    entity = Column(String)
    fields = Column(JSON, default=dict)
    snippet = Column(Text)
    source_url = Column(String)
    confidence = Column(Float)
    validation_notes = Column(JSON, default=list)
    captured_at = Column(DateTime(timezone=True), default=now)


class Comparison(Base):
    __tablename__ = "comparisons"
    id = Column(String, primary_key=True, default=lambda: uid("cmp"))
    run_id = Column(String, ForeignKey("runs.id"), index=True)
    entity_key = Column(String)
    entity = Column(String)
    change_type = Column(String)     # new | removed | price_up | price_down | copy_changed | availability | formatting | noise | missing_data
    classification = Column(String)  # material | noise | formatting | missing_data
    field = Column(String, nullable=True)
    before = Column(JSON, nullable=True)
    after = Column(JSON, nullable=True)
    delta_pct = Column(Float, nullable=True)
    source_url = Column(String)
    confidence = Column(Float)


class Summary(Base):
    __tablename__ = "summaries"
    id = Column(String, primary_key=True, default=lambda: uid("sum"))
    run_id = Column(String, ForeignKey("runs.id"), unique=True)
    headline = Column(Text)
    body = Column(JSON, default=dict)   # what_changed, why_it_matters, evidence, owner, confidence, actions
    generator = Column(String)          # template | llm
    alerts = Column(JSON, default=list)
    export_path = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=now)


class Feedback(Base):
    __tablename__ = "feedback"
    id = Column(String, primary_key=True, default=lambda: uid("fb"))
    run_id = Column(String, ForeignKey("runs.id"))
    target_type = Column(String)   # record | comparison | summary
    target_id = Column(String)
    verdict = Column(String)       # accepted | rejected | corrected
    correction = Column(JSON, nullable=True)
    note = Column(Text, nullable=True)
    reviewer = Column(String)
    created_at = Column(DateTime(timezone=True), default=now)


_sqlite = settings.database_url.startswith("sqlite")
_connect = {"check_same_thread": False, "timeout": 30} if _sqlite else {}
engine = create_engine(settings.database_url, connect_args=_connect, pool_pre_ping=True)

if _sqlite:
    from sqlalchemy import event

    @event.listens_for(engine, "connect")
    def _wal(conn, _):
        cur = conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA busy_timeout=30000")
        cur.close()
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def init_db():
    Base.metadata.create_all(engine)
    _add_missing_columns()


def _add_missing_columns():
    """Tiny forward-only migration: add columns introduced after a database was first created."""
    from sqlalchemy import inspect, text
    insp = inspect(engine)
    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            if not insp.has_table(table.name):
                continue
            existing = {c["name"] for c in insp.get_columns(table.name)}
            for col in table.columns:
                if col.name not in existing:
                    ddl = col.type.compile(dialect=engine.dialect)
                    conn.execute(text(f'ALTER TABLE {table.name} ADD COLUMN {col.name} {ddl}'))
