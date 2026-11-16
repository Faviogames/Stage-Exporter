"""A dressed roadside row of ACR props along a WRCG polyline (owner 2026-11-16, Ngema m ~1574: the straw/bamboo wall
WALL_BAMBOO_01 replaced by ACR's metal chain-link fence, hedges behind it, plastic barriers in front, and lights).

Stage build "fence_rows": [{"points": [[x, y], ...] (WRCG metres, along the old wall), "fence": ["SM_ChainlinkFenceA6", ...],
"hedge": true, "barriers": true, "continuous": false, "barrier_every_m": 12, "barrier_run": 3, "front_m": 1.3, "back_m": 1.5, "lights": true,
"light_cd": 5000, "light_radius_cm": 2500, "light_height_m": 8, "light_every_m": 12, "light_toward_m": 4}].
Meshes are cloned from ACR's Monte Carlo cell of wr_tapeposts (it holds all of them): fence panels are BC_PhysicsActor_C
(2.37 m wide, pivot at one end, so each panel starts where the previous ends), hedges and barriers StaticMeshActor.
"Behind" is the side away from the route. The old wall is dropped with a "props_at" rule (wr_fixes._props_at).
Not checked in game: the panels' facing, the hedge's pivot (its long axis is Y, origin in the middle) and the barriers' collision.
"""
import json

import numpy as np

import wr_breakables
import wr_finish as wf
import wr_tapeposts as tp

PANEL_M = {"SM_ChainlinkFenceA6": 2.37, "SM_ChainlinkFenceA9": 2.37}
HEDGE, BARRIER, BARRIER_M, HEDGE_M = "SM_Hedge02", "SM_PlasticBarrierAFix", 1.52, 6.79
PACKAGES = {HEDGE: "/Game/Foliage/Trees/Hedge/", BARRIER: "/Game/Props/RallyProps/PlasticBarrierA/"}   # StaticMeshActors: mesh swapped on a template
CLASSES = ("BC_PhysicsActor_C", "StaticMeshActor")
FENCE_KG = 20000.0                 # chain-link panels: a car does not move them


def tp_source(root):
    import wr_roadside
    return type(_DST[0])(wr_roadside._fence_source(root))      # the Munster cell the red/white barrier is cloned from


_DST = [None]


def _find_actor(cell, mesh, cls):
    n = len(cell.exports)
    for i in range(1, n + 1):
        if cell.class_name(i) != cls:
            continue
        for c in range(1, n + 1):
            if cell.exp(c).get("OuterIndex") != i or "StaticMeshComponent" not in str(cell.class_name(c)):
                continue
            for p in cell.exp(c).get("Data") or []:
                v = p.get("Value")
                if p.get("Name") == "StaticMesh" and isinstance(v, int) and v < 0 and mesh == str(cell.imports[-v - 1].get("ObjectName", "")):
                    return i
    return None


def options(cfg):
    r = (cfg or {}).get("fence_rows")
    return r if isinstance(r, list) and r else None


