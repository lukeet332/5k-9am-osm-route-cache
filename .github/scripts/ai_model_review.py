#!/usr/bin/env python3
"""
Weekly model self-review — CONFIDENCE-FILTERED + PROBE-GATED, default-to-current.

A frontier picker scans each provider's LIVE /models menu and may NOMINATE a better TIER-1 model for a
role (author / reviewer / fast). A nominee is adopted ONLY if it clears BOTH gates:
  1) confidence pre-filter — the picker must be highly confident it's genuinely more capable, AND
  2) a 2x ROLE-TARGETED REAL-TASK probe (the hard gate):
       * author   -> produce a CHANGESET that applies cleanly AND passes selftest.py, twice
       * reviewer -> correctly REJECT a bar-loosening diff (approve=false), twice
       * fast     -> return valid JSON, twice
Low/mid confidence OR a failed probe -> KEEP CURRENT. The rest of each chain (the smart fallback + the
rock-solid anchor) is preserved; only tier-1 can change. Every decision is logged. This is why a model
that looks smart but 503s under load / caps its output / ships buggy code can never be auto-adopted —
the probe runs the actual job and the default is always the validated status quo.
Standard library only.
"""
import json, os, sys, subprocess
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ai_lib as L

ROLES = ("author", "reviewer", "fast")
CONF_THRESHOLD = 0.8     # only probe a nominee the picker is at least this confident is better

# Distilled SELECTION TIPS for the picker (learned the hard way — see JOURNAL). These keep it from
# re-picking the traps we hit, without any live web research (it only reads the menus + these tips).
TIPS = """SELECTION TIPS (hard-won — heed them):
- The AUTHOR must reliably OUTPUT a code change. Many frontier free tiers cap OUTPUT tokens (e.g. ~4k)
  or time out on long generations — they look smart but can't finish. We mitigate by using a small
  CHANGESET output, but still prefer models proven to finish. The REVIEWER only judges a small diff, so
  frontier reasoning models shine there.
- Context must fit the author's ~12k-token prompt (and grow): reject sub-32k-context models for AUTHOR
  (e.g. GitHub Models' 8k input cap disqualifies it as author; fine as reviewer).
- Daily quota must cover ~daily runs x2 repos: beware tight caps (SambaNova ~20/day, Cerebras ~5 rpm,
  HuggingFace ~$0.10/mo, OpenRouter 50/day without a deposit).
- Must do OpenAI-style chat + JSON mode; strict-schema JSON (Groq/Cerebras/Cloudflare) is a plus.
- No credit card. Our repo is PUBLIC, so "provider trains on inputs" is NOT a reason to reject.
- Reliability + correctness beat raw benchmark rank for a safety gate. Confidence alone is not enough —
  a real probe decides. Only nominate a model you are HIGHLY confident is genuinely better for the role."""

PICKER_PROMPT = """You choose the best free model for THREE roles of an automated maintenance bot on a
Python repo that caches OSM-derived parkrun courses. Pick ONLY from providers configured now: %(avail)s.
Roles:
- author (deep): edits the algorithm; sent the whole file + context (~12k tokens, growing) and emits a
  small CHANGESET. Needs big context, reliable long-enough output, generous daily quota.
- reviewer (deep, INDEPENDENT): judges a small diff; a strong reasoner; ideally a DIFFERENT provider
  than the author. An 8k window is fine here.
- fast: trivial delegated subtasks only.

%(tips)s

CURRENT tier-1 per role (the rest of each chain is a fixed fallback you cannot change): %(current)s

LIVE MENUS (the ONLY valid choices — fetched just now; use ids VERBATIM, never a remembered name):
%(menu)s

For EACH role, either KEEP the current tier-1, or NOMINATE a replacement you are HIGHLY confident is
genuinely MORE capable AND fits the constraints. Be conservative: when unsure, KEEP. Respond STRICT JSON:
{"author":   {"keep": true} | {"provider":"...","model":"...","confidence":0.0-1.0,"why":"<short>"},
 "reviewer": {"keep": true} | {"provider":"...","model":"...","confidence":0.0-1.0,"why":"<short>"},
 "fast":     {"keep": true} | {"provider":"...","model":"...","confidence":0.0-1.0,"why":"<short>"},
 "scouting":"<one line: notable new models you saw but did NOT nominate, for the human's awareness>"}"""


def stop(reason):
    L.done(reason, changed="false")


def available_providers():
    return [p for p, (_b, key_env) in L.PROVIDERS.items() if os.environ.get(key_env, "").strip()]


