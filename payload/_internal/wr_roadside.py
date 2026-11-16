"""Stage options: acr_wire_fence replaces WRCG tape with native ACR wire fence.
wrcg_tape_post_physics keeps WRCG tape and makes its original posts physical.
acr_red_tape is an optional legacy replacement.
brake_boards adds native signs 100 m and 50 m before tight turns.
corner_posts clones the physical ACR red corner markers (universal by default).
brake_boards is universal (on unless its config says false); acr_wire_fence is Kenya only (off unless its config says true).
"""
import base64
import copy
import json
import math
import os
import struct
import tempfile
from pathlib import Path

import numpy as np

import wr_finish as wf
import wr_groundcover as gc


SIGN_PACKAGE = "/Game/Props/RallyProps/Signs/"
CORNER_POST_CELL = "17DBY54HBNI92Q50PHMQDI639"
CORNER_POST_LEVEL = Path("acr/Content/Levels/LivignoIceDrivingSchool/_Generated_")
FENCE_CELL = "1XXMH9FJVC7ZDS8TC9W2RQY3Z"
FENCE_LEVEL = Path("acr/Content/Levels/AlsaceS2Munster/_Generated_")
POLE_MESH = "SM_OldTreeBranchWgquchfs_Rotated"


DEFAULT_OFF = ("acr_wire_fence", "acr_red_tape")
_RED_TAPE = {}


def on(cfg, key):
    return bool((cfg or {}).get(key, key not in DEFAULT_OFF))


def replace_tape(cfg):
    return not on(cfg, "wrcg_tape_post_physics") and (on(cfg, "acr_red_tape") or on(cfg, "acr_wire_fence"))


def _road_test(stage_dir, margin_cells=2):
    # Use the actual drivable meshes, including the run-in, run-off and junctions.
    step = 0.5
    with np.load(stage_dir / "collision_all_prm.npz") as data:
        points = gc._tri_points(data["positions"], data["triangles"], step / 2)
    occupied = {tuple(p) for p in np.unique(np.floor(points[:, :2] / step).astype(int), axis=0)}

    offsets = range(-margin_cells, margin_cells + 1)

    def clear(xy):
        for x, y in np.floor(np.atleast_2d(xy)[:, :2] / step).astype(int):
            if any((x + i, y + j) in occupied for i in offsets for j in offsets):
                return False
        return True

    return clear


def _clear_span(a, b, clear):
    # Test every 0.5 m road-raster cell crossed by the segment, including
    # cells only grazed near a grid corner.
    cuts = [0.0, 1.0]
    for start, end in zip(a[:2], b[:2]):
        if start == end:
            continue
        lo, hi = sorted((start, end))
        edges = np.arange(math.floor(lo * 2) + 1, math.ceil(hi * 2)) * 0.5
        cuts.extend((edges - start) / (end - start))
    cuts = np.sort(cuts)
    t = np.r_[cuts, 0.5 * (cuts[:-1] + cuts[1:])]
    return clear(a + t[:, None] * (b - a))


def _tape_plan(items, clear):
    poles, spans, seen = {}, [], set()
    for item in items:
        if item["template"] != "TapeCloth":
            continue
        a = np.asarray(item["pos"], float)
        b = a + float(item["size"][0]) * np.asarray(item["dir"], float)
        ka, kb = (tuple(np.rint(v[:2] * 5).astype(int)) for v in (a, b))
        pair = tuple(sorted((ka, kb)))
        if ka == kb or pair in seen:
            continue
        A, B = poles.get(ka, a), poles.get(kb, b)
        if not _clear_span(A, B, clear):
            continue
        poles.setdefault(ka, a)
        poles.setdefault(kb, b)
        spans.append((ka, kb))
        seen.add(pair)
    return poles, spans


def _route_samples(route):
    along = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(route[:, :2], axis=0), axis=1))]
    return np.column_stack([np.interp(np.arange(int(along[-1]) + 1), along, v) for v in route.T]), along


