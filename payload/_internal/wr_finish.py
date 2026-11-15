"""Finish stop marshal: Hafren South's forward-stage BC_StopMarshalEndSequence_C, placed at our finish.

The builder adds only the start marshal: the end sequence's class is missing from bin/acr_stage.usmap, so UAssetAPI keeps
the actor as a RawExport (214 bytes of unversioned properties) and UMap.clone refuses it. Here the actor export is copied by
hand, every reference in its raw properties remapped (layout read from the stock cell, checked before use), and its
components cloned under it. Placement copies Hafren's layout relative to the road at the finish trigger: the marshal stands
3.3 m past BC_EndSequenceTrigger_C, 0.9 m right of the centreline, facing the incoming car; its ComeCloser trigger (a child
actor 37 m in front of him) comes along unchanged.
"""
import base64
import copy
import json
import math
import struct
import sys
from pathlib import Path

import numpy as np

CELL = "wr_cells_legacy/acr/Content/Levels/WalesS4HafrenSouth/_Generated_/9XYWDVYVYCEUG004BCIGGGZ1X.json"
ACTOR_CLASS = "BC_StopMarshalEndSequence_C"
# Hafren South forward finish, measured from the stock cells (BC_EndSequenceTrigger_C in 7FF9A0XR2..., marshal in 9XYWD...)
# Hafren's own offsets: 3.3 m past the stop trigger, 0.9 m right. The marshal goes with the stop control (the booth): at 20 m
# past it he stood apart from it and the game penalised 5 s after the booth (owner 2026-11-14); more room to brake is
# the stage's "stop_after_m" (the booth and the marshal together). Per stage "finish_marshal_*_m" still move him.
ALONG_CM, LEFT_CM, YAW_FROM_ROAD_DEG = 329.0, -93.0, 74.65

# raw property block of the stock actor: unversioned header, then values in schema order
HEADER = bytes.fromhex("000e03080b02100203021d024a021403")
OBJ_AT = (16, 20, 24, 28, 32)           # MarshalEndSequence, ComeCloser, Animation, Decal, RespawnBox
NAME_AT = (36, 44, 52, 60, 68, 76)      # Head/Body/Hat type, body/clothes/hat customisation
IMPORT_AT = 84                          # HeadPoseAsset
NAME2_AT = 88                           # MeshType
ARRAYS = ((96, 3), (120, 5))            # Accessories, BlueprintCreatedComponents: (count offset, count)
OBJ2_AT = (112, 116)                    # BodySkeletalMesh, RootComponent
RAW_SIZE = 214


def _i32(b, o):
    return struct.unpack_from("<i", b, o)[0]


def _check_layout(raw):
    if len(raw) != RAW_SIZE or raw[:16] != HEADER:
        return False
    return all(_i32(raw, o) == n for o, n in ARRAYS)


def _name_index(dst, s):
    dst.add_name(s)
    return dst.names.index(s)


def _remap_ref(i, mapping, cell, dst):
    if i > 0:
        return mapping[i]
    if i < 0:
        return dst.ensure_import(cell.import_key(i))
    return 0


def _remap_raw(raw, mapping, cell, dst):
    b = bytearray(raw)
    refs = list(OBJ_AT) + [IMPORT_AT] + list(OBJ2_AT)
    for o, n in ARRAYS:
        refs += [o + 4 + 4 * k for k in range(n)]
    for o in refs:
        struct.pack_into("<i", b, o, _remap_ref(_i32(b, o), mapping, cell, dst))
    for o in NAME_AT + (NAME2_AT,):
        struct.pack_into("<i", b, o, _name_index(dst, cell.names[_i32(b, o)]))
    return bytes(b)


def _prop(e, name):
    return next((p for p in (e.get("Data") or []) if isinstance(p, dict) and p.get("Name") == name), None)


def _vec(e, name):
    p = _prop(e, name)
    v = p["Value"][0]["Value"]
    return v


def _root_of(dst, actor):
    r = _prop(dst.exp(actor), "RootComponent")
    return r["Value"] if r else None


