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

    print(f"OK — reconstructed {L:.0f} m / {len(pts)} pts; helpers + lock + trust hierarchy pass.")

if __name__ == "__main__":
    try:
        main()
    except AssertionError as e:
        print("SELFTEST FAILED:", e); sys.exit(1)
