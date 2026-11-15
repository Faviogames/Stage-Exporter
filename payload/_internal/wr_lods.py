"""WRCG props whose LOD nodes are named out of order: the LODs are put in order of detail.

Some WRCG models name their LOD nodes against their detail. HIGHWAY_ALSACE_MIDDLE_SNOW (Sweden's snowy guard rail, 283 on
Sävar) has 'HIGHWAY_ALSACE_MIDDLE_SNOW' = a 4-triangle snow strip, '_LOD1' = the snow (344), '_LOD2' = the rail (1260) and
'_LOD3' = a 35-triangle rail; the snow of the Swedish houses puts different things under one name (SE_GARAGE_SNOW 'Snow':
the roof snow, a snow bank beside the garage as _LOD1/_LOD2, a ground patch as _LOD3). In ACR the builder takes the names,
so close up the rail was a strip and it appeared farther away (owner 2026-11-09: "the road barriers show at some
distances and not at others").

Per object (the node name without _LOD<n>) whose triangle counts do not go down with the LOD number, the LOD meshes are
grouped by their bounding box: near-identical boxes (IoU >= SAME_BOX: the rail and its 35-triangle version 0.57, the
garage bank 1.0) are LODs of one thing and are ordered by triangle count; meshes with other boxes (rail vs snow 0.24) are
separate things and are shown at every LOD. LOD k is the k-th mesh of every group (its last one where a group has fewer).

A LOD mesh made of separate cards (welded open-edge share > CARD_OPEN) is not a LOD but a cut-out detail: HAYSTACK
(Panzerplatte's red-banded bales at the start and finish, 25) has the bale as 'IT_Haystack_01' (52) and '_LOD1' (166)
and its straw tufts as '_LOD2' (94 triangles, 0.68 open). Ordered by triangles the tufts came second, so a little away
the bale was gone and only the tufts were left floating (owner 2026-11-10: "las balas de paja ... se tienen que ver
así"). The cards go with LOD0, seen from both sides, and their material gets alpha test.
"""
import re
from collections import defaultdict

import numpy as np

LOD_RE = re.compile(r"_LOD(\d+)$", re.I)
GROW = 1.25                 # a LOD with 25 % more triangles than the one before: out of order
SAME_BOX = 0.5              # bounding boxes overlapping this much (IoU) are LODs of one thing
CARD_OPEN = 0.5             # a LOD mesh with more open edges than this is cut-out cards (straw tufts), not a LOD...
CARD_MIN_PIECES = 12        # ...made of this many separate pieces (HAYSTACK's tufts 25; Sweden's rail LOD3 9)...
CARD_FLAT = 0.95            # ...with this share of their area in flat pieces (tufts 1.00, the rail's LOD3 0.76)
FLAT_DEG = 25.0
_stats = {"props": 0, "objects": 0}


def _tris(parts):
    return sum(len(p.geom.triangles) for p in parts)


def _box(parts):
    P = np.concatenate([np.asarray(p.geom.positions, float).reshape(-1, 3) for p in parts])
    return P.min(0), P.max(0)


def _iou(a, b):
    lo, hi = np.maximum(a[0], b[0]), np.minimum(a[1], b[1])
    inter = np.prod(np.clip(hi - lo, 0, None) + 1e-3)
    va, vb = np.prod(a[1] - a[0] + 1e-3), np.prod(b[1] - b[0] + 1e-3)
    return float(inter / (va + vb - inter))


