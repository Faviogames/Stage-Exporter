"""Hand-placed scenes by route metre (owner 2026-11-15: "como un editor"): parked vehicles, spectators and a safety net.

Stage build "scene": {"at_m": 2879.0, "vehicle_lateral_m": 13.0, "fence_lateral_m": 8.5, "gap_m": 4.0, "people": 6, "fence": true,
"vehicles": ["BUS_01_KENYA", "CMN_COMBI"]}. Lateral metres are from the route centreline, positive to the LEFT of the
travel direction (verified on Seyabei: the owner's position read from ACR's shared memory, 11.8 m left of m 2879).
- vehicles: WRCG props (their own PSI, like wr_animals): parked one behind the other, centred on at_m, long axis along the
  road, the line at vehicle_lateral_m; collision from their LOD0 mesh (wr_fixes._graph_collision, PM_WallMetalBigObject);
- fence: WRCG's red net (NetCloth NET_RED, 2 m x 0.9 m pieces, solid with net_solid) in a straight line at fence_lateral_m
  along the whole line of vehicles plus 8 m each side, closed at both ends towards the vehicles;
- people: ACR spectators (wr_crowd) between the fence and the vehicles.
Measured models (m, LOD0): BUS_01_KENYA 2.54 x 8.81 x 3.17 (long axis Y), CMN_COMBI 5.67 x 2.51 x 2.52 (long axis X), both
centred on their origin and standing on z 0. Not checked in game: the ground under the line (it follows the road's height).
"""
import copy
import math

import numpy as np

DEFAULTS = {"at_m": 0.0, "vehicle_lateral_m": 13.0, "fence_lateral_m": 8.5, "gap_m": 4.0, "people": 6, "fence": True,
            "vehicles": ["BUS_01_KENYA", "CMN_COMBI"], "lights": True, "light_cd": 10000.0, "light_height_m": 9.0,
            "light_side_m": 6.0, "light_radius_cm": 2500.0}
MODELS = {"BUS_01_KENYA": ("DATA:/GRAPH/PROPS/VEHICLES/COACH/BUS_01_KENYA.PSI", 8.81, 2.54, 90.0),
          "CMN_COMBI": ("DATA:/GRAPH/PROPS/VEHICLES/COMBI/CMN_COMBI.PSI", 5.67, 2.51, 0.0)}   # psi, length, width, yaw offset
NET = "DATA:/GRAPH/RAILCLONE/NET_TAPE/PMA/NET_RED.PMA"
PIECE_M = 2.0
_ROUTES = {}


def options(cfg):
    o = (cfg or {}).get("scene")
    return dict(DEFAULTS, **o) if isinstance(o, dict) and o.get("at_m") else None


def route_of(cfg):
    slug = cfg["slug"]
    if slug not in _ROUTES:
        import tools.acrmod.build_stage as bs
        _ROUTES[slug] = np.asarray(bs.route_wrcg(bs.load_cfg(slug)), float)
    return _ROUTES[slug]


def frame(route, m):
    """(point xyz, heading xy, left normal xy) of the route at route metre m."""
    s = np.r_[0.0, np.cumsum(np.hypot(*np.diff(route[:, :2], axis=0).T))]
    i = int(np.clip(np.searchsorted(s, m), 3, len(route) - 4))
    h = route[i + 3, :2] - route[i - 3, :2]
    h = h / np.hypot(*h)
    return np.array([np.interp(m, s, route[:, k]) for k in range(3)]), h, np.array([-h[1], h[0]])


def at(route, m, lateral):
    p, h, n = frame(route, m)
    return np.r_[p[:2] + n * lateral, p[2]], h