def _turn_angles(xy, samples):
    before = xy[samples, :2] - xy[samples - 16, :2]
    after = xy[samples + 16, :2] - xy[samples, :2]
    return np.arctan2(before[:, 0] * after[:, 1] - before[:, 1] * after[:, 0],
                      np.sum(before * after, axis=1))


BOARD_MIN_DEG = 60.0         # owner 2026-11-15: 100 / 50 boards showed before bends that were not tight (was 40)
_FENCES = {}


def _fence_segments(cfg):
    """Nx4 (x1, y1, x2, y2) WRCG metres of the stage's nets and tapes: a board must stand on the road side of them."""
    slug = (cfg or {}).get("slug")
    if slug not in _FENCES:
        segs = []
        try:
            from tools.acrmod import cloth_visual as cv
            items, _ = getattr(cv.collect_cloth, "original", cv.collect_cloth)(cfg["wrcg_level"], near_m=150.0)
            for it in items:
                a = np.asarray(it["pos"], float)[:2]
                b = a + float(it["size"][0]) * np.asarray(it["dir"], float)[:2]
                segs.append((*a, *b))
        except Exception as e:                 # without them the boards are placed as before
            print(f"    brake boards: net positions not read ({type(e).__name__}: {e})")
        _FENCES[slug] = np.asarray(segs, float).reshape(-1, 4)
    return _FENCES[slug]


def _behind_fence(a, b, segs, margin=0.6):
    """True if the segment road centre a -> board b crosses a fence segment or ends within `margin` m of one."""
    if not len(segs):
        return False
    near = segs[(np.minimum(segs[:, 0], segs[:, 2]) < max(a[0], b[0]) + 3) & (np.maximum(segs[:, 0], segs[:, 2]) > min(a[0], b[0]) - 3)
                & (np.minimum(segs[:, 1], segs[:, 3]) < max(a[1], b[1]) + 3) & (np.maximum(segs[:, 1], segs[:, 3]) > min(a[1], b[1]) - 3)]
    d = b - a
    for x1, y1, x2, y2 in near:
        e = np.array([x2 - x1, y2 - y1])
        den = d[0] * e[1] - d[1] * e[0]
        if abs(den) > 1e-9:
            t = ((x1 - a[0]) * e[1] - (y1 - a[1]) * e[0]) / den
            u = ((x1 - a[0]) * d[1] - (y1 - a[1]) * d[0]) / den
            if 0 <= t <= 1 and 0 <= u <= 1:
                return True
        ee = float(e @ e)
        w = np.clip(((b[0] - x1) * e[0] + (b[1] - y1) * e[1]) / ee, 0, 1) if ee else 0.0
        if np.hypot(b[0] - (x1 + w * e[0]), b[1] - (y1 + w * e[1])) < margin:
            return True
    return False


def _board_plan(route, clear, cfg=None):
    route = np.asarray(route, float)
    min_deg = float((cfg or {}).get("brake_board_min_deg", BOARD_MIN_DEG))
    segs = _fence_segments(cfg) if cfg else np.zeros((0, 4))
    if len(route) < 142:
        return []
    samples_xyz, along = _route_samples(route)
    xy = samples_xyz[:, :2]
    samples = np.arange(115, len(xy) - 25)
    turn = np.abs(_turn_angles(xy, samples))
    corners = []
    for i in np.argsort(turn)[::-1]:
        s = int(samples[i])
        if turn[i] < math.radians(min_deg):
            break
        if all(abs(s - k) >= 140 for k in corners):
            corners.append(s)
    result = []
    for corner in sorted(corners):
        for distance in (100, 50):
            s = corner - distance
            head, side = wf._heading(xy, s)
            for offset in (3.5, 4.0, 4.5, 5.0, 6.0, 7.0, 8.0, 9.0):
                locations = [xy[s] + sign * side * offset for sign in (1, -1)]
                point = next((p for p in locations if clear(p) and not _behind_fence(xy[s], p, segs)), None)
                if point is not None:
                    index = np.searchsorted(along, s, side="right") - 1
                    result.append((distance, s, np.r_[point, route[index, 2]], np.r_[point + head, route[index, 2]]))
                    break
    return result


