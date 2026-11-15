"""WRCG's spline-skinned meshes (COMMON/LEVELS/<level>/SPLINEMESHSKINNERBUILDSTEP/<NODE>.<node id>.PRM) in the ACR stage.

WRCG builds the painted road lines (<road piece>_LINES_BORDER / _LINES_MIDDLE), other markings (MARQUAGE), the concrete
gutters along the road (<road piece>_GUTTER), dry-stone and castle walls (HIGHWAYWALLSPAWNER / WALLSPAWNER) and a few
more by skinning a mesh along a spline; the level export reads none of them, so the ACR stages had almost no lines, no
gutters and none of these walls (owner drive 2026-11-09, Riudecanyes: the stone wall on the way down from the castle).

Reading them:
- prm.parse_rmat stops on most of these files (one zero padding byte after the RMat chunk): patch_rmat.
- A file holds a list of meshes (a wall: 5 sections of ~48 m, a gutter: 88), each with its LODs; prm.read_mesh_file reads
  the first only, so each section is read from a copy of the file that keeps that section alone (sections()).
- Placement: the vertices are in the frame of the node chain: the positions of the piece's node and of all its parents
  added up (chain_offset; checked on Riudecanyes: lines 1.5 cm over the road collision, walls standing on the terrain).
- Which: the pieces whose node is loaded with the stage (its load mask has the stage's selective-load bit, from the
  inventory) and that come within NEAR_M of the route.
Visuals: every piece becomes a prop for the tool's prop builder (props_visual): an instance whose psi is
PREFIX + '<level>/<file name>', whose model is read here (all sections, LODs as nodes <stem>_LOD<n>, the WRCG material of
each section, UVs from 0..4096 integers) instead of a P3D model; the builder makes the static mesh, its LODs, the
materials (WRCG PMA -> ACR material instance, masked where the texture has holes: the lines) and the actor. Line pieces
are lifted LINE_LIFT_M more so they are not hidden in the baked road.
Collision: the pieces' own PhysX meshes (walls ROCK, gutters KERB) are appended to collision_extra.npz after the WRCG
export as static owners (source 'wr-skinned'), so the collision container gets them like any static prop (walls then get
PM_WallRock and its impact sound, wr_fixes._patch_wall_materials).
"""
import json
import os
import re
import struct
import tempfile
from pathlib import Path

import numpy as np

DIR = "SPLINEMESHSKINNERBUILDSTEP"
PREFIX = "WRSKIN:"
SOURCE = "wr-skinned"
LINE_LIFT_M = 0.006
NEAR_M = 60.0
UV_SCALE = 4096.0


def kind(stem):
    s = stem.upper()
    if "_LINES_" in s or s.startswith("MARQUAGE"):
        return "line"
    if "GUTTER" in s:
        return "gutter"
    if "WALL" in s:
        return "wall"
    return "other"


def patch_rmat():
    """Most skinned PRMs end their RMat chunk with one padding byte (always 0); prm.parse_rmat stopped on them with
    'RMat parse ended at N, chunk size N+1'. The chunk is parsed without its zero padding."""
    import tools.wrcg.prm as prm
    if getattr(prm.parse_rmat, "_wr", False):
        return
    orig = prm.parse_rmat

    def parse_rmat(b, is_prm):
        try:
            return orig(b, is_prm)
        except ValueError as e:
            m = re.match(r"RMat parse ended at (\d+), chunk size (\d+)", str(e))
            if not m or int(m.group(2)) - int(m.group(1)) > 8 or any(bytes(b[int(m.group(1)):])):
                raise
            return orig(b[:int(m.group(1))], is_prm)

    parse_rmat._wr = True
    prm.parse_rmat = parse_rmat


# --- the level's pieces ------------------------------------------------------------------------------------------------

def _level(level):
    import tools.wrcg.gamefs as gf
    import tools.wrcg.plm_routes as pr
    return pr.Level(gf.files_root() / "WIN32" / "LEVELS" / level / f"{level}.PLM")


