"""Central configuration. Every secret and policy knob comes from the environment."""
import os
from dataclasses import dataclass, field

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load_dotenv(path=os.path.join(ROOT, ".env")):
    """Minimal .env loader (no extra dependency). Real environment variables win."""
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8-sig") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            val = val.split(" #", 1)[0].strip().strip('"').strip("'")
            os.environ.setdefault(key.strip(), val)


_load_dotenv()


def _list(name: str, default: str) -> list[str]:
    return [x.strip().lower() for x in os.getenv(name, default).split(",") if x.strip()]


@dataclass(frozen=True)
class Settings:
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./webops.db")
    anthropic_api_key: str | None = os.getenv("ANTHROPIC_API_KEY") or None
    anthropic_model: str = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")
    # Browser engine: "playwright" (real headless Chromium) or "http" (httpx fetch, no JS)
    browser_engine: str = os.getenv("BROWSER_ENGINE", "auto")
    browser_timeout_s: float = float(os.getenv("BROWSER_TIMEOUT_S", "20"))
    max_retries: int = int(os.getenv("BROWSER_MAX_RETRIES", "2"))
    max_concurrent_runs: int = int(os.getenv("MAX_CONCURRENT_RUNS", "3"))
    default_headed: bool = os.getenv("BROWSER_HEADED", "false").lower() == "true"
    default_speed: str = os.getenv("BROWSER_SPEED", "normal")
    # Governance
    domain_allowlist: list[str] = field(default_factory=lambda: _list(
        "DOMAIN_ALLOWLIST", "localhost,127.0.0.1,books.toscrape.com,quotes.toscrape.com"))
    rate_limit_per_domain_per_min: int = int(os.getenv("RATE_LIMIT_PER_DOMAIN_PER_MIN", "120"))
    max_pages_per_run: int = int(os.getenv("MAX_PAGES_PER_RUN", "25"))
    run_budget_usd: float = float(os.getenv("RUN_BUDGET_USD", "0.50"))
    # Change detection
    price_change_threshold_pct: float = float(os.getenv("PRICE_CHANGE_THRESHOLD_PCT", "3"))
    min_confidence: float = float(os.getenv("MIN_EXTRACTION_CONFIDENCE", "0.7"))
    # Self-reference so the worker can browse the bundled demo sources
    public_base_url: str = os.getenv("PUBLIC_BASE_URL", "http://127.0.0.1:8000")
    scheduler_enabled: bool = os.getenv("SCHEDULER_ENABLED", "true").lower() == "true"
    snapshot_dir: str = os.getenv("SNAPSHOT_DIR", "./data/runtime_snapshots")
    # Demo auth: API tokens mapped to roles (use SSO/JWT in production)
    api_tokens: str = os.getenv(
        "API_TOKENS", "creator-token:creator,reviewer-token:reviewer,admin-token:admin,worker-token:service")

    def __post_init__(self):
        # The bundled demo sources live on this service's own host; always allow it.
        from urllib.parse import urlparse
        host = (urlparse(self.public_base_url).hostname or "").lower()
        if host and host not in self.domain_allowlist:
            object.__setattr__(self, "domain_allowlist", self.domain_allowlist + [host])


settings = Settings()
