#!/usr/bin/env python3
"""Build a cache of UK parkrun 5k courses as GPX, from OpenStreetMap only.

Per parkrun (worked south to north), in priority order:
  1. OSM route relation named "... parkrun" near the start, if within +/-8% of 5k.
  2. else reconstruct from open Saturday-09:00 GPS traces (multi-lap aware).
  3. else log a gap.

Data is OpenStreetMap (c) OpenStreetMap contributors, ODbL. Be kind to OSM: hard rate-limit,
descriptive User-Agent, early-stop paging, on-disk caching. Not for bulk harvesting.
"""
import json, os, re, math, time, datetime, urllib.request, urllib.parse, argparse, subprocess

UA = "5k-9am-osm-route-cache/0.1 (personal; +https://github.com/lukeet332)"
EVENTS_URL = "https://images.parkrun.com/events.json"
OVERPASS = "https://overpass-api.de/api/interpreter"
OSM_TRACKPOINTS = "https://api.openstreetmap.org/api/0.6/trackpoints"
UK_CC, ADULT = 97, 1
TARGET = 5000
REL_LO, REL_HI = 4800, 5200      # keep a relation only this close to 5k
HALF_REL_LO, HALF_REL_HI = 2300, 2800  # half-distance band: candidates for doubling
SANE_LO, SANE_HI = 1500, 9000    # off-tolerance finds in this band -> diagnostics; wider = noise
RATE_S = 1.5            # min seconds between network calls
HAVANT = (50.87577, -0.97557)    # rollout anchor: start here, work north
COVERAGE_REFINE = 0.80  # re-query accurate courses only once >=80% are within tolerance

HERE = os.path.dirname(os.path.abspath(__file__))
ROUTES = os.path.join(HERE, "routes")
TRACECACHE = os.path.join(HERE, ".tracecache")

try:
    from zoneinfo import ZoneInfo
    _LON = ZoneInfo("Europe/London")
    def local(dt): return dt.astimezone(_LON)
except Exception:                          # crude BST fallback
    def local(dt):
        y = dt.year
        def ls(m):
            d = datetime.date(y, m, 31); return d - datetime.timedelta(days=(d.weekday()+1) % 7)
        return dt + datetime.timedelta(hours=1 if ls(3) <= dt.date() < ls(10) else 0)

def H(a, b, c, e):
    R = 6371000.0; dl = math.radians(c-a); dn = math.radians(e-b)
    h = math.sin(dl/2)**2 + math.cos(math.radians(a))*math.cos(math.radians(c))*math.sin(dn/2)**2
    return 2*R*math.asin(min(1, math.sqrt(h)))

def length(pts): return sum(H(pts[i-1][0], pts[i-1][1], pts[i][0], pts[i][1]) for i in range(1, len(pts)))

def assemble(ways):
    """Greedily chain unordered member ways into one polyline, flipping to connect endpoints."""
    rem = [list(w) for w in ways if len(w) >= 2]
    if not rem:
        return []
    chain = rem.pop(0)
    while rem:
        tail = chain[-1]; bi = 0; flip = False; bd = float("inf")
        for i, w in enumerate(rem):
            ds = H(tail[0], tail[1], w[0][0], w[0][1])
            de = H(tail[0], tail[1], w[-1][0], w[-1][1])
            if ds < bd: bd, bi, flip = ds, i, False
            if de < bd: bd, bi, flip = de, i, True
        nx = rem.pop(bi)
        chain += nx[::-1] if flip else nx
    return chain

_last = [0.0]
def _throttle():
    wait = RATE_S - (time.time() - _last[0])
    if wait > 0: time.sleep(wait)
    _last[0] = time.time()

# Ban-safety: if OSM throttles us (429) too often in a run, stop early rather than keep hammering it.
RATE_LIMIT_HITS = [0]
MAX_RATE_LIMIT_HITS = 6

def _get(url, data=None, timeout=70):
    _throttle()
    req = urllib.request.Request(url, data=data, headers={"User-Agent": UA})
    for attempt in range(4):
        try:
            return urllib.request.urlopen(req, timeout=timeout).read().decode("utf-8", "ignore")
        except urllib.error.HTTPError as ex:
            if ex.code == 429:
                RATE_LIMIT_HITS[0] += 1     # OSM throttling us
            if ex.code in (429, 504) and attempt < 3:
                time.sleep(5 * (attempt + 1)); continue
            raise