def add_finish_marshal(dst, work_acr, route_ue, ground, log=print, name="WrcgFinishMarshal", side_m=None, along_m=None, box_scale=None):
    U = type(dst)
    cell = U(json.loads((Path(work_acr) / CELL).read_text(encoding="utf-8")))
    src = next(i for i in range(1, len(cell.exports) + 1) if cell.class_name(i) == ACTOR_CLASS)
    raw = base64.b64decode(cell.exp(src)["Data"])
    if not _check_layout(raw):
        log("    finish marshal: unexpected raw layout of the stock actor, skipped")
        return False
    level = next(i for i in range(1, len(dst.exports) + 1) if dst.class_name(i) == "Level")
    trig = next((i for i in range(1, len(dst.exports) + 1) if dst.class_name(i) == "BC_EndSequenceTrigger_C"), None)
    if trig is None:
        log("    finish marshal: no BC_EndSequenceTrigger_C in the level, skipped")
        return False

    # the actor export, by hand
    e = copy.deepcopy(cell.exp(src))
    e["ObjectName"] = name
    dst.add_name(name)
    e["OuterIndex"] = level
    for k in ("ClassIndex", "TemplateIndex", "SuperIndex"):
        e[k] = _remap_ref(e[k], {}, cell, dst) if e[k] < 0 else 0
    dst.exports.append(e)
    actor = len(dst.exports)
    cell_level = next(i for i in range(1, len(cell.exports) + 1) if cell.class_name(i) == "Level")
    mapping = {src: actor, cell_level: level}
    # its components (and what they reference, e.g. the ComeCloser child actor), with the actor pre-mapped
    for c in [i for i in range(1, len(cell.exports) + 1) if cell.exp(i).get("OuterIndex") == src]:
        if c not in mapping:
            mapping.update(dst.clone(cell, c, actor, preset=dict(mapping)))
    e["Data"] = base64.b64encode(_remap_raw(raw, mapping, cell, dst)).decode()
    for k in ("SerializationBeforeSerializationDependencies", "CreateBeforeSerializationDependencies",
              "SerializationBeforeCreateDependencies"):
        e[k] = [_remap_ref(i, mapping, cell, dst) for i in e.get(k) or []]
    e["CreateBeforeCreateDependencies"] = [level]
    dst.register_actor(level, actor)
    # the ComeCloser child actor lives in the level too
    for s, d in mapping.items():
        if s not in (src, cell_level) and cell.exp(s).get("OuterIndex") == cell_level:
            dst.register_actor(level, d)

    # placement: road frame at the finish trigger
    tl = _vec(dst.exp(_root_of(dst, trig)), "RelativeLocation")
    tp = (float(tl["X"]), float(tl["Y"]))
    import numpy as np
    d = np.hypot(route_ue[:, 0] - tp[0], route_ue[:, 1] - tp[1])
    i = int(d.argmin())
    a, b = route_ue[max(i - 5, 0)], route_ue[min(i + 5, len(route_ue) - 1)]
    t = np.array([b[0] - a[0], b[1] - a[1]]); t /= np.linalg.norm(t)
    left = np.array([-t[1], t[0]])
    al = ALONG_CM if along_m is None else along_m * 100.0              # owner 2026-11-14: too close, easy to crash into
    lf = LEFT_CM if side_m is None else -side_m * 100.0
    xy = np.array(tp) + t * al + left * lf
    z = ground(float(xy[0]), float(xy[1]), float(tl["Z"]))
    road_yaw = math.degrees(math.atan2(t[1], t[0]))
    body = mapping[next(c for c in mapping if cell.exp(c).get("OuterIndex") == src and cell.class_name(c) == "CrowdSkeletalMeshComponent")]
    loc = _vec(dst.exp(body), "RelativeLocation")
    loc["X"], loc["Y"], loc["Z"] = float(xy[0]), float(xy[1]), float(z)
    rot = _vec(dst.exp(body), "RelativeRotation")
    rot["Pitch"], rot["Yaw"], rot["Roll"] = 0.0, road_yaw + YAW_FROM_ROAD_DEG, 0.0
    if box_scale is not None:                       # the marshal's respawn box (26 x 26 x 109 cm): scaled, 1 = Hafren's
        for sc_, dd in mapping.items():
            if "RespawnBox" in str(cell.class_name(sc_)):
                try:
                    be = _vec(dst.exp(dd), "BoxExtent")
                    for ax in ("X", "Y", "Z"):
                        be[ax] = float(be[ax]) * float(box_scale)
                    log(f"    finish marshal: respawn box x{float(box_scale):g}")
                except (StopIteration, KeyError, TypeError):
                    pass                                    # a component of that class without a box
    for s, dd in mapping.items():
        if s != cell_level:
            dst._add_export_names(dst.exp(dd))
    log(f"    finish marshal: Hafren's stop sequence {al/100:.1f} m past the finish trigger, "
        f"{-lf/100:.1f} m right of the road centre ({len(mapping)} exports)")
    return True


