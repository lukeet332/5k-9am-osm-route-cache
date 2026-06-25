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

REJECT (approve=false) if the diff does ANY of:
- violates a hard invariant, or loosens the accuracy bars (4.8-5.2 relation / 4.5-5.6 trace) to
  inflate coverage;
- makes the AI/code emit hand-authored coordinates or hard-coded routes;
- weakens the OSM rate-limiting / politeness, or removes ODbL attribution / the parkrun disclaimer;
- edits anything outside build_cache.py / an AI_CONTEXT.md append, or touches selftest/workflows;
- isn't clearly justified by the OUTCOMES, or risks breaking the caching mechanism.
APPROVE (approve=true) only if it is clearly safe AND a genuine improvement to the dual truth
metric (coverage AND closeness-to-5k) within the invariants.

Respond with STRICT JSON only:
{"approve": true|false, "feedback": "<concise, specific, actionable — what to fix if rejected>"}"""


def main():
    diff_path = L.REPO / "pr.diff"
    diff = diff_path.read_text(errors="ignore")[:60000] if diff_path.exists() else ""
    if not diff.strip():
        L.done("Empty diff — nothing to review; approving trivially.", approve="true", feedback="no changes")
    prompt = (PROMPT
              + "\n\n===== CONTRACT (AI_CONTEXT.md) =====\n" + L.CONTEXT_FILE.read_text(errors="ignore")[:14000]
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
