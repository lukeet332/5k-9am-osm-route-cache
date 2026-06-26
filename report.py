#!/usr/bin/env python3
"""Per-country coverage report.

Writes coverage_by_country.json and refreshes the "Coverage by country" table in README.md:
each country's TOTAL adult parkruns (from the live parkrun event list) vs MAPPED (locked in
index.json). Only the UK is swept today, so other countries show NA/<total> until the global
rollout reaches them. Run after a cache build. Kept OUT of build_cache.py (the AI's algorithm
file) so that file stays lean; reuses build_cache's helpers.
"""
import json, os, re
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
START, END = "<!-- COVERAGE-BY-COUNTRY:START -->", "<!-- COVERAGE-BY-COUNTRY:END -->"


def build():
    index_path = os.path.join(bc.HERE, "index.json")
    index = json.load(open(index_path)) if os.path.exists(index_path) else {}
    feats = json.loads(bc._get(bc.EVENTS_URL))["events"]["features"]
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


def render_readme(rows, world_t, world_m):
    lines = [f"_Worldwide: {world_m}/{world_t} parkruns mapped across {len(rows)} countries. "
             f"Only the UK is swept so far; others show NA until the global rollout reaches them._", "",
             "| Country | Mapped / Total |", "|---|---|"]
    for cc, name, t, m in rows:
        lines.append(f"| {name} | {(str(m)+'/'+str(t)) if m else 'NA/'+str(t)} |")
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