# --- the finish where WRCG has it, the stop control after it ------------------------------------------------------------

# ACR (Hafren South forward): the timing finish (the last RaceSector) at s 5253 m, the stop control
# (BC_EndSequenceTrigger_C, the stop marshal 3.3 m past it) 181 m later at 5434, the gameplay splines 140 m beyond. The
# builder put the finish and the stop trigger together 15 m before the end of the route, so the car crossed the line at
# speed, stopped farther on and the marshal stood on the line (owner 2026-11-09: Sanremo, then Sävar "un marshall en la
# meta en lugar de estar al siguiente punto de parada"). WRCG: the timing finish is at its STOP posts
# (STARTENDS/ENDING_<tag>/.../PLOT_STOP_*, = start + SECTIONS.CFG lap), the stop control (Marshal_Tent) 46-60 m later;
# the route often ends right there (Sävar at the posts, Sanremo 28 m past them), WRCG's road goes on.
# Here: the gameplay route goes on past the end of ours (WRCG's full track spline, then along the road collision), the
# timing finish moves onto WRCG's line and the stop trigger with the marshal goes by WRCG's tent, STOP_MIN_M..STOP_MAX_M
# past the line, with AFTER_STOP_M of spline left after it.
RUNOFF_MAX_M = 180.0
STOP_MIN_M, STOP_MAX_M, STOP_DEFAULT_M = 30.0, 150.0, 100.0   # WRCG's stop controls: 35-60 m after the line
AFTER_STOP_M = 30.0
FALLBACK_GAP_M = 40.0           # no road for a run-off: the timing line comes this far before the stop trigger
_LAYOUT = {}


def _finish_props(stage_dir, level, tag, route_xy, log=print):
    """World xyz of WRCG's finish-area markers of the stage: (line posts, stop-control posts, stop-control tents).
    Rally stages: STARTENDS/.../ENDING_<tag>/... with PLOT_STOP posts at the timing line and a Marshal_Tent after it.
    Super specials (Panzerplatte): .../STARTEND/ENDING_PART01 (the flying finish: PLOT02_END_RED posts) and
    ENDING_PART02 (the stop control: PLOT02_END_RED posts, tent, table, chairs) - found by the name of the group only,
    owner 2026-11-10: "el final de la etapa de Alemania esta mal, la meta no esta clara y el marshall ahi plantado solo"."""
    import re
    import tools.wrcg.prop_instances as pi
    line, stop, tents, checks = [], [], [], []
    try:
        inst, _ = pi.collect_instances(level, categories=("static", "dynamic", "decor", "spline", "clutter"),
                                       route_xy=route_xy, near_m=60.0, startends_stage=tag)
    except Exception as e:
        log(f"    finish: WRCG props not read ({e})")
        return line, stop, tents
    own = re.compile(rf"ENDING_{re.escape(tag)}(?![R0-9])", re.I) if tag else None
    # Panzerplatte: .../STARTEND/ENDING_PART01; Corsica: SS1/FR_SS1_STARTEND/EndSS1/ENDING_PART01 (and the reverse's
    # FR_SS1R_STARTEND at our start: not ours). Owner 2026-11-11 (Pietrosella): "la carpa del marshall de la llegada está
    # antes del marshall": the group was not recognised, the stop marshal went 100 m past the route's end, the tent
    # stayed where WRCG has it.
    sss = re.compile(r"STARTENDS?/(?:END\w*/)?ENDING_PART", re.I)
    reverse = re.compile(rf"(?<![A-Z0-9]){re.escape(tag)}R(?![0-9])", re.I) if tag else None
    for p in inst:
        path = p.path or ""
        if not ((own and own.search(path)) or sss.search(path)):
            continue
        if reverse and reverse.search(path) and not (own and own.search(path)):
            continue
        up = path.upper()
        last = up.rsplit("/", 1)[-1]
        xyz = np.asarray(p.world, float)[:3, 3].copy()
        if last.startswith("PLOT") and "START" not in last:
            if "CHECKPOINT" in last:
                if "ENDING_PART01" in up:                        # Corsica's flying finish: checkpoint boards only
                    checks.append(xyz)
            elif "PART01" in up:
                line.append(xyz)
            elif "PLOT_STOP" in last or "_END" in last:
                stop.append(xyz)
        elif re.match(r"MARSHALL?_TENT|TENT_", last) and "PART01" not in up:
            tents.append(xyz)
    return (line or checks), stop, tents


