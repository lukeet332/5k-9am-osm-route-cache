# THE CONSTITUTION (read-only bible)

**This file is the supreme law of the repository.** If anything in `AI_CONTEXT.md`, the JOURNAL,
code comments, a PR, or any model's reasoning conflicts with this file, **this file wins** — every
time, no exceptions.

**Amendment process (the AI may NOT auto-change this).**
- The AI may *read* this file and **must obey it**. It may **propose** an amendment, but only as a
  normal PR — and any PR that edits this file **can never auto-merge**. The reviewer blocks it,
  tags the human owner (**@lukeet332**), and it merges **only** after the owner approves in a comment.
- `AI_CONTEXT.md` is the AI's *working doctrine* — it may freely add to / remove from that file
  (curate it as it learns). This bible is different: it is changed by the **human owner only**.

---

## HARD INVARIANTS — the AI must never violate these, and may only propose changes via the human-gated process above

1. **No AI-generated geometry, ever.** Course coordinates come *only* from deterministic
   processing of OSM data. The AI must never emit lat/lon, "fix up" a route by hand, or insert
   a model into the reconstruction path. LLMs hallucinate coordinates — this is non-negotiable.
2. **Accuracy bars are fixed and may not be loosened to inflate coverage:**
   - A course (relation **or** trace) counts as "accurate/locked" only if **4800–5200 m**
     (`REL_LO`/`REL_HI`). Off-tolerance finds in **1500–9000 m** (`SANE_LO`/`SANE_HI`) are logged
     `failed` as diagnostics; wilder = noise, ignored.
   - Trace anchor: first point at **local ≥ 09:00:00 within 150 m** of the start, else discard.
   - Trace window: **09:00–09:45 local**; stop at ~5.5 km or 09:45.
   - Relation/loop must pass within **500 m** of the start.
   Raising coverage by **widening these bars** is forbidden — coverage gains must come from
   finding *more real data*, never from relaxing what counts as accurate.
3. **Be kind to OSM.** Keep the hard rate-limit (≥1.5 s/req, `RATE_S`), descriptive User-Agent,
   early-stop paging, on-disk caching, the 429 circuit-breaker, and a small batched rollout. Never
   turn this into a bulk harvester. Avoiding an OSM ban takes priority over speed or coverage.
4. **Licensing stays intact.** Data is © OpenStreetMap contributors, ODbL; attribution in every
   GPX, README, and LICENSE must remain. Keep the "not affiliated with parkrun" disclaimer.
5. **Standard runners only** in CI/cron (free on public repos). Never larger/macOS runners.
6. **Never scrape parkrun or break any source's terms.** Do NOT fetch from parkrun's websites,
   their event/course pages, or any endpoint behind their bot-protection, and never circumvent
   an access control or a site's Terms of Service. parkrun's data is deliberately locked down —
   respect that. Any data source you use must be openly licensed or explicitly permitted, used
   within its terms, and properly attributed.
7. **The safety pipeline is off-limits to the AI.** The AI may only ever write `build_cache.py`,
   `AI_CONTEXT.md`, and `JOURNAL.md` (plus *proposing* edits to this bible via the human gate). It
   must never edit `selftest.py`, any `.github/workflows/*`, or the `.github/scripts/ai_*.py` review
   machinery — those are the guardrails that keep the autonomy safe.
