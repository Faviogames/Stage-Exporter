"""Replay TV cameras that keep the car framed and in focus.

The builder clones Hafren South's 38 TvCameraComponents, places them along our route (7.6 m off the road, one every ~154 m)
and scales Hafren's spline distances to our length, but keeps Hafren's focal lengths, which were set for Hafren's own
camera-to-road distances; 7 of them are fixed wide shots (no tracking, no zoom) aimed at a Hafren corner. Owner drives
2026-11-09: the car was not always framed or in focus; then, with tracking and zoom fixed, the car still often left the
cameras' range.

Here the route is cut where a camera loses the car: from the start of a section, candidates abeam points 20-130 m
ahead (both sides, several distances from the road and heights) are tried, and the one that keeps the car (car-height
route points, every RUN_STEP_M) in clear line of sight over the WRCG terrain for the longest stretch wins; the next
camera takes over where that one loses the car (RUN_M: 25-180 m). Hafren's cameras are reused and more are cloned into
the same BC_ReplayCamerasActor_C. Every camera gets the tracking and focus settings of a full tracking camera: 20 of
Hafren's carry a tracking window of their own (TrackingSettings Start/EndSplineDist at Hafren distances), outside which
they stay at a fixed rotation, and kept it (owner 2026-11-09: fixed cameras the car drives out of). Its zoom is
rebuilt from its distance to the route over its section, so the car fills about the same share of the frame all along.
"""
import copy
import math

import numpy as np

SECTION_M = 70.0
SENSOR_MM = 23.76          # Hafren's cameras: FieldOfView 3.78 deg at 360 mm
FRAME_M = 11.0             # frame width at the car: a ~4.3 m car fills ~40 % of it
FOCAL_MM = (20.0, 800.0)
STEP_CM = 1000.0           # one zoom key every 10 m of spline
SIDES = (-1, 1)
OFFSETS_M = (6.0, 10.0, 16.0)
HEIGHTS_M = (2.5, 5.0)
AHEAD_M = (15.0, 35.0, 55.0, 80.0, 105.0)    # camera abeam this far ahead of its section start
RUN_M = (20.0, 110.0)                         # a camera's stretch: shortest, longest
RUN_STEP_M = 4.0
MAX_VIEW_M = 120.0                            # farther than this the car is too small
OCC_MARGIN_M = 200.0
TREE_SPECIES = ("pine", "maple", "oak", "olive", "cypress", "tree")
CAR_H_M = 1.0
CLEAR_M = 0.3
# a big jump gets its own camera (owner 2026-11-10, Arganil: "resalta salto grande en la parte final"): low and to the
# side of the take-off, from FOCUS_BEFORE_M before it to FOCUS_AFTER_M after it (the flight and the landing)
FOCUS_BEFORE_M, FOCUS_AFTER_M = 30.0, 45.0
FOCUS_OFFSETS_M, FOCUS_HEIGHTS_M = (12.0, 18.0, 25.0), (1.5, 3.0)
JUMP_TOKENS = ("BIG_JUMP",)
TEXEL, ORIGIN = 0.5, -2048.0


def _prop(e, name):
    return next((p for p in e["Data"] if p.get("Name") == name), None)


def _field(struct, name):
    return next((p for p in struct["Value"] if p.get("Name") == name), None)


def _focal(dist_m):
    return float(np.clip(SENSOR_MM * dist_m / FRAME_M, *FOCAL_MM))


def _h(H, x, y):
    """Height at x, y of a grid: the WRCG heightfield (0.5 m, origin -2048 m) or (Z, x0, y0) for a window of it."""
    Z, ox, oy = H if isinstance(H, tuple) else (H, ORIGIN, ORIGIN)
    i = np.clip(np.round((np.asarray(y) - oy) / TEXEL).astype(int), 0, Z.shape[0] - 1)
    j = np.clip(np.round((np.asarray(x) - ox) / TEXEL).astype(int), 0, Z.shape[1] - 1)
    return np.asarray(Z[i, j], float)