def _timing_finish_s(stage_dir, R):
    try:
        v = json.loads((stage_dir / "validation.json").read_text(encoding="utf-8"))
        m = json.loads((stage_dir / "markers.json").read_text(encoding="utf-8"))
        lap = (v.get("sections_cfg") or {}).get("LapLength_m")
        st = next((g["route_s_m"] for g in m["grids_and_checkpoints"] if g["name"] == "Start_Pos"), None)
        if lap and st is not None and st + lap <= R[-1, 0] + 1.0:
            return float(st + lap)
    except (OSError, ValueError, KeyError):
        pass
    return None


def wrcg_finish_s(stage_dir, level, tag, log=print):
    """Route s (m, route_centerline_1m.csv) of WRCG's finish line: the stage's STOP posts, else the timing finish."""
    stage_dir = Path(stage_dir)
    R = np.loadtxt(stage_dir / "route_centerline_1m.csv", delimiter=",", skiprows=1)
    line, stops, _ = _finish_props(stage_dir, level, tag, R[-400:, 1:3], log)
    stops = line or stops
    s = [float(R[int(np.argmin(np.hypot(R[:, 1] - t[0], R[:, 2] - t[1]))), 0]) for t in stops
         if np.hypot(R[:, 1] - t[0], R[:, 2] - t[1]).min() < 12.0]
    if s:
        return float(np.median(s)), "WRCG's STOP posts"
    f = _timing_finish_s(stage_dir, R)
    return (f, "the timing finish (start + SECTIONS.CFG lap)") if f is not None else (None, None)


