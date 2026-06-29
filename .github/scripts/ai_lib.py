#!/usr/bin/env python3
"""
Shared helpers for the weekly AI maintenance bots (author / reviewer / model-review).

Safety model mirrors the WearOsGpx repo's proven pipeline:
  * GitHub Models by default, authenticated with the BOT_PAT secret (a real PAT with models:read —
    the built-in GITHUB_TOKEN is NOT entitled to the Models API). Other providers need their own key.
  * Model choice lives in .github/ai_model.json and is self-updated by ai_model_review.py.
  * The bot may only ever OVERWRITE a tiny allow-list of files (build_cache.py, and an
    append to AI_CONTEXT.md) — path-traversal guarded. Everything else is off limits.
  * The author's change must pass selftest.py before a PR opens; CI re-runs it; a second
    AI must approve; branch protection requires the CI check. No unverified/unreviewed merge.
Standard library only.
"""
import json, os, re, sys, time, urllib.request, urllib.error, uuid
from pathlib import Path

REPO = Path.cwd().resolve()
CONTEXT_FILE = (REPO / "AI_CONTEXT.md").resolve()
BIBLE_FILE = (REPO / "AI_CONTEXT_READ_ONLY_BIBLE.md").resolve()  # the constitution (supreme law)
MODEL_CONFIG = (REPO / ".github" / "ai_model.json").resolve()
INDEX_FILE = (REPO / "index.json").resolve()
ALGO_FILE = (REPO / "build_cache.py").resolve()
JOURNAL_FILE = (REPO / "JOURNAL.md").resolve()   # the bots' running diary of ideas/learnings
BEHAVIOR_TEST_FILE = (REPO / "test_behavior.py").resolve()   # EDITABLE behavioural expectations (not invariants)
# Files a bot may write. The BIBLE is included so the AI can *propose* an amendment — but a PR that
# touches it can NEVER auto-merge: the reviewer (ai-review.yml) blocks it and tags the human owner, who
# must approve in a comment (`/approve-bible`). test_behavior.py IS writable so the author can UPDATE a
# behavioural expectation a genuine algorithm change alters — but selftest.py (frozen invariants) and
# .github/** are deliberately NOT here.
ALLOWED = {ALGO_FILE, CONTEXT_FILE, JOURNAL_FILE, BIBLE_FILE, BEHAVIOR_TEST_FILE}

# Multi-source menu (all free), same registry as the WearOsGpx app. The weekly review picks
# the best PAIR — master (author) + slave (reviewer) — from TWO DIFFERENT providers where
# possible, so the review is genuinely independent. github-models needs no secret (built-in
# GITHUB_TOKEN); the rest need their key as a repo secret. A provider with no key is simply
# skipped, so the system always degrades gracefully (worst case: github-models only).
# The reviewer must stay a DEEP model — it is the safety gate; the fast tier never reviews.
# Cloudflare Workers AI puts the ACCOUNT ID in its OpenAI-compatible URL — read it from a repo secret
# at import. If it's unset the base is incomplete, so calls just fail and the provider is skipped
# gracefully (its key gate + the fallback chain absorb that) — it never hard-breaks the pipeline.
_CF_ACCOUNT = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "").strip()
PROVIDERS = {
    "github-models": ("https://models.github.ai/inference", "GH_MODELS_TOKEN"),
    "gemini": ("https://generativelanguage.googleapis.com/v1beta/openai", "GEMINI_API_KEY"),
    "openrouter": ("https://openrouter.ai/api/v1", "OPENROUTER_API_KEY"),
    "groq": ("https://api.groq.com/openai/v1", "GROQ_API_KEY"),
    "mistral": ("https://api.mistral.ai/v1", "MISTRAL_API_KEY"),
    # More free, no-credit-card, OpenAI-compatible endpoints — widen the menu + fallback chain. A
    # model that can't deliver strict JSON simply fails the live probe / call and is skipped.
    "huggingface": ("https://router.huggingface.co/v1", "HF_TOKEN"),
    "cloudflare": (f"https://api.cloudflare.com/client/v4/accounts/{_CF_ACCOUNT}/ai/v1", "CLOUDFLARE_API_TOKEN"),
    "sambanova": ("https://api.sambanova.ai/v1", "SAMBANOVA_API_KEY"),     # fast frontier (DeepSeek-V3.x)
    "cerebras": ("https://api.cerebras.ai/v1", "CEREBRAS_API_KEY"),        # fast frontier reasoner (GLM-4.7)
    "nvidia": ("https://integrate.api.nvidia.com/v1", "NVIDIA_API_KEY"),   # frontier (DeepSeek-V4); free, no daily cap
}

