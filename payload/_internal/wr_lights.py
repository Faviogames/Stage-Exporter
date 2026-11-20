"""Night lights on WRCG's street lamps.

ACR's Monte Carlo S1 (Bollene) lights its village lamps with BP_MonBolStreetLampB3_LightOnly: a root static mesh (the lamp
head) and a spot light under it. Its class is missing from bin/acr_stage.usmap, so the actor is a RawExport (105 bytes:
the spot light and root references, the components list, the actor label); like the finish marshal it is copied by hand,
its references remapped, its components cloned. One goes on top of every WRCG street lamp prop of the level, its own lamp
head removed (StaticMesh none), so only the light is added to our lamp.
"""
import base64
import copy
import json
import re
import struct
from pathlib import Path

CELL = "wr_stock_cells/acr/Content/Levels/MonteCarloS1Bollene/_Generated_/1ETRLVT1729OA30AHK5CGZOQ7.json"
ACTOR_CLASS = "BP_MonBolStreetLampB3_LightOnly_C"
HEADER = bytes.fromhex("00041e021d021403")
REF_AT = (8, 12, 17, 25)                 # SpotLight, root, RootComponent (after a 1-byte field), BlueprintCreatedComponents[0]
RAW_SIZE = 105
BP_PKG = "Props/MonteCarloProps/MonBolStreetLampB/BP_MonBolStreetLampB3_LightOnly"
# the blueprint's spot light hangs 6.98 m above its root (Monte Carlo's root is the lamp post's foot) and gives 3.6 cd
# over 15 m: on our lamps (root at the lamp head) it was ~7 m above them and lit nothing visible (owner 2026-11-09:
# the lamps do not light). Ours: at the root, straight down, brighter, a bit further.
LIGHT = {"OuterConeAngle": 75.0, "AttenuationRadius": 2200.0, "Temperature": 3300.0, "Intensity": 25.0}
LIGHT_ORDER = ("OuterConeAngle", "IntensityUnits", "AttenuationRadius", "Temperature", "bUseTemperature", "Intensity",
               "CastShadows")
LAMP_RE = re.compile(r"^WrcgProp_(.*(STREETLAMP|STREET_LAMP|LAMPADAIRE|LAMPPOST|LANTERN|LAMP_POST).*?)(_\d+)?$", re.I)
BELOW_TOP_CM = 40.0


def _prop(e, name):
    return next((p for p in (e.get("Data") or []) if isinstance(p, dict) and p.get("Name") == name), None)


def _i32(b, o):
    return struct.unpack_from("<i", b, o)[0]


def _mesh_top_cm(mesh_pkg, legacy_roots, cache={}):
    """Top of the prop mesh above its pivot, from its ExtendedBounds (converted once per mesh)."""
    if mesh_pkg in cache:
        return cache[mesh_pkg]
    import tools.acrmod.common as c
    top = None
    rel = mesh_pkg.replace("/Game/", "acr/Content/") + ".uasset"
    for root in legacy_roots:
        p = Path(root) / rel
        if p.exists():
            out = p.with_suffix(".wr.json")
            c.asset_json(p, out)
            d = json.loads(out.read_text(encoding="utf-8"))
            e = next(x for x in d["Exports"] if x["ObjectName"] == mesh_pkg.rsplit("/", 1)[-1])
            b = {f["Name"]: f["Value"][0]["Value"] for f in _prop(e, "ExtendedBounds")["Value"]
                 if f["Name"] in ("Origin", "BoxExtent")}
            top = float(b["Origin"]["Z"]) + float(b["BoxExtent"]["Z"])
            break
    cache[mesh_pkg] = top
    return top


