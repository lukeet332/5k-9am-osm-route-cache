#!/usr/bin/env python3
"""
Weekly AUTHOR bot: look at the current cache outcomes + the algorithm, and propose ONE
focused improvement to build_cache.py (or an append to AI_CONTEXT.md) that raises the dual
truth metric — coverage AND closeness-to-5k — strictly within the AI_CONTEXT invariants.

It edits the deterministic ALGORITHM only; it never emits coordinates itself. The change
must then pass selftest.py (workflow gate), a second AI review, and CI before it can merge.
Standard library only; writes are allow-listed + path-guarded in ai_lib.
"""
import os, sys, json, urllib.request, urllib.error
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ai_lib as L

# ---- PR-thread access (the author keeps context across revision rounds; the reviewer stays
#      stateless + independent). The branch files + the live diff ARE the author's prior work, and
#      the PR comments ARE the critique history — so no new persisted state is needed. All best-effort:
#      on the first author run (no PR yet) or the self-test retry (no PR), these no-op gracefully. ----
def _gh_api(method, path, body=None):
    tok = (os.environ.get("GH_TOKEN") or os.environ.get("GH_MODELS_TOKEN")
           or os.environ.get("BOT_PAT") or "").strip()
    repo = os.environ.get("GITHUB_REPOSITORY", "").strip()
    if not (tok and repo):
        return None
    req = urllib.request.Request(
        f"https://api.github.com/repos/{repo}{path}",
        data=(json.dumps(body).encode() if body is not None else None),
        headers={"Authorization": f"Bearer {tok}", "Accept": "application/vnd.github+json",
                 "User-Agent": "5k-9am-osm-route-cache author bot"},
        method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read() or "null")
    except Exception as e:
        print(f"(gh api {method} {path} unavailable: {e.__class__.__name__})")
        return None

def _pr_diff():
    """The author's change SO FAR vs main — built by the review job before it calls us back."""
    p = L.REPO / "pr.diff"
    return p.read_text(errors="ignore") if p.exists() else ""

def _pr_conversation():
    """The review debate so far, oldest first: reviewer/arbiter issue-comments AND CodeRabbit's
    line-anchored INLINE review comments — so the author sees EXACTLY what was flagged and on which
    line (it used to see only issue-comments, missing CodeRabbit's specific objections, so it fixed
    the wrong thing). Inline bodies are capped to their headline (the objection sits at the top)."""
    pr = os.environ.get("PR", "").strip()
    if not pr:
        return ""
    items = []
    for c in (_gh_api("GET", f"/issues/{pr}/comments") or []):
        items.append((c.get("created_at", ""), (c.get("user") or {}).get("login", "?"), "",
                      (c.get("body") or "").strip()))
    for c in (_gh_api("GET", f"/pulls/{pr}/comments") or []):   # CodeRabbit's line-level objections
        loc = f' [{c.get("path", "?")}:{c.get("line") or c.get("original_line") or "?"}]'
        items.append((c.get("created_at", ""), (c.get("user") or {}).get("login", "?"), loc,
                      (c.get("body") or "").strip()[:700]))
    items.sort(key=lambda x: x[0])
    return "\n\n".join(f"--- {who}{loc} ---\n{body}" for _, who, loc, body in items if body)

def _post_reply(summary, why=""):
    """The author speaks in the PR thread: what it changed in response + WHY. Builds the conversation
    for the next round and makes the whole debate auditable by the human owner."""
    pr = os.environ.get("PR", "").strip()
    if not pr:
        return
    body = "🤖 **Author revised** — targeted fix, kept the prior approach:\n\n> " + summary
    if why:
        body += "\n\n**Why / how:**\n" + why
    _gh_api("POST", f"/issues/{pr}/comments", {"body": body})

