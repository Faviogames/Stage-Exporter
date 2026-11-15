"""The road inside tunnels (owner 2026-11-11, Pietrosella, 2nd drive: "ahora el túnel se ve sin carretera por dentro").

The builder draws the road only in the baked terrain textures, which are mapped from above: the road triangles inside a
tunnel were painted on the hill over it (1st drive), and once left out of the bake (wr_fixes._drop_tunnel_road) the
tunnel floor showed the hill's grass. The tunnel road (road collision under more than wr_groundcover.TUNNEL_COVER_M of
terrain) now gets a mesh of its own: a prop for the tool's prop builder (like wr_skinned's pieces), WRCG's world-space
asphalt of that road piece (its WS_*_DIFF / NRM / IOR textures) mapped every WS_TILE_M, LIFT_M over the collision (under
the road lines, wr_skinned.LINE_LIFT_M + their 1.5 cm), both faces."""
import copy
import json
from pathlib import Path

import numpy as np

from wr import ROOT

PREFIX = "WRTUN:"
LIFT_M = 0.01
WS_TILE_M = 10.0
TEMPLATE_PMA = "DATA:/GRAPH/COUNTRY_PROPS/FR_FRANCECORSE/TUNNEL/PMA/FR_BORDER_01.PMA"     # GENERIC.PFX, 3 maps
DEFAULT_WS = "DATA:/GRAPH/ROADS_PROCEDURAL/ASPHALT/TEXTURES/WS_ASPHALT_USED_DARKGREY_01_01_DIFF.PTX"
_GEOM = {}


def _stage_dir(slug):
    return ROOT / "work" / "wrcg" / slug


def geometry(slug):
    """(positions (N, 3), triangles (M, 3), piece names of those triangles) of the stage's tunnel road, WRCG m."""
    if slug in _GEOM:
        return _GEOM[slug]
    import wr_groundcover as gc
    sd = _stage_dir(slug)
    r = np.load(sd / "collision_all_prm.npz", allow_pickle=True)
    meta = json.loads((sd / "terrain" / "meta.json").read_text(encoding="utf-8"))
    H = np.load(sd / "terrain" / "heights_0p5m.npy", mmap_mode="r")
    tun = gc._covered(r["positions"], r["triangles"], H, gc.window(meta))
    T = r["triangles"][tun]
    used, inv = np.unique(T.reshape(-1), return_inverse=True)
    pieces = sorted({str(r["piece_names"][p]) for p in r["tri_piece"][tun]}) if "piece_names" in r.files else []
    _GEOM[slug] = (r["positions"][used].astype(float), inv.reshape(-1, 3), pieces)
    return _GEOM[slug]


def _ws_texture(slug, pieces):
    """WRCG's world-space asphalt colour texture of the tunnel's road pieces (their RMat), else DEFAULT_WS."""
    try:
        idx = json.loads((_stage_dir(slug) / "index.json").read_text(encoding="utf-8"))
        stems = {p.split(".")[0].upper() for p in pieces}
        found = []

        def walk(o):
            if isinstance(o, dict):
                if str(o.get("stem", "")).upper() in stems and isinstance(o.get("rmat"), dict):
                    for m in o["rmat"].get("materials", []):
                        found.extend(t for t in m.get("textures", []) if "/WS_" in t.upper() and t.upper().endswith("_DIFF.PTX"))
                for v in o.values():
                    walk(v)
            elif isinstance(o, list):
                for v in o:
                    walk(v)
        walk(idx)
        return found[0] if found else DEFAULT_WS
    except Exception:
        return DEFAULT_WS


def instance(slug):
    import tools.wrcg.prop_instances as pi
    P, T, _ = geometry(slug)
    if not len(T):
        return None
    world = np.eye(4)
    world[:3, 3] = (P.min(0) + P.max(0)) / 2.0
    return pi.PropInstance(name="WR_TUNNEL_ROAD", path=f"WRTUN/{slug}", psi=f"{PREFIX}{slug}", psi_name="WR_TUNNEL_ROAD",
                           world=world, category="static", node_id=0, parent_name="WRTUN", spawner_id=None)


def read_prop(psi):
    import tools.wrcg.p3d_render as pr
    import wr_skinned
    slug = psi[len(PREFIX):]
    P, T, pieces = geometry(slug)
    c = (P.min(0) + P.max(0)) / 2.0
    pos = (P - c + np.array([0.0, 0.0, LIFT_M])).astype(np.float32)
    tris = np.vstack([T, T[:, ::-1]]).astype(np.int64)            # both faces
    uv = (P[:, :2] / WS_TILE_M).astype(np.float32)
    nor = np.tile(np.array([0.0, 0.0, 1.0], np.float32), (len(P), 1))
    diff = _ws_texture(slug, pieces)
    tmpl = wr_skinned._pma(TEMPLATE_PMA)
    pma = copy.copy(tmpl)
    pma.name = "WR_TUNNEL_ASPHALT"
    pma.path = Path("WR_TUNNEL_ASPHALT.PMA")
    pma.switches = {"Use DiffuseMap": 1, "Use NormalMap": 1, "Use StructureMap": 1}
    pma.params = {"DiffuseMap": diff, "NormalMap": diff[:-len("_DIFF.PTX")] + "_NRM.PTX",
                  "StructureMap": diff[:-len("_DIFF.PTX")] + "_IOR.PTX"}
    geom = pr.P3dGeom(mesh_index=0, formats=["POS_", "NORM", "UV0_"], positions=pos, triangles=tris, normals=nor,
                      normal_w=None, uvs=[uv], colors=None, tangents_raw=None)
    part = pr.PropPart(node="WR_TUNNEL_ROAD", section=0, lod=0, matrix=np.eye(4), geom=geom,
                       pma_path="DATA:/WR/WR_TUNNEL_ASPHALT.PMA", pma=pma)
    nodes = [pr.P3dNode(name="WR_TUNNEL_ROAD", local=np.eye(4), chain=np.eye(4), parent=-1, depth=0, mesh_index=0,
                        has_physics=False, n_children_declared=0)]
    model = pr.P3dModel(path=Path(f"WR_TUNNEL_ROAD_{slug}"), meshes=[], nodes=nodes, lod_distances=[0.0], heap_size=0)
    psir = pr.PsiRender(path=Path(f"WR_TUNNEL_ROAD_{slug}"), p3d=f"WR_TUNNEL_ROAD_{slug}", materials={}, shapes={})
    return pr.Prop(psi_path=psi, name="WR_TUNNEL_ROAD", model=model, psi=psir, parts=[part])


def patch():
    import tools.wrcg.p3d_render as pr
    if getattr(pr.read_prop, "_wr_tunnel", False):
        return
    orig = pr.read_prop

    def read_prop_(psi, *a, **k):
        return read_prop(psi) if str(psi).startswith(PREFIX) else orig(psi, *a, **k)

    for attr in ("_wr",):
        if getattr(orig, attr, False):
            setattr(read_prop_, attr, True)
    read_prop_._wr_tunnel = True
    pr.read_prop = read_prop_


def add_instance(out, slug):
    """The props with the stage's tunnel road added (when it has one)."""
    try:
        inst = instance(slug)
    except Exception as e:
        print(f"    tunnel road: not added ({type(e).__name__}: {e})")
        return out
    if inst is None:
        return out
    P, T, pieces = geometry(slug)
    print(f"    tunnel road: {len(T)} triangles of {', '.join(pieces)} as a road mesh of their own "
          f"({_ws_texture(slug, pieces).rsplit('/', 1)[-1]})")
    return list(out) + [inst]
