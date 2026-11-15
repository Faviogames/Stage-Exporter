"""The service park tent (owner 2026-11-11: "antes de darle a iniciar el tramo, en el parque de asistencia, el coche está
rotado en el eje de la Z 90º ... Lo suyo sería que el coche se viera dentro de una carpa de la escudería, tal y como se
hace con los tramos originales del juego"; "el giro de 90 solo es necesario si no hay carpa").

ACR's own rallies load a service park level of their own (AlsaceServicePark, WalesServicePark, ...: the team tent made
of ~150 static meshes, decals, lights and a tyre rack round the ServiceParkTargetPoint); which one is chosen by location
is not in the data tables, and our locations have none, so the game shows the car at our level's ServiceParkTargetPoint,
in the open. The tent of AlsaceServicePark (its actors within SCENE_M of its target point) is copied into the stage
level, moved without turning (the service park camera looks in a fixed direction: Alsace's car stands at yaw 183.9, ours
at the road's yaw + 180 = 85.5 looked turned by 90 deg), around a flat clearing near the start (site(): no road, prop or
tree within reach, ground within FLAT_M), and the target point goes there with Alsace's yaw. Stage build:
"service_park_tent": true."""
import json
import math
from pathlib import Path

import numpy as np

from wr import ROOT

LEVEL_JSON = ROOT / "work" / "acr" / "wr_servicepark" / "acr" / "Content" / "Levels" / "AlsaceServicePark.json"
SCENE_M = 9.5
KINDS = ("StaticMeshActor", "DecalActor", "SpotLight", "RectLight", "BC_TiresRack_C")
SITE_R_M = 10.0                   # the clearing: flat, no prop or tree within this
FLAT_M = 0.5
ROAD_CLEAR_M = 14.0
SEARCH_MIN_M, SEARCH_MAX_M = 30.0, 300.0
CLEAR_PLANTS_M = 13.0
PREFIX = "WrcgServicePark"
SITE_FILE = "service_park_site.json"


def _prop(e, name):
    return next((p for p in (e.get("Data") or []) if isinstance(p, dict) and p.get("Name") == name), None)


def site(stage_dir, log=print):
    """(x, y, z) of the tent's clearing, WRCG m, near the start (cached in the stage folder), or None."""
    stage_dir = Path(stage_dir)
    f = stage_dir / SITE_FILE
    if f.exists():
        d = json.loads(f.read_text(encoding="utf-8"))
        return tuple(d["site"]) if d.get("site") else None
    import wr_groundcover as gc
    meta = json.loads((stage_dir / "terrain" / "meta.json").read_text(encoding="utf-8"))
    H = np.load(stage_dir / "terrain" / "heights_0p5m.npy", mmap_mode="r")
    ox, oy = gc.window(meta)
    R = np.loadtxt(stage_dir / "route_centerline_1m.csv", delimiter=",", skiprows=1)
    s0 = R[0, 1:4]
    cell = 2.0
    lo = s0[:2] - SEARCH_MAX_M - SITE_R_M - 4
    n = int(2 * (SEARCH_MAX_M + SITE_R_M + 4) / cell)
    shape = (n, n)
    gx, gy = np.meshgrid(lo[0] + (np.arange(n) + 0.5) * cell, lo[1] + (np.arange(n) + 0.5) * cell)
    hi_ = np.clip(((gy - oy) / gc.TEXEL).astype(int), 0, H.shape[0] - 1)
    hj_ = np.clip(((gx - ox) / gc.TEXEL).astype(int), 0, H.shape[1] - 1)
    Z = np.asarray(H[hi_, hj_], float)
    k = int(SITE_R_M / cell)
    zmax, zmin = Z.copy(), Z.copy()
    for di in range(-k, k + 1):
        for dj in range(-k, k + 1):
            if di * di + dj * dj > k * k:
                continue
            sh = np.roll(np.roll(Z, di, 0), dj, 1)
            zmax, zmin = np.maximum(zmax, sh), np.minimum(zmin, sh)
    flat = (zmax - zmin) <= FLAT_M
    road = np.load(stage_dir / "collision_all_prm.npz")
    d_road = gc._dist(gc._raster(gc._tri_points(road["positions"], road["triangles"], 1.0), lo, shape, cell),
                      ROAD_CLEAR_M + 2, cell)
    extra = np.load(stage_dir / "collision_extra.npz")
    d_prop = gc._dist(gc._raster(gc._tri_points(extra["positions"], extra["triangles"], 1.0), lo, shape, cell),
                      SITE_R_M + 2, cell)
    trees = []
    try:
        veg = json.loads((stage_dir / "vegetation" / "instances.json").read_text(encoding="utf-8"))["instances"]
        trees = [(r["x"], r["y"]) for r in veg if r.get("src") != "wr_groundcover"]
    except Exception:
        pass
    d_tree = gc._dist(gc._raster(np.array(trees, float).reshape(-1, 2), lo, shape, cell), SITE_R_M + 2, cell)
    free = lambda d, r: ~np.isfinite(d) | (d > r)
    ok = flat & free(d_road, ROAD_CLEAR_M) & free(d_prop, SITE_R_M) & free(d_tree, SITE_R_M - 1.0)
    dist = np.hypot(gx - s0[0], gy - s0[1])
    ok &= (dist >= SEARCH_MIN_M) & (dist <= SEARCH_MAX_M)
    ok[:k + 1, :] = ok[-k - 1:, :] = False
    ok[:, :k + 1] = ok[:, -k - 1:] = False
    if not ok.any():
        f.write_text(json.dumps({"site": None}), encoding="utf-8")
        log("service park: no flat clearing near the start for the tent")
        return None
    i, j = np.unravel_index(np.argmin(np.where(ok, dist, np.inf)), ok.shape)
    out = (float(gx[i, j]), float(gy[i, j]), float(Z[i, j]))
    f.write_text(json.dumps({"site": out, "from_start_m": float(dist[i, j])}), encoding="utf-8")
    log(f"service park: tent clearing {dist[i, j]:.0f} m from the start (ground within {zmax[i, j] - zmin[i, j]:.2f} m)")
    return out


