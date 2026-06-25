#!/usr/bin/env python3
"""
Weekly AUTHOR bot: look at the current cache outcomes + the algorithm, and propose ONE
focused improvement to build_cache.py (or an append to AI_CONTEXT.md) that raises the dual
truth metric — coverage AND closeness-to-5k — strictly within the AI_CONTEXT invariants.

It edits the deterministic ALGORITHM only; it never emits coordinates itself. The change
must then pass selftest.py (workflow gate), a second AI review, and CI before it can merge.
Standard library only; writes are allow-listed + path-guarded in ai_lib.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ai_lib as L

PROMPT = """You maintain a Python pipeline that caches UK parkrun 5k courses as GPX, derived
ONLY from OpenStreetMap (route relations + open Saturday-09:00 GPS traces). Read the CONTRACT
(AI_CONTEXT.md) first — it is binding. Then, using the OUTCOMES and the current ALGORITHM, decide
if there is ONE worthwhile improvement to the deterministic algorithm that would raise the dual
truth metric (coverage AND closeness-to-5k) WITHOUT violating any hard invariant.

You edit the deterministic code only — you NEVER output coordinates or hand-draw routes; the code
computes geometry from OSM. You must NOT loosen the accuracy bars (4.8-5.2 relation / 4.5-5.6 trace),
weaken the OSM rate-limiting, or remove licensing/attribution. Good kinds of change: querying more
historical Saturdays or the high-footfall Christmas/New-Year dates (note: not always Saturdays — use
each event's local time), averaging multiple traces to cut GPS noise, smarter multi-lap detection or
way-chaining, better rollout/rotation. Make the SMALLEST change that is clearly justified by the
OUTCOMES. If nothing is clearly worth changing, return an empty "changes" array.

Respond with STRICT JSON only:
{"summary": "<one line>", "changes": [{"path": "build_cache.py", "content": "<COMPLETE new file>"}]}
"content" must be the entire file, not a diff. You may also append (never rewrite) a one-line
durable learning under AI_CONTEXT.md's "## Learnings (appended by the bot)" section by returning the
full AI_CONTEXT.md with your bullet added. Only touch build_cache.py and/or AI_CONTEXT.md."""


def main():
    cfg = L.load_model_config()
    if not any(os.environ.get(cfg[r]["api_key_env"], "").strip() for r in ("primary", "fallback")):
        L.done("No model credentials — skipping (no changes).")
    prompt = (PROMPT
              + "\n\n===== CONTRACT (AI_CONTEXT.md) =====\n" + L.CONTEXT_FILE.read_text(errors="ignore")[:14000]
              + "\n\n===== OUTCOMES =====\n" + L.outcomes_summary()
              + "\n\n===== ALGORITHM (build_cache.py) =====\n" + L.ALGO_FILE.read_text(errors="ignore"))
    fb = os.environ.get("REVIEW_FEEDBACK", "").strip()
    if fb:   # revision round: the reviewer rejected the previous attempt
        prompt += "\n\n===== REVIEWER FEEDBACK ON YOUR PREVIOUS ATTEMPT (address it) =====\n" + fb[:2000]
    result, slot = L.call_with_roles(prompt)
    if result is None:
        L.done("No model available — skipping (no changes).")
    print("Proposal:", result.get("summary", "(none)"))
    n = L.apply_changes(result)
    label = L.bot_label(slot["model"])
    L.emit(model_used=slot["model"], bot_label=label, summary=str(result.get("summary", ""))[:300])
    L.done(f"Applied {n} change(s) from {label}.")


if __name__ == "__main__":
    main()