# Each role is a CHAIN tried in order: a bleeding-edge frontier model first, then a smart fallback on a
# DIFFERENT provider, then a rock-solid anchor — so a single overloaded free endpoint never sinks a run.
# Picked from an empirical bake-off (changeset output, selftest-gated): see JOURNAL/AI_CONTEXT.
DEFAULT_AUTHOR = [
    {"provider": "nvidia", "model": "deepseek-ai/deepseek-v4-flash"},  # frontier (best SWE-bench); find-matching verified on the clean file
    {"provider": "sambanova", "model": "DeepSeek-V3.2"},               # proven reliable fallback, different provider
    {"provider": "gemini", "model": "gemini-2.5-flash"},              # rock-solid anchor, third provider
]
DEFAULT_REVIEWER = [
    {"provider": "cerebras", "model": "zai-glm-4.7"},               # frontier reasoner, validated as gate
    {"provider": "groq", "model": "openai/gpt-oss-120b"},           # frontier + strict JSON, different provider
    {"provider": "github-models", "model": "openai/gpt-4.1"},       # rock-solid independent anchor
]
DEFAULT_FAST = [{"provider": "gemini", "model": "gemini-2.5-flash"}]   # trivial delegated subtasks only


def emit(**kv):
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a") as f:
            for k, v in kv.items():
                v = str(v)
                if "\n" in v:                       # multiline value -> GitHub Actions heredoc form
                    d = f"GHADELIM_{uuid.uuid4().hex}"   # random per value: a fixed delim is injectable
                    while d in v:                       # never collide with attacker-influenceable content
                        d = f"GHADELIM_{uuid.uuid4().hex}"
                    f.write(f"{k}<<{d}\n{v}\n{d}\n")
                else:
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


def _resolve_chain(items, default):
    """Resolve a role's CHAIN (ordered list of slots). Falls back to the default chain if absent."""
    items = items if isinstance(items, list) and items else default
    return [resolve(s, default[0]) for s in items]


def load_model_config():
    """Return per-role CHAINS: {"author": [...], "reviewer": [...], "fast": [...]}. Each chain is tried
    in order at call time (frontier first, anchor last). Back-compat: a legacy {primary,fallback,fast}
    config maps primary->author, fallback->reviewer."""
    data = {}
    try:
        if MODEL_CONFIG.exists():
            data = json.loads(MODEL_CONFIG.read_text())
    except Exception as e:
        print(f"Could not read ai_model.json ({e.__class__.__name__}); using defaults.")
    if "author" in data or "reviewer" in data:          # new per-role-chain schema
        return {"author": _resolve_chain(data.get("author"), DEFAULT_AUTHOR),
                "reviewer": _resolve_chain(data.get("reviewer"), DEFAULT_REVIEWER),
                "fast": _resolve_chain(data.get("fast"), DEFAULT_FAST)}
    # legacy single-slot schema -> wrap each as a 1-element chain
    return {"author": _resolve_chain([data["primary"]] if data.get("primary") else None, DEFAULT_AUTHOR),
            "reviewer": _resolve_chain([data["fallback"]] if data.get("fallback") else None, DEFAULT_REVIEWER),
            "fast": _resolve_chain([data["fast"]] if data.get("fast") else None, DEFAULT_FAST)}


def bot_label(model):
    return re.sub(r"[^A-Za-z0-9._-]", "-", model.split("/")[-1]) + "-bot"


def _post(url, headers, payload, attempts=3, timeout=300):
    """POST with retry+backoff on TRANSIENT errors (429 rate-limit, 500/502/503/504 server/overload,
    AND read timeouts). This is an ASYNC pipeline, so slow-but-correct is fine: a frontier model on a
    free tier can take a while, hence a generous 300s/attempt. Changeset output is small so calls are
    usually quick; the timeout just lets a slow tier finish rather than getting cut off. Non-transient
    errors (400/401/413 …) raise immediately; attempts kept low so worst-case stays within the job."""
    # A real User-Agent: some providers (e.g. Groq) sit behind Cloudflare, which 403s the default
    # "Python-urllib/x.y" signature (error 1010). A normal UA passes and is harmless elsewhere.
    req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                 headers={**headers, "Content-Type": "application/json",
                                          "User-Agent": "Mozilla/5.0 (5k-9am-osm-route-cache AI maintenance bot)"},
                                 method="POST")
    for i in range(attempts):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504) and i < attempts - 1:
                time.sleep(3 * (i + 1) ** 2)        # 3s, 12s
                continue
            raise
        except (urllib.error.URLError, TimeoutError):   # connection error OR read timeout (slow gen)
            if i < attempts - 1:
                time.sleep(3 * (i + 1)); continue
            raise


