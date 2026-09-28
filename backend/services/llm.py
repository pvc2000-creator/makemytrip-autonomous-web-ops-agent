"""LLM access. Keys stay server-side. Every call is optional: with no ANTHROPIC_API_KEY the agents use
deterministic template logic, so the product works (and is testable) offline."""
import json
import re

import httpx

from backend.config import settings

# Rough per-token prices for cost indicators (USD per million tokens). Adjust to your contract.
PRICE_IN, PRICE_OUT = 3.0, 15.0


class LLMResult:
    def __init__(self, data, cost_usd, raw):
        self.data, self.cost_usd, self.raw = data, cost_usd, raw


def available() -> bool:
    return bool(settings.anthropic_api_key)


def complete_json(system: str, user: str, max_tokens: int = 1200) -> LLMResult | None:
    """Ask for JSON only; validate it parses. Returns None on any failure (caller falls back)."""
    if not available():
        return None
    try:
        resp = httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": settings.anthropic_api_key, "anthropic-version": "2023-06-01",
                     "content-type": "application/json"},
            json={"model": settings.anthropic_model, "max_tokens": max_tokens,
                  "system": system + "\nRespond with a single JSON object only. No prose, no code fences.",
                  "messages": [{"role": "user", "content": user}]},
            timeout=60)
        resp.raise_for_status()
        body = resp.json()
        text = "".join(b.get("text", "") for b in body.get("content", []))
        text = re.sub(r"^```(json)?|```$", "", text.strip()).strip()
        usage = body.get("usage", {})
        cost = usage.get("input_tokens", 0) / 1e6 * PRICE_IN + usage.get("output_tokens", 0) / 1e6 * PRICE_OUT
        return LLMResult(json.loads(text), round(cost, 5), text)
    except Exception:
        return None
