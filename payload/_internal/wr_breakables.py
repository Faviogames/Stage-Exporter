"""Breakable signs (owner 2026-11-11, Pietrosella: "hay unas pequeñas señales que se deberían de romper cuando las
tocamos ... no debe afectar prácticamente a la inercia del coche"). WRCG's signs are dynamic props there (mass 0), and
the builder leaves light dynamic props without collision: in ACR the car went through them. ACR knocks its own signs
over: BC_PhysicsActor_C, a StaticMeshActor with a PhysicsActorComponent (Munster's 50 km/h sign, cell 1XXMH...). A
stage build's "breakable_signs": [WRCG psi] swaps those WRCG signs for copies of ACR's physical one (SIGNS: the ACR mesh
and the side its plate faces, mesh xy), on the WRCG sign's post, its plate facing the same way.

The facing: on both meshes the plate is mounted in front of the post. WRCG's (FR_PANEL_R03, its convex collision):
the plate's vertices lie 3.2 cm off the post's along the plate normal. ACR's SM_TrafficSignFraSpeedlimit50 (LOD0
positions): the plate (above 2.1 m) at +2.2 cm in Y, the post at -0.4 cm: its plate faces +Y."""
import json
import re
from pathlib import Path

from wr import ROOT

WORK = ROOT / "work"
CELL = WORK / "acr" / "wr_alsace" / "acr" / "Content" / "Levels" / "AlsaceS2Munster" / "_Generated_" / \
    "1XXMH9FJVC7ZDS8TC9W2RQY3Z.json"
SIGNS = {"FR_PANEL_R03": ("SM_TrafficSignFraSpeedlimit50", (0.0, 1.0))}
PREFIX = "WrcgBreakable"
PLATE_M, POST_M = 0.9, 1.2          # top / bottom of the WRCG sign's collision: plate / post


def _cfg(slug):
    import tools.datafiles as df
    try:
        return df.load_json(f"stage_builds/{slug}.json") or {}
    except Exception:
        return {}


def wanted(slug):
    return [n for n in (_cfg(slug).get("breakable_signs") or []) if n in SIGNS]


def signs(slug, names=None):
    """[(psi, node id, post base xyz, plate front xy)] of the stage's WRCG signs (WRCG world, from their collision)."""
    import numpy as np
    names = wanted(slug) if names is None else names
    if not names:
        return []
    d = np.load(WORK / "wrcg" / slug / "collision_extra.npz", allow_pickle=True)
    P, T = d["positions"], d["triangles"]
    out = []
    for i, p in enumerate(d["owner_psi"]):
        if str(p) not in names:
            continue
        V = np.unique(P[T[d["tri_piece"] == i].reshape(-1)], axis=0).astype(float)
        if len(V) < 6:
            continue
        c = V[:, :2].mean(0)
        w, vec = np.linalg.eigh(np.cov((V[:, :2] - c).T))
        n = vec[:, 0]
        z0, z1 = V[:, 2].min(), V[:, 2].max()
        top, low = V[V[:, 2] > z1 - PLATE_M], V[V[:, 2] < z0 + POST_M]
        off = float(np.dot(top[:, :2].mean(0) - low[:, :2].mean(0), n))
        if abs(off) < 0.01:
            continue                                       # no plate offset to tell the front by
        base = low[:, :2].mean(0)
        out.append((str(p), str(d["owner_node_id"][i]), (float(base[0]), float(base[1]), float(z0)),
                    tuple(float(x) for x in n * np.sign(off))))
    return out


_REPLACED = {}


def drop_props(insts, slug):
    """The props without the WRCG signs that become ACR physical ones."""
    if slug not in _REPLACED:
        _REPLACED[slug] = {(s[0], s[1]) for s in signs(slug)}
    rep = _REPLACED[slug]
    if not rep:
        return insts
    out = [p for p in insts if ((p.psi_name or "").upper(), str(p.node_id)) not in rep]
    if len(out) != len(insts):
        print(f"    breakable signs: {len(insts) - len(out)} WRCG signs left to ACR's physical ones")
    return out


def _prop(e, name):
    return next((p for p in (e.get("Data") or []) if isinstance(p, dict) and p.get("Name") == name), None)