def _corner_post_plan(route, clear, cfg=None):
    """ACR's red posts at bends >= corner_post_min_deg (45), at least corner_post_gap_m apart (500); with
    corner_post_fill_m also on the straights, one about every that many metres, alternating sides (owner 2026-11-15:
    they showed too little); corner_post_skip_m [[from, to]]: none in those route metres."""
    cfg = cfg or {}
    skip = cfg.get("corner_post_skip_m") or []
    min_deg, gap = float(cfg.get("corner_post_min_deg", 45.0)), float(cfg.get("corner_post_gap_m", 500.0))
    fill = float(cfg.get("corner_post_fill_m") or 0.0)
    route = np.asarray(route, float)
    if len(route) < 3:
        return []
    xyz, _ = _route_samples(route)
    xy = xyz[:, :2]
    samples = np.arange(120, len(xyz) - 120)
    angles = _turn_angles(xy, samples)
    result = []

    def place(s, inward):
        head, side = wf._heading(xy, s)
        for distance in np.arange(2.5, 7.01, 0.25):
            point = xy[s] + distance * inward(side)
            # Cover the whole 20 cm base in addition to the road-test margin.
            footprint = point + [[-0.15, -0.15], [-0.15, 0.15], [0.15, -0.15], [0.15, 0.15], [0, 0]]
            if clear(footprint) and all(np.linalg.norm(point - p[:2]) >= 16.0 for _, p, _ in result):
                result.append((s, np.r_[point, xyz[s, 2]], np.r_[point + head, xyz[s, 2]]))
                return True
        return False

    for i in np.argsort(-np.abs(angles), kind="stable"):
        if abs(angles[i]) < math.radians(min_deg):
            break
        s = int(samples[i])
        if any(abs(s - at) < gap for at, _, _ in result) or any(a <= s <= b for a, b in skip):
            continue
        sign = math.copysign(1.0, angles[i])
        place(s, lambda side, sign=sign: sign * side)
    if fill:
        flip = 1.0
        for s in range(int(samples[0]), int(samples[-1]), 10):
            if any(abs(s - at) < fill for at, _, _ in result) or any(a <= s <= b for a, b in skip):
                continue
            if abs(angles[s - int(samples[0])]) > math.radians(min_deg):
                continue                                    # a bend: left to the bend rule
            if place(s, lambda side, f=flip: f * side):
                flip = -flip
    return sorted(result, key=lambda row: row[0])


def _prop(asset, i, name):
    return wf._prop(asset.exp(i), name)


def _value(asset, i, name):
    p = _prop(asset, i, name)
    return p["Value"] if p is not None else 0


def _level(asset):
    return next(i for i in range(1, len(asset.exports) + 1) if asset.class_name(i) == "Level")


def _clone(dst, src, actor, level, name, preset):
    start = len(dst.exports) + 1
    clone = dst.clone(src, actor, level, preset=preset)[actor]
    dst.exp(clone)["ObjectName"] = name
    dst.add_name(name)
    dst.register_actor(level, clone)
    for i in range(start, len(dst.exports) + 1):
        dst._add_export_names(dst.exp(i))
    return clone


def _fence_template(src):
    for i in range(1, len(src.exports) + 1):
        if src.class_name(i) != "BC_LargeTapeActorBarbedWireFence_C":
            continue
        c = next(j for j in range(1, len(src.exports) + 1)
                 if src.exp(j)["OuterIndex"] == i and src.class_name(j) == "TapeComponent")
        a = _value(src, c, "AttachParent")
        if a and src.import_key(_value(src, a, "StaticMesh"))[1][0] == POLE_MESH:
            return i, c, a, src.exp(a)["OuterIndex"], _value(src, c, "AttachEndToActor")
    raise ValueError("ACR's wire fence with branch posts was not found")