def layout(row, route_xy):
    """{'fence': [(mesh, x, y, yaw)], 'hedge': [...], 'barrier': [...], 'lights': [(x, y)]} in the points' own frame; yaw in degrees."""
    P = np.asarray(row["points"], float)
    R = np.asarray(route_xy, float)[:, :2]
    names = ["SM_ChainlinkFenceA6"] if row.get("fence") is None else (row["fence"] or [])        # "fence": false = no panels
    out = {"fence": [], "hedge": [], "barrier": [], "lights": []}
    run, k, travelled, next_light = 0.0, 0, 0.0, 0.0
    for a, b in zip(P[:-1], P[1:]):
        v = b - a
        seg = float(np.hypot(*v))
        if seg < 0.5:
            continue
        u = v / seg
        mid = (a + b) / 2
        away = mid - R[int(np.hypot(R[:, 0] - mid[0], R[:, 1] - mid[1]).argmin())]
        n = np.array([-u[1], u[0]])
        n = n if n @ away >= 0 else -n                      # unit normal pointing away from the route
        yaw = float(np.degrees(np.arctan2(u[1], u[0])))
        t = 0.0
        while names and t < seg - 0.3:
            mesh = names[k % len(names)]
            p = a + u * t
            out["fence"].append((mesh, p[0], p[1], yaw))
            if row.get("hedge", True) and k % 3 == 0:
                h = p + u * (PANEL_M[mesh] / 2) + n * float(row.get("back_m", 1.5))
                out["hedge"].append((HEDGE, h[0], h[1], yaw + 90.0))
            k += 1
            t += PANEL_M[mesh]
        every = float(row.get("barrier_every_m", 12.0))
        if row.get("barriers", True) and row.get("continuous"):        # one barrier after another along the whole segment
            for c in np.arange(0.0, seg - 0.2, BARRIER_M):
                q = a + u * c - n * float(row.get("front_m", 0.0))
                out["barrier"].append((BARRIER, q[0], q[1], yaw))
        elif row.get("barriers", True):
            c = 0.0
            while c < seg:
                for j in range(int(row.get("barrier_run", 3))):
                    q = a + u * min(seg, c + j * BARRIER_M) - n * float(row.get("front_m", 1.3))
                    out["barrier"].append((BARRIER, q[0], q[1], yaw))
                c += every + BARRIER_M * int(row.get("barrier_run", 3))
        if row.get("lights", True):                       # spacing counted along the whole row, not per segment
            c = next_light - travelled
            while c < seg:
                q = a + u * c - n * float(row.get("light_toward_m", 4.0))
                out["lights"].append((q[0], q[1]))
                c += float(row.get("light_every_m", 12.0))
            next_light = travelled + c
        travelled += seg
    return out