def _light_props(work_acr):
    """The stock spot light's own properties (from the blueprint), ours set: in their serialised order."""
    import tools.acrmod.common as c
    root = Path(work_acr) / "wr_lampbp"
    ua = root / "acr" / "Content" / (BP_PKG + ".uasset")
    if not ua.exists():
        import os
        c.retoc("to-legacy", os.environ["WRCG2ACR_ACR_PAKS"], str(root), "-f", BP_PKG.rsplit("/", 1)[-1],
                "--version", "UE5_6", "--no-shaders")
    js = ua.with_suffix(".json")
    if not js.exists():
        c.asset_json(ua, js)
    bp = json.loads(js.read_text(encoding="utf-8"))
    tmpl = next(e for e in bp["Exports"] if e["ObjectName"] == "SpotLight_GEN_VARIABLE")
    props = {p["Name"]: copy.deepcopy(p) for p in tmpl["Data"]}
    for k, v in LIGHT.items():
        props[k]["Value"] = float(v)
    head = [props[k] for k in LIGHT_ORDER if k in props]
    loc, rot = props["RelativeLocation"], props["RelativeRotation"]
    lv = loc["Value"][0]["Value"]
    lv["X"], lv["Y"], lv["Z"] = 0.0, 0.0, -10.0
    rv = rot["Value"][0]["Value"]
    rv["Pitch"], rv["Yaw"], rv["Roll"] = -90.0, 0.0, 0.0
    return head, [loc, rot]


def add_lamp_lights(dst, work_acr, legacy_roots, log=print, prefix="WrcgLampLight"):
    U = type(dst)
    cell = U(json.loads((Path(work_acr) / CELL).read_text(encoding="utf-8")))
    src = next(i for i in range(1, len(cell.exports) + 1) if cell.class_name(i) == ACTOR_CLASS)
    raw = base64.b64decode(cell.exp(src)["Data"])
    kids = [i for i in range(1, len(cell.exports) + 1) if cell.exp(i).get("OuterIndex") == src]
    if len(raw) != RAW_SIZE or raw[:8] != HEADER or {_i32(raw, o) for o in REF_AT} != set(kids):
        log("lamp lights: unexpected raw layout of the stock light actor, skipped")
        return 0
    level = next(i for i in range(1, len(dst.exports) + 1) if dst.class_name(i) == "Level")
    cell_level = next(i for i in range(1, len(cell.exports) + 1) if cell.class_name(i) == "Level")
    root_src = next(k for k in kids if cell.class_name(k) == "StaticMeshComponent")
    spot_src = next(k for k in kids if cell.class_name(k) == "SpotLightComponent")

    light_head, light_frame = _light_props(work_acr)
    lamps = []
    for i in range(1, len(dst.exports) + 1):
        e = dst.exp(i)
        m = LAMP_RE.match(e["ObjectName"])
        if not m or dst.class_name(i) != "StaticMeshActor":
            continue
        comp = dst.exp(_prop(e, "StaticMeshComponent")["Value"])
        mesh_i = _prop(comp, "StaticMesh")["Value"]
        pkg = dst.import_key(mesh_i)[0][0] if mesh_i < 0 else None     # ((package, ...), (object, ...))
        top = _mesh_top_cm(pkg, legacy_roots) if pkg else None
        loc = _prop(comp, "RelativeLocation")["Value"][0]["Value"]
        sc = _prop(comp, "RelativeScale3D")
        sz = float(sc["Value"][0]["Value"]["Z"]) if sc else 1.0
        lamps.append((float(loc["X"]), float(loc["Y"]), float(loc["Z"]) + sz * ((top or 600.0) - BELOW_TOP_CM)))

    for n, (x, y, z) in enumerate(lamps):
        e = copy.deepcopy(cell.exp(src))
        name = f"{prefix}_{n}"
        dst.add_name(name)
        e["ObjectName"] = name
        e["OuterIndex"] = level
        for k in ("ClassIndex", "TemplateIndex"):
            e[k] = dst.ensure_import(cell.import_key(e[k]))
        e["SuperIndex"] = 0
        dst.exports.append(e)
        actor = len(dst.exports)
        mapping = {src: actor, cell_level: level}
        mapping.update(dst.clone(cell, root_src, actor, preset=dict(mapping)))
        mapping.update(dst.clone(cell, spot_src, actor, preset=dict(mapping)))
        spot = dst.exp(mapping[spot_src])                        # our light settings, in serialised order
        rest = [p for p in spot["Data"] if p.get("Name") not in set(LIGHT_ORDER) | {"RelativeLocation", "RelativeRotation"}]
        attach = [p for p in rest if p.get("Name") == "AttachParent"]
        others = [p for p in rest if p.get("Name") != "AttachParent"]
        spot["Data"] = copy.deepcopy(light_head) + attach + copy.deepcopy(light_frame) + others
        b = bytearray(raw)
        for o in REF_AT:
            struct.pack_into("<i", b, o, mapping[_i32(raw, o)])
        e["Data"] = base64.b64encode(bytes(b)).decode()
        for k in ("SerializationBeforeSerializationDependencies", "CreateBeforeSerializationDependencies",
                  "SerializationBeforeCreateDependencies"):
            e[k] = [mapping[i] if i > 0 else dst.ensure_import(cell.import_key(i)) for i in e.get(k) or []]
        e["CreateBeforeCreateDependencies"] = [level]
        dst.register_actor(level, actor)
        root = dst.exp(mapping[root_src])
        v = _prop(root, "RelativeLocation")["Value"][0]["Value"]
        v["X"], v["Y"], v["Z"] = x, y, z
        r = _prop(root, "RelativeRotation")["Value"][0]["Value"]
        r["Pitch"], r["Yaw"], r["Roll"] = 0.0, 0.0, 0.0
        s = _prop(root, "RelativeScale3D")["Value"][0]["Value"]
        s["X"] = s["Y"] = s["Z"] = 1.0
        root["Data"].insert(0, {"$type": "UAssetAPI.PropertyTypes.Objects.ObjectPropertyData, UAssetAPI",
                                "Name": "StaticMesh", "ArrayIndex": 0, "PropertyGuid": None, "IsZero": False,
                                "PropertyTagFlags": "None", "PropertyTypeName": None,
                                "PropertyTagExtensions": "NoExtension", "Value": 0})   # no Monte Carlo lamp head
        dst.add_name("StaticMesh")
        for d_ in mapping.values():
            if d_ != level:
                dst._add_export_names(dst.exp(d_))
    log(f"lamp lights: {len(lamps)} street lamps lit (Monte Carlo's BP_MonBolStreetLampB3_LightOnly spot light at the "
        f"lamp head, straight down, {LIGHT['Intensity']:.0f} cd over {LIGHT['AttenuationRadius'] / 100:.0f} m)")
    return len(lamps)

