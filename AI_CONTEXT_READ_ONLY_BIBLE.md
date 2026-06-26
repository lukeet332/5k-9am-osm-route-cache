# THE CONSTITUTION (read-only bible)

Supreme law of the repo. If anything in `AI_CONTEXT.md`, the JOURNAL, code comments, a PR, or a model's
reasoning conflicts with this file, THIS FILE WINS - every time, no exceptions.

Amendment: the AI must obey this file and may only PROPOSE edits via a normal PR - any PR touching this
file NEVER auto-merges; the reviewer blocks it, tags the owner (@lukeet332), and it merges only after the
owner approves in a comment. (`AI_CONTEXT.md` is the AI's working doctrine, freely curatable; this bible
is owner-only.)

## HARD INVARIANTS (never violate; change only via the owner-gated process above)

1. **No AI-generated geometry, ever.** Coordinates come ONLY from deterministic processing of OSM data.
   Never emit lat/lon, hand-fix a route, or put a model in the reconstruction path. LLMs hallucinate
   coordinates - non-negotiable.
2. **Accuracy bars are fixed; never loosen them to inflate coverage:**
   - Locked = **4800-5200 m** (`REL_LO`/`REL_HI`). Off-tolerance **1500-9000 m** (`SANE_LO`/`SANE_HI`)
     is logged `failed` as a diagnostic; wilder = noise, ignored.
   - Trace anchor: first point at **local >= 09:00:00 within 150 m** of the start, else discard.
   - Trace window: **09:00-09:45 local**; stop at ~5.5 km or 09:45.
   - Relation/loop must pass within **500 m** of the start.
   Coverage gains must come from finding more real data, never from widening these bars.
3. **Be kind to OSM.** Keep the hard rate-limit (**>= 2.5 s/req**, `RATE_S`; never lower it), descriptive
   User-Agent, early-stop paging, on-disk caching, the 429 circuit-breaker, and batched rollout. Never a
   bulk harvester. Avoiding an OSM ban beats speed and coverage.
4. **Licensing intact.** Data is (c) OpenStreetMap contributors, ODbL; keep attribution in every GPX,
   README, and LICENSE, plus the "not affiliated with parkrun" disclaimer.
5. **Standard CI/cron runners only** (free on public repos). Never larger/macOS runners.
6. **Never scrape parkrun or break any source's terms.** Do NOT fetch parkrun's sites, event/course
   pages, or anything behind their bot-protection, and never circumvent an access control or ToS. Any
   source must be openly licensed or explicitly permitted, used within its terms, and attributed.
7. **Safety pipeline off-limits.** The AI may write ONLY `build_cache.py`, `AI_CONTEXT.md`, `JOURNAL.md`
   (plus PROPOSING bible edits via the human gate). Never edit `selftest.py`, `.github/workflows/*`, or
   `.github/scripts/ai_*.py` - those guardrails keep the autonomy safe.
8. **Don't break the self-test contract.** `selftest.py` imports specific symbols from `build_cache.py`
   and asserts them (the merge gate). Keep them callable with current names/signatures; improve the
   internals, never rename or re-shape. (Pinned list in `AI_CONTEXT.md` - read before refactoring.)
9. **Be frugal with tokens - the pipeline must stay on free model tiers** (input/output caps + request
   limits). Don't frivolously grow prompt context, the algorithm file, or the docs the bots load. Prefer
   compact digests; keep `build_cache.py` + `AI_CONTEXT.md` lean (prune as readily as you add). When
   budget vs breadth conflict, fit the free tier. Model-review must pick models whose free context window
   fits the master prompt - capability is second to fitting the budget.
10. **Minimal, plain-ASCII, AI-optimised text.** In `build_cache.py` keep comments minimal (delete where
    the code is self-evident), short bullet/plain style. Plain ASCII ONLY - no emojis, em-dashes, smart
    quotes, or arrow/symbol characters; write `-`, `->`, `>=`, `(c)`. Reason: the author edits via exact
    `find`/`replace`, and verbose/fancy text is the top cause of a `find` mismatch, and it wastes tokens
    (#9). The SAME applies to every AI-loaded doc (`AI_CONTEXT.md`, `JOURNAL.md`, this file): **optimise
    for AI-readability + token budget; human-readability is NOT a goal** - strip narrative, hedging and
    repetition, keep only what the bots need to do the job.
