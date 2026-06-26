#!/usr/bin/env python3
"""Per-country coverage report.

Writes coverage_by_country.json and refreshes the "Coverage by country" table in README.md:
each country's TOTAL adult parkruns (from the parkrun event list) vs MAPPED (locked in index.json).
Run after a cache build. Kept OUT of build_cache.py (the AI's algorithm file) so that stays lean.

Network-resilient: the event list is cached ~weekly (.events_cache.json) so this rarely hits the
network and is kind to OSM; if the fetch fails (e.g. we were just rate-limited) it falls back to the
cache, and failing that to the last coverage_by_country.json - so the README's worldwide tally still
updates from the always-current index.json instead of freezing.
"""
import json, os, re, time
from collections import defaultdict
import build_cache as bc

# parkrun countrycode -> display name (derived from each country's parkrun domain).
COUNTRY_NAMES = {
    97: "United Kingdom", 3: "Australia", 85: "South Africa", 42: "Ireland", 74: "Poland",
    98: "United States", 32: "Germany", 65: "New Zealand", 14: "Canada", 46: "Japan",
    64: "Netherlands", 44: "Italy", 88: "Sweden", 23: "Denmark", 67: "Norway", 30: "Finland",
    4: "Austria", 82: "Singapore", 54: "Lithuania", 57: "Malaysia",
}
README = os.path.join(bc.HERE, "README.md")
OUT = os.path.join(bc.HERE, "coverage_by_country.json")
EVENTS_CACHE = os.path.join(bc.HERE, ".events_cache.json")
EVENTS_TTL_S = 7 * 86400          # parkrun's event list changes slowly; refetch ~weekly (kind to OSM)
START, END = "<!-- COVERAGE-BY-COUNTRY:START -->", "<!-- COVERAGE-BY-COUNTRY:END -->"


def _events():
    """Cached event features (eventname + countrycode). Cached ~weekly so report.py rarely hits the
    network and NEVER crashes the build when we are being rate-limited. Returns the features or None."""
    if os.path.exists(EVENTS_CACHE) and (time.time() - os.path.getmtime(EVENTS_CACHE)) < EVENTS_TTL_S:
        try:
            return json.load(open(EVENTS_CACHE))
        except Exception:
            pass
    try:
        feats = json.loads(bc._get(bc.EVENTS_URL))["events"]["features"]
        json.dump(feats, open(EVENTS_CACHE, "w"))
        return feats
    except Exception:
        if os.path.exists(EVENTS_CACHE):
            try:
                return json.load(open(EVENTS_CACHE))
            except Exception:
                pass
        return None


def build():
    index = json.load(open(os.path.join(bc.HERE, "index.json"))) if os.path.exists(os.path.join(bc.HERE, "index.json")) else {}
    feats = _events()
    if feats is not None:
        total, mapped = defaultdict(int), defaultdict(int)
        for f in feats:
            p = f["properties"]
            if p.get("seriesid") != bc.ADULT:        # adult 5k only (exclude junior 2k)
                continue
            cc = p.get("countrycode")
            total[cc] += 1
            if bc.is_locked(index.get(p["eventname"])):
                mapped[cc] += 1
        rows = sorted(([cc, COUNTRY_NAMES.get(cc, f"country {cc}"), total[cc], mapped[cc]] for cc in total),
                      key=lambda r: -r[2])
        world_t, world_m = sum(total.values()), sum(mapped.values())
        json.dump({"world_total": world_t, "world_mapped": world_m,
                   "countries": [{"code": c, "name": n, "total": t, "mapped": m} for c, n, t, m in rows]},
                  open(OUT, "w"), indent=1)
        return rows, world_t, world_m
    # FALLBACK: event list unavailable (e.g. just rate-limited). Keep last-known per-country rows but
    # refresh the worldwide MAPPED tally from the always-current index.json, so the README still updates.
    world_m = sum(1 for e in index.values() if bc.is_locked(e))
    try:
        prev = json.load(open(OUT))
    except Exception:
        prev = {}
    rows = [[c["code"], c["name"], c["total"], c["mapped"]] for c in prev.get("countries", [])]
    world_t = prev.get("world_total") or 0
    return rows, world_t, world_m


def render_readme(rows, world_t, world_m):
    lines = [f"_Worldwide: {world_m}/{world_t} parkruns mapped across {len(rows)} countries "
             f"(UK first; other countries fill in as the global rollout sweeps them)._", "",
             "| Country | Mapped / Total |", "|---|---|"]
    for cc, name, t, m in rows:
        lines.append(f"| {name} | {m}/{t} |")
    block = START + "\n" + "\n".join(lines) + "\n" + END
    if not os.path.exists(README):
        return
    r = open(README).read()
    if START in r and END in r:
        r = re.sub(re.escape(START) + r".*?" + re.escape(END), lambda _: block, r, flags=re.S)
    else:
        r = r.rstrip() + "\n\n## Coverage by country\n\n" + block + "\n"
    open(README, "w").write(r)


def main():
    rows, wt, wm = build()
    render_readme(rows, wt, wm)
    print(f"country report: {wm}/{wt} mapped across {len(rows)} countries")


if __name__ == "__main__":
    main()
