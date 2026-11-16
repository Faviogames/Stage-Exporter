"""ACR's own safety nets in place of WRCG's NetCloth (owner 2026-11-16: "que se caigan luego del golpe, duras como ahora").

Stage build "acr_nets": true | {"nets": true (false: WRCG nets stay, only the barriers below), "pole_kg": 9.0, "keep": [{"match": "GREEN", "from_m": 3030, "to_m": 3110}],
"barriers": [{"from_m": 3030, "to_m": 3110, "barrier_kg": 120.0}]}.
- every WRCG red net (NET_RED) becomes ACR's BC_LargeTapeActor with its default orange material (M_SafetyNetting_Orange)
  and every green one (LARGENET_GREEN) the same actor with M_SafetyNetting_Green, hung between wooden beams
  (SM_WoodenNarrowBeam, TapePoleActor: physical, they fall when hit) at the WRCG pieces' own positions and heights
  (pieces of 2 m are merged to spans of up to 6.5 m); the tape's own particles sag between the beams;
- "pole_kg": the beams' mass; ACR leaves it to the mesh (about 4.3 kg from its box and scale 1.3), twice that by default (owner:
  "el doble de masa");
- "keep": pieces left as WRCG cloth (+ the net_solid wall); "barriers": red pieces in those route metres become ACR's physical
  plastic barriers (SM_PlasticBarrierAFix, white and red alternating, BC_PhysicsActor_C, barrier_kg each).
The replaced pieces leave the cloth list (so no cloth and no net_solid wall for them) and their WRCG sticks are left out
(wr_roadside.replaces_stick). Not checked in game: how hard a hit on a span feels, FPS with many spans.
"""
import copy
import json
import math

import numpy as np

import wr_finish as wf
import wr_roadside as rs

DEFAULTS = {"nets": True, "pole_kg": 9.0, "keep": [], "barriers": []}
PKG = "/Game/Props/RallyProps/SafetyNetting/"
BARRIER_PKG = "/Game/Props/RallyProps/PlasticBarrierA/"
BARRIER_LEN_M = 1.55                  # SM_PlasticBarrierAFix is 1.516 m long (x), 0.54 m wide, 0.81 m tall
BARRIER_KG = 240.0
MAX_SPAN_M = 6.5
_ROUTES = {}
_PLAN = {}


def options(cfg):
    o = (cfg or {}).get("acr_nets")
    return dict(DEFAULTS, **o) if isinstance(o, dict) else (dict(DEFAULTS) if o else None)


def _route(cfg):
    slug = cfg["slug"]
    if slug not in _ROUTES:
        import tools.acrmod.build_stage as bs
        r = np.asarray(bs.route_wrcg(bs.load_cfg(slug)), float)[:, :2]
        _ROUTES[slug] = (r, np.r_[0.0, np.cumsum(np.hypot(*np.diff(r, axis=0).T))])
    return _ROUTES[slug]


def color(item):
    """'RED' | 'GREEN' | None: the WRCG net a cloth item is."""
    if item.get("template") != "NetCloth":
        return None
    m = str(item.get("material")).upper()
    return "RED" if "NET_RED" in m else "GREEN" if "LARGENET_GREEN" in m else None


def _in(rows, m, mat=None):
    return next((r for r in rows if r["from_m"] <= m <= r["to_m"] and (mat is None or r.get("match", "").upper() in mat)), None)


def classify(item, cfg):
    """None (stays WRCG cloth) | 'net' (ACR net) | 'barrier' (ACR plastic barriers), by colour and route metre."""
    o = options(cfg)
    c = color(item)
    if not o or not c:
        return None
    r, s = _route(cfg)
    p = np.asarray(item["pos"], float)
    m = float(s[int(np.hypot(r[:, 0] - p[0], r[:, 1] - p[1]).argmin())])
    if c == "RED" and _in(o["barriers"], m):
        return "barrier"
    if not o["nets"] or _in(o["keep"], m, str(item.get("material")).upper()):
        return None
    return "net"


def _endpoints(it):
    a = np.asarray(it["pos"], float)
    return a, a + float(it["size"][0]) * np.asarray(it["dir"], float)


