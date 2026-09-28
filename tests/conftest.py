"""Spins up the real API on a free port (HTTP browser engine) so tests exercise the full pipeline."""
import os
import socket
import sys
import tempfile
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

_s = socket.socket(); _s.bind(("127.0.0.1", 0)); PORT = _s.getsockname()[1]; _s.close()
_tmp = tempfile.mkdtemp()
os.environ.update({
    "DATABASE_URL": f"sqlite:///{_tmp}/test.db", "SNAPSHOT_DIR": f"{_tmp}/snaps",
    "PUBLIC_BASE_URL": f"http://127.0.0.1:{PORT}", "BROWSER_ENGINE": "http",
    "SCHEDULER_ENABLED": "false", "BROWSER_MAX_RETRIES": "1", "ANTHROPIC_API_KEY": "", "RATE_LIMIT_PER_DOMAIN_PER_MIN": "1000",
})

import httpx  # noqa: E402
import pytest  # noqa: E402
import uvicorn  # noqa: E402


@pytest.fixture(scope="session")
def api():
    from backend.api.main import app
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=PORT, log_level="warning"))
    threading.Thread(target=server.run, daemon=True).start()
    base = f"http://127.0.0.1:{PORT}"
    for _ in range(50):
        try:
            httpx.get(base + "/api/health"); break
        except httpx.HTTPError:
            time.sleep(0.1)
    with httpx.Client(base_url=base, timeout=30) as c:
        yield c
    server.should_exit = True


def wait_run(c, run_id, timeout=30):
    end = time.time() + timeout
    while time.time() < end:
        r = c.get(f"/api/runs/{run_id}").json()
        if r["state"] in ("completed", "pending_review", "failed", "awaiting_approval"):
            return r
        time.sleep(0.2)
    raise AssertionError(f"run {run_id} stuck in {r['state']}")
