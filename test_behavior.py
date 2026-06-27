#!/usr/bin/env python3
"""
Behavioural self-test — EDITABLE expectations (CI, runs alongside selftest.py). Pins the EXACT current
behaviour of tunable algorithm logic (specific best_lap_n outputs, the doubled distance + source label,
the exact audit set). Unlike selftest.py (frozen invariants), the AI author MAY edit THIS file - but only
to UPDATE a behavioural expectation that a genuine algorithm change legitimately alters, NEVER to weaken
or delete a constitutional invariant (those live in selftest.py and stay frozen). The arbiter + CodeRabbit
verify every edit here is a legit behavioural update, not a loosened safety net. No network; pure + fast.
"""
import os, sys
import build_cache as bc


def main():
    # 1) best_lap_n exact regression examples (the current outputs; selftest.py freezes the PROPERTY).
    assert bc.best_lap_n(2450) == 2, f"best_lap_n(2450)={bc.best_lap_n(2450)} (expected 2)"
    assert bc.best_lap_n(1666) == 3, f"best_lap_n(1666)={bc.best_lap_n(1666)} (expected 3)"
    assert bc.best_lap_n(1000) == 5, f"best_lap_n(1000)={bc.best_lap_n(1000)} (expected 5)"

    # 2) relation doubling EXACT: a ~2.5k single-lap relation doubles to ~2x the lap PATH length and is
    #    labelled osm_relation_doubled. (selftest.py freezes only the invariant: in-band success.)
    lap = [(51.5 + i * 0.0001, -0.1) for i in range(226)]   # straight ~2.5k open line
    lap_len = bc.length(lap)
    ev = {"name": "behavdouble", "long": "Double parkrun", "lat": 51.5, "lon": -0.1}
    orig_rel, orig_tr = bc.relation_course, bc.trace_course
    try:
        bc.relation_course = lambda *_: ("X parkrun", lap_len, lap)
        bc.trace_course = lambda *_: None
        r = bc.build_one(ev)
        assert r["source"] == "osm_relation_doubled", f"doubled source label changed: {r.get('source')}"
        assert abs(r["distance_m"] - round(2 * lap_len)) <= 1, \
            f"doubled distance must be 2x the lap path ({round(2 * lap_len)}), got {r['distance_m']}"
    finally:
        bc.relation_course, bc.trace_course = orig_rel, orig_tr
        f = os.path.join(bc.ROUTES, "behavdouble.gpx")
        if os.path.exists(f):
            os.remove(f)

    # 3) self-audit EXACT recoverable set for a fixed fixture (selftest.py freezes only the invariants:
    #    gaps/successes never flagged, a recoverable failed entry is flagged).
    fake = {
        "twolap":   {"status": "failed",  "relation_m": 2450},   # x2 = 4900 -> recoverable
        "threelap": {"status": "failed",  "relation_m": 1666},   # x3 = 4998 -> recoverable
        "tracedbl": {"status": "failed",  "trace_m": 2500},      # x2 = 5000 -> recoverable (via trace)
        "genuine":  {"status": "gap",     "relation_m": None},   # no data -> NOT
        "wayoff":   {"status": "failed",  "relation_m": 3300},   # best N=2 -> 6600, out of band -> NOT
        "done":     {"status": "success", "relation_m": 2450},   # already success -> NOT
    }
    flagged = {r[0] for r in bc.audit_recoverable(fake)}
    assert flagged == {"twolap", "threelap", "tracedbl"}, f"audit_recoverable set changed: {flagged}"

    print("OK (behaviour) — best_lap_n examples + doubled distance/source + audit set pass.")


if __name__ == "__main__":
    try:
        main()
    except AssertionError as e:
        print("BEHAVIOUR SELFTEST FAILED:", e); sys.exit(1)