def _cell_source(root, cache, level, cell):
    cached = root / "work/acr" / cache / level / f"{cell}.json"
    if not cached.is_file():
        from tools.acrmod import common

        cached.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="wr_fence_") as tmp:
            common.retoc("to-legacy", os.environ["WRCG2ACR_ACR_PAKS"], tmp, "-f", cell,
                         "--version", "UE5_6", "--no-shaders")
            common.asset_json(Path(tmp) / level / f"{cell}.umap", cached)
    return json.loads(cached.read_text(encoding="utf-8-sig"))


def _fence_source(root):
    return _cell_source(root, "wr_alsace", FENCE_LEVEL, FENCE_CELL)


def _add_fence(dst, root, poles, spans, to_ue, ground):
    if not spans:
        return
    source = type(dst)(_fence_source(root))
    tape, tape_comp, pole_comp, pole, end_pole = _fence_template(source)
    level, source_level = _level(dst), _level(source)
    root_parent = _value(source, pole_comp, "AttachParent")
    raw = base64.b64decode(source.exp(tape)["Data"])
    tag_count = struct.unpack_from("<I", raw, 14)[0]
    suffix = raw[18 + tag_count * 8:]
    if (raw[:6] != bytes.fromhex("00 02 3e 02 02 03")
            or struct.unpack_from("<ii", raw, 6) != (tape_comp, tape_comp)
            or len(suffix) != 77 or not suffix[12:].startswith(b"BC_LargeTapeActorBarbedWireFence")):
        raise ValueError("Unexpected ACR wire fence layout")
    loc = {}
    for n, (key, pos) in enumerate(poles.items()):
        x, y, z = map(float, to_ue([pos])[0])
        z = float(ground(x, y, z - 90.0))
        actor = _clone(dst, source, pole, level, f"WrcgAcrFencePost_{n}", {source_level: level, root_parent: 0})
        comp = _value(dst, actor, "RootComponent")
        dst.exp(comp)["Data"] = [p for p in dst.exp(comp)["Data"] if p.get("Name") not in {"AttachParent", "RelativeRotation"}]
        wf._vec(dst.exp(comp), "RelativeLocation").update(X=x, Y=y, Z=z)
        loc[key] = actor, comp, np.array([x, y, z])
    for n, (a, b) in enumerate(spans):
        actor_a, comp_a, p = loc[a]
        actor_b, _, q = loc[b]
        export = copy.deepcopy(source.exp(tape))
        name = f"WrcgAcrFence_{n}"
        dst.add_name(name)
        export["ObjectName"], export["OuterIndex"] = name, level
        for field in ("ClassIndex", "SuperIndex", "TemplateIndex"):
            export[field] = wf._remap_ref(export[field], {}, source, dst)
        dst.exports.append(export)
        actor = len(dst.exports)
        mapping = {source_level: level, tape: actor, pole_comp: comp_a, pole: actor_a, end_pole: actor_b}
        c = dst.clone(source, tape_comp, actor, preset=mapping)[tape_comp]
        mapping[tape_comp] = c
        for field in ("SerializationBeforeSerializationDependencies", "CreateBeforeSerializationDependencies",
                      "SerializationBeforeCreateDependencies", "CreateBeforeCreateDependencies"):
            export[field] = [wf._remap_ref(r, mapping, source, dst) for r in export.get(field) or []]
        dst._add_export_names(dst.exp(c))
        dst.register_actor(level, actor)
        if _value(dst, c, "AttachParent") != comp_a or _value(dst, c, "AttachEndToActor") != actor_b:
            raise ValueError("ACR fence endpoints were not remapped")
        # Two export refs, no stock PCG tags, then the original footer with a fresh GUID.
        data = raw[:6] + struct.pack("<iiI", c, c, 0) + suffix[:-32] + os.urandom(16) + suffix[-16:]
        dst.exp(actor)["Data"] = base64.b64encode(data).decode("ascii")
        _prop(dst, c, "TapeLength")["Value"] = float(np.linalg.norm(q - p)) * 1.025


