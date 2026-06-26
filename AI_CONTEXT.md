# AI maintenance context & guardrails

This repo builds a cache of parkrun-distance (5k) courses worldwide (UK first) as GPX, **derived only
from OpenStreetMap** (route relations + openly-contributed Saturday-09:00 GPS traces). A weekly
AI maintenance job may propose **one** improvement PR; a second AI reviews it; they iterate
until both are satisfied and CI passes; then it merges. This file is the contract for that AI.

## HARD INVARIANTS -> see the CONSTITUTION

The hard invariants and the fixed accuracy bars live in **`AI_CONTEXT_READ_ONLY_BIBLE.md`** - the
read-only **constitution**, which **supersedes this file**. **Read it first and obey it absolutely.**
You may *propose* an amendment to it, but only as a PR that requires the human owner's approval and
**can never auto-merge** (the reviewer blocks it and tags @lukeet332).

This file (`AI_CONTEXT.md`) is your **working doctrine** - strategy, learnings, process notes. Unlike
the constitution, you may **freely curate it: add to it, and remove from it** what you judge obsolete
or unhelpful - always *within* the constitution's bounds. Anything here that conflicts with the
constitution is void.

## Truth metric (what to optimise)

Two things jointly, scored against reality:
1. **Coverage** - fraction of parkruns with a cached course (UK first, then worldwide - the end goal
   is to map ALL parkruns), and
2. **Closeness to 5k** - how near each cached course is to 5000 m.

The AI improves *both* by **finding more real data and extracting it better** - never by
loosening the accuracy bars. The single most powerful lever is **which datetimes it queries**:
- Sweep **more historical Saturdays** (each adds traces to average -> better accuracy + coverage).
- Query **high-footfall special events** - **Christmas Day and New Year's Day**, which have huge
  parkrun turnout (so far more GPS uploads land in OSM). NOTE these are **not always Saturdays** -
  parkrun runs them on the actual date whatever the weekday - so the anchor generalises from
  "Saturday 09:00" to **"known parkrun event datetimes at 09:00 local"** (Saturdays + Christmas
  Day + NYD). This is a real coverage unlock and fully within the invariants.

