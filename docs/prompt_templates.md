# Prompt templates

LLM calls are optional and always validated; on any failure the deterministic path is used.
Keys stay server-side (`backend/services/llm.py`). Every system prompt ends with:
"Respond with a single JSON object only. No prose, no code fences."

## Planner refinement (`agents/planner/planner.py`)

System:
> You are the planning agent of a governed web-operations platform for a travel company. You may
> only use these tools: navigate, dismiss_popups, wait_for, screenshot, capture_html, extract,
> compare, summarize, route. Never add URLs that are not in the task. Return
> {"extra_risks": [str], "priority_order": [url], "notes": str}.

User: task objective, template, URLs, expected fields, current risks.

Validation: at most 5 risks of 200 chars; `priority_order` accepted only if it is a permutation of
the task URLs; result re-validated against the plan schema.

## Summary writer (`agents/completion/completer.py`)

System:
> You write concise operations summaries for a travel company's growth team. Use only the facts
> given. Return {"headline": str (max 14 words), "why_it_matters": str (max 45 words)}.

User: workflow name, owner, list of material changes (already computed).

Validation: both fields must be strings; length capped. Evidence, numbers, owner and actions are never
taken from the model.

## Extraction

Extraction is schema-driven (CSS selectors + normalizers), not LLM-based, so results are reproducible
and testable. A model-assisted fallback for unknown layouts would return JSON matching
`extraction/schemas` `Record` and be capped at confidence 0.6 so it always routes to review.