def occlusion(stage_dir, H, route_xy, log=print):
    """(Z, x0, y0): the terrain around the route with what blocks a camera's view on it: the props' and walls'
    collision (collision_extra.npz) and WRCG's trees (their crown footprint up to their height). Owner 2026-11-09:
    with the terrain only, cameras were chosen that could not see the car behind trees and houses."""
    import json
    from pathlib import Path
    stage_dir = Path(stage_dir)
    R = np.asarray(route_xy, float)[:, :2]
    Hz, ox, oy = H if isinstance(H, tuple) else (H, ORIGIN, ORIGIN)   # (grid, x0, y0): SSS arenas are smaller
    org, size = np.array([ox, oy]), np.array([Hz.shape[1], Hz.shape[0]])
    lo = np.floor((R.min(0) - OCC_MARGIN_M - org) / TEXEL).astype(int).clip(0, size - 1)
    hi = np.ceil((R.max(0) + OCC_MARGIN_M - org) / TEXEL).astype(int).clip(1, size)
    Z = np.array(Hz[lo[1]:hi[1], lo[0]:hi[0]], np.float32)
    x0, y0 = ox + lo[0] * TEXEL, oy + lo[1] * TEXEL

    def stamp(x, y, z):
        j = np.round((x - x0) / TEXEL).astype(int)
        i = np.round((y - y0) / TEXEL).astype(int)
        ok = (i >= 0) & (i < Z.shape[0]) & (j >= 0) & (j < Z.shape[1])
        np.maximum.at(Z, (i[ok], j[ok]), z[ok].astype(np.float32))

    n_props = n_trees = 0
    f = stage_dir / "collision_extra.npz"
    if f.exists():
        d = np.load(f)
        P, T = d["positions"].astype(float), d["triangles"].astype(np.int64)
        for k in range(0, len(T), 200000):                    # triangle corners and a few points inside
            A, B, C = P[T[k:k + 200000, 0]], P[T[k:k + 200000, 1]], P[T[k:k + 200000, 2]]
            for u, v in ((1, 0), (0, 1), (0, 0), (1 / 3, 1 / 3), (0.5, 0.5), (0.5, 0), (0, 0.5)):
                Q = A + u * (B - A) + v * (C - A)
                stamp(Q[:, 0], Q[:, 1], Q[:, 2])
        n_props = len(T)
    f = stage_dir / "vegetation" / "instances.json"
    if f.exists():
        trees = [t for t in json.loads(f.read_text(encoding="utf-8"))["instances"]
                 if t.get("src") == "wrcg" and any(k in str(t.get("species", "")) for k in TREE_SPECIES)]
        for t in trees:
            r = max(0.5, 0.35 * float(t.get("foot_m") or 2.0))
            h = float(t.get("wrcg_h_m") or 6.0)
            g = np.arange(-r, r + 1e-6, TEXEL)
            gx, gy = np.meshgrid(g, g)
            m = gx * gx + gy * gy <= r * r
            stamp(t["x"] + gx[m], t["y"] + gy[m], np.full(int(m.sum()), t["z"] + 0.9 * h))
        n_trees = len(trees)
    log(f"replay cameras: line of sight over the terrain, {n_props} prop/wall collision triangles and {n_trees} trees")
    return Z, x0, y0


def _visible(H, cam, pts):
    """Share of pts (N,3, WRCG m, car height) in clear line of sight from cam over the terrain."""
    ok = 0
    for p in pts:
        d = np.linalg.norm(p[:2] - cam[:2])
        n = max(2, int(d / 2.0))
        t = np.linspace(0.05, 0.95, n)
        seg = cam[None, :] + (p - cam)[None, :] * t[:, None]
        ok += bool(np.all(_h(H, seg[:, 0], seg[:, 1]) < seg[:, 2] - CLEAR_M))
    return ok / max(len(pts), 1)


