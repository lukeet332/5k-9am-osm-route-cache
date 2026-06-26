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
BIBLE_FILE = (REPO / "AI_CONTEXT_READ_ONLY_BIBLE.md").resolve()  # the constitution (supreme law)
MODEL_CONFIG = (REPO / ".github" / "ai_model.json").resolve()
INDEX_FILE = (REPO / "index.json").resolve()
ALGO_FILE = (REPO / "build_cache.py").resolve()
JOURNAL_FILE = (REPO / "JOURNAL.md").resolve()   # the bots' running diary of ideas/learnings
# Files a bot may write. The BIBLE is included so the AI can *propose* an amendment — but a PR that
# touches it can NEVER auto-merge: the reviewer (ai-review.yml) blocks it and tags the human owner,
# who must approve in a comment (`/approve-bible`). selftest.py / .github/** are deliberately NOT here.
ALLOWED = {ALGO_FILE, CONTEXT_FILE, JOURNAL_FILE, BIBLE_FILE}

# Multi-source menu (all free), same registry as the WearOsGpx app. The weekly review picks
# the best PAIR — master (author) + slave (reviewer) — from TWO DIFFERENT providers where
# possible, so the review is genuinely independent. github-models needs no secret (built-in
# GITHUB_TOKEN); the rest need their key as a repo secret. A provider with no key is simply
# skipped, so the system always degrades gracefully (worst case: github-models only).
# The reviewer must stay a DEEP model — it is the safety gate; the fast tier never reviews.
PROVIDERS = {
    "github-models": ("https://models.github.ai/inference", "GH_MODELS_TOKEN"),
    "gemini": ("https://generativelanguage.googleapis.com/v1beta/openai", "GEMINI_API_KEY"),
    "openrouter": ("https://openrouter.ai/api/v1", "OPENROUTER_API_KEY"),
    "groq": ("https://api.groq.com/openai/v1", "GROQ_API_KEY"),
    "mistral": ("https://api.mistral.ai/v1", "MISTRAL_API_KEY"),
}
DEFAULT_PRIMARY = {"provider": "github-models", "model": "openai/gpt-4.1"}    # master / deep author
DEFAULT_FALLBACK = {"provider": "gemini", "model": "gemini-2.5-pro"}          # slave / deep independent reviewer
DEFAULT_FAST = {"provider": "gemini", "model": "gemini-2.5-flash"}            # fast tier for delegated quick subtasks (never reviews)


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


def journal_tail(max_chars=6000):
    """The most recent slice of JOURNAL.md — the bots' accumulated ideas/learnings."""
    if not JOURNAL_FILE.exists():
        return "(empty — no prior entries)"
    return JOURNAL_FILE.read_text(errors="ignore")[-max_chars:]


def outcomes_summary():
    """Rich, factual report of the current cache outcomes for the prompt — maximum signal for
    the author/reviewer. Surfaces success/failed/gap counts, how many successes are PROVISIONAL
    (relation-sourced, not GPS-verified -> upgrade targets), plus the failed-entry diagnostics
    (what each source measured), highlighting actionable patterns like likely single-laps."""
    try:
        idx = json.loads(INDEX_FILE.read_text()) if INDEX_FILE.exists() else {}
    except Exception:
        idx = {}
    def status(e):
        return e.get("status") or ("success" if (e.get("distance_m") and 4800 <= e["distance_m"] <= 5200) else "gap")
    counts = {"success": 0, "failed": 0, "gap": 0}
    for e in idx.values():
        counts[status(e)] = counts.get(status(e), 0) + 1
    succ = [e for e in idx.values() if status(e) == "success"]
    # Provisional = relation-sourced success (not GPS-verified) -> the AI's upgrade backlog.
    provisional = sum(1 for e in succ if e.get("provisional") or e.get("source") == "osm_relation")
    trusted = counts["success"] - provisional
    failed = [e for e in idx.values() if status(e) == "failed"]
    # Actionable patterns in the failed diagnostics:
    single_lap = sum(1 for e in failed if (e.get("relation_m") or 0) and 2000 <= e["relation_m"] <= 2800)  # ~half 5k -> likely a 2-lap parkrun
    near_miss = sum(1 for e in failed if (e.get("distance_m") or 0) and (4300 <= e["distance_m"] < 4800 or 5200 < e["distance_m"] <= 5700))  # just outside tolerance -> often an incomplete relation
    sample = [{"name": k, "status": status(v), "relation_m": v.get("relation_m"), "trace_m": v.get("trace_m")}
              for k, v in list(idx.items()) if status(v) == "failed"][:8]
    return (f"INDEX outcomes (of {len(idx)} attempted): success={counts['success']} "
            f"({trusted} trusted GPS-trace, {provisional} PROVISIONAL relation-sourced -> upgrade to "
            f"real 09:00 traces), failed(off-tolerance, index.json only)={counts['failed']}, gap={counts['gap']}. "
            f"Of the failed: ~{single_lap} have a ~2.0-2.8km relation (likely ONE LAP of a 2-lap parkrun "
            f"— consider doubling), ~{near_miss} are near-misses just outside 4.8-5.2km (often an "
            f"incomplete relation — consider way-chaining/gap-bridging). Sample failed: {sample}.")
