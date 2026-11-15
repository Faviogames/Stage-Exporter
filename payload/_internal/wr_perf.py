"""Performance of our levels: draw and cull distances like ACR's own stages.

Owner 2026-11-10: "algunos tramos se notan con peor rendimiento al inicio del tramo ... el tema de la optimización me
parece sumamente importante". ACR's stages are World Partition levels (cells streamed in by distance, HLODs far away)
and their components carry draw distances: in Munster's cells half the static meshes have CachedMaxDrawDistance 20000
(200 m), the grass (CustomGrassRegistererComponent) fades out between 10000 and 15000 cm (some kinds 300 or 500 m),
without dynamic shadows and without distance-field lighting. Our levels are one persistent level, and the tool's build
of Riudecanyes reverse had:
  - 4,275 prop StaticMeshComponents (WrcgProp_*) without any draw distance, all casting shadows;
  - ~490,000 ground cover instances (WrcgVeg_gc_*: our species define cull_end_cm 12000-30000, but the builder's cull
    comes from WRCG's per-instance max_visible_m, -1 for ours) drawn at any distance; willow and broom (40,000) with
    shadows; distance-field lighting on for all of them.
Now:
  - ground cover: InstanceStart/EndCullDistance from our species (0.8 x end .. end), no shadows,
    bAffectDistanceFieldLighting false (as ACR's grass);
  - props: LDMaxDrawDistance and CachedMaxDrawDistance by the prop's size (DRAW_BY_SIZE), as ACR's cull distance
    volumes give its props; pieces of runs (rails, walls) at least LINEAR_MIN_CM; big things (houses, rock walls,
    gantries) and our skinned road pieces (WRSKIN_*: lines, gutters, walls) keep no limit. Riudecanyes reverse: 3,894
    of 4,275 props get one. Checked: UaTool writes and reads back the properties (level +39 KB).
"""
import copy
import re

import numpy as np

# largest LOD0 dimension (m) -> draw distance (cm); bigger props: none. ACR's small props: 200 m.
DRAW_BY_SIZE = ((0.6, 10000.0), (1.5, 20000.0), (4.0, 35000.0), (10.0, 70000.0), (25.0, 150000.0))
# pieces of long runs along the road (guard rails, walls, fences: 1,477 SMALLHIGHWAY_MID of 3 m on Riudecanyes) would
# appear piece by piece: at least this far
NO_LIMIT_RE = r"PYLON|HIGHVOLTAGE|SPLINESPAWNERLINES|ELECTRIC_LINE|POWER_LINE"
LINEAR_WORDS = ("HIGHWAY", "RAIL", "WALL", "FENCE", "BARRIER", "SIDEWALK", "KERB", "CURB", "GUARD", "_MIDDLE")
LINEAR_MIN_CM = 70000.0
PROP_PREFIX = "WrcgProp_"
_PSI = {}          # sanitised prop name (as in the actor name) -> psi
_SIZE = {}         # psi -> largest LOD0 dimension (m)


# --- ground cover ------------------------------------------------------------------------------------------------------

def veg_kwargs(species, k):
    """add_hism_actor keyword arguments for our ground cover species (cull from the species, no shadows; stones and
    rocks keep theirs) and far forest (no shadows: 100-200 k impostor trees from 150 m); others unchanged."""
    import wr_groundcover
    sp = wr_groundcover.SPECIES.get(species or "")
    if not sp or not str(species).startswith(("gc_", "far_")):
        return k
    k = dict(k)
    if not k.get("cull_cm") and sp.get("cull_end_cm"):
        k["cull_cm"] = float(sp["cull_end_cm"])
    if sp.get("kind") != "rock":
        k["cast_shadow"] = False
    return k


def veg_after(dst, n0, species):
    """bAffectDistanceFieldLighting false on the HISM components just added for a ground cover / far forest species."""
    if not str(species or "").startswith(("gc_", "far_")):
        return
    for i in range(n0 + 1, len(dst.exports) + 1):
        if "InstancedStaticMeshComponent" in dst.class_name(i):
            _set_bool(dst, dst.exp(i), "bAffectDistanceFieldLighting", False)


# --- props -------------------------------------------------------------------------------------------------------------

def note_props(insts):
    """Remember the psi of every collected prop instance, by the name its actor gets."""
    for p in insts:
        name = getattr(p, "psi_name", None)
        if name and p.psi:
            _PSI.setdefault(_safe(name), p.psi)
    return insts


def _safe(s):
    try:
        import tools.acrmod.props_visual as pv
        return pv._safe(s)
    except Exception:
        return re.sub(r"[^A-Za-z0-9_]", "_", s)


def _size(psi):
    if psi not in _SIZE:
        import tools.wrcg.p3d_render as pr
        try:
            pts = []
            for x in pr.read_prop(psi).parts:
                if x.lod != 0 or x.geom is None:
                    continue
                P = np.asarray(x.geom.positions, float).reshape(-1, 3)
                pts.append((np.c_[P, np.ones(len(P))] @ np.asarray(x.matrix, float).T)[:, :3])
            P = np.concatenate(pts)
            _SIZE[psi] = float((P.max(0) - P.min(0)).max())
        except Exception:
            _SIZE[psi] = None
    return _SIZE[psi]


def _draw_cm(size_m):
    if size_m is None:
        return None
    for lim, cm in DRAW_BY_SIZE:
        if size_m <= lim:
            return cm
    return None


