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

PROMPT = """You are the MERGE ARBITER for an automated change to a Python pipeline that caches
OSM-derived parkrun 5k courses. A dedicated code-review bot (CodeRabbit) has ALREADY reviewed this PR
for code quality, correctness, and churn - its verdict + summary are provided below and are the SOURCE
OF TRUTH on code quality. Do NOT re-do line-by-line code critique or duplicate its findings.

Decide whether this PR should MERGE, using CodeRabbit's verdict PLUS the factors it does not own. The
CONSTITUTION (read-only bible) and CONTRACT (AI_CONTEXT.md) bind; read the JOURNAL too. Pick ONE verdict:

- "revise": pick this if CodeRabbit's state is CHANGES_REQUESTED for a fixable CODE issue AND the change
  is otherwise worth keeping - it is blocking, so the author must address its comments. ALSO pick revise
  if YOU spot a hard-invariant / safety violation (loosened accuracy bars 4.8-5.2 / 4.5-5.6, AI- or
  hand-authored coordinates, weakened OSM rate-limiting, dropped ODbL / parkrun attribution, edits outside
  build_cache.py / JOURNAL.md / AI_CONTEXT.md / test_behavior.py, ANY edit to selftest.py - the frozen
  invariants/safety net - a test_behavior.py edit that WEAKENS/DELETES a check rather than updating a
  behavioural expectation a real code change altered, or a JOURNAL.md diff that REMOVES/REWRITES an existing
  entry - JOURNAL is APPEND-ONLY churn memory, and deleting an entry to dodge a churn/duplicate finding is
  gaming: treat it as a violation and keep the churn finding - broken self-test contract) - you are the
  safety backstop even if CodeRabbit missed it. State the one blocker. Do NOT use revise for a churn PR (see churn).
  CRITICAL - lean toward AGREEMENT, not a stalled loop: if CodeRabbit's state is NOT CHANGES_REQUESTED
  (approved/commented), you may ONLY revise for a HARD-INVARIANT/safety violation from the list above. A
  functional/correctness/quality concern that CodeRabbit chose NOT to block on is NOT grounds to revise -
  CodeRabbit + the self-test + CI are the correctness net, so APPROVE and let them catch it. Re-blocking a
  PR that CodeRabbit already cleared just deadlocks the loop.
- "churn": the change re-proposes a JOURNAL "ALREADY IMPLEMENTED" idea with no meaningful improvement, or
  is a no-op -> the author should ABANDON it and propose a NEW idea (the PR is CLOSED). Churn takes
  PRECEDENCE: if the change is churn, return churn even if CodeRabbit requested changes - a dead idea is
  closed, not revised. A justified improvement that BUILDS ON a done idea is NOT churn; a robustness fix
  recovering ERROR events is NOT churn.
- "approve": CodeRabbit is NOT blocking (state approved/commented), the change is novel (not churn),
  within the invariants, and a genuine net step toward the goal. This is the default when nothing blocks.

Defer code quality + style to CodeRabbit - do NOT block on "could be better"; CodeRabbit + the self-test
+ CI are the correctness net. Your value-add is the MERGE call: honour CodeRabbit's verdict, guard the
hard invariants as a backstop, and judge churn / novelty.

Respond with STRICT JSON only:
{"verdict": "approve"|"revise"|"churn",
 "feedback": "<2-4 plain sentences: the verdict + the key reason (cite CodeRabbit if it is the blocker)>"}"""

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
    # CodeRabbit's verdict on THIS PR (set by the workflow's crgate step): state + its summary. This is
    # the source of truth on code quality + churn that the arbiter honours.
    cr_state = (os.environ.get("CODERABBIT_STATE", "").strip() or "none")
    cr_source = (os.environ.get("CODERABBIT_SOURCE", "").strip() or "none")
    crf = L.REPO / "coderabbit_review.txt"
    cr_summary = crf.read_text(errors="ignore").strip()[:4000] if crf.exists() else ""
    cr_kind = ("Walkthrough below = PR explanation for novelty/churn; not for line critique."
               if cr_source == "walkthrough"
               else "Review summary below (walkthrough unavailable); judge novelty on the diff + JOURNAL.")
    # author's stated intent, normalised to a compact plain-ASCII claim (BIBLE: AI-loaded text stays frugal)
    pr_body = " ".join((os.environ.get("PR_BODY", "") or "").split()).encode("ascii", "ignore").decode()[:2000]
    prompt = (PROMPT
              + "\n\n===== CONSTITUTION (AI_CONTEXT_READ_ONLY_BIBLE.md — SUPREME) =====\n"
              + (L.BIBLE_FILE.read_text(errors="ignore")[:6000] if L.BIBLE_FILE.exists() else "(missing)")
              + "\n\n===== CONTRACT (AI_CONTEXT.md, excerpt) =====\n" + L.CONTEXT_FILE.read_text(errors="ignore")[:5000]
              + "\n\n===== JOURNAL (what's already been tried/DONE - use to spot churn) =====\n" + L.journal_tail()
              + "\n\n===== OUTCOMES =====\n" + L.outcomes_summary()
              + "\n\n===== AUTHOR'S PR DESCRIPTION (its stated intent/why - a CLAIM; verify vs diff + JOURNAL) =====\n"
              + (pr_body or "(author gave no description)")
              + "\n\n===== CODERABBIT VERDICT (source of truth on code quality + churn) =====\n"
              + f"state: {cr_state} (CHANGES_REQUESTED = blocking). {cr_kind}\n"
              + (cr_summary or "(no CodeRabbit notes available - judge on the diff + invariants)")
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
