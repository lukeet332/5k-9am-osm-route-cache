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

PROMPT = """You configure TWO GitHub Models models for an automated maintenance bot on a Python
repo that caches OSM-derived running courses:
- AUTHOR ("primary", deep thinking): the best free reasoning/code model on GitHub Models for
  analysing data outcomes and editing a Python algorithm carefully.
- REVIEWER ("fallback"): a capable but ideally DIFFERENT free GitHub Models model, used to
  adversarially review the author's change independently.

HARD CONSTRAINTS: both must be available on **GitHub Models** (provider "github-models") and free
via GITHUB_TOKEN, with enough headroom for ~2 calls/week. Prefer a reasoning-class model for the
author. Make the reviewer a different model from the author where a good option exists.

Current configuration: %(current)s

Respond with STRICT JSON only:
{"primary": {"provider": "github-models", "model": "<exact GitHub Models id>"},
 "fallback": {"provider": "github-models", "model": "<exact GitHub Models id>"},
 "reason": "<one or two sentences>"}
Keep a role unchanged UNLESS a clearly better option exists."""


def stop(reason):
    L.done(reason, changed="false")


def main():
    cur = L.load_model_config()
    cur_short = {r: {"provider": cur[r]["provider"], "model": cur[r]["model"]} for r in ("primary", "fallback")}
    rec, _ = L.call_with_roles(PROMPT % {"current": json.dumps(cur_short)}, roles=("primary", "fallback"))
    if not isinstance(rec, dict):
        stop("No usable recommendation — keeping current models.")

    new = {}
    for role in ("primary", "fallback"):
        r = rec.get(role)
        if not isinstance(r, dict) or str(r.get("provider", "")) not in L.PROVIDERS or not str(r.get("model", "")).strip():
            stop(f"Recommendation for {role} invalid — keeping current.")
        new[role] = {"provider": r["provider"], "model": str(r["model"]).strip()}

    changed = [r for r in ("primary", "fallback") if new[r] != cur_short[r]]
    if not changed:
        stop("Both roles still optimal — no change.")

    for role in changed:                       # validate each change with a live call
        base_url, key_env = L.PROVIDERS[new[role]["provider"]]
        try:
            test = L.call_json({"base_url": base_url, "model": new[role]["model"], "api_key_env": key_env},
                               'Reply with the JSON {"ok": true} and nothing else.')
            assert isinstance(test, dict)
        except Exception as e:
            stop(f"Recommended {role} failed live validation ({e.__class__.__name__}) — keeping current.")

    L.MODEL_CONFIG.write_text(json.dumps({"primary": new["primary"], "fallback": new["fallback"]}, indent=2) + "\n")
    L.emit(changed="true", changed_roles=" & ".join(changed),
           primary=f'{new["primary"]["provider"]}/{new["primary"]["model"]}',
           fallback=f'{new["fallback"]["provider"]}/{new["fallback"]["model"]}',
           reason=str(rec.get("reason", "")).replace("\n", " ").strip()[:400])


if __name__ == "__main__":
    main()