def _merge_tape(poles, spans, clear):
    neighbors = {k: set() for k in poles}
    for a, b in spans:
        neighbors[a].add(b)
        neighbors[b].add(a)
    for k, adjacent in neighbors.items():
        if len(adjacent) != 2:
            continue
        a, b = sorted(adjacent)
        A, B, P = poles[a], poles[b], poles[k]
        line = B[:2] - A[:2]
        length = float(np.linalg.norm(line))
        if not 0.5 < length <= 6.5 or b in neighbors[a]:
            continue
        t = float(np.dot(P[:2] - A[:2], line) / length ** 2)
        if not 0 < t < 1 or np.linalg.norm((P - (A + t * (B - A)))[:2]) > 0.45:
            continue
        if not _clear_span(A, B, clear):
            continue
        neighbors[a].remove(k)
        neighbors[b].remove(k)
        neighbors[a].add(b)
        neighbors[b].add(a)
        adjacent.clear()
    used = {k: p for k, p in poles.items() if neighbors[k]}
    return used, [(a, b) for a in used for b in sorted(neighbors[a]) if a < b]


def _panel_endpoints(item):
    start = np.asarray(item["pos"], float)
    return start, start + float(item["size"][0]) * np.asarray(item["dir"], float)


def _panel_key(item):
    return tuple(np.rint(np.r_[_panel_endpoints(item)] * 1000).astype(int).ravel())


def _red_panel(item):
    name = str(item.get("material", "")).replace(chr(92), "/").rsplit("/", 1)[-1]
    return item["template"] == "TapeCloth" and name.upper() == "TAPE_RED.PMA"


def _red_tape_plan(items, route, clear):
    xy = np.asarray(route, float)[:, :2]
    fixed, replaced = {}, set()
    panels = []
    for item in items:
        if not _red_panel(item):
            continue
        start, end = _panel_endpoints(item)
        positions = []
        for pos in (start, end):
            key = tuple(np.rint(pos[:2] * 5).astype(int))
            if key not in fixed:
                center = xy[np.argmin(np.sum((xy - pos[:2]) ** 2, axis=1))]
                off = pos[:2] - center
                length = float(np.linalg.norm(off))
                direction = np.r_[off / max(length, 0.01), 0.0]
                fixed[key] = next((pos + d * direction for d in np.arange(0, 3.1, 0.5)
                                   if clear(pos + d * direction)), None)
            positions.append(fixed[key])
        a, b = positions
        if a is None or b is None or np.array_equal(np.rint(a[:2] * 5), np.rint(b[:2] * 5)):
            continue
        if _clear_span(a, b, clear):
            panels.append(dict(item, pos=a, dir=b - a, size=(1.0, item["size"][1])))
            replaced.add(_panel_key(item))
    poles, spans = _merge_tape(*_tape_plan(panels, clear), clear)
    return poles, spans, replaced


def _is_replaced(item, panels):
    return _red_panel(item) and _panel_key(item) in panels


def _red_layout(root, cfg, route=None, clear=None):
    from tools.acrmod import build_stage as bs, cloth_visual as cv

    slug = cfg["slug"]
    key = root, slug
    if key not in _RED_TAPE:
        collect = getattr(cv.collect_cloth, "original", cv.collect_cloth)
        items, _ = collect(cfg["wrcg_level"], near_m=150.0)
        if any(_red_panel(item) for item in items):
            if route is None:
                route = bs.route_wrcg(bs.load_cfg(slug))
            if clear is None:
                clear = _road_test(root / "work" / "wrcg" / slug)
            poles, spans, panels = _red_tape_plan(items, route, clear)
        else:
            poles, spans, panels = {}, [], set()
        anchors = ([], [])
        for item in items:
            anchors[int(_is_replaced(item, panels))].extend(_panel_endpoints(item))
        kept, removed = (np.asarray(p, float).reshape(-1, 3)[:, :2] for p in anchors)
        _RED_TAPE[key] = poles, spans, panels, kept, removed
    return _RED_TAPE[key]


