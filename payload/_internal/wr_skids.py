"""Tyre skid marks in the corners of tarmac stages: few long decals on the racing line, placed the way Munster's are.

ACR's MI_AsphaltDecalProceduralSkids_01 (parent M_MasterDecals_WorldSpace) draws T_TyreMarks_M's streaks in WORLD space:
their scale and direction do not follow the decal, so each decal must turn them itself, and Munster's three do so with
DecalColor.R = the rotation that lays the streaks along the decal's length (radians, any multiple of pi apart; worked out
from them: lengths heading -169.1 and -150.6 deg give 4.52 / 1.06 rad, Munster 7.69 = 4.52 + pi and 1.0). Ours used
Munster's three colours whatever their direction, so the streaks crossed the decals: short repeated dashes (owner
2026-11-09, twice: repeated and small). Munster's decals are also tilted to the road (pitch -84 to -87, roll), ~4.3 m
wide (Z 0.84-0.9) and 7-26 m long, and there are few of them.

Here: the tool's racing line (racing_line.compute); corners where it turns at least MIN_TURN_DEG with a radius under
MEDIUM_M (tight ones, under TIGHT_M, marked from LEAD_M before to LEAD_M after; medium ones from the apex on); along each,
ONE chain of decals end to end (OVERLAP), each as long as the curve allows (its middle within SAGITTA_M of the line,
LEN_M), on the racing line, tilted along the slope, its streaks turned along it (DecalColor.R), Munster's G, B, A.
"""
import copy
import json
import math
from pathlib import Path

import numpy as np

CELL = "wr_alsace/acr/Content/Levels/AlsaceS2Munster/_Generated_/1XXMH9FJVC7ZDS8TC9W2RQY3Z.json"
MATERIAL = "MI_AsphaltDecalProceduralSkids_01"
TIGHT_M, MEDIUM_M = 45.0, 90.0
MIN_TURN_DEG = 35.0
LEAD_M = 8.0
SAGITTA_M = 0.6
LEN_M = (10.0, 24.0)
OVERLAP = 0.12
WIDTH_SCALE = (0.8, 0.9)      # x 256 cm half width: ~4.1-4.6 m (Munster 0.84 / 0.9)
DEPTH_SCALE = 0.25            # +-64 cm of projection: camber
GBA = [(1.0, 1.0, -2.04), (1.0, 0.82, -2.04)]   # Munster's G, B, A
MAX_DECALS = 600


def _prop(e, name):
    return next((p for p in (e.get("Data") or []) if isinstance(p, dict) and p.get("Name") == name), None)


def corners(line_ue, step_cm=100.0):
    """Racing line resampled every metre (UE cm, (n,3)) and its corners [(i0, i1, apex, min radius m, turn deg)]."""
    P = np.asarray(line_ue, float)
    s = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(P[:, :2], axis=0), axis=1))])
    g = np.arange(0.0, s[-1], step_cm)
    q = np.stack([np.interp(g, s, P[:, c]) for c in range(3)], 1)
    hd = np.unwrap(np.arctan2(*np.gradient(q[:, :2], axis=0).T[::-1]))
    k = 8
    hd_s = np.convolve(hd, np.ones(2 * k + 1) / (2 * k + 1), mode="same")
    curv = np.gradient(hd_s) / (step_cm / 100.0)
    radius = 1.0 / np.maximum(np.abs(curv), 1e-6)
    out, i = [], 0
    while i < len(g):
        if radius[i] >= MEDIUM_M:
            i += 1
            continue
        j = i
        while j < len(g) and radius[j] < MEDIUM_M and np.sign(curv[j]) == np.sign(curv[i]):
            j += 1
        turn = abs(math.degrees(hd_s[min(j, len(g) - 1)] - hd_s[i]))
        if j - i >= 5 and turn >= MIN_TURN_DEG:
            apex = i + int(np.argmin(radius[i:j]))
            out.append((i, j, apex, float(radius[i:j].min()), turn))
        i = j
    return q, out


def _rotator(p0, p1):
    """UE rotator of a decal projecting down onto the road, its length (Y) from p0 to p1 (UE cm), Z = X x Y."""
    import tools.acrmod.props_visual as pv
    Y = (p1 - p0) / max(np.linalg.norm(p1 - p0), 1e-6)
    down = np.array([0.0, 0.0, -1.0])
    X = down - Y * float(down @ Y)
    X /= max(np.linalg.norm(X), 1e-9)
    Z = np.cross(X, Y)
    return tuple(float(v) for v in pv.ue_rotator(np.column_stack([X, Y, Z])))