PROMPT = """You maintain a Python pipeline that caches UK parkrun 5k courses as GPX, derived ONLY
from OpenStreetMap. The CONSTITUTION (AI_CONTEXT_READ_ONLY_BIBLE.md) is the SUPREME LAW — read it
first and obey it absolutely; it overrides everything else. You may NOT freely edit it: you may only
*propose* an amendment, and such a PR requires the human owner's approval and never auto-merges, so
do that rarely and only with strong justification. Then read the CONTRACT (AI_CONTEXT.md) — your
working doctrine, which you MAY curate (add/remove) within the constitution's bounds — then the
JOURNAL (your past ideas + learnings), the OUTCOMES, and the current ALGORITHM. Propose ONE worthwhile improvement to
the deterministic algorithm that genuinely moves us toward the goal — caching ALL parkruns at ~5k —
by raising the dual truth metric (coverage AND closeness-to-5k), WITHOUT violating any hard invariant.

BUILD ON THE JOURNAL: don't repeat an idea already tried (especially one that didn't help); build on
what worked; get progressively more creative week over week. Improving an algorithm includes PRUNING
— you may remove or simplify logic you judge incorrect, obsolete, or unhelpful, not only add. But
avoid churn: every addition OR removal must plausibly advance the goal; no cosmetic/pointless edits.

You edit the deterministic code only — NEVER output coordinates or hand-draw routes; the code computes
geometry from OSM. Do NOT loosen the accuracy bars (4.8-5.2 relation / 4.5-5.6 trace), weaken the OSM
rate-limiting, or remove licensing/attribution. If nothing is clearly worth changing this week, return
an empty "edits" array.

PRIORITISE ERRORS: if the OUTCOMES report shows ERRORS (events crashing mid-build), they are
suppressing coverage RIGHT NOW - fixing the crash (e.g. guard the failing call so one bad input skips
that ITEM, not the whole event) takes priority over any new idea. A robustness fix that recovers
erroring events is always worthwhile and is NEVER churn.

OUTPUT A SMALL CHANGESET — never whole files. Respond with STRICT JSON only:
{"summary": "<one line>", "why": "<2-5 short plain-ASCII bullet lines>", "version_bump": "patch|minor|major",
 "edits": [{"path": "build_cache.py", "find": "<exact existing snippet>", "replace": "<new snippet>"}]}
"why" becomes the PR description for the reviewers + owner: 2-5 SHORT plain-ASCII bullet lines explaining
your DECISION - the signal/outcome that motivated it, the mechanism, the expected effect, and how it
stays within the invariants. Be concrete and decision-explaining, no fluff (one-off per PR, so this is
NOT reloaded context - a few extra lines here is fine and aids review).
Each edit's "find" MUST be copied VERBATIM — character-for-character, including exact indentation and
comments — from the CURRENT build_cache.py shown below, and must match EXACTLY ONCE in the file. If a
"find" isn't unique or doesn't match, the edit is rejected and your WHOLE change is dropped — so keep
each "find" minimal but include enough surrounding lines to be unambiguous. "replace" is the new text
for that snippet. You may give several edits; keep them tight, correct, and self-consistent.
COMMENT STYLE (constitution #10): keep any comments you write MINIMAL and plain-ASCII - no emojis,
em-dashes, smart quotes or arrows (use -, ->, >=, (c)). Verbose, fancy-punctuation comments are the
top cause of a later `find` failing to match, and they bloat the prompt. Prefer deleting a comment to
adding one.
"version_bump" classifies THIS change by SCOPE/AMBITION:
  - "patch": a small tweak, bugfix, threshold nudge, prune, or refactor.
  - "minor": a meaningful new capability or real coverage/accuracy gain (the usual case).
  - "major": an ambitious, substantial rework. Use sparingly.
If "edits" is empty, use "patch".
You normally edit ONLY build_cache.py. You MAY also curate AI_CONTEXT.md with the same find/replace
edits. If your change legitimately alters a BEHAVIOURAL expectation (e.g. a specific best_lap_n output,
the doubled distance/source label, the exact audit set), you MAY also edit test_behavior.py in the SAME
changeset to update that expectation — but ONLY the expectation that genuinely changed, NEVER to weaken
or remove a check. You do NOT need to touch JOURNAL.md — the pipeline records a journal entry from your
"summary" automatically. JOURNAL.md is APPEND-ONLY: you may ADD an entry but must NEVER remove or rewrite
an existing one (it is the immutable churn-detection record — the apply step rejects any removal, and
deleting an entry to dodge a churn/duplicate finding is forbidden; fix the CHANGE, not the memory). NEVER edit selftest.py (the FROZEN invariants / safety net — bars, source-trust,
no-abort, best_lap_n property) or anything under .github/ (the safety pipeline); a change that can only
pass by editing selftest.py is breaking an invariant, not improving. You MAY propose a constitution
(AI_CONTEXT_READ_ONLY_BIBLE.md) amendment as an edit, but only rarely + with strong justification,
knowing it will NOT auto-merge (it needs the human owner's explicit approval)."""

