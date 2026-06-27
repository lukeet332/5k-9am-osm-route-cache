#!/usr/bin/env python3
"""
Caching self-test — the CI gate. No network: it builds a synthetic Saturday-09:00 trace
fixture and asserts the reconstruction still yields a ~5k course, plus checks the pure
geometry helpers. If this fails, the caching mechanism is broken and the PR must not merge.
"""
import os, datetime, sys
import build_cache as bc

def make_fixture():
    os.makedirs(bc.TRACECACHE, exist_ok=True)
    # 301 points, ~16.7 m apart => ~5.0 km, on Sat 2025-04-12 from 08:01Z (= 09:01 BST local).
    base = datetime.datetime(2025, 4, 12, 8, 1, 0, tzinfo=datetime.timezone.utc)
    lat0, lon0 = 51.5, -0.1
    pts = []
    for i in range(301):
        t = base + datetime.timedelta(seconds=i * 1.5)
        pts.append(f'<trkpt lat="{lat0 + i*0.00015:.6f}" lon="{lon0:.6f}">'
                   f'<time>{t.strftime("%Y-%m-%dT%H:%M:%SZ")}</time></trkpt>')
    gpx = '<?xml version="1.0"?><gpx><trk><trkseg>' + "".join(pts) + '</trkseg></trk></gpx>'
    # Write under the SAME cache key trace_points() looks up (event + default half_m + page),
    # so the test is a deterministic cache hit with no network.
    open(bc._trace_cache_file("selftest", 900, 0), "w").write(gpx)
    return lat0, lon0

