# 5k 9am route GPX cache (OSM-derived)

A cache of UK parkrun-distance (5k) courses as GPX files, built **entirely from
OpenStreetMap** for offline/navigation use by a personal Wear OS running app.

> **Data:** © OpenStreetMap contributors, made available under the
> [Open Database License (ODbL)](https://opendatacommons.org/licenses/odbl/). Any
> redistribution of these GPX files must keep this attribution and stay ODbL.
>
> **Not affiliated with parkrun.** Courses are derived from public OpenStreetMap data
> (route relations + openly-contributed GPS traces), not from parkrun's own data.

## How changes reach `main` (protected, PR-only)

- **Code** (AI maintenance) → PR labelled `automerge` → must pass the CI self-test **and** the
  AI review before auto-merge.
- **Cache data** (the weekly job) → PR labelled `cache-update` → auto-merges **bypassing the code
  CI** (the data is the output of already-reviewed code; the code self-test is irrelevant to it).
- The app reads the cache from `main`:
  `https://raw.githubusercontent.com/lukeet332/5k-9am-osm-route-cache/main/index.json`.

## How a course is chosen (per event, worked south → north)

1. **OSM route relation** named "… parkrun" near the start — used **only if within ±8 % of 5 km**.
2. else **reconstructed from OSM's open Saturday-09:00 GPS traces** — multi-lap aware, anchored
   at the start at 09:00 local, trimmed to the 09:00–09:45 race window.
3. else **no entry** (logged as a gap — most parkruns have no OSM trace; coverage is partial **by design**).

## Coverage is partial — and that's expected

Most runners log to Strava/Garmin, not OSM, so the open trace pool is sparse. A regional survey
returned a usable course for roughly **1 in 10** parkruns. This cache fills in the ones OSM *does*
cover and grows slowly as the OSM corpus does; it is **not** a complete parkrun course library
(no free, legal source for that exists). The consuming app falls back to live lookup / "record
your own run" for everything not in here.

## Run it

```bash
python3 build_cache.py --offset 0 --limit 50   # first 50, south → north
```

Outputs `routes/<eventname>.gpx` + `index.json`. Re-runs are incremental and cache OSM
responses on disk. **Be kind to OSM**: the script is hard rate-limited (~1 req/1.5 s), uses a
descriptive User-Agent, stops paging early, and is intended to run slowly in small regional
batches — **not** as a bulk harvester.

A weekly GitHub Action (`.github/workflows/weekly-saturday.yml`) re-runs it on a public repo
(free unlimited Actions minutes) to gradually improve coverage.
