"""ACR spectators on WRCG's own spectator spots.

WRCG places its spectators as PLM nodes Public*/PublicMA_<n> under <tag>/<level>_<tag>_GRAPHS/.../Public/<group> (1,316 for
ES2_SPAIN SS4). Each 8 m cluster of them becomes one ACR BC_CrowdSystemSpawnerBakedActor, cloned from Hafren South's start
cell (the one the start marshal comes from, already in work/acr): the spawner's BakedSpawnData.Elements are rewritten with our
positions (snapped to our ground), each element copied from a stock one (character, clothes, animation bucket). The crowd
manager these spawners need is already in the level (cloned with the start marshal).
"""
import copy
import json
import math
import re
from collections import defaultdict
from pathlib import Path

import numpy as np

CLUSTER_M = 8.0          # one ACR spawner per 8 m grid cell
MIN_ROUTE_M = 5.0        # nobody closer than this to the route centreline
MAX_ROUTE_M = 120.0      # nor farther (outside the terrain detail)
SKIP_GROUPS = ("Sound",)  # WRCG's crowd sound emitters, not people
FLARE_MIN_GROUP = 3       # groups this big get a red flare in the front row...
FLARE_EVERY = 8           # ...and one more per 8 spectators


def wrcg_spectators(plm_path, tag):
    """[(group, world position (3,))] of the spectator nodes of stage <tag> (e.g. 'SS4'), WRCG world metres."""
    import tools.wrcg.plm as plm
    import tools.wrcg.plm_props as pp
    nodes = plm.Plm(plm_path).nodes()
    stack, parent = [], {}
    for n in nodes:
        while stack and stack[-1].depth >= n.depth:
            stack.pop()
        parent[n.index] = stack[-1] if stack else None
        stack.append(n)
    # GR_ACROPOLIS: SS3/GR_SS3_GRAPH; FR_FRANCECORSE: SS1/FR_SS1_Graph (no spectators found while case mattered)
    graphs = re.compile(rf"^{re.escape(tag)}/\w*_{re.escape(tag)}_GRAPHS?$", re.I)
    out = []
    for n in nodes:
        # GR_ACROPOLIS: Public_Man_/Public_Woman_<n>; PT2_PORTUGAL: PublicVA_Man_A_<n> / PublicVA_Woman_B_<n>
        if not re.match(r"(?i)public(va|ma)?(_man|_woman)?(_[a-z])?_\d+$", n.name):
            continue
        chain, q = [], n
        while q is not None:
            chain.append(q)
            q = parent[q.index]
        if not any(graphs.match(x.name) for x in chain) or chain[1].name in SKIP_GROUPS:
            continue
        m = np.eye(4)
        for q in chain:
            m = np.asarray(pp.node_matrix(q.pos, q.rot, q.scale)) @ m
        out.append((chain[1].name, m[:3, 3].copy()))
    return out


def _prop(e, name):
    return next(p for p in e["Data"] if p["Name"] == name)


def _field(struct_prop, name):
    return next(p for p in struct_prop["Value"] if p["Name"] == name)


def _set_xyz(vec_struct, x, y, z):
    v = vec_struct["Value"][0]["Value"]
    v["X"], v["Y"], v["Z"] = float(x), float(y), float(z)


def _set_quat_yaw(quat_struct, yaw_deg):
    q = quat_struct["Value"][0]["Value"]
    h = math.radians(yaw_deg) / 2
    q["X"], q["Y"], q["Z"], q["W"] = 0.0, 0.0, math.sin(h), math.cos(h)