def fix(prop):
    """Reorders the LODs of the objects that need it, in place; returns the number of objects changed."""
    if not isinstance(prop.parts, list):
        return 0
    objects = defaultdict(lambda: defaultdict(list))          # base node -> lod -> parts
    for part in prop.parts:
        objects[LOD_RE.sub("", part.node)][part.lod].append(part)
    changed = 0
    for base, by_lod in objects.items():
        lods = sorted(by_lod)
        if len(lods) < 2:
            continue
        t = [_tris(by_lod[l]) for l in lods]
        if not any(t[i + 1] > GROW * t[i] for i in range(len(t) - 1)):
            continue
        cards = [l for l in lods if _open_ratio(by_lod[l]) > CARD_OPEN and _pieces(by_lod[l]) >= CARD_MIN_PIECES
                 and _pieces(by_lod[l], flat=True) >= CARD_FLAT]
        solid = [l for l in lods if l not in cards]
        if not solid:
            cards, solid = [], lods
        groups = []                                           # [(box, [lod, ...])]
        for l in solid:
            b = _box(by_lod[l])
            g = next((g for g in groups if _iou(g[0], b) >= SAME_BOX), None)
            if g is None:
                groups.append((b, [l]))
            else:
                g[1].append(l)
        order = [sorted(g[1], key=lambda l: -_tris(by_lod[l])) for g in groups]
        n = max(len(o) for o in order)
        new_lod = {}
        for o in order:
            for k in range(n):
                new_lod.setdefault(o[min(k, len(o) - 1)], set()).add(k)
        for l in cards:                     # cut-out details (straw tufts) go with the most detailed mesh only
            new_lod[l] = {0}
            for part in by_lod[l]:
                if part.geom is not None:
                    part.geom = _doubled(part.geom)
            _cut_out(prop, by_lod[l])
        for l, ks in new_lod.items():
            k = min(ks)                     # a group with fewer LODs keeps its last mesh for the farther LODs
            for part in by_lod[l]:
                part.lod = k
                part.node = base if k == 0 else f"{base}_LOD{k}"
        extra = []                          # copies of a short group's last mesh for the LODs past its own
        for o in order:
            last = o[-1]
            for k in range(len(o), n):
                for part in by_lod[last]:
                    q = _copy(part)
                    q.lod, q.node = k, f"{base}_LOD{k}"
                    extra.append(q)
        prop.parts.extend(extra)
        changed += 1
    if changed:
        _merge_sections(prop)
        _sync_nodes(prop)
        _stats["props"] += 1
        _stats["objects"] += changed
    return changed


def _open_ratio(parts):
    """Share of a mesh's edges used by one face only, after welding equal positions: about 0 for a closed mesh, 0.68
    for HAYSTACK's straw tufts (separate cards)."""
    o = e = 0
    for p in parts:
        if p.geom is None or not len(p.geom.triangles):
            continue
        P = np.round(np.asarray(p.geom.positions, float).reshape(-1, 3), 3)
        _, inv = np.unique(P, axis=0, return_inverse=True)
        T = inv.reshape(-1)[np.asarray(p.geom.triangles, np.int64).reshape(-1, 3)]
        ed = np.sort(np.concatenate([T[:, [0, 1]], T[:, [1, 2]], T[:, [2, 0]]]), axis=1)
        _, cnt = np.unique(ed, axis=0, return_counts=True)
        o += int((cnt == 1).sum())
        e += len(cnt)
    return o / max(e, 1)


def _pieces(parts, flat=False):
    """Number of separate pieces (connected by shared welded vertices) of a mesh; flat=True: the share of its area in
    flat pieces (every face within FLAT_DEG of the piece's mean normal), i.e. cards."""
    n, area, flat_area = 0, 0.0, 0.0
    for p in parts:
        if p.geom is None or not len(p.geom.triangles):
            continue
        P = np.round(np.asarray(p.geom.positions, float).reshape(-1, 3), 3)
        _, inv = np.unique(P, axis=0, return_inverse=True)
        T = inv.reshape(-1)[np.asarray(p.geom.triangles, np.int64).reshape(-1, 3)]
        root = np.arange(int(inv.max()) + 1)

        def find(a):
            while root[a] != a:
                root[a] = root[root[a]]
                a = root[a]
            return a
        for a, b, c in T:
            ra, rb, rc = find(a), find(b), find(c)
            root[rb] = ra
            root[find(rc)] = ra
        n += len({find(v) for v in np.unique(T)})
        if flat:
            V = np.asarray(p.geom.positions, float).reshape(-1, 3)[np.asarray(p.geom.triangles, np.int64).reshape(-1, 3)]
            fn = np.cross(V[:, 1] - V[:, 0], V[:, 2] - V[:, 0])
            a = np.linalg.norm(fn, axis=1)
            u = fn / np.maximum(a, 1e-12)[:, None]
            piece = np.array([find(t[0]) for t in T])
            for r in np.unique(piece):
                m = piece == r
                mean = (u[m] * a[m, None]).sum(0)
                mean /= max(np.linalg.norm(mean), 1e-12)
                area += a[m].sum()
                if (np.abs(u[m] @ mean) >= np.cos(np.radians(FLAT_DEG))).all():
                    flat_area += a[m].sum()
    return flat_area / max(area, 1e-12) if flat else n