# --- WRCG's own small signs and posts, physical (owner 2026-11-11, 2nd drive) ----------------------------------------
# Pietrosella: "estas señales deberían romperse" (the white posts with a red band, CMN_RED_PLOT; the yellow medical
# boards, PLOT_MEDICAL_YELLOW) "la del poste si puede ser un poco más dura ... pero que se rompa"; Brattby: "unos palos a
# los laterales de la pista de nieve que deberían romperse" (DIRECTIONAL_POLEORANGE_*, STICK_RED*). ACR has no such
# meshes, so the WRCG prop itself becomes physical: its static mesh gets a box body (BodySetup AggGeom, as ACR's
# physical props have: SM_PlasticBarrierAFix, SM_MileMarkerA; boxes need no cooked data) the size of its bounds, and
# each actor becomes a copy of Munster's BC_PhysicsActor_C with the WRCG mesh, where it stood; the builder's static
# actor goes BURY_CM under the ground. The tape posts (RAILCLONE/NET_TAPE/STICK*) stay: their tapes would hang.
# 3rd drive (Brattby): "este pequeñito se rompe pero me para el coche. Al romperlo, su colisión se mantiene allí": the
# box was the whole bounds (the red stick's flag: 0.4 x 0.3 x 2.5 m = 300 kg at the default density), so the body
# hardly moved and stood there once its mesh was gone. Now the box is the post only (POST_M across, at the pivot, the
# whole height) and the mass is set (MASS_KG; the white posts with a red band a little harder, as asked); ACR's own 50
# sign weighs ~26 kg (its two boxes, scale 0.76). Also the parking and direction signs on a post, WRCG's breakable
# (_BRK) signs and mailboxes ("la señal de parking ... debería romperse").
BREAKABLE_PSI = re.compile(r"/SIGNS/MARKER/|/SIGNS/POLE/|/SIGNS/PLOTS/PLOT_(MEDICAL|RADIO)|/SE_SIGNS/STICK_|"
                           r"/ROAD_SIGNS/CMN_BALISE|/FR_PANEL_H00\.|/JAPAN_SIGNS/PARKING\.|/SE_PANEL/SE_DIRECTION_PANEL|"
                           r"/SIGNS/SIGN_\w*_BRK\.|_MAILBOX_\d+_BRK\.", re.I)
MASS_KG = ((re.compile(r"/SIGNS/MARKER/|BALISE", re.I), 22.0), (re.compile(r"MAILBOX", re.I), 15.0),
           (re.compile(r".", re.I), 8.0))
POST_M = 0.16
MAX_WIDE_M = 1.6                               # wider than this (a gate, a long board): not made physical
PROP_PREFIX = "WrcgProp_"
BURY_CM = 1.0e6
BOX_TEMPLATE = Path(__file__).resolve().parent / "wr_assets" / "box_body_template.json"


def _mass_for(psi):
    return next(m for pat, m in MASS_KG if pat.search(str(psi)))


def _body_mass(e, kg):
    """The component's BodyInstance with its mass set (bOverrideMass, MassInKgOverride)."""
    p = _prop(e, "BodyInstance")
    if not p:
        return
    vals = [v for v in p["Value"] if v.get("Name") not in ("bOverrideMass", "MassInKgOverride")]
    base = {"ArrayIndex": 0, "PropertyGuid": None, "IsZero": False, "PropertyTagFlags": "None",
            "PropertyTypeName": None, "PropertyTagExtensions": "NoExtension"}
    vals.append(dict(base, **{"$type": "UAssetAPI.PropertyTypes.Objects.BoolPropertyData, UAssetAPI",
                              "Name": "bOverrideMass", "Value": True}))
    vals.append(dict(base, **{"$type": "UAssetAPI.PropertyTypes.Objects.FloatPropertyData, UAssetAPI",
                              "Name": "MassInKgOverride", "Value": float(kg)}))
    p["Value"] = vals


def _vec_of(e, name):
    """The vector / rotator dict of a struct property; None if absent or stored as zero (an empty Value)."""
    p = _prop(e, name)
    if not p or not p.get("Value") or not isinstance(p["Value"], list):
        return None
    v = p["Value"][0].get("Value") if isinstance(p["Value"][0], dict) else None
    return v if isinstance(v, dict) else None


def _mesh_file(pkg, roots):
    rel = pkg.replace("/Game/", "acr/Content/") + ".uasset"
    return [Path(r) / rel for r in roots if (Path(r) / rel).exists()]


def mesh_bounds(uasset):
    """(origin, extent) of a mesh asset's ExtendedBounds, cm."""
    import tempfile
    import tools.acrmod.common as c
    tmp = Path(tempfile.mkdtemp(prefix="wr_bnd_"))
    try:
        c.asset_json(uasset, tmp / "m.json")
        j = json.loads((tmp / "m.json").read_text(encoding="utf-8"))
        mesh = next(e for e in j["Exports"] if e["ObjectName"] == Path(uasset).stem)
        b = {f["Name"]: f["Value"][0]["Value"] for f in _prop(mesh, "ExtendedBounds")["Value"]
             if f.get("Name") in ("Origin", "BoxExtent")}
        return ([float(b["Origin"][k]) for k in "XYZ"], [float(b["BoxExtent"][k]) for k in "XYZ"])
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)


