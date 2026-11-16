"""ACR's wooden fence post instead of WRCG's thin metal tape sticks (owner 2026-11-15: the wooden posts with wire of Munster
look more convincing).

WRCG's tapes hang from RAILCLONE/NET_TAPE/STICK* props (1-1.3 m, 4-10 cm: the red-and-white tape of the start). Stage build
"tape_posts": {"mesh": "SM_FenceModularA_Pole1", "near_m": 60, "max": 1200}: those sticks are left out of the props and an ACR
physical actor (BC_PhysicsActor_C with that mesh, copied from a Monte Carlo cell that uses it) stands where each one was.
All the sticks are replaced (max is above their count, or the tape would hang loose).
The tape cloth stays as it is. Not checked in game: the post's size against the tape's height, and the cost of the physics
actors (hence near_m and max).
"""
import json
import re
import shutil
import tempfile
from pathlib import Path

import numpy as np

import wr_finish as wf

STICK_RE = re.compile(r"/NET_TAPE/STICK", re.I)
AD_BOARD_RE = re.compile(r"(?!FENCE_)[A-Z0-9]+_BANNER_[A-Z0-9_]+", re.I)
CELL = "DGC4CM72D5ALBJN52GZTKJ1D0"
LEVEL_DIR = "Levels/MonteCarloS1Bollene/_Generated_/"
ACTOR_CLASS = "BC_PhysicsActor_C"
DEFAULTS = {"mesh": "SM_FenceModularA_Pole1", "near_m": 60.0, "max": 1200}


def options(cfg):
    o = cfg.get("tape_posts")
    return dict(DEFAULTS, **o) if isinstance(o, dict) else (dict(DEFAULTS) if o else None)


def _json(work_acr):
    return Path(work_acr) / "wr_tapeposts" / f"{CELL}.json"


def prepare(work_acr, paks):
    import tools.acrmod.common as c
    out = _json(work_acr)
    if out.exists():
        return
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix="wr_tapeposts_"))
    try:
        c.retoc("to-legacy", paks, str(tmp), "-f", CELL, "--version", "UE5_6", "--no-shaders")
        c.asset_json(tmp / "acr" / "Content" / (LEVEL_DIR + CELL + ".umap"), out)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def stick_points(insts, route_xy, near_m, limit):
    """[(x, y, z, yaw_deg)] WRCG metres of the tape sticks within near_m of the route, nearest first, at most `limit`."""
    R = np.asarray(route_xy, float)[:, :2]
    pts = []
    for p in insts:
        if not STICK_RE.search(str(p.psi)):
            continue
        W = np.asarray(p.world, float)
        d = float(np.hypot(R[:, 0] - W[0, 3], R[:, 1] - W[1, 3]).min())
        if d <= near_m:
            pts.append((d, (W[0, 3], W[1, 3], W[2, 3], float(np.degrees(np.arctan2(W[1, 0], W[0, 0]))))))
    return [q for _, q in sorted(pts, key=lambda t: t[0])[:limit]]


def _find_actor(cell, mesh):
    n = len(cell.exports)
    for i in range(1, n + 1):
        if cell.class_name(i) != ACTOR_CLASS:
            continue
        for c in range(1, n + 1):
            if cell.exp(c).get("OuterIndex") != i or "StaticMeshComponent" not in str(cell.class_name(c)):
                continue
            for p in cell.exp(c).get("Data") or []:
                v = p.get("Value")
                if p.get("Name") == "StaticMesh" and isinstance(v, int) and v < 0 and mesh in str(
                        cell.imports[-v - 1].get("ObjectName", "")):
                    return i
    return None


def add(dst, work_acr, points_ue, ground, mesh, log=print):
    U = type(dst)
    cell = U(json.loads(_json(work_acr).read_text(encoding="utf-8")))
    src = _find_actor(cell, mesh)
    if not src:
        log(f"    tape posts: {mesh} not found in the cell, skipped")
        return 0
    level = next(i for i in range(1, len(dst.exports) + 1) if dst.class_name(i) == "Level")
    cell_level = next(i for i in range(1, len(cell.exports) + 1) if cell.class_name(i) == "Level")
    n = 0
    for x, y, yaw in points_ue:
        mapping = dst.clone(cell, src, level, preset={cell_level: level})
        actor = mapping[src]
        uname = f"WrcgTapePost_{n}"
        dst.exp(actor)["ObjectName"] = uname
        dst.add_name(uname)
        dst.register_actor(level, actor)
        root = next(p for p in dst.exp(actor)["Data"] if p.get("Name") == "RootComponent")["Value"]
        comp = dst.exp(root)
        loc = wf._vec(comp, "RelativeLocation")
        loc["X"], loc["Y"], loc["Z"] = float(x), float(y), float(ground(float(x), float(y), 0.0))
        rot = wf._vec(comp, "RelativeRotation")
        rot["Pitch"], rot["Yaw"], rot["Roll"] = 0.0, float(yaw), 0.0
        for d in mapping.values():
            dst._add_export_names(dst.exp(d))
        n += 1
    log(f"    tape posts: {n} wooden posts ({mesh}) instead of WRCG's metal sticks")
    return n