def load_events():
    raw = _get(EVENTS_URL)
    feats = json.loads(raw)["events"]["features"]
    uk = []
    for f in feats:
        p = f["properties"]
        if p["countrycode"] == UK_CC and p["seriesid"] == ADULT:
            lon, lat = f["geometry"]["coordinates"]
            uk.append({"name": p["eventname"], "long": p["EventLongName"],
                       "loc": p.get("EventLocation", ""), "lat": lat, "lon": lon})
    hav = HAVANT[0]
    north = sorted([e for e in uk if e["lat"] >= hav], key=lambda e: e["lat"])   # Havant northward
    south = sorted([e for e in uk if e["lat"] < hav], key=lambda e: -e["lat"])    # then southern outliers
    ordered = north + south
    for i, e in enumerate(ordered):
        e["ord"] = i
    return ordered

def relation_course(lat, lon, name):
    q = (f'[out:json][timeout:60];relation["route"~"running|foot|walking|hiking"]'
         f'["name"](around:2000,{lat},{lon});out geom;')
    try:
        r = json.loads(_get(OVERPASS, urllib.parse.urlencode({"data": q}).encode()))
    except Exception:
        return None
    best = None
    for el in r.get("elements", []):
        nm = el.get("tags", {}).get("name", "").lower()
        if "parkrun" not in nm and name not in nm:
            continue
        ways = [[(g["lat"], g["lon"]) for g in (m.get("geometry") or [])] for m in el.get("members", [])]
        chain = assemble(ways)                       # way-chaining for a trustworthy length
        if len(chain) < 2 or min(H(lat, lon, p[0], p[1]) for p in chain) > 500:
            continue
        L = length(chain)
        if best is None or abs(L - TARGET) < abs(best[1] - TARGET):
            best = (el["tags"]["name"], L, chain)
    return best

CACHE_TTL_S = 30 * 86400   # reuse a cached trace page for 30 days, then re-fetch

def _trace_cache_file(name, half_m, page):
    """Cache path keyed on event + search radius + page, so a changed radius re-fetches rather than
    reusing a different-bbox response."""
    return os.path.join(TRACECACHE, f"{name}_h{int(half_m)}_p{page}.gpx")

def trace_points(name, lat, lon, half_m=900, max_pages=5):
    os.makedirs(TRACECACHE, exist_ok=True)
    dlat = half_m/111000.0; dlon = half_m/(111000.0*math.cos(math.radians(lat)))
    bbox = f"{lon-dlon:.6f},{lat-dlat:.6f},{lon+dlon:.6f},{lat+dlat:.6f}"
    pts = []
    for p in range(max_pages):
        cf = _trace_cache_file(name, half_m, p)
        txt = None
        if os.path.exists(cf) and (time.time() - os.path.getmtime(cf)) < CACHE_TTL_S:
            cached = open(cf, errors="ignore").read()
            if "<gpx" in cached:                 # ignore a poisoned/partial cached body
                txt = cached
        if txt is None:
            try:
                txt = _get(f"{OSM_TRACKPOINTS}?bbox={bbox}&page={p}", timeout=60)
            except Exception:
                break
            if txt and "<gpx" in txt:            # persist only a valid gpx body
                open(cf, "w").write(txt)
        n = 0
        for m in re.finditer(r'<trkpt lat="([\-\d.]+)" lon="([\-\d.]+)"[^>]*>(.*?)</trkpt>', txt, re.S):
            n += 1
            tm = re.search(r'<time>([^<]+)</time>', m.group(3))
            if not tm:
                continue
            try:
                t = datetime.datetime.fromisoformat(tm.group(1).replace("Z", "+00:00"))
            except Exception:
                continue
            pts.append((float(m.group(1)), float(m.group(2)), t))
        if n < 5000:
            break          # last page reached
    return pts

