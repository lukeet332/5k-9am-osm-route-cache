# 5k 9am route GPX cache (OSM-derived)

![parkruns successfully mapped](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/lukeet332/5k-9am-osm-route-cache/main/coverage.json)

A cache of parkrun-distance (5k) courses as GPX files (UK first, rolling out worldwide), built
**entirely from OpenStreetMap** for offline/navigation use by a personal Wear OS running app. The badge above
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
- **The constitution** (`AI_CONTEXT_READ_ONLY_BIBLE.md`) is the **supreme law** — hard invariants +
  the fixed accuracy bars — and it supersedes everything else. The AI obeys it and may *curate*
  `AI_CONTEXT.md` (its working doctrine) freely, but a PR that edits the constitution **can never
  auto-merge**: the reviewer blocks it, tags the human owner, and it merges only after an owner
  comment beginning `/approve-bible`.
- **Cache data** (the cache job) → committed **directly to `main`, one commit per route as it
  locks** (the admin cache bot bypasses the PR rule for *generated data only*; the code self-test
  is irrelevant to data, and CI ignores data-only pushes). Code still goes through PR + CI + review.
- The app reads the cache from `main`:
  `https://raw.githubusercontent.com/lukeet332/5k-9am-osm-route-cache/main/index.json`.

## How a course is chosen (per event, worked south → north)

Both an OSM relation and a reconstructed GPS trace are measured; a course counts only if within
**±4 % of 5 km** (4.8–5.2 km). When both qualify, the **real GPS trace wins** — it's the true course
runners actually ran:

1. **Reconstructed from OSM's open Saturday-09:00 GPS traces** — multi-lap aware, anchored at the
   start at 09:00 local, trimmed to the 09:00–09:45 race window. **Trusted** (`provisional: false`).
2. else an **OSM route relation** named "… parkrun" near the start — a curated line that *measures*
   ~5k. Shipped but marked **`provisional: true`** (not GPS-verified) so it can be upgraded to a real
   trace later.
3. else **no entry** (logged as a gap — most parkruns have no OSM trace; coverage is partial **by design**).

## Two outputs: `routes/` (for the app) and `index.json` (for the AI)

- **`routes/<event>.gpx`** — **only successful courses** (within 4.8–5.2 km). This is all the **app**
  needs; it's also what the badge counts. One file per event; a later non-success deletes it.
- **`index.json`** — the **full detailed log of every attempt**, which is what the **AI** reads to
  improve the script. Each entry:
  - `status` — `success` | `failed` | `gap`
  - `distance_m` — the chosen course length (null for a gap)
  - `relation_m`, `trace_m` — what the OSM *relation* and the *09:00 trace* each measured (so a
    `failed` like `relation_m: 2238` flags "≈ one lap of a 2-lap parkrun → try doubling")
  - `source` (`osm_9am_trace` = trusted GPS, `osm_relation` = provisional), `provisional` (true on
    relation-sourced successes), `trace_date`, `last_tried`, `lat`, `lon`

**Failures are kept as data, not files** — the off-distance geometry isn't stored (it would bloat the
cache and the AI's token budget); the metadata above is the signal. The full coverage history (and any
past geometry) lives in **git history**.

## Versioned releases (the algorithm's changelog)

Every time an **AI improvement PR merges**, a semver'd GitHub Release is cut automatically
(`release.yml`), so the algorithm's evolution has a readable history. The bump reflects the
**scope/ambition** of the change (it can't break the output contract — the AI only edits the
algorithm): **patch** = small tweak/fix, **minor** = a real new capability/quality gain, **major** =
an ambitious rework. The AI author declares the level in its PR; the release notes carry its summary
+ the diff. Cache-data commits and manual PRs don't cut releases. Each cached course is also stamped
with the version that built it — `built_by` in `index.json` and the GPX `creator` — for provenance.

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

## Coverage by country

<!-- COVERAGE-BY-COUNTRY:START -->
_Worldwide: 150/2364 parkruns mapped across 20 countries (UK first; other countries fill in as the global rollout sweeps them)._

| Country | Mapped / Total |
|---|---|
| United Kingdom | 132/886 |
| Australia | 2/543 |
| South Africa | 2/229 |
| Ireland | 1/114 |
| Poland | 5/109 |
| United States | 0/101 |
| Germany | 4/79 |
| New Zealand | 1/74 |
| Canada | 0/64 |
| Japan | 0/53 |
| Netherlands | 2/30 |
| Italy | 1/15 |
| Sweden | 0/15 |
| Denmark | 0/13 |
| Norway | 0/13 |
| Finland | 0/9 |
| Austria | 0/6 |
| Singapore | 0/5 |
| Lithuania | 0/5 |
| Malaysia | 0/1 |
<!-- COVERAGE-BY-COUNTRY:END -->