def main():     # self-check of the stick filter on synthetic props
    class P:
        def __init__(self, psi, x):
            self.psi, self.world = psi, np.array([[1, 0, 0, x], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]], float)
    route = np.c_[np.arange(0, 100.0), np.zeros(100)]
    pts = stick_points([P("DATA:/GRAPH/RAILCLONE/NET_TAPE/STICK01.PSI", 50.0), P("X/OTHER.PSI", 50.0)], route, 30, 10)
    assert len(pts) == 1 and pts[0][0] == 50.0, pts
    assert options({}) is None and options({"tape_posts": True})["max"] == 1200
    print("wr_tapeposts self-check ok")



# --- Original WRCG tape sticks, with the native ACR tape-pole physics ---


def _panel_footprint(origin, extent, loc, rot, scale):
    """Conservative plan of the original whole sign, in UE cm."""
    scale = np.array([float(scale[k]) for k in "XYZ"])
    o = np.asarray(origin, float) * scale
    e = np.asarray(extent, float) * np.abs(scale)
    pitch, yaw, roll = np.deg2rad([float(rot[k]) for k in ("Pitch", "Yaw", "Roll")])
    cp, cy, cr = np.cos([pitch, yaw, roll])
    sp, sy, sr = np.sin([pitch, yaw, roll])
    r = np.array([[cp*cy, cp*sy, sp],
                  [sr*sp*cy-cr*sy, sr*sp*sy+cr*cy, -sr*cp],
                  [-cr*sp*cy-sr*sy, -cr*sp*sy+sr*cy, cr*cp]])
    # Sample both ends and the whole footprint, including tilted boards.
    grid = np.meshgrid(*(np.linspace(o[i]-e[i], o[i]+e[i], int(np.ceil(2*e[i]/20))+1)
                         for i in range(3)))
    return np.column_stack([g.ravel() for g in grid]) @ r[:, :2] + [float(loc["X"]), float(loc["Y"])]