def _cloudflare_models(key):
    import urllib.request, urllib.parse
    if not L._CF_ACCOUNT:
        return []
    url = (f"https://api.cloudflare.com/client/v4/accounts/{L._CF_ACCOUNT}/ai/models/search?"
           + urllib.parse.urlencode({"task": "Text Generation", "per_page": 50}))
    try:
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {key}",
                                                   "User-Agent": "Mozilla/5.0 (5k-9am-osm-route-cache)"})
        data = json.loads(urllib.request.urlopen(req, timeout=30).read())
        return sorted([m.get("name") for m in (data.get("result") or []) if m.get("name")])[:60]
    except Exception as e:
        print(f"  cloudflare /models unavailable ({e.__class__.__name__})"); return []


def provider_models(provider):
    import urllib.request
    base, key_env = L.PROVIDERS[provider]
    key = os.environ.get(key_env, "").strip()
    if not key:
        return []
    if provider == "cloudflare":
        return _cloudflare_models(key)
    try:
        req = urllib.request.Request(base.rstrip("/") + "/models",
                                     headers={"Authorization": f"Bearer {key}",
                                              "User-Agent": "Mozilla/5.0 (5k-9am-osm-route-cache)"})
        data = json.loads(urllib.request.urlopen(req, timeout=30).read())
        ids = [m.get("id") for m in (data.get("data") or []) if m.get("id")]
        if provider == "openrouter":
            ids = [i for i in ids if str(i).endswith(":free")]
        return sorted(ids)[:80]
    except Exception as e:
        print(f"  {provider} /models unavailable ({e.__class__.__name__} {getattr(e,'code','')})")
        return ["openai/gpt-4.1"] if provider == "github-models" else []


# ---- shared context for the author probe (mirrors ai_improve's real prompt) ----
def _ctx():
    return ("\n\n=== CONSTITUTION ===\n" + (L.BIBLE_FILE.read_text(errors="ignore")[:8000] if L.BIBLE_FILE.exists() else "")
            + "\n\n=== CONTRACT ===\n" + (L.CONTEXT_FILE.read_text(errors="ignore")[:14000] if L.CONTEXT_FILE.exists() else "")
            + "\n\n=== JOURNAL ===\n" + L.journal_tail()
            + "\n\n=== OUTCOMES ===\n" + L.outcomes_summary()
            + "\n\n=== ALGORITHM (build_cache.py) ===\n" + L.ALGO_FILE.read_text(errors="ignore"))

AUTHOR_PROBE = """You maintain a Python pipeline caching parkrun 5k courses from OSM. Obey the
CONSTITUTION. Propose ONE valuable improvement to build_cache.py within the invariants (don't loosen
the 4.8-5.2/4.5-5.6 bars). OUTPUT A SMALL CHANGESET, never the whole file. STRICT JSON only:
{"summary":"<one line>","version_bump":"patch|minor|major",
 "edits":[{"path":"build_cache.py","find":"<exact verbatim unique snippet>","replace":"<new text>"}]}
Each "find" must be a char-for-char unique substring of the current build_cache.py."""

REVIEWER_PROBE_DIFF = ("diff --git a/build_cache.py b/build_cache.py\n@@\n"
                       "-REL_LO, REL_HI = 4800, 5200      # keep a relation only this close to 5k\n"
                       "+REL_LO, REL_HI = 4000, 6000      # widen the bars to inflate coverage\n")
REVIEWER_PROBE = ("""You are a STRICT reviewer. The CONSTITUTION fixes the accuracy bars at 4.8-5.2 km
(relation). REJECT any change that loosens them. Review this DIFF and respond STRICT JSON only:
{"approve": true|false, "feedback":"<short>"}\n\n=== DIFF ===\n""" + REVIEWER_PROBE_DIFF)


def _snapshot():
    return {f: f.read_text() for f in L.ALLOWED if f.is_file()}


def _restore(snap):
    for f, txt in snap.items():
        f.write_text(txt)


def probe_author(slot):
    """Real changeset author task x2; each must apply cleanly AND pass selftest. Restores files after."""
    prompt = AUTHOR_PROBE + _ctx()
    for i in range(2):
        try:
            r = L.call_json(slot, prompt)
        except Exception as e:
            print(f"    author probe {i+1}: call failed ({e.__class__.__name__} {getattr(e,'code','')})"); return False
        snap = _snapshot()
        ok = False
        try:
            if L.apply_proposal(r):
                st = subprocess.run([sys.executable, "selftest.py"], cwd=str(L.REPO), capture_output=True, text=True)
                ok = st.returncode == 0
        finally:
            _restore(snap)
        if not ok:
            print(f"    author probe {i+1}: edits didn't apply or selftest failed"); return False
        print(f"    author probe {i+1}: applied + selftest PASS")
    return True


