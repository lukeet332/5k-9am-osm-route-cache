# AI maintenance contract (AI_CONTEXT.md)

Repo caches parkrun 5k courses worldwide (UK-first) as GPX, derived ONLY from OpenStreetMap (route
relations + open Saturday-09:00 GPS traces). Weekly: author AI proposes ONE improvement PR -> reviewer
AI judges -> iterate to consensus -> selftest gates -> merge. This file = working doctrine you may
add/remove within the constitution. Optimised for AI reading: terse, dense, not prose.

## Constitution (supreme)
Hard invariants + fixed accuracy bars live in `AI_CONTEXT_READ_ONLY_BIBLE.md` (SUPREME, overrides this
file). Read it first, obey absolutely. You may PROPOSE a BIBLE amendment but it NEVER auto-merges
(reviewer blocks + tags @lukeet332). Anything here that conflicts with it is void.

## Truth metric (optimise both, scored vs reality)
1. Coverage = fraction of parkruns with a cached course (UK first, then world; goal = map ALL parkruns).
2. Closeness = how near each course is to 5000 m.
Raise both by finding more real data + extracting it better, NEVER by loosening bars. Top lever = which
datetimes you query:
- More historical Saturdays (more traces to average -> accuracy + coverage).
- High-footfall Christmas Day + New Year's Day (huge turnout -> more GPS uploads). NOT Saturdays -> the
  anchor generalises to "known parkrun event datetimes at 09:00 local" (Saturdays + Xmas + NYD).

GLOBAL ROLLOUT = LIVE. `load_events` queries EVERY adult parkrun (~2361), UK-first (Havant->north) then
country+lat; never-tried foreign events sweep first. "09:00 local" is PER-EVENT: `local(dt,lat,lon)`
derives the IANA tz from coords via `timezonefinder` (DST-correct via zoneinfo), fallback Europe/London.
DO NOT revert to UK-only, hardcoded London, or a lon/offset hack (ignores DST + zone edges, drops foreign
traces, broke the UK once). `relation_course` is tz-agnostic. `coverage.json` + badge + description = the
WORLD tally; per-country mapped/total via `report.py` -> `coverage_by_country.json` + README table (LIVE).