def trace_courses_multi(name, lat, lon):
    pts = trace_points(name, lat, lon)
    # group by date: Saturday/Christmas/New-Year, local 09:00-09:45, anchored within 150m of the start
    traces = {}
    for la, lo, t in pts:
        ldt = local(t)
        is_saturday = ldt.weekday() == 5
        is_christmas_day = ldt.month == 12 and ldt.day == 25
        is_new_years_day = ldt.month == 1 and ldt.day == 1

        if (is_saturday or is_christmas_day or is_new_years_day) and ldt.hour == 9 and ldt.minute < 45:
            date = ldt.date().isoformat()
            traces.setdefault(date, []).append((la, lo, t))
    valid_traces = []
    for date, win in traces.items():
        win = sorted(win, key=lambda p: p[2])
        if not win or H(lat, lon, win[0][0], win[0][1]) > 150:
            continue
        path = [win[0]]; d = 0.0
        for p in win[1:]:
            d += H(path[-1][0], path[-1][1], p[0], p[1]); path.append(p)
            if d >= 5500 or (p[2] - path[0][2]).total_seconds() > 2700:   # ~5.5k or past 09:45
                break
        valid_traces.append([(p[0], p[1]) for p in path])
    if not valid_traces:
        return None
    # pointwise mean across traces
    minlen = min(len(t) for t in valid_traces)
    avg_path = []
    for i in range(minlen):
        las = [t[i][0] for t in valid_traces]
        los = [t[i][1] for t in valid_traces]
        avg_path.append((sum(las)/len(las), sum(los)/len(los)))
    avg_len = length(avg_path)
    first_date = list(traces.keys())[0]
    return avg_len, avg_path, first_date

def trace_course(name, lat, lon):
    res = trace_courses_multi(name, lat, lon)
    if res:
        return res
    # fallback: single trace
    pts = trace_points(name, lat, lon)
    win = []
    for la, lo, t in pts:
        ldt = local(t)
        is_saturday = ldt.weekday() == 5
        is_christmas_day = ldt.month == 12 and ldt.day == 25
        is_new_years_day = ldt.month == 1 and ldt.day == 1
        if (is_saturday or is_christmas_day or is_new_years_day) and ldt.hour == 9 and ldt.minute < 45:
            win.append((la, lo, t))
    win = sorted(win, key=lambda p: p[2])

    if not win or H(lat, lon, win[0][0], win[0][1]) > 150:
        return None
    path = [win[0]]; d = 0.0
    for p in win[1:]:
        d += H(path[-1][0], path[-1][1], p[0], p[1]); path.append(p)
        if d >= 5500 or (p[2] - path[0][2]).total_seconds() > 2700:   # ~5.5k or past 09:45
            break
    return length(path), [(p[0], p[1]) for p in path], win[0][2].date().isoformat()

_VERSION = [None]
def algo_version():
    """Latest git release tag (e.g. 'v1.2.0'), or 'dev' if untagged. Stamped into every GPX + index
    entry as provenance so a later run can tell which version built a course. Cached."""
    if _VERSION[0] is None:
        try:
            out = subprocess.run(["git", "describe", "--tags", "--abbrev=0"],
                                 cwd=HERE, capture_output=True, text=True)
            _VERSION[0] = out.stdout.strip() or "dev"
        except Exception:
            _VERSION[0] = "dev"
    return _VERSION[0]

def write_gpx(name, longname, pts, source):
    os.makedirs(ROUTES, exist_ok=True)
    with open(os.path.join(ROUTES, f"{name}.gpx"), "w") as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n')
        f.write(f'<gpx version="1.1" creator="5k-9am-osm-route-cache {algo_version()}" xmlns="http://www.topografix.com/GPX/1/1">\n')
        f.write(f'  <metadata><desc>Derived from OpenStreetMap ((c) OpenStreetMap contributors, ODbL). source={source}; built_by={algo_version()}</desc></metadata>\n')
        f.write(f'  <trk><name>{longname}</name><trkseg>\n')
        for la, lo in pts:
            f.write(f'    <trkpt lat="{la:.6f}" lon="{lo:.6f}"/>\n')
        f.write('  </trkseg></trk>\n</gpx>\n')