def add_crowd(dst, cell_json, spots_ue, route_ue, ground, log=print, prefix="WrcgCrowd"):
    """Add one cloned spawner per cluster of spots (UE cm, (N,3)); returns the number of spectators placed."""
    cell = type(dst)(json.loads(Path(cell_json).read_text(encoding="utf-8")))
    spawners = [i for i in range(1, len(cell.exports) + 1)
                if cell.class_name(i) == "BC_CrowdSystemSpawnerBakedActor_C"]
    if not spawners:
        log("    crowd: no stock spawner in the source cell, skipped")
        return 0
    pool, add_tmpl = [], None
    for i in spawners:
        els = _field(_prop(cell.exp(i), "BakedSpawnData"), "Elements")["Value"]
        for el in els:
            el = copy.deepcopy(el)
            for p in el["Value"]:
                if p["Name"] == "AdditionalMeshes":
                    add_tmpl = add_tmpl or (copy.deepcopy(p["Value"][0]) if p["Value"] else None)
                    p["Value"] = []          # umbrellas, phones, hoods: a dry Mediterranean stage
            pool.append(el)
    flare = _flare_item(add_tmpl) if add_tmpl else None

    # keep spots off the road, snap them to our ground, face the nearest route point
    r2 = route_ue[:, :2]
    keep = []
    for p in spots_ue:
        d = np.hypot(*(r2 - p[:2]).T)
        i = int(d.argmin())
        if not (MIN_ROUTE_M * 100 <= d[i] <= MAX_ROUTE_M * 100):
            continue
        z = ground(float(p[0]), float(p[1]), float(p[2]))
        if z is None or not math.isfinite(z):
            continue
        # element rotations are relative to the spawner root (yaw 0 here) and the characters face their local +Y:
        # Hafren's spawners face the road within 9 deg that way; a spectator turned away from the stage by more than
        # MaxLookAtStageVariation (45 deg) never looks at the car
        yaw = math.degrees(math.atan2(r2[i, 1] - p[1], r2[i, 0] - p[0])) - 90.0
        keep.append((float(p[0]), float(p[1]), float(z), yaw, float(d[i])))

    cells = defaultdict(list)
    for s in keep:
        cells[(int(s[0] // (CLUSTER_M * 100)), int(s[1] // (CLUSTER_M * 100)))].append(s)

    level = next(i for i in range(1, len(dst.exports) + 1) if dst.class_name(i) == "Level")
    src = spawners[0]
    sounds = [i for i in range(1, len(cell.exports) + 1) if cell.class_name(i) == "BC_CrowdManagedAmbientSound_C"]
    n_people, n_flares_total = 0, [0]
    for k, (key, group) in enumerate(sorted(cells.items())):
        new = dst.clone(cell, src, level)[src]   # clone() maps every source export to its copy
        name = f"{prefix}_{k}"
        dst.add_name(name)
        dst.exp(new)["ObjectName"] = name
        dst.register_actor(level, new)
        # each stock spawner has its own id, shared with its crowd sound (CrowdSystemSpawnerPCG_<id> / CrowdSystemAudio_<id>)
        gid = f"{prefix}{k:04d}"
        _set_tags(dst, dst.exp(new), [f"CrowdSystemSpawnerPCG_{gid}"])
        cx, cy = np.mean([g[0] for g in group]), np.mean([g[1] for g in group])
        cz = min(g[2] for g in group) + 150.0
        root = next(c for c in dst.children(new) if dst.class_name(c) == "SceneComponent")
        _set_xyz(_prop(dst.exp(root), "RelativeLocation"), cx, cy, cz)
        _set_rot0(dst.exp(root))
        els = []
        # red flares: the front row of each group holds ACR's crowd smoke stick ("Smoke" add mesh, smoke animations)
        n_flares = 0 if len(group) < FLARE_MIN_GROUP else 1 + len(group) // FLARE_EVERY
        front = set(sorted(range(len(group)), key=lambda q: group[q][4])[:n_flares])
        for j, (x, y, z, yaw, _) in enumerate(group):
            el = copy.deepcopy(pool[(k * 7 + j) % len(pool)])
            el["Name"] = str(j)
            tr = _field(el, "Transform")
            _set_xyz(_field(tr, "Translation"), x - cx, y - cy, z - cz)
            _set_quat_yaw(_field(tr, "Rotation"), yaw)
            if flare is not None and j in front:
                _field(el, "AdditionalMeshes")["Value"] = [copy.deepcopy(flare)]
                n_flares_total[0] += 1
            els.append(el)
        _field(_prop(dst.exp(new), "BakedSpawnData"), "Elements")["Value"] = els
        dst._add_export_names(dst.exp(new))   # the copied elements' FNames (characters, customisations)
        rt = next((c for c in dst.children(new) if dst.class_name(c) == "CrowdSystemRuntime"), None)
        if rt is not None:
            radius = max(math.hypot(g[0] - cx, g[1] - cy) for g in group) + 100.0
            for p in dst.exp(rt).get("Data", []):
                if p["Name"] == "BoundsRadius":
                    p["Value"] = float(radius)
        if sounds:
            _add_sound(dst, cell, sounds[k % len(sounds)], level, f"{prefix}Sound_{k}", gid, group, root)
        n_people += len(group)
    log(f"    crowd: {n_people} spectators of {len(spots_ue)} WRCG spots in {len(cells)} spawners, "
        f"{n_flares_total[0]} with red flares ({len(spots_ue) - len(keep)} dropped: on the road, too far or off the ground)")
    return n_people


# People at the start and finish tables. WRCG's start and stop controls have chairs (START_ZONE/CHAISE_1) at their tables
# and nobody on them in ACR, only the start marshal (owner 2026-11-10: "no hay gente sentada en las sillas de los
# marshalls y sólo hay el que da la salida"). ACR seats its crowd with the "Chair" add mesh (DA_CrowdStandardAddMeshGroup:
# DA_CrowdChairAddMesh = SM_SeatA, spawn share 0) and DA_CrowdAnimations' "Chair" set (Sitting_Chair idles); each WRCG
# chair becomes one such element facing the way the chair faces, and the WRCG chair itself is left out (wr_fixes) so the
# two seats do not overlap.
def add_seated(dst, cell_json, seats_ue, ground, log=print, prefix="WrcgSeated", pose=None):
    """seats_ue: [(x, y, z, facing yaw in degrees)] in UE cm; one spawner per CLUSTER_M cell. Returns people placed.
    pose "Sitting" / "SittingRock": no chair, the person sits on the ground / a rock as the stock spectators do (see _set_pose)."""
    cell = type(dst)(json.loads(Path(cell_json).read_text(encoding="utf-8")))
    spawners = [i for i in range(1, len(cell.exports) + 1)
                if cell.class_name(i) == "BC_CrowdSystemSpawnerBakedActor_C"]
    if not spawners or not seats_ue:
        return 0
    pool, add_tmpl = [], None
    for i in spawners:
        for el in _field(_prop(cell.exp(i), "BakedSpawnData"), "Elements")["Value"]:
            el = copy.deepcopy(el)
            for p in el["Value"]:
                if p["Name"] == "AdditionalMeshes":
                    add_tmpl = add_tmpl or (copy.deepcopy(p["Value"][0]) if p["Value"] else None)
                    p["Value"] = []
            pool.append(el)
    if add_tmpl is None and pose is None:
        log("    seated people: no add-mesh entry to copy, skipped")
        return 0
    chair = _flare_item(add_tmpl, "Chair") if pose is None else None
    seats = []
    for x, y, z, yaw in seats_ue:
        g = ground(float(x), float(y), float(z))
        seats.append((float(x), float(y), float(g if g is not None and math.isfinite(g) else z), float(yaw)))
    cells = defaultdict(list)
    for s in seats:
        cells[(int(s[0] // (CLUSTER_M * 100)), int(s[1] // (CLUSTER_M * 100)))].append(s)
    level = next(i for i in range(1, len(dst.exports) + 1) if dst.class_name(i) == "Level")
    src = spawners[0]
    n = 0
    for k, (key, group) in enumerate(sorted(cells.items())):
        new = dst.clone(cell, src, level)[src]
        name = f"{prefix}_{k}"
        dst.add_name(name)
        dst.exp(new)["ObjectName"] = name
        dst.register_actor(level, new)
        _set_tags(dst, dst.exp(new), [f"CrowdSystemSpawnerPCG_{prefix}{k:04d}"])
        cx, cy = np.mean([g[0] for g in group]), np.mean([g[1] for g in group])
        cz = min(g[2] for g in group) + 150.0
        root = next(c for c in dst.children(new) if dst.class_name(c) == "SceneComponent")
        _set_xyz(_prop(dst.exp(root), "RelativeLocation"), cx, cy, cz)
        _set_rot0(dst.exp(root))
        els = []
        for j, (x, y, z, yaw) in enumerate(group):
            el = copy.deepcopy(pool[(k * 5 + j * 3) % len(pool)])
            el["Name"] = str(j)
            tr = _field(el, "Transform")
            _set_xyz(_field(tr, "Translation"), x - cx, y - cy, z - cz)
            _set_quat_yaw(_field(tr, "Rotation"), yaw - 90.0)       # the characters face their local +Y
            if pose is None:
                _field(el, "AdditionalMeshes")["Value"] = [copy.deepcopy(chair)]
            else:
                _field(el, "AdditionalMeshes")["Value"] = []
                _set_pose(dst, el, pose, _slope_deg(ground, x, y, z))
            els.append(el)
        _field(_prop(dst.exp(new), "BakedSpawnData"), "Elements")["Value"] = els
        dst._add_export_names(dst.exp(new))
        rt = next((c for c in dst.children(new) if dst.class_name(c) == "CrowdSystemRuntime"), None)
        if rt is not None:
            radius = max(math.hypot(g[0] - cx, g[1] - cy) for g in group) + 100.0
            for p in dst.exp(rt).get("Data", []):
                if p["Name"] == "BoundsRadius":
                    p["Value"] = float(radius)
        n += len(group)
    log(f"    seated people: {n} " + (f"{pose} on the ground" if pose else "at the start and finish tables (WRCG's chairs, ACR's crowd seat)") + f", {len(cells)} spawners")
    return n


def _slope_deg(ground, x, y, z, d=100.0):
    """Ground slope (degrees) at a point, from the heights 1 m away."""
    h = [ground(x + dx, y + dy, z) for dx, dy in ((d, 0.0), (-d, 0.0), (0.0, d), (0.0, -d))]
    if any(v is None or not math.isfinite(v) for v in h):
        return 0.0
    return math.degrees(math.atan(math.hypot(h[0] - h[1], h[2] - h[3]) / (2.0 * d)))


def _set_pose(dst, el, pose, slope):
    """The attribute that makes ACR sit a spectator (stock cell DGC4CM72...: SittingRock people have it in their AttributesMap with
    value None, and the ground slope in SlopeDegrees; DA_CrowdSittingReqs asks for "Sitting" + the classified slope)."""
    pairs = _field(_field(el, "Attributes"), "AttributesMap")["Value"]
    pair = copy.deepcopy(pairs[0])
    pair[0]["Value"], pair[1]["Value"] = pose, "None"
    dst.add_name(pose)
    pairs.append(pair)
    sd = next(f for f in el["Value"] if f["Name"] == "SlopeDegrees")
    sd["InnerType"], sd["IsZero"] = "FloatProperty", False
    # DA_CrowdSittingReqs = Sitting and NOT SlopeClassified: a steep slope (the Greece hill is ~40 deg) would classify and drop the
    # flat sitting set, leaving the person with no animation (owner 2026-11-18: not seen); stock SittingRock people are 0.2-6.6 deg.
    sd["Value"] = {"$type": "UAssetAPI.PropertyTypes.Objects.FloatPropertyData, UAssetAPI", "Name": "0", "ArrayIndex": 0,
                   "PropertyGuid": None, "IsZero": False, "PropertyTagFlags": "None", "PropertyTypeName": None,
                   "PropertyTagExtensions": "NoExtension", "Value": float(min(slope, 6.0))}


def _flare_item(tmpl, rep="Smoke"):
    """An AdditionalMeshes entry for the crowd smoke stick: DA_CrowdStandardAddMeshGroup's "Smoke" (DA_SmokeMesh, spawn
    share 0 so ACR never picks it by itself), animated by DA_CrowdAnimations' "Smoke" set."""
    item = copy.deepcopy(tmpl)
    for p in item["Value"]:
        if p["Name"] == "RepresentationId":
            p["Value"] = rep
        elif p["Name"] == "CustomizationsIds":
            p["Value"] = []
    return item


def _set_tags(dst, e, tags):
    p = _prop(e, "Tags")
    tmpl = p["Value"][0]
    vals = []
    for i, t in enumerate(tags):
        v = copy.deepcopy(tmpl)
        v["Name"], v["Value"] = str(i), t
        dst.add_name(t)
        vals.append(v)
    p["Value"] = vals


def _add_sound(dst, cell, src, level, name, gid, group, spawner_root):
    """Hafren's BC_CrowdManagedAmbientSound_C for one spawner: box round the group, group size, the spawner's id.
    Its audio component is attached to its spawner's root there, so it is attached to ours."""
    sub = set(cell.subtree(src))
    preset = {}
    for c in sub:
        data = cell.exp(c).get("Data")
        ap = next((p for p in data if p.get("Name") == "AttachParent"), None) if isinstance(data, list) else None
        if ap and ap["Value"] and ap["Value"] not in sub:
            preset[ap["Value"]] = spawner_root
    new = dst.clone(cell, src, level, preset=preset)[src]
    dst.add_name(name)
    dst.exp(new)["ObjectName"] = name
    dst.register_actor(level, new)
    e = dst.exp(new)
    _set_tags(dst, e, [f"CrowdSystemAudio_{gid}", "CrowdSystemAudio"])
    xs, ys, zs = [g[0] for g in group], [g[1] for g in group], [g[2] for g in group]
    box = _prop(e, "Box")["Value"][0]["Value"]        # FBox: {"Min": FVector, "Max": FVector, "IsValid": 1}
    box["Min"].update(X=min(xs) - 100.0, Y=min(ys) - 100.0, Z=min(zs) - 10.0)
    box["Max"].update(X=max(xs) + 100.0, Y=max(ys) + 100.0, Z=max(zs) + 10.0)
    for p in e["Data"]:
        if p["Name"] == "GroupSize":
            p["Value"] = len(group)


def _set_rot0(root_exp):
    for p in root_exp.get("Data", []):
        if p["Name"] == "RelativeRotation":
            r = p["Value"][0]["Value"]
            r["Pitch"], r["Yaw"], r["Roll"] = 0.0, 0.0, 0.0