def replaces_stick(cfg, prop):
    """A WRCG tape stick (NET_TAPE STICK*) at an end of a replaced piece, not of a kept one."""
    slug = cfg["slug"]
    if slug not in _PLAN:
        import tools.acrmod.cloth_visual as cv
        items, _ = getattr(cv.collect_cloth, "original", cv.collect_cloth)(cfg["wrcg_level"], near_m=150.0)
        gone, kept = [], []
        for it in items:
            if color(it):
                (gone if classify(it, cfg) else kept).extend(e[:2] for e in _endpoints(it))
        _PLAN[slug] = (np.asarray(gone, float).reshape(-1, 2), np.asarray(kept, float).reshape(-1, 2))
    gone, kept = _PLAN[slug]
    q = np.asarray(prop.world, float)[:2, 3]
    near = lambda P: len(P) and float(np.hypot(P[:, 0] - q[0], P[:, 1] - q[1]).min()) <= 1.0
    return bool(near(gone) and not near(kept))


def spans_of(items):
    """(poles {key: xyz}, spans [(key, key)]) of consecutive net pieces, merged to spans of up to MAX_SPAN_M."""
    always = lambda xy: True
    poles, spans = rs._tape_plan([dict(it, template="TapeCloth") for it in items], always)
    return rs._merge_tape(poles, spans, always)


def barrier_places(items):
    """[(xyz centre, heading xy)] of barriers laid end to end along the pieces' line (WRCG metres)."""
    if not items:
        return []
    pts = []
    for it in sorted(items, key=lambda i: tuple(np.round(np.asarray(i["pos"], float)[:2], 1))):
        a, b = _endpoints(it)
        pts += [a, b]
    P = np.asarray(pts, float)
    # order the pieces' starts along the line: greedy nearest neighbour from the end farthest from the centroid
    order, left = [int(np.argmax(np.hypot(*(P[:, :2] - P[:, :2].mean(0)).T)))], set(range(len(P)))
    left.discard(order[0])
    while left:
        i = min(left, key=lambda k: np.hypot(*(P[k, :2] - P[order[-1], :2])))
        order.append(i)
        left.discard(i)
    L = P[order]
    L = L[np.r_[True, np.hypot(*np.diff(L[:, :2], axis=0).T) > 0.05]]
    s = np.r_[0.0, np.cumsum(np.hypot(*np.diff(L[:, :2], axis=0).T))]
    out = []
    for d in np.arange(BARRIER_LEN_M / 2.0, s[-1] - BARRIER_LEN_M / 2.0 + 1e-6, BARRIER_LEN_M):
        c = np.array([np.interp(d, s, L[:, k]) for k in range(3)])
        h = np.array([np.interp(d + 0.4, s, L[:, k]) - np.interp(d - 0.4, s, L[:, k]) for k in range(2)])
        out.append((c, h / max(float(np.hypot(*h)), 1e-9)))
    return out


# --- writing into the level -------------------------------------------------------------------------------------------

def _pole_mass(dst, comp, kg):
    """Set the mass (bOverrideMass, MassInKgOverride) of a component that already has a BodyInstance."""
    import wr_breakables
    before = len(next((p for p in dst.exp(comp)["Data"] if p.get("Name") == "BodyInstance"), {"Value": []})["Value"])
    wr_breakables._body_mass(dst.exp(comp), kg)
    return before > 0


def _set_material(dst, comp, pkg_name, actor):
    import wr_rvt
    e = dst.exp(comp)
    om = wr_rvt._prop(e, "OverrideMaterials")
    old = om["Value"][0]["Value"]
    new = dst.ensure_import(wr_rvt._key(PKG + pkg_name, "MaterialInstanceConstant"))
    wr_rvt._set(e, wr_rvt._obj_array("OverrideMaterials", new, om))
    for idx in (actor, comp):
        for key, refs in dst.exp(idx).items():
            if key.endswith("Dependencies") and refs:
                dst.exp(idx)[key] = [new if r == old else r for r in refs]
    dst._add_export_names(e)


def _template(source):
    for i in range(1, len(source.exports) + 1):
        if source.class_name(i) != "BC_LargeTapeActor_C":
            continue
        c = rs._value(source, i, "RootComponent")
        post_comp = rs._value(source, c, "AttachParent") if c else 0
        mesh = rs._value(source, post_comp, "StaticMesh") if post_comp else 0
        if mesh < 0 and source.import_key(mesh)[1][0] == "SM_WoodenNarrowBeam":
            return i, c, post_comp, source.exp(post_comp)["OuterIndex"], rs._value(source, c, "AttachEndToActor")
    raise ValueError("ACR's large net on wooden beams was not found")