def call_json(slot, prompt, max_tokens=4000):
    """Call an OpenAI-compatible /chat/completions endpoint and parse a JSON object reply.
    NOTE: max_tokens MUST be set — some providers (Cloudflare Workers AI) default to a tiny 256-token
    output, which silently truncates a changeset to invalid/empty JSON. The default 4000 covers a
    review verdict / picker reply and stays within the tightest free output cap (GitHub Models = 4000);
    the AUTHOR passes a higher value (its providers allow it) so a big changeset never truncates."""
    key = os.environ.get(slot["api_key_env"], "").strip()
    if not key:
        raise RuntimeError(f"no key in env {slot['api_key_env']}")
    data = _post(slot["base_url"].rstrip("/") + "/chat/completions",
                 {"Authorization": f"Bearer {key}"},
                 {"model": slot["model"], "temperature": 0.1, "max_tokens": max_tokens,
                  "response_format": {"type": "json_object"},
                  "messages": [{"role": "user", "content": prompt}]})
    who = f'{slot.get("provider", "?")}/{slot.get("model", "?")}'
    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        raise RuntimeError(f"unexpected response shape from {who}: {str(data)[:200]}")
    if not isinstance(content, str) or not content.strip():
        raise RuntimeError(f"empty/non-text content from {who} (capped output or reasoning-only reply?)")
    return json.loads(content)


def call_role(prompt, role):
    """Try each model in the ROLE's chain (author/reviewer/fast) in order; the first that returns valid
    JSON wins. A model with no key, or that errors/times out, is skipped — so the chain degrades from
    the frontier primary through a smart fallback to the rock-solid anchor. Returns (result, slot) or
    (None, None)."""
    chain = load_model_config().get(role) or []
    # The author emits a changeset (occasionally large); give it real output headroom. The reviewer /
    # fast / picker reply small, and the reviewer anchor (GitHub Models) caps output at 4000.
    max_tokens = 8000 if role == "author" else 4000
    for slot in chain:
        if not os.environ.get(slot["api_key_env"], "").strip():
            print(f"{role}: skip {slot['provider']}/{slot['model']} (no key)")
            continue
        # Retry ONCE on the same tier for a transient REPLY error (malformed/empty/odd-shape JSON — a
        # model occasionally emits a stray token or a reasoning-only reply) before demoting. A flaky
        # one-off here used to needlessly drop us to a weaker tier (e.g. Gemini JSONDecodeError -> fall
        # through). HTTP/connection errors are NOT retried here (_post already retried transient 429/5xx;
        # a 400/401/413 would just repeat) — they demote immediately.
        err = None
        for attempt in (1, 2):
            try:
                print(f"{role}: trying {slot['provider']} ({slot['model']})… (try {attempt})")
                return call_json(slot, prompt, max_tokens=max_tokens), slot
            except (json.JSONDecodeError, RuntimeError) as e:
                err = e
                if attempt == 1:
                    print(f"{role}: {slot['provider']} transient reply error ({e.__class__.__name__}) — retrying once")
                    time.sleep(2); continue
            except Exception as e:
                err = e; break
        # Surface the real cause (HTTP status + body) — a swallowed HTTPError once hid that the
        # built-in GITHUB_TOKEN can't reach GitHub Models. Don't print the token itself.
        code = getattr(err, "code", "")
        body = ""
        try:
            if hasattr(err, "read"):
                body = err.read().decode("utf-8", "ignore")[:300]
        except Exception:
            pass
        print(f"{role}: {slot['provider']} unavailable ({err.__class__.__name__} {code}) {body}")
    return None, None


# Backward-compat shim: older callers used call_with_roles((reviewer-ish, author-ish)). Map to the
# new role chains so nothing breaks during the transition.
def call_with_roles(prompt, roles=("primary", "fallback")):
    role = "reviewer" if roles and roles[0] in ("fallback", "reviewer") else "author"
    return call_role(prompt, role)


def is_safe(path):
    rf = Path(path).resolve()
    try:
        rf.relative_to(REPO)
    except ValueError:
        return False
    return rf in ALLOWED