def chain_offset(lv, n):
    """The positions of a node and of all its parents added up. The skinned pieces' nodes share one position per kind
    (ES2_SPAIN: lines and gutters (-136.6, 1671.5, 60.1), walls (-101.5, 1427.2, 300.6)) and their parents carry the
    rest (the road piece: (0, 0, 35.4)); with the node's own position the lines came out 35.35 m under the road."""
    o = np.zeros(3)
    for _ in range(32):
        if n is None:
            break
        o += np.asarray(n.pos, float)
        n = lv.parent(n)
    return o


_PIECES = {}


def pieces(level):
    """[{file, stem, kind, node, node_id, mask, group, offset}] for the level's skinned pieces (cached per process)."""
    if level in _PIECES:
        return _PIECES[level]
    import tools.wrcg.gamefs as gf
    patch_rmat()
    lv = _level(level)
    by_id = {n.node_id: n for n in lv.plm.nodes()}
    out = []
    for f in sorted((gf.files_root() / "COMMON" / "LEVELS" / level / DIR).glob("*.PRM")):
        stem, nid = f.name.rsplit(".", 2)[0], f.name.rsplit(".", 2)[-2]
        n = by_id.get(int(nid)) if nid.isdigit() else None
        if n is None:
            continue
        out.append({"file": f, "stem": stem, "kind": kind(stem), "node": n.name, "node_id": n.node_id,
                    "mask": int(n.unk16), "group": lv.top(n).name, "offset": chain_offset(lv, n)})
    _PIECES[level] = out
    return out


_SECTIONS = {}


def sections(p):
    """prm.MeshFile per mesh of the file's mesh list (read_mesh_file reads the first one only)."""
    key = str(p["file"])
    if key in _SECTIONS:
        return _SECTIONS[key]
    import tools.wrcg.prm as prm
    patch_rmat()
    raw = p["file"].read_bytes()
    _, nodes = prm.parse_container(raw)
    meli = next(n for n in nodes if n.form == "MeLi")
    pairs = [(meli.kids[i], meli.kids[i + 1]) for i in range(0, len(meli.kids) - 1)
             if meli.kids[i].cid == "Mesh" and meli.kids[i + 1].form == "LdLi"]
    if len(pairs) <= 1:
        out = [prm.read_mesh_file(p["file"])]
    else:
        before, after = raw[:meli.off - 8], raw[meli.off + meli.size:]
        out = []
        with tempfile.TemporaryDirectory(prefix="wr_skin_") as tmp:
            for i, (m, ld) in enumerate(pairs):
                body = b"MeLi" + raw[m.off - 8:m.off + m.size] + raw[ld.off - 8:ld.off + ld.size]
                f = Path(tmp) / f"s{i}.PRM"
                data = bytearray(before + b"LIST" + struct.pack("<I", len(body)) + body + after)
                data[4:8] = struct.pack("<I", len(data) - 8)                  # RIFF size
                f.write_bytes(bytes(data))
                out.append(prm.read_mesh_file(f))
    _SECTIONS[key] = out
    return out


def lod0_world(p):
    V = [s.vpos.reshape(-1, 3) for mf in sections(p) for s in mf.submeshes if s.lod == 0]
    return np.concatenate(V) + p["offset"]


def stage_mask(stage_id):
    """1 << the stage's selective-load id (inventory load_id), or None."""
    import tools.datafiles as df
    st = next((s for s in df.load_json("wrcg_stage_inventory.json")["stages"] if s["id"] == stage_id), None)
    return int(st["load_id"]) if st and st.get("load_id") else None