def clear_plants(instances, stage_dir):
    """The vegetation instances without those on the tent's clearing."""
    s = site(stage_dir)
    if s is None:
        return instances
    return [r for r in instances if math.hypot(r["x"] - s[0], r["y"] - s[1]) > CLEAR_PLANTS_M]


def add(dst, slug, shift, ground, log=print):
    """The tent round the level's ServiceParkTargetPoint, moved to the clearing; True if placed."""
    import tools.acrmod.props_visual as pv
    stage_dir = ROOT / "work" / "wrcg" / slug
    s = site(stage_dir, log)
    if s is None or not LEVEL_JSON.exists():
        return False
    tp_dst = next((i for i in range(1, len(dst.exports) + 1) if dst.class_name(i) == "ServiceParkTargetPoint"), None)
    if tp_dst is None:
        return False
    lv = type(dst)(json.loads(LEVEL_JSON.read_text(encoding="utf-8")))

    def root(asset, i):
        rc = _prop(asset.exp(i), "RootComponent")
        return rc["Value"] if rc and isinstance(rc.get("Value"), int) and rc["Value"] > 0 else None

    def vec(asset, comp, name):
        p = _prop(asset.exp(comp), name)
        return p["Value"][0]["Value"] if p else None

    lv_level = next(i for i in range(1, len(lv.exports) + 1) if lv.class_name(i) == "Level")
    actors = [i for i in range(1, len(lv.exports) + 1) if lv.exp(i).get("OuterIndex") == lv_level]
    tp = next(i for i in actors if lv.class_name(i) == "ServiceParkTargetPoint")
    t_loc, t_rot = vec(lv, root(lv, tp), "RelativeLocation"), vec(lv, root(lv, tp), "RelativeRotation")
    T = np.array([float(t_loc[k]) for k in "XYZ"])
    # the floor: the tent's tarp floor (stock: 1.1 m under the target point)
    c = pv.wrcg_world_to_ue(np.array([s], float), shift)[0]
    zs = [ground(float(c[0] + 600 * math.cos(a)), float(c[1] + 600 * math.sin(a)), float(c[2])) for a in
          np.linspace(0, 2 * math.pi, 12, endpoint=False)] + [ground(float(c[0]), float(c[1]), float(c[2]))]
    zs = [z for z in zs if z is not None and math.isfinite(z)]
    floor = float(np.median(zs)) if zs else float(c[2])
    new_T = np.array([c[0], c[1], floor + 110.0])
    level = next(i for i in range(1, len(dst.exports) + 1) if dst.class_name(i) == "Level")
    n, kinds = 0, {}
    for i in actors:
        k = lv.class_name(i)
        if k not in KINDS:
            continue
        r = root(lv, i)
        loc = vec(lv, r, "RelativeLocation") if r else None
        if loc is None:
            continue
        p = np.array([float(loc[q]) for q in "XYZ"])
        if math.hypot(p[0] - T[0], p[1] - T[1]) > SCENE_M * 100:
            continue
        a = dst.clone(lv, i, level)[i]
        name = f"{PREFIX}_{n}"
        dst.add_name(name)
        dst.exp(a)["ObjectName"] = name
        dst.register_actor(level, a)
        q = p - T + new_T
        nl = vec(dst, root(dst, a), "RelativeLocation")
        nl["X"], nl["Y"], nl["Z"] = float(q[0]), float(q[1]), float(q[2])
        kinds[k] = kinds.get(k, 0) + 1
        n += 1
    # the car: where Alsace's stands in its tent, with its yaw
    rc = root(dst, tp_dst)
    l, rr = vec(dst, rc, "RelativeLocation"), vec(dst, rc, "RelativeRotation")
    l["X"], l["Y"], l["Z"] = float(new_T[0]), float(new_T[1]), float(new_T[2])
    if rr is not None:
        rr["Yaw"] = float(t_rot["Yaw"]) if t_rot else 183.9
    away = json.loads((stage_dir / SITE_FILE).read_text(encoding="utf-8")).get("from_start_m", 0.0)
    log(f"service park: Alsace's team tent ({n} actors: {', '.join(f'{v} {k_}' for k_, v in sorted(kinds.items()))}) "
        f"on a clearing {away:.0f} m from the start; the car there at yaw {float(rr['Yaw']) if rr else 0.0:.1f}")
    return True
