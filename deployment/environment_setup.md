# Environment setup

| Variable | Purpose | Default |
|---|---|---|
| DATABASE_URL | SQLAlchemy URL. SQLite for local, Postgres/Supabase for deployment | sqlite:///./webops.db |
| PUBLIC_BASE_URL | Public URL of the API; used to seed demo source URLs | http://127.0.0.1:8000 |
| SNAPSHOT_DIR | HTML snapshots, screenshots, CSV exports | ./data/runtime_snapshots |
| ANTHROPIC_API_KEY | Enables LLM planner refinement and summary writing (server-side only) | empty |
| ANTHROPIC_MODEL | Model id | claude-sonnet-4-6 |
| BROWSER_ENGINE | auto, playwright, http | auto |
| BROWSER_TIMEOUT_S / BROWSER_MAX_RETRIES | Navigation timeout and retry budget | 20 / 2 |
| DOMAIN_ALLOWLIST | Comma-separated hostnames the worker may visit (subdomains included) | localhost,127.0.0.1,... |
| RATE_LIMIT_PER_DOMAIN_PER_MIN | Per-host request cap across all runs | 120 |
| MAX_PAGES_PER_RUN | Hard page cap per run | 25 |
| MIN_EXTRACTION_CONFIDENCE | Below this, records route the run to review | 0.7 |
| PRICE_CHANGE_THRESHOLD_PCT | Price moves below this are noise | 3 |
| SCHEDULER_ENABLED | Runs recurring workflows in-process | true |
| API_TOKENS | token:role pairs for bearer auth | demo tokens |

Deployed on a public host, add that host to `DOMAIN_ALLOWLIST` and set `PUBLIC_BASE_URL` to it,
otherwise the policy engine (correctly) refuses to browse the bundled sources.
