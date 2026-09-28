# Demonstration flow (about 6 minutes)

**Setup.** Fresh database, `uvicorn backend.api.main:app`, open `/`. The sidebar shows the backend
connection and browser engine.

1. **Problem (30s).** Growth and ops teams check competitor offers, hotel rates, campaign pages and
   partner feeds by hand. Show *Workflows*: five seeded, scheduled workflows with owners.
2. **Plan (45s).** *Review plan* on Competitor offers: per-source browser steps, tools limited to a
   whitelist, flagged risks, stop conditions.
3. **Baseline (45s).** *Run all workflows*. Open a run while it moves along the route strip; show the
   activity log (engine, pop-up dismissed, records extracted). Hotel pricing halts at Approval.
4. **Governance (45s).** Switch *Acting as* to Task creator and try to approve: refused. Switch to
   Reviewer, approve from the *Review queue*; the run resumes.
5. **Market moves (30s).** *Move market forward a day* twice.
6. **Change detection (90s).** *Run all workflows*. Open Hotel pricing: Needs review. Summary shows
   what changed, why it matters, owner, routing, and three review reasons. *Changes*: material vs noise
   vs formatting. *Records*: the Goa redesign found via fallback selectors at low confidence, with
   notes. *Snapshots*: captured HTML and screenshots.
7. **Completion (30s).** Accept the summary; the run becomes Completed. Download the CSV.
8. **Failure handling (30s).** *New workflow* with an off-allowlist URL: rejected at intake. With
   `/mock/blocked`: run fails visibly with `browser_blocked`.
9. **Dashboard (30s).** Completion rate, review backlog, confidence, source health with layout drift
   and failures, model spend.

## Interactive booking (about 3 minutes)

1. *Workflows* → **Book a flight: Pune to Goa** → *Start*. In Run options pick **Slow** and tick
   **Also open a visible Chrome window** (optional). Start.
2. The *Live browser* tab shows each action with an orange highlight: cookie banner, typing Pune and Goa,
   date, travellers, Search, non-stop filter, sort by cheapest, fares recorded.
3. The agent compares all options and selects the cheapest, fills traveller details and **unticks the
   pre-ticked insurance** (point out: it avoided a ₹349 add-on).
4. On the review page it reads the total and stops. The approval card shows the flight, traveller and
   total. Press **Pause** to show control, then **Approve and continue**.
5. It confirms, verifies "Booking confirmed" and reads the reference. Summary shows the booking card.
6. Run it again and choose **Don't approve**: the run ends "Not booked" without confirming.
7. Open *Live browsers* while *Run all monitoring workflows* runs to show three browsers working in parallel.