def build_one(ev):
    """Resolve one parkrun. Returns a rich dict (status success/failed/gap + diagnostics) that IS the
    index.json schema. routes/<name>.gpx holds only successful geometry (for the app); index.json logs
    every attempt incl. relation_m/trace_m (for the AI). A real 09:00 GPS trace is the true course and
    wins over a relation; relation successes ship provisional:true (curated, not GPS-verified)."""
    name, lat, lon = ev["name"], ev["lat"], ev["lon"]
    rel = relation_course(lat, lon, name)        # (relname, dist, chain) or None
    tr = trace_course(name, lat, lon)            # (dist, pts, date) or None
    diag = {"relation_m": round(rel[1]) if rel else None,
            "trace_m": round(tr[0]) if tr else None}

    if tr and REL_LO <= tr[0] <= REL_HI:          # success: real 09:00 GPS trace (trusted)
        write_gpx(name, ev["long"], tr[1], "osm_9am_trace")
        return {"source": "osm_9am_trace", "distance_m": round(tr[0]), "status": "success",
                "provisional": False, "trace_date": tr[2], **diag}

    # double a half-distance trace (2-lap course, GPS only)
    if tr and HALF_REL_LO <= tr[0] <= HALF_REL_HI:
        doubled_path = tr[1] + tr[1]
        doubled_len = 2 * length(tr[1])
        if REL_LO <= doubled_len <= REL_HI:
            write_gpx(name, ev["long"], doubled_path, "osm_9am_trace_doubled")
            return {"source": "osm_9am_trace_doubled", "distance_m": round(doubled_len), "status": "success",
                    "provisional": False, "trace_date": tr[2], **diag}
    if rel and REL_LO <= rel[1] <= REL_HI:        # success: OSM relation (provisional)
        write_gpx(name, ev["long"], rel[2], "osm_relation")
        return {"source": "osm_relation", "distance_m": round(rel[1]), "status": "success",
                "provisional": True, **diag}

    # double a half-distance relation. Use 2*length(lap), NOT length(lap+lap): concatenation adds a
    # phantom jump from lap end back to start, overshooting and losing real 2-lap courses.
    if rel and HALF_REL_LO <= rel[1] <= HALF_REL_HI:
        doubled_chain = rel[2] + rel[2]
        doubled_len = 2 * length(rel[2])
        if REL_LO <= doubled_len <= REL_HI:
            write_gpx(name, ev["long"], doubled_chain, "osm_relation_doubled")
            return {"source": "osm_relation_doubled", "distance_m": round(doubled_len), "status": "success",
                    "provisional": True, **diag}

    # not a success: no geometry. drop any stale success GPX from a prior run.
    stale = os.path.join(ROUTES, f"{name}.gpx")
    if os.path.exists(stale):
        os.remove(stale)

    cands = []                                    # failed: off-tolerance find -> index.json log only
    if rel and SANE_LO <= rel[1] <= SANE_HI:
        cands.append(("osm_relation_offdist", rel[1], None))
    if tr  and SANE_LO <= tr[0]  <= SANE_HI:
        cands.append(("osm_9am_trace_offdist", tr[0], tr[2]))

    # relations whose doubled length is sane but out of tolerance -> diagnostic
    if rel and HALF_REL_LO <= rel[1] <= HALF_REL_HI:
        doubled_len = 2 * length(rel[2])
        if SANE_LO <= doubled_len <= SANE_HI and not (REL_LO <= doubled_len <= REL_HI):
            cands.append(("osm_relation_doubled_offdist", doubled_len, None))

    # half-distance traces that fail to double into tolerance
    if tr and HALF_REL_LO <= tr[0] <= HALF_REL_HI:
        doubled_len = 2 * length(tr[1])
        if SANE_LO <= doubled_len <= SANE_HI and not (REL_LO <= doubled_len <= REL_HI):
            cands.append(("osm_9am_trace_doubled_offdist", doubled_len, tr[2]))

    if cands:
        src, dist, date = min(cands, key=lambda c: abs(c[1] - TARGET))
        r = {"source": src, "distance_m": round(dist), "status": "failed", **diag}
        if date:
            r["trace_date"] = date
        return r

    return {"source": None, "distance_m": None, "status": "gap", **diag}   # gap: no usable data

def is_locked(entry):
    """True iff a course is cached within the 4.8-5.2km tolerance."""
    return bool(entry) and entry.get("distance_m") and REL_LO <= entry["distance_m"] <= REL_HI

def _git(*a):
    try:
        subprocess.run(["git", *a], cwd=HERE, check=True, capture_output=True)
        return True
    except Exception as e:
        print("  git:", getattr(e, "stderr", e))
        return False