def _physical_roadside_props(dst, legacy_root, saved_start, cfg, shift, log):
    import copy

    from tools.acrmod import build_stage as bs, props_visual as pv
    import wr_breakables as wb
    import wr_perf
    import wr_roadside as roadside
    from wr import ROOT

    route = np.asarray(bs.route_wrcg(cfg), float)
    clear = roadside._road_test(ROOT / "work" / "wrcg" / cfg["slug"], margin_cells=1)
    frame = np.asarray(pv.wrcg_world_to_ue(np.array([[0., 0., 0.], [1., 0., 0.], [0., 1., 0.]]), shift), float)[:, :2]
    inverse = np.linalg.inv(frame[1:] - frame[0])
    todo, assets = [], {}
    for i in range(saved_start, len(dst.exports) + 1):
        if dst.class_name(i) != "StaticMeshActor":
            continue
        name = dst.exp(i)["ObjectName"]
        if not name.startswith(wr_perf.PROP_PREFIX):
            continue
        stem = re.sub(r"_\d+$", "", name[len(wr_perf.PROP_PREFIX):])
        psi = wr_perf._PSI.get(stem)
        if not psi:
            continue
        panel = bool(AD_BOARD_RE.fullmatch(stem))
        if panel:
            if not roadside.on(cfg, "wrcg_ad_board_physics"):
                continue
        elif not (roadside.on(cfg, "wrcg_tape_post_physics") and STICK_RE.search(str(psi))):
            continue
        _, comp, prop = wf._mesh_of(dst, i)
        if not comp:
            continue
        old = dst.exp(comp)
        loc = wb._vec_of(old, "RelativeLocation")
        if loc is None:
            continue
        xy = (np.array([float(loc["X"]), float(loc["Y"])]) - frame[0]) @ inverse
        if np.min(np.sum((route[:, :2] - xy) ** 2, axis=1)) > 18.0 ** 2:
            continue
        mesh = prop["Value"]
        if mesh not in assets:
            package = dst.import_key(mesh)[0][0]
            files = wb._mesh_file(package, [legacy_root])
            assets[mesh] = (files[0], wb.mesh_bounds(files[0]) if panel else None) if files else (None, None)
        path, bounds = assets[mesh]
        if not path:
            continue
        if panel:
            origin, extent = bounds
            if not (37.5 <= max(extent[:2]) <= 210 and min(extent[:2]) <= 45 and 15 <= extent[2] <= 115):
                continue
            rot = wb._vec_of(old, "RelativeRotation") or dict(Pitch=0, Yaw=0, Roll=0)
            scale = wb._vec_of(old, "RelativeScale3D") or dict(X=1, Y=1, Z=1)
            footprint = (_panel_footprint(origin, extent, loc, rot, scale) - frame[0]) @ inverse
        else:
            footprint = xy + [[-0.12, -0.12], [-0.12, 0.12], [0.12, -0.12], [0.12, 0.12], [0, 0]]
        # Sticks at the verge overlap the road raster's margin (226 of 602 on Ngema, 22 of 26 near m 3491): left out they stay the
        # core's NoCollision originals and never fall (owner 2026-11-16: "a veces cae y a veces no"). "tape_stick_on_road": false = old rule.
        if clear(footprint) or (not panel and roadside.on(cfg, "tape_stick_on_road")):
            todo.append((i, old, mesh, path, panel))
    if not todo:
        return 0

    source, native_actor = roadside.corner_post_template(dst, ROOT)
    source_level, level = roadside._level(source), roadside._level(dst)
    preset = {source_level: level}
    if any(panel for _, _, _, _, panel in todo):
        advert_cell = type(dst)(roadside._fence_source(ROOT))
        advert_actor = next(i for i in range(1, len(advert_cell.exports) + 1)
                            if advert_cell.class_name(i) == ACTOR_CLASS
                            and wf._mesh_of(advert_cell, i)[0] == "SM_FraMunAdvertM")
        advert_preset = {roadside._level(advert_cell): level}
        comp = roadside._value(advert_cell, advert_actor, "RootComponent")
        parent = roadside._value(advert_cell, comp, "AttachParent")
        if parent:
            advert_preset[parent] = 0

    prepared = set()
    counts = {False: 0, True: 0}
    for i, old, mesh, path, panel in todo:
        if mesh not in prepared:
            wb.add_box_body(path, log, panel=panel)
            prepared.add(mesh)
        if panel:
            name = f"WrcgPhysicalAdBoard_{i}"
            actor = roadside._clone(dst, advert_cell, advert_actor, level, name, advert_preset)
        else:
            name = f"WrcgPhysicalTapeStick_{i}"
            actor = roadside._clone(dst, source, native_actor, level, name, preset)
        child = dst.exp(roadside._value(dst, actor, "RootComponent"))
        target = wf._prop(child, "StaticMesh")
        old_mesh = target["Value"]
        target["Value"] = mesh
        for e in (dst.exp(actor), child):
            for key, refs in e.items():
                if key.endswith("Dependencies") and refs:
                    e[key] = [mesh if ref == old_mesh else ref for ref in refs]
        inherited = {"AttachParent", "RelativeLocation", "RelativeRotation", "RelativeScale3D",
                     "OverrideMaterials", "CustomPrimitiveData"}
        child["Data"] = [p for p in child["Data"] if p.get("Name") not in inherited]
        child["Data"].extend(copy.deepcopy(p) for p in old["Data"]
                             if p.get("Name") in inherited - {"AttachParent"})
        wb._body_mass(child, 12.0 if panel else 2.5)
        dst._add_export_names(child)
        # The core's source is already NoCollision; hide it where it stood so
        # only the native movable actor can be seen or hit.
        wr_perf._set_bool(dst, old, "bHiddenInGame", True)
        counts[panel] += 1
    if counts[False]:
        log(f"WRCG physical tape sticks: {counts[False]} original posts with ACR corner-post physics, 2.5 kg")
    if counts[True]:
        log(f"WRCG physical ad boards: {counts[True]} original panels with ACR Munster advert physics, 12 kg")
    return sum(counts.values())


def patch_physics(cfg_for_slug):
    from tools.acrmod import props_visual as pv, stagectx as sc
    import wr_roadside as roadside

    if getattr(pv.add_ittiri_props, "_wr_tape_physics", False):
        return
    original = pv.add_ittiri_props

    def add_props(dst, legacy_root, shift_baked, *a, **k):
        start = len(dst.exports) + 1
        result = original(dst, legacy_root, shift_baked, *a, **k)
        cfg = cfg_for_slug(sc.cur().slug)
        if cfg and any(roadside.on(cfg, key) for key in ("wrcg_tape_post_physics", "wrcg_ad_board_physics")):
            _physical_roadside_props(dst, legacy_root, start, cfg, shift_baked, k.get("log") or print)
        return result

    add_props._wr_tape_physics = True
    pv.add_ittiri_props = add_props


if __name__ == "__main__":
    main()