def _run(H, cam, pts):
    """How many of pts (in order) are in clear line of sight from cam before the first one that is not (or too far)."""
    for k, p in enumerate(pts):
        if np.linalg.norm(p[:2] - cam[:2]) > MAX_VIEW_M:
            return k
        d = np.linalg.norm(p[:2] - cam[:2])
        n = max(2, int(d / 2.0))
        t = np.linspace(0.05, 0.95, n)
        seg = cam[None, :] + (p - cam)[None, :] * t[:, None]
        if not np.all(_h(H, seg[:, 0], seg[:, 1]) < seg[:, 2] - CLEAR_M):
            return k
    return len(pts)


def jump_points(stage_dir, look_m=180.0):
    """Route s (route_centerline_1m.csv) of the take-off of each big jump WRCG's co-driver calls (JUMP_TOKENS): the
    sharpest crest of the road surface (collision_all_prm.npz) within look_m after the call."""
    import json
    from pathlib import Path
    stage_dir = Path(stage_dir)
    try:
        pn = json.loads((stage_dir / "pacenotes.json").read_text(encoding="utf-8"))
        mk = json.loads((stage_dir / "markers.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    at = {p["name"]: p.get("route_s_m") for p in mk.get("pacenotes", [])}
    calls = sorted(at[n["name"]] for n in pn.get("notes", []) if at.get(n["name"]) is not None and
                   any(t in JUMP_TOKENS for t in n.get("tokens", [])))
    if not calls:
        return []
    R = np.loadtxt(stage_dir / "route_centerline_1m.csv", delimiter=",", skiprows=1)
    P = np.load(stage_dir / "collision_all_prm.npz")["positions"].astype(float)
    out = []
    for c in calls:
        m = (R[:, 0] >= c) & (R[:, 0] <= c + look_m)
        Q = R[m]
        if len(Q) < 20:
            continue
        box = (P[:, 0] > Q[:, 1].min() - 5) & (P[:, 0] < Q[:, 1].max() + 5) & (P[:, 1] > Q[:, 2].min() - 5) &               (P[:, 1] < Q[:, 2].max() + 5)
        near = P[box]
        z = []
        for q in Q:
            d = np.hypot(near[:, 0] - q[1], near[:, 1] - q[2])
            k = np.argsort(d)[:6]
            z.append(np.median(near[k, 2]) if len(k) and d[k[0]] < 2.0 else q[3])
        z = np.array(z)
        slope = np.gradient(z, Q[:, 0])
        bend = np.roll(slope, -4) - np.roll(slope, 4)            # change of slope over 8 m; crests are negative
        bend[:4] = bend[-4:] = 0.0
        i = int(np.argmin(bend))
        if bend[i] < -0.12:
            out.append(float(Q[i, 0]))
    return out


def plan(spline_wrcg, H, occ=None, focus=()):
    """[(s0_m, s1_m, camera xyz WRCG m, share of the stretch in sight)]: each camera covers the stretch from s0 on
    where it keeps the car in sight (over occ, else the terrain H); the next one takes over there. focus: spline s of
    big jumps, each with a camera of its own (FOCUS_*)."""
    occ = H if occ is None else occ
    focus = sorted(float(f) for f in focus)
    P = np.asarray(spline_wrcg, float)
    s = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(P[:, :2], axis=0), axis=1))])
    at = lambda v: np.array([np.interp(v, s, P[:, c]) for c in range(3)])
    out, s0 = [], 0.0
    while s0 < s[-1] - 1.0:
        here = next((f for f in focus if abs(s0 - (f - FOCUS_BEFORE_M)) < 1.0), None)
        nxt = next((f - FOCUS_BEFORE_M for f in focus if f - FOCUS_BEFORE_M > s0 + 1.0), None)
        aheads, offsets, heights = ((FOCUS_BEFORE_M,), FOCUS_OFFSETS_M, FOCUS_HEIGHTS_M) if here is not None else             (AHEAD_M, OFFSETS_M, HEIGHTS_M)
        grid = np.arange(s0, min(s0 + RUN_M[1], s[-1]) + 1e-6, RUN_STEP_M)
        road = np.array([at(v) for v in grid])
        road[:, 2] += CAR_H_M
        best = None
        for ahead in aheads:
            sa = min(s0 + ahead, s[-1])
            a, b = at(max(sa - 2, 0)), at(min(sa + 2, s[-1]))
            t = (b - a)[:2] / max(np.linalg.norm((b - a)[:2]), 1e-6)
            left = np.array([-t[1], t[0]])
            base = at(sa)
            for side in SIDES:
                for off in offsets:
                    xy = base[:2] + left * side * off
                    gz = float(_h(H, xy[0], xy[1]))
                    if float(_h(occ, xy[0], xy[1])) > gz + 0.5:      # inside a tree, a wall or a house
                        continue
                    for hh in heights:
                        cam = np.array([xy[0], xy[1], max(gz, base[2] - 1.0) + hh])
                        n = _run(occ, cam, road)
                        score = n - 0.05 * off / 6.0
                        if best is None or score > best[0]:
                            best = (score, cam, n)
        if best is None:                                       # every candidate inside something: a plain one
            base = at(min(s0 + AHEAD_M[1], s[-1]))
            best = (0.0, np.array([base[0], base[1], base[2] + HEIGHTS_M[-1]]), 0)
        n = best[2]
        s1 = min(max(s0 + n * RUN_STEP_M, s0 + RUN_M[0]), s[-1])
        if here is not None:                               # the jump camera: through the landing
            s1 = min(max(s1, here + FOCUS_AFTER_M), s[-1])
        elif nxt is not None and s1 > nxt:                 # the camera before a jump hands over at its approach
            s1 = nxt
        if s[-1] - s1 < RUN_M[0]:                          # no short last stretch
            s1 = s[-1]
        share = min(1.0, n * RUN_STEP_M / max(s1 - s0, 1e-6))
        out.append((s0, s1, best[1], share))
        s0 = s1
    return out


