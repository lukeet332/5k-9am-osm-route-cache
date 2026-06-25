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


def main():
    diff_path = L.REPO / "pr.diff"
    diff = diff_path.read_text(errors="ignore")[:60000] if diff_path.exists() else ""
    if not diff.strip():
        L.done("Empty diff — nothing to review; approving trivially.", approve="true", feedback="no changes")
    prompt = (PROMPT
              + "\n\n===== CONTRACT (AI_CONTEXT.md) =====\n" + L.CONTEXT_FILE.read_text(errors="ignore")[:14000]
              + "\n\n===== JOURNAL (past ideas + learnings) =====\n" + L.journal_tail()
              + "\n\n===== OUTCOMES =====\n" + L.outcomes_summary()
              + "\n\n===== DIFF =====\n" + diff)
    # reviewer prefers the fallback model so it isn't the same instance as the author
    result, slot = L.call_with_roles(prompt, roles=("fallback", "primary"))
    if result is None:
        # Fail SAFE: if no reviewer is available, do NOT approve — leave for a human.
        L.done("No reviewer model available — not approving.", approve="false",
               feedback="reviewer model unavailable; needs human review")
    approve = bool(result.get("approve"))
    feedback = str(result.get("feedback", "")).replace("\n", " ").strip()[:600] or "(no feedback)"
    print(f"Reviewer ({slot['model']}): approve={approve} — {feedback}")
    L.emit(approve="true" if approve else "false", feedback=feedback, reviewer=slot["model"])


if __name__ == "__main__":
    main()