# Revision rounds REUSE the author's own context instead of starting over. The reviewer rejected (or
# the self-test failed); the working-tree files shown above ARE the author's previous attempt, and the
# diff + conversation below are its prior work and the critique. The author makes the SMALLEST fix that
# resolves the objection — it does NOT re-derive from scratch, switch ideas, or reopen settled parts.
REVISION_PROMPT = """=== THIS IS A REVISION ROUND — NOT A NEW PROPOSAL ===
The ALGORITHM and files shown above are YOUR OWN previous attempt (already in the working tree), not
the baseline. A reviewer or the self-test gate found a problem with it. Revise, don't restart:
- Keep your previous APPROACH and make the SMALLEST change that fully resolves the feedback's ROOT
  cause. Do NOT rewrite from scratch and do NOT switch to a different idea.
- Leave every part the feedback did NOT object to byte-for-byte identical (no incidental churn).
- Add NO unrelated edits — only the edit(s) that fix the objection.
Return a corrected CHANGESET ("edits") in the same JSON shape; each "find" must still match the current
build_cache.py verbatim and exactly once."""


def main():
    cfg = L.load_model_config()
    if not any(os.environ.get(s["api_key_env"], "").strip() for s in cfg["author"]):
        L.done("No author model credentials — skipping (no changes).")
    prompt = (PROMPT
              + "\n\n===== CONSTITUTION (AI_CONTEXT_READ_ONLY_BIBLE.md — SUPREME, obey absolutely) =====\n"
              + (L.BIBLE_FILE.read_text(errors="ignore")[:8000] if L.BIBLE_FILE.exists() else "(missing)")
              + "\n\n===== CONTRACT (AI_CONTEXT.md) =====\n" + L.CONTEXT_FILE.read_text(errors="ignore")[:14000]
              + "\n\n===== JOURNAL (past ideas + learnings) =====\n" + L.journal_tail()
              + "\n\n===== OUTCOMES =====\n" + L.outcomes_summary()
              + "\n\n===== ALGORITHM (build_cache.py) =====\n" + L.ALGO_FILE.read_text(errors="ignore"))
    fb = os.environ.get("REVIEW_FEEDBACK", "").strip()
    revising = bool(fb)
    if revising:   # revision round: a reviewer (or the self-test gate) rejected the previous attempt.
        prompt += "\n\n" + REVISION_PROMPT
        diff = _pr_diff()
        if diff:
            prompt += ("\n\n===== YOUR CHANGE SO FAR (diff vs main — this IS your prior work) =====\n"
                       + diff[:12000])
        convo = _pr_conversation()
        if convo:
            prompt += "\n\n===== REVIEW CONVERSATION SO FAR (oldest first) =====\n" + convo[-9000:]
        prompt += "\n\n===== REVIEWER'S LATEST FEEDBACK (resolve its root cause) =====\n" + fb[:6000]
    result, slot = L.call_role(prompt, "author")
    if result is None:
        L.done("No author model available — skipping (no changes).")
    print("Proposal:", result.get("summary", "(none)"))
    n = L.apply_proposal(result)
    why = str(result.get("why", "")).strip()[:1200]
    if revising and n:
        _post_reply(str(result.get("summary", "")).strip()[:600] or "(see diff)", why)
    label = L.bot_label(slot["model"])
    bump = str(result.get("version_bump", "patch")).strip().lower()
    if bump not in ("patch", "minor", "major"):
        bump = "patch"
    L.emit(model_used=slot["model"], bot_label=label, version_bump=bump,
           summary=str(result.get("summary", ""))[:300], why=(why or "(no rationale given)"))
    L.done(f"Applied {n} change(s) from {label} [{bump}].")


if __name__ == "__main__":
    main()