def runoff(stage_dir, R, length_m, backward=False):
    """WRCG m points (about 1 m apart) continuing the route R (s, x, y, z rows) past its end (backward: before its
    start, the points going away from it): WRCG's full track spline (route_full_1m.csv) as far as it goes, then the
    middle of the road (collision_all_prm.npz) step by step."""
    stage_dir = Path(stage_dir)
    if backward:
        R = R[::-1]
    pts = []
    f = stage_dir / "route_full_1m.csv"
    if f.exists():
        F = np.loadtxt(f, delimiter=",", skiprows=1)
        d = np.hypot(F[:, 1] - R[-1, 1], F[:, 2] - R[-1, 2])
        j = int(d.argmin())
        if d[j] < 2.0:
            pts = [p for p in (F[max(j - int(length_m), 0):j, 1:4][::-1] if backward else
                               F[j + 1:j + 1 + int(length_m), 1:4])]
    road = np.load(stage_dir / "collision_all_prm.npz")["positions"].astype(float)
    cur = np.asarray(pts[-1] if pts else R[-1, 1:4], float)
    back = np.vstack([R[-15:, 1:4]] + ([np.array(pts[-15:])] if pts else []))
    t = back[-1, :2] - back[0, :2]
    t /= max(np.linalg.norm(t), 1e-9)
    near = road[np.hypot(road[:, 0] - cur[0], road[:, 1] - cur[1]) < length_m + 60.0]
    step = 2.0
    while len(pts) < length_m and len(near):
        q = cur[:2] + t * step
        nrm = np.array([-t[1], t[0]])
        rel = near[:, :2] - q
        along, across = rel @ t, rel @ nrm
        m = (np.abs(along) < 1.5) & (np.abs(across) < 7.0)
        if m.sum() < 4:
            break
        a = across[m]
        lo, hi = np.percentile(a, 5), np.percentile(a, 95)
        if hi - lo < 2.5:                                     # no road surface across: the road ends
            break
        c = float(np.clip((lo + hi) / 2.0, -0.8, 0.8)) if hi - lo < 12.0 else 0.0
        xy = q + nrm * c
        zs = near[m][np.abs(a - c) < 2.5, 2]
        z = float(np.median(zs)) if len(zs) else float(cur[2])
        new = np.array([xy[0], xy[1], z])
        pts += [cur + (new - cur) * 0.5, new]
        d = new[:2] - cur[:2]
        t = 0.6 * t + 0.4 * d / max(np.linalg.norm(d), 1e-9)
        t /= np.linalg.norm(t)
        cur = new
    return np.array(pts[:int(length_m)], float).reshape(-1, 3)


def _along(R, ext):
    """s of the route points and of the run-off points after them."""
    if not len(ext):
        return R[:, 0]
    steps = np.linalg.norm(np.diff(np.vstack([R[-1:, 1:4], ext])[:, :2], axis=0), axis=1)
    return np.concatenate([R[:, 0], float(R[-1, 0]) + np.cumsum(steps)])


def layout(slug, cfg, stage_dir, log=print):
    """The finish of a stage: {'F': timing finish s, 'S': stop trigger s, 'ext': run-off (WRCG m), 'E': route end s,
    'why', 'tent'}; s along route_centerline_1m.csv continued along the run-off. Computed once per stage and process."""
    if slug in _LAYOUT:
        return _LAYOUT[slug]
    stage_dir = Path(stage_dir)
    R = np.loadtxt(stage_dir / "route_centerline_1m.csv", delimiter=",", skiprows=1)
    E = float(R[-1, 0])
    ext = runoff(stage_dir, R, RUNOFF_MAX_M)
    X = np.vstack([R[:, 1:4], ext]) if len(ext) else R[:, 1:4]
    S_all = _along(R, ext)
    line, stops, tents = _finish_props(stage_dir, cfg["wrcg_level"], cfg.get("startends_stage"),
                                       X[-(400 + len(ext)):, :2], log)

    def s_of(p, within):
        d = np.hypot(X[:, 0] - p[0], X[:, 1] - p[1])
        return float(S_all[int(d.argmin())]) if d.min() < within else None

    ls = [s for s in (s_of(p, 12.0) for p in line) if s is not None]
    ss = [s for s in (s_of(p, 12.0) for p in stops) if s is not None]
    if ls:                                     # a flying finish of its own: the stop posts belong to the stop control
        F, why = float(np.median(ls)), "WRCG's finish posts"
        tents = tents + [p for p in stops]
    elif ss:
        F, why = float(np.median(ss)), "WRCG's STOP posts"
    else:
        F, why = _timing_finish_s(stage_dir, R), "the timing finish"
    if F is None:
        _LAYOUT[slug] = None
        return None
    ts = [s for s in (s_of(p, 40.0) for p in tents) if s is not None and s > F]
    tent = min(ts) if ts else None
    want = float(np.clip(tent if tent is not None else F + STOP_DEFAULT_M, F + STOP_MIN_M, F + STOP_MAX_M))
    if cfg.get("stop_after_m"):                                # per stage: the stop control this far after the line (m)
        want = F + float(np.clip(float(cfg["stop_after_m"]), STOP_MIN_M, 250.0))
    end_x = float(S_all[-1])
    S = min(want, end_x - AFTER_STOP_M)
    if S < F + 25.0:                                          # not enough road: the timing line comes earlier
        S = end_x - 15.0
        F = min(F, S - FALLBACK_GAP_M)
        why += f", {FALLBACK_GAP_M:.0f} m before the stop (no road past the route)"
    keep = int(np.searchsorted(S_all[len(R):], S + AFTER_STOP_M)) + 1 if len(ext) else 0
    out = {"F": F, "S": S, "E": E, "ext": ext[:keep], "why": why, "tent": tent}
    _LAYOUT[slug] = out
    return out


