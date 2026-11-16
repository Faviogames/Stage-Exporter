"""WRCG's animals as props (owner 2026-11-14: Kenya's flamingos and giraffes; cows he saw at the start are WRCG's BUFFALO).

The level's animals are nodes under <tag>/<..>_<tag>_GRAPH/ANIMALS: BUFFALO01_n, FLAMINGO_n, GIRAFE_n, ... The base
collector leaves them out ('/CHARACTERS/' is in prop_instances.EXCLUDE_PSI_PATTERNS) and flamingos and giraffes are not
mesh nodes at all (their model comes through a public graphic bank), so the instances are made here from the nodes by name:
  FLAMINGO_<n> -> FLAMINGO_01 / FLAMINGO_02 PSI (the bank's two meshes, by parity), GIRAFE_<n> -> GIRAFE,
  BUFFALO01_<n> -> BUFFALO03.
Stage build "animals": {"tag": "SS2", "types": ["FLAMINGO", "GIRAFE"], "near_m": 150, "max": 80}. The flamingos are static
meshes; giraffes and buffalo are skinned and stand in their bind pose, frozen (shortcut: no animation, no collision).
"""
import copy
import re

import numpy as np

from wr import ROOT

DIR = "DATA:/GRAPH/CHARACTERS/ANIMALS/"
MESH = {"FLAMINGO": lambda n: f"FLAMINGO_0{1 + n % 2}", "GIRAFE": lambda n: "GIRAFE", "BUFFALO01": lambda n: "BUFFALO03"}
NAME = re.compile(r"(?i)^(FLAMINGO|GIRAFE|BUFFALO01)_(\d+)$")


_AUTO = {}
AUTO = {"types": ["GIRAFE", "BUFFALO"], "min_straight_m": 400.0, "every_m": 260.0, "herd": [2, 5], "offset_m": [28.0, 60.0], "seed": 7}


def straights(route, min_len, max_deg=14.0):
    """[(s0, s1)] route metres of runs that turn less than max_deg in any 100 m, at least min_len long."""
    xy = np.asarray(route, float)[:, :2]
    along = np.r_[0.0, np.cumsum(np.hypot(*np.diff(xy, axis=0).T))]
    m = np.arange(0.0, along[-1], 10.0)
    P = np.c_[np.interp(m, along, xy[:, 0]), np.interp(m, along, xy[:, 1])]
    h = np.arctan2(*(P[5:] - P[:-5]).T[::-1])
    turn = np.degrees(np.abs(np.angle(np.exp(1j * (h[10:] - h[:-10])))))
    ok = np.r_[turn < max_deg, False]
    out, start = [], None
    for i, f in enumerate(ok):
        if f and start is None:
            start = i
        if not f and start is not None:
            if (i - start) * 10.0 >= min_len:
                out.append((m[start] + 50.0, m[min(i, len(m) - 1)] + 50.0))
            start = None
    return out


