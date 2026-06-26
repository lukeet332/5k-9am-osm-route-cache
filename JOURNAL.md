# Idea journal

The weekly AI maintenance bots keep a running diary here — each entry records an idea tried,
*why* (from the outcomes at the time), what changed, and (in hindsight) whether it helped. The
author reads this before proposing, to build on what worked, avoid repeating what didn't, and get
progressively more creative over time. Append-only; newest at the bottom.

---

### Seed — initial algorithm
- **Idea:** Relation-first (kept only at 4.8–5.2 km, proper way-chaining) → fall back to a
  reconstructed Saturday-09:00 GPS trace (multi-lap aware, 09:00–09:45 local, 150 m start anchor)
  → else logged gap. Havant → north rollout, gap-first with last-tried rotation, refine once ≥80%
  within tolerance.
- **Why:** OSM relations are sometimes incomplete/short; real Saturday-morning traces recover the
  true ~5k where they exist.
- **Outcome:** Baseline. Early coverage is thin (most parkruns have no OSM trace) — the open
  problem the weekly bot is here to chip away at.

### v0.1.0 — relation doubling for half-distance (2-lap) parkruns  ✅ DONE
- **Idea:** an OSM relation measuring ~2.3–2.8 km is likely ONE lap of a 2-lap parkrun; double the
  relation geometry to recover the full ~5 k course.
- **Implemented** in `build_one` (`HALF_REL_LO/HALF_REL_HI` = 2300/2800, doubled-chain, marked
  provisional). **This is already in the code — do NOT re-propose plain relation-doubling.**

### v0.2.0 — (churn, a lesson) ⚠️
- A re-proposal of the doubling above produced only a one-word comment edit (doubling already
  existed). It merged because the journal was empty so nothing flagged the repeat — now fixed.
- **Learning:** doubling for half-distance relations is DONE. Next ideas must be genuinely NEW, e.g.:
  prefer recent Saturdays (courses change over the years); handle out-and-back as well as loop
  doublings; trace doubling for ~half-distance traces; averaging more historical Saturdays; smarter
  relation way-chaining / gap-bridging; high-footfall Christmas/New-Year sweeps for extra traces.