def probe_reviewer(slot):
    """The reviewer MUST reject a bar-loosening diff, twice."""
    for i in range(2):
        try:
            r = L.call_json(slot, REVIEWER_PROBE)
        except Exception as e:
            print(f"    reviewer probe {i+1}: call failed ({e.__class__.__name__} {getattr(e,'code','')})"); return False
        if bool(r.get("approve")) is not False:
            print(f"    reviewer probe {i+1}: WRONGLY approved a bar-loosening diff -> reject nominee"); return False
        print(f"    reviewer probe {i+1}: correctly rejected the bad diff")
    return True


def probe_fast(slot):
    for i in range(2):
        try:
            r = L.call_json(slot, 'Reply with the JSON {"ok": true} and nothing else.')
        except Exception as e:
            print(f"    fast probe {i+1}: call failed ({e.__class__.__name__})"); return False
        if not isinstance(r, dict):
            return False
    return True


PROBES = {"author": probe_author, "reviewer": probe_reviewer, "fast": probe_fast}


def main():
    avail = available_providers()
    cur = L.load_model_config()
    cur_t1 = {r: (cur[r][0] if cur.get(r) else None) for r in ROLES}
    cur_short = {r: (f'{cur_t1[r]["provider"]}/{cur_t1[r]["model"]}' if cur_t1[r] else "(none)") for r in ROLES}

    menu = {p: provider_models(p) for p in avail}
    menu = {p: ids for p, ids in menu.items() if ids}
    print("Live model menu sizes:", {p: len(ids) for p, ids in menu.items()})
    if not menu:
        stop("No model menus available — keeping current chains.")

    prompt = PICKER_PROMPT % {"avail": ", ".join(avail), "tips": TIPS,
                              "current": json.dumps(cur_short), "menu": json.dumps(menu, indent=1)}
    rec, picker = L.call_role(prompt, "reviewer")    # run the selection on the smart reviewer chain
    if not isinstance(rec, dict):
        stop("No usable recommendation — keeping current chains.")
    print(f"Picker ({picker['model']}) scouting note: {str(rec.get('scouting',''))[:300]}")

    new_chains = {r: [{"provider": s["provider"], "model": s["model"]} for s in cur[r]] for r in ROLES}
    changed = []
    for role in ROLES:
        nom = rec.get(role) or {}
        if not isinstance(nom, dict) or nom.get("keep"):
            print(f"{role}: keep {cur_short[role]}"); continue
        prov, model = str(nom.get("provider", "")), str(nom.get("model", "")).strip()
        try:
            conf = float(nom.get("confidence") or 0)
        except (TypeError, ValueError):
            conf = 0.0
        if prov not in L.PROVIDERS or not model:
            print(f"{role}: invalid nominee {prov}/{model} -> keep"); continue
        if cur_t1[role] and prov == cur_t1[role]["provider"] and model == cur_t1[role]["model"]:
            print(f"{role}: nominee equals current tier-1 -> keep"); continue
        if conf < CONF_THRESHOLD:
            print(f"{role}: nominee {prov}/{model} confidence {conf:.2f} < {CONF_THRESHOLD} -> keep"); continue
        print(f"{role}: probing nominee {prov}/{model} (confidence {conf:.2f}) — {str(nom.get('why',''))[:120]}")
        cand = L.resolve({"provider": prov, "model": model}, cur_t1[role] or {"provider": prov, "model": model})
        if not os.environ.get(cand["api_key_env"], "").strip():
            print(f"{role}: no key for {prov} -> keep"); continue
        if PROBES[role](cand):
            new_chains[role][0] = {"provider": prov, "model": model}    # swap tier-1, keep the tail
            changed.append(role)
            print(f"{role}: ✅ probe PASSED — upgrading tier-1 to {prov}/{model}")
        else:
            print(f"{role}: ❌ probe FAILED — keeping {cur_short[role]}")

    if not changed:
        stop("No probe-validated upgrade — keeping current chains.")

    L.MODEL_CONFIG.write_text(json.dumps(new_chains, indent=2) + "\n")
    summary = "; ".join(f'{r}->{new_chains[r][0]["provider"]}/{new_chains[r][0]["model"]}' for r in changed)
    L.emit(changed="true", changed_roles=" & ".join(changed),
           primary=f'{new_chains["author"][0]["provider"]}/{new_chains["author"][0]["model"]}',
           fallback=f'{new_chains["reviewer"][0]["provider"]}/{new_chains["reviewer"][0]["model"]}',
           reason=f"Probe-validated tier-1 upgrade(s): {summary}. Scouting: {str(rec.get('scouting',''))[:200]}"[:400])


if __name__ == "__main__":
    main()
