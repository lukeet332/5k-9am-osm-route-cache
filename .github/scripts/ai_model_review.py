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

- MASTER author ("primary"): edits the whole algorithm — it is sent the ENTIRE algorithm file PLUS
  its context in one prompt, so it is CONTEXT-BOUND. Pick the SMARTEST free code/reasoning model whose
  free INPUT window comfortably fits that prompt with room to grow (see TOKEN CAPACITY). Capability is
  maximised AMONG models that fit — fitting the budget is the hard gate.
- SLAVE reviewer ("fallback"): the safety gate + critic; it also runs THIS selection. It reviews the
  author's DIFF (only the CHANGED lines — on a ~5k-token algorithm a real change is small, so an 8k
  window is almost always enough) and reads the model menu. Pick the DEEPEST, smartest free reasoning
  model from a DIFFERENT provider than the master for an independent check; an 8k model (e.g.
  github-models gpt-4.1) is perfectly fine — a bigger window is a mild plus, NOT a requirement. (If a
  diff ever exceeds the reviewer's window the pipeline flags it to the human instead of failing
  silently, so don't over-optimise for context size — favour reasoning quality + reliability.)
- FAST ("fast"): a fast, cheap model (Flash-class) for trivial delegated subtasks only.

OBJECTIVE: pick the SMARTEST master + reviewer that STILL FIT within the free request limits —
maximise capability, with the free quota as a HARD constraint (not the other way round).

HARD CONSTRAINTS:
- Every model must be FREE (reject any paid model outright).
- TOKEN CAPACITY (applies to the MASTER only): the master prompt (whole algorithm + context) is
  MEASURED at ~%(master_tokens)s input tokens right now and GROWS over time. The master's free-tier
  INPUT limit must be at least ~2x that, for growth headroom. GitHub Models' free tier caps input at
  ~8000 tokens for EVERY model — too small for the master, so NEVER pick a github-models model as
  master. A big-context free model (e.g. Gemini Flash ~1M, or a free OpenRouter model with a large
  window) fits. The REVIEWER sees only a DIFF (rarely more than a few k tokens on this codebase), so an
  8k model (e.g. github-models gpt-4.1) is fine — a bigger window is a mild plus, not required. If a
  diff ever exceeds the reviewer's window the pipeline flags it to the human (it never silently merges).
- This same configuration runs across TWO repositories that may, by chance, pick the SAME models —
  so each model's FREE request quota must comfortably cover BOTH repos' combined usage (a few
  automated calls per week each). Reject any model whose free tier is too tight for that.
- Master and reviewer should be from TWO DIFFERENT providers when >=2 are available.
- Among the models that satisfy the above, choose the two most capable (reasoning/code quality).

Current configuration: %(current)s

LIVE AVAILABLE MODELS (the ONLY valid choices — fetched just now from each provider). You MUST return
model ids that appear VERBATIM in this list; NEVER guess or use a remembered name (they are often
deprecated, e.g. there is no gemini-1.5-flash here):
%(menu)s

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


def provider_models(provider):
    """Fetch the REAL model ids a provider currently serves (OpenAI-style GET /models), so the
    selector chooses from live slugs instead of guessing deprecated names. Best-effort: any failure
    returns []. OpenRouter is filtered to truly-free (':free') ids and every list is capped to keep
    the selector prompt lean."""
    import urllib.request
    base, key_env = L.PROVIDERS[provider]
    key = os.environ.get(key_env, "").strip()
    if not key:
        return []
    try:
        req = urllib.request.Request(base.rstrip("/") + "/models",
                                     headers={"Authorization": f"Bearer {key}",
                                              "User-Agent": "Mozilla/5.0 (5k-9am-osm-route-cache)"})
        data = json.loads(urllib.request.urlopen(req, timeout=30).read())
        ids = [m.get("id") for m in (data.get("data") or []) if m.get("id")]
        if provider == "openrouter":
            ids = [i for i in ids if str(i).endswith(":free")]   # only no-cost models
        return sorted(ids)[:80]
    except Exception as e:
        print(f"  {provider} /models unavailable ({e.__class__.__name__} {getattr(e,'code','')})")
        # github-models has no OpenAI /models listing — fall back to a known good reviewer id.
        return ["openai/gpt-4.1"] if provider == "github-models" else []


def main():
    avail = available_providers()
    cur = L.load_model_config()
    cur_short = {r: {"provider": cur[r]["provider"], "model": cur[r]["model"]} for r in ROLES}
    # ASSESS the project's token size FIRST: measure the real master-author prompt (whole algorithm +
    # constitution + working doctrine + journal tail + outcomes + instruction overhead) so the selector
    # can reject any model whose free input window can't fit it (with growth headroom).
    def _chars(f): return len(f.read_text(errors="ignore")) if f.exists() else 0
    master_chars = (_chars(L.ALGO_FILE) + _chars(L.CONTEXT_FILE) + _chars(L.BIBLE_FILE)
                    + len(L.journal_tail()) + len(L.outcomes_summary()) + 3000)  # +3000 ≈ instruction block
    master_tokens = master_chars // 4   # ~4 chars/token
    print(f"Measured master prompt: ~{master_chars} chars (~{master_tokens} tokens).")
    menu = {p: provider_models(p) for p in avail}
    menu = {p: ids for p, ids in menu.items() if ids}   # drop providers we couldn't list
    print("Live model menu:", {p: len(ids) for p, ids in menu.items()})
    base_args = {"avail": ", ".join(avail) or "github-models",
                 "master_tokens": f"~{master_tokens}", "menu": json.dumps(menu, indent=1)}

    algo_for_probe = L.ALGO_FILE.read_text(errors="ignore")[:20000]

    def live_ok(provider, model, big=False):
        """Dummy call the chosen model to confirm it's actually live + usable. For the MASTER author
        (big=True) the probe carries an algorithm-sized payload, so a model that handles tiny calls but
        503s / times out under the REAL author load (seen with some preview flash models) is rejected
        HERE — not after it silently fails every author run. Returns (ok, error)."""
        base_url, key_env = L.PROVIDERS[provider]
        if not os.environ.get(key_env, "").strip():
            return False, f"no key for {provider}"
        probe = 'Reply with the JSON {"ok": true} and nothing else.'
        if big:   # approximate the author's real prompt size to catch big-call-only failures
            probe = "Ignore the following code; just " + probe + "\n\n=====\n" + algo_for_probe
        try:
            r = L.call_json({"base_url": base_url, "model": model, "api_key_env": key_env}, probe)
            return isinstance(r, dict), ("" if isinstance(r, dict) else "non-dict reply")
        except Exception as e:
            body = ""
            try:
                if hasattr(e, "read"):
                    body = e.read().decode("utf-8", "ignore")[:160]
            except Exception:
                pass
            return False, f"{e.__class__.__name__} {getattr(e,'code','')} {body}".strip()

    # Propose -> dummy-test the chosen models -> if any is dead, tell the selector to AVOID it and
    # pick a DIFFERENT live one. Retry a few rounds, then keep current if nothing live is found.
    avoid, MAX_TRIES = [], 3
    for attempt in range(MAX_TRIES):
        prompt = PROMPT % {**base_args, "current": json.dumps(cur_short)}
        if avoid:
            prompt += ("\n\nDO NOT choose any of these — they just FAILED a live availability test: "
                       + "; ".join(avoid) + ". Pick DIFFERENT, currently-live models from the menu.")
        # Run the SELECTION on the DEEPER reviewer model first: this prompt is small (menu + config,
        # not the whole algorithm), so it fits the reviewer's window, and picking the best models is a
        # reasoning-heavy judgment best given to the smartest model. Falls back to the author if down.
        rec, _ = L.call_with_roles(prompt, roles=("fallback", "primary"))
        if not isinstance(rec, dict):
            stop("No usable recommendation — keeping current models.")
        new, bad = {}, None
        for role in ROLES:
            r = rec.get(role)
            if not isinstance(r, dict) or str(r.get("provider", "")) not in L.PROVIDERS or not str(r.get("model", "")).strip():
                bad = role; break
            new[role] = {"provider": r["provider"], "model": str(r["model"]).strip()}
        if bad:
            stop(f"Recommendation for {bad} invalid — keeping current.")
        if len(avail) >= 2 and new["primary"]["provider"] == new["fallback"]["provider"]:
            stop("Master and reviewer must be from two different sources (>=2 available) — keeping current.")
        changed = [r for r in ROLES if new[r] != cur_short[r]]
        if not changed:
            stop("All roles still optimal — no change.")

        failures = []                            # dummy-call each newly-chosen model
        for role in changed:
            ok, err = live_ok(new[role]["provider"], new[role]["model"], big=(role == "primary"))
            tag = f'{new[role]["provider"]}/{new[role]["model"]}'
            if not ok:
                print(f"  {role} {tag} failed live test: {err}")
                failures.append(tag)
        if failures:
            avoid = list(dict.fromkeys(avoid + failures))
            continue                             # re-ask, avoiding the dead model(s)

        L.MODEL_CONFIG.write_text(json.dumps({r: new[r] for r in ROLES}, indent=2) + "\n")
        L.emit(changed="true", changed_roles=" & ".join(changed),
               primary=f'{new["primary"]["provider"]}/{new["primary"]["model"]}',
               fallback=f'{new["fallback"]["provider"]}/{new["fallback"]["model"]}',
               reason=str(rec.get("reason", "")).replace("\n", " ").strip()[:400])
        return

    stop(f"No fully-live model set found after {MAX_TRIES} tries — keeping current.")


if __name__ == "__main__":
    main()
