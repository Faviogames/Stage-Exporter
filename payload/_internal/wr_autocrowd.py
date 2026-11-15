"""Automatic spectator spots for stages whose WRCG graph has few (owner 2026-11-14: "publico automatico").

Spectators gather where a rally has them: outside of tight corners and at junction mouths, not on long empty stretches.
auto_spots() picks those places from the route's geometry, leaves WRCG's own spots and any prop alone, and returns
positions like wr_crowd.wrcg_spectators() does ([(group, world position)], WRCG metres), which wr_crowd.add_crowd turns
into ACR spectators (ground snapped, facing the road, red flares in the front row).

Options (stage config "auto_crowd": true or a dict): every_m (one cluster per this much route, default 600),
min_turn_deg (corner turn over TURN_WINDOW_M to count as a hotspot, 65), size ([5, 5] people), offset_m ([9, 14]
from the road centre), side ("inside" of the bend, or "outside"), clear_m (8: least distance to any road), seed, max_clusters (8).
Known limits: the ground slope is not checked (add_crowd only snaps to the ground), so a cluster can end up on a steep bank.
"""
import numpy as np

TURN_WINDOW_M = 30.0
KEEP_FROM_WRCG_M = 20.0        # no automatic cluster this near a WRCG spectator spot
BLOCK_MARGIN_M = 1.0           # nor this near a prop that has a collision
MIN_BETWEEN_M = 150.0          # route distance between two clusters
# owner 2026-11-14: too many "suicidal" extras, and a drift runs wide: the inside of the bend (where a real crowd stands),
# 9-14 m from the road, at least CLEAR_M from every other stretch of road, few clusters
DEFAULTS = {"every_m": 600.0, "min_turn_deg": 65.0, "size": [5, 5], "offset_m": [9.0, 14.0], "seed": 1, "max_clusters": 8,
            "side": "inside", "clear_m": 8.0}


def _resample(route, step=2.0):
    r = np.asarray(route, float)
    seg = np.hypot(*np.diff(r[:, :2], axis=0).T)
    s = np.concatenate([[0.0], np.cumsum(seg)])
    t = np.arange(0.0, s[-1], step)
    return s, t, np.c_[np.interp(t, s, r[:, 0]), np.interp(t, s, r[:, 1]), np.interp(t, s, r[:, 2])]


def hotspots(route, min_turn_deg, step=2.0):
    """[(s_m, turn_deg, outside_normal_xy)] local maxima of the heading change over TURN_WINDOW_M, strongest first."""
    _, t, P = _resample(route, step)
    k = int(round(TURN_WINDOW_M / step / 2))
    if len(P) < 4 * k:
        return []
    d = np.diff(P[:, :2], axis=0)
    h = np.unwrap(np.arctan2(d[:, 1], d[:, 0]))
    turn = np.zeros(len(h))
    for i in range(k, len(h) - k):
        turn[i] = h[i + k] - h[i - k]
    out = []
    for i in range(k, len(h) - k):
        a = abs(np.degrees(turn[i]))
        if a >= min_turn_deg and a >= abs(np.degrees(turn[max(i - k, 0):i + k + 1])).max() - 1e-9:
            tang = np.array([np.cos(h[i]), np.sin(h[i])])
            left = np.array([-tang[1], tang[0]])
            out.append((float(t[i]), float(a), -left if turn[i] > 0 else left))   # outside of the turn
    return sorted(out, key=lambda x: -x[1])


def auto_spots(route, existing_xy=(), blockers=(), opts=True):
    """route (N,3) WRCG metres; existing_xy: WRCG spectator spots (x, y) already there; blockers: [(lo_xy, hi_xy)] of props."""
    o = dict(DEFAULTS, **(opts if isinstance(opts, dict) else {}))
    rng = np.random.default_rng(int(o["seed"]))
    s, t, P = _resample(route)
    E = np.asarray(list(existing_xy), float).reshape(-1, 2)
    B = [(np.asarray(lo, float) - BLOCK_MARGIN_M, np.asarray(hi, float) + BLOCK_MARGIN_M) for lo, hi in blockers]
    want = min(int(o["max_clusters"]), max(1, int(round(s[-1] / float(o["every_m"])))))
    chosen, spots = [], []
    for st, turn, out_n in hotspots(route, float(o["min_turn_deg"])):
        if len(chosen) >= want:
            break
        if st < 40.0 or st > s[-1] - 40.0 or any(abs(st - c) < MIN_BETWEEN_M for c in chosen):
            continue                                              # not on the start / finish lines, not bunched up
        i = int(np.searchsorted(t, st))
        away = out_n if o["side"] == "outside" else -out_n
        c = P[i, :2] + away * rng.uniform(*o["offset_m"])
        if np.hypot(P[:, 0] - c[0], P[:, 1] - c[1]).min() < float(o["clear_m"]):
            continue                                              # a hairpin's other leg, a junction: too near a road
        if len(E) and np.hypot(E[:, 0] - c[0], E[:, 1] - c[1]).min() < KEEP_FROM_WRCG_M:
            continue
        tang = np.array([-away[1], away[0]])
        n = int(rng.integers(o["size"][0], o["size"][1] + 1))
        pts = []
        for j in range(n):
            q = c + tang * (j - n / 2) * 1.1 + away * rng.uniform(-1.5, 1.5)
            if any((q > lo).all() and (q < hi).all() for lo, hi in B):
                continue
            if np.hypot(P[:, 0] - q[0], P[:, 1] - q[1]).min() < float(o["clear_m"]):
                continue                                          # every person keeps clear of the road, not only the centre
            pts.append(q)
        if len(pts) < max(4, n // 2):
            continue
        chosen.append(st)
        spots += [(f"AUTO_{len(chosen):02d}", np.array([q[0], q[1], P[i, 2]])) for q in pts]
    return spots, chosen


def main():      # self-check: a 90-degree left corner gets one cluster, inside by default and clear of the road
    ang = np.linspace(0, np.pi / 2, 60)
    arc = np.c_[np.r_[np.arange(0, 200, 5.0), 200 + 40 * np.sin(ang), np.full(40, 240.0)],
                np.r_[np.zeros(40), 40 - 40 * np.cos(ang), 40 + np.arange(1, 41) * 5.0], np.zeros(140)]
    o = {"every_m": 100, "min_turn_deg": 35, "clear_m": 4.0}
    sp_in, ch = auto_spots(arc, opts=o)
    sp_out, ch2 = auto_spots(arc, opts=dict(o, side="outside"))
    assert len(ch) == 1 and len(ch2) == 1 and sp_in and sp_out, (ch, ch2)
    cin, cout = np.mean([q for _, q in sp_in], axis=0), np.mean([q for _, q in sp_out], axis=0)
    assert cin[1] > cout[1] and cin[0] < cout[0], (cin, cout)      # inside is up-left of the bend, outside down-right
    assert not auto_spots(np.c_[np.arange(0, 500, 5.0), np.zeros(100), np.zeros(100)])[1]
    print("wr_autocrowd self-check ok")


if __name__ == "__main__":
    main()