FILL_SCALE = 0.1125     # 15 % of the initial intensity, minus 25 % more (owner 2026-11-15: grass too bright around the 3.1 km boards)


def add_sector_fill(dst, root, route, shift, zones, cfg, log=print):
    """Shadowless neutral fill in configured parts of the route and on their boards."""
    import numpy as np

    import wr_roadside as roadside

    xyz, _ = roadside._route_samples(np.asarray(route, float))
    board_plan = roadside._board_plan(route, roadside._road_test(root / "work" / "wrcg" / cfg["slug"]), cfg)
    positions = []
    for start, end in zones:
        for s in range(int(start) + 20, min(int(end), len(xyz)), 34):
            positions.append((xyz[s] + [0, 0, 10], 4300, 115000 * FILL_SCALE))
        for _, s, point, ahead in board_plan:
            if start <= s <= end:
                positions.append((point - 4.0 * (ahead - point) + [0, 0, 2.7], 1800, 16000 * FILL_SCALE))
    count = _add_fill_lights(dst, root, shift, positions, "WrcgSectorFill")
    log(f"ACR sector fill: {count} lights at {zones} m")
    return count


BOARD_LIGHT_CD = 135.0       # was 180: -25 % (owner 2026-11-15, the grass around the 100/50 boards looked too bright and green)
BOARD_LIGHT_H_M = 1.1        # was 0.75: higher, so its 1.5 m sphere barely touches the grass (less of a spot on the ground)