def fix(dst, spline_wrcg, spline_ue, H, to_ue, log=print, occ=None, focus=()):
    """spline_wrcg / spline_ue: gameplay CenterSpline points (pre-start + route), WRCG m and UE cm; H: WRCG heights
    (0.5 m grid, origin -2048 m); to_ue: WRCG m (N,3) -> UE cm (N,3)."""
    cams = [i for i in range(1, len(dst.exports) + 1) if dst.class_name(i) == "TvCameraComponent"]
    if not cams:
        return 0
    # a full tracking camera without a tracking window of its own
    tmpl_i = next(i for i in cams if _prop(dst.exp(i), "ZoomSettings") and
                  _field(_prop(dst.exp(i), "TrackingSettings"), "bEnableTracking") and
                  not any(_field(_prop(dst.exp(i), "TrackingSettings"), n) for n in
                          ("StartSplineDist", "EndSplineDist", "bEnableStartSplineDist", "bEnableEndSplineDist")))
    tmpl = dst.exp(tmpl_i)
    t_track, t_focus, t_zoom = (copy.deepcopy(_prop(tmpl, n)) for n in ("TrackingSettings", "FocusSettings", "ZoomSettings"))
    t_key = copy.deepcopy(t_zoom["Value"][0])
    owner = tmpl["OuterIndex"]
    inst = _prop(dst.exp(owner), "InstanceComponents")
    root = _prop(tmpl, "AttachParent")["Value"]

    sections = plan(spline_wrcg, H, occ, focus)
    while len(cams) < len(sections):                           # more cameras: clones of a full one, same actor and root
        m = dst.clone(dst, tmpl_i, owner, preset={root: root, owner: owner})
        new = m[tmpl_i]
        name = f"TvCamera{len(cams)}"
        dst.add_name(name)
        dst.exp(new)["ObjectName"] = name
        item = copy.deepcopy(inst["Value"][0])
        item["Name"], item["Value"] = str(len(inst["Value"])), new
        inst["Value"].append(item)
        cams.append(new)
    s_ue = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(spline_ue, axis=0), axis=1))])
    vis = []
    for k, i in enumerate(cams):
        e = dst.exp(i)
        if k >= len(sections):                                   # spare Hafren cameras: parked past the end
            _prop(e, "StartSplineDist")["Value"] = float(s_ue[-1] + 100000.0 + k)
            continue
        s0, s1, cam_w, share = sections[k]
        vis.append(share)
        cam = to_ue(cam_w[None, :])[0]
        v = _prop(e, "RelativeLocation")["Value"][0]["Value"]
        v["X"], v["Y"], v["Z"] = (float(c) for c in cam)
        s0c, s1c = s0 * 100.0, s1 * 100.0
        _prop(e, "StartSplineDist")["Value"] = float(s0c)
        tr = _prop(e, "TrackingSettings")                      # the template's: tracking all along, no window
        tr["Value"] = copy.deepcopy(t_track["Value"])
        _field(tr, "bEnableTracking")["Value"] = True
        p0 = np.array([np.interp(s0c, s_ue, spline_ue[:, c]) for c in range(3)])
        yaw = math.degrees(math.atan2(p0[1] - cam[1], p0[0] - cam[0]))
        for n in ("StartingRotation", "EndingRotation"):
            f = _field(tr, n)
            if f is not None:
                r = f["Value"][0]["Value"] if isinstance(f["Value"], list) else f["Value"]
                r["Pitch"], r["Yaw"], r["Roll"] = 0.0, yaw, 0.0
        r = _prop(e, "RelativeRotation")
        if r is not None:
            rv = r["Value"][0]["Value"]
            rv["Pitch"], rv["Yaw"], rv["Roll"] = 0.0, yaw, 0.0
        fo = _prop(e, "FocusSettings")
        fo["Value"] = copy.deepcopy(t_focus["Value"])
        grid = np.arange(s0c, max(s1c, s0c + STEP_CM) + 1.0, STEP_CM)
        foc = [_focal(np.linalg.norm(np.array([np.interp(gg, s_ue, spline_ue[:, c]) for c in range(3)]) - cam) / 100.0)
               for gg in grid]
        keys = []
        for j in range(len(grid) - 1):
            key = copy.deepcopy(t_key)
            key["Name"] = str(j)
            for f, val in (("StartSplineDist", grid[j]), ("EndSplineDist", grid[j + 1]), ("StartFocalLength", foc[j]),
                           ("EndFocalLength", foc[j + 1]), ("InterpExp", 1.0)):
                _field(key, f)["Value"] = float(val)
            keys.append(key)
        zs = _prop(e, "ZoomSettings")
        if zs is None:
            zs = copy.deepcopy(t_zoom)
            e["Data"].append(zs)
        zs["Value"] = keys
        for n in ("DefaultFocalLength", "CurrentFocalLength"):
            if _prop(e, n):
                _prop(e, n)["Value"] = foc[0]
        if _prop(e, "FieldOfView"):
            _prop(e, "FieldOfView")["Value"] = math.degrees(2 * math.atan(SENSOR_MM / (2 * foc[0])))
        dst._add_export_names(e)
    lens = [b - a for a, b, _, _ in sections]
    log(f"replay cameras: {len(sections)} cameras, each until it loses the car ({min(lens):.0f}-{max(lens):.0f} m, "
        f"median {np.median(lens):.0f}; car in sight: median {np.median(vis):.0%}, worst {min(vis):.0%}); "
        f"all tracking with tracked focus, zoom every {STEP_CM / 100:.0f} m")
    return len(sections)