def apply_proposal(result):
    """Apply an author proposal. Two formats supported:
      * "edits":   [{path, find, replace}]  — a precise CHANGESET (preferred: small output, fits every
                    free output cap). Each `find` must appear EXACTLY ONCE in the (allow-listed,
                    existing) file. Application is ATOMIC: if ANY edit fails to match, NOTHING is
                    written and 0 is returned, so the caller treats it as a failed attempt and the
                    chain/retry moves on (a partial apply would corrupt the file).
      * "changes": [{path, content}]        — whole-file overwrite (legacy / big-context models).
    Returns the number of files/edits applied (0 = nothing applied)."""
    edits = result.get("edits") or []
    if edits:
        pending = {}                                   # Path -> new content (staged, not yet written)
        for e in edits:
            rel = str(e.get("path", "")).lstrip("/")
            find, repl = e.get("find"), e.get("replace")
            target = (REPO / rel).resolve() if rel else None
            if not rel or find is None or repl is None:
                print("  edit rejected: missing path/find/replace"); return 0
            if not is_safe(target) or not target.is_file():
                print(f"  edit rejected (not allow-listed/existing): {rel}"); return 0
            cur = pending.get(target, target.read_text())
            n = cur.count(find)
            if n != 1:                                 # must match exactly once (present + unambiguous)
                print(f"  edit rejected: 'find' appears {n}x in {rel} (need exactly 1)"); return 0
            new = cur.replace(find, repl, 1)
            if new == cur:                             # no-op (find == replace) -> "applied" but zero diff
                print(f"  edit rejected: no-op in {rel} (replace identical to find — propose a real change)"); return 0
            pending[target] = new
        for target, content in pending.items():
            target.write_text(content); print(f"  edited: {target.name}")
        return len(edits)
    # whole-file fallback
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


# Old name kept as an alias so existing imports keep working.
apply_changes = apply_proposal


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
    # ERRORS = events that crashed mid-build (e.g. a corrupt OSM trace point). Recorded as
    # status=error so a recurring crash is visible HERE and prioritised, not lost to the Actions log.
    errored = [e for e in idx.values() if status(e) == "error"]
    err_msgs = {}
    for e in errored:
        m = (e.get("error") or "?")[:60]
        err_msgs[m] = err_msgs.get(m, 0) + 1
    top_err = sorted(err_msgs.items(), key=lambda kv: -kv[1])[:3]
    err_line = (f" ERRORS (crashed mid-build, suppressing coverage -> FIX THESE FIRST)={len(errored)}"
                + (": " + ", ".join(f"{m} x{n}" for m, n in top_err) if top_err else "") + ".") if errored else ""
    # SELF-AUDIT: non-success entries whose relation_m/trace_m, at the best integer lap count (1..6),
    # lands in 4800-5200 -> current code should map them (stale) OR a best-integer-N lap rule would.
    # x2 cases self-heal (build_cache prioritises them); x3+/x5 need a generalised lap rule = your job.
    def _bestn(v): return min(range(1, 7), key=lambda n: abs(n * v - 5000))
    recov = []
    for k, e in idx.items():
        if status(e) == "success":
            continue
        for fld in ("relation_m", "trace_m"):
            v = e.get(fld)
            if v and 4800 <= _bestn(v) * v <= 5200:
                recov.append((k, _bestn(v))); break
    multilap = [k for k, n in recov if n >= 3]
    rec_line = (f" AUDIT: {len(recov)} non-success entries look RECOVERABLE (best lap-multiple in band). "
                f"{len(multilap)} need a best-integer-N lap rule (N>=3), e.g. {multilap[:6]} - generalising "
                f"the x2 doubling to N laps would map these.") if recov else ""
    return (f"INDEX outcomes (of {len(idx)} attempted): success={counts['success']} "
            f"({trusted} trusted GPS-trace, {provisional} PROVISIONAL relation-sourced -> upgrade to "
            f"real 09:00 traces), failed(off-tolerance, index.json only)={counts['failed']}, gap={counts['gap']}. "
            f"Of the failed: ~{single_lap} have a ~2.0-2.8km relation (likely ONE LAP of a 2-lap parkrun "
            f"— consider doubling), ~{near_miss} are near-misses just outside 4.8-5.2km (often an "
            f"incomplete relation — consider way-chaining/gap-bridging). Sample failed: {sample}.{err_line}{rec_line}")
