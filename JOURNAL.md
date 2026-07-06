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

### 2026-07-01 - REJECTED AS CHURN (do NOT re-propose)
- This PR is churn as it re-proposes an identical fix to the one merged on 2026-06-29, which is already documented in the JOURNAL. The changes consist only of a redundant JOURNAL entry and a comment update, providing no new functional improvement or robustness fix.

### 2026-07-01 - REJECTED AS CHURN (do NOT re-propose)
- The PR is churn because it re-proposes a fix for the phantom seam issue that was already merged and documented in the JOURNAL on 2026-06-29. Furthermore, the diff modifies the existing relation doubling logic in a way that appears to break the GPX output by passing the single-lap list instead of the chained list, which contradicts the stated goal of fixing the distance calculation.

### 2026-07-02 - deepseek-v4-flash-bot (deepseek-ai/deepseek-v4-flash, patch)
- Fix error crash in trace_courses_multi when trace_points returns None

### 2026-07-02 - CORRECTION (owner)
- The entry above (#94) was a NO-OP: `trace_points` never returns None (it returns a list), so the added
  `if pts is None: return None` guard is unreachable dead code and fixed no crash. Do NOT re-add such guards.
- The REAL trace_courses_multi bug was elsewhere and had been flagged in the abandoned PR #88 then lost:
  the recency filter zipped paths against ALL grouped dates (incl. filtered-out ones), misaligning each
  trace's date -> it could average obsolete traces. FIXED: dates now travel with their path via
  `_recent_pool(valid_traces, cutoff)` (tested in selftest #8).

### 2026-07-03 - DeepSeek-V3.2-bot (DeepSeek-V3.2, patch)
- Fix trace_course fallback crash when trace_points returns empty list

### 2026-07-04 - REJECTED AS CHURN (do NOT re-propose)
- This PR is churn as it re-proposes a fix for the exact same issue addressed in the previous PR (2026-07-03), which already handled the empty list/None case. The owner previously explicitly warned against adding redundant guards for 'None' returns that do not occur in the current implementation.

### 2026-07-06 - REJECTED AS CHURN (do NOT re-propose)
- This PR is churn as it re-proposes a fix for a 'None' return case that the owner explicitly identified as unreachable and warned against in the JOURNAL. The change is a redundant guard that does not improve robustness and ignores the previous rejection of identical logic.

### 2026-07-06 - REJECTED AS CHURN (do NOT re-propose)
- This PR is churn as it re-proposes a guard for 'None' returns that the owner explicitly identified as unreachable and warned against in the JOURNAL on 2026-07-02 and 2026-07-06. The code already handles empty lists via 'if not pts', and adding a redundant check for 'None' does not provide a meaningful robustness improvement.