def add_box_body(uasset, log=print, panel=False):
    """A box round the mesh's post (POST_M across at the pivot, the bounds' height) as its simple collision (BodySetup
    AggGeom); panels get a thin full-width box. False if it already has a body."""
    import copy as _copy
    import tempfile
    import tools.acrmod.common as c
    tmp = Path(tempfile.mkdtemp(prefix="wr_body_"))
    try:
        c.asset_json(uasset, tmp / "m.json")
        j = json.loads((tmp / "m.json").read_text(encoding="utf-8"))
        name = Path(uasset).stem
        mesh = next(e for e in j["Exports"] if e["ObjectName"] == name)
        body = next(e for e in j["Exports"] if "BodySetup" in e["ObjectName"])
        if any(p.get("Name") == "AggGeom" for p in body.get("Data") or []):
            return False
        b = {f["Name"]: f["Value"][0]["Value"] for f in _prop(mesh, "ExtendedBounds")["Value"]
             if f.get("Name") in ("Origin", "BoxExtent")}
        agg = json.loads(BOX_TEMPLATE.read_text(encoding="utf-8"))
        box = agg["Value"][0]["Value"][0]["Value"]
        cen = next(p for p in box if p["Name"] == "Center")["Value"][0]["Value"]
        cen["X"], cen["Y"], cen["Z"] = 0.0, 0.0, float(b["Origin"]["Z"])
        dims = {k: 2.0 * float(b["BoxExtent"][k]) for k in "XYZ"}
        if panel:
            thin = min("XY", key=dims.get)
            dims[thin] = min(12.0, dims[thin])
            cen["X"], cen["Y"] = (float(b["Origin"][k]) for k in "XY")
            # WRC's stand can extend below its pivot. Keep that part out of the collider.
            top = cen["Z"] + dims["Z"] / 2.0
            bottom = max(2.0, cen["Z"] - dims["Z"] / 2.0)
            cen["Z"], dims["Z"] = (bottom + top) / 2.0, top - bottom
        else:
            dims["X"], dims["Y"] = (min(POST_M * 100.0, dims[k]) for k in "XY")
        for p in box:
            if p["Name"] in dims:
                p["Value"] = max(2.0, dims[p["Name"]])
        body["Data"] = [agg] + list(body.get("Data") or [])
        # (never copy a stock body's cooked data into ours: 2026-11-11 the game stopped loading the stage with
        # "BodySetup_0: Serial size mismatch: Expected read size 19019, Actual read size 109")
        c.write_asset(j, tmp / "w.json", uasset)
        return True
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)


