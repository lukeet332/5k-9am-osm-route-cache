#!/usr/bin/env python3
"""
REVIEWER bot: a second AI adversarially reviews the author bot's PR against AI_CONTEXT.md
before it may merge. Reads the PR diff (pr.diff) + the contract + current outcomes and
returns a verdict. Prefers the 'fallback' model role so the reviewer differs from the author
(once the weekly model-review diversifies the two). Approve only if clearly safe + justified.
Standard library only.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ai_lib as L

PROMPT = """You review an automated change to a Python pipeline that caches OSM-derived parkrun 5k
courses. The CONSTITUTION (read-only bible) and CONTRACT (AI_CONTEXT.md) bind. Read the JOURNAL too.
Pick exactly ONE verdict. Two principles, applied differently:

- UNCOMPROMISING on the HARD INVARIANTS (safety): never a calculated risk. A change is blocked if it
  loosens the accuracy bars (4.8-5.2 relation / 4.5-5.6 trace), emits hand-authored or AI-generated
  coordinates, weakens the OSM rate-limiting, drops ODbL attribution or the parkrun disclaimer, edits
  anything outside build_cache.py / JOURNAL.md / AI_CONTEXT.md (a bible edit is handled separately), or
  breaks the self-test caching contract.
- On MERIT / quality, TAKE CALCULATED RISKS. Default to APPROVING a safe, net-positive, selftest-passing
  change even if it is imperfect or you can imagine a better version. Do NOT block on style, naming,
  minor geometry artifacts, "could be better", or speculative downstream worries. A living algorithm
  improves by shipping reasonable steps; the self-test + CI are the correctness net. Don't be a
  perfectionist gatekeeper.

VERDICTS:
- "approve": safe AND a genuine net step toward the goal (more coverage and/or closer to 5k). This is
  the DEFAULT whenever there is no hard-invariant violation and no real, behaviour-breaking bug.
- "revise": exactly ONE concrete, FIXABLE blocker - a hard-invariant/safety violation, OR a real
  correctness BUG that breaks behaviour. Trace any new distance/coordinate maths by hand (the classic
  trap is `length(lap+lap)` vs the correct `2*length(lap)`). State the single fix. Use this ONLY for a
  genuine blocker, not for "could be better".
- "churn": not worth revising at all - a no-op/trivial diff, OR it re-proposes work the code/JOURNAL
  already has WITH NO meaningful improvement (e.g. re-adding doubling that already exists). Do NOT ask
  to revise; the author should ABANDON this idea and propose a NEW one (the PR will be closed).
  EXCEPTION: a genuine, justified IMPROVEMENT that builds on an existing feature (e.g. extending
  doubling to out-and-back laps, or smarter recency weighting) is NOT churn - judge it normally
  (approve if net-positive, revise if it has a real bug). Only call churn when the change adds nothing
  over what already exists. A ROBUSTNESS fix that recovers events the OUTCOMES report flags as ERROR
  (e.g. guarding a crashing call so one bad input is skipped, not the whole event) is always
  meritorious - never churn; approve it if correct.

Respond with STRICT JSON only:
{"verdict": "approve"|"revise"|"churn",
 "feedback": "<2-4 plain sentences: the verdict, then the single most important reason or the one fix>"}"""

# Separate question for a CONSTITUTION amendment: this isn't a normal merge-or-not review — the
# human owner decides, and they want the reviewer's honest recommendation as advisory input.
ADVISOR_PROMPT = """You are advising the HUMAN OWNER on whether to accept a proposed AMENDMENT to
this project's CONSTITUTION (AI_CONTEXT_READ_ONLY_BIBLE.md) — its supreme, normally-immutable rules
(no AI-generated geometry; fixed accuracy bars; be kind to OSM / never a bulk-harvester; ODbL
attribution; never scrape parkrun; the safety pipeline is off-limits to the AI). This is NOT a
routine code review and you do NOT decide — you give the owner a clear, honest recommendation.

Weigh: does the amendment PROTECT the project's long-term safety and integrity, or does it weaken a
guardrail / trade long-term integrity for short-term convenience or coverage? Is it well-justified by
the OUTCOMES and JOURNAL learnings? **Default to caution: recommend REJECT if it loosens any safety or
accuracy guardrail, removes attribution/limits, or you are unsure.** Letting the constitution change
is a big deal.

