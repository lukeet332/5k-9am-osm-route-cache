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