def prop_draw_distances(dst, log=print):
    """LDMaxDrawDistance / CachedMaxDrawDistance on the props' StaticMeshComponents, by size; returns the count set."""
    level = next(i for i in range(1, len(dst.exports) + 1) if dst.class_name(i) == "Level")
    counts, unknown, done = {}, set(), None
    for i in range(1, len(dst.exports) + 1):
        e = dst.exp(i)
        name = e.get("ObjectName", "")
        if e.get("OuterIndex") != level or not name.startswith(PROP_PREFIX):
            continue
        stem = re.sub(r"_\d+$", "", name[len(PROP_PREFIX):])
        psi = _PSI.get(stem)
        if psi is None:
            unknown.add(stem)
            continue
        # pylons and power lines are seen from far (owner 2026-11-11: "quitar su optimización de dibujado, para que se
        # vean a cualquier lejanía")
        cm = None if re.search(NO_LIMIT_RE, str(psi), re.I) else _draw_cm(_size(psi))
        if cm is not None and any(w in stem.upper() for w in LINEAR_WORDS):
            cm = max(cm, LINEAR_MIN_CM)
        if cm is None:
            counts["no limit"] = counts.get("no limit", 0) + 1
            continue
        for c in dst.children(i):
            if dst.class_name(c) == "StaticMeshComponent":
                ex = dst.exp(c)
                _set_float(dst, ex, "LDMaxDrawDistance", cm)
                _set_float(dst, ex, "CachedMaxDrawDistance", cm)
                done = ex
        counts[f"{cm / 100:.0f} m"] = counts.get(f"{cm / 100:.0f} m", 0) + 1
    if done is not None:
        dst._add_export_names(done)
    n = sum(v for k, v in counts.items() if k != "no limit")
    log(f"draw distances: {n} props by size ({', '.join(f'{k} {v}' for k, v in sorted(counts.items()))})"
        + (f"; {len(unknown)} kinds without a known psi kept" if unknown else ""))
    return n


# --- lean level JSON ---------------------------------------------------------------------------------------------------
# UaTool reads the level JSON as one string, so a level's JSON must stay under ~1 G characters (Arganil's no longer
# converts back). Every property object carries six fields that only repeat their default value, and save() writes with
# indentation: Panzerplatte 570 M characters, 314 M without the default fields (7.5 M of them), 240 M compact. UaTool
# writes byte-identical .umap/.uexp from both (checked 2026-11-10), so the vegetation can be denser.
DEFAULTS = (("ArrayIndex", 0), ("PropertyGuid", None), ("IsZero", False), ("PropertyTagFlags", "None"),
            ("PropertyTypeName", None), ("PropertyTagExtensions", "NoExtension"))


def _strip(root):
    """Drops the default-valued fields of every property object; returns [(dict, removed items)] to put them back."""
    removed = []
    stack = [root]
    while stack:
        x = stack.pop()
        if isinstance(x, dict):
            t = x.get("$type")
            if isinstance(t, str) and "PropertyTypes" in t:
                gone = []
                for k, v in DEFAULTS:
                    if k in x and type(x[k]) is type(v) and x[k] == v:
                        gone.append((k, x.pop(k)))
                if gone:
                    removed.append((x, gone))
            stack.extend(v for v in x.values() if isinstance(v, (dict, list)))
        elif isinstance(x, list):
            stack.extend(v for v in x if isinstance(v, (dict, list)))
    return removed


def lean_save(orig, umap, path):
    """orig(umap, path) writing the level JSON without default fields and without indentation."""
    import json as _json
    removed = _strip(umap.j)
    dumps = _json.dumps

    def compact(obj, *a, **k):
        if obj is umap.j:
            k.pop("indent", None)
            k["separators"] = (",", ":")
        return dumps(obj, *a, **k)
    _json.dumps = compact
    try:
        out = orig(umap, path)
        try:
            import os
            n = os.path.getsize(path)
            print(f"    level JSON: {n / 1e6:.0f} M characters written lean ({len(removed)} property objects trimmed)"
                  + ("  WARNING: near UaTool's ~1 G limit" if n > 900e6 else ""))
        except OSError:
            pass
        return out
    finally:
        _json.dumps = dumps
        for x, gone in removed:
            for k, v in gone:
                x.setdefault(k, v)


# --- property helpers --------------------------------------------------------------------------------------------------

def _base(e):
    """A plain property of the export to copy the fields from (any non-struct one)."""
    for p in e.get("Data") or []:
        if isinstance(p, dict) and p.get("$type", "").endswith(("BoolPropertyData, UAssetAPI",
                                                                  "ObjectPropertyData, UAssetAPI",
                                                                  "EnumPropertyData, UAssetAPI")):
            return p
    return None


def _put(dst, e, name, typ, value):
    data = e.get("Data")
    if not isinstance(data, list):
        return
    for p in data:
        if isinstance(p, dict) and p.get("Name") == name:
            p["Value"] = value
            return
    b = _base(e)
    if b is None:
        return
    q = {k: copy.deepcopy(v) for k, v in b.items() if k in ("$type", "Name", "ArrayIndex", "PropertyGuid", "IsZero",
                                                           "PropertyTagFlags", "PropertyTypeName",
                                                           "PropertyTagExtensions")}
    q["$type"] = f"UAssetAPI.PropertyTypes.Objects.{typ}, UAssetAPI"
    q["Name"], q["ArrayIndex"], q["IsZero"], q["Value"] = name, 0, False, value
    data.append(q)
    dst.add_name(name)


def _set_float(dst, e, name, value):
    _put(dst, e, name, "FloatPropertyData", float(value))


def _set_bool(dst, e, name, value):
    _put(dst, e, name, "BoolPropertyData", bool(value))