def make_physical(dst, roots, log=print):
    """WRCG's breakable props (BREAKABLE_PSI) in the level as ACR physical actors with their own mesh."""
    import wr_perf
    todo = []
    for i in range(1, len(dst.exports) + 1):
        e = dst.exp(i)
        name = e["ObjectName"]
        if not name.startswith(PROP_PREFIX) or dst.class_name(i) != "StaticMeshActor":
            continue
        stem = re.sub(r"_\d+$", "", name[len(PROP_PREFIX):])
        psi = wr_perf._PSI.get(stem)
        if not psi or not BREAKABLE_PSI.search(str(psi)):
            continue
        cp = _prop(e, "StaticMeshComponent")
        mp = _prop(dst.exp(cp["Value"]), "StaticMesh") if cp else None
        if not mp or not isinstance(mp.get("Value"), int) or mp["Value"] >= 0:
            continue
        todo.append((i, cp["Value"], mp["Value"], stem, psi))
    if not todo:
        return 0
    bodies, kinds, wide = {}, {}, []
    for _, _, mi, stem, _psi in todo:
        pkg = dst.import_key(mi)[0][0]
        if pkg in bodies:
            continue
        files = _mesh_file(pkg, roots)
        ok = False
        try:
            if files:
                _, ext = mesh_bounds(files[0])
                if 2.0 * max(ext[0], ext[1]) > MAX_WIDE_M * 100.0:
                    wide.append(stem)
                    bodies[pkg] = False
                    continue
        except Exception:
            pass
        for f in files:
            try:
                add_box_body(f, log)
                ok = True
            except Exception as ex:
                log(f"breakable props: no box body for {pkg} ({type(ex).__name__}: {ex})")
        bodies[pkg] = ok
    if wide:
        log(f"breakable props: too wide to knock over, kept static: {', '.join(sorted(set(wide)))}")
    cell = type(dst)(json.loads(CELL.read_text(encoding="utf-8")))
    level = next(k for k in range(1, len(dst.exports) + 1) if dst.class_name(k) == "Level")
    src = next(k for k in range(1, len(cell.exports) + 1) if cell.class_name(k) == "BC_PhysicsActor_C")
    n = 0
    for i, comp, mi, stem, psi in todo:
        if not bodies.get(dst.import_key(mi)[0][0]):
            continue
        old = dst.exp(comp)
        a = dst.clone(cell, src, level)[src]
        nm = f"{PREFIX}_{stem}_{n}"
        dst.add_name(nm)
        dst.exp(a)["ObjectName"] = nm
        dst.register_actor(level, a)
        ne = dst.exp(_prop(dst.exp(a), "RootComponent")["Value"])
        _prop(ne, "StaticMesh")["Value"] = mi
        ne["Data"] = [p for p in ne["Data"] if p.get("Name") != "CustomPrimitiveData"]
        _body_mass(ne, _mass_for(psi))
        for key in ("RelativeLocation", "RelativeRotation", "RelativeScale3D"):
            src_v, dst_v = _vec_of(old, key), _vec_of(ne, key)
            if dst_v is None:
                continue
            if src_v is None:
                src_v = {"Pitch": 0.0, "Yaw": 0.0, "Roll": 0.0} if key == "RelativeRotation" else \
                    {"X": 1.0, "Y": 1.0, "Z": 1.0} if key == "RelativeScale3D" else None
            if src_v is not None:
                for kk in [k for k in dst_v if not k.startswith("$")]:
                    dst_v[kk] = float(src_v.get(kk, dst_v[kk]))
        om = _prop(old, "OverrideMaterials")
        if om:
            ne["Data"].append(json.loads(json.dumps(om)))
        loc = _vec_of(old, "RelativeLocation")
        if loc is not None:
            loc["Z"] = float(loc["Z"]) - BURY_CM                     # the builder's static one out of the way
        kinds[stem] = kinds.get(stem, 0) + 1
        n += 1
    if n:
        dst._add_export_names(dst.exp(a))
        log(f"breakable props: {n} WRCG props physical, a box body on their mesh "
            f"({', '.join(f'{k} {v}' for k, v in sorted(kinds.items()))})")
    return n


def add(dst, slug, shift, ground, log=print):
    import math
    import numpy as np
    import tools.acrmod.props_visual as pv
    todo = signs(slug)
    if not todo:
        return 0
    cell = type(dst)(json.loads(CELL.read_text(encoding="utf-8")))
    level = next(i for i in range(1, len(dst.exports) + 1) if dst.class_name(i) == "Level")
    src = {}
    for i in range(1, len(cell.exports) + 1):
        if cell.class_name(i) != "BC_PhysicsActor_C":
            continue
        cp = _prop(cell.exp(i), "StaticMeshComponent")
        mp = _prop(cell.exp(cp["Value"]), "StaticMesh") if cp else None
        if mp and isinstance(mp.get("Value"), int) and mp["Value"] < 0:
            src.setdefault(cell.import_key(mp["Value"])[1][0], i)
    n = 0
    for k, (psi, node, base, front) in enumerate(todo):
        mesh, local = SIGNS[psi]
        if mesh not in src:
            log(f"breakable signs: no {mesh} in Munster's cell, {psi} left out")
            continue
        a = dst.clone(cell, src[mesh], level)[src[mesh]]
        name = f"{PREFIX}_{psi}_{k}"
        dst.add_name(name)
        dst.exp(a)["ObjectName"] = name
        dst.register_actor(level, a)
        comp = _prop(dst.exp(a), "RootComponent")["Value"]
        p0 = np.array([base, (base[0] + front[0], base[1] + front[1], base[2])], float)
        ue = pv.wrcg_world_to_ue(p0, shift)
        f = ue[1, :2] - ue[0, :2]
        yaw = math.degrees(math.atan2(f[1], f[0]) - math.atan2(local[1], local[0]))
        z = ground(float(ue[0, 0]), float(ue[0, 1]), float(ue[0, 2]))
        z = float(z) if z is not None and math.isfinite(z) else float(ue[0, 2])
        e = dst.exp(comp)
        loc = _prop(e, "RelativeLocation")["Value"][0]["Value"]
        loc["X"], loc["Y"], loc["Z"] = float(ue[0, 0]), float(ue[0, 1]), z
        rot = _prop(e, "RelativeRotation")["Value"][0]["Value"]
        rot["Pitch"], rot["Yaw"], rot["Roll"] = 0.0, yaw, 0.0
        n += 1
    if n:
        log(f"breakable signs: {n} WRCG {'/'.join(sorted({t[0] for t in todo}))} signs are ACR's physical "
            f"{'/'.join(sorted({SIGNS[t[0]][0] for t in todo}))} (BC_PhysicsActor_C, from Munster)")
    return n