**Global rollout - LIVE (the end goal is to map ALL parkruns worldwide as GPX).** As of the global
rollout, `load_events` queries EVERY adult parkrun worldwide (~2361 events), not just the UK. UK is
ordered first (Havant -> north), then the rest by country+latitude; foreign events are never-tried so
the last_tried rotation sweeps them first - harvesting untapped foreign data while UK gaps wait. The
"09:00 local" anchor is now PER-EVENT: `local(dt, lat, lon)` derives each event's IANA timezone from
its coordinates via the `timezonefinder` package (DST-correct via zoneinfo), with a graceful fallback
to Europe/London if the package is absent. DO NOT revert to a UK-only query or a hardcoded London tz,
and DO NOT replace timezonefinder with a longitude/offset hack - that ignores DST + zone boundaries and
silently drops foreign traces (it broke the UK once). `relation_course` is timezone-agnostic, so foreign
relation successes need no tz. Coverage + the badge are now the WORLD tally; per-country progress lives
in the README table (`report.py` / `coverage_by_country.json`). The remaining lever for thin-coverage
countries is additional openly-licensed data sources (within the invariants) - every parkrun mapped.
**Per-country reporting (LIVE):** `report.py` writes `coverage_by_country.json` and the README
"Coverage by country" table (each country's mapped/total), and `coverage.json` + the repo description
are the WORLD tally. Per-country progress is already visible; it fills in as the rollout sweeps each country.

## Source trust & the long-term "map it to the mm" goal

Not all successes are equal - **be suspicious of any cached course that wasn't built from real
Saturday-09:00 GPS.** The `source` field on every success says which it is:
- **`osm_9am_trace` (`provisional: false`) - TRUSTED.** Reconstructed from real runners' GPS: it's
  what people actually ran. This is the gold standard.
- **`osm_relation` (`provisional: true`) - PROVISIONAL.** A curated OSM line that merely *measures*
  4.8-5.2 km. Good enough to ship to the app, but it may not be the true course (a rough relation
  can happen to total ~5k). Treat with suspicion.

`build_one` already encodes this: when both qualify, the **trace wins**.
Your standing remit, in priority order:
1. **Coverage first** - fill `gap`s and fix `failed`s (most parkruns still have no course).
2. **Upgrade provisional -> trace** - as the trace pool grows, replace `provisional: true`
   (relation) successes with real `osm_9am_trace` courses. (Re-querying locked courses already
   happens in the refine phase once >=80% are within tolerance - that's when this kicks in.)
3. **Long-term, LOW-priority end goal - refine even already-trusted courses.** Once the
   successfully-mapped count is very high (even with traces everywhere), keep nudging quality up:
   the dream is to map each parkrun **to the millimetre** by **averaging many individuals' GPS
   traces** of the same course (more uploads -> less noise -> the true line). This never stops, but
   it is **always lower priority than coverage and upgrading provisionals** - don't spend the
   weekly improvement on micro-refining trusted courses while gaps/failures and provisionals remain.

All three obey the HARD INVARIANTS - more/better *real* data, never AI geometry, never loosened bars.

## Tested contract - keep these callable (improve internals, don't rename/re-signature)

`selftest.py` is the merge gate; it imports these from `build_cache.py` and asserts their behaviour.
**You may freely rewrite their internals** (that's how you improve the algorithm), but if you rename
them or change their signature/return shape the self-test fails and your PR is blocked. Keep:
- `assemble(ways) -> list[(lat,lon)]` - chain unordered ways into one polyline.
- `trace_course(name, lat, lon) -> (metres, [(lat,lon)], date_str) | None` - reconstruct from traces.
- `build_one(ev) -> dict` with keys `status` (`success`/`failed`/`gap`), `source`, `distance_m`,
  `relation_m`, `trace_m`, and `provisional` on successes - this dict IS the `index.json` schema.
- `is_locked(entry) -> bool` - true iff `distance_m` is within the 4800-5200 m bars.
- `write_gpx(name, longname, pts, source)` - writes `routes/<name>.gpx` (stamps the version).
- `length(pts)`, `algo_version() -> str`, `_trace_cache_file(name, half_m, page)`.
- Constants `REL_LO`/`REL_HI` (4800/5200), `ROUTES`, `TRACECACHE`.

If you genuinely need to change one of these contracts you can't edit `selftest.py` (it's off-limits)
- so keep a thin wrapper with the old signature, or leave the human to adjust the test. Keep this list
current if you add/rename a tested symbol.

## What the weekly AI MAY improve (within the invariants)

Operational and algorithmic *means*, as long as outputs still validate against `selftest.py`:
- **Querying strategy / rollout** - which dates and events to pull (per Truth metric above),
  region prioritisation, gap-retry cadence, search radius, backoff.
- Better trace extraction - e.g. **averaging multiple Saturdays' traces** to cut GPS noise,
  smarter multi-lap detection, smoothing/simplification. Also consider **preferring recent Saturdays**:
  parkruns occasionally change their course, so blending a years-old trace with current ones can mix
  two different routes - weighting/limiting to the most recent ~1-2 years tracks the *current* course
  more faithfully (the trace fetch is date-agnostic today, so all historical Saturdays are averaged).
- Smarter relation way-chaining (gap bridging, dedup) for a more accurate measured length.
- **Timestamp-less ("public"/"private" privacy) traces - a big untapped coverage lever, and a model
  of the lateral creativity wanted here.** OSM returns per-point `<time>` only for `identifiable` /
  `trackable` traces; `public` / `private` traces come back anonymised and TIME-STRIPPED, so the
  09:00-Saturday window silently drops them (build_cache skips any trkpt with no `<time>`). That likely
  discards a LOT of usable GPS near each start. Recover it WITHOUT timestamps by using SPATIAL
  recurrence instead of time: cluster every trace passing near the start anchor, find the ~5k path the
  MOST traces share (the dominant repeated route from the start is almost certainly the parkrun course),
  and accept it only on the usual bars (start within 150m, distance in 4.5-5.6k). This turns the privacy
  limitation into a method (frequency-of-traversal). GUARDRAILS: never accept a single ambiguous track
  (commuters, dog-walkers, cyclists share those paths); require MULTIPLE corroborating traces + a clean
  ~5k geometry; keep results provisional; never invent a line to hit 5k.
- **Course-topology-aware extraction (big lever for the off-tolerance `failed` entries).** parkrun
  courses are not all simple loops: they can be a single loop, N laps (2, 3, ...), a partial lap then
  full lap(s) (e.g. 1.5 laps), an out-and-back, or point-to-point with different start/finish. Current
  code only handles an in-band relation/trace plus 2x doubling of a ~2.3-2.8k half-distance find - it
  misses 3-lap (~1.67k), ~2.5-lap, 1.5-lap (~3.3k), and out-and-back partials. Generalise to detect the
  topology and recover the full ~5k course. SAFEST signal: detect repetition WITHIN a GPS trace (a
  multi-lap run physically retraces the same loop N times) - recover the single lap + lap count from
  the trace itself, then confirm N*lap is ~5k. Multiply/extend ONLY with real evidence (a closed loop,
  or repeated geometry in the trace), keep results provisional, and NEVER just "multiply a number until
  it hits 5k" (that invents coverage from coincidence - a false positive, forbidden). This targets the
  ~100 `failed` entries that have real OSM data at the wrong distance.
- Rollout prioritisation, gap-retry cadence, search radius, backoff - operational knobs only.
- A **QA flag** for courses whose distance is in-band but whose shape looks wrong
  (self-intersections, spikes) - flag for human review; do not silently rewrite geometry.
- Diagnosing low-yield regions and reporting *why* (not fabricating data to fill them).
- **Event-age prioritisation via the events.json `id`.** events.json has no start-date, but each
  feature has a top-level `id` that is roughly chronological (Bushy = 1, the first parkrun) - lower id
  ~ older event. Older events have years of Saturdays so are far likelier to have OSM data; brand-new
  (high-id) events usually have none yet. Capturing `id` in `load_events` lets you prioritise older
  events first and treat very new ones as EXPECTED gaps (don't churn retrying them). It is a noisy
  proxy (cancelled/junior/overseas ids interleave) and does NOT save network calls (the trace fetch is
  bbox-wide + date-agnostic). The true first-run date would need parkrun's event pages - off-limits
  (invariant #6) - so use only this id proxy, never fetch parkrun for dates.
- **Additional data sources beyond OSM** - to lift coverage where OSM is thin, the algorithm MAY
  eventually pull from *other openly-licensed / explicitly-permitted* sources (e.g. open GPS-trace
  or public-domain route datasets, government/park open data), used within their terms and
  attributed. This is allowed ONLY within invariant #6: **never parkrun's sites, never scraping,
  never circumventing terms/access controls.** OSM stays the primary source; others are additive.

## Where your full context lives (read these)

Two outputs, two audiences - know which is which:
- **`routes/<event>.gpx`** - successful courses only. That's for the *app*; you rarely need to read
  the geometry.
- **`index.json` - YOUR full log. Read this for context.** One entry per attempted parkrun:
  - `status`: `success` | `failed` | `gap`
  - `distance_m`: chosen course length (null for a gap)
  - `relation_m`, `trace_m`: what the OSM *relation* and the *09:00 trace* each measured - present
    even when unused. **This is your richest signal**, especially on `failed` entries.
  - `source` (`osm_9am_trace` = trusted GPS / `osm_relation` = provisional), `provisional` (true on
    relation-sourced successes - your upgrade targets), `trace_date`, `last_tried`, `lat`, `lon`
- **`failed` entries are the gold for improvement** - e.g. `relation_m ~ 2300` => likely one lap of a
  2-lap parkrun (try doubling); `distance_m` just outside 4.8-5.2 km => likely an incomplete relation
  (try way-chaining). Off-distance *geometry* is deliberately NOT stored (token/space cost) - work
  from the metadata; older states are in git history if ever needed.
- You're normally handed a compact digest of all this (an outcomes summary) to keep token use low;
  read `index.json` directly only when you need per-event detail. Prefer **derived feature flags in
  index.json** over raw geometry - they're cheap and reusable.

## The idea JOURNAL (build context over time)

`JOURNAL.md` is the bots' running diary. Each week the author reads it, then appends an entry
(date, the idea, *why* from the outcomes, what you changed). The point is **accumulated knowledge**:
build on what worked, don't repeat what didn't, and get **progressively more creative week over
week. The reviewer also reads it. Append-only; never rewrite past entries.

## Process the AI must follow

1. **Author / MASTER** (weekly): read the JOURNAL + `index.json` outcomes + the algorithm, and
   propose ONE improvement *within the invariants* that genuinely advances the goal (caching ALL
   parkruns at ~5k). Improving the algorithm includes **pruning** logic that's wrong/obsolete, not
   only adding - but no pointless churn. Append a JOURNAL entry. If nothing's worth changing, just
   journal why.
2. **Reviewer / SLAVE** (a different AI): judge the PR on **two axes** - (a) SAFETY: invariants,
   accuracy bars, geometry, OSM-kindness, licensing; and (b) MERIT: does it really move us toward
   the goal, or is it silly add/remove churn or a re-tried failed idea? **Aim for consensus** - be
   a collaborator, not a perfectionist gatekeeper; don't block on style; once concerns are
   addressed, approve. Loop (max 3 rounds) until both are satisfied.
3. **Gate**: `selftest.py` **must pass**; a PR that breaks caching cannot merge. Only then merge.
4. **Declare a `version_bump`** in your proposal (`patch`/`minor`/`major`) by the SCOPE/ambition of
   the change - patch = small tweak/fix/prune, minor = a real new capability or quality gain (the
   usual case), major = an ambitious rework (sparingly). It can't break the output contract (you only
   edit the algorithm), so it's purely a readable signal. Merging your PR auto-cuts a semver release.

## Models - smartest free pair + a fast tier (self-updating)

Configured in `.github/ai_model.json`, re-evaluated weekly from a multi-source menu
(`github-models`, `gemini`, `openrouter`, `groq`, `mistral` - a provider with no key is skipped):
- **`primary` - MASTER author** (deep): the strongest free reasoner; defaults to GitHub Models
  (built-in `GITHUB_TOKEN`, no secret).
- **`fallback` - SLAVE reviewer** (deep + INDEPENDENT): a strong model from a **different
  provider** where >=2 are available, so the review is genuinely independent. Must stay deep -
  never the fast tier. Falls back to the master if its provider key is absent.
- **`fast`** (e.g. Gemini Flash): for *simple delegated subtasks only* - never reviews, never
  touches accuracy.

The weekly review picks the **SMARTEST master + reviewer that still FIT the free request limits**
- capability maximised, the free quota a hard constraint - and, since the same config runs on two
repos that might pick the same models, each must have free-tier headroom for **both repos combined**.
It validates every change with a live call; a provider with no key is simply skipped (graceful).

## Learnings (appended by the bot)
- Averaging multiple Saturday-09:00 traces improves closeness-to-5k and coverage without violating invariants.
- Expanded trace extraction to include Christmas Day and New Year's Day, as these are high-footfall events with valuable GPS data.
