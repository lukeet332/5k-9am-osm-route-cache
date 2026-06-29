# Idea journal (AI diary)

Author reads this before proposing: build on what worked, never re-propose a DONE idea as-is, get more
creative. Reviewer reads it to spot churn. Bot: APPEND-ONLY (never rewrite past entries), dense ASCII
(BIBLE #10); the owner may periodically compact losslessly. Newest entry at the bottom. Idea seeds to
think laterally: see the "levers" section of AI_CONTEXT.md.

## Lessons (do not relearn)
- CHURN GUARD: a re-proposal of existing doubling once merged as a 1-word edit because the journal was
  empty - nothing flagged the repeat. Genuinely-NEW ideas only; re-proposing a DONE idea = churn (PR
  closed). A justified MEANINGFUL improvement on a done idea is NOT churn.
- DOUBLING DISTANCE (v0.2.1 hot-fix): NEVER measure length(lap+lap) - self-concatenation adds a phantom
  end->start seam that overshoots and loses real 2-lap courses. Use 2*length(lap). A green self-test
  does not prove new distance maths unless a case actually exercises it - hand-trace the arithmetic and
  watch for the seam trap.

## ALREADY IMPLEMENTED - do NOT re-propose as-is (a meaningful improvement ON one is fine, not churn)
- Relation doubling for ~2.3-2.8k (HALF_REL_LO/HI), provisional.
- Trace doubling for ~2.3-2.8k Saturday-09:00 traces.
- Multi-Saturday trace averaging (pointwise mean); prefer recent (last 2yr).
- Christmas Day + New Year's Day events in the 09:00-09:45 window.
- Correct doubled distance = 2*length(lap), never length(lap+lap).
- GLOBAL event query (load_events: all ~2361 adult parkruns, UK-first).
- Per-event tz via timezonefinder (do NOT revert to hardcoded London or a lon/offset hack).
- Per-country reporting (report.py -> coverage_by_country.json + README table).
- Batched Overpass per 1-degree cell + .relcache; _get honours Retry-After (do NOT revert to per-event
  Overpass queries - that hammers OSM).
- Self-audit (audit_recoverable/best_lap_n): flags + prioritises non-success entries recoverable at the
  best integer lap count, so stale/lap-N cases self-heal.
- Error observability: a crash mid-build is recorded as status=error (visible + prioritised), not lost
  to the Actions log.

## Entries (terse, newest last)
- Seed: relation-first (4.8-5.2k) -> Saturday-09:00 trace fallback -> gap; Havant->north, gap-first
  rotation, refine at >=80%. Baseline; coverage thin (most parkruns have no OSM trace).
- v0.1.0: relation doubling for 2-lap. DONE.
- v0.2.0: churn lesson (see Lessons).
- v0.2.1: doubling-distance phantom-seam fix (see Lessons).
- 2024-07-30: added Christmas/NYD trace extraction.
- 2026-06-26 DeepSeek-V3.2: trace doubling for half-distance traces.
- 2026-06-26 deepseek-v4-flash: prefer recent traces (last 2yr) in averaging.

### 2026-06-27 - deepseek-v4-flash-bot (deepseek-ai/deepseek-v4-flash, minor)
- Generalise doubling from 2x to best-integer-N lap rule for traces and relations, recovering ~10 more courses from the audit list.

### 2026-06-29 - deepseek-v4-flash-bot (deepseek-ai/deepseek-v4-flash, patch)
- Fix trace doubling: use N*length(lap) not length(lap*N) to avoid phantom seam overshoot
