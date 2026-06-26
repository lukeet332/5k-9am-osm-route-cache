#!/usr/bin/env python3
"""
Weekly model self-review (multi-source). Ask the current model which models are best TODAY for
three roles — MASTER author, SLAVE reviewer (a DIFFERENT source, for an independent check), and a
FAST delegate — choosing from the providers whose keys are actually present. Validate any change
with a live call, then rewrite .github/ai_model.json. A provider with no key is skipped, so this
never needs a secret it doesn't have and never breaks: any error / no warranted change ->
changed=false. Standard library only.
"""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ai_lib as L

ROLES = ("primary", "fallback", "fast")
PROMPT = """You configure THREE models for an automated maintenance bot on a Python repo that
caches OSM-derived running courses. Pick ONLY from these providers whose keys are configured
right now: %(avail)s.

- MASTER author ("primary", DEEP): the best free reasoning/code model for analysing data
  outcomes and carefully editing a Python algorithm.
- SLAVE reviewer ("fallback", DEEP + INDEPENDENT): the safety gate. A strong reasoning model
  from a DIFFERENT provider than the master where two or more providers are available, so the
  review is genuinely independent. It MUST stay deep — never a fast/small model.
- FAST ("fast"): a fast, cheap model (e.g. a Flash-class model) for simple delegated subtasks.

OBJECTIVE: pick the SMARTEST master + reviewer that STILL FIT within the free request limits —
maximise capability, with the free quota as a HARD constraint (not the other way round).

HARD CONSTRAINTS:
- Every model must be FREE (reject any paid model outright).
- TOKEN CAPACITY (critical): the MASTER author is sent the ENTIRE algorithm file PLUS its context in
  one prompt — currently about %(master_tokens)s input tokens, and GROWING as the algorithm evolves.
  Its free-tier INPUT limit must comfortably exceed that. NOTE: GitHub Models' free tier caps input at
  ~8000 tokens for ALL models — too small for the master; do NOT pick a github-models model as master.
  A big-context free model (e.g. Gemini Flash, ~1M tokens) fits. The reviewer only sees a small DIFF,
  so an 8000-token model is fine there — which makes github-models a good INDEPENDENT reviewer choice.
- This same configuration runs across TWO repositories that may, by chance, pick the SAME models —
  so each model's FREE request quota must comfortably cover BOTH repos' combined usage (a few
  automated calls per week each). Reject any model whose free tier is too tight for that.
- Master and reviewer should be from TWO DIFFERENT providers when >=2 are available.
- Among the models that satisfy the above, choose the two most capable (reasoning/code quality).

Current configuration: %(current)s

Respond with STRICT JSON only:
{"primary": {"provider": "...", "model": "..."},
 "fallback": {"provider": "...", "model": "..."},
 "fast": {"provider": "...", "model": "..."},
 "reason": "<one or two sentences>"}
Keep a role unchanged UNLESS a clearly better option exists."""


def stop(reason):
    L.done(reason, changed="false")


def available_providers():
    return [p for p, (_base, key_env) in L.PROVIDERS.items() if os.environ.get(key_env, "").strip()]


def main():
    avail = available_providers()
    cur = L.load_model_config()
    cur_short = {r: {"provider": cur[r]["provider"], "model": cur[r]["model"]} for r in ROLES}
    # Rough size of the master author's prompt (whole algorithm + context) so the selector can reject
    # models whose free-tier input window can't fit it.
    def _chars(f): return len(f.read_text(errors="ignore")) if f.exists() else 0
    master_tokens = (_chars(L.ALGO_FILE) + _chars(L.CONTEXT_FILE) + _chars(L.BIBLE_FILE) + 4000) // 4
    rec, _ = L.call_with_roles(
        PROMPT % {"avail": ", ".join(avail) or "github-models", "current": json.dumps(cur_short),
                  "master_tokens": f"~{master_tokens}"},
        roles=("primary", "fallback"),
    )
    if not isinstance(rec, dict):
        stop("No usable recommendation — keeping current models.")

    new = {}
    for role in ROLES:
        r = rec.get(role)
        if not isinstance(r, dict) or str(r.get("provider", "")) not in L.PROVIDERS or not str(r.get("model", "")).strip():
            stop(f"Recommendation for {role} invalid — keeping current.")
        new[role] = {"provider": r["provider"], "model": str(r["model"]).strip()}

    # master + reviewer must be two different sources when we actually have two to choose from
    if len(avail) >= 2 and new["primary"]["provider"] == new["fallback"]["provider"]:
        stop("Master and reviewer must be from two different sources (>=2 available) — keeping current.")

    changed = [r for r in ROLES if new[r] != cur_short[r]]
    if not changed:
        stop("All roles still optimal — no change.")

    for role in changed:                       # validate each change with a live call
        base_url, key_env = L.PROVIDERS[new[role]["provider"]]
        if not os.environ.get(key_env, "").strip():
            stop(f"{role} provider key ({key_env}) not configured — keeping current.")
        try:
            test = L.call_json({"base_url": base_url, "model": new[role]["model"], "api_key_env": key_env},
                               'Reply with the JSON {"ok": true} and nothing else.')
            assert isinstance(test, dict)
        except Exception as e:
            stop(f"Recommended {role} failed live validation ({e.__class__.__name__}) — keeping current.")

    L.MODEL_CONFIG.write_text(json.dumps({r: new[r] for r in ROLES}, indent=2) + "\n")
    L.emit(changed="true", changed_roles=" & ".join(changed),
           primary=f'{new["primary"]["provider"]}/{new["primary"]["model"]}',
           fallback=f'{new["fallback"]["provider"]}/{new["fallback"]["model"]}',
           reason=str(rec.get("reason", "")).replace("\n", " ").strip()[:400])


if __name__ == "__main__":
    main()
