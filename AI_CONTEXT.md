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
6. **Never scrape parkrun or break any source's terms.** Do NOT fetch from parkrun's websites,
   their event/course pages, or any endpoint behind their bot-protection, and never circumvent
   an access control or a site's Terms of Service. parkrun's data is deliberately locked down —
   respect that. Any data source you use must be openly licensed or explicitly permitted, used
   within its terms, and properly attributed.

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
- **Additional data sources beyond OSM** — to lift coverage where OSM is thin, the algorithm MAY
  eventually pull from *other openly-licensed / explicitly-permitted* sources (e.g. open GPS-trace
  or public-domain route datasets, government/park open data), used within their terms and
  attributed. This is allowed ONLY within invariant #6: **never parkrun's sites, never scraping,
  never circumventing terms/access controls.** OSM stays the primary source; others are additive.

## Where your full context lives (read these)

Two outputs, two audiences — know which is which:
- **`routes/<event>.gpx`** — successful courses only. That's for the *app*; you rarely need to read
  the geometry.
- **`index.json` — YOUR full log. Read this for context.** One entry per attempted parkrun:
  - `status`: `success` | `failed` | `gap`
  - `distance_m`: chosen course length (null for a gap)
  - `relation_m`, `trace_m`: what the OSM *relation* and the *09:00 trace* each measured — present
    even when unused. **This is your richest signal**, especially on `failed` entries.
  - `source`, `trace_date`, `last_tried`, `lat`, `lon`
- **`failed` entries are the gold for improvement** — e.g. `relation_m ≈ 2300` ⇒ likely one lap of a
  2-lap parkrun (try doubling); `distance_m` just outside 4.8–5.2 km ⇒ likely an incomplete relation
  (try way-chaining). Off-distance *geometry* is deliberately NOT stored (token/space cost) — work
  from the metadata; older states are in git history if ever needed.
- You're normally handed a compact digest of all this (an outcomes summary) to keep token use low;
  read `index.json` directly only when you need per-event detail. Prefer **derived feature flags in
  index.json** over raw geometry — they're cheap and reusable.

## The idea JOURNAL (build context over time)

`JOURNAL.md` is the bots' running diary. Each week the author reads it, then appends an entry
(date, the idea, *why* from the outcomes, what changed). The point is **accumulated knowledge**:
build on what worked, don't repeat what didn't, and get **progressively more creative week over
week. The reviewer also reads it. Append-only; never rewrite past entries.

## Process the AI must follow

1. **Author / MASTER** (weekly): read the JOURNAL + `index.json` outcomes + the algorithm, and
   propose ONE improvement *within the invariants* that genuinely advances the goal (caching ALL
   parkruns at ~5k). Improving the algorithm includes **pruning** logic that's wrong/obsolete, not
   only adding — but no pointless churn. Append a JOURNAL entry. If nothing's worth changing, just
   journal why.
2. **Reviewer / SLAVE** (a different AI): judge the PR on **two axes** — (a) SAFETY: invariants,
   accuracy bars, geometry, OSM-kindness, licensing; and (b) MERIT: does it really move us toward
   the goal, or is it silly add/remove churn or a re-tried failed idea? **Aim for consensus** — be
   a collaborator, not a perfectionist gatekeeper; don't block on style; once concerns are
   addressed, approve. Loop (max 3 rounds) until both are satisfied.
3. **Gate**: `selftest.py` **must pass**; a PR that breaks caching cannot merge. Only then merge.

## Models — smartest free pair + a fast tier (self-updating)

Configured in `.github/ai_model.json`, re-evaluated weekly from a multi-source menu
(`github-models`, `gemini`, `openrouter`, `groq`, `mistral` — a provider with no key is skipped):
- **`primary` — MASTER author** (deep): the strongest free reasoner; defaults to GitHub Models
  (built-in `GITHUB_TOKEN`, no secret).
- **`fallback` — SLAVE reviewer** (deep + INDEPENDENT): a strong model from a **different
  provider** where ≥2 are available, so the review is genuinely independent. Must stay deep —
  never the fast tier. Falls back to the master if its provider key is absent.
- **`fast`** (e.g. Gemini Flash): for *simple delegated subtasks only* — never reviews, never
  touches accuracy.

The weekly review picks the **SMARTEST master + reviewer that still FIT the free request limits**
— capability maximised, the free quota a hard constraint — and, since the same config runs on two
repos that might pick the same models, each must have free-tier headroom for **both repos combined**.
It validates every change with a live call; a provider with no key is simply skipped (graceful).

## Learnings (appended by the bot)
- Averaging multiple Saturday-09:00 traces improves closeness-to-5k and coverage without violating invariants.