def replaces_stick(root, cfg, prop):
    try:                                    # first: wrcg_tape_post_physics (on by default) returns below
        import wr_acrnets
        if wr_acrnets.options(cfg) and wr_acrnets.replaces_stick(cfg, prop):
            return True
    except Exception as e:
        print(f"    ACR nets: sticks kept ({type(e).__name__}: {e})")
    if on(cfg, "wrcg_tape_post_physics"):
        return False
    if cfg.get("tape_posts"):
        return True
    if not on(cfg, "acr_red_tape"):
        return on(cfg, "acr_wire_fence")
    _, _, _, kept, removed = _red_layout(root, cfg)
    point = np.asarray(prop.world, float)[:2, 3]
    return (np.any(np.sum((removed - point) ** 2, axis=1) <= 1.0)
            and not np.any(np.sum((kept - point) ** 2, axis=1) <= 1.0))


def _red_tape_template(source):
    for i in range(1, len(source.exports) + 1):
        if source.class_name(i) != "BC_NarrowTapeActor_C":
            continue
        component = _value(source, i, "RootComponent")
        post = _value(source, component, "AttachParent") if component else 0
        mesh = _value(source, post, "StaticMesh") if post else 0
        # The Munster ribbon on plain wood inherits M_NarrowTapes_Inst (the red
        # material of BC_NarrowTapeActor). The other posts use different dressing.
        if (mesh < 0 and source.import_key(mesh)[1][0] == "SM_WoodenNarrowBeamShort"
                and not _value(source, component, "OverrideMaterials")):
            return i, component, post
    raise ValueError("Munster's red ribbon with plain wooden posts was not found")


def _add_red_tape(dst, root, poles, spans, to_ue, ground):
    source = type(dst)(_fence_source(root))
    tape, c0, post_comp = _red_tape_template(source)
    post = source.exp(post_comp)["OuterIndex"]
    end = _value(source, c0, "AttachEndToActor")
    level, src_level = _level(dst), _level(source)
    parent = _value(source, post_comp, "AttachParent")
    place = {}
    for i, (key, point) in enumerate(poles.items()):
        x, y, z = map(float, to_ue([point])[0])
        z = float(ground(x, y, z - 100.0))
        mapping = {src_level: level}
        if parent:
            mapping[parent] = 0
        a = _clone(dst, source, post, level, f"WrcgAcrRedTapePost_{i}", mapping)
        c = _value(dst, a, "RootComponent")
        dst.exp(c)["Data"] = [p for p in dst.exp(c)["Data"] if p.get("Name") not in {"AttachParent", "RelativeRotation"}]
        wf._vec(dst.exp(c), "RelativeLocation").update(X=x, Y=y, Z=z)
        place[key] = a, c, np.array([x, y, z])
    for i, (k, l) in enumerate(spans):
        a, c, p = place[k]
        b, _, q = place[l]
        actor = _clone(dst, source, tape, level, f"WrcgAcrRedTape_{i}",
                       {src_level: level, post: a, post_comp: c, end: b})
        t = _value(dst, actor, "RootComponent")
        if _value(dst, t, "AttachParent") != c or _value(dst, t, "AttachEndToActor") != b:
            raise ValueError("ACR red tape endpoints were not remapped")
        component = dst.exp(t)
        start_at, end_at = (wf._vec(component, name) for name in ("RelativeLocation", "EndLocation"))
        delta = q - p
        delta[2] += float(end_at["Z"]) - float(start_at["Z"])
        length = float(np.linalg.norm(delta))
        _prop(dst, t, "TapeLength")["Value"] = length * 1.035
        particles = _value(dst, t, "InitialParticlesPositions")
        for u, particle in zip(np.linspace(0, 1, len(particles)), particles):
            x, y, z = delta * u
            particle["Value"][0]["Value"].update(X=float(x), Y=float(y), Z=float(z - min(80, length * 0.18) * u * (1 - u)))