def add_nets(dst, source, groups, o, to_ue, ground, log):
    """groups: {'RED': items, 'GREEN': items}; returns (spans, poles)."""
    tape, c0, post_comp, post, end = _template(source)
    level, src_level = rs._level(dst), rs._level(source)
    parent = rs._value(source, post_comp, "AttachParent")
    mat = {"RED": "M_SafetyNetting_Orange", "GREEN": "M_SafetyNetting_Green"}
    n_poles = n_spans = massless = 0
    for col, items in groups.items():
        if not items:
            continue
        poles, spans = spans_of(items)
        place = {}
        for key, pt in poles.items():
            x, y, z = map(float, to_ue([pt])[0])
            z = float(ground(x, y, z - 100.0))
            mapping = {src_level: level}
            if parent:
                mapping[parent] = 0
            a = rs._clone(dst, source, post, level, f"WrcgAcrNetPost_{col}_{n_poles}", mapping)
            c = rs._value(dst, a, "RootComponent")
            dst.exp(c)["Data"] = [p for p in dst.exp(c)["Data"] if p.get("Name") not in {"AttachParent", "RelativeRotation"}]
            wf._vec(dst.exp(c), "RelativeLocation").update(X=x, Y=y, Z=z)
            massless += 0 if _pole_mass(dst, c, float(o["pole_kg"])) else 1
            place[key] = a, c, np.array([x, y, z])
            n_poles += 1
        for k, l in spans:
            a, c, p = place[k]
            b, _, q = place[l]
            actor = rs._clone(dst, source, tape, level, f"WrcgAcrNet_{col}_{n_spans}",
                              {src_level: level, post: a, post_comp: c, end: b})
            t = rs._value(dst, actor, "RootComponent")
            if rs._value(dst, t, "AttachParent") != c or rs._value(dst, t, "AttachEndToActor") != b:
                raise ValueError("ACR net endpoints were not remapped")
            _set_material(dst, t, mat[col], actor)
            comp = dst.exp(t)
            start_at, end_at = (wf._vec(comp, name) for name in ("RelativeLocation", "EndLocation"))
            delta = q - p
            delta[2] += float(end_at["Z"]) - float(start_at["Z"])
            length = float(np.linalg.norm(delta))
            rs._prop(dst, t, "TapeLength")["Value"] = length * 1.035
            for u, particle in zip(np.linspace(0, 1, len(rs._value(dst, t, "InitialParticlesPositions"))),
                                   rs._value(dst, t, "InitialParticlesPositions")):
                x, y, z = delta * u
                particle["Value"][0]["Value"].update(X=float(x), Y=float(y), Z=float(z - min(80, length * 0.18) * u * (1 - u)))
            n_spans += 1
    log(f"ACR nets: {n_spans} spans on {n_poles} wooden beams ({o['pole_kg']:g} kg each)"
        + (f"; {massless} beams without a body to set the mass on" if massless else ""))
    return n_spans, n_poles


def add_barriers(dst, source, items, kg, to_ue, ground, log, places=None, prefix="WrcgAcrBarrier"):
    """ACR's physical plastic barriers (a BC_PhysicsActor_C of Munster with SM_PlasticBarrierAFix) along `items`."""
    import wr_rvt
    places = barrier_places(items) if places is None else places     # places: [(centre xyz, heading xy)], WRCG metres
    if not places:
        return 0
    src = next(i for i in range(1, len(source.exports) + 1) if source.class_name(i) == "BC_PhysicsActor_C"
               and wf._prop(source.exp(rs._value(source, i, "StaticMeshComponent")), "BodyInstance"))
    level, src_level = rs._level(dst), rs._level(source)
    for n, (c, h) in enumerate(places):
        p, q = to_ue([c, c + np.r_[h, 0.0]])
        x, y, z = map(float, p)
        a = rs._clone(dst, source, src, level, f"{prefix}_{n}", {src_level: level})
        _, comp, prop = wf._mesh_of(dst, a)
        old = prop["Value"]
        new = dst.ensure_import(wr_rvt._key(BARRIER_PKG + "SM_PlasticBarrierAFix", "StaticMesh"))
        prop["Value"] = new
        e = dst.exp(comp)
        mat = dst.ensure_import(wr_rvt._key(BARRIER_PKG + ("MI_PlasticBarrierAWhite" if n % 2 == 0 else "MI_PlasticBarrierARed"),
                                             "MaterialInstanceConstant"))
        om = wr_rvt._prop(e, "OverrideMaterials")
        if om:
            old_m = om["Value"][0]["Value"]
            wr_rvt._set(e, wr_rvt._obj_array("OverrideMaterials", mat, om))
        else:
            old_m = None
            import wr_water
            tmpl = json.loads(wr_rvt.PROP_RVT.read_text(encoding="utf-8-sig"))
            wr_rvt._set(e, wr_rvt._obj_array("OverrideMaterials", mat, tmpl))
        for idx in (a, comp):
            for key, refs in dst.exp(idx).items():
                if key.endswith("Dependencies") and refs:
                    dst.exp(idx)[key] = [new if r == old else (mat if r == old_m and old_m else r) for r in refs]
        wf._vec(e, "RelativeLocation").update(X=x, Y=y, Z=float(ground(x, y, z)))
        wf._vec(e, "RelativeRotation").update(Pitch=0.0, Roll=0.0, Yaw=math.degrees(math.atan2(q[1] - y, q[0] - x)))
        e["Data"] = [d for d in e["Data"] if d.get("Name") not in ("RelativeScale3D", "CachedMaxDrawDistance")]
        _pole_mass(dst, comp, kg)
        dst._add_export_names(e)
    log(f"ACR plastic barriers: {len(places)} ({kg:g} kg each) in place of the red net")
    return len(places)