def _cut_out(prop, parts):
    """The material of these cards with alpha test, for every part of the prop that uses it: WRCG draws the tufts of
    HAYSTACK with its texture's alpha (MEULE_DIFF: the tufts at 255 on a 0 background, the bale all 255) although its
    PMA says no alpha test; opaque in ACR they were pale rectangles around the bale."""
    import copy
    done = {}
    for part in parts:
        pma = getattr(part, "pma", None)
        if pma is None or (pma.switches or {}).get("Use AlphaTest"):
            continue
        key = getattr(part, "pma_path", None) or id(pma)
        if key not in done:
            q = copy.copy(pma)
            q.switches = dict(pma.switches or {}, **{"Use AlphaTest": 1})
            done[key] = q
    for part in prop.parts:
        key = getattr(part, "pma_path", None) or id(getattr(part, "pma", None))
        if key in done:
            part.pma = done[key]


# WRCG draws an object without LOD variants (a node with no _LOD<n> siblings) at every distance; the builder puts it in
# LOD0 only, so past LOD0 it was gone. Sävar's first houses (owner 2026-11-10, "las casas ... se ven rotísimas"):
# SE_HOUSE_03 kept its walls but lost its roof (SE_House_Roof_03, LOD0 only), SE_HOUSE_03_SNOW kept its snow sheets but
# lost the house under them (FI_House_03). Such an object gets copies of its last mesh in the prop's farther LODs.
def fill_lods(prop):
    if not isinstance(prop.parts, list):
        return 0
    n = max((p.lod for p in prop.parts), default=0)
    if n == 0:
        return 0
    objects = defaultdict(lambda: defaultdict(list))
    for part in prop.parts:
        objects[LOD_RE.sub("", part.node)][part.lod].append(part)
    extra, filled = [], 0
    for base, by_lod in objects.items():
        have = sorted(by_lod)
        missing = [k for k in range(have[0] + 1, n + 1) if k not in by_lod]
        if not missing or have[0] != 0:                    # complete, or a far-only object (impostor cards)
            continue
        for k in missing:
            src = max(l for l in by_lod if l < k)
            for part in by_lod[src]:
                q = _copy(part)
                q.lod, q.node = k, f"{base}_LOD{k}"
                extra.append(q)
        filled += 1
    if extra:
        prop.parts.extend(extra)
        _merge_sections(prop)
        _sync_nodes(prop)
    return filled


def _copy(part):
    import copy
    q = copy.copy(part)
    q.geom = copy.copy(part.geom)
    return q


def _merge_sections(prop):
    """Parts that now share node and section (the snow and the rail, one material) become one mesh."""
    import tools.wrcg.p3d_render as pr
    by = defaultdict(list)
    for part in prop.parts:
        by[(part.node, part.section)].append(part)
    out = []
    for (node, sec), parts in by.items():
        if len(parts) == 1:
            out.append(parts[0])
            continue
        gs = [p.geom for p in parts]
        nuv = min(len(g.uvs or []) for g in gs)
        pos, tri, nor, uvs, base = [], [], [], [[] for _ in range(nuv)], 0
        has_n = all(g.normals is not None for g in gs)
        for g in gs:
            P = np.asarray(g.positions, np.float32).reshape(-1, 3)
            pos.append(P)
            tri.append(np.asarray(g.triangles, np.int64).reshape(-1, 3) + base)
            if has_n:
                nor.append(np.asarray(g.normals, np.float32).reshape(len(P), -1)[:, :3])
            for k in range(nuv):
                uvs[k].append(np.asarray(g.uvs[k], np.float32).reshape(len(P), -1))
            base += len(P)
        g0 = gs[0]
        geom = pr.P3dGeom(mesh_index=g0.mesh_index, formats=list(g0.formats), positions=np.concatenate(pos),
                          triangles=np.concatenate(tri), normals=np.concatenate(nor) if has_n else None, normal_w=None,
                          uvs=[np.concatenate(u) for u in uvs], colors=None, tangents_raw=None)
        p0 = _copy(parts[0])
        p0.geom = geom
        out.append(p0)
    prop.parts[:] = out


def _sync_nodes(prop):
    """The model's LOD nodes: one per LOD that has parts (the builder reads them by name)."""
    import copy
    names = {p.node for p in prop.parts}
    nodes = list(prop.model.nodes)
    by_name = {n.name: n for n in nodes}
    keep = [n for n in nodes if not LOD_RE.search(n.name) or n.name in names]
    for name in sorted(names - {n.name for n in keep}):
        base = LOD_RE.sub("", name)
        src = by_name.get(base) or next((n for n in nodes if LOD_RE.sub("", n.name) == base), None)
        if src is not None:
            n = copy.copy(src)
            n.name = name
            keep.append(n)
    prop.model.nodes = keep


