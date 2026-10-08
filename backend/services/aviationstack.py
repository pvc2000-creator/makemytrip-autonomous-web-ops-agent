"""Aviationstack client for the MakeMyTrip Web Ops Agent.

Real flight *status* data (not fares): route, schedule, delay, terminal/gate.

Designed for the free plan (about 100 requests per month):
  * every response is cached on disk, so repeated runs cost nothing;
  * a monthly request counter stops calls before the quota is gone;
  * the API key is read from the environment and never logged;
  * HTTPS is tried first; plain HTTP is used only if you opt in
    (AVIATIONSTACK_ALLOW_HTTP=true), because HTTP sends the key unencrypted.

Environment variables
  AVIATIONSTACK_API_KEY         required
  AVIATIONSTACK_MONTHLY_LIMIT   default 90 (keeps a safety margin under 100)
  AVIATIONSTACK_CACHE_TTL_MIN   default 60
  AVIATIONSTACK_CACHE_DIR       default <system temp>/aviationstack_cache
  AVIATIONSTACK_ALLOW_HTTP      default false

Quick test:  python -m backend.services.aviationstack DEL BOM
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

BASE_HOST = "api.aviationstack.com"
ENDPOINT = "/v1/flights"
SOURCE_NAME = "aviationstack"


class AviationstackError(Exception):
    """Any problem talking to Aviationstack (message never contains the key)."""


class MissingApiKey(AviationstackError):
    pass


class QuotaExceeded(AviationstackError):
    pass


def _cache_dir() -> Path:
    d = os.getenv("AVIATIONSTACK_CACHE_DIR") or str(Path(tempfile.gettempdir()) / "aviationstack_cache")
    p = Path(d)
    p.mkdir(parents=True, exist_ok=True)
    return p


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------- quota guard
def _quota_file() -> Path:
    return _cache_dir() / "quota.json"


def requests_used_this_month() -> int:
    month = _now().strftime("%Y-%m")
    try:
        data = json.loads(_quota_file().read_text())
        return int(data["count"]) if data.get("month") == month else 0
    except (OSError, ValueError, KeyError):
        return 0


def _bump_quota() -> None:
    month = _now().strftime("%Y-%m")
    _quota_file().write_text(json.dumps({"month": month, "count": requests_used_this_month() + 1}))


def _monthly_limit() -> int:
    try:
        return int(os.getenv("AVIATIONSTACK_MONTHLY_LIMIT", "90"))
    except ValueError:
        return 90


# ---------------------------------------------------------------- HTTP layer
def _http_get(url: str, timeout: int = 20) -> Dict[str, Any]:
    """GET a URL and return parsed JSON. Isolated so tests can replace it."""
    req = urllib.request.Request(url, headers={"User-Agent": "mmt-web-ops-agent/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (fixed https/http host)
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        # Aviationstack returns its error JSON with a 4xx status.
        try:
            return json.loads(e.read().decode("utf-8"))
        except Exception:  # noqa: BLE001
            raise AviationstackError(f"HTTP {e.code} from Aviationstack") from None
    except urllib.error.URLError as e:
        raise AviationstackError(f"Network error: {getattr(e, 'reason', 'unknown')}") from None
    except (TimeoutError, OSError):
        raise AviationstackError("Network error: timed out or connection failed") from None
    except ValueError:
        raise AviationstackError("Aviationstack returned a non-JSON response") from None


def _build_url(scheme: str, params: Dict[str, Any]) -> str:
    return f"{scheme}://{BASE_HOST}{ENDPOINT}?{urllib.parse.urlencode(params)}"


def _fetch(params: Dict[str, Any], api_key: str) -> Dict[str, Any]:
    full = dict(params, access_key=api_key)
    payload = _http_get(_build_url("https", full))
    err = payload.get("error") if isinstance(payload, dict) else None
    if err and str(err.get("code")) in {"105", "https_access_restricted"}:
        if os.getenv("AVIATIONSTACK_ALLOW_HTTP", "").lower() not in {"1", "true", "yes"}:
            raise AviationstackError(
                "Your Aviationstack plan refuses HTTPS. Set AVIATIONSTACK_ALLOW_HTTP=true to "
                "allow plain HTTP (the key is then sent unencrypted; use only for a demo key)."
            )
        payload = _http_get(_build_url("http", full))
        err = payload.get("error") if isinstance(payload, dict) else None
    if err:
        code = err.get("code", "unknown")
        msg = err.get("message") or err.get("type") or "error"
        # Never echo the key: the API message does not contain it, but scrub anyway.
        raise AviationstackError(f"Aviationstack error {code}: {str(msg).replace(api_key, '***')}")
    return payload


# ---------------------------------------------------------------- caching
def _cache_path(params: Dict[str, Any]) -> Path:
    key = hashlib.sha256(json.dumps(params, sort_keys=True).encode()).hexdigest()[:24]
    return _cache_dir() / f"flights_{key}.json"


def _cache_ttl_seconds() -> int:
    try:
        return int(float(os.getenv("AVIATIONSTACK_CACHE_TTL_MIN", "60")) * 60)
    except ValueError:
        return 3600


def _read_cache(params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    p = _cache_path(params)
    try:
        if time.time() - p.stat().st_mtime <= _cache_ttl_seconds():
            return json.loads(p.read_text())
    except (OSError, ValueError):
        pass
    return None


def _write_cache(params: Dict[str, Any], payload: Dict[str, Any]) -> None:
    try:
        _cache_path(params).write_text(json.dumps(payload))
    except OSError:
        pass  # cache is best-effort


# ---------------------------------------------------------------- normalisation
def _delay(v: Any) -> Optional[int]:
    try:
        return int(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def normalise(item: Dict[str, Any], fetched_at: str) -> Dict[str, Any]:
    dep = item.get("departure") or {}
    arr = item.get("arrival") or {}
    airline = item.get("airline") or {}
    flight = item.get("flight") or {}
    flight_iata = flight.get("iata") or flight.get("number") or ""
    flight_date = item.get("flight_date") or ""
    return {
        "entity_key": f"{flight_iata}|{flight_date}",
        "flight_iata": flight_iata,
        "airline": airline.get("name") or "",
        "flight_date": flight_date,
        "status": item.get("flight_status") or "unknown",
        "dep_airport": dep.get("airport") or "",
        "dep_iata": dep.get("iata") or "",
        "dep_scheduled": dep.get("scheduled"),
        "dep_estimated": dep.get("estimated"),
        "dep_delay_min": _delay(dep.get("delay")),
        "dep_terminal": dep.get("terminal"),
        "dep_gate": dep.get("gate"),
        "arr_airport": arr.get("airport") or "",
        "arr_iata": arr.get("iata") or "",
        "arr_scheduled": arr.get("scheduled"),
        "arr_estimated": arr.get("estimated"),
        "arr_delay_min": _delay(arr.get("delay")),
        "arr_terminal": arr.get("terminal"),
        "arr_gate": arr.get("gate"),
        "source": SOURCE_NAME,
        "fetched_at": fetched_at,
    }


# ---------------------------------------------------------------- public API
def get_flights(
    dep_iata: Optional[str] = None,
    arr_iata: Optional[str] = None,
    flight_iata: Optional[str] = None,
    flight_status: Optional[str] = None,
    limit: int = 10,
) -> List[Dict[str, Any]]:
    """Return normalised flight-status records.

    Raises MissingApiKey, QuotaExceeded or AviationstackError; the caller
    should catch these and fall back to the mock sources.
    """
    api_key = os.getenv("AVIATIONSTACK_API_KEY", "").strip()
    if not api_key:
        raise MissingApiKey("AVIATIONSTACK_API_KEY is not set")

    params: Dict[str, Any] = {"limit": max(1, min(int(limit), 100))}
    if dep_iata:
        params["dep_iata"] = dep_iata.upper()
    if arr_iata:
        params["arr_iata"] = arr_iata.upper()
    if flight_iata:
        params["flight_iata"] = flight_iata.upper()
    if flight_status:
        params["flight_status"] = flight_status.lower()

    payload = _read_cache(params)
    if payload is None:
        if requests_used_this_month() >= _monthly_limit():
            raise QuotaExceeded(
                f"Monthly Aviationstack budget of {_monthly_limit()} requests is used up; "
                "using cached or mock data instead."
            )
        payload = _fetch(params, api_key)
        _bump_quota()
        _write_cache(params, payload)

    fetched_at = _now().isoformat(timespec="seconds")
    return [normalise(i, fetched_at) for i in (payload.get("data") or [])]


def _load_dotenv_for_cli(path: str = ".env") -> None:
    """Minimal .env reader so the command-line test works without extra packages."""
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k, v = k.strip(), v.strip().strip('"').strip("'")
                if k.startswith("AVIATIONSTACK_") and v:
                    os.environ.setdefault(k, v)
    except OSError:
        pass


if __name__ == "__main__":  # python -m backend.services.aviationstack DEL BOM
    _load_dotenv_for_cli()
    origin = sys.argv[1] if len(sys.argv) > 1 else None
    dest = sys.argv[2] if len(sys.argv) > 2 else None
    try:
        rows = get_flights(dep_iata=origin, arr_iata=dest, limit=5)
    except AviationstackError as exc:
        print(f"[{type(exc).__name__}] {exc}")
        sys.exit(1)
    print(f"{len(rows)} flights  (requests used this month: {requests_used_this_month()})")
    for r in rows:
        print(f"{r['flight_iata']:8} {r['airline'][:18]:18} {r['dep_iata']}->{r['arr_iata']} "
              f"{r['status']:10} dep_delay={r['dep_delay_min']} gate={r['dep_gate']}")