def _stage_route(slug):
    import tools.acrmod.build_stage as bs
    import tools.acrmod.props_visual as pv
    cfg = bs.load_cfg(slug)
    route = np.asarray(bs.route_wrcg(cfg), float)
    shift = bs.stage_shift(cfg, route)
    return cfg, route, shift, pv


def _pad(v, n_old, n_add):
    if not n_add:
        return v
    if isinstance(v, np.ndarray) and v.ndim >= 1 and len(v) == n_old:
        return np.concatenate([v, np.repeat(v[-1:], n_add, axis=0)])
    if isinstance(v, list) and len(v) == n_old and n_old > 3:
        return v + [v[-1]] * n_add
    if isinstance(v, tuple) and len(v) == n_old and n_old > 3:
        return v + (v[-1],) * n_add
    return v


def patch_gameplay(log=print):
    """build_stage's process: gameplay.add_gameplay gets the route with its run-off (finish_marshal stages)."""
    import tools.acrmod.build_stage as bs
    import tools.acrmod.gameplay as gp
    if getattr(gp.add_gameplay, "_wr", False):
        return
    orig = gp.add_gameplay
    names = ("half_width_cm", "ideal_cm", "ideal_meta", "pre_cm", "widths_cm")

    def add_gameplay(dst, cell, route_cm, *a, **k):
        kw = dict(zip(names, a))
        kw.update(k)
        try:
            import tools.acrmod.stagectx as sc
            slug = sc.cur().slug
            cfg, route, shift, pv = _stage_route(slug)
            lay = layout(slug, cfg, Path(sys.executable).resolve().parent.parent / "work" / "wrcg" / slug, log) \
                if cfg.get("finish_marshal") else None
            rc = np.asarray(route_cm, float)
            end_ue = pv.wrcg_world_to_ue(route[-1:], shift)[0]
            if lay is not None and len(lay["ext"]) and np.linalg.norm(rc[-1, :2] - end_ue[:2]) < 300.0:
                ext = pv.wrcg_world_to_ue(lay["ext"], shift)[:, :rc.shape[1]]
                n0, n = len(rc), len(ext)
                kw2 = dict(kw)
                ideal = kw.get("ideal_cm")
                if isinstance(ideal, np.ndarray) and ideal.ndim == 2 and len(ideal) > 2 and \
                        np.linalg.norm(ideal[-1, :2] - end_ue[:2]) < 3000.0:
                    kw2["ideal_cm"] = np.vstack([ideal, ext[:, :ideal.shape[1]]])
                    if isinstance(kw.get("ideal_meta"), dict):
                        kw2["ideal_meta"] = {kk: _pad(vv, len(ideal), n) for kk, vv in kw["ideal_meta"].items()}
                # widths (left, right): one per point of the route resampled every SPLINE_SPACING_CM (gr_ss3: 620
                # for 4955 m), or one per route point
                new_rc = np.vstack([rc, ext])
                r0 = len(gp.resample(rc, gp.SPLINE_SPACING_CM))
                r1 = len(gp.resample(new_rc, gp.SPLINE_SPACING_CM))

                def pad_w(x):
                    if isinstance(x, np.ndarray) and len(x) == r0:
                        return _pad(x, r0, r1 - r0)
                    return _pad(x, n0, n)

                w = kw.get("widths_cm")
                if isinstance(w, (tuple, list)) and w and all(isinstance(x, np.ndarray) for x in w):
                    kw2["widths_cm"] = type(w)(pad_w(x) for x in w)
                elif isinstance(w, np.ndarray):
                    kw2["widths_cm"] = pad_w(w)
                shapes = {key: [getattr(x, "shape", None) for x in v] if isinstance(v, (tuple, list)) else
                          getattr(v, "shape", type(v).__name__) for key, v in kw2.items()}
                log(f"    finish: gameplay route +{n} m past the end of ours (run-off to the stop control); route_cm "
                    f"{rc.shape} -> {new_rc.shape}, resampled {r0} -> {r1}, args {shapes}")
                route_cm, kw = new_rc, kw2
        except Exception as e:
            log(f"    finish: gameplay route left as it is ({type(e).__name__}: {e})")
        return orig(dst, cell, route_cm, **kw)

    add_gameplay._wr = True
    gp.add_gameplay = add_gameplay
    if getattr(bs, "add_gameplay", None) is orig:
        bs.add_gameplay = add_gameplay