def main():
    # 1) geometry helpers
    chain = bc.assemble([[(0.0, 0.0), (1.0, 0.0)], [(2.0, 0.0), (1.0, 0.0)]])  # 2nd reversed
    assert chain[0] == (0.0, 0.0) and chain[-1] == (2.0, 0.0), f"assemble broke: {chain}"
    d = bc.length([(51.5, 0.0), (51.5, 0.001)])
    assert 60 <= d <= 80, f"length off: {d}"

    # 2) end-to-end trace reconstruction (the caching mechanism)
    lat0, lon0 = make_fixture()
    res = bc.trace_course("selftest", lat0, lon0)
    assert res is not None, "trace_course returned nothing for a valid Saturday-9am fixture"
    L, pts, date = res
    assert bc.REL_LO <= L <= bc.REL_HI, f"reconstructed distance out of success band: {L:.0f} m"
    assert date == "2025-04-12", f"wrong trace date: {date}"
    assert len(pts) > 50, f"too few points: {len(pts)}"

    # 3) lock predicate honours the fixed tolerance — pin the EXACT constitutional bars (4800–5200),
    #    not just a loose midpoint, so the boundaries can't silently drift in code.
    assert bc.is_locked({"distance_m": 5000}) and not bc.is_locked({"distance_m": 4300})
    assert bc.is_locked({"distance_m": 4810}) and not bc.is_locked({"distance_m": 4790}), "REL_LO bar drifted"
    assert bc.is_locked({"distance_m": 5190}) and not bc.is_locked({"distance_m": 5210}), "REL_HI bar drifted"

    # 3b) version provenance: algo_version() always yields a non-empty string (tag or 'dev'),
    #     and write_gpx stamps it into the GPX creator so each course records what built it.
    v = bc.algo_version()
    assert isinstance(v, str) and v, f"algo_version must be a non-empty string, got {v!r}"
    bc.write_gpx("selftestver", "Selftest", [(51.5, -0.1), (51.5001, -0.1)], "osm_relation")
    vf = os.path.join(bc.ROUTES, "selftestver.gpx")
    gpx_txt = open(vf).read()
    os.remove(vf)
    assert f'creator="5k-9am-osm-route-cache {v}"' in gpx_txt, "GPX creator must carry the version stamp"

    # 4) source trust hierarchy: a real 09:00 trace WINS over a relation (both in-tolerance) and is
    #    trusted; a relation-only success ships but is flagged provisional (not GPS-verified).
    line = [(51.5, -0.1), (51.5, -0.1)]
    ev = {"name": "selftesttrust", "long": "Selftest parkrun", "lat": 51.5, "lon": -0.1}
    orig_rel, orig_tr = bc.relation_course, bc.trace_course
    try:
        bc.relation_course = lambda lat, lon, name: ("X parkrun", 5010.0, line)
        bc.trace_course = lambda name, lat, lon: (4990.0, line, "2025-04-12")
        r = bc.build_one(ev)
        assert r["source"] == "osm_9am_trace" and r["provisional"] is False, f"trace must win+trust: {r}"
        bc.trace_course = lambda name, lat, lon: None
        r = bc.build_one(ev)
        assert r["source"] == "osm_relation" and r["provisional"] is True, f"relation must be provisional: {r}"
    finally:
        bc.relation_course, bc.trace_course = orig_rel, orig_tr
        f = os.path.join(bc.ROUTES, "selftesttrust.gpx")
        if os.path.exists(f):
            os.remove(f)

    # 5) relation DOUBLING measures TWO LAPS, not a phantom seam. A 2-lap parkrun's relation is
    #    ONE lap (~2.5k); doubling must report ~2x the lap's PATH length. length(lap+lap) is WRONG —
    #    it adds a bogus segment from the lap's end back to its start, overshooting and pushing real
    #    2-lap courses out of the 4.8-5.2k success band (the "0 doublings, 2 offdist" we saw).
    lap = [(51.5 + i * 0.0001, -0.1) for i in range(226)]   # straight, open ~2.5k line
    lap_len = bc.length(lap)
    assert 2400 <= lap_len <= 2600, f"fixture lap not ~2.5k: {lap_len:.0f}"
    assert bc.REL_LO <= 2 * lap_len <= bc.REL_HI, f"fixture: two laps must be in-band: {2*lap_len:.0f}"
    assert bc.length(lap + lap) > bc.REL_HI, "fixture must expose the seam bug (self-concat overshoots)"
    ev2 = {"name": "selftestdouble", "long": "Double parkrun", "lat": 51.5, "lon": -0.1}
    orig_rel2, orig_tr2 = bc.relation_course, bc.trace_course
    try:
        bc.relation_course = lambda lat, lon, name: ("X parkrun", lap_len, lap)
        bc.trace_course = lambda name, lat, lon: None
        r = bc.build_one(ev2)
        assert r["status"] == "success" and r["source"] == "osm_relation_doubled", \
            f"a ~2.5k relation must double into a success, not get lost to the seam: {r}"
        assert abs(r["distance_m"] - round(2 * lap_len)) <= 1, \
            f"doubled distance must be 2x the lap path ({round(2*lap_len)}), got {r['distance_m']}"
    finally:
        bc.relation_course, bc.trace_course = orig_rel2, orig_tr2
        f = os.path.join(bc.ROUTES, "selftestdouble.gpx")
        if os.path.exists(f):
            os.remove(f)

    # 6) a single corrupt/extreme trace timestamp must skip that POINT, not abort the whole event.
    #    Regression: local()'s astimezone can throw "date value out of range" on a poisoned <time>;
    #    that exception used to escape the per-point loop and lose the entire course (it showed up as
    #    ~11 events/sweep "ERROR date value out of range", silently suppressing coverage). Now guarded.
    base = datetime.datetime(2025, 4, 12, 8, 1, 0, tzinfo=datetime.timezone.utc)
    lat0p, lon0p = 51.5, -0.1
    rows = []
    for i in range(301):
        t = base + datetime.timedelta(seconds=i * 1.5)
        rows.append(f'<trkpt lat="{lat0p + i*0.00015:.6f}" lon="{lon0p:.6f}">'
                    f'<time>{t.strftime("%Y-%m-%dT%H:%M:%SZ")}</time></trkpt>')
    gpxp = '<?xml version="1.0"?><gpx><trk><trkseg>' + "".join(rows) + '</trkseg></trk></gpx>'
    open(bc._trace_cache_file("selftestpoison", 900, 0), "w").write(gpxp)
    poison_t = base + datetime.timedelta(seconds=150 * 1.5)   # one mid-course point blows up in local()
    real_local = bc.local
    def poison_local(dt, lat=None, lon=None):
        if dt == poison_t:
            raise OverflowError("date value out of range")
        return real_local(dt, lat, lon)
    bc.local = poison_local
    try:
        resp = bc.trace_course("selftestpoison", lat0p, lon0p)
    finally:
        bc.local = real_local
    assert resp is not None, "one poisoned timestamp must not abort the whole trace"
    Lp = resp[0]
    assert bc.REL_LO <= Lp <= bc.REL_HI, f"poisoned-point trace still reconstructs ~5k: {Lp:.0f} m"

    # 7) self-audit flags recoverable entries (the stale 2-lap regression class) and only those: a
    #    non-success entry whose relation_m/trace_m hits the band at its best integer lap count must be
    #    flagged; a genuine no-data gap, an already-success entry, and a truly-off length must not.
    assert bc.best_lap_n(2450) == 2 and bc.best_lap_n(1666) == 3 and bc.best_lap_n(1000) == 5, "best_lap_n wrong"
    fake = {
        "twolap":   {"status": "failed",  "relation_m": 2450},   # x2 = 4900 -> recoverable
        "threelap": {"status": "failed",  "relation_m": 1666},   # x3 = 4998 -> recoverable
        "tracedbl": {"status": "failed",  "trace_m": 2500},      # x2 = 5000 -> recoverable (via trace)
        "genuine":  {"status": "gap",     "relation_m": None},   # no data -> NOT
        "wayoff":   {"status": "failed",  "relation_m": 3300},   # best N=2 -> 6600, out of band -> NOT
        "done":     {"status": "success", "relation_m": 2450},   # already success -> NOT
    }
    flagged = {r[0] for r in bc.audit_recoverable(fake)}
    assert flagged == {"twolap", "threelap", "tracedbl"}, f"audit_recoverable wrong: {flagged}"

    # 8) N-LAP PROPERTY INVARIANT (scalable - not a one-off fixture): across synthetic lap lengths,
    #    build_one MUST succeed EXACTLY when the lap is itself in-band OR best_lap_n (N>=2) lands N*lap in
    #    4.8-5.2k. Expectation derived from the SAME predicate the self-audit uses, so test + audit can't
    #    drift. Catches "no-op" generalisations whose N-lap branch is gated out before it runs (v0.6.0
    #    generalised the multiplier but kept the 2-lap entry gate, so it recovered nothing - RED here).
    ev_nlap = {"name": "selftestnlap", "long": "N-lap parkrun", "lat": 51.5, "lon": -0.1}
    orig_rel3, orig_tr3 = bc.relation_course, bc.trace_course
    bc.trace_course = lambda name, lat, lon: None
    try:
        for target in range(900, 5400, 100):
            k = max(2, round(target / 11.132))                 # ~11.1 m per 0.0001 deg latitude step
            lap = [(51.5 + i * 0.0001, -0.1) for i in range(k + 1)]
            Ln = bc.length(lap)                                # distinct name: don't clobber test-2's L
            n = bc.best_lap_n(Ln)
            expect = (bc.REL_LO <= Ln <= bc.REL_HI) or (n >= 2 and bc.REL_LO <= n * Ln <= bc.REL_HI)
            bc.relation_course = lambda lat, lon, name, _l=lap, _L=Ln: ("X parkrun", _L, _l)
            got = bc.build_one(ev_nlap)["status"] == "success"
            assert got == expect, f"N-lap invariant broken: lap~{Ln:.0f}m bestN={n} expect={expect} got_success={got}"
    finally:
        bc.relation_course, bc.trace_course = orig_rel3, orig_tr3
        fn = os.path.join(bc.ROUTES, "selftestnlap.gpx")
        if os.path.exists(fn):
            os.remove(fn)

    print(f"OK — reconstructed {L:.0f} m / {len(pts)} pts; helpers + lock + trust + doubling + error-guard + audit + n-lap-invariant pass.")

if __name__ == "__main__":
    try:
        main()
    except AssertionError as e:
        print("SELFTEST FAILED:", e); sys.exit(1)