# WRCG draws some open meshes from both sides (house snow sheets and house details: 38-45 % of their faces turn away from
# the house). ACR's prop material (M_Simple) culls back faces, so whole parts of the Swedish houses were missing
# (owner 2026-11-10: "casas con partes o enteras todavía invisibles"). An open part (edges used by one face) whose
# faces turn both ways (each way at least TWO_SIDED_MIN of its area, seen from the prop's centre) gets every face a
# second time, reversed, with reversed normals.
TWO_SIDED_MIN = 0.15


# Power lines (owner 2026-11-11, Pietrosella: "los cables de la luz se ven muy gruesos"): WRCG's high-voltage cables
# (PYLON_04) are tubes 7-8 cm across, the small lines' (JP_ELECTRIC_LINES_*) 3-6 cm. A long thin piece of such a prop
# (WIRE_MIN_LEN_M along one axis, under WIRE_MAX_M across) is a wire: its cross-sections are shrunk around their own
# centres (slices of WIRE_SLICE_M along it, so the sag stays) to WIRE_TARGET_M across. The poles are untouched.
WIRE_RE = re.compile(r"PYLON|ELECTRIC_LINE|POWER_LINE|CABLE|HIGHVOLTAGE|SPLINESPAWNERLINES", re.I)
# wires: pieces longer than WIRE_MIN_LEN_M and not upright (a high-voltage pylon's lattice: beams 8.5-10 m, cross-arm
# chords 24 m, legs 74 m upright, 0.2-0.3 m thick: kept; its lines are 120 m long, 0.275 m thick; PYLON_04's 37 m)
WIRE_MIN_LEN_M, WIRE_MAX_M, WIRE_TARGET_M, WIRE_SLICE_M = 30.0, 0.35, 0.03, 0.25
WIRE_MAX_RISE = 0.7                            # |z| of the piece's direction


def _labels(T, n):
    """Connected piece of every vertex (union-find over the triangles)."""
    root = np.arange(n)

    def find(a):
        while root[a] != a:
            root[a] = root[root[a]]
            a = root[a]
        return a
    for a, b, c in T:
        ra = find(a)
        root[find(b)] = ra
        root[find(c)] = ra
    return np.array([find(i) for i in range(n)])


def thin_wires(prop):
    n = 0
    for part in prop.parts:
        g = part.geom
        if g is None or not len(g.triangles):
            continue
        P = np.asarray(g.positions, np.float32).reshape(-1, 3).copy()
        T = np.asarray(g.triangles, np.int64).reshape(-1, 3)
        W = np.unique(np.round(P, 3), axis=0, return_inverse=True)[1].reshape(-1)     # welded ids
        lab = _labels(W[T], int(W.max()) + 1)[W]
        changed = False
        for c in np.unique(lab):
            idx = np.nonzero(lab == c)[0]
            V = P[idx].astype(float)
            if len(V) < 6:
                continue
            # along the wire's own direction (owner 2026-11-11: Riudecanyes' and Brattby's high-voltage lines still
            # thick: a wire at an angle to the x / y axes looked as wide as its slant over a slice)
            m0 = V.mean(0)
            axis = np.linalg.svd(V - m0, full_matrices=False)[2][0]
            s = (V - m0) @ axis
            if s.max() - s.min() < WIRE_MIN_LEN_M or abs(float(axis[2])) > WIRE_MAX_RISE:
                continue
            b = np.floor((s - s.min()) / WIRE_SLICE_M).astype(np.int64)
            cnt = np.maximum(np.bincount(b), 1)
            cen = np.stack([np.bincount(b, V[:, k]) / cnt for k in range(3)], 1)[b]
            off = V - cen
            perp = off - np.outer(off @ axis, axis)
            r = float(np.linalg.norm(perp, axis=1).max())
            if 2 * r > WIRE_MAX_M or r <= 0:
                continue
            f = min(1.0, WIRE_TARGET_M / (2 * r))
            if f >= 0.95:
                continue
            P[idx] = (cen + (off - perp) + perp * f).astype(np.float32)
            changed = True
            n += 1
        if changed:
            import copy
            q = copy.copy(g)
            q.positions = P
            part.geom = q
    return n


BUILDING_RE = re.compile(r"/HOUSES/|BARN|HOUSE|CHURCH|FARM|SHED|GARAGE|HANGAR|BUILDING|CABIN", re.I)