def _place(dst, root, route_ue, j):
    """Moves a component onto route point j, turning its yaw with the road; returns metres moved."""
    import math
    loc = _vec(dst.exp(root), "RelativeLocation")
    old = np.array([float(loc["X"]), float(loc["Y"])])
    i_old = int(np.argmin(np.hypot(route_ue[:, 0] - old[0], route_ue[:, 1] - old[1])))
    heading = lambda k: math.degrees(math.atan2(*(route_ue[min(k + 5, len(route_ue) - 1), :2] -
                                                  route_ue[max(k - 5, 0), :2])[::-1]))
    loc["X"], loc["Y"], loc["Z"] = (float(c) for c in route_ue[j])
    rot = _prop(dst.exp(root), "RelativeRotation")
    if rot is not None:
        r = rot["Value"][0]["Value"]
        r["Yaw"] = float(r["Yaw"]) + heading(j) - heading(i_old)
    return float(np.linalg.norm(route_ue[i_old, :2] - route_ue[j, :2]) / 100.0)


# The finish boards (owner 2026-11-11, Pietrosella: "poner un marcador de llegada a meta en el fin del tramo"). Stages
# built without the builder's dressing ("dressing": false: WRCG's own start and finish props) had no finish board at
# all. ACR's dressing (stage_dressing.add_dressing) is run on a scratch level at our timing line and at our stop
# control, and its boards copied in: the yellow pre-finish boards 100 m before the line, the flying-finish boards at the
# line (left and right, 4.3 m from the centre) and, at the stop control, the same boards as ACR's stop-control board.
# Not its gantries (a 9 m arch over WRCG's narrow finish roads). A level that has ACR's finish boards keeps its own.
SIGNS = "/Game/Props/RallyProps/Signs/"
BOARD_PREFIX = "WrcgFinishBoard"


def _heading(X, j):
    a, b = X[max(j - 5, 0), :2], X[min(j + 5, len(X) - 1), :2]
    t = (b - a) / max(float(np.linalg.norm(b - a)), 1e-6)
    return t, np.array([-t[1], t[0]])


def _mesh_of(asset, i):
    cp = _prop(asset.exp(i), "StaticMeshComponent")
    mp = _prop(asset.exp(cp["Value"]), "StaticMesh") if cp and cp.get("Value") else None
    if mp and isinstance(mp.get("Value"), int) and mp["Value"] < 0:
        return asset.import_key(mp["Value"])[1][0], cp["Value"], mp
    return None, None, None