def add(dst, root, cfg, route_xy, to_ue, shift, ground, log):
    import wr_lights
    import wr_roadside as roadside
    rows = options(cfg)
    if not rows:
        return
    from wr import ROOT
    import os
    work = ROOT / "work" / "acr"
    tp.prepare(work, os.environ["WRCG2ACR_ACR_PAKS"])
    U = type(dst)
    _DST[0] = dst
    cell = U(json.loads(tp._json(work).read_text(encoding="utf-8")))
    level = next(i for i in range(1, len(dst.exports) + 1) if dst.class_name(i) == "Level")
    cell_level = next(i for i in range(1, len(cell.exports) + 1) if cell.class_name(i) == "Level")
    srcs, n, lights = {}, 0, []
    import wr_roadside
    clear = wr_roadside._road_test(ROOT / "work" / "wrcg" / cfg["slug"], margin_cells=0)      # nothing on the road mesh itself
    R = np.asarray(route_xy, float)[:, :2]
    skipped = 0

    def off_road(x, y, kind):                      # barriers also keep 3 m from the route's centre line (the lane)
        return bool(clear(np.array([x, y]))) and (kind != "barrier" or float(np.hypot(R[:, 0] - x, R[:, 1] - y).min()) >= 3.0)
    for row in rows:
        lay = layout(row, route_xy)
        statics, barrier_places = [], []
        for kind in ("fence", "hedge", "barrier"):
            for mesh, x, y, yaw in lay[kind]:
                if kind != "hedge" and not off_road(x, y, kind):
                    skipped += 1                     # in the carriageway (owner 2026-11-16: barriers in the middle of the stretch)
                    continue
                if mesh not in srcs:
                    srcs[mesh] = _find_actor(cell, mesh, "BC_PhysicsActor_C")
                if mesh == BARRIER:                      # ACR's physical plastic barrier (wr_acrnets), white / red, heavy
                    h = np.array([np.cos(np.radians(yaw)), np.sin(np.radians(yaw))])
                    barrier_places.append((np.array([x + h[0] * BARRIER_M / 2, y + h[1] * BARRIER_M / 2, 0.0]), h))
                    continue
                if mesh in PACKAGES:
                    statics.append((f"WrcgFenceRow_{kind}_{n}", PACKAGES[mesh] + mesh, np.array([x, y, 0.0]),
                                    np.array([x + np.cos(np.radians(yaw - 90.0)), y + np.sin(np.radians(yaw - 90.0)), 0.0]), (1.0, 1.0, 1.0)))
                    n += 1
                    continue
                src = srcs[mesh]
                if not src:
                    log(f"fence rows: {mesh} not found in the cell, skipped")
                    continue
                ue = to_ue(np.array([[x, y, 0.0], [x + np.cos(np.radians(yaw)), y + np.sin(np.radians(yaw)), 0.0]]))
                yaw_ue = float(np.degrees(np.arctan2(ue[1, 1] - ue[0, 1], ue[1, 0] - ue[0, 0])))
                mapping = dst.clone(cell, src, level, preset={cell_level: level})
                actor = mapping[src]
                uname = f"WrcgFenceRow_{n}"
                dst.exp(actor)["ObjectName"] = uname
                dst.add_name(uname)
                dst.register_actor(level, actor)
                comp = dst.exp(next(p for p in dst.exp(actor)["Data"] if p.get("Name") == "RootComponent")["Value"])
                loc = wf._vec(comp, "RelativeLocation")
                loc["X"], loc["Y"], loc["Z"] = float(ue[0, 0]), float(ue[0, 1]), float(ground(float(ue[0, 0]), float(ue[0, 1]), 0.0))
                rot = wf._vec(comp, "RelativeRotation")
                rot["Pitch"], rot["Yaw"], rot["Roll"] = 0.0, yaw_ue, 0.0
                comp_idx = next(p for p in dst.exp(actor)["Data"] if p.get("Name") == "StaticMeshComponent")["Value"]
                if row.get("fence_kg", FENCE_KG):
                    wr_breakables._body_mass(dst.exp(comp_idx), float(row.get("fence_kg", FENCE_KG)))   # practically immovable
                for d in mapping.values():
                    dst._add_export_names(dst.exp(d))
                n += 1
        if barrier_places:
            import wr_acrnets
            wr_acrnets.add_barriers(dst, tp_source(root), None, float(row.get("barrier_kg", wr_acrnets.BARRIER_KG)), to_ue, ground, log,
                                    places=barrier_places, prefix=f"WrcgRowBarrier{id(row) % 9973}")
        if statics:
            roadside._add_roadside_props(dst, statics, to_ue(np.asarray(route_xy, float)), to_ue, ground, 7.0)
        for x, y in lay["lights"]:
            lights.append((x, y, float(row.get("light_height_m", 8.0)), float(row.get("light_radius_cm", 2500.0)),
                           float(row.get("light_cd", 5000.0))))
    nl = 0
    if lights:
        R = np.asarray(route_xy, float)
        pos = []
        for x, y, h, r, cd in lights:
            z0 = float(R[int(np.hypot(R[:, 0] - x, R[:, 1] - y).argmin()), 2]) if R.shape[1] > 2 else 0.0
            pos.append((np.array([x, y, z0 + h]), r, cd))
        nl = wr_lights._add_fill_lights(dst, root, shift, pos, "WrcgRowFill")
    if skipped:
        log(f"fence rows: {skipped} pieces left out because they stood on the road")
    log(f"fence rows: {n} ACR props (metal fence, hedges, plastic barriers) and {nl} lights")


def main():     # self-check on a straight synthetic wall 24 m long, the route 4 m to its right (+y is left of travel)
    route = np.c_[np.arange(0, 100.0), np.zeros(100), np.zeros(100)]
    row = {"points": [[10.0, 4.0], [34.0, 4.0]], "fence": ["SM_ChainlinkFenceA6", "SM_ChainlinkFenceA9"]}
    lay = layout(row, route)
    assert len(lay["fence"]) == 10 and abs(lay["fence"][1][1] - 12.37) < 1e-6 and lay["fence"][0][0] != lay["fence"][1][0]
    assert all(abs(y - 5.5) < 1e-6 for _, _, y, _ in lay["hedge"]) and all(abs(y - 2.7) < 1e-6 for _, _, y, _ in lay["barrier"])
    assert len(lay["lights"]) == 2 and all(abs(y - 0.0) < 1e-6 for _, y in lay["lights"])
    print("wr_fencerow self-check ok")


if __name__ == "__main__":
    main()