def layout(route, o):
    """{'vehicles': [(name, psi, centre xyz, yaw_deg, length, width)], 'fence': [(pos xyz, dir xy)], 'people': [xyz]}"""
    names = list(o["vehicles"])
    lengths = [MODELS[n][1] for n in names]
    total = sum(lengths) + o["gap_m"] * (len(names) - 1)
    m = o["at_m"] - total / 2.0
    vehicles = []
    for name, ln in zip(names, lengths):
        centre, h = at(route, m + ln / 2.0, o["vehicle_lateral_m"])
        psi, _, width, off = MODELS[name]
        vehicles.append((name, psi, centre, math.degrees(math.atan2(h[1], h[0])) - off, ln, width))
        m += ln + o["gap_m"]
    start, end = o["at_m"] - total / 2.0 - 8.0, o["at_m"] + total / 2.0 + 8.0
    fence = []
    if o["fence"]:
        for k in range(int(math.ceil((end - start) / PIECE_M))):
            p, h = at(route, start + k * PIECE_M, o["fence_lateral_m"])
            fence.append((p, h))
        span = o["vehicle_lateral_m"] - o["fence_lateral_m"]
        for m_end in (start, end):                          # closing the ends, towards the vehicles
            n = frame(route, m_end)[2]
            for k in range(int(math.ceil(span / PIECE_M))):
                p, _ = at(route, m_end, o["fence_lateral_m"] + k * PIECE_M)
                fence.append((p, n))
    people = []
    lat = (o["fence_lateral_m"] + o["vehicle_lateral_m"] - max(w for _, _, _, _, _, w in vehicles) / 2.0) / 2.0 + 0.2
    for k in range(int(o["people"])):
        people.append(at(route, o["at_m"] - total / 2.0 - 3.0 + (total + 6.0) * (k + 0.5) / max(1, int(o["people"])),
                         lat + 0.5 * ((k % 3) - 1))[0])
    return {"vehicles": vehicles, "fence": fence, "people": people}


def vehicle_props(template, cfg):
    """PropInstance copies of `template` for the scene's vehicles (WRCG world matrices)."""
    o = options(cfg)
    if not o or template is None:
        return []
    out = []
    for k, (name, psi, c, yaw, _, _) in enumerate(layout(route_of(cfg), o)["vehicles"]):
        t = math.radians(yaw)
        w = np.array([[math.cos(t), -math.sin(t), 0, c[0]], [math.sin(t), math.cos(t), 0, c[1]], [0, 0, 1, c[2]], [0, 0, 0, 1]])
        p = copy.copy(template)
        for a, v in (("category", "static"), ("name", f"WrcgScene_{name}_{k}"), ("node_id", f"scene{k}"),
                     ("parent_name", "WrcgScene"), ("path", f"WrcgScene/{name}_{k}"), ("psi", psi), ("psi_name", name),
                     ("spawner_id", None), ("world", w)):
            setattr(p, a, v)
        out.append(p)
    return out


def rock_props(insts, cfg, more=None):
    """Stage build "rocks": {"psi_name": "M_RED_ROCK_02_B", "m_from": 3052, "m_to": 3092, "step_m": 5, "lateral_m": 6.5,
    "sink_m": 0.5}: copies of a WRCG rock prop that the level already has (so its model path is known), in a line at lateral_m
    (positive = left of travel) along the route, each turned and scaled a little ("rocks" may be a list of such dicts; "aligned": true
    keeps them straight along the route; `more()` gives other props to find the template in). Blocks cutting a bend where the ground
    reads as drivable (owner 2026-11-16, Seyabei m 3070, inside of the left bend)."""
    rs = (cfg or {}).get("rocks")
    rs = rs if isinstance(rs, list) else ([rs] if rs else [])
    out = []
    for n, r in enumerate(rs):                         # "aligned": true = no turn and no scale change (a row of bales: owner 2026-11-16)
        names = r["psi_name"] if isinstance(r["psi_name"], list) else [r["psi_name"]]       # a list: used in turn, one per step (poles 01-03)
        pool = list(insts)
        if more is not None and not all(any(p.psi_name == nm for p in pool) for nm in names):
            pool += list(more())
        tmpls = [next((p for p in pool if p.psi_name == nm), None) for nm in names]
        if any(t is None for t in tmpls):
            print(f"    rocks: no {', '.join(nm for nm, t in zip(names, tmpls) if t is None)} among the level's props, none added")
            continue
        route = route_of(cfg)
        for k, m in enumerate(np.arange(float(r["m_from"]), float(r["m_to"]) + 1e-6, float(r.get("step_m", 5.0)))):
            al = bool(r.get("aligned"))
            c, h = at(route, float(m), float(r["lateral_m"]) + (0.0 if al else (0.4 if k % 2 else -0.4)))
            t = math.atan2(h[1], h[0]) + (math.radians(float(r.get("yaw_deg", 0.0))) if al else math.radians(37.0 * k))     # yaw_deg: turn of an aligned prop (a pylon's arm is its local +Y: -90)
            sc = 1.0 if al else 1.0 + 0.15 * math.sin(k * 2.3)
            w = np.array([[sc * math.cos(t), -sc * math.sin(t), 0, c[0]], [sc * math.sin(t), sc * math.cos(t), 0, c[1]],
                          [0, 0, sc, c[2] - float(r.get("sink_m", 0.5))], [0, 0, 0, 1]])
            p = copy.copy(tmpls[k % len(tmpls)])
            p.scene_solid = bool(r.get("solid", True))              # "solid": false = no collision made for it (cables)
            tag = f"{n}_{k}" if n else f"{k}"
            for a, v in (("name", f"WrcgScene_Rock_{tag}"), ("node_id", f"scenerock{tag}"), ("parent_name", "WrcgScene"),
                         ("path", f"WrcgScene/Rock_{tag}"), ("spawner_id", None), ("world", w)):
                setattr(p, a, v)
            out.append(p)
    return out