def add_finish_boards(dst, X_ue, F, S, ground, road_width_m=7.0, log=print):
    import copy
    import wr_rvt
    import tools.acrmod.stage_dressing as sd
    import tools.acrmod.vegetation_visual as vv
    if any(dst.class_name(i) == "StaticMeshActor" and _mesh_of(dst, i)[0] == "SM_RaceFlyingFinish"
           for i in range(1, len(dst.exports) + 1)):
        log("    finish boards: the level has ACR's own, kept")
        return 0
    level = next(i for i in range(1, len(dst.exports) + 1) if dst.class_name(i) == "Level")
    n, where = 0, []
    for at, take in ((F, {"SM_RacePreFlyingFinish": None, "SM_RaceFlyingFinish": None}),
                     (S, {"SM_RaceFlyingFinish": "SM_RaceStopControl"})):
        tmp = copy.deepcopy(vv._template())
        n0 = len(tmp.exports)
        sd.add_dressing(tmp, X_ue, float(at), float(road_width_m), ground, boards=True)
        for i in range(n0 + 1, len(tmp.exports) + 1):
            if tmp.class_name(i) != "StaticMeshActor":
                continue
            mesh = _mesh_of(tmp, i)[0]
            if mesh not in take:
                continue
            a = dst.clone(tmp, i, level)[i]
            new = take[mesh] or mesh
            side = tmp.exp(i)["ObjectName"].rsplit("_", 1)[-1]
            name = f"{BOARD_PREFIX}_{new[3:]}_{side}"
            dst.add_name(name)
            dst.exp(a)["ObjectName"] = name
            dst.register_actor(level, a)
            if take[mesh]:
                _, c, mp = _mesh_of(dst, a)
                old, mi = mp["Value"], dst.ensure_import(wr_rvt._key(SIGNS + new, "StaticMesh"))
                mp["Value"] = mi
                for e in (dst.exp(a), dst.exp(c)):
                    for key in ("SerializationBeforeSerializationDependencies", "CreateBeforeSerializationDependencies",
                                "SerializationBeforeCreateDependencies", "CreateBeforeCreateDependencies"):
                        if e.get(key):
                            e[key] = [mi if x == old else x for x in e[key]]
            n += 1
            where.append(new[3:])
    log(f"    finish boards: ACR's pre-finish (s {F - 100:.0f} m), flying finish (s {F:.0f} m) and stop control "
        f"(s {S:.0f} m) boards, {n} ({', '.join(sorted(set(where)))})")
    return n


def finish_layout(dst, slug, cfg, stage_dir, shift, log=print):
    """The timing finish onto WRCG's line, the stop trigger by WRCG's stop control (see layout); returns the route with
    its run-off in UE cm (for placing the marshal) or None."""
    import tools.acrmod.props_visual as pv
    lay = layout(slug, cfg, stage_dir, log)
    if lay is None:
        log("    finish: no WRCG finish line found, the builder's kept")
        return None
    R = np.loadtxt(Path(stage_dir) / "route_centerline_1m.csv", delimiter=",", skiprows=1)
    X = np.vstack([R[:, 1:4], lay["ext"]]) if len(lay["ext"]) else R[:, 1:4]
    S_all = _along(R, lay["ext"])
    X_ue = pv.wrcg_world_to_ue(X, shift)
    jF = int(np.argmin(np.abs(S_all - lay["F"])))
    jS = int(np.argmin(np.abs(S_all - lay["S"])))
    sectors = [i for i in range(1, len(dst.exports) + 1) if dst.class_name(i) == "RaceSector"]
    trig = next((i for i in range(1, len(dst.exports) + 1) if dst.class_name(i) == "BC_EndSequenceTrigger_C"), None)
    if not sectors or trig is None:
        log("    finish: no RaceSector / BC_EndSequenceTrigger_C, the builder's kept")
        return None
    last = max(sectors, key=lambda i: int((_prop(dst.exp(i), "Index") or {}).get("Value") or 0))
    mF = _place(dst, _root_of(dst, last), X_ue, jF)
    mS = _place(dst, _root_of(dst, trig), X_ue, jS)
    tent = ", by WRCG's marshal tent" if lay["tent"] is not None else ""
    log(f"    finish: timing line on {lay['why']} (s {lay['F']:.0f} m, moved {mF:.0f} m), stop control "
        f"{lay['S'] - lay['F']:.0f} m after it (s {lay['S']:.0f} m{tent}, moved {mS:.0f} m), gameplay route "
        f"{len(lay['ext'])} m past the end of ours ({lay['E']:.0f} m)")
    try:
        import tools.acrmod.ittiri_ground as ig
        add_finish_boards(dst, X_ue, lay["F"], lay["S"], ig.make_ground_fn(shift), cfg.get("road_width_m") or 7.0, log=log)
    except Exception as e:
        log(f"    finish boards: not added ({type(e).__name__}: {e})")
    return X_ue