def herds(route, template, gp, blocked=None):
    """Herds of animals beside the long straights ("auto": {"types", "min_straight_m", "every_m", "herd": [min, max],
    "offset_m": [near, far], "seed"}): one every_m metres, sides alternating, each animal turned its own way, at the
    height of the route (shortcut: a bank beside the road may leave them floating or sunk; frozen, no collision)."""
    o = dict(AUTO, **(gp.get("auto") if isinstance(gp.get("auto"), dict) else {}))
    route = np.asarray(route, float)
    along = np.r_[0.0, np.cumsum(np.hypot(*np.diff(route[:, :2], axis=0).T))]
    rng = np.random.default_rng(int(o["seed"]))
    out, side = [], 1.0
    for s0, s1 in straights(route, float(o["min_straight_m"])):
        for m in np.arange(s0 + 60.0, s1 - 60.0, float(o["every_m"])):
            i = int(np.clip(np.searchsorted(along, m), 3, len(route) - 4))
            hd = route[i + 3, :2] - route[i - 3, :2]
            hd = hd / np.hypot(*hd)
            n = np.array([-hd[1], hd[0]])
            side = -side
            kind = o["types"][int(rng.integers(len(o["types"])))].upper()
            kind = "BUFFALO01" if kind == "BUFFALO" else kind
            c = route[i, :2] + side * n * rng.uniform(*o["offset_m"])
            for k in range(int(rng.integers(o["herd"][0], o["herd"][1] + 1))):
                q = c + rng.normal(0, 4.0, 2)
                if blocked is not None and blocked(q):
                    continue
                t = rng.uniform(0, 2 * np.pi)
                w = np.array([[np.cos(t), -np.sin(t), 0, q[0]], [np.sin(t), np.cos(t), 0, q[1]], [0, 0, 1, route[i, 2]], [0, 0, 0, 1]])
                name = MESH[kind](k)
                p = copy.copy(template)
                for a_, v in (("category", "static"), ("name", f"WrcgHerd_{kind}_{len(out)}"), ("node_id", f"herd{len(out)}"),
                              ("parent_name", "WrcgHerd"), ("path", f"WrcgHerd/{kind}_{len(out)}"), ("psi", f"{DIR}{name}.PSI"),
                              ("psi_name", name), ("spawner_id", None), ("world", w)):
                    setattr(p, a_, v)
                out.append(p)
    return out


def placed(route, template, rows):
    """Hand-placed groups, "animals.place": [{"m": 4453, "type": "GIRAFE", "per_side": 3, "lateral_m": [22, 40], "spread_m": 40,
    "seed": 1}]: per_side animals on each side of the road around route metre m (lateral from the centreline), spread_m long,
    each turned its own way, at the route's height (frozen, no collision). Owner 2026-11-16, Ngema m ~4453."""
    import wr_scene
    out = []
    for r in rows:
        rng = np.random.default_rng(int(r.get("seed", 1)))
        kind = str(r.get("type", "GIRAFE")).upper()
        kind = "BUFFALO01" if kind == "BUFFALO" else kind
        lat = r.get("lateral_m", [22.0, 40.0])
        for side in (1.0, -1.0):
            for k in range(int(r.get("per_side", 3))):
                m = float(r["m"]) + (k + rng.uniform(-0.3, 0.3) - (int(r.get("per_side", 3)) - 1) / 2.0) * float(r.get("spread_m", 40.0)) / max(1, int(r.get("per_side", 3)) - 1)
                c, _ = wr_scene.at(route, m, side * rng.uniform(*lat))
                t = rng.uniform(0, 2 * np.pi)
                w = np.array([[np.cos(t), -np.sin(t), 0, c[0]], [np.sin(t), np.cos(t), 0, c[1]], [0, 0, 1, c[2]], [0, 0, 0, 1]])
                name = MESH[kind](k)
                p = copy.copy(template)
                for a_, v in (("category", "static"), ("name", f"WrcgPlaced_{kind}_{len(out)}"), ("node_id", f"placed{len(out)}"),
                              ("parent_name", "WrcgPlaced"), ("path", f"WrcgPlaced/{kind}_{len(out)}"), ("psi", f"{DIR}{name}.PSI"),
                              ("psi_name", name), ("spawner_id", None), ("world", w)):
                    setattr(p, a_, v)
                out.append(p)
    return out


