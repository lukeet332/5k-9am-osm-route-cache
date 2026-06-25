# 5k 9am route GPX cache (OSM-derived)

![parkruns successfully mapped](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/lukeet332/5k-9am-osm-route-cache/main/coverage.json)

A cache of UK parkrun-distance (5k) courses as GPX files, built **entirely from
OpenStreetMap** for offline/navigation use by a personal Wear OS running app. The badge above
is the live count of parkruns successfully mapped (within the 4.8–5.2 km success tolerance),
refreshed every cache run.

> **Data:** © OpenStreetMap contributors, made available under the
> [Open Database License (ODbL)](https://opendatacommons.org/licenses/odbl/). Any
> redistribution of these GPX files must keep this attribution and stay ODbL.
>
> **Not affiliated with parkrun.** Courses are derived from public OpenStreetMap data
> (route relations + openly-contributed GPS traces), not from parkrun's own data.

## How changes reach `main` (protected, PR-only)

- **Code** (AI maintenance) → PR labelled `automerge` → must pass the CI self-test **and** the
  AI review before auto-merge.
- **Cache data** (the cache job) → committed **directly to `main`, one commit per route as it
  locks** (the admin cache bot bypasses the PR rule for *generated data only*; the code self-test
  is irrelevant to data, and CI ignores data-only pushes). Code still goes through PR + CI + review.
- The app reads the cache from `main`:
  `https://raw.githubusercontent.com/lukeet332/5k-9am-osm-route-cache/main/index.json`.

## How a course is chosen (per event, worked south → north)

1. **OSM route relation** named "… parkrun" near the start — used **only if within ±4 % of 5 km** (4.8–5.2 km).
2. else **reconstructed from OSM's open Saturday-09:00 GPS traces** — multi-lap aware, anchored
   at the start at 09:00 local, trimmed to the 09:00–09:45 race window.
3. else **no entry** (logged as a gap — most parkruns have no OSM trace; coverage is partial **by design**).

## `routes/` layout — `success/` vs `failed/`

- **`routes/success/<event>.gpx`** — courses within the 4.8–5.2 km success tolerance. **These are
  what the app uses**, and what the badge counts.
- **`routes/failed/<event>.gpx`** — OSM data was found near the start but it's *off-tolerance*
  (e.g. a ~2.5 km relation that's likely **one lap of a 2-lap parkrun**, or a near-miss incomplete
  relation). Kept purely as **diagnostics for the AI** to iterate on — not used as a course.
- An event lives in **at most one** folder at a time (`build_one` clears both before writing), so a
  success **replaces/deletes** any prior failed entry. Every `index.json` entry also records what the
  relation *and* the trace measured (`relation_m`, `trace_m`) plus a `status`. Old versions live in
  **git history**, not as duplicate files.

## Coverage is partial — and that's expected

Most runners log to Strava/Garmin, not OSM, so the open trace pool is sparse — many parkruns have
no usable OSM trace yet. This cache fills in the ones OSM *does* cover and grows over time as the
OSM corpus does; it is **not** a complete parkrun course library (no free, legal source for that
exists). The consuming app falls back to live lookup / "record your own run" for everything not here.

## Run it

```bash
python3 build_cache.py --limit 30                # Havant → north, gap-first (open events only)
python3 build_cache.py --limit 30 --commit-each  # …and commit+push each route as it locks
```

Outputs `routes/<eventname>.gpx` + `index.json`. Re-runs are incremental (skips already-accurate
courses, rotates through gaps) and cache OSM responses on disk. **Be kind to OSM**: hard
rate-limited (~1 req/1.5 s), descriptive User-Agent, early-stop paging, and a **circuit-breaker
that stops a run if OSM starts rate-limiting (HTTP 429)** so we never get the IP blocked.

A GitHub Action (`.github/workflows/weekly-saturday.yml`) runs it on a schedule (frequent during
the initial cache build, then dial back to weekly), committing each route straight to `main`.