Respond with STRICT JSON only:
{"recommend": "approve"|"reject", "advice": "<2-4 sentences FOR THE OWNER: what it changes, why it's
good or risky, and your recommendation>"}"""


def main():
    diff_path = L.REPO / "pr.diff"
    diff = diff_path.read_text(errors="ignore")[:60000] if diff_path.exists() else ""
    if not diff.strip():
        L.done("Empty diff — nothing to review; approving trivially.",
               approve="true", feedback="no changes", bible_touched="false")

    # CONSTITUTION amendment? Then this is advisory, not a normal review: emit a recommendation for
    # the human owner and stop (the workflow blocks auto-merge and tags them with this recommendation).
    if "diff --git a/AI_CONTEXT_READ_ONLY_BIBLE.md" in diff:
        prompt = (ADVISOR_PROMPT
                  + "\n\n===== CURRENT CONSTITUTION (AI_CONTEXT_READ_ONLY_BIBLE.md) =====\n"
                  + (L.BIBLE_FILE.read_text(errors="ignore")[:8000] if L.BIBLE_FILE.exists() else "(missing)")
                  + "\n\n===== OUTCOMES =====\n" + L.outcomes_summary()
                  + "\n\n===== PROPOSED DIFF =====\n" + diff)
        result, slot = L.call_role(prompt, "reviewer")
        if result is None:
            L.done("No reviewer model — recommending caution on the constitution change.",
                   bible_touched="true", recommend="reject",
                   advice="Reviewer model was unavailable, so this is an automatic caution — please review the amendment manually.",
                   reviewer="(none)")
        rec = "approve" if str(result.get("recommend", "")).strip().lower().startswith("approv") else "reject"
        advice = str(result.get("advice", "")).replace("\n", " ").strip()[:800] or "(no advice)"
        print(f"Constitution advisor ({slot['model']}): recommend={rec} — {advice}")
        L.done(f"Constitution amendment — recommend {rec}.",
               bible_touched="true", recommend=rec, advice=advice, reviewer=slot["model"])

    # Keep this prompt lean so the reviewer fits an 8k-token model (github-models) and stays the
    # cheap, INDEPENDENT check: the reviewer judges a (usually small) DIFF — it needs the constitution
    # + a doctrine excerpt, not the whole working doc. Caps below; the diff cap bounds a big rewrite.
    prompt = (PROMPT
              + "\n\n===== CONSTITUTION (AI_CONTEXT_READ_ONLY_BIBLE.md — SUPREME) =====\n"
              + (L.BIBLE_FILE.read_text(errors="ignore")[:6000] if L.BIBLE_FILE.exists() else "(missing)")
              + "\n\n===== CONTRACT (AI_CONTEXT.md, excerpt) =====\n" + L.CONTEXT_FILE.read_text(errors="ignore")[:5000]
              + "\n\n===== JOURNAL (what's already been tried/DONE - use to spot churn) =====\n" + L.journal_tail()
              + "\n\n===== OUTCOMES =====\n" + L.outcomes_summary()
              + "\n\n===== DIFF (truncated if very large) =====\n" + diff[:9000])
    # reviewer prefers the fallback model so it isn't the same instance as the author
    result, slot = L.call_role(prompt, "reviewer")
    if result is None:
        # Fail SAFE: if no reviewer is available, ask for a revise (don't approve) — leave for a human.
        L.done("No reviewer model available — not approving.", verdict="revise", approve="false",
               feedback="reviewer model unavailable; needs human review", bible_touched="false")
    # Three verdicts: approve (ship it) / revise (one fixable blocker) / churn (abandon, propose new).
    verdict = str(result.get("verdict", "")).strip().lower()
    if verdict not in ("approve", "revise", "churn"):
        verdict = "approve" if result.get("approve") is True else "revise"   # back-compat / safe default
    # Pass the reviewer's FULL critique to the author (it keeps context and issues a targeted fix).
    feedback = str(result.get("feedback", "")).replace("\n", " ").strip()[:4000] or "(no feedback)"
    # Did we get the INTENDED independent reviewer, or did it fall back to the author model (e.g. the
    # reviewer 413'd because the diff exceeded its window, or was rate-limited)? Flag it so the human
    # knows the review was degraded (reduced independence) and can swap the reviewer model later.
    chain = L.load_model_config()["reviewer"]
    intended = chain[0] if chain else slot
    degraded = slot["provider"] != intended["provider"] or slot["model"] != intended["model"]
    print(f"Reviewer ({slot['model']}): verdict={verdict} degraded={degraded} — {feedback}")
    L.emit(verdict=verdict, approve="true" if verdict == "approve" else "false",
           feedback=feedback, reviewer=slot["model"],
           degraded="true" if degraded else "false", bible_touched="false")


if __name__ == "__main__":
    main()