def _add_roadside_props(dst, props, route_ue, to_ue, ground, width):
    from tools.acrmod import stage_dressing as sd, vegetation_visual as vv
    import wr_rvt

    if not props:
        return
    src = copy.deepcopy(vv._template())
    first = len(src.exports) + 1
    section = np.asarray(route_ue[:180])
    sd.add_dressing(src, section, 140.0, width, ground, boards=True)
    actor = next(i for i in range(first, len(src.exports) + 1)
                 if wf._mesh_of(src, i)[0] == "SM_RaceFlyingFinish")
    level, source_level = _level(dst), _level(src)
    for name, package, point, ahead, scale_xyz in props:
        p, q = to_ue([point, ahead])
        x, y, z = map(float, p)
        a = _clone(dst, src, actor, level, name, {source_level: level})
        _, c, prop = wf._mesh_of(dst, a)
        old = prop["Value"]
        new = dst.ensure_import(wr_rvt._key(package, "StaticMesh"))
        prop["Value"] = new
        for idx in (a, c):
            for key, refs in dst.exp(idx).items():
                if key.endswith("Dependencies") and refs:
                    dst.exp(idx)[key] = [new if r == old else r for r in refs]
        component = dst.exp(c)
        location = _prop(dst, c, "RelativeLocation")
        wf._vec(component, "RelativeLocation").update(X=x, Y=y, Z=float(ground(x, y, z)))
        wf._vec(component, "RelativeRotation").update(Pitch=0.0, Roll=0.0,
                                                      Yaw=math.degrees(math.atan2(q[1] - y, q[0] - x)) + 90.0)
        scale = copy.deepcopy(location)
        scale["Name"] = scale["Value"][0]["Name"] = "RelativeScale3D"
        scale["Value"][0]["Value"].update(zip("XYZ", scale_xyz))
        component["Data"] = [p for p in component["Data"] if p.get("Name") not in
                             {"RelativeScale3D", "OverrideMaterials", "CachedMaxDrawDistance"}]
        component["Data"].append(scale)
        dst._add_export_names(component)


def corner_post_template(dst, root):
    src = type(dst)(_cell_source(root, "wr_stock_cells", CORNER_POST_LEVEL, CORNER_POST_CELL))
    actor = next(i for i in range(1, len(src.exports) + 1)
                 if src.class_name(i) == "BC_PhysicsActor_C" and wf._mesh_of(src, i)[0] == "SM_CornerCuttingA")
    return src, actor


def _add_corner_posts(dst, root, posts, to_ue, ground):
    if not posts:
        return
    src, actor = corner_post_template(dst, root)
    level, src_level = _level(dst), _level(src)
    for n, (_, position, _) in enumerate(posts):
        x, y, z = map(float, to_ue([position])[0])
        a = _clone(dst, src, actor, level, f"WrcgCornerPost_{n}", {src_level: level})
        component = dst.exp(_value(dst, a, "RootComponent"))
        wf._vec(component, "RelativeLocation").update(X=x, Y=y, Z=float(ground(x, y, z)))
        wf._vec(component, "RelativeRotation").update(Pitch=0.0, Roll=0.0)


def _skip_cloth(items, cfg):
    """cfg "cloth_skip": [{"match": "NET_RED", "from_m": 2950, "to_m": 3150}]: cloth pieces whose material contains `match`
    and whose nearest route metre is in the range are left out (collision included: net_solid reads the same items)."""
    rules = (cfg or {}).get("cloth_skip") or []
    if not rules:
        return items
    import tools.acrmod.build_stage as bs
    route = np.asarray(bs.route_wrcg(bs.load_cfg(cfg["slug"])), float)[:, :2]
    s = np.r_[0.0, np.cumsum(np.hypot(*np.diff(route, axis=0).T))]
    keep = []
    for it in items:
        mat, p = str(it.get("material")).upper(), it["pos"]
        i = int(np.hypot(route[:, 0] - p[0], route[:, 1] - p[1]).argmin())
        if any(r["match"].upper() in mat and r["from_m"] <= s[i] <= r["to_m"] for r in rules):
            continue
        keep.append(it)
    return keep