def streak_rotation(p0, p1):
    """DecalColor.R that lays the world-space streaks along p0 -> p1."""
    h = math.atan2(p1[1] - p0[1], p1[0] - p0[0])
    return float((-(h - math.pi / 2)) % math.pi)


def plan(line_ue, rng):
    q, cs = corners(line_ue)
    lead = int(LEAD_M)
    decals = []                                  # (priority, p0, p1, width, gba)
    for (i0, i1, apex, rmin, turn) in cs:
        a0 = max(i0 - lead, 0) if rmin < TIGHT_M else apex
        a1 = min(i1 + lead, len(q) - 1)
        seg = int(round(float(np.clip(math.sqrt(8.0 * rmin * SAGITTA_M), *LEN_M))))
        step = max(4, int(round(seg * (1.0 - OVERLAP))))
        gba = GBA[int(rng.integers(len(GBA)))]
        width = float(rng.uniform(*WIDTH_SCALE))
        a = a0
        while a < a1 - 3:
            b = min(a + seg, a1)
            decals.append((abs((a + b) // 2 - apex) / max(rmin, 1.0), q[a], q[b], width * float(rng.uniform(0.95, 1.05)), gba))
            a += step
    return sorted(decals, key=lambda d: d[0])[:MAX_DECALS], cs


def add_skids(dst, work_acr, route_ue, log=print, prefix="WrcgSkid", seed=11, racing_ue=None):
    U = type(dst)
    cell = U(json.loads((Path(work_acr) / CELL).read_text(encoding="utf-8")))
    mat = next(-(k + 1) for k, x in enumerate(cell.imports) if x["ObjectName"] == MATERIAL)
    comps = [i for i in range(1, len(cell.exports) + 1)
             if cell.class_name(i) == "DecalComponent" and (_prop(cell.exp(i), "DecalMaterial") or {}).get("Value") == mat]
    comp_src = comps[0]
    color_tmpl = copy.deepcopy(_prop(cell.exp(comp_src), "DecalColor")["Value"])
    actor_src = cell.exp(comp_src)["OuterIndex"]
    level = next(i for i in range(1, len(dst.exports) + 1) if dst.class_name(i) == "Level")
    rng = np.random.default_rng(seed)
    line = np.asarray(racing_ue if racing_ue is not None else route_ue, float)
    decals, cs = plan(line, rng)
    for n, (_, p0, p1, width, gba) in enumerate(decals):
        mid = (p0 + p1) / 2.0
        m = dst.clone(cell, actor_src, level)
        actor = m[actor_src]
        name = f"{prefix}_{n}"
        dst.add_name(name)
        dst.exp(actor)["ObjectName"] = name
        dst.register_actor(level, actor)
        c = dst.exp(m[comp_src])
        v = _prop(c, "RelativeLocation")["Value"][0]["Value"]
        v["X"], v["Y"], v["Z"] = float(mid[0]), float(mid[1]), float(mid[2])
        r = _prop(c, "RelativeRotation")["Value"][0]["Value"]
        r["Pitch"], r["Yaw"], r["Roll"] = _rotator(p0, p1)
        sc = _prop(c, "RelativeScale3D")["Value"][0]["Value"]
        sc["X"], sc["Y"], sc["Z"] = DEPTH_SCALE, float(np.linalg.norm(p1 - p0)) / 2.0 / 256.0, width
        col = _prop(c, "DecalColor")
        if col is not None:
            col["Value"] = copy.deepcopy(color_tmpl)
            cv = col["Value"][0]["Value"]
            cv["R"], (cv["G"], cv["B"], cv["A"]) = streak_rotation(p0, p1), gba
    lens = [float(np.linalg.norm(p1 - p0)) / 100.0 for _, p0, p1, _, _ in decals]
    log(f"skid marks: {len(decals)} decals in {len(cs)} corners of the racing line (one chain per corner, "
        f"{min(lens, default=0):.0f}-{max(lens, default=0):.0f} m, streaks turned along each, tilted to the slope), "
        f"{MATERIAL} as Munster's")
    return len(decals)
