# AI maintenance context & guardrails

This repo builds a cache of UK parkrun-distance (5k) courses as GPX, **derived only from
OpenStreetMap** (route relations + openly-contributed Saturday-09:00 GPS traces). A weekly
AI maintenance job may propose **one** improvement PR; a second AI reviews it; they iterate
until both are satisfied and CI passes; then it merges. This file is the contract for that AI.

## HARD INVARIANTS — never change, never propose changing

1. **No AI-generated geometry, ever.** Course coordinates come *only* from deterministic
   processing of OSM data. The AI must never emit lat/lon, "fix up" a route by hand, or insert
   a model into the reconstruction path. LLMs hallucinate coordinates — this is non-negotiable.
2. **Accuracy bars are fixed and may not be loosened to inflate coverage:**
   - A route relation is "accurate/locked" only if **4800–5200 m** (`REL_LO`/`REL_HI`).
   - A reconstructed trace is accepted only if **4500–5600 m** (`TRACE_LO`/`TRACE_HI`).
   - Trace anchor: first point at **local ≥ 09:00:00 within 150 m** of the start, else discard.
   - Trace window: **09:00–09:45 local**; stop at ~5.5 km or 09:45.
   - Relation/loop must pass within **500 m** of the start.
   Raising coverage by **widening these bars** is forbidden — coverage gains must come from
   finding *more real data* (see Truth metric), never from relaxing what counts as accurate.
3. **Be kind to OSM.** Keep the hard rate-limit (≥1.5 s/req), descriptive User-Agent, early-stop
   paging, on-disk caching, and small batched rollout. Never turn this into a bulk harvester.
4. **Licensing stays intact.** Data is © OpenStreetMap contributors, ODbL; attribution in every
   GPX, README, and LICENSE must remain. Keep the "not affiliated with parkrun" disclaimer.
5. **Standard runners only** in CI/cron (free on public repos). Never larger/macOS runners.

## Truth metric (what to optimise)

Two things jointly, scored against reality:
1. **Coverage** — fraction of UK parkruns with a cached course, and
2. **Closeness to 5k** — how near each cached course is to 5000 m.

The AI improves *both* by **finding more real data and extracting it better** — never by
loosening the accuracy bars. The single most powerful lever is **which datetimes it queries**:
- Sweep **more historical Saturdays** (each adds traces to average → better accuracy + coverage).
- Query **high-footfall special events** — **Christmas Day and New Year's Day**, which have huge
  parkrun turnout (so far more GPS uploads land in OSM). NOTE these are **not always Saturdays** —
  parkrun runs them on the actual date whatever the weekday — so the anchor generalises from
  "Saturday 09:00" to **"known parkrun event datetimes at 09:00 local"** (Saturdays + Christmas
  Day + NYD). This is a real coverage unlock and fully within the invariants.

**Phased rollout.** Start UK-only (`countrycode 97`), Havant → north. Once UK coverage is high
enough (target: the same ≥80% within-tolerance bar), the AI should **expand to all parkruns
worldwide**, efficiently, reusing gap-fill + rotation + skip-locked so it never re-queries what's
already accurate. CRITICAL for global: the "09:00 local" anchor must use **each event's own
local timezone** (derived from its coordinates/country), not the hardcoded `Europe/London` used
for the UK phase — otherwise the time filter silently misses every overseas parkrun. Generalising
the timezone is a prerequisite the AI must handle before (or as part of) the global expansion.

## What the weekly AI MAY improve (within the invariants)

Operational and algorithmic *means*, as long as outputs still validate against `selftest.py`:
- **Querying strategy / rollout** — which dates and events to pull (per Truth metric above),
  region prioritisation, gap-retry cadence, search radius, backoff.
- Better trace extraction — e.g. **averaging multiple Saturdays' traces** to cut GPS noise,
  smarter multi-lap detection, smoothing/simplification.
- Smarter relation way-chaining (gap bridging, dedup) for a more accurate measured length.
- Rollout prioritisation, gap-retry cadence, search radius, backoff — operational knobs only.
- A **QA flag** for courses whose distance is in-band but whose shape looks wrong
  (self-intersections, spikes) — flag for human review; do not silently rewrite geometry.
- Diagnosing low-yield regions and reporting *why* (not fabricating data to fill them).

## Process the AI must follow

1. **Author** (weekly): read `index.json` outcomes + the latest run log, decide if the caching
   algorithm can be improved *within the invariants*. If yes, open exactly one focused PR with a
   clear rationale tied to observed data. If nothing's worth changing, do nothing.
2. **Reviewer** (second AI): critique the PR against this file and CI. If it violates an
   invariant, games coverage, touches geometry, or isn't justified by data — request changes.
   Loop until both author and reviewer are satisfied.
3. **Gate**: `selftest.py` (the caching self-test) **must pass**; a PR that breaks the caching
   mechanism cannot merge. Only then merge.

## Self-updating model (GitHub Models only)

All AI here runs on **GitHub Models** via the workflow's built-in `GITHUB_TOKEN` (free, no
secret to manage). The weekly review picks the best available **GitHub Models** model for this
job (a reasoning-class model is preferred — one deep think per week beats many shallow ones) and
records it in `model.json`. Because every GitHub model uses the same `GITHUB_TOKEN`, switching
models **never needs a new secret** — it can self-update freely within the catalogue. Only
*extending beyond GitHub Models* to another provider would need a key, and that must be a
review-required PR @mentioning the owner — never automatic.