def two_sided(prop, building=False):
    """building: every open part both ways (wall shells with windows: through a window the far wall's inner side
    showed the sky; Sävar's destroyed barn, a ruin in WRCG, looked like paper)."""
    import tools.wrcg.p3d_render as pr
    parts = [p for p in prop.parts if p.geom is not None and len(p.geom.triangles)]
    if not parts:
        return 0
    allp = np.concatenate([np.asarray(p.geom.positions, float).reshape(-1, 3) for p in parts if p.lod == 0] or
                          [np.asarray(parts[0].geom.positions, float).reshape(-1, 3)])
    c0 = allp.mean(0)
    n = 0
    for part in parts:
        g = part.geom
        P = np.asarray(g.positions, np.float32).reshape(-1, 3)
        T = np.asarray(g.triangles, np.int64).reshape(-1, 3)
        e = np.sort(np.concatenate([T[:, [0, 1]], T[:, [1, 2]], T[:, [2, 0]]]), axis=1)
        _, cnt = np.unique(e, axis=0, return_counts=True)
        if not (cnt == 1).any():
            continue                                        # closed: one side is enough
        fn = np.cross(P[T[:, 1]] - P[T[:, 0]], P[T[:, 2]] - P[T[:, 0]]).astype(float)
        a = np.linalg.norm(fn, axis=1)
        out = ((fn / np.maximum(a, 1e-12)[:, None]) * (P[T].mean(1) - c0)).sum(1)
        share_in = float(a[out < 0].sum() / max(a.sum(), 1e-12))
        if not building and not TWO_SIDED_MIN <= share_in <= 1.0 - TWO_SIDED_MIN:
            continue
        W = np.unique(np.round(P, 3), axis=0, return_inverse=True)[1].reshape(-1)[T]
        _, twin = np.unique(np.sort(W, axis=1), axis=0, return_counts=True)
        if (twin > 1).sum() * 2 >= TWO_SIDED_MIN * len(T):
            continue                                        # faces already doubled (cut-out cards from fix())
        part.geom = _doubled(g)
        n += 1
    return n


def _doubled(g):
    """The mesh with every face a second time, reversed, with reversed normals (seen from both sides)."""
    import tools.wrcg.p3d_render as pr
    P = np.asarray(g.positions, np.float32).reshape(-1, 3)
    T = np.asarray(g.triangles, np.int64).reshape(-1, 3)
    k = len(P)
    N = None if g.normals is None else np.asarray(g.normals, np.float32).reshape(k, -1)[:, :3]
    uvs = [np.asarray(u, np.float32).reshape(k, -1) for u in (g.uvs or [])]

    def twice(x):
        if x is None:
            return None
        x = np.asarray(x)
        return np.concatenate([x, x]) if len(x) == k else x

    return pr.P3dGeom(mesh_index=g.mesh_index, formats=list(g.formats), positions=np.concatenate([P, P]),
                      triangles=np.concatenate([T, T[:, ::-1] + k]),
                      normals=None if N is None else np.concatenate([N, -N]), normal_w=twice(g.normal_w),
                      uvs=[np.concatenate([u, u]) for u in uvs], colors=twice(g.colors),
                      tangents_raw=twice(g.tangents_raw))


def patch(log=print):
    """build_stage's process: every prop the builder reads goes through fix()."""
    import tools.wrcg.p3d_render as pr
    if getattr(pr.read_prop, "_wr_lods", False):
        return
    orig = pr.read_prop

    def read_prop(psi, *a, **k):
        prop = orig(psi, *a, **k)
        try:
            n = fix(prop)
            if n:
                log(f"    LODs in order of detail: {getattr(prop, 'name', psi)} ({n} object{'s' if n > 1 else ''})")
        except Exception as e:                                  # a model we cannot reorder stays as it is
            log(f"    LODs of {psi} kept ({e})")
        try:
            if WIRE_RE.search(str(psi)):
                n = thin_wires(prop)
                if n:
                    log(f"    wires thinner: {getattr(prop, 'name', psi)} ({n} wire pieces to {WIRE_TARGET_M * 100:.0f} cm)")
        except Exception as e:
            log(f"    wires of {psi} kept ({e})")
        try:
            n = fill_lods(prop)
            if n:
                log(f"    LODs filled: {getattr(prop, 'name', psi)} ({n} object{'s' if n > 1 else ''} drawn at every distance)")
        except Exception as e:
            log(f"    LOD fill of {psi} skipped ({e})")
        try:
            n = two_sided(prop, building=bool(BUILDING_RE.search(str(psi))))
            if n:
                log(f"    both faces: {getattr(prop, 'name', psi)} ({n} open part{'s' if n > 1 else ''} seen from both sides)")
        except Exception as e:
            log(f"    faces of {psi} kept ({e})")
        return prop

    read_prop._wr_lods = True
    for attr in ("_wr",):
        if getattr(orig, attr, False):
            setattr(read_prop, attr, True)
    pr.read_prop = read_prop
