"""Planner agent: turns a task into a structured, reviewable browser plan.

The step list comes from the workflow library (agents/planner/workflows.py), so plans are
reproducible. With an LLM configured, the planner may add risks and reorder monitoring sources,
restricted to the whitelisted tools and the task's own URLs; anything else is discarded.
"""
from pydantic import BaseModel, ValidationError

from agents.planner.workflows import TOOLS, WORKFLOWS, build_steps
from backend.auth.policy import policy
from backend.services import llm


class PlanStep(BaseModel):
    order: int
    tool: str
    target: str | None = None
    args: dict = {}
    purpose: str


class PlanOut(BaseModel):
    steps: list[PlanStep]
    tools: list[str]
    extraction_schema: str | None
    risks: list[str]
    stop_conditions: list[str]
    planner: str


def _template(task) -> PlanOut:
    raw, schema = build_steps(task)
    wf = WORKFLOWS[task.template]
    risks = []
    for s in raw:
        if s["tool"] == "navigate" and s.get("target") and "{{" not in s["target"] and not policy.is_allowed(s["target"]):
            risks.append(f"{s['target']} is outside the domain allowlist and will be blocked")
    tools = {s["tool"] for s in raw}
    if wf["kind"] == "transaction":
        risks.append("This workflow performs an irreversible action; it pauses for human approval before confirming")
        risks.append("The agent will not type into payment, OTP or password fields")
    if tools & {"click", "fill", "select", "check", "uncheck", "pick_best"}:
        risks.append("Interactive steps need the Playwright browser; if a selector changes the step fails visibly")
    if task.template == "hotel_pricing":
        risks.append("Prices may differ by occupancy and date; comparison keyed on city + hotel + stay date")
    if task.template == "competitor_offers":
        risks.append("Promotional prices can be teasers; confirm before external action")
    if "extract" in tools or "paginate" in tools:
        risks.append("Layout changes are detected through fallback selectors and lower confidence")
    return PlanOut(
        steps=[PlanStep(**s) for s in raw], tools=sorted(tools), extraction_schema=schema, risks=risks,
        stop_conditions=[
            "Monitoring: a failed source is skipped and the rest continue; transactions stop at the first failure",
            "Stop if the page cap, rate limit or run budget is reached, or a page leaves the allowlist",
            "Pause for a person at every approval step; stop if not approved",
            "Route to review if any record falls below minimum confidence",
        ],
        planner="template")


def build_plan(task) -> tuple[PlanOut, float]:
    plan = _template(task)
    if WORKFLOWS[task.template]["kind"] != "monitor" or len(task.target_urls or []) < 2:
        return plan, 0.0
    result = llm.complete_json(
        system=("You are the planning agent of a governed web-operations platform for a travel company. "
                "You may only use these tools: " + ", ".join(TOOLS) + ". Never add URLs that are not in the task. "
                "Return {\"extra_risks\": [str], \"priority_order\": [url], \"notes\": str}."),
        user=f"Task objective: {task.objective}\nTemplate: {task.template}\nURLs: {task.target_urls}\nCurrent risks: {plan.risks}")
    if result is None:
        return plan, 0.0
    try:
        extra = [str(r)[:200] for r in result.data.get("extra_risks", [])][:5]
        order = [u for u in result.data.get("priority_order", []) if u in task.target_urls]
        if order and set(order) == set(task.target_urls):
            rank = {u: i for i, u in enumerate(order)}
            browse = sorted([s for s in plan.steps if s.target], key=lambda s: (rank.get(s.target, 99), s.order))
            tail = [s for s in plan.steps if not s.target]
            plan.steps = browse + tail
            for i, s in enumerate(plan.steps, 1):
                s.order = i
        plan.risks += extra
        plan.planner = "llm"
        PlanOut.model_validate(plan.model_dump())
    except (ValidationError, AttributeError, KeyError, TypeError):
        plan = _template(task)
    return plan, result.cost_usd
