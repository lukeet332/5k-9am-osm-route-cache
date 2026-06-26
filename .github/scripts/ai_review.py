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

PROMPT = """You are a STRICT, adversarial reviewer of an automated change to a Python pipeline
that caches OSM-derived parkrun 5k courses. The CONTRACT (AI_CONTEXT.md) is binding. Another AI
proposed the DIFF below. Your job is to catch anything that should not merge.

Judge it on TWO axes, then decide:

1) SAFETY / CORRECTNESS — REJECT if it: violates a hard invariant; loosens the accuracy bars
   (4.8-5.2 relation / 4.5-5.6 trace) to inflate coverage; makes the code emit hand-authored
   coordinates or hard-coded routes; weakens the OSM rate-limiting; removes ODbL attribution / the
   parkrun disclaimer; edits anything outside build_cache.py / JOURNAL.md / an AI_CONTEXT.md append;
   or risks breaking the caching mechanism.
2) MERIT — this is an ALGORITHM, so judge whether the change genuinely moves us toward the goal of
   caching ALL parkruns at ~5k (better coverage AND/OR closeness-to-5k). REJECT pointless churn:
   logic added or removed that doesn't plausibly help, or re-trying an idea the JOURNAL shows already
   failed. A good change is a real, sensible step — ideally building on the journal's learnings.

APPROVE (approve=true) when it is safe AND a genuine net step toward the goal. Aim for CONSENSUS —
you are a collaborator, not a perfectionist gatekeeper: don't block on style, naming, or "could be
even better"; once your concerns are addressed, APPROVE; don't invent new objections each round. CI
+ the self-test are the correctness net. Keep feedback to the ONE or TWO blocking issues, specific
and actionable.

Respond with STRICT JSON only:
{"approve": true|false, "feedback": "<concise: the blocking issue(s) to fix, or why it's approved>"}"""

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
        result, slot = L.call_with_roles(prompt, roles=("fallback", "primary"))
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

    prompt = (PROMPT
              + "\n\n===== CONSTITUTION (AI_CONTEXT_READ_ONLY_BIBLE.md — SUPREME) =====\n"
              + (L.BIBLE_FILE.read_text(errors="ignore")[:8000] if L.BIBLE_FILE.exists() else "(missing)")
              + "\n\n===== CONTRACT (AI_CONTEXT.md) =====\n" + L.CONTEXT_FILE.read_text(errors="ignore")[:14000]
              + "\n\n===== JOURNAL (past ideas + learnings) =====\n" + L.journal_tail()
              + "\n\n===== OUTCOMES =====\n" + L.outcomes_summary()
              + "\n\n===== DIFF =====\n" + diff)
    # reviewer prefers the fallback model so it isn't the same instance as the author
    result, slot = L.call_with_roles(prompt, roles=("fallback", "primary"))
    if result is None:
        # Fail SAFE: if no reviewer is available, do NOT approve — leave for a human.
        L.done("No reviewer model available — not approving.", approve="false",
               feedback="reviewer model unavailable; needs human review", bible_touched="false")
    approve = bool(result.get("approve"))
    feedback = str(result.get("feedback", "")).replace("\n", " ").strip()[:600] or "(no feedback)"
    print(f"Reviewer ({slot['model']}): approve={approve} — {feedback}")
    L.emit(approve="true" if approve else "false", feedback=feedback, reviewer=slot["model"], bible_touched="false")


if __name__ == "__main__":
    main()
