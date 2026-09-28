# Browser and source governance policy

1. **Allowlist only.** The worker visits only hosts in `DOMAIN_ALLOWLIST` (subdomains included) over
   http/https. Intake rejects other URLs; the worker re-checks before every navigation. The service's
   own host is added automatically so the bundled demo sources work.
2. **Approved access paths only.** No login automation, CAPTCHA solving, paywall or robots bypass.
   A 401/403 is recorded as `browser_blocked` and never retried.
3. **Rate limits.** At most `RATE_LIMIT_PER_DOMAIN_PER_MIN` requests per host across all runs, and
   `MAX_PAGES_PER_RUN` per run. Hitting either stops that source with `policy_restriction`.
3a. **Navigation guard.** Every main-frame navigation, including ones triggered by clicking links or
   submitting forms, is checked against the allowlist and aborted if it leaves it.
3b. **Sensitive fields.** The agent refuses to type into card, CVV, OTP, PIN or password fields.
3c. **Transactions.** Workflows that commit something (bookings) run on demand only, never on a schedule,
   and always include an approval step before the irreversible action. Declining stops the run there.
4. **Identification.** Requests carry a descriptive User-Agent with a contact address.
5. **Retries.** Only timeouts, 5xx and 429, at most `BROWSER_MAX_RETRIES`, with back-off.
6. **Credentials.** Model keys, partner credentials and tokens live only in backend environment
   variables. Nothing sensitive is sent to the browser UI. Session data is not persisted.
7. **Evidence.** Each capture stores URL, timestamp, title, status, content hash, HTML and (under
   Playwright) a screenshot. Every conclusion cites its source URL and confidence.
8. **Human confirmation.** Runs are held in `pending_review` on low confidence, layout drift, source
   failures or price moves ≥10%. Summaries state when human confirmation is needed before external action.
9. **Retention.** Keep snapshots long enough to compare consecutive runs (recommended 30 days for
   HTML and screenshots, 12 months for structured records), then prune.
10. **Adding a source.** Source owner requests it → compliance confirms terms of use and that no API
    exists → security adds the host to the allowlist → a workflow with `requires_approval=true` runs
    under review until stable.