def cloth_items(cfg):
    o = options(cfg)
    if not o:
        return []
    # same types as the core's own items (ndarray pos / dir, tuple size): it subtracts them
    return [{"pos": np.asarray(p, float), "dir": np.array([float(h[0]), float(h[1]), 0.0]), "size": (PIECE_M, 0.9),
             "template": "NetCloth", "material": NET} for p, h in layout(route_of(cfg), o)["fence"]]


def light_positions(cfg):
    """[(WRCG xyz, radius cm, candelas)]: one high, broad, shadowless light per vehicle on the road side (the shaded side:
    the sun is behind them). Like the sector fill lights (high and wide, no spot on the ground), not like the low board
    lights. Owner 2026-11-15: "no como focos puestos en el suelo"."""
    o = options(cfg)
    if not o or not o["lights"]:
        return []
    route = route_of(cfg)
    names = list(o["vehicles"])
    lengths = [MODELS[n][1] for n in names]
    m = o["at_m"] - (sum(lengths) + o["gap_m"] * (len(names) - 1)) / 2.0
    out = []
    for ln in lengths:
        p, _ = at(route, m + ln / 2.0, o["vehicle_lateral_m"] - o["light_side_m"])
        out.append((p + [0.0, 0.0, o["light_height_m"]], o["light_radius_cm"], o["light_cd"]))
        m += ln + o["gap_m"]
    return out


def people_xyz(cfg):
    o = options(cfg)
    return [p for p in layout(route_of(cfg), o)["people"]] if o else []


def main():     # self-check on a straight synthetic route heading +x (left = +y)
    route = np.c_[np.arange(0, 200.0), np.zeros(200), np.full(200, 10.0)]
    o = dict(DEFAULTS, at_m=100.0)
    lay = layout(route, o)
    (b, _, cb, yb, _, _), (c, _, cc, yc, _, _) = lay["vehicles"]
    assert b == "BUS_01_KENYA" and abs(cb[1] - 13.0) < 1e-6 and abs(cc[1] - 13.0) < 1e-6 and cb[0] < cc[0]
    assert abs(yb + 90.0) < 1e-6 and abs(yc) < 1e-6, (yb, yc)   # bus: long axis Y, so yaw = heading - 90
    assert all(abs(p[1] - 8.5) < 1e-6 for p, _ in lay["fence"][:10]) and len(lay["people"]) == 6
    assert all(8.5 < p[1] < 13.0 for p in lay["people"])
    _ROUTES["x"] = route
    class P:
        psi_name, psi = "M_RED_ROCK_02_B", "x.PSI"
    rk = rock_props([P()], {"slug": "x", "rocks": {"psi_name": "M_RED_ROCK_02_B", "m_from": 50, "m_to": 90, "step_m": 10, "lateral_m": 6.5}})
    assert len(rk) == 5 and all(abs(abs(np.asarray(q.world)[1, 3]) - 6.5) < 0.5 for q in rk) and abs(np.asarray(rk[0].world)[2, 3] - 9.5) < 1e-6
    ps = light_positions({"scene": dict(DEFAULTS, at_m=100.0), "slug": "x"})
    assert len(ps) == 2 and all(abs(q[0][1] - 7.0) < 1e-6 and abs(q[0][2] - 19.0) < 1e-6 for q in ps), ps   # 13 - 6 m left, 9 m up
    print("wr_scene self-check ok")


if __name__ == "__main__":
    main()