def select(level, route_xy, mask=None, near_m=NEAR_M, log=print):
    """Pieces loaded with the stage (node load mask shares a bit with mask; any when mask is None) with a LOD0 vertex
    within near_m of the route (plan view)."""
    R = np.asarray(route_xy, float)[:, :2]
    lo, hi = R.min(0) - near_m, R.max(0) + near_m
    out, bad = [], []
    for p in pieces(level):
        if mask is not None and p["mask"] != -1 and not (p["mask"] & mask):
            continue
        try:
            V = lod0_world(p)[:, :2]
        except Exception as e:
            bad.append(f"{p['stem']} ({e})")
            continue
        V = V[(V[:, 0] > lo[0]) & (V[:, 0] < hi[0]) & (V[:, 1] > lo[1]) & (V[:, 1] < hi[1])]
        if not len(V):
            continue
        V = V[:: max(1, len(V) // 300)]
        d = min(float(np.sqrt(((V[:, None, :] - R[None, k:k + 1500, :]) ** 2).sum(-1)).min()) for k in range(0, len(R), 1500))
        if d <= near_m:
            out.append(p)
    if bad:
        log(f"    skinned meshes: {len(bad)} unreadable: {', '.join(bad[:5])}")
    return out


# --- visuals: synthetic props ------------------------------------------------------------------------------------------

def _pma(path):
    import tools.wrcg.gamefs as gf
    import tools.wrcg.p3d_render as pr
    rel = "WIN32/" + path.split(":/", 1)[-1] if path.upper().startswith("DATA:/") else path
    f = gf.fetch(rel)
    return pr.read_pma(f) if f else None


def _alpha_tested(pma):
    """WRCG blends its road lines over the road with their texture's alpha (LINES_GENERIC_CLEAN: paint 213 grey at
    alpha 255, the rest 44 grey at alpha 0); opaque in ACR the rest showed as a lighter rim along every line, a little
    above the darker baked road (owner 2026-11-10). With alpha test the builder gives them the masked material: the
    paint only."""
    import copy
    q = copy.copy(pma)
    q.switches = dict(pma.switches or {}, **{"Use AlphaTest": 1})
    return q


def _centre(p):
    V = lod0_world(p)
    return (V.min(0) + V.max(0)) / 2.0


def read_prop(psi):
    """A p3d_render.Prop for PREFIX + '<level>/<file name>': one part per section, material and LOD (LOD n as node
    <stem>_LOD<n>, the way the builder recognises a P3D model's LODs), around the piece's LOD0 centre."""
    import tools.wrcg.p3d_render as pr
    level, name = psi[len(PREFIX):].split("/", 1)
    p = next(q for q in pieces(level) if q["file"].name == name)
    c = _centre(p) - p["offset"]
    pmas, parts, nl = {}, [], 1
    for mf in sections(p):
        mats = mf.rmat.materials if mf.rmat else []
        for s in mf.submeshes:
            shader = mats[s.material_index]["shader"] if s.material_index < len(mats) else None
            if shader not in pmas:
                pmas[shader] = _pma(shader) if shader else None
                if p["kind"] == "line" and pmas[shader] is not None:
                    pmas[shader] = _alpha_tested(pmas[shader])
            pos = s.vpos.reshape(-1, 3)
            uv = np.asarray(s.uvs, float).reshape(len(pos), -1) / UV_SCALE if s.uvs is not None else np.zeros((len(pos), 2))
            uvs = [uv[:, 2 * k:2 * k + 2].astype(np.float32) for k in range(max(1, uv.shape[1] // 2))]
            nor = None if s.nor is None else np.asarray(s.nor, np.float32).reshape(len(pos), -1)[:, :3]
            geom = pr.P3dGeom(mesh_index=s.lod, formats=["POS_", "NORM", "UV0_"], positions=(pos - c).astype(np.float32),
                              triangles=np.asarray(s.indices, np.int64).reshape(-1, 3), normals=nor, normal_w=None,
                              uvs=uvs, colors=None, tangents_raw=None)
            node = p["stem"] if s.lod == 0 else f"{p['stem']}_LOD{s.lod}"
            parts.append(pr.PropPart(node=node, section=s.material_index, lod=s.lod, matrix=np.eye(4), geom=geom,
                                     pma_path=shader, pma=pmas[shader]))
            nl = max(nl, s.lod + 1)
    names = [p["stem"]] + [f"{p['stem']}_LOD{k}" for k in range(1, nl)]
    nodes = [pr.P3dNode(name=n, local=np.eye(4), chain=np.eye(4), parent=-1, depth=0, mesh_index=k, has_physics=False,
                        n_children_declared=0) for k, n in enumerate(names)]
    model = pr.P3dModel(path=p["file"], meshes=[], nodes=nodes, lod_distances=[float(k) for k in range(nl)], heap_size=0)
    psir = pr.PsiRender(path=p["file"], p3d=str(p["file"]), materials={}, shapes={})
    return pr.Prop(psi_path=psi, name=unique_name(p), model=model, psi=psir, parts=parts)


def unique_name(p):
    """Piece name + node id: names repeat (Riudecanyes has two HIGHWAYWALLSPAWNER_1, _3, _16, ...) and the builder names
    the static mesh after the prop, so two walls ended up with one mesh."""
    return f"{p['stem']}_{p['node_id']}"


def instance(level, p):
    import tools.wrcg.prop_instances as pi
    c = _centre(p)
    if p["kind"] == "line":
        c = c + np.array([0.0, 0.0, LINE_LIFT_M])
    world = np.eye(4)
    world[:3, 3] = c
    return pi.PropInstance(name=unique_name(p), path=f"{DIR}/{p['stem']}.{p['node_id']}", psi=f"{PREFIX}{level}/{p['file'].name}",
                           psi_name=f"WRSKIN_{unique_name(p)}", world=world, category="static", node_id=p["node_id"],
                           parent_name=p["group"], spawner_id=None)


def patch_props(stage_info, log=print):
    """Add the stage's skinned pieces to the props (the static ones near the route) and read their models here.
    stage_info() -> (cfg, stage mask) of the stage being built, or None."""
    import tools.wrcg.p3d_render as pr
    import tools.wrcg.prop_instances as pi
    if getattr(pi.collect_instances, "_wr", False):
        return
    orig_ci, orig_rp = pi.collect_instances, pr.read_prop

    def read_prop_(psi, *a, **k):
        return read_prop(psi) if str(psi).startswith(PREFIX) else orig_rp(psi, *a, **k)

    def collect_instances(level="SSS_IT_ITTIRI", categories=("static", "dynamic", "clutter", "spline", "decor"), **k):
        out, info = orig_ci(level, categories, **k)
        si = stage_info()
        if si is None or "static" not in categories or k.get("route_xy") is None:
            return out, info
        cfg, mask = si
        if not cfg.get("skinned_meshes", True):
            return out, info
        sel = select(level, k["route_xy"], mask, min(float(k.get("near_m") or NEAR_M), NEAR_M), log)
        if sel:
            out = list(out) + [instance(level, p) for p in sel]
            n = {}
            for p in sel:
                n[p["kind"]] = n.get(p["kind"], 0) + 1
            log(f"    skinned meshes: {len(sel)} pieces added to the props ({', '.join(f'{v} {k_}' for k_, v in sorted(n.items()))})")
        return out, info

    read_prop_._wr = collect_instances._wr = True
    pr.read_prop = read_prop_
    pi.collect_instances = collect_instances


# --- collision ---------------------------------------------------------------------------------------------------------

def append_collision(stage_dir, level, mask, log=print):
    """Append the PhysX meshes of the stage's skinned pieces to <stage_dir>/collision_extra.npz as static owners."""
    import tools.wrcg.prm as prm
    npz = Path(stage_dir) / "collision_extra.npz"
    route = Path(stage_dir) / "route_centerline_1m.csv"
    if not npz.exists() or not route.exists():
        return 0
    R = np.loadtxt(route, delimiter=",", skiprows=1)[:, 1:3]
    d = dict(np.load(npz, allow_pickle=False))
    keep = d["owner_source"] != SOURCE                                    # a second run replaces ours
    if not keep.all():
        tri_keep = keep[d["tri_piece"]]
        remap = -np.ones(len(keep), np.int64)
        remap[keep] = np.arange(int(keep.sum()))
        for k in list(d):
            if k.startswith("owner_"):
                d[k] = d[k][keep]
        for k in ("triangles", "tri_piece", "tri_slot_sub", "tri_surface", "tri_surface_src", "tri_category"):
            d[k] = d[k][tri_keep]
        d["tri_piece"] = remap[d["tri_piece"]].astype(d["tri_piece"].dtype)
    surf = list(d["surface_names"])
    cat_static = list(d["category_names"]).index("static")
    src_idx = list(d["surface_src_names"]).index("baked_prm") if "baked_prm" in list(d["surface_src_names"]) else 0
    P, T, piece, surface, owners = [d["positions"]], [d["triangles"]], [d["tri_piece"]], [d["tri_surface"]], []
    nv, no = len(d["positions"]), len(d["owner_name"])
    added = {}
    for p in select(level, R, mask, log=log):
        if p["kind"] == "line":
            continue
        mf = sections(p)[0]
        ents = prm.read_phys_prm(mf.raw, mf.phys_off, mf.phys_size) if mf.phys_off else []
        for e in ents:
            if e.mesh is None or not len(e.mesh.tris):
                continue
            name = (e.pmc or "").upper() or ("KERB" if p["kind"] == "gutter" else "ROCK")
            if name not in surf:
                name = "ROCK"
            V = np.asarray(e.mesh.verts, np.float64).reshape(-1, 3) + p["offset"]
            F = np.asarray(e.mesh.tris, np.int64).reshape(-1, 3)
            P.append(V.astype(np.float32))
            T.append((F + nv).astype(d["triangles"].dtype))
            piece.append(np.full(len(F), no + len(owners), d["tri_piece"].dtype))
            surface.append(np.full(len(F), surf.index(name), d["tri_surface"].dtype))
            owners.append((p, name, V, len(F)))
            nv += len(V)
            added[p["kind"]] = added.get(p["kind"], 0) + len(F)
    if not owners:
        return 0
    if no + len(owners) > np.iinfo(d["tri_piece"].dtype).max:
        log("    skinned meshes: too many collision owners, collision not added")
        return 0
    nt = sum(len(x) for x in T) - len(d["triangles"])
    d["positions"], d["triangles"] = np.concatenate(P), np.concatenate(T)
    d["tri_piece"], d["tri_surface"] = np.concatenate(piece), np.concatenate(surface)
    d["tri_slot_sub"] = np.concatenate([d["tri_slot_sub"], np.zeros(nt, d["tri_slot_sub"].dtype)])
    d["tri_surface_src"] = np.concatenate([d["tri_surface_src"], np.full(nt, src_idx, d["tri_surface_src"].dtype)])
    d["tri_category"] = np.concatenate([d["tri_category"], np.full(nt, cat_static, d["tri_category"].dtype)])

    def add(key, vals):
        arr = d[key]
        vals = np.asarray(vals)
        if arr.dtype.kind == "U":
            width = max(arr.dtype.itemsize // 4, max((len(str(v)) for v in vals), default=1))
            d[key] = np.concatenate([arr.astype(f"<U{width}"), vals.astype(f"<U{width}")])
        else:
            d[key] = np.concatenate([arr, vals.astype(arr.dtype)])

    add("owner_name", [p["stem"] for p, *_ in owners])
    add("owner_path", [f"{DIR}/{p['stem']}.{p['node_id']}" for p, *_ in owners])
    add("owner_psi", ["" for _ in owners])
    add("owner_category", [cat_static for _ in owners])
    add("owner_dynamic", [False for _ in owners])
    add("owner_mass", [0.0 for _ in owners])
    add("owner_shape_kinds", ["mesh" for _ in owners])
    add("owner_surface", [s for _, s, _, _ in owners])
    add("owner_source", [SOURCE for _ in owners])
    add("owner_node_id", [p["node_id"] for p, *_ in owners])
    d["owner_bbox_min"] = np.concatenate([d["owner_bbox_min"], np.array([V.min(0) for *_, V, _ in owners], d["owner_bbox_min"].dtype)])
    d["owner_bbox_max"] = np.concatenate([d["owner_bbox_max"], np.array([V.max(0) for *_, V, _ in owners], d["owner_bbox_max"].dtype)])
    add("owner_ntris", [n for *_, n in owners])
    for k in [k for k in d if k.startswith("owner_")]:
        assert len(d[k]) == len(d["owner_name"]), k
    np.savez(npz, **d)
    log(f"    skinned meshes: collision of {len(owners)} pieces added ({', '.join(f'{v} {k} triangles' for k, v in sorted(added.items()))})")
    return len(owners)