def patch(cfg_for_slug):
    from tools.acrmod import cloth_visual as cv, stagectx as sc

    if getattr(cv.collect_cloth, "_wr_roadside", False):
        return
    original = cv.collect_cloth

    def collect(*a, **k):
        items, stats = original(*a, **k)
        cfg = cfg_for_slug(sc.cur().slug) or {}
        if cfg and replace_tape(cfg) and on(cfg, "acr_red_tape"):
            _, _, panels, _, _ = _red_layout(Path(__file__).resolve().parent.parent, cfg)
            items = [item for item in items if not _is_replaced(item, panels)]
        elif cfg and replace_tape(cfg) and on(cfg, "acr_wire_fence"):
            items = [item for item in items if item["template"] != "TapeCloth"]
        items = _skip_cloth(items, cfg)
        try:                                    # ACR's own nets replace WRCG's red / green ones (wr_acrnets.py)
            import wr_acrnets
            if cfg and wr_acrnets.options(cfg):
                items = [item for item in items if wr_acrnets.classify(item, cfg) is None]
        except Exception as e:
            print(f"    ACR nets: WRCG nets kept ({type(e).__name__}: {e})")
        try:                                    # hand-placed scene: its safety net (wr_scene.py)
            import wr_scene
            extra = wr_scene.cloth_items(cfg) if cfg else []
            if extra:
                items = list(items) + extra
        except Exception as e:
            print(f"    scene net: not added ({type(e).__name__}: {e})")
        return items, stats

    collect._wr_roadside = True
    collect.original = original
    cv.collect_cloth = collect


def add(dst, root, cfg, route, shift, ground, log):
    from tools.acrmod import cloth_visual as cv, props_visual as pv

    stage_dir = root / "work" / "wrcg" / cfg["slug"]
    clear = _road_test(stage_dir)

    def to_ue(x):
        return np.asarray(pv.wrcg_world_to_ue(np.asarray(x, float), shift), float)

    if replace_tape(cfg) and on(cfg, "acr_red_tape"):
        poles, spans, panels, _, _ = _red_layout(root, cfg, route, clear)
        if spans:
            _add_red_tape(dst, root, poles, spans, to_ue, ground)
            log(f"ACR Munster red tape: {len(spans)} spans, {len(poles)} wooden posts from {len(panels)} WRCG panels")
    elif replace_tape(cfg) and on(cfg, "acr_wire_fence"):
        try:
            items, _ = cv.collect_cloth.original(cfg["wrcg_level"], near_m=150.0)
            poles, spans = _tape_plan(items, clear)
            if spans:
                _add_fence(dst, root, poles, spans, to_ue, ground)
                total = sum(i["template"] == "TapeCloth" for i in items)
                log(f"ACR wire fence: {len(spans)} spans, {len(poles)} posts, {total - len(spans)} overlaps or duplicates omitted")
            else:
                log("ACR wire fence: no WRCG tape outside the road, none added")
        except Exception as e:                  # universal now: one stage's odd data must not stop the export
            log(f"ACR wire fence: not added ({type(e).__name__}: {e})")
    try:
        import wr_acrnets
        if wr_acrnets.options(cfg):
            wr_acrnets.add(dst, root, cfg, to_ue, ground, log)
    except Exception as e:                      # the stage keeps its WRCG nets' absence only if this fails: say so
        log(f"ACR nets: not added ({type(e).__name__}: {e})")
    if on(cfg, "brake_boards"):
        try:
            boards = _board_plan(route, clear, cfg)
            props = [(f"WrcgBrakeBoard_{distance}_{i}", SIGN_PACKAGE + f"SM_DistanceSign{distance}B",
                      point, ahead, (0.86625, 0.86625, 1.056)) for i, (distance, _, point, ahead) in enumerate(boards)]
            _add_roadside_props(dst, props, to_ue(route), to_ue, ground, cfg.get("road_width_m") or 7.0)
            log(f"ACR braking boards: {len(boards)} at route m {[s for _, s, _, _ in boards]}")
        except Exception as e:
            log(f"ACR braking boards: not added ({type(e).__name__}: {e})")
    if on(cfg, "corner_posts"):
        try:
            posts = _corner_post_plan(route, clear, cfg)
            _add_corner_posts(dst, root, posts, to_ue, ground)
            log(f"ACR physical corner posts: {len(posts)} at route m {[s for s, _, _ in posts]}")
        except Exception as e:
            log(f"ACR corner posts: not added ({type(e).__name__}: {e})")