## Source trust + priorities
Every success has a `source`:
- `osm_9am_trace` (provisional:false) = TRUSTED (real runners' GPS; gold standard).
- `osm_relation` (provisional:true) = PROVISIONAL (a curated line that merely MEASURES 4.8-5.2k; may not
  be the true course). Treat with suspicion.
`build_one`: trace wins when both qualify. Priorities: (1) COVERAGE first - fill `gap`, fix `failed`;
(2) upgrade provisional -> trace as the trace pool grows (refine phase, >=80% locked); (3) LOWEST -
refine trusted courses toward mm-accuracy by averaging many GPS traces; never spend the weekly slot here
while gaps/failed/provisionals remain. All obey invariants (real data only, never AI geometry, never
loosened bars).

## Tested contract
TWO gate files (CI runs both). `selftest.py` = FROZEN invariants/properties + safety net, OFF-LIMITS to
edit (constitutional bars, source-trust/provisional, no-abort robustness, the best_lap_n argmin PROPERTY,
audit safety). `test_behavior.py` = EDITABLE behavioural expectations (specific best_lap_n outputs, exact
doubled distance/source label, exact audit set); you MAY update it IN THE SAME changeset when a real
build_cache.py change legitimately alters one of those expectations - but ONLY that expectation, NEVER to
weaken/remove a check (the arbiter + CodeRabbit reject a loosened safety net). A change that can only pass
by editing selftest.py is breaking an invariant, not improving.
Both import these from `build_cache.py` and assert their behaviour. Rewrite internals freely (that IS how
you improve), but DO NOT rename or change signature/return shape or the gate fails. Keep current if you
add/rename a tested symbol:
- `assemble(ways) -> [(lat,lon)]`
- `trace_course(name,lat,lon) -> (m, [(lat,lon)], date_str) | None`
- `build_one(ev) -> dict{status: success|failed|gap, source, distance_m, relation_m, trace_m, provisional}` (= index.json schema)
- `is_locked(entry) -> bool` (distance_m in 4800-5200)
- `audit_recoverable(index)`, `best_lap_n(length_m)` (self-audit: flags non-success entries recoverable at the best integer lap count)
- `_recent_pool(valid_traces, cutoff)` (multi-trace averaging: keeps each path paired with its date; recent-or-all pool)
- `write_gpx(name,longname,pts,source)`; `length(pts)`; `algo_version()->str`; `_trace_cache_file(name,half_m,page)`
- consts `REL_LO`/`REL_HI` (4800/5200), `ROUTES`, `TRACECACHE`
Must change a contract? Can't edit selftest.py -> keep a thin old-signature wrapper, update the matching
expectation in test_behavior.py, or leave it to the human.

## Levers you MAY improve (within invariants; output must still pass selftest)
- Querying/rollout: which dates+events, region priority, gap-retry cadence, search radius, backoff.
- Trace extraction: average multiple Saturdays (cut noise); PREFER recent ~1-2yr (courses change; mixing
  old+new blends two routes); smoothing/simplify.
- Relation way-chaining: gap-bridge + dedup for an accurate measured length.
- RESEARCHED LEVERS for the no-named-relation gaps (verified OSS tools; hand-code the deterministic core;
  ship provisional; calibrate thresholds vs the ~131 already mapped):
  - MAP-MATCH + EDGE VOTING (highest impact): the trackpoints API exposes EVERY trace's points regardless
    of privacy (incl. time-stripped/anonymised), so snap many nearby traces to the path graph
    (leuven.mapmatching / map-matching-2) and keep the most-traversed connected ~5k subgraph. Voting is
    NOT a library - count traces per edge yourself; need >=N corroborating traces (paths shared by
    commuters/dogs/cyclists - never trust one). Needs no relation.
  - PARK-BOUNDARY LOOP (works with zero traces): confine an osmnx walk graph to the event's OSM greenspace
    polygon (graph_from_polygon), find the ~5k closed loop via a fixed-length-cycle heuristic
    (Lewis-Corcoran). Guard against the wrong adjacent park.
  - N-LAP: generalise the fixed 2x to "smallest N (1..6) with N*lap in 4.8-5.2k" (the self-audit flags
    these); get N from real repetition in a trace, NEVER by multiplying until it hits 5k (false positive,
    forbidden).
  - DATA-DRIVEN START TIME: learn each event's start by clustering Saturday-morning trace starts instead
    of hardcoding 09:00 (recovers foreign events that don't start at 09:00).
  - TRIAGE + REPAIR (cheap glue): route each gap to the fitting lever; mark genuinely-no-data events final
    so they stop being re-swept; near-miss relations -> trim degree-1 spurs / bridge small gaps
    (osmnx+networkx), accept only if a trace agrees.
  Compose: park polygon confines edge-voting (fewer false edges); start/lap detection feeds all.
- QA flag: in-band but mis-shaped (self-intersections/spikes) -> flag for human, never silently rewrite.
- Event-age via events.json `id` (roughly chronological, Bushy=1): older events likelier to have OSM data
  -> prioritise low id, treat very-new high id as EXPECTED gaps. Noisy proxy (junior/overseas ids
  interleave), no network saving. Never fetch parkrun for true dates (invariant #6).
- Additional sources beyond OSM: other openly-licensed/permitted data (open GPS-trace, public-domain
  routes, gov/park open data), attributed, within their terms - ONLY within invariant #6 (never parkrun,
  never scraping, never circumventing). OSM stays primary; others additive.

## index.json = your log (read for per-event detail)
One entry per attempted parkrun: `status` (success|failed|gap|error); `distance_m` (null if gap);
`relation_m` + `trace_m` (what the OSM relation & 09:00 trace each measured, present even when unused -
your richest signal, esp. on `failed`); `source`; `provisional`; `trace_date`; `last_tried`; `lat`;
`lon`; `error` (message, on status=error crashes). `routes/<event>.gpx` = successes only (for the app;
rarely read geometry). FAILED entries are the gold: `relation_m`~2300 => one lap of a 2-lap (double);
`distance_m` just outside 4.8-5.2k => incomplete relation (way-chain). Off-distance geometry is NOT
stored (cost) - work from metadata (git history has older states). You usually get a compact outcomes
digest; read index.json directly only when you need per-event detail.

## JOURNAL.md (accumulate knowledge)
Bots' running diary. Author reads it then appends (date, idea, why-from-outcomes, what changed). Build on
what worked, don't repeat what didn't, get more creative over time. Reviewer reads it to spot churn. Bot:
append-only (never rewrite past entries — ENFORCED: the apply step rejects any edit that removes/rewrites
an existing entry, so you can't delete churn-memory to dodge a duplicate finding), dense ASCII (BIBLE #10);
the owner may periodically compact it losslessly. It is tail-loaded (capped) - density = more retained lessons per token.

## Process
1. Author (weekly): read JOURNAL + index.json outcomes + the algorithm -> propose ONE improvement within
   the invariants that genuinely advances the goal. Pruning wrong/obsolete logic counts; no pointless
   churn. Append a JOURNAL entry (or journal why nothing changed).
2. Reviewer (a different AI): judge on (a) SAFETY (invariants, bars, geometry, OSM-kindness, licensing)
   and (b) MERIT (real progress vs churn / re-tried failure). Aim for consensus - collaborator, not
   gatekeeper; don't block on style; loop until both satisfied (capped rounds).
3. Gate: `selftest.py` (frozen invariants) + `test_behavior.py` (editable expectations) MUST pass, else no merge.
4. `version_bump` by scope: patch=tweak/fix/prune, minor=real new capability or quality gain (usual),
   major=ambitious rework (rare). Merge auto-cuts a semver release.

## Models
Per-role chains in `.github/ai_model.json` (author / reviewer / fast), each frontier->fallback->anchor,
re-evaluated weekly from a multi-provider menu; a provider with no key is skipped. Reviewer must differ
from the author (independent) and stay deep (never the fast tier). Pick the smartest models that FIT the
free request limits (hard constraint; the same config runs on 2 repos -> need headroom for both).

## Learnings (bot-appended)
- Averaging multiple Saturday-09:00 traces improves closeness + coverage within invariants.
- Added Christmas Day + New Year's Day events (high-footfall -> valuable GPS).
