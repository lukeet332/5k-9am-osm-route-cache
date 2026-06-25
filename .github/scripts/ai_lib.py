#!/usr/bin/env python3
"""
Shared helpers for the weekly AI maintenance bots (author / reviewer / model-review).

Safety model mirrors the WearOsGpx repo's proven pipeline:
  * GitHub Models only, via the workflow's built-in GITHUB_TOKEN (models:read) — no secret.
  * Model choice lives in .github/ai_model.json and is self-updated by ai_model_review.py.
  * The bot may only ever OVERWRITE a tiny allow-list of files (build_cache.py, and an
    append to AI_CONTEXT.md) — path-traversal guarded. Everything else is off limits.
  * The author's change must pass selftest.py before a PR opens; CI re-runs it; a second
    AI must approve; branch protection requires the CI check. No unverified/unreviewed merge.
Standard library only.
"""
import json, os, re, sys, urllib.request
from pathlib import Path

REPO = Path.cwd().resolve()
CONTEXT_FILE = (REPO / "AI_CONTEXT.md").resolve()
MODEL_CONFIG = (REPO / ".github" / "ai_model.json").resolve()
INDEX_FILE = (REPO / "index.json").resolve()
ALGO_FILE = (REPO / "build_cache.py").resolve()
ALLOWED = {ALGO_FILE, CONTEXT_FILE}          # the ONLY files a bot may write

# Both providers free. Three tiers:
#  * github-models (GITHUB_TOKEN, no secret) — the DEEP author/reasoner.
#  * gemini (needs GEMINI_API_KEY) — supplies the DEEP, INDEPENDENT reviewer (2.5 Pro, a
#    different family so the review is genuinely independent) AND the FAST tier (2.5 Flash)
#    the deep model can hand quick/simple subtasks to. If GEMINI_API_KEY is absent the
#    system degrades gracefully to github-models (reviewer falls back to the deep author).
# The reviewer must stay a DEEP model — it is the safety gate; Flash is NOT used to review.
PROVIDERS = {
    "github-models": ("https://models.github.ai/inference", "GH_MODELS_TOKEN"),
    "gemini": ("https://generativelanguage.googleapis.com/v1beta/openai", "GEMINI_API_KEY"),
}
DEFAULT_PRIMARY = {"provider": "github-models", "model": "openai/gpt-4.1"}    # deep author
DEFAULT_FALLBACK = {"provider": "gemini", "model": "gemini-2.5-pro"}          # deep independent reviewer
DEFAULT_FAST = {"provider": "gemini", "model": "gemini-2.5-flash"}            # fast tier for delegated quick subtasks (never review)


def emit(**kv):
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a") as f:
            for k, v in kv.items():
                f.write(f"{k}={v}\n")
    for k, v in kv.items():
        print(f"{k}={v}")


def done(msg, **outputs):
    print(msg)
    if outputs:
        emit(**outputs)
    sys.exit(0)          # "nothing to do" is always a success


def resolve(slot, default):
    slot = slot if isinstance(slot, dict) else {}
    provider = slot.get("provider") if slot.get("provider") in PROVIDERS else default["provider"]
    model = slot.get("model")
    if not (isinstance(model, str) and model.strip()):
        model = default["model"]
    base_url, key_env = PROVIDERS[provider]
    return {"provider": provider, "model": model.strip(), "base_url": base_url, "api_key_env": key_env}


def load_model_config():
    data = {}
    try:
        if MODEL_CONFIG.exists():
            data = json.loads(MODEL_CONFIG.read_text())
    except Exception as e:
        print(f"Could not read ai_model.json ({e.__class__.__name__}); using defaults.")
    return {"primary": resolve(data.get("primary"), DEFAULT_PRIMARY),
            "fallback": resolve(data.get("fallback"), DEFAULT_FALLBACK),
            "fast": resolve(data.get("fast"), DEFAULT_FAST)}


def bot_label(model):
    return re.sub(r"[^A-Za-z0-9._-]", "-", model.split("/")[-1]) + "-bot"


def _post(url, headers, payload):
    req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                 headers={**headers, "Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read())


def call_json(slot, prompt):
    """Call an OpenAI-compatible /chat/completions endpoint and parse a JSON object reply."""
    key = os.environ.get(slot["api_key_env"], "").strip()
    if not key:
        raise RuntimeError(f"no key in env {slot['api_key_env']}")
    data = _post(slot["base_url"].rstrip("/") + "/chat/completions",
                 {"Authorization": f"Bearer {key}"},
                 {"model": slot["model"], "temperature": 0.1,
                  "response_format": {"type": "json_object"},
                  "messages": [{"role": "user", "content": prompt}]})
    return json.loads(data["choices"][0]["message"]["content"])


def call_with_roles(prompt, roles=("primary", "fallback")):
    """Try the given config roles in order; return (result, slot) or (None, None)."""
    cfg = load_model_config()
    for role in roles:
        slot = cfg[role]
        if not os.environ.get(slot["api_key_env"], "").strip():
            continue
        try:
            print(f"Asking {role}: {slot['provider']} ({slot['model']})…")
            return call_json(slot, prompt), slot
        except Exception as e:
            print(f"{role} {slot['provider']} unavailable ({e.__class__.__name__}).")
    return None, None


def is_safe(path):
    rf = Path(path).resolve()
    try:
        rf.relative_to(REPO)
    except ValueError:
        return False
    return rf in ALLOWED


def apply_changes(result):
    changed = 0
    for ch in result.get("changes", []):
        rel = str(ch.get("path", "")).lstrip("/")
        content = ch.get("content")
        target = (REPO / rel).resolve() if rel else None
        if not rel or content is None:
            continue
        if not is_safe(target):
            print(f"  skip (not in allow-list): {rel}"); continue
        if not target.is_file():
            print(f"  skip (not an existing file): {rel}"); continue
        target.write_text(content)
        print(f"  patched: {rel}"); changed += 1
    return changed


def outcomes_summary():
    """Compact, factual report of the current cache outcomes for the prompt."""
    try:
        idx = json.loads(INDEX_FILE.read_text()) if INDEX_FILE.exists() else {}
    except Exception:
        idx = {}
    locked = [e for e in idx.values() if e.get("distance_m") and 4800 <= e["distance_m"] <= 5200]
    sources = {}
    dists = []
    for e in idx.values():
        sources[e.get("source") or "gap"] = sources.get(e.get("source") or "gap", 0) + 1
        if e.get("distance_m"):
            dists.append(e["distance_m"])
    avg_off = round(sum(abs(d - 5000) for d in dists) / len(dists)) if dists else 0
    return (f"index entries: {len(idx)}; within 4.8-5.2km (locked): {len(locked)}; "
            f"sources: {sources}; mean |distance-5000| over cached: {avg_off} m.")