def write_coverage(index, events):
    """Write coverage.json: the live tally driving the README badge and repo description. Called after
    each success so the count tracks in real time. Always green: every mapped course is a success."""
    total = len(events)
    locked = sum(1 for e in events if is_locked(index.get(e["name"])))
    pct = round(100 * locked / total, 1) if total else 0.0
    json.dump({"schemaVersion": 1, "label": "parkruns successfully mapped",
               "message": f"{locked}/{total} ({pct}%)", "color": "brightgreen",
               "locked": locked, "total": total, "percent": pct},
              open(os.path.join(HERE, "coverage.json"), "w"), indent=1)
    return locked, total, pct

def commit_route(name, res):
    """Push this one resolved route immediately. If main moved under us, rebase and retry once."""
    _git("add", "-A")
    _git("-c", "user.name=cache-bot", "-c", "user.email=cache-bot@users.noreply.github.com",
         "commit", "-m", f"cache: {name} [{res['status']}] ({res['source']}, {res['distance_m']}m)")
    if not _git("push"):
        _git("pull", "--rebase", "origin", "main")
        _git("push")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="max OPEN parkruns to query this run (0 = all open)")
    ap.add_argument("--commit-each", action="store_true", help="git commit+push each route the moment it locks (real-time)")
    args = ap.parse_args()
    events = load_events()
    today = datetime.date.today().isoformat()
    index_path = os.path.join(HERE, "index.json")
    index = json.load(open(index_path)) if os.path.exists(index_path) else {}

    total = len(events)
    locked = sum(1 for e in events if is_locked(index.get(e["name"])))
    refine = (locked / total if total else 0.0) >= COVERAGE_REFINE
    print(f"coverage {locked}/{total} ({locked/total:.0%}) within 4.8-5.2km -> "
          f"{'REFINE (re-querying accurate ones too)' if refine else 'GAP-FILL (skipping accurate ones)'}")

    # candidates: gaps + inaccurate (or everything once >=80% accurate). Rotate by last_tried so a
    # perpetual gap can't hog the budget: never-tried first (Havant->north), then oldest-tried first.
    cands = [e for e in events if refine or not is_locked(index.get(e["name"]))]
    cands.sort(key=lambda e: ((index.get(e["name"]) or {}).get("last_tried", ""), e["ord"]))
    if args.limit:
        cands = cands[:args.limit]

    tally = {"success": 0, "failed": 0, "gap": 0}
    for ev in cands:
        try:
            res = build_one(ev)
        except Exception as ex:
            print(f"  {ev['name']:<24} ERROR {ex}"); continue
        entry = {"long": ev["long"], "lat": ev["lat"], "lon": ev["lon"], "last_tried": today,
                 "built_by": algo_version(), **res}
        index[ev["name"]] = entry
        json.dump(index, open(index_path, "w"), indent=1, sort_keys=True)   # save incrementally
        st = res["status"]
        tally[st] = tally.get(st, 0) + 1
        print(f"  {ev['name']:<24} {st:<8} {(res.get('source') or '-'):<24} {res.get('distance_m') or ''}")
        if args.commit_each and st == "success":   # real-time: push each course as it locks
            write_coverage(index, events)
            commit_route(ev["name"], res)
        if RATE_LIMIT_HITS[0] >= MAX_RATE_LIMIT_HITS:   # ban-safety: OSM throttling us
            print(f"\nOSM rate-limited us {RATE_LIMIT_HITS[0]}x - stopping this run early to stay safe. "
                  f"The next scheduled run resumes from here (rotation).")
            break

    # ban-safety signal for the self-chaining workflow: leave a .throttled marker (gitignored) so the
    # next run backs off instead of chaining straight back in. Absent on a clean run.
    throttled = os.path.join(HERE, ".throttled")
    if RATE_LIMIT_HITS[0] >= MAX_RATE_LIMIT_HITS:
        open(throttled, "w").write(str(RATE_LIMIT_HITS[0]))
    elif os.path.exists(throttled):
        os.remove(throttled)

    locked2, _, _ = write_coverage(index, events)   # final sync
    print(f"\nprocessed {len(cands)}: {tally['success']} success, {tally['failed']} failed (off-tol diagnostics), "
          f"{tally['gap']} gap. coverage now {locked2}/{total} ({locked2/total:.0%}).")

if __name__ == "__main__":
    main()
