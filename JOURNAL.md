# Idea journal

The weekly AI maintenance bots keep a running diary here - each entry records an idea tried,
*why* (from the outcomes at the time), what changed, and (in hindsight) whether it helped. The
author reads this before proposing, to build on what worked, avoid repeating what didn't, and get
progressively more creative over time. Append-only; newest at the bottom.

---

### Seed - initial algorithm
- **Idea:** Relation-first (kept only at 4.8-5.2 km, proper way-chaining) -> fall back to a
  reconstructed Saturday-09:00 GPS trace (multi-lap aware, 09:00-09:45 local, 150 m start anchor)
  -> else logged gap. Havant -> north rollout, gap-first with last-tried rotation, refine once >=80%
  within tolerance.
- **Why:** OSM relations are sometimes incomplete/short; real Saturday-morning traces recover the
  true ~5k where they exist.
- **Outcome:** Baseline. Early coverage is thin (most parkruns have no OSM trace) - the open
  problem the weekly bot is here to chip away at.

### v0.1.0 - relation doubling for half-distance (2-lap) parkruns   DONE
- **Idea:** an OSM relation measuring ~2.3-2.8 km is likely ONE lap of a 2-lap parkrun; double the
  relation geometry to recover the full ~5 k course.
- **Implemented** in `build_one` (`HALF_REL_LO/HALF_REL_HI` = 2300/2800, doubled-chain, marked
  provisional). **This is already in the code - do NOT re-propose plain relation-doubling.**

### v0.2.0 - (churn, a lesson)
- A re-proposal of the doubling above produced only a one-word comment edit (doubling already
  existed). It merged because the journal was empty so nothing flagged the repeat - now fixed.
- **Learning:** doubling for half-distance relations is DONE. Next ideas must be genuinely NEW, e.g.:
  prefer recent Saturdays (courses change over the years); handle out-and-back as well as loop
  doublings; trace doubling for ~half-distance traces; averaging more historical Saturdays; smarter
  relation way-chaining / gap-bridging; high-footfall Christmas/New-Year sweeps for extra traces.

### v0.2.1 - fix the doubling distance (human hot-fix)
- **Bug found:** the doubling measured `length(rel[2] + rel[2])`, i.e. `length(lap+lap)`. Concatenating
  a polyline to itself makes `length()` add a PHANTOM segment from the lap's end back to its start, so
  the reported distance was `2*lap + (end->start jump)`. For laps that don't perfectly close this
  overshoots the 4.8-5.2k band - which is **exactly why doubling produced 0 successes and 2
  `osm_relation_doubled_offdist`**: real 2-lap courses were being pushed out of band and logged as
  failures.
- **Fix:** report `2 * length(rel[2])` (two laps' path length); the doubled *geometry* the app draws is
  still `rel[2]+rel[2]`. Added a deterministic self-test (`selftestdouble`) that a ~2.5k lap doubles to
  a ~5.0k SUCCESS - it was RED before the fix, GREEN after. **Lesson: a green self-test does not prove
  new distance maths is right unless a case actually exercises it; the reviewer now hand-traces
  distance arithmetic and watches for the self-concatenation phantom-seam trap.**

### 2024-07-30 - Expand trace extraction to include Christmas Day and New Year's Day events
- **Idea:** Expand trace extraction to include Christmas Day and New Year's Day events.
- **Why:** The `AI_CONTEXT.md` explicitly states these are high-footfall special events with huge parkrun turnout, offering a "real coverage unlock" by providing more GPS traces for averaging. The current algorithm only considers Saturdays. This should increase both coverage and closeness-to-5k by leveraging more real-world data.
- **What changed:** Modified `trace_courses_multi` and the single-trace fallback in `trace_course` to include traces from December 25th and January 1st, in addition to Saturdays, within the 09:00-09:45 local time window.

### 2026-06-26 - DeepSeek-V3.2-bot (DeepSeek-V3.2, minor)
- Add trace doubling for half-distance traces to capture 2-lap parkruns missed by relation-only doubling

### ALREADY IMPLEMENTED - do NOT re-propose AS-IS (re-proposing the same thing = churn, PR closed). A justified, MEANINGFUL improvement that builds on one of these is welcome and is NOT churn.
- Relation doubling for ~2.3-2.8k relations (double the lap to recover a 2-lap course). DONE.
- Trace doubling for ~2.3-2.8k Saturday-09:00 GPS traces (osm_9am_trace_doubled in build_one). DONE.
- Multi-Saturday trace averaging (trace_courses_multi, pointwise mean). DONE.
- Christmas Day + New Year's Day events included in the 09:00-09:45 trace window. DONE.
- Correct doubled distance uses 2*length(lap), never length(lap+lap). DONE.
Propose a genuinely NEW idea instead, e.g.: prefer/weight recent traces (courses change); smarter
relation way-chaining / gap-bridging; out-and-back doubling; per-event local timezone for global
expansion; QA flag for in-band but mis-shaped courses; additional openly-licensed data sources.

### 2026-06-26 - deepseek-v4-flash-bot (deepseek-ai/deepseek-v4-flash, minor)
- Prefer recent traces (last 2 years) in averaging to track current course shape and avoid mixing old/obsolete routes