def fix_sign_lighting(dst, root, route, shift, ground, cfg, log=print):
    """Suppress nearby advert shadows and give the braking boards a tight fill."""
    import re
    import numpy as np
    from tools.acrmod import props_visual as pv
    import wr_breakables as wb
    import wr_finish as wf
    import wr_perf
    import wr_roadside as roadside
    from wr_tapeposts import AD_BOARD_RE

    start, end = cfg["sign_lighting_m"]
    points, _ = roadside._route_samples(route)
    xy = pv.wrcg_world_to_ue(points, shift)[:, :2]
    adverts = 0
    for i in range(1, len(dst.exports) + 1):
        name = dst.exp(i)["ObjectName"]
        if not name.startswith("WrcgPhysicalAdBoard_"):
            if not name.startswith(wr_perf.PROP_PREFIX):
                continue
            stem = re.sub(r"_\d+$", "", name[len(wr_perf.PROP_PREFIX):])
            if not AD_BOARD_RE.fullmatch(stem):
                continue
        _, c, _ = wf._mesh_of(dst, i)
        if not c:
            continue
        component = dst.exp(c)
        loc = wb._vec_of(component, "RelativeLocation")
        if not loc:
            continue
        d2 = ((xy - [loc["X"], loc["Y"]]) ** 2).sum(axis=1)
        at = int(d2.argmin())
        if start <= at <= end and d2[at] <= 1800 ** 2:
            wr_perf._set_bool(dst, component, "CastShadow", False)
            adverts += 1

    positions = []
    if roadside.on(cfg, "brake_boards"):
        clear = roadside._road_test(root / "work" / "wrcg" / cfg["slug"])
        for distance, s, point, ahead in roadside._board_plan(route, clear, cfg):
            if not start <= s <= end:
                continue
            x, y, z = pv.wrcg_world_to_ue(np.asarray([point]), shift)[0]
            position = point - 0.85 * (ahead - point)
            position[2] += (float(ground(x, y, z)) - z) / 100.0 + BOARD_LIGHT_H_M
            positions.append((position, 150.0, BOARD_LIGHT_CD))
            log(f"sign lighting: {distance} m board at route m {s}")
    count = _add_fill_lights(dst, root, shift, positions, "WrcgBrakeBoardFill")
    log(f"sign lighting: {adverts} advert components without shadows, {count} brake board lights")
    return adverts, count