def instances(level, template, route_xy, gp):
    import tools.wrcg.plm as plm
    import tools.wrcg.plm_props as pp
    nodes = plm.Plm(ROOT / "work" / "wrcg_fs" / "WIN32" / "LEVELS" / level / f"{level}.PLM").nodes()
    tag = gp["tag"]
    want = {t.upper() for t in gp.get("types") or ["FLAMINGO", "GIRAFE"]}
    want |= {"BUFFALO01"} if "BUFFALO" in want else set()
    near = float(gp.get("near_m", 150.0))
    graphs = re.compile(rf"^{re.escape(tag)}/\w*_{re.escape(tag)}_GRAPHS?$", re.I)
    R = np.asarray(route_xy, float)[:, :2]
    stack, parent, out = [], {}, []
    for n in nodes:
        while stack and stack[-1].depth >= n.depth:
            stack.pop()
        parent[n.index] = stack[-1] if stack else None
        stack.append(n)
    for n in nodes:
        m = NAME.match(n.name)
        if not m or m.group(1).upper() not in want:
            continue
        chain, q = [], n
        while q is not None:
            chain.append(q)
            q = parent[q.index]
        if not any(x.name.upper() == "ANIMALS" for x in chain) or not any(graphs.match(x.name) for x in chain):
            continue
        w = np.eye(4)
        for q in chain:
            w = np.asarray(pp.node_matrix(q.pos, q.rot, q.scale)) @ w
        if np.hypot(R[:, 0] - w[0, 3], R[:, 1] - w[1, 3]).min() > near:
            continue
        kind, k = m.group(1).upper(), int(m.group(2))
        name = MESH[kind](k)
        p = copy.copy(template)
        for a, v in (("category", "static"), ("name", n.name), ("node_id", str(n.node_id)), ("parent_name", chain[1].name),
                     ("path", "/".join(x.name for x in reversed(chain))), ("psi", f"{DIR}{name}.PSI"),
                     ("psi_name", name), ("spawner_id", None), ("world", w)):
            setattr(p, a, v)
        out.append(p)
    out = out[: int(gp.get("max", 80))]
    if gp.get("place"):                                      # hand-placed groups by route metre
        try:
            import tools.acrmod.build_stage as bs
            import tools.acrmod.stagectx as sc
            extra = placed(np.asarray(bs.route_wrcg(bs.load_cfg(sc.cur().slug)), float), template, gp["place"])
            print(f"    animals: {len(extra)} placed by hand")
            out += extra
        except Exception as e:
            print(f"    animals: placed groups not added ({type(e).__name__}: {e})")
    if gp.get("auto") not in (None, False):                                       # herds on the long straights (every stage; the WRCG ones above are few)
        try:
            import tools.acrmod.build_stage as bs
            import tools.acrmod.stagectx as sc
            import wr_fixes
            import wr_roadside as rs
            slug = sc.cur().slug
            if slug not in _AUTO:                            # this runs once per prop collection (~150 per export): read the data once
                _AUTO[slug] = (np.asarray(bs.route_wrcg(bs.load_cfg(slug)), float), rs._road_test(ROOT / "work" / "wrcg" / slug, margin_cells=6),
                               rs._obstacles(dict(wr_fixes._cfg(slug) or {}, slug=slug)))
            route, clear, obstacles = _AUTO[slug]
            extra = herds(route, template, gp, lambda q: not clear(q) or rs._blocked(q, q, obstacles))
            print(f"    animals: {len(extra)} in herds beside the long straights")
            out += extra
        except Exception as e:
            print(f"    animals: herds not added ({type(e).__name__}: {e})")
    return out


def main():     # self-check of the name mapping
    assert NAME.match("FLAMINGO_118") and NAME.match("GIRAFE_3") and NAME.match("BUFFALO01_52") and not NAME.match("ZEBRA_1")
    assert MESH["FLAMINGO"](7) == "FLAMINGO_02" and MESH["FLAMINGO"](8) == "FLAMINGO_01"
    route = np.c_[np.arange(0, 1500.0), np.zeros(1500), np.zeros(1500)]
    st = straights(route, 400.0)
    assert len(st) == 1 and st[0][0] < 100 and st[0][1] > 1300, st
    class P:
        pass
    hs = herds(route, P(), {"auto": {"every_m": 300}})
    assert len(hs) >= 6 and all(20 < abs(np.asarray(q.world)[1, 3]) < 90 for q in hs) and len({np.sign(np.asarray(q.world)[1, 3]) for q in hs}) == 2
    print("wr_animals self-check ok")


if __name__ == "__main__":
    main()
