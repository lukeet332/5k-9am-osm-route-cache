#!/usr/bin/env python3
"""
Weekly model self-review (GitHub Models only). Ask the current model which GitHub Models
models are best TODAY for the two roles — AUTHOR (deep-thinking, for analysing a data
pipeline) and REVIEWER (a DIFFERENT model, for an independent adversarial check). Validate
any proposed change with a live call, then rewrite .github/ai_model.json. Because everything
runs on the same GITHUB_TOKEN, switching models never needs a new secret. Never breaks:
any error / no warranted change -> changed=false. Standard library only.
"""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ai_lib as L

ROLES = ("primary", "fallback", "fast")
PROMPT = """You configure THREE models for an automated maintenance bot on a Python repo that
caches OSM-derived running courses. Providers available: "github-models" (free via GITHUB_TOKEN)
and "gemini" (free, needs a key).
- AUTHOR ("primary", DEEP): best free reasoning/code model for analysing data outcomes and
  editing a Python algorithm carefully. Prefer "github-models" (no secret needed).
- REVIEWER ("fallback", DEEP + INDEPENDENT): the safety gate — must be a strong reasoning model,
  ideally a DIFFERENT family/provider from the author for a genuinely independent review (e.g. a
  Gemini Pro tier). It MUST stay deep — NEVER a fast/small model here.
- FAST ("fast"): a fast, cheap model (e.g. Gemini Flash) for simple delegated subtasks only.

HARD CONSTRAINTS: every model must be free with headroom for a few calls/week. Keep the reviewer
deep and independent. Keep a role unchanged UNLESS a clearly better option exists.

Current configuration: %(current)s

Respond with STRICT JSON only:
{"primary": {"provider": "...", "model": "..."},
 "fallback": {"provider": "...", "model": "..."},
 "fast": {"provider": "...", "model": "..."},
 "reason": "<one or two sentences>"}"""


def stop(reason):
    L.done(reason, changed="false")


def main():
    cur = L.load_model_config()
    cur_short = {r: {"provider": cur[r]["provider"], "model": cur[r]["model"]} for r in ROLES}
    rec, _ = L.call_with_roles(PROMPT % {"current": json.dumps(cur_short)}, roles=("primary", "fallback"))
    if not isinstance(rec, dict):
        stop("No usable recommendation — keeping current models.")

    new = {}
    for role in ROLES:
        r = rec.get(role)
        if not isinstance(r, dict) or str(r.get("provider", "")) not in L.PROVIDERS or not str(r.get("model", "")).strip():
            stop(f"Recommendation for {role} invalid — keeping current.")
        new[role] = {"provider": r["provider"], "model": str(r["model"]).strip()}

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