def net_fill_positions(zones, items, route):
    """Stage build "net_fill": [{"m": [from, to], "material": "NET_RED", "every_m": 20, "toward_m": 5, "height_m": 8, "cd": 8000,
    "radius_cm": 2500, "per_side": false, "min_scale": 0}]: for the cloth pieces (the core's collect_cloth items) of that material along that stretch of the route,
    one high, broad, shadowless light per every_m metres, over the pieces' centre moved toward the road, so the net's road-facing
    side gets the light and the ground gets no spot (like the vehicles' lights, owner 2026-11-16). [(WRCG xyz, radius cm, cd)]."""
    import re
    import numpy as np
    R = np.asarray(route, float)
    out = []
    for z in zones:
        a, b = float(z["m"][0]), float(z["m"][1])
        rx, every = re.compile(z.get("material", "NET_RED"), re.I), float(z.get("every_m", 20.0))
        groups = {}
        for it in items:
            if not rx.search(str(it.get("material", ""))):
                continue
            p = np.asarray(it["pos"], float)
            if it.get("scale", 1e9) < float(z.get("min_scale", 0.0)):
                continue
            dr = np.hypot(R[:, 0] - p[0], R[:, 1] - p[1])
            i = int(dr.argmin())
            if z.get("max_lat_m") and dr[i] > float(z["max_lat_m"]):      # only what stands this close to the road
                continue
            if a <= i <= b:
                side = 0
                if z.get("per_side"):                       # one group per side of the road (+1 left of travel, -1 right)
                    h = R[min(i + 3, len(R) - 1), :2] - R[max(i - 3, 0), :2]
                    side = 1 if (-h[1] * (p[0] - R[i, 0]) + h[0] * (p[1] - R[i, 1])) > 0 else -1
                groups.setdefault((int((i - a) // every), side), []).append((p, i))
        for g in groups.values():
            P = np.mean([p for p, _ in g], axis=0)
            i = int(np.mean([i for _, i in g]))
            toward = R[i, :2] - P[:2]
            lat = float(np.hypot(*toward))
            step = toward / lat * min(float(z.get("toward_m", 5.0)), lat) if lat > 1e-6 else np.zeros(2)
            out.append((np.r_[P[:2] + step, P[2] + float(z.get("height_m", 8.0))], float(z.get("radius_cm", 2500.0)), float(z.get("cd", 8000.0))))
    return out


def _add_fill_lights(dst, root, shift, positions, prefix):
    if not positions:
        return 0
    import numpy as np
    from tools.acrmod import props_visual as pv
    import wr_finish as wf
    import wr_perf
    import wr_roadside as roadside

    # AC Rally's stock service-vehicle cell contains normal PointLight exports.
    from wr_support import prepare

    light_cell = "1NHBZUP73ATQTYQOJ9DL4PH54"
    import os
    prepare(root / "work/acr", os.environ["WRCG2ACR_ACR_PAKS"], {"truck"})
    src = type(dst)(json.loads((root / "work/acr/wr_support" / f"{light_cell}.json").read_text(encoding="utf-8-sig")))
    actor = next(i for i in range(1, len(src.exports) + 1) if src.class_name(i) == "PointLight")
    source_component = roadside._value(src, actor, "RootComponent")
    preset = {roadside._level(src): roadside._level(dst)}
    # The stock light is attached to a controller for parked vehicle lights.
    controllers = [i for i in src.children(actor) if i != source_component]
    preset.update({i: 0 for i in controllers})
    level = roadside._level(dst)
    for n, (position, radius, candelas) in enumerate(positions):
        a = roadside._clone(dst, src, actor, level, f"{prefix}_{n}", preset)
        e = dst.exp(a)
        e["Data"] = [p for p in e["Data"] if p.get("Name") != "InstanceComponents"]
        for key, refs in e.items():
            if key.endswith("Dependencies") and refs:
                e[key] = [i for i in refs if i]
        c = dst.exp(roadside._value(dst, a, "RootComponent"))
        loc = pv.wrcg_world_to_ue(np.asarray([position]), shift)[0]
        wf._vec(c, "RelativeLocation").update(zip("XYZ", map(float, loc)))
        for name, value in (("Intensity", candelas), ("AttenuationRadius", radius),
                            ("Temperature", 6500), ("SpecularScale", 0.0)):
            wr_perf._set_float(dst, c, name, value)
        wr_perf._set_bool(dst, c, "CastShadows", False)
        c["Data"] = [p for p in c["Data"] if p.get("Name") not in
                     {"AttachParent", "OriginalLightGuid", "LightGuid", "Mobility"}]
        mobility = copy.deepcopy(_prop(c, "IntensityUnits"))
        mobility.update(Name="Mobility", EnumType="EComponentMobility", Value="Movable")
        c["Data"].append(mobility)
        dst._add_export_names(c)
    return len(positions)

def set_day_skylight(dst, sky_actor, factor):
    """Scale the native sky's daytime ambient light, keeping the other phases."""
    import wr_rvt

    name = "Sky Light Intensity"
    prop = _prop(sky_actor, name)
    default = dict(ArrayIndex=0, PropertyGuid=None, IsZero=False, PropertyTagFlags="None",
                   PropertyTypeName=None, PropertyTagExtensions="NoExtension")
    if prop is None:
        prop = dict(default, **{"$type": "UAssetAPI.PropertyTypes.Structs.StructPropertyData, UAssetAPI",
                    "Name": name, "StructType": "DayPhaseAndWeatherBasedFloat", "SerializeNone": True,
                    "StructGUID": "{00000000-0000-0000-0000-000000000000}",
                    "SerializationControl": "NoExtension", "Operation": "None",
                    "Value": [{"$type": "UAssetAPI.PropertyTypes.Objects.FloatPropertyData, UAssetAPI",
                               **default, "Name": phase, "Value": 1.5}
                              for phase in ("Sunrise", "Day", "Sunset", "Night")]})
        wr_rvt._set(sky_actor, prop)
    day = next((p for p in prop["Value"] if p.get("Name") == "Day"), None)
    if day is None:
        day = dict(default, **{"$type": "UAssetAPI.PropertyTypes.Objects.FloatPropertyData, UAssetAPI",
                   "Name": "Day", "Value": 1.5})
        prop["Value"].append(day)
    day["Value"] = float(day["Value"]) * float(factor)
    dst._add_export_names(sky_actor)
    return day["Value"]