def add(dst, root, cfg, to_ue, ground, log):
    import tools.acrmod.cloth_visual as cv
    o = options(cfg)
    items, _ = getattr(cv.collect_cloth, "original", cv.collect_cloth)(cfg["wrcg_level"], near_m=150.0)
    items = rs._skip_cloth(items, cfg)
    groups, bars = {"RED": [], "GREEN": []}, []
    for it in items:
        k = classify(it, cfg)
        if k == "net":
            groups[color(it)].append(it)
        elif k == "barrier":
            bars.append(it)
    if not any(groups.values()) and not bars:
        log("ACR nets: no WRCG red or green nets to replace")
        return
    source = type(dst)(rs._fence_source(root))
    if any(groups.values()):
        add_nets(dst, source, groups, o, to_ue, ground, log)
    if bars:
        kg = next((float(z.get("barrier_kg", BARRIER_KG)) for z in o["barriers"]), BARRIER_KG)
        add_barriers(dst, source, bars, kg, to_ue, ground, log)


def main():     # self-check on synthetic pieces
    def piece(x, y, mat="NET_RED.PMA"):
        return {"pos": np.array([x, y, 0.0]), "dir": np.array([1.0, 0.0, 0.0]), "size": (2.0, 0.9), "template": "NetCloth", "material": mat}
    assert color(piece(0, 0)) == "RED" and color(piece(0, 0, "LARGENET_GREEN.PMA")) == "GREEN" and color(dict(piece(0, 0), template="TapeCloth")) is None
    items = [piece(2.0 * k, 0.0) for k in range(8)]
    poles, spans = spans_of(items)
    assert len(spans) <= 5 and len(poles) == len(spans) + 1, (len(spans), len(poles))
    b = barrier_places(items)
    assert len(b) == int(16.0 // BARRIER_LEN_M) and abs(b[0][1][0] - 1.0) < 1e-6 and abs(b[0][0][0] - BARRIER_LEN_M / 2.0) < 1e-6, b[:2]
    _ROUTES["x"] = (np.c_[np.arange(0, 60.0), np.zeros(60)], np.arange(0, 60.0))
    cfg = {"slug": "x", "acr_nets": {"keep": [{"match": "GREEN", "from_m": 0, "to_m": 20}], "barriers": [{"from_m": 30, "to_m": 50}]}}
    assert classify(piece(10, 0, "LARGENET_GREEN.PMA"), cfg) is None and classify(piece(10, 0), cfg) == "net"
    assert classify(piece(40, 0), cfg) == "barrier" and classify(piece(40, 0, "LARGENET_GREEN.PMA"), cfg) == "net"
    off = {"slug": "x", "acr_nets": {"nets": False, "barriers": [{"from_m": 30, "to_m": 50}]}}
    assert classify(piece(10, 0), off) is None and classify(piece(40, 0), off) == "barrier"
    assert options({}) is None and options({"acr_nets": True})["pole_kg"] == 9.0
    print("wr_acrnets self-check ok")


if __name__ == "__main__":
    main()
