"""Our fixes on top of the packaged exporter, applied in the step process right before its main() (see wr.py).

Stage build settings they read (data/stage_builds/<slug>.json, all optional):
  "acr_surface": "Tarmac" | "Gravel"   default: Tarmac when the inventory says the stage is mostly paved
  "tyres": "<TireCompoundsSets row>"    default: TarmacSnow on tarmac (ACR's stock tarmac stages), GravelOnly on gravel
  "tyre_degradation": "Low"             DT_TracksVariants DegradationLevel (stock: Medium); Low suggests the soft compound
  "car_setup": "<SurfaceTypes row>"     the car's preset by surface (default: the stage's surface, Gravel on snow)
  "weather_distribution": "<row>"       DT_Tracks WeatherTypesDistribution (the builder keeps Hafren's 'Wales')
  "air_temperature_c": <float>          DT_Tracks OptimalAirTemperature (Hafren's 5)
  "crowd": true                         ACR spectators on WRCG's spectator spots (wr_crowd.py)
  "ground_cover": true                  Alsace-density grass and small plants on WRCG's terrain layers (wr_groundcover.py)
  "rvt": true                           RVT volume + RVT-only terrain copies for the grass materials (wr_rvt.py)
  "net_solid" / "fence_solid" / "rock_solid" / "tree_solid" / "own_spawners_only": collision for nets, wire fences and stones, and no spawners of other stages (default ON for every stage; false switches off)
  "stop_after_m": 100                   stop control (and the finish marshal with it) this far after the finish line (default WRCG's, clamped 30-150)
  "finish_marshal_box": 0.1             scale of the finish marshal's respawn box (1 = ACR's; small = hitting him no longer respawns)
  "finish_marshal_along_m": 3.3         finish marshal this far past the stop trigger (default 3.3, with the booth), "finish_marshal_side_m": right of the road centre (0.9)
  "finish_marshal": true                Hafren's stop marshal at the finish (wr_finish.py)
  "skinned_meshes": true                WRCG's road lines, gutters and spline walls (wr_skinned.py; default on)
  "road_albedo": 0.6                    the road textures' colour times this (linear), for darker asphalt (default 1)
  "greece_gravel_dust": true             native Loutraki wheel particles (wr_gravel.py)
  "tree_visibility_tuning": true        roadside trees never distance-culled (universal since 2026-11-18, false = off; wr_perf.py)
  "gravel_grip_trial_m": [from, to]      local GravelHard-to-GravelFine comparison (wr_gravel.py)
  "tyre_marks": true                    rubber along the racing line baked into the road, as Munster (wr_tyremarks.py)
  "sign_lighting_m": [from, to]          local advert shadows and brake board visibility, in route metres (wr_lights.py)
  "water_animated_oceans": ["Ocean_4"]   selected WRCG meshes use ACR's animated water material
  "water_surface": "<physical material>"  optional material for shallow submerged road triangles
  "location": "Spain"                   ACR location "Imported <location>" (default: the WRCG country)
"""
import json
import os
from pathlib import Path

from wr import ROOT

WORK = ROOT / "work"

VEG_PREFIX = "WrcgVeg_"      # the builder names the vegetation actors WrcgVeg_<species>_<n>[_c<cull>]


def _mix_instances(slug, species, mix, log=print):
    """tree_meshes "mix": [{"mesh": "Fig/SM_Fig01", "weight": 0.25, "scale": [0.7, 1.0]}, ...]: the stage's instances of `species` get
    a mesh index (position in the mix) drawn by weight and a scale drawn from that entry's range (instances.json, rewritten in place
    with a fixed seed, so running it twice gives the same file)."""
    import re
    import numpy as np
    f = WORK / "wrcg" / slug / "vegetation" / "instances.json"
    text = f.read_text(encoding="utf-8")
    w = np.array([float(e.get("weight", 1.0)) for e in mix])
    w = w / w.sum()
    rng = np.random.default_rng(7)
    n = [0] * len(mix)

    def one(m):
        k = int(rng.choice(len(mix), p=w))
        lo, hi = mix[k].get("scale") or (0.7, 1.0)
        n[k] += 1
        o = re.sub(r'"mesh": \d+', f'"mesh": {k}', m.group(0), count=1)
        return re.sub(r'"scale": [-0-9.eE]+', f'"scale": {rng.uniform(lo, hi):.3f}', o, count=1)
    text = re.sub(r'\{[^{}]*"species": "' + re.escape(species) + r'"[^{}]*\}', one, text)
    f.write_text(text, encoding="utf-8")
    log(f"    tree mix: {species} -> " + ", ".join(f"{e['mesh'].rsplit('/', 1)[-1]} {c}" for e, c in zip(mix, n)))


def _stage_tree_meshes(slug, log=print):
    """Stage key "tree_meshes": {"olive": {"meshes": ["Smoketree/SM_Smoketree02", ...], "scale": [lo, hi]}} replaces a species' meshes (and scale) for this stage only."""
    want = (_cfg(slug) or {}).get("tree_meshes")
    if not want:
        return
    import tools._embedded as em
    import tools.datafiles as df
    vm = df.load_json("wrcg_vegetation_map.json")
    for k, v in want.items():
        if k in vm.get("acr_species", {}):
            if v.get("mix"):
                v = dict(v, meshes=[e["mesh"] for e in v["mix"]])
                _mix_instances(slug, k, v["mix"], log)
            upd = {"meshes": ["/Game/Foliage/Trees/" + m for m in v["meshes"]]}
            if v.get("scale"):
                upd["scale"] = list(v["scale"])
            vm["acr_species"][k] = dict(vm["acr_species"][k], **upd)
            log(f"    tree meshes: {k} -> {', '.join(upd['meshes'])}")
    em.DATA["wrcg_vegetation_map.json"] = df.scramble(json.dumps(vm, ensure_ascii=False).encode("utf-8"))


def before(module, args):
    import wr_skinned
    wr_skinned.patch_rmat()
    if module == "tools.acrmod.build_stage":
        import wr_compat
        wr_compat.prepare()
        for slug in [a for a in args if not a.startswith("-")]:
            start_pos_alias(slug)
            _drop_pacenote_tokens(slug)
            _drop_rocks(slug)
            _drop_collision(slug)
        import wr_pack
        wr_pack.patch_cache()
        wr_skinned.patch_props(_stage_info)
        import wr_lods
        wr_lods.patch()
        import wr_tunnel
        wr_tunnel.patch()
        import wr_finish
        wr_finish.patch_gameplay()
        _patch_prestart()
        if "--one-stage" in args:                     # a stage's own build process
            one = args[args.index("--one-stage") + 1]
            import wr_snowtrees
            if wr_snowtrees.is_snow(_cfg(one)):       # snowy ACR trees (wr_snowtrees.py)
                wr_snowtrees.patch_species()
            _stage_tree_meshes(one)
            _stage_surfaces(one)
        _patch_solid_props()
        _patch_graph_props()
        import wr_tyremarks
        wr_tyremarks.patch_build(_stage_info)
        _patch_tables()
        _patch_physmat_wood()
        _patch_crowd()
        _patch_ground_cover_materials()
        _patch_level_save()
        _patch_wall_materials()
        _patch_road_grid()
        _patch_road_fringe()
        _patch_road_seams()
        _patch_decals()
        import wr_roadside
        wr_roadside.patch(_cfg)
        import wr_tapeposts
        wr_tapeposts.patch_physics(_cfg)
        _patch_sheared_props()
        _patch_water()
        _patch_no_water()
        _patch_water_surface()
        import wr_gravel
        wr_gravel.patch_grip(_cfg)
        _patch_psi_names()


    if module == "tools.wrcg.vegetation_replay":
        _patch_replay_rules()
    if module.startswith("tools.wrcg."):
        _add_crossings()


def after(module, args):
    if module == "tools.wrcg.export_stage":
        _after_export_stage(args)
    if module == "tools.wrcg.terrain" and "--out" in args:
        _base_layers(Path(args[args.index("--out") + 1]) / "terrain_mesh.npz")
    if module == "tools.acrmod.ittiri_terrain" and args[:1] == ["adjust"] and len(args) > 1:
        _base_layers(WORK / "wrcg" / args[1] / "terrain" / "terrain_mesh_adj.npz")
    if module == "tools.wrcg.textures" and "--out" in args:
        _road_tone(Path(args[args.index("--out") + 1]))
        _road_tint(Path(args[args.index("--out") + 1]))
        _terrain_match(Path(args[args.index("--out") + 1]))
        snow_tone(Path(args[args.index("--out") + 1]))
    if module == "tools.acrmod.build_stage":
        mod = args[args.index("--mod-dir") + 1] if "--mod-dir" in args else "wrcg_stages"
        for slug in [a for a in args if not a.startswith("-") and (WORK.parent / "custom" / "data" / "stage_builds" / f"{a}.json").exists()]:
            import wr_compat
            wr_compat.after_build(slug, (_cfg(slug) or {}).get("name") or slug, mod)     # ACR 26756580: materials' shader maps + level layout
            _tint_cloth(slug, mod)
            _light_props(slug, mod)
            _fix_missing_materials(slug, mod)
    if module == "tools.wrcg.vegetation_replay" and "--stage" in args:
        slug = args[args.index("--stage") + 1]
        cfg = _cfg(slug)
        if cfg and cfg.get("ground_cover"):
            import wr_groundcover
            wr_groundcover.append(WORK / "wrcg" / slug, log=lambda s: print(f"[{slug}] {s}"))


def _tint_cloth(slug, mod="wrcg_stages"):
    """"cloth_tint": {"LARGENET_GREEN": [r, g, b]}: the net's material instance gets Simple_BaseColorTintMultiply = this
    (linear, 1 = as WRCG's texture), written into the built legacy folder before the pak is made (owner 2026-11-15:
    a lighter green net)."""
    import tempfile
    import tools.acrmod.common as c
    cfg = _cfg(slug) or {}
    for key, rgb in (cfg.get("cloth_tint") or {}).items():
        f = WORK / "acr" / "mods" / mod / "legacy" / "acr" / "Content" / "Environments" / cfg["name"] / "Props" / "Materials" / f"MI_{key}.uasset"
        if not f.exists():
            print(f"    [{slug}] cloth tint: {f.name} not found, skipped")
            continue
        tmp = Path(tempfile.mkdtemp(prefix="wr_cloth_"))
        c.asset_json(f, tmp / "mi.json")
        d = json.loads((tmp / "mi.json").read_text(encoding="utf-8"))
        n = 0
        for p in d["Exports"][0]["Data"]:
            if p["Name"] != "VectorParameterValues":
                continue
            for s in p["Value"]:
                fld = {x["Name"]: x for x in s["Value"]}
                if next(x["Value"] for x in fld["ParameterInfo"]["Value"] if x["Name"] == "Name") == "Simple_BaseColorTintMultiply":
                    fld["ParameterValue"]["Value"][0]["Value"].update(R=float(rgb[0]), G=float(rgb[1]), B=float(rgb[2]))
                    n += 1
        if n:
            c.write_asset(d, tmp / "mi.edit.json", f)
        print(f"    [{slug}] cloth tint: {key} x{list(rgb)} ({'written' if n else 'no tint parameter found'})")


def _light_props(slug, mod="wrcg_stages"):
    """"prop_ao" (universal, 0.5 by default, false = off): every prop material instance of the stage (signs, fences, cars,
    boards...) gets Simple_AO intensity = this, so the side of an object that faces away from the sun is less dark
    (owner 2026-11-15, Seyabei: the shaded side of the parked vehicles and of the boards). M_Simple's default for it is
    NOT known (not readable from the stock asset), 0.5 assumes it is 1; not checked in game."""
    import copy
    import tempfile
    import tools.acrmod.common as c
    cfg = _cfg(slug) or {}
    val = cfg.get("prop_ao", 0.5)
    if val is False or val is None or not cfg.get("name"):
        return
    folder = WORK / "acr" / "mods" / mod / "legacy" / "acr" / "Content" / "Environments" / cfg["name"] / "Props" / "Materials"
    done = skipped = 0
    for f in sorted(folder.glob("MI_*.uasset")):
        tmp = Path(tempfile.mkdtemp(prefix="wr_ao_"))
        try:
            d = c.asset_json(f, tmp / "mi.json")
            data = d["Exports"][0]["Data"]
            sc = next((p for p in data if p["Name"] == "ScalarParameterValues"), None)
            if sc is None or not sc["Value"]:
                skipped += 1
                continue
            vals = sc["Value"]
            def pname(item):
                fl = {x["Name"]: x for x in item["Value"]}
                return next(x["Value"] for x in fl["ParameterInfo"]["Value"] if x["Name"] == "Name"), fl
            hit = False
            for item in vals:
                n, fl = pname(item)
                if n == "Simple_AO intensity":
                    fl["ParameterValue"]["Value"] = float(val)
                    hit = True
            if not hit:
                item = copy.deepcopy(vals[0])
                n, fl = pname(item)
                for x in fl["ParameterInfo"]["Value"]:
                    if x["Name"] == "Name":
                        x["Value"] = "Simple_AO intensity"
                fl["ParameterValue"]["Value"] = float(val)
                vals.append(item)
                if "Simple_AO intensity" not in d["NameMap"]:
                    d["NameMap"].append("Simple_AO intensity")
            c.write_asset(d, tmp / "mi.edit.json", f)
            done += 1
        except Exception as e:
            skipped += 1
            print(f"    [{slug}] prop AO: {f.name} skipped ({e!r})")
    print(f"    [{slug}] prop AO: Simple_AO intensity {val} on {done} prop materials ({skipped} skipped)")


def _drop_rocks(slug):
    """"drop_rocks": [{"m": 3401, "radius": 30}]: every stone / rock / pebble of the vegetation (rock, gc_rock, gc_stone...)
    within radius metres of route metre m is taken out of vegetation/instances.json, so it has neither visual nor
    collision (owner 2026-11-15, Seyabei m 3401: an almost invisible stone gave a hard hit). The first run keeps the
    original as instances.before_drop.json (refreshed when a new WRCG export rewrote instances.json) and every run filters
    that copy, so changing the list always works."""
    import re
    import shutil
    import numpy as np
    import tools.acrmod.build_stage as bs
    import wr_scene
    cfg = _cfg(slug) or {}
    zones = cfg.get("drop_rocks") or []
    f = WORK / "wrcg" / slug / "vegetation" / "instances.json"
    orig = f.with_name("instances.before_drop.json")
    if not zones or not (f.exists() or orig.exists()):
        return
    if not orig.exists() or f.stat().st_mtime_ns > orig.stat().st_mtime_ns:      # a new WRCG export rewrote the file
        shutil.copyfile(f, orig)
    import tools.acrmod.stagectx as sc
    bcfg = bs.load_cfg(slug)                                  # before() runs with no stage context: the core would read another stage's route
    sc.use(sc.Stage(slug, cfg["name"], cfg["wrcg_level"], str(cfg["stage_id"]).split("/")[-1]))
    route = np.asarray(bs.route_wrcg(bcfg), float)
    spots = [(wr_scene.frame(route, float(z["m"]))[0][:2], float(z.get("radius", 30.0))) for z in zones]
    rx = re.compile(r'\{[^{}]*"species": "([^"]*)"[^{}]*\}')
    kind = re.compile(r"rock|stone|peb")
    xy = re.compile(r'"x": (-?[0-9.eE+-]+), "y": (-?[0-9.eE+-]+)')
    dropped = [0]

    def keep(m):
        if not kind.search(m.group(1)):
            return m.group(0)
        q = xy.search(m.group(0))
        if q and any(np.hypot(float(q.group(1)) - c[0], float(q.group(2)) - c[1]) <= r for c, r in spots):
            dropped[0] += 1
            return "\x00"
        return m.group(0)
    text = rx.sub(keep, orig.read_text(encoding="utf-8"))
    text = re.sub(r",?\s*\x00", "", text).replace("[,", "[")
    f.write_text(text, encoding="utf-8")
    import os
    os.utime(orig, ns=(f.stat().st_atime_ns, f.stat().st_mtime_ns))      # same time: only a newer instances.json counts as new
    print(f"    [{slug}] drop rocks: {dropped[0]} stones/rocks within {zones} left out of the vegetation")


def _drop_collision(slug):
    """Stage build "drop_collision": [{"node_id": "1190063953"}, ...]: the collision of those owners of
    work/wrcg/<slug>/collision_extra.npz (props, spawners; see its owner_node_id) is left out of the build: its triangles
    are removed from the file. The first run keeps the original as collision_extra.before_drop.npz (refreshed when a new
    WRCG export rewrote the file) and every run filters that copy. Owner 2026-11-16, Ngema m ~2970: a grey wall that
    could not be crossed (the collision of two rows of CATTLE_BARRIER_01)."""
    import os
    import shutil
    import numpy as np
    rows = (_cfg(slug) or {}).get("drop_collision") or []
    f = WORK / "wrcg" / slug / "collision_extra.npz"
    orig = f.with_name("collision_extra.before_drop.npz")
    if not rows and orig.exists():                        # the list was emptied: put the original collision back
        shutil.copyfile(orig, f)
        orig.unlink()
        print(f"    [{slug}] drop collision: original collision restored")
        return
    if not rows or not (f.exists() or orig.exists()):
        return
    if not orig.exists() or f.stat().st_mtime_ns > orig.stat().st_mtime_ns:
        shutil.copyfile(f, orig)
    d = dict(np.load(orig, allow_pickle=True))
    ids = {str(r["node_id"]) for r in rows}
    owners = [i for i, n in enumerate(d["owner_node_id"]) if str(n) in ids]
    n_tri = len(d["triangles"])
    keep = ~np.isin(d["tri_piece"], owners)
    for k, v in list(d.items()):
        if hasattr(v, "__len__") and not isinstance(v, str) and len(v) == n_tri and k.startswith(("tri", "triangles")):
            d[k] = np.asarray(v)[keep]
    np.savez(f, **d)
    os.utime(orig, ns=(f.stat().st_atime_ns, f.stat().st_mtime_ns))
    print(f"    [{slug}] drop collision: {len(owners)} owners, {int((~keep).sum())} triangles left out of {n_tri}")


def _fix_missing_materials(slug, mod="wrcg_stages"):
    """A prop mesh that points to a material instance the core did not write (Seyabei: HOUSE_003 -> MI_WALL, seen as pale
    default panels, owner 2026-11-15) gets a copy of its sibling MI_<name>_2 (or the first MI_<name>_N)."""
    import re
    import tempfile
    import tools.acrmod.common as c
    import wr_snowtrees as st
    cfg = _cfg(slug) or {}
    if not cfg.get("name"):
        return
    legacy = WORK / "acr" / "mods" / mod / "legacy"
    props = legacy / "acr" / "Content" / "Environments" / cfg["name"] / "Props"
    mats = props / "Materials"
    have = {f.stem for f in mats.glob("MI_*.uasset")}
    for sm in props.glob("SM_*.uasset"):
        for name in sorted(set(m.decode() for m in re.findall(rb"/Props/Materials/(MI_[A-Za-z0-9_]+)", sm.read_bytes()))):
            if name in have:
                continue
            sib = sorted(n for n in have if re.fullmatch(re.escape(name) + r"_\d+", n))
            if not sib:
                print(f"    [{slug}] missing material {name} (used by {sm.stem}): no sibling to copy")
                continue
            tmp = tempfile.mkdtemp(prefix="wr_mi_")
            pkg = f"/Game/Environments/{cfg['name']}/Props/Materials/"
            d = c.asset_json(mats / f"{sib[0]}.uasset", Path(tmp) / "mi.json")
            st._clone(d, pkg + sib[0], pkg + name, {}, legacy, tmp)
            have.add(name)
            print(f"    [{slug}] missing material {name} (used by {sm.stem}): copy of {sib[0]}")


def _on(slug, key):
    """Collision fixes that are for every stage (owner 2026-11-14, Spain: "ese arreglo debe ser universal"): on unless the
    stage build says false."""
    return bool((_cfg(slug) or {}).get(key, True))


def _cfg(slug):
    import tools.datafiles as df
    try:
        return df.load_json(f"stage_builds/{slug}.json")
    except Exception:
        return None


def _base_layers(npz):
    """Terrain holes. WRCG marks a terrain triangle that must not be drawn or collided with (a tunnel's portals) by
    setting 0x80 on its layer (IT_SANREMO: 126 triangles, layers 128-143, at both ends of the Ronde tunnel, s 1463-1633
    m); ittiri_terrain.collision_meshes knows the 16 layers only and stopped with KeyError: 134. Those triangles are
    cut out of the terrain mesh (first try kept them with their base layer: the tunnel came out closed, owner
    2026-11-09). The tunnel itself is a skinned mesh (FR_TUNNEL_01, wr_skinned.py)."""
    import numpy as np
    if not Path(npz).exists():
        return
    d = dict(np.load(npz, allow_pickle=True))
    tl = d.get("tri_layer")
    if tl is None or not (tl >= 128).any():
        return
    keep = tl < 128
    nt = len(d["triangles"])
    for k, v in list(d.items()):
        if hasattr(v, "shape") and v.ndim >= 1 and len(v) == nt and k != "positions":
            d[k] = v[keep]
    np.savez(npz, **d)
    print(f"    terrain: {int((~keep).sum())} hole triangles (layer flag 0x80) cut out ({Path(npz).name})")


def _stage_info():
    """(cfg, selective-load mask) of the stage build_stage is building, or None."""
    import tools.acrmod.stagectx as sc
    import wr_skinned
    try:
        slug = sc.cur().slug
    except Exception:
        return None
    cfg = _cfg(slug)
    return (cfg, wr_skinned.stage_mask(cfg.get("stage_id"))) if cfg else None


def _after_export_stage(args):
    """WRCG side, per exported stage: the skinned pieces' collision into collision_extra.npz (wr_skinned.py)."""
    import tools.wrcg.stage_spec as ss
    import wr_skinned
    root = Path(args[args.index("--out-root") + 1]) if "--out-root" in args else WORK / "wrcg"
    for sid in [a for a in args if "/" in a and not a.startswith("-")]:
        slug = ss.slug(sid)
        cfg = _cfg(slug) or {}
        crossing_uvs(root / slug, log=lambda s, slug=slug: print(f"[{slug}] {s.strip()}"))
        if not cfg.get("skinned_meshes", True):
            continue
        wr_skinned.append_collision(root / slug, cfg.get("wrcg_level") or sid.split("/")[0], wr_skinned.stage_mask(sid),
                                    log=lambda s, slug=slug: print(f"[{slug}] {s.strip()}"))


# WRCG's crossings and roundabouts (INTERSECTIONBUILDSTEP pieces, copied in with the road by _add_crossings) carry no
# UVs (uv_raw all 0): their PROCEDURALROAD material has world-space textures only (WS_ASPHALT_PANZERPLATTE_01), mapped
# by position in WRCG. Baked with UV 0 the whole piece took one texel (owner 2026-11-10, Riudecanyes' roundabouts
# s 5833-6131: "un poco roto de textura y/o UVs"). They get planar UVs from x, y at the road's texel density (the road
# pieces: about 0.1 UV per metre), centred on the piece so the int16 UVs (x 4096) do not overflow, the origin on a whole
# tile so neighbouring pieces stay in phase.
WS_TILE_M = 10.0


def crossing_uvs(stage_dir, log=print):
    import numpy as np
    done = []
    for f in sorted(Path(stage_dir, "render_prm").glob("*.npz")):
        d = dict(np.load(f))
        uv = d.get("uv_raw")
        if uv is None or np.any(uv[:, :2]) or not len(uv):
            continue
        P = d["positions"].astype(float)
        c = np.round(P[:, :2].mean(0) / WS_TILE_M) * WS_TILE_M
        u = np.clip(np.round((P[:, :2] - c) / WS_TILE_M * 4096.0), -32767, 32767).astype(np.int16)
        uv = uv.copy()
        uv[:, 0:2] = u
        uv[:, 2:4] = u
        d["uv_raw"] = uv
        np.savez(f, **d)
        done.append(f.stem)
    if done:
        log(f"crossings: world-space UVs ({WS_TILE_M:.0f} m tiles) for {len(done)} road pieces without UVs: "
            f"{', '.join(sorted({s.rsplit('_lod', 1)[0] for s in done}))}")
    return done


# --- darker asphalt ---------------------------------------------------------------------------------------------------

# The road is baked into the terrain tiles from WRCG's asphalt textures as they are (RS_ASPHALT_PANZERPLATTE_01_01: sRGB
# 0.23 on average, the baked road the same); WRCG darkens and mixes them in its road shader, ACR's own asphalt
# (Munster) is its texture times a 0.5 grey tint. Owner drive 2026-11-09: the asphalt looked light grey, Catalan asphalt
# is darker. With "road_albedo" in the stage build, the stage's asphalt textures (work/wrcg/<slug>/textures/*ASPHALT*
# _DIFF.png, the tyre-mark texture apart) are written again with their linear colour times that factor; the export's
# own files are kept in textures/_wr_orig.
TONE_ORIG = "_wr_orig"
TONE_STATE = "_wr_tone.json"


TARMAC_LIGHT = 0.33


def _road_tone(tex_dir):
    import numpy as np
    from PIL import Image
    slug = tex_dir.parent.name
    cfg = _cfg(slug) or {}
    factor = float(cfg.get("road_albedo") or 1.0)
    orig_dir, state_f = tex_dir / TONE_ORIG, tex_dir / TONE_STATE
    try:
        state = json.loads(state_f.read_text())
    except (OSError, ValueError):
        state = {}
    done = []
    # the light TARMAC ones too (Arganil's WS_TARMAC_WORN, mean sRGB 0.38, stayed light grey: owner 2026-11-10 "el
    # asfalto sigue mal"); Catalunya's (0.19-0.28) are dark already and are left alone
    files = sorted(tex_dir.glob("*ASPHALT*_DIFF.png"))
    for f in sorted(tex_dir.glob("*TARMAC*_DIFF.png")):
        if "TIRE" in f.name.upper() or f in files:
            continue
        g = orig_dir / f.name
        mean = float(np.asarray(Image.open(g if g.exists() else f).convert("RGB"), np.float32).mean()) / 255.0
        if mean > TARMAC_LIGHT:
            files.append(f)
    for f in files:
        if "TIREMARK" in f.name.upper():
            continue
        src = orig_dir / f.name
        mine = state.get(f.name)
        if not (mine and src.exists() and abs(f.stat().st_mtime - mine["mtime"]) < 1e-3):
            orig_dir.mkdir(exist_ok=True)                    # the export wrote it (again): that is the original
            src.write_bytes(f.read_bytes())
        if abs(factor - 1.0) < 1e-6:
            if mine:
                f.write_bytes(src.read_bytes())
                state.pop(f.name, None)
            continue
        im = Image.open(src)
        a = np.asarray(im.convert("RGBA"), np.float32) / 255.0
        lin = np.where(a[..., :3] <= 0.04045, a[..., :3] / 12.92, ((a[..., :3] + 0.055) / 1.055) ** 2.4) * factor
        a[..., :3] = np.where(lin <= 0.0031308, lin * 12.92, 1.055 * np.power(np.maximum(lin, 0), 1 / 2.4) - 0.055)
        out = Image.fromarray((np.clip(a, 0, 1) * 255 + 0.5).astype(np.uint8), "RGBA")
        (out if im.mode == "RGBA" else out.convert(im.mode if im.mode in ("RGB", "L") else "RGB")).save(f)
        state[f.name] = {"mtime": f.stat().st_mtime, "factor": factor}
        done.append(f.name.split("__")[-1].replace("_DIFF.png", ""))
    state_f.write_text(json.dumps(state, indent=1))
    if done:
        print(f"[{slug}] asphalt textures x{factor} (linear): {', '.join(done)}")


def _acr_png(name):
    """wr_assets/<name>.png: the colour of an ACR texture (DXT1), made once from the user's own game (nothing of ACR is shipped)."""
    import subprocess
    import struct
    import tempfile
    import numpy as np
    from PIL import Image
    out = Path(__file__).resolve().parent / "wr_assets" / f"{name}.png"
    if out.exists():
        return out
    import wr
    import wr_tyremarks
    paks = wr._installs()[1] / "acr" / "Content" / "Paks"
    tmp = Path(tempfile.mkdtemp(prefix="wr_tex_"))
    subprocess.run([str(ROOT / "bin" / "retoc" / "retoc.exe"), "to-legacy", str(paks), str(tmp), "-f", name, "--version", "UE5_6",
                    "--no-shaders", "--no-script-objects"], capture_output=True)
    uexp = next(tmp.rglob(name + ".uexp"), None)
    if uexp is None:
        raise RuntimeError(f"ACR texture {name} not found in the game: {paks}")
    d = uexp.read_bytes()
    i = d.find(b"PF_")
    w, h, _ = struct.unpack("<3i", d[i - 16:i - 4])
    fmt = d[i:i + struct.unpack("<i", d[i - 4:i])[0] - 1].decode()
    bulk = uexp.with_suffix(".ubulk")
    if fmt != "PF_DXT1" or not bulk.exists():
        raise RuntimeError(f"ACR texture {name}: format {fmt} not supported here (DXT1 with .ubulk expected)")
    px = wr_tyremarks._decode_bc1(bulk.read_bytes()[: w * h // 2], w, h)
    Image.fromarray(np.ascontiguousarray(px), "RGB").save(out)
    print(f"    ACR texture {name} extracted from the game ({w}x{h})")
    return out


def _road_tint(tex_dir):
    """"road_tint": [r, g, b], the road's gravel textures (ROADS_PROCEDURAL/GRAVEL) times this in linear colour (owner
    2026-11-14: Kenya's road redder, brown, arid); "road_track_texture": the name of an ACR texture in wr_assets/ whose colour replaces the track's (alpha kept); "road_texture": the same for the main road gravel textures (colour of wr_assets/<name>.png, own alpha kept, no tint; "terrain_match" then follows it); "road_track_tint": the same for the wheel-track texture (TM_*, beige and
    pale over the red road: a grey band where the wheels pass; dark brown wanted). Originals kept in _wr_orig."""
    import numpy as np
    from PIL import Image
    slug = tex_dir.parent.name
    cfg = _cfg(slug) or {}
    tint, track = cfg.get("road_tint"), cfg.get("road_track_tint")
    orig_dir, state_f = tex_dir / TONE_ORIG, tex_dir / "_wr_tint.json"
    try:
        state = json.loads(state_f.read_text())
    except (OSError, ValueError):
        state = {}
    done = []
    for f in sorted(tex_dir.glob("*ROADS_PROCEDURAL__GRAVEL*_DIFF.png")):
        is_tm = "__TM_" in f.name.upper()
        swap = cfg.get("road_track_texture") if is_tm else cfg.get("road_texture")
        want = (track or ([1.0, 1.0, 1.0] if swap else None)) if is_tm else ([1.0, 1.0, 1.0] if swap else tint)
        src, mine = orig_dir / f.name, state.get(f.name)
        if not (mine and src.exists() and abs(f.stat().st_mtime - mine["mtime"]) < 1e-3):
            orig_dir.mkdir(exist_ok=True)
            src.write_bytes(f.read_bytes())
        if not want:
            if mine:
                f.write_bytes(src.read_bytes())
                state.pop(f.name, None)
            continue
        im = Image.open(src)
        a = np.asarray(im.convert("RGBA"), np.float32) / 255.0
        if swap:                       # the colour of an ACR texture (wr_assets/<name>.png), the track's own alpha kept
            tx = Image.open(_acr_png(swap)).convert("RGB").resize(im.size, Image.LANCZOS)
            a[..., :3] = np.asarray(tx, np.float32) / 255.0
        a[..., :3] = _lin_to_srgb(_srgb_to_lin(a[..., :3]) * np.asarray(want, np.float32))
        out = Image.fromarray((np.clip(a, 0, 1) * 255 + 0.5).astype(np.uint8), "RGBA")
        (out if im.mode == "RGBA" else out.convert(im.mode if im.mode in ("RGB", "L") else "RGB")).save(f)
        state[f.name] = {"mtime": f.stat().st_mtime, "tint": list(want)}
        done.append(f.name.split("__")[-1].replace("_DIFF.png", ""))
    state_f.write_text(json.dumps(state, indent=1))
    if done:
        print(f"[{slug}] road gravel textures tinted (linear): {', '.join(done)}")


TERRAIN_MATCH_RE = ("TERRAIN__GRAVEL__", "TERRAIN__ROCK__ROCKY_SOIL", "VR_TERRAIN__KENYA__GRAVEL", "VR_TERRAIN__KENYA__MUD",
                    "VR_TERRAIN__KENYA__SAND")
MATCH_CLIP = (0.55, 1.7)


def _terrain_match(tex_dir):
    """"terrain_match": the terrain's soil textures (gravel, rocky soil, Kenya's gravel, mud and sand) get a per-channel
    factor that takes their mean linear colour to that of the road's gravel textures (already tinted by "road_tint"), so the
    road and the ground around it are one colour (owner 2026-11-14: patches of a lighter sand colour). Detail is kept;
    DIFFHM's alpha (height) is untouched. Originals in _wr_orig under TERRAIN_STATE."""
    import numpy as np
    from PIL import Image
    slug = tex_dir.parent.name
    if not (_cfg(slug) or {}).get("terrain_match"):
        return
    road = [f for f in tex_dir.glob("*ROADS_PROCEDURAL__GRAVEL*_DIFF.png") if "__TM_" not in f.name.upper()]
    if not road:
        return
    lin = lambda f: _srgb_to_lin(np.asarray(Image.open(f).convert("RGB"), np.float32) / 255.0).reshape(-1, 3).mean(0)
    target = np.mean([lin(f) for f in road], axis=0)
    orig_dir, state_f = tex_dir / TONE_ORIG, tex_dir / "_wr_terrain.json"
    try:
        state = json.loads(state_f.read_text())
    except (OSError, ValueError):
        state = {}
    done = []
    for f in sorted(tex_dir.glob("*_DIFF*.png")):
        if not any(k in f.name for k in TERRAIN_MATCH_RE) or "ROADS_PROCEDURAL" in f.name:
            continue
        src, mine = orig_dir / f.name, state.get(f.name)
        if not (mine and src.exists() and abs(f.stat().st_mtime - mine["mtime"]) < 1e-3):
            orig_dir.mkdir(exist_ok=True)
            src.write_bytes(f.read_bytes())
        im = Image.open(src)
        a = np.asarray(im.convert("RGBA"), np.float32) / 255.0
        l = _srgb_to_lin(a[..., :3])
        fac = np.clip(target / np.maximum(l.reshape(-1, 3).mean(0), 1e-4), *MATCH_CLIP)
        a[..., :3] = _lin_to_srgb(l * fac)
        out = Image.fromarray((np.clip(a, 0, 1) * 255 + 0.5).astype(np.uint8), "RGBA")
        (out if im.mode == "RGBA" else out.convert(im.mode if im.mode in ("RGB", "L") else "RGB")).save(f)
        state[f.name] = {"mtime": f.stat().st_mtime, "factor": [round(float(x), 2) for x in fac]}
        done.append(f"{f.name.split('__')[-1].replace('.png', '')} x{[round(float(x), 2) for x in fac]}")
    state_f.write_text(json.dumps(state, indent=1))
    if done:
        print(f"[{slug}] terrain textures matched to the road colour: {'; '.join(done)}")


# WRCG's snow road textures are blue on purpose (RS_SNOW_LARGEROAD_BLUE_01_01 mean sRGB 0.73 / 0.80 / 0.84): WRCG's own
# lighting takes the blue out, ACR shows it (owner 2026-11-09, Sävar: "la pista nevada está azulada"). ACR's snow road
# (Livigno, MI_LivignoSnowTrack: Snowy_Road_ue3mccan 0.88 / 0.88 / 0.88, Chunky_Snow 0.91 / 0.92 / 0.92) is neutral white.
# The *SNOW*_BLUE* colour textures keep SNOW_CHROMA of their colour and their mean brightness goes to SNOW_TARGET (sRGB).
SNOW_CHROMA = 0.15
SNOW_TARGET = 0.86
SNOW_STATE = "wr_snow_tone.json"


def _srgb_to_lin(a):
    import numpy as np
    return np.where(a <= 0.04045, a / 12.92, ((a + 0.055) / 1.055) ** 2.4)


def _lin_to_srgb(a):
    import numpy as np
    return np.where(a <= 0.0031308, a * 12.92, 1.055 * np.power(np.maximum(a, 0), 1 / 2.4) - 0.055)


def snow_tone(tex_dir):
    """Neutral snow (see SNOW_*). The originals are kept in TONE_ORIG like the asphalt ones; files already toned (same
    mtime as recorded) are left alone."""
    import numpy as np
    from PIL import Image
    tex_dir = Path(tex_dir)
    slug = tex_dir.parent.name
    orig_dir, state_f = tex_dir / TONE_ORIG, tex_dir / SNOW_STATE
    try:
        state = json.loads(state_f.read_text())
    except (OSError, ValueError):
        state = {}
    done = []
    for f in sorted(tex_dir.glob("*_DIFF.png")):
        n = f.name.upper().split("__")[-1]
        if "SNOW" not in n or "_BLUE" not in n:
            continue
        src = orig_dir / f.name
        mine = state.get(f.name)
        if mine and src.exists() and abs(f.stat().st_mtime - mine["mtime"]) < 1e-3:
            continue
        orig_dir.mkdir(exist_ok=True)                         # the export wrote it (again): that is the original
        src.write_bytes(f.read_bytes())
        im = Image.open(src)
        a = np.asarray(im.convert("RGBA"), np.float32) / 255.0
        lin = _srgb_to_lin(a[..., :3])
        y = (lin * np.array([0.2126, 0.7152, 0.0722], np.float32)).sum(-1, keepdims=True)
        lin = y + (lin - y) * SNOW_CHROMA
        lin *= float(_srgb_to_lin(np.float32(SNOW_TARGET))) / max(float(y.mean()), 1e-6)
        a[..., :3] = _lin_to_srgb(np.clip(lin, 0, 1))
        out = Image.fromarray((np.clip(a, 0, 1) * 255 + 0.5).astype(np.uint8), "RGBA")
        (out if im.mode == "RGBA" else out.convert(im.mode if im.mode in ("RGB", "L") else "RGB")).save(f)
        state[f.name] = {"mtime": f.stat().st_mtime, "chroma": SNOW_CHROMA, "target": SNOW_TARGET}
        done.append(n.replace("_DIFF.PNG", ""))
    if done:
        state_f.write_text(json.dumps(state, indent=1))
        print(f"[{slug}] snow textures neutral white (chroma x{SNOW_CHROMA}, mean sRGB {SNOW_TARGET}): {', '.join(done)}")
    return done


# --- vegetation replay rules for levels without hand-made ones -------------------------------------------------------

# WRCG type name keywords -> one of the hand-made Acropolis rules (its species, meshes, bands); None drops the type (grass
# and flowers: the ground cover draws those)
AUTO_RULES = [
    (r"dead|cactus|aloe", None), (r"grass|weed|flower|clover|moss|fern|leaf|leaves|straw", None),
    # Kenya (owner 2026-11-14: the acacias, baobabs and euphorbias were all dropped): the closest of the Acropolis species
    (r"acacia|canarium", "OLIVETREE"), (r"baobab|banana|palm", "SUGAR_ROUND_01"), (r"euphorb|candelabr", "AZALEA_P_01"),
    (r"bush|shrub|azalea|rosemary|sage|bramble|broom|myrtle|heather|lavender|thyme|gorse|juniper_b|_p_|_p$", "AZALEA_P_01"),
    (r"cypres|cypress", "CYPRES"), (r"pine|larch|spruce|fir|conifer|cedar|scots", "PINE"),
    (r"olive|lemon|orange|citrus", "OLIVETREE"),
    (r"oak|hazel|sugar|round|buckeye|chestnut|walnut", "SUGAR_ROUND_01"),
    (r"beech|maple|plane|platane|lime|aspen|birch|eucalyptus|poplar|ash|elm|bignay|tree", "SUGAR_ROUND_01"),
    (r"rock|pebble|peeble|stone|boulder", "Peebles_Generic_01"),
]


def _auto_rule(type_name):
    import re as _re
    import tools.datafiles as df
    base = df.load_json("wrcg_vegetation_map.json")["locations"]["GR_ACROPOLIS"]["replay_types"]
    for pat, ref in AUTO_RULES:
        if _re.search(pat, type_name, _re.I):
            if ref is None:
                return {"species": None, "why": f"auto (wr_fixes): {type_name} dropped"}
            r = dict(base[ref])
            r["why"] = f"auto (wr_fixes): {type_name} as Acropolis {ref}"
            return r
    return {"species": None, "why": f"auto (wr_fixes): {type_name} unknown, dropped"}


def _patch_replay_rules():
    import tools.wrcg.vegetation_replay as vr
    if getattr(vr.replay_types, "_wr", False):
        return
    orig = vr.replay_types

    class Auto(dict):
        def _fill(self, k):
            if not dict.__contains__(self, k):
                dict.__setitem__(self, k, _auto_rule(str(k)))

        def get(self, k, d=None):
            self._fill(k)
            return dict.get(self, k, d)

        def __contains__(self, k):
            self._fill(k)
            return True

        def __getitem__(self, k):
            self._fill(k)
            return dict.__getitem__(self, k)

    def replay_types(level):
        try:
            r = orig(level)
        except BaseException:
            r = None
        if r:
            return r
        print(f"{level}: no hand-made replay rules, WRCG types mapped by name (wr_fixes.AUTO_RULES)")
        return Auto()

    replay_types._wr = True
    vr.replay_types = replay_types


# --- start -----------------------------------------------------------------------------------------------------------

def start_pos_alias(slug):
    """The builder takes the start grid from the node named 'Start_Pos'; some levels prefix it (ES2_SS4_Start_Pos),
    and without it the stage started at s 0, 47 m before WRCG's grid, with the start marshal 8 m from the car."""
    p = WORK / "wrcg" / slug / "markers.json"
    if not p.exists():
        return
    m = json.loads(p.read_text(encoding="utf-8"))
    grid = m.get("grids_and_checkpoints", [])
    if any(x["name"] == "Start_Pos" for x in grid):
        return
    named = [x for x in grid if x["name"].endswith("_Start_Pos")]
    if len(named) != 1:
        return
    grid.insert(0, dict(named[0], name="Start_Pos"))
    p.write_text(json.dumps(m, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"    [{slug}] start grid: {named[0]['name']} used as Start_Pos (s {named[0].get('route_s_m')} m)")


# --- surface, tyres, weather (DT_TracksVariants / DT_Tracks) ---------------------------------------------------------

def _stage_cfgs():
    import tools.datafiles as df
    return [df.load_json(n) for n in df.names("stage_builds/*.json")]


def _surface(cfg):
    if cfg.get("acr_surface"):
        return cfg["acr_surface"]
    import tools.datafiles as df
    inv = df.load_json("wrcg_stage_inventory.json")
    st = next((s for s in inv["stages"] if s["id"] == cfg.get("stage_id")), None)
    import wr_stages
    return wr_stages.surface(st or {})


def _prop(row, name):
    return next((p for p in row["Value"] if p["Name"] == name), None)


def _set_ref_row(ref_struct, row):
    next(p for p in ref_struct["Value"] if p["Name"] == "Row")["Value"] = row


def _fix_variants(asset):
    by_row = {c.get("variant_row"): c for c in _stage_cfgs()}
    for row in asset["Exports"][0]["Table"]["Data"]:
        cfg = by_row.get(row["Name"])
        if cfg is None:
            continue
        surface = _surface(cfg)
        # ACR's own: tarmac stages TarmacSnow, gravel GravelOnly, snow (Livigno) FullSnow with the gravel car setup
        tyres = cfg.get("tyres") or {"Tarmac": "TarmacSnow", "Snow": "FullSnow"}.get(surface, "GravelOnly")
        setup = cfg.get("car_setup") or ("Gravel" if surface == "Snow" else surface)
        # The suggested compound: ACR has no default tyre per stage; its compounds carry the track degradation they are
        # meant for (DT_TireCompounds: TarmacSoft Low, TarmacMedium Medium, TarmacHard High) and every stock stage, like
        # the Hafren rows ours are cloned from, is Medium. Owner 2026-11-12: "haz que los neumáticos por defecto sean
        # los de asfalto seco blandos" -> "tyre_degradation": "Low" (it also means less tyre wear on the stage).
        deg = cfg.get("tyre_degradation")
        if deg and _prop(row, "DegradationLevel"):
            _set_ref_row(_prop(row, "DegradationLevel"), deg)
            # every stock row is Medium: "Low" is not in the table's name map (UaTool could not write it, 2026-11-12)
            _add_names(asset, _prop(row, "DegradationLevel"))
        st = _prop(row, "SurfaceTypes")
        if st and st["Value"]:
            key, share = st["Value"][0]
            _set_ref_row(key, surface)
            share["Value"] = 100.0
            st["Value"] = st["Value"][:1]
        _set_ref_row(_prop(row, "CarSetupDefaultSurfaceType"), setup)
        _set_ref_row(_prop(row, "TireCompounds"), tyres)
        img = _IMAGES.get(cfg.get("name")) or {}
        import wr_images
        for field, slot in (("VariantImage", "card"), ("LobbyVariantImage", "lobby")):
            if slot in img and _prop(row, field):
                wr_images.set_ref(asset, _prop(row, field), img[slot])
        for sector in (_prop(row, "Sectors") or {"Value": []})["Value"]:
            s = next((p for p in sector["Value"] if p["Name"] == "SurfaceType"), None)
            if s:
                _set_ref_row(s, surface)
        print(f"    [{cfg['slug']}] {row['Name']}: surface {surface}, car setup {setup}, tyres {tyres}"
              + (f", track degradation {deg}" if deg else ""))


def _fix_tracks(asset):
    by_track = {c.get("name"): c for c in _stage_cfgs()}
    for row in asset["Exports"][0]["Table"]["Data"]:
        cfg = by_track.get(row["Name"])
        if cfg is None:
            continue
        img = _IMAGES.get(row["Name"]) or {}
        if "background" in img:
            import wr_images
            for field in ("TrackImage", "LobbyTrackImage"):
                if _prop(row, field):
                    wr_images.set_ref(asset, _prop(row, field), img["background"])
        if cfg.get("weather_distribution"):
            _set_ref_row(_prop(row, "WeatherTypesDistribution"), cfg["weather_distribution"])
        if cfg.get("air_temperature_c") is not None:
            _prop(row, "OptimalAirTemperature")["Value"] = float(cfg["air_temperature_c"])
        if cfg.get("weather_distribution") or cfg.get("air_temperature_c") is not None:
            print(f"    [{cfg['slug']}] {row['Name']}: weather {cfg.get('weather_distribution')}, "
                  f"air {cfg.get('air_temperature_c')} C")


def _patch_physmat_wood():
    """ACR build 26756580 (2026-11-19) changed DMPhysicalMaterial: with the core's usmap (build 25170642) the stock wood material reads as a
    RawExport and custom_physmat.build_wood fails ('string indices must be integers'). Fallback: the stock material as it is (the wood
    props keep ACR's own friction). A stopgap until the core knows the new build."""
    import tools.acrmod.custom_physmat as cp
    if getattr(cp.build_wood, "_wr_fallback", False):
        return
    orig = cp.build_wood

    def build_wood(content_root, *a, **k):
        try:
            return orig(content_root, *a, **k)
        except TypeError as e:
            print(f"    physical material wood: the core cannot edit it with this game build ({e}); using ACR's own, unchanged")
            import tempfile
            from pathlib import Path
            j = cp._clone_json("PM_GuardrailWoodHF", cp.WOOD)
            out = Path(content_root) / (cp.WOOD[len("/Game/"):] + ".uasset")
            out.parent.mkdir(parents=True, exist_ok=True)
            cp.write_asset(j, Path(tempfile.mkdtemp(prefix="wr_pmw_")) / "PM_WrcgWood.json", out)
            return cp.WOOD
    build_wood._wr_fallback = True
    cp.build_wood = build_wood
    orig_map = cp.build_mapping

    def build_mapping(content_root, *a, **k):          # the same for the mapping table (it only adds our wood material to ACR's)
        try:
            return orig_map(content_root, *a, **k)
        except TypeError as e:
            print(f"    physical materials mapping: the core cannot edit it with this game build ({e}); using ACR's own, unchanged")
            import tempfile
            from pathlib import Path
            j = cp._clone_json("DA_PhysMaterialsMappingCommon", cp.MAPPING)
            out = Path(content_root) / (cp.MAPPING[len("/Game/"):] + ".uasset")
            out.parent.mkdir(parents=True, exist_ok=True)
            cp.write_asset(j, Path(tempfile.mkdtemp(prefix="wr_pmm_")) / "DA_WrcgPhysMaterialsMapping.json", out)
            _append_mapping_wood(out)
            return cp.MAPPING
    cp.build_mapping = build_mapping


def _append_mapping_wood(uasset):
    """Levels baked before the 26756580 update index our wood material as the entry after ACR's 44 (the game crashed with 'surfaceDefs.size()'
    otherwise): append PM_WrcgWood to the mapping, edited with the new usmap (bin/acr_26756580.usmap)."""
    import json, subprocess, tempfile, copy
    from pathlib import Path
    tool, usmap = WORK.parent / "bin" / "uatool" / "UaTool.exe", WORK.parent / "bin" / "acr_26756580.usmap"
    if not (tool.exists() and usmap.exists()):
        print("    physical materials mapping: bin/acr_26756580.usmap missing, wood entry not appended")
        return
    tmp = Path(tempfile.mkdtemp(prefix="wr_pmm_")) / "m.json"
    subprocess.run([str(tool), "dumpjson", str(uasset), str(usmap), str(tmp)], check=True, capture_output=True)
    j = json.loads(tmp.read_text(encoding="utf-8"))
    pm = j["Exports"][0]["Data"][0]["Value"]
    if len(pm) != 44:
        print(f"    physical materials mapping: {len(pm)} entries (expected 44), wood entry not appended")
        return
    im, names = j["Imports"], j["NameMap"]
    src = next(x for x in im if x.get("ObjectName") == "PM_GuardrailWoodHF")          # PM_WrcgWood is a clone of it: same import, our path
    pkg_path = "/Game/Environments/WrcgShared/PhysicalMaterials/PM_WrcgWood"
    pkg = dict(im[-src["OuterIndex"] - 1], ObjectName=pkg_path)
    im.append(pkg)
    im.append(dict(src, ObjectName="PM_WrcgWood", OuterIndex=-len(im)))
    names += [n for n in (pkg_path, "PM_WrcgWood") if n not in names]
    e = copy.deepcopy(pm[0])
    e["Name"], e["ArrayIndex"], e["Value"] = str(len(pm)), len(pm), -len(im)
    pm.append(e)
    tmp.write_text(json.dumps(j), encoding="utf-8")
    subprocess.run([str(tool), "fromjson", str(tmp), str(usmap), str(uasset)], check=True, capture_output=True)
    print("    physical materials mapping: wood entry appended (45 entries)")


def _patch_tables():
    import tools.acrmod.stagepack as sp
    if getattr(sp.write_asset, "_wr", False):
        return
    orig = sp.write_asset

    def write_asset(json_obj, tmp_json, out_uasset):
        name = Path(str(out_uasset)).stem
        if name == "DT_TracksVariants":
            _fix_variants(json_obj)
        elif name == "DT_Tracks":
            _fix_tracks(json_obj)
            try:
                import wr_penalty
                if wr_penalty.write_table(orig, WORK / "acr", next(q for q in Path(str(out_uasset)).parents if q.name == "Content")):
                    print(f"    penalty table written: PropsCollision {wr_penalty.PENALTY_S:g} s in Free Practice")
            except Exception as e:
                print(f"    penalty table: not written ({type(e).__name__}: {e})")
        elif name in LOCATION_TABLES and _LOCATIONS:
            _fix_location_table(name, json_obj)
        return orig(json_obj, tmp_json, out_uasset)

    write_asset._wr = True
    sp.write_asset = write_asset
    _patch_locations()


# --- one ACR location per country ("Imported Spain", "Imported Greece", ...) ------------------------------------------

# The tool puts every stage in one new location (row WrcgTest, "WRCG Imported Stages", country Italy). Owner 2026-11-09:
# a location per country instead. stagepack.patch makes each new location from the stock tables, and with two new
# locations the second write of the logo and background tables lost the first one's row; the three location tables
# are therefore completed here as they are written: rows made by earlier writes are kept, a Wrcg* row of a location no
# stage uses (a leftover) is dropped, and each location lists its stages (default variant and surface of its first).
LOCATION_TABLES = ("DT_TracksLocations", "DT_TracksLocationsLogos", "DT_TracksLocationsBackgrounds")
_LOCATIONS = {}          # location row -> [(track row, variant row, surface)]
_IMAGES = {}             # track row -> {slot: DT_TracksTextures row} (wr_images)
_LOCATION_TITLES = {}    # location row -> its title
LOCATION_DESCRIPTION = "Stages imported from WRC Generations. Free Practice only."
_LOCATION_ROWS = {}      # table -> {row name: row json} written so far


def _country(cfg):
    import tools.datafiles as df
    inv = df.load_json("wrcg_stage_inventory.json")["stages"]
    st = next((s for s in inv if s["id"] == cfg.get("stage_id")), None)
    if st is None:
        st = next((s for s in inv if s.get("location_folder") == cfg.get("wrcg_level")), {})
    import wr_stages
    return wr_stages.country_name(st.get("country_en")) or "Imported"


def location_of(cfg):
    """(row, title, ACR country row) of a stage build. 'location' in the stage build overrides the country."""
    country = cfg.get("location") or _country(cfg)
    key = "".join(w for w in country.split())
    return "Wrcg" + key, f"[MOD] {country}", cfg.get("location_country") or key


def _patch_locations():
    import tools.acrmod.stagepack as sp
    import wr_images
    if getattr(sp.patch, "_wr", False):
        return
    orig = sp.patch

    def patch(stages, out_legacy, *a, **k):
        import wr_images
        by_track = {c.get("name"): c for c in _stage_cfgs()}
        _LOCATIONS.clear()
        _LOCATION_ROWS.clear()
        _IMAGES.clear()
        for st in stages:
            cfg = by_track.get(st.track_row)
            if cfg is None:
                continue
            # names from the stage build as it is now (a stage reused from the cache carries the names of its build)
            if cfg.get("track_name"):
                st.track_name = cfg["track_name"]
            if cfg.get("stage_name") and st.variants:
                st.variants[0].stage_name = cfg["stage_name"]
            row, title, country = location_of(cfg)
            st.location_row, st.location_title, st.location_country = row, title, country
            st.location_description = wr_images.location_text(row) or LOCATION_DESCRIPTION
            _LOCATION_TITLES[row] = title
            st.new_location = row not in _LOCATIONS
            _LOCATIONS.setdefault(row, []).append((st.track_row, st.variants[0].row if st.variants else None,
                                                   _surface(cfg)))
        if _LOCATIONS:
            print("    locations: " + "; ".join(f"{r} ({', '.join(t for t, _, _ in v)})" for r, v in _LOCATIONS.items()))
        _IMAGES.update(wr_images.write_stage_images(
            out_legacy, [(st.track_row, by_track[st.track_row]["slug"]) for st in stages if st.track_row in by_track]))
        return orig(stages, out_legacy, *a, **k)

    patch._wr = True
    sp.patch = patch
    orig_card = sp._card_image

    def card_image(out_legacy, tmp, table, row, image_rel, tex_name, *a, **k):
        """A location's own logo / background (custom/images/<location row>/), in a texture of its own."""
        import tools._embedded as em
        import tools.datafiles as df
        slot = {"Logos": "logo", "Backgrounds": "background"}.get(table)
        src = wr_images.find(wr_images.IMAGES / row, slot) if slot else None
        if slot:                                   # its own image, else ours ('Imported <Country>'), never the tool's
            image_rel = f"ui/wr_{row}_{slot}.png"
            data = wr_images.png_bytes(src, wr_images.LOC_SLOTS[slot]) if src is not None else                 wr_images.default_location_png(slot, _LOCATION_TITLES.get(row, row))
            em.DATA[image_rel] = df.scramble(data)
            tex_name = f"T_{row}{'Logo' if slot == 'logo' else 'Background'}"
            print(f"    menu images: {row} {slot} ({'own' if src is not None else 'default'})")
        return orig_card(out_legacy, tmp, table, row, image_rel, tex_name, *a, **k)

    card_image._wr = True
    sp._card_image = card_image


_NAME_KEYS = ("Name", "StructType", "ArrayType", "InnerType", "EnumType", "PropertyTypeName")


def _add_names(asset, obj):
    names, nm = set(), asset["NameMap"]

    def walk(o):
        if isinstance(o, dict):
            for k in _NAME_KEYS:
                v = o.get(k)
                if isinstance(v, str) and v and " " not in v and not v.startswith("{"):
                    names.add(v)
            if "NamePropertyData" in str(o.get("$type", "")) and isinstance(o.get("Value"), str):
                names.add(o["Value"])
            if "FTopLevelAssetPath" in str(o.get("$type", "")):       # soft paths are names too (the default logo
                for k in ("PackageName", "AssetName"):                 # of a location carried into another's write)
                    if isinstance(o.get(k), str):
                        names.add(o[k])
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    walk(obj)
    # UE5 packages: the export data may only use the first NamesReferencedFromExportDataCount names; appended after it
    # they made ACR stop at start-up ("DT_TracksLocationsLogos: Bad name index 36/35", owner 2026-11-09). A name the
    # carried rows need goes into that range (moved there if it is past it) and the count grows with it.
    count = asset.get("NamesReferencedFromExportDataCount")
    if not isinstance(count, int) or not 0 <= count <= len(nm):
        have = set(nm)
        nm.extend(sorted(n for n in names if n not in have))
        return
    for n in sorted(names):
        if n in nm[:count]:
            continue
        if n in nm:
            nm.remove(n)
        nm.insert(count, n)
        count += 1
    asset["NamesReferencedFromExportDataCount"] = count


def _fix_location_table(name, asset):
    import copy
    rows = asset["Exports"][0]["Table"]["Data"]
    seen = _LOCATION_ROWS.setdefault(name, {})
    for r in rows:
        if r["Name"] in _LOCATIONS:
            seen[r["Name"]] = copy.deepcopy(r)
    keep = [r for r in rows if not r["Name"].startswith("Wrcg") or r["Name"] in _LOCATIONS]
    have = {r["Name"] for r in keep}
    carried = [copy.deepcopy(r) for n, r in seen.items() if n not in have]
    keep += carried
    for r in carried:                                       # their names must be in this asset's name map
        _add_names(asset, r)
    if name == "DT_TracksLocations":
        for r in keep:
            if r["Name"] not in _LOCATIONS:
                continue
            tracks = _LOCATIONS[r["Name"]]
            tp = _prop(r, "Tracks")
            if tp and tp["Value"]:
                proto = tp["Value"][0]
                items = []
                for i, (track, _, _) in enumerate(tracks):
                    it = copy.deepcopy(proto)
                    it["Name"] = str(i)
                    _set_ref_row(it, track)
                    items.append(it)
                tp["Value"] = items
            dv = _prop(r, "DefaultVariant")
            if dv and tracks[0][1]:
                _set_ref_row(dv, tracks[0][1])
            sd = _prop(r, "SurfaceTypesData")
            if sd and sd["Value"]:
                s = next((p for p in sd["Value"][0]["Value"] if p["Name"] == "SurfaceType"), None)
                if s:
                    _set_ref_row(s, tracks[0][2])
                sd["Value"] = sd["Value"][:1]
    dropped = len(rows) - len([r for r in rows if not r["Name"].startswith("Wrcg") or r["Name"] in _LOCATIONS])
    asset["Exports"][0]["Table"]["Data"] = keep
    if dropped or len(keep) != len(rows):
        print(f"    {name}: {', '.join(n for n in _LOCATIONS)} ({dropped} old row(s) dropped)")


# --- spectators ------------------------------------------------------------------------------------------------------

def _start_arch_m(slug):
    """Route metre (from the route start) of the stage's own start arch (WRCG prop ARCH_START_*, within 12 m of the road and
    40 m of the start): the countdown marshal stands in line with it (owner 2026-11-18). None when there is none."""
    import re
    import numpy as np
    import tools.acrmod.build_stage as bs
    import tools.wrcg.prop_instances as pi
    cfg = bs.load_cfg(slug)
    R = np.asarray(bs.route_wrcg(cfg), float)
    s = np.r_[0.0, np.cumsum(np.hypot(*np.diff(R[:, :2], axis=0).T))]
    collect = getattr(pi.collect_instances, "__wrapped_orig__", None) or pi.collect_instances
    import wr_skinned
    props, _ = collect(cfg["wrcg_level"], ("static", "dynamic", "clutter", "spline", "decor"), route_xy=R[:100, :2], near_m=60.0,
                       stage_mask=wr_skinned.stage_mask(cfg.get("stage_id")))
    best = None
    for p in props:
        if not re.match(r"ARCH_START", str(p.psi_name)):
            continue
        t = np.asarray(p.world)[:3, 3]
        d = np.hypot(R[:, 0] - t[0], R[:, 1] - t[1])
        j = int(d.argmin())
        if d[j] <= 12.0 and 0.0 <= s[j] <= 40.0 and (best is None or s[j] < best):
            best = float(s[j])
    return None if best is None else round(best, 1)


START_MARSHAL_BACK_M = 1.5     # the marshal stands this far toward the car from the start arch (owner 2026-11-19: he touched the giant WRC sign)
START_BOX_GAP_M = 3.5          # the red box (BC_StartSequenceTrigger, where the car stops) this far before the marshal; Greece SS3 verified


def _start_box(dst, route_cm, shift_m, slug, marshal_s_m=None):
    """The level's start-sequence actors (the red box where the car stops). Universal: BC_StartSequenceTrigger and
    BC_CompleStartTargetPoint go to START_BOX_GAP_M before the marshal (never back: a shift is clamped to 0..10 m); the stage
    build "start_box_shift_m" gives the metres by hand (0 = stays). BC_PlayerStartsManager stands elsewhere: only logged."""
    import re
    import numpy as np
    R = np.asarray(route_cm, float)
    found = []
    for i in range(1, len(dst.exports) + 1):
        cn = dst.class_name(i)
        if not re.search(r"StartSequenceTrigger|CompleStartTarget|PlayerStartsManager", cn or ""):
            continue
        e = dst.exp(i)
        root = next((p for p in e.get("Data") or [] if p.get("Name") == "RootComponent"), None)
        comp = dst.exp(root["Value"]) if root and isinstance(root.get("Value"), int) and root["Value"] > 0 else None
        loc = next((p for p in (comp or {}).get("Data") or [] if p.get("Name") == "RelativeLocation"), None)
        if loc is None:
            print(f"    [{slug}] start box: {cn} has no RelativeLocation")
            continue
        v = loc["Value"][0]["Value"]
        x, y, z = float(v["X"]), float(v["Y"]), float(v["Z"])
        k = int(np.argmin(np.hypot(R[:, 0] - x, R[:, 1] - y)))
        k2 = next((j for j in range(k + 1, len(R)) if np.hypot(*(R[j, :2] - R[k, :2])) >= 200.0), len(R) - 1)
        s_m = float(np.sum(np.hypot(*np.diff(R[:k + 1, :2], axis=0).T))) / 100.0 if k else 0.0
        print(f"    [{slug}] start box: {cn} at ({x / 100:.1f}, {y / 100:.1f}, {z / 100:.1f}) m, route m {s_m:.1f} of the pre-start route")
        found.append((cn, v, x, y, R[k2, :2] - R[k, :2], s_m))
    if shift_m is None:
        trig = next((f for f in found if "StartSequenceTrigger" in f[0]), None)
        shift_m = 0.0 if trig is None or marshal_s_m is None else float(np.clip(marshal_s_m - START_BOX_GAP_M - trig[5], 0.0, 10.0))
    for cn, v, x, y, d, _ in found:
        if shift_m and "PlayerStartsManager" not in cn:
            d = d / max(float(np.hypot(*d)), 1e-6)
            v["X"], v["Y"] = x + d[0] * shift_m * 100.0, y + d[1] * shift_m * 100.0
            print(f"    [{slug}] start box: {cn} moved {float(shift_m):+.2f} m along the road")


def _patch_crowd():
    import tools.acrmod.start_marshal as sm
    if getattr(sm.add_start_marshal, "_wr", False):
        return
    orig = sm.add_start_marshal

    def add_start_marshal(dst, hs_persistent, route_cm, s_trigger_cm, spawn_cm):
        import tools.acrmod.stagectx as sc
        cfg = _cfg(sc.cur().slug) or {}
        m = cfg.get("start_marshal_m")      # explicit metre; else the stage's own start arch (universal), "start_marshal_m": false = the core's 8 m
        if m is None:
            try:
                m = _start_arch_m(sc.cur().slug)
                m = None if m is None else max(m - START_MARSHAL_BACK_M, 8.0)    # never nearer than the core's 8 m: the red box stands at route m 5, 3 m before it
            except Exception as e:
                print(f"    [{sc.cur().slug}] start arch not found ({type(e).__name__}: {e}): marshal left at the core's 8 m")
        if m is not None and m is not False:       # the core puts him 8 m after the route start (= Seyabei's arch ARCH_START_KE); the stage's own arch may be elsewhere
            s_trigger_cm += (float(m) - 8.0) * 100.0
            print(f"    [{sc.cur().slug}] start marshal at route m {float(m):g} (the core's 8 m moved to the start arch)")
        out = orig(dst, hs_persistent, route_cm, s_trigger_cm, spawn_cm)
        try:
            _start_box(dst, route_cm, cfg.get("start_box_shift_m"), sc.cur().slug,
                       marshal_s_m=(s_trigger_cm + sm.AFTER_TRIGGER_M * 100.0) / 100.0)
        except Exception as e:
            print(f"    [{sc.cur().slug}] start box: not handled ({type(e).__name__}: {e})")
        _add_crowd(dst)
        dst._wr_hs = hs_persistent        # source of the RVT volume, used when the level is saved
        return out

    add_start_marshal._wr = True
    sm.add_start_marshal = add_start_marshal


def _add_crowd(dst):
    import numpy as np
    import tools.acrmod.build_stage as bs
    import tools.acrmod.ittiri_ground as ig
    import tools.acrmod.props_visual as pv
    import tools.acrmod.stagectx as sc
    import tools.acrmod.start_marshal as sm
    import wr_crowd
    slug = sc.cur().slug
    cfg = bs.load_cfg(slug)
    if not cfg.get("crowd"):
        return
    tag = cfg.get("crowd_tag") or cfg["stage_id"].split("/")[-1]     # ES2_SPAIN/SS1's spectators are under SS3
    level = cfg["wrcg_level"]
    plm = WORK / "wrcg_fs" / "WIN32" / "LEVELS" / level / f"{level}.PLM"
    spots = wr_crowd.wrcg_spectators(plm, tag)
    if not spots and tag.endswith("R"):
        # WRCG's reverse stages have no spectators of their own (SS3R, SS4R, SS1R: none); those of the forward stage
        # stand along the same road and face it (owner 2026-11-10: "Riudecanyes y Savallà reverse sin público")
        spots = wr_crowd.wrcg_spectators(plm, tag[:-1])
        if spots:
            print(f"    [{slug}] crowd: none under {tag}, the forward stage's ({tag[:-1]}) taken")
    route = bs.route_wrcg(cfg)
    if cfg.get("auto_crowd"):                          # extra clusters at corners (wr_autocrowd.py)
        try:
            import wr_autocrowd
            d = np.load(WORK / "wrcg" / slug / "collision_extra.npz", allow_pickle=True)
            blockers = [(d["owner_bbox_min"][i][:2], d["owner_bbox_max"][i][:2]) for i in range(len(d["owner_psi"]))]
            extra, chosen = wr_autocrowd.auto_spots(np.asarray(route, float)[:, :3], [(p[0], p[1]) for _, p in spots],
                                                    blockers, cfg["auto_crowd"])
            spots = list(spots) + extra
            print(f"    [{slug}] auto crowd: {len(chosen)} clusters, {len(extra)} spectators at route m {[round(c) for c in sorted(chosen)]}")
        except Exception as e:
            print(f"    [{slug}] auto crowd: not added ({type(e).__name__}: {e})")
    if cfg.get("crowd_drop"):                         # [{"at": [x, y], "radius": r}] WRCG metres: spectators standing there are left out
        n0 = len(spots)
        def gone(q, r):                                   # {"at", "radius"} or {"box": [x0, y0, x1, y1], "zmin": z}
            if "box" in r:
                return r["box"][0] <= q[0] <= r["box"][2] and r["box"][1] <= q[1] <= r["box"][3] and q[2] >= float(r.get("zmin", -1e9))
            return float(np.hypot(q[0] - r["at"][0], q[1] - r["at"][1])) <= float(r.get("radius", 1.0))
        spots = [(g, q) for g, q in spots if not any(gone(q, r) for r in cfg["crowd_drop"])]
        print(f"    [{slug}] crowd_drop: {n0 - len(spots)} spectator spots left out")
    if not spots:
        print(f"    [{slug}] crowd: no WRCG spectator nodes under {tag}, skipped")
        return
    shift = bs.stage_shift(cfg, route)
    route_ue = pv.wrcg_world_to_ue(route, shift)
    spots_ue = pv.wrcg_world_to_ue(np.array([p for _, p in spots]), shift)
    try:                                              # hand-placed scene: its spectators (wr_scene.py)
        import wr_scene
        more = wr_scene.people_xyz(cfg)
        if more:
            spots_ue = np.vstack([spots_ue, pv.wrcg_world_to_ue(np.array(more), shift)])
            print(f"    [{slug}] scene: {len(more)} spectators added next to the parked vehicles")
    except Exception as e:
        print(f"    [{slug}] scene spectators: not added ({type(e).__name__}: {e})")
    each_ue = None                                    # "cone_each": true on a crowd_add entry = a penalty cone of its own for each person
    if cfg.get("crowd_add"):                          # [{"at": [x, y, z], "n": 4, "depth_m": 0.9, "spread_m": 0.9}] WRCG metres: a few spectators
        more, each = [], []                           # standing behind the tape / fence there, on the side away from the route
        R = np.asarray(route, float)
        for r in cfg["crowd_add"]:
            c = np.asarray(r["at"], float)
            j = int(np.hypot(R[:, 0] - c[0], R[:, 1] - c[1]).argmin())
            away = c[:2] - R[j, :2]
            away = away / max(float(np.hypot(*away)), 1e-6)
            tang = np.array([-away[1], away[0]])
            n = int(r.get("n", 4))
            for k in range(n):
                off = (k - (n - 1) / 2) * float(r.get("spread_m", 0.9))
                q = c[:2] + away * (float(r.get("depth_m", 0.9)) + 0.3 * (k % 2)) + tang * off
                more.append([q[0], q[1], c[2]])
                if r.get("cone_each"):
                    each.append(more[-1])
        spots_ue = np.vstack([spots_ue, pv.wrcg_world_to_ue(np.array(more), shift)])
        if each:
            each_ue = pv.wrcg_world_to_ue(np.array(each), shift)
        print(f"    [{slug}] crowd_add: {len(more)} spectators placed by hand")
    if cfg.get("tape_posts") and cfg.get("wrcg_tape_post_physics") is False:  # optional old wood-post replacement
        try:
            import tools.wrcg.prop_instances as pi
            import wr_skinned
            import wr_tapeposts
            o = wr_tapeposts.options(cfg)
            collect = getattr(pi.collect_instances, "__wrapped_orig__", None) or pi.collect_instances
            r_xy = np.asarray(route, float)[:, :2]
            insts, _ = collect(level, ("static", "dynamic", "clutter", "spline", "decor"), route_xy=r_xy,
                               near_m=o["near_m"] + 20.0, stage_mask=wr_skinned.stage_mask(cfg.get("stage_id")))
            pts = wr_tapeposts.stick_points(insts, r_xy, o["near_m"], int(o["max"]))
            if pts:
                ue = pv.wrcg_world_to_ue(np.array([q[:3] for q in pts]), shift)
                wr_tapeposts.prepare(WORK / "acr", os.environ["WRCG2ACR_ACR_PAKS"])
                wr_tapeposts.add(dst, WORK / "acr", [(u[0], u[1], q[3]) for u, q in zip(ue, pts)], ig.make_ground_fn(shift),
                                 o["mesh"], log=lambda s: print(f"    [{cfg['name']}] {s.strip()}"))
        except Exception as e:
            print(f"    [{slug}] tape posts: not added ({type(e).__name__}: {e})")
    if cfg.get("support_vehicles"):                   # ACR's ambulance / security car / van behind the crowd (wr_support.py)
        try:
            import wr_support
            plan = wr_support.places(spots_ue, route_ue, cfg["support_vehicles"])
            wr_support.prepare(WORK / "acr", os.environ["WRCG2ACR_ACR_PAKS"], {k for k, _, _ in plan})
            wr_support.add(dst, WORK / "acr", plan, ig.make_ground_fn(shift), log=lambda s: print(f"    [{cfg['name']}] {s.strip()}"))
        except Exception as e:
            print(f"    [{slug}] support vehicles: not added ({type(e).__name__}: {e})")
    if cfg.get("crowd_penalty"):                      # hidden CurveCut cones in front of the crowd (wr_penalty.py)
        try:
            import wr_penalty
            wr_penalty.prepare(WORK / "acr", os.environ["WRCG2ACR_ACR_PAKS"])
            cones = wr_penalty.cone_points(spots_ue, route_ue)
            if each_ue is not None:
                cones = np.vstack([cones, wr_penalty.cone_points(each_ue, route_ue, cell_m=0.5)])
            wr_penalty.add_cones(dst, WORK / "acr", cones, ig.make_ground_fn(shift),
                                 log=lambda s: print(f"    [{cfg['name']}] {s.strip()}"))
        except Exception as e:
            print(f"    [{slug}] crowd penalty: not added ({type(e).__name__}: {e})")
    wr_crowd.add_crowd(dst, sm.MARSHAL_CELL_SRC, spots_ue, route_ue, ig.make_ground_fn(shift),
                       log=lambda s: print(f"    [{cfg['name']}] {s.strip()}"),
                       prefix=f"{cfg['name']}Crowd")


# --- ground cover materials (RVT) ------------------------------------------------------------------------------------

def _patch_ground_cover_materials():
    import tools.acrmod.vegetation_visual as vv
    if getattr(vv.add_hism_actor, "_wr", False):
        return
    orig = vv.add_hism_actor

    import re
    import wr_groundcover
    # the builder tilts aligned instances by at most 12 deg; grass on steeper banks then floats on the downhill side
    vv.MAX_TILT_DEG = wr_groundcover.MAX_TILT_DEG          # the ground cover is laid on the ground up to this tilt

    def add_hism_actor(dst, tmpl, *a, **k):
        import tools.acrmod.stagectx as sc
        import wr_perf
        n0 = len(dst.exports)
        name = str(k.get("name", a[0] if a else ""))
        species = re.sub(r"_\d+(_c\d+)?$", "", name[len(VEG_PREFIX):]) if name.startswith(VEG_PREFIX) else None
        perf = _on(sc.cur().slug, "veg_perf")               # "veg_perf": false = the vegetation as the core builds it (no wr_perf cull / shadow / DFL changes)
        if perf:
            k = wr_perf.veg_kwargs(species, k)              # ground cover: cull distance, no shadows (wr_perf.py)
        visibility_tuning = species in wr_perf.TREE_VISIBILITY_SPECIES | {"shrub"} and _on(sc.cur().slug, "tree_visibility_tuning")
        if visibility_tuning and species in wr_perf.TREE_VISIBILITY_SPECIES:
            k["cull_cm"] = 0.0
        elif visibility_tuning and (k.get("cull_cm") or 0) > 0:
            k["cull_cm"] *= 1.25
        out = orig(dst, tmpl, *a, **k)
        if perf:
            wr_perf.veg_after(dst, n0, species)
        if visibility_tuning and species in wr_perf.TREE_VISIBILITY_SPECIES and out.get("hism"):
            wr_perf.extend_tree_visibility(dst, out["hism"], species)
        mesh = str(k.get("mesh") or "").split(".")[0]
        mats = wr_groundcover.MATERIALS.get(species) or wr_groundcover.MESH_MATERIALS.get(mesh) or \
            _snow_tree_materials(k.get("mesh")) or _far_tree_materials(k.get("mesh")) or _stone_materials(k.get("mesh"))
        if mats and any("_RVT_" in m for m in mats):         # universal: lighter grass (wr_grasslight.py), "grass_light": false = off
            try:
                import tools.acrmod.stagectx as sc
                import wr_grasslight
                slug = sc.cur().slug
                cfg = _cfg(slug) or {}
                opts = wr_grasslight.options(cfg)
                legacy = next(iter(sorted((WORK / "acr" / "mods").glob(f"*/stages/{slug}/legacy"))), None)
                if opts and legacy is not None:
                    mats = wr_grasslight.materials_for(mats, opts, cfg["name"], legacy)
            except Exception as e:
                print(f"    grass light: stock materials kept ({type(e).__name__}: {e})")
        if mats:
            import wr_rvt
            tmpl_p = json.loads(wr_rvt.PROP_RVT.read_text())
            idx = [dst.ensure_import(wr_rvt._key(m, "MaterialInstanceConstant")) for m in mats]
            for i in range(n0 + 1, len(dst.exports) + 1):
                if "InstancedStaticMeshComponent" in dst.class_name(i):
                    p = wr_rvt._obj_array("OverrideMaterials", idx[0], tmpl_p)
                    p["Value"] += [dict(p["Value"][0], Name=str(j), Value=v) for j, v in enumerate(idx[1:], 1)]
                    wr_rvt._set(dst.exp(i), p)
                    dst.add_name("OverrideMaterials")
        return out

    add_hism_actor._wr = True
    vv.add_hism_actor = add_hism_actor


def _stage_surfaces(slug):
    """'surface_overrides' {WRCG surface: ACR physical material} of a stage build, for its own build process only.
    Arganil (owner 2026-11-10): its cobbles (PAVE, s 6575-6879 m in the fourth sector) as the most slippery tarmac-type
    surface ACR has, PM_SurfaceConcrete (SurfaceType ST_KERB, WearMultiplier 2); ACR's PM_SurfaceCobblestones is
    ST_SNOW and drove like snow on Riudecanyes. The asphalt of its last sector (TARMAC2) stays PM_SurfaceTarmacSmooth."""
    ov = (_cfg(slug) or {}).get("surface_overrides")
    if not ov:
        return
    import tools._embedded as em
    import tools.datafiles as df
    sm = df.load_json("wrcg_surface_map.json")
    for row in sm["map"]:
        if row.get("surface") in ov:
            row.update(acr_physmat=ov[row["surface"]], confidence="stage override")
    em.DATA["wrcg_surface_map.json"] = df.scramble(json.dumps(sm, ensure_ascii=False).encode("utf-8"))
    print(f"    [{slug}] surfaces: " + ", ".join(f"{k} -> {v}" for k, v in ov.items()))


def _patch_solid_props():
    """'solid_props' [psi name parts] of a stage build: those WRCG props keep their collision. The builder leaves out
    light dynamic props (movable in WRCG, mass under 50 kg or unknown), so Arganil's white plastic hay bales protecting
    the last sector (CMN_PLASTIC_WHITE_HAYBALL_DIRT, mass 0) could be driven through (owner 2026-11-10: "no olvides los
    bolardos blancos de protección"). Static in ACR, PM_WallPlasticBarrier (impact sound)."""
    import tools.acrmod.ittiri_container as ic
    if getattr(ic.extra_meshes, "_wr", False):
        return
    orig = ic.extra_meshes

    def extra_meshes(offset=(0.0, 0.0, 0.0), *a, **k):
        import inspect
        import tools.acrmod.stagectx as sc
        drop = tuple((_cfg(sc.cur().slug) or {}).get("drop_psi") or ())       # "drop_psi": no collision for those props either
        if drop:
            k["exclude"] = tuple(k.get("exclude") or inspect.signature(orig).parameters["exclude"].default) + drop
        out = orig(offset, *a, **k)
        cats = k.get("categories", a[0] if a else (0, 1, 2))
        try:
            import numpy as np
            import tools.acrmod.stagectx as sc
            slug = sc.cur().slug
            words = [w.upper() for w in (_cfg(slug) or {}).get("solid_props") or []]
            if not words or 2 not in tuple(cats):
                return out
            d = np.load(WORK / "wrcg" / slug / "collision_extra.npz", allow_pickle=True)
            own = [i for i, p in enumerate(d["owner_psi"]) if any(w in str(p).upper() for w in words)]
            mask = np.isin(d["tri_piece"], own)
            if not mask.any():
                return out
            pm, names, surf = ic.surface_to_pm(), d["surface_names"], d["tri_surface"]

            def pm_for(tris):
                vals, cnt = np.unique(surf[tris], return_counts=True)
                p = pm.get(str(names[vals[cnt.argmax()]]), "")
                return p if "Wall" in p else "PM_WallPlasticBarrier"

            extra = ic._meshes_from(d, mask, offset, "WrcgSolidProp", pm_for)
            print(f"    solid props: {len(own)} {'/'.join(words)} props kept as obstacles ({int(mask.sum())} triangles, "
                  f"{len(extra)} meshes)")
            return list(out) + list(extra)
        except Exception as e:
            print(f"    solid props: not added ({type(e).__name__}: {e})")
            return out

    def with_graph(offset=(0.0, 0.0, 0.0), *a, **k):
        out = extra_meshes(offset, *a, **k)
        cats = k.get("categories", a[0] if a else (0, 1, 2))
        try:
            import tools.acrmod.stagectx as sc
            slug = sc.cur().slug
            if 2 in tuple(cats) and ((_cfg(slug) or {}).get("graph_props_solid") or (_cfg(slug) or {}).get("rocks") or (_cfg(slug) or {}).get("solid_by_name")):
                out = list(out) + _graph_collision(slug, offset)
        except Exception as e:
            print(f"    graph props: no collision added ({type(e).__name__}: {e})")
        try:
            import tools.acrmod.stagectx as sc
            import tools.acrmod.build_stage as bs
            import tools.acrmod.ittiri_container as ic
            import wr_fencerow
            slug = sc.cur().slug
            if 2 in tuple(cats) and wr_fencerow.options(_cfg(slug) or {}):
                d = wr_fencerow.panel_collision(_cfg(slug), bs.route_wrcg(bs.load_cfg(slug)))
                if d is not None:
                    out = list(out) + list(ic._meshes_from(d, __import__("numpy").ones(len(d["triangles"]), bool), offset, "WrcgFencePanel",
                                                           lambda t: "PM_WallBasic"))
                    print(f"    fence panels: collision for {len(d['triangles']) // 12} static panels")
        except Exception as e:
            print(f"    fence panels: no collision added ({type(e).__name__}: {e})")
        try:
            import tools.acrmod.stagectx as sc
            if 2 in tuple(cats):
                out = list(out) + _tyre_collision(sc.cur().slug, offset)
        except Exception as e:
            print(f"    tyre stacks: no collision added ({type(e).__name__}: {e})")
        try:
            import tools.acrmod.stagectx as sc
            if 2 in tuple(cats) and _on(sc.cur().slug, "fence_solid"):
                out = list(out) + _fence_collision(sc.cur().slug, offset)
        except Exception as e:
            print(f"    wire fences: no collision added ({type(e).__name__}: {e})")
        try:
            import tools.acrmod.stagectx as sc
            if 2 in tuple(cats) and _on(sc.cur().slug, "rock_solid"):
                out = list(out) + _rock_collision(sc.cur().slug, offset)
        except Exception as e:
            print(f"    rocks: no collision added ({type(e).__name__}: {e})")
        try:
            import tools.acrmod.stagectx as sc
            if 2 in tuple(cats) and _on(sc.cur().slug, "tree_solid"):
                out = list(out) + _tree_collision(sc.cur().slug, offset)
        except Exception as e:
            print(f"    trees: no collision added ({type(e).__name__}: {e})")
        try:
            import tools.acrmod.stagectx as sc
            if 2 in tuple(cats) and _on(sc.cur().slug, "net_solid"):
                out = list(out) + _net_collision(sc.cur().slug, offset)
        except Exception as e:
            print(f"    nets: no collision added ({type(e).__name__}: {e})")
        try:
            import tools.acrmod.stagectx as sc
            if 2 in tuple(cats):
                out = list(out) + _pole_collision(sc.cur().slug, offset)
        except Exception as e:
            print(f"    posts and signs: no collision added ({type(e).__name__}: {e})")
        return out

    with_graph._wr = True
    ic.extra_meshes = with_graph


# Props of the stage's own WRCG graph left out by the builder. The builder takes the props of the stage's selective-load
# group (stage_mask: Riudecanyes 256); part of the stage's own graph (SS3/ES2_SS3_GRAPHS, where its spectators are) is
# not in that group: on Riudecanyes 172 props within 60 m, among them the straw bales of the roundabouts (ES_HAYSTACK
# s 5962-6006, owner 2026-11-10: "unos bolardos de paja en la parte final del tramo que desaparecieron"), the white
# plastic ones (s 5866-5910), the dam railing (DAM_RAILING, 73) and six castle wall pieces whose collision was there
# but not the wall. "graph_props": {"tag": <graph tag>, "names": [psi name parts] or all, "near_m"} adds them;
# "graph_props_solid": [psi name parts] gives those a collision built from their LOD0 mesh (WRCG has none for them in
# the stage, they are not in its collision export either).
GRAPH_PM = (("BUS_01", "PM_WallMetalBigObject"), ("CMN_COMBI", "PM_WallMetalBigObject"), ("PLASTIC", "PM_WallPlasticBarrier"), ("RAIL", "PM_WallMetalGuardrail"), ("HAY", "PM_WallHayBale"),
            ("WALL", "PM_WallRock"), ("ROCK", "PM_WallRock"))


def _graph_props(slug, level, categories, k, collect):
    import re
    import numpy as np
    gp = (_cfg(slug) or {}).get("graph_props")
    if not gp or k.get("route_xy") is None:
        return []
    tag = gp["tag"]
    names = [n.upper() for n in gp.get("names") or []]
    own = re.compile(rf"^{re.escape(tag)}/\w*_{re.escape(tag)}_GRAPHS?/", re.I)      # FR_FRANCECORSE: FR_SS1_Graph
    allp, _ = collect(level, categories, **dict(k, stage_mask=None))
    R = np.asarray(k["route_xy"], float)[:, :2]
    near = float(gp.get("near_m", 60.0))
    out = []
    for p in allp:
        if not own.match(p.path or "") or (names and not any(n in (p.psi_name or "").upper() for n in names)):
            continue
        t = np.asarray(p.world, float)[:3, 3]
        if np.hypot(R[:, 0] - t[0], R[:, 1] - t[1]).min() <= near:
            out.append(p)
    return out


SPAWNER_TAG = None


def _own_spawners(out):
    """"own_spawners_only": a level's stages share roads, and the spline spawners of the other stages (KE_ES1_..., KE_SS2R_...:
    the posts and nets that close this road for them) stand on this stage's road (Kenya SS2, owner 2026-11-14: posts
    in the middle of the road). Spawners named for another stage tag (SS1, SS2R, ES1...) are dropped."""
    import re
    import tools.acrmod.stagectx as sc
    cfg = _cfg(sc.cur().slug) or {}
    if not cfg.get("own_spawners_only", True):
        return out
    own = str(cfg.get("stage_id", "")).split("/")[-1].upper()
    if not own:
        return out
    rx = re.compile(r"SplineSpawnerBuildStep/[A-Z0-9]+_((?:SS|ES)\d+R?)_", re.I)
    keep, drop = [], 0
    for p in out:
        m = rx.match(p.path or "")
        if m and m.group(1).upper() != own:
            drop += 1
        else:
            keep.append(p)
    if drop:
        print(f"    own spawners: {drop} props of other stages' spline spawners left out (kept {own} and the shared ones)")
    return keep


_NO_PSI = set()


def _skip_empty_psi(fn):
    """Kenya's ES1 start zone has nodes (TABLE_JARDIN, CHAISE_1) whose model reference is 0xFFFFFFFF (none): the core's
    collect_instances calls .rsplit on that int and the whole build stopped (owner 2026-11-15, Ntulele). On that error the
    node is left out (by name, for this process) and the collection runs again; any other error goes on as before."""
    import tools.wrcg.plm as plm
    if not getattr(plm.Plm.nodes, "_wr_skip", False):
        nodes = plm.Plm.nodes

        def filtered(self, *a, **k):
            return [n for n in nodes(self, *a, **k) if n.name not in _NO_PSI]
        filtered._wr_skip = True
        plm.Plm.nodes = filtered

    def wrapped(*a, **k):
        import traceback
        for _try in range(40):
            try:
                return fn(*a, **k)
            except AttributeError as e:
                f = [fr for fr, _ in traceback.walk_tb(e.__traceback__)][-1]
                name = f.f_locals.get("psi_name")
                if "rsplit" not in str(e) or f.f_locals.get("psi") != 0xFFFFFFFF or not name or name in _NO_PSI:
                    raise
                _NO_PSI.add(name)
                print(f"    props: node {name} has no model (psi -1), left out")
        return fn(*a, **k)
    wrapped._wr_skip = True
    return wrapped


def _patch_graph_props():
    import tools.wrcg.prop_instances as pi
    if getattr(pi.collect_instances, "_wr_graph", False):
        return
    orig = _skip_empty_psi(pi.collect_instances)

    def collect_instances(level="SSS_IT_ITTIRI", categories=("static", "dynamic", "clutter", "spline", "decor"), **k):
        out, info = orig(level, categories, **k)
        if k.get("route_xy") is None:
            return out, info
        import wr_perf
        wr_perf.note_props(out)                             # psi of each prop actor, for its draw distance
        if k.get("stage_mask") is not None:
            try:
                import collections
                import tools.acrmod.stagectx as sc
                slug = sc.cur().slug
                have = {(p.path, p.node_id) for p in out}
                extra = [p for p in _graph_props(slug, level, categories, k, orig) if (p.path, p.node_id) not in have]
                if extra:
                    c = collections.Counter(p.psi_name for p in extra)
                    print(f"    graph props: {len(extra)} props of the stage's own WRCG graph added "
                          f"({', '.join(f'{n} {v}' for n, v in c.most_common(8))})")
                    out = list(out) + extra
            except Exception as e:
                print(f"    graph props: not added ({type(e).__name__}: {e})")
        if k.get("stage_mask") is not None and out:
            try:                                   # WRCG's flamingos and giraffes (wr_animals.py)
                import tools.acrmod.stagectx as sc
                gp = (_cfg(sc.cur().slug) or {}).get("animals")
                if gp and "static" in tuple(categories):
                    import wr_animals
                    ex = wr_animals.instances(level, out[0], k["route_xy"], gp)
                    if ex:
                        import collections
                        c = collections.Counter(p.psi_name for p in ex)
                        print(f"    animals: {len(ex)} added ({', '.join(f'{n} {v}' for n, v in c.most_common())}), frozen in their bind pose")
                        out = list(out) + ex
            except Exception as e:
                print(f"    animals: not added ({type(e).__name__}: {e})")
        if k.get("stage_mask") is not None and out and "static" in tuple(categories):
            try:                                   # hand-placed scene: parked vehicles (wr_scene.py)
                import tools.acrmod.stagectx as sc
                import wr_scene
                extra = wr_scene.vehicle_props(out[0], _cfg(sc.cur().slug) or {})
                if extra:
                    print(f"    scene: {len(extra)} parked vehicles added ({', '.join(p.psi_name for p in extra)})")
                    out = list(out) + extra
                rocks = wr_scene.rock_props(out, _cfg(sc.cur().slug) or {}, lambda: orig(level, ("dynamic", "decor"), **k)[0])
                if rocks:
                    print(f"    rocks: {len(rocks)} {rocks[0].psi_name} added in a line")
                    out = list(out) + rocks
            except Exception as e:
                print(f"    scene vehicles: not added ({type(e).__name__}: {e})")
        try:                                       # every tyre stack that gets a collision is drawn too
            import re
            if float(k.get("near_m") or 0.0) < TYRE_NEAR_M and "decor" in tuple(categories):
                have = {(p.path, p.node_id) for p in out}
                more, _ = orig(level, categories, **dict(k, near_m=TYRE_NEAR_M))
                add = [p for p in more if re.search(TYRE_RE, p.psi_name or "", re.I) and (p.path, p.node_id) not in have]
                if add:
                    out = list(out) + add
                    print(f"    tyre stacks: {len(add)} more drawn (those within {TYRE_NEAR_M:.0f} m, with collision)")
        except Exception as e:
            print(f"    tyre stacks: none added ({type(e).__name__}: {e})")
        out = _own_spawners(out)
        out = _drop_hanging(out)
        try:
            import tools.acrmod.stagectx as sc
            import wr_breakables
            out = wr_breakables.drop_props(out, sc.cur().slug)       # WRCG signs that become ACR physical ones
        except Exception as e:
            print(f"    breakable signs: WRCG signs kept ({type(e).__name__}: {e})")
        if "static" in tuple(categories):
            try:
                import tools.acrmod.stagectx as sc
                import wr_tunnel
                out = wr_tunnel.add_instance(out, sc.cur().slug)          # the road inside tunnels (wr_tunnel.py)
            except Exception as e:
                print(f"    tunnel road: not added ({type(e).__name__}: {e})")
        return _take_seats(out), info

    collect_instances._wr_graph = True
    collect_instances.__wrapped_orig__ = orig      # _graph_collision's own collection: no chairs taken there
    for attr in ("_wr",):
        if getattr(orig, attr, False):
            setattr(collect_instances, attr, True)
    pi.collect_instances = collect_instances


# WRCG's flags (FLAG_01_METAL_*, in the FLAG_NEXTGEN prefabs) are the cloth only, 5.3-6.9 m up, bone-animated; their pole
# is not a prop. In ACR they hung in the air (owner 2026-11-10: Panzerplatte's start and Sanremo's lamp road, "objetos
# flotantes"). Flag props whose mesh starts more than HANG_M above their origin are left out.
HANG_M = 2.0
_HANG = {}


# WRCG's flying birds (OBJ_BIRD_FLYING, ANIMPROPS: 102 on Pietrosella) are animated there; in ACR they stood still in
# the sky (owner 2026-11-11: "unos pájaros congelados en el aire, elimínalos todos").
DROP_PSI = ("OBJ_BIRD",)


def _replaces_tape_stick(prop):
    import tools.acrmod.stagectx as sc
    import wr_roadside
    cfg = _cfg(sc.cur().slug)
    return bool(cfg and wr_roadside.replaces_stick(ROOT, cfg, prop))


_ZONES = {}


def _prop_zones():
    """Stage build "drop_props_at": [{"psi": regex, "m": [from, to]}, {"psi": regex, "m": centre, "radius": r}] (route metres,
    the build's route): matching WRCG props whose nearest route point lies in that stretch are left out (owner 2026-11-16:
    the dark advert banners of Seyabei km 3.1, the incomplete house and the raised tank at km 5.3). Optional "near_cloth": "GREEN"
    (+ "cloth_m", 0.6): only props within cloth_m of a cloth piece of that material (posts left by a removed net)."""
    try:
        import re
        import numpy as np
        import tools.acrmod.build_stage as bs
        import tools.acrmod.stagectx as sc
        slug = sc.cur().slug
        rows = (_cfg(slug) or {}).get("drop_props_at") or []
        if not rows:
            return []
        if slug not in _ZONES:
            R = np.asarray(bs.route_wrcg(bs.load_cfg(slug)), float)[:, :2]
            zs = []
            for z in rows:
                m = z["m"]
                a, b = (float(m[0]), float(m[1])) if isinstance(m, (list, tuple)) else (float(m) - float(z.get("radius", 30)), float(m) + float(z.get("radius", 30)))
                pts = None
                if z.get("near_cloth"):                  # only props standing at a cloth piece whose material has this text
                    import tools.acrmod.cloth_visual as cv
                    import wr_roadside
                    items = getattr(cv.collect_cloth, "original", cv.collect_cloth)(bs.load_cfg(slug)["wrcg_level"], near_m=150.0)[0]     # unfiltered: cloth_skip removed these
                    shown = {id(it) for it in wr_roadside._skip_cloth(items, _cfg(slug) or {})}
                    ends = lambda it: [np.asarray(it["pos"], float)[:2], np.asarray(it["pos"], float)[:2] + float(it["size"][0]) * np.asarray(it["dir"], float)[:2]]
                    sel = [it for it in items if z["near_cloth"].upper() in str(it.get("material")).upper()
                           and a <= int(np.hypot(R[:, 0] - it["pos"][0], R[:, 1] - it["pos"][1]).argmin()) <= b]
                    pts = np.array([q for it in sel if id(it) not in shown for q in ends(it)] or [[1e9, 1e9]])      # pieces still left out
                    keep_pts = np.array([q for it in sel if id(it) in shown for q in ends(it)] or [[1e9, 1e9]])    # pieces that stay: their posts stay
                zs.append((re.compile(z["psi"], re.I), a, b, pts, float(z.get("cloth_m", 0.6)), keep_pts if pts is not None else None))
            _ZONES[slug] = (R, zs)
        return [_ZONES[slug]]
    except Exception as e:
        print(f"    drop_props_at: not applied ({type(e).__name__}: {e})")
        return []


def _props_at(insts):
    """Stage build "props_at": [{"psi": regex, "at": [x, y], "radius": r, "zmin": z0, "zmax": z1, "action": "drop" | "sink", "m": 0.3}]
    (WRCG world metres): the props whose name matches and that stand within r of the point (and between zmin and zmax, optional)
    are dropped, or lowered by m. Owner 2026-11-16, Ngema m ~2970: floating chairs, market stalls 0.3 m above the ground.
    The WRCG collision (collision_extra.npz) of a lowered prop stays where it was."""
    import re
    import numpy as np
    import tools.acrmod.stagectx as sc
    rows = (_cfg(sc.cur().slug) or {}).get("props_at") or []
    if not rows:
        return insts
    def inside(r, W):
        if "box" in r:                                  # [x0, y0, x1, y1]
            x0, y0, x1, y1 = r["box"]
            return x0 <= W[0, 3] <= x1 and y0 <= W[1, 3] <= y1
        return float(np.hypot(W[0, 3] - r["at"][0], W[1, 3] - r["at"][1])) <= float(r.get("radius", 1.0))
    rules = [(re.compile(r["psi"], re.I), r, r.get("zmin", -1e9), r.get("zmax", 1e9), r.get("action", "drop"), float(r.get("m", 0.0))) for r in rows]
    out, done = [], [0] * len(rules)
    for p in insts:
        W = np.asarray(p.world, float)
        hit = next((k for k, (rx, r, z0, z1, _, _) in enumerate(rules)
                    if rx.fullmatch(p.psi_name or "") and inside(r, W) and z0 <= W[2, 3] <= z1), None)
        if hit is None:
            out.append(p)
            continue
        done[hit] += 1
        if rules[hit][4] == "sink":
            W = W.copy()
            W[2, 3] -= rules[hit][5]
            p.world = W
            out.append(p)
    print("    props_at: %d props changed (%s)" % (sum(done), ", ".join("%s x%d" % (r["psi"], n) for r, n in zip(rows, done))))
    return out


def _in_prop_zone(p, zones):
    import numpy as np
    R, zs = zones[0]
    name = p.psi_name or ""
    cand = [z for z in zs if z[0].fullmatch(name)]
    if not cand:
        return False
    W = np.asarray(p.world, float)[:3, 3]
    i = int(np.hypot(R[:, 0] - W[0], R[:, 1] - W[1]).argmin())
    return any(a <= i <= b and (pts is None or (float(np.hypot(pts[:, 0] - W[0], pts[:, 1] - W[1]).min()) <= d and float(np.hypot(kp[:, 0] - W[0], kp[:, 1] - W[1]).min()) > 0.3)) for _, a, b, pts, d, kp in cand)


def _drop_hanging(insts):
    import numpy as np
    import tools.wrcg.p3d_render as pr
    out, dropped = [], {}
    try:
        import tools.acrmod.stagectx as sc
        extra = tuple(w.upper() for w in (_cfg(sc.cur().slug) or {}).get("drop_psi") or ())     # stage config "drop_psi"
    except Exception:
        extra = ()
    zones = _prop_zones()
    insts = _props_at(insts)
    for p in insts:
        name = (p.psi_name or "").upper()
        if extra and any(w in name for w in extra):
            dropped[name] = dropped.get(name, 0) + 1
            continue
        if zones and _in_prop_zone(p, zones):
            dropped[name] = dropped.get(name, 0) + 1
            continue
        if name.startswith("STICK") and "/NET_TAPE/" in str(p.psi).upper() and _replaces_tape_stick(p):
            dropped["TAPE STICK"] = dropped.get("TAPE STICK", 0) + 1
            continue
        if name.startswith(DROP_PSI):
            dropped[name] = dropped.get(name, 0) + 1
            continue
        if name.startswith("FLAG"):
            if p.psi not in _HANG:
                try:
                    parts = [x for x in pr.read_prop(p.psi).parts if x.lod == 0]
                    _HANG[p.psi] = min(float(np.asarray(x.geom.positions, float).reshape(-1, 3)[:, 2].min())
                                       for x in parts) if parts else 0.0
                except Exception:
                    _HANG[p.psi] = 0.0
            if _HANG[p.psi] > HANG_M:
                dropped[name] = dropped.get(name, 0) + 1
                continue
        out.append(p)
    if dropped:
        print(f"    props left out (pole-less flags, flying birds): {sum(dropped.values())} ({', '.join(sorted(dropped))})")
    return out


# WRCG's chairs at the start and stop control tables (START_ZONE/CHAISE_1): each one becomes a seated ACR spectator on
# ACR's crowd seat (wr_crowd.add_seated, at save time in _late_level), so the WRCG chair is left out of the props.
# Its seat centre and facing come from its LOD0 mesh: the backrest is the top quarter, the chair faces away from it.
SEAT_PSI = ("START_ZONE/CHAISE",)
_SEATS = {}            # (psi, x, y) -> (WRCG world matrix, local seat bottom centre (3,), local facing (2,))
_SEAT_SHAPE = {}


def _seat_shape(psi):
    import numpy as np
    import tools.wrcg.p3d_render as pr
    if psi not in _SEAT_SHAPE:
        P = np.concatenate([(np.c_[np.asarray(x.geom.positions, float).reshape(-1, 3), np.ones(len(np.asarray(
            x.geom.positions).reshape(-1, 3)))] @ np.asarray(x.matrix, float).T)[:, :3]
            for x in pr.read_prop(psi).parts if x.lod == 0])
        lo, hi = P.min(0), P.max(0)
        c = (lo + hi) / 2
        back = P[P[:, 2] > lo[2] + 0.75 * (hi[2] - lo[2])][:, :2].mean(0)
        f = c[:2] - back
        f = f / np.linalg.norm(f) if np.linalg.norm(f) > 1e-3 else np.array([0.0, 1.0])
        _SEAT_SHAPE[psi] = (np.array([c[0], c[1], lo[2]]), f)
    return _SEAT_SHAPE[psi]


def _take_seats(insts):
    import numpy as np
    out, n = [], 0
    for p in insts:
        if any(s in (p.psi or "").upper() for s in SEAT_PSI):
            try:
                W = np.asarray(p.world, float)
                key = (p.psi, round(float(W[0, 3]), 2), round(float(W[1, 3]), 2))
                n += key not in _SEATS
                _SEATS[key] = (W, *_seat_shape(p.psi))
                continue
            except Exception as e:
                print(f"    seated people: chair {p.psi} kept ({type(e).__name__}: {e})")
        out.append(p)
    if n:
        print(f"    seated people: {n} WRCG table chairs replaced by seated ACR spectators")
    return out


def _seats_ue(shift):
    """[(x, y, z, facing yaw deg)] UE cm of the chairs taken by _take_seats."""
    import math
    import numpy as np
    import tools.acrmod.props_visual as pv
    out = []
    for W, c, f in _SEATS.values():
        a = W @ np.array([c[0], c[1], c[2], 1.0])
        b = W @ np.array([c[0] + f[0], c[1] + f[1], c[2], 1.0])
        ua, ub = pv.wrcg_world_to_ue(np.array([a[:3], b[:3]]), shift)
        out.append((float(ua[0]), float(ua[1]), float(ua[2]), math.degrees(math.atan2(ub[1] - ua[1], ub[0] - ua[0]))))
    return out


FENCE_LINK_M = 7.0                 # posts of one fence spawner closer than this are joined by a wall
FENCE_H = (0.25, 1.4)              # wall from this far above the post's foot to this height (m)
PROP_FENCE_RE = __import__("re").compile(r"(WOOD|METAL|WIRE|BARB)\w*FENCE|FENCE\w*(BARB|WIRE|WOOD)", __import__("re").I)   # props that are a fence themselves
FENCE_KEEP_OFF_M = 2.0
PROP_FENCE_KEEP_OFF_M = 1.2         # a prop fence closer to the route's centre line than this is a gate / on the lane: left open             # a link that crosses the route or passes this close to it is a gate: left open


def _fence_collision(slug, offset):
    """"fence_solid": WRCG's wire fences (High_Fence_*_Spawner: posts with a collision, the wires none) get a thin
    two-sided wall between neighbouring posts of the same spawner. A link across the stage's road (a gate, a gap in
    the fence) is not built, so the road is never closed."""
    import collections
    import numpy as np
    import tools.acrmod.build_stage as bs
    import tools.acrmod.ittiri_container as ic
    d0 = np.load(WORK / "wrcg" / slug / "collision_extra.npz", allow_pickle=True)
    R = np.asarray(bs.route_wrcg(bs.load_cfg(slug)), float)[:, :2]
    groups = collections.defaultdict(list)
    for i, pth in enumerate(d0["owner_path"]):
        pth = str(pth)
        if "FENCE" in pth.upper() and str(d0["owner_psi"][i]).upper().split("/")[-1].startswith("POLE_"):
            lo, hi = d0["owner_bbox_min"][i], d0["owner_bbox_max"][i]
            groups[pth.split("/")[1]].append(((lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, float(lo[2]), float(hi[2])))

    def crosses(a, b):
        for k in range(len(R) - 1):
            c, e = R[k], R[k + 1]
            o = lambda p, q, r: (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
            if o(a, b, c) * o(a, b, e) < 0 and o(c, e, a) * o(c, e, b) < 0:
                return True
        return False

    def near_route(a, b, d=FENCE_KEEP_OFF_M):
        for t in np.linspace(0.0, 1.0, 5):
            q = a + (b - a) * t
            if np.hypot(R[:, 0] - q[0], R[:, 1] - q[1]).min() < d:
                return True
        return False

    prop_groups = set()
    try:                                 # fences made of plain props with no collision at all (Ngema's WOOD_FENCE_BARBWIRE_01_BRK, owner 2026-11-16)
        import tools.wrcg.prop_instances as pi
        import wr_skinned
        cfg = _cfg(slug) or {}
        insts, _ = pi.collect_instances(cfg["wrcg_level"], ("static", "dynamic", "clutter", "spline", "decor"), route_xy=R, near_m=60.0,
                                        stage_mask=wr_skinned.stage_mask(cfg.get("stage_id")))
        lo_all, hi_all = d0["owner_bbox_min"][:, :2], d0["owner_bbox_max"][:, :2]
        for q in insts:
            if q.category != "decor" or not PROP_FENCE_RE.search(q.psi_name or ""):
                continue
            W = np.asarray(q.world, float)
            if len(lo_all) and ((W[0, 3] > lo_all[:, 0] - 0.3) & (W[0, 3] < hi_all[:, 0] + 0.3) & (W[1, 3] > lo_all[:, 1] - 0.3) & (W[1, 3] < hi_all[:, 1] + 0.3)).any():
                continue                 # already has a collision of its own
            key = str(q.path).rsplit("/", 1)[0]
            prop_groups.add(key)
            groups[key].append((W[0, 3], W[1, 3], float(W[2, 3]), float(W[2, 3])))
    except Exception as e:
        print(f"    wire fences: prop fences not read ({type(e).__name__}: {e})")
    from wr_roadside import _road_test
    on_road = _road_test(WORK / "wrcg" / slug, margin_cells=1)

    pos, tri, n, links, gates, close = [], [], 0, 0, 0, 0
    for g, P in groups.items():
        P = np.asarray(P, float)
        done = set()
        for i in range(len(P)):
            dist = np.hypot(P[:, 0] - P[i, 0], P[:, 1] - P[i, 1])
            for j in np.argsort(dist)[1:3]:
                if dist[j] > FENCE_LINK_M or (min(i, j), max(i, j)) in done:
                    continue
                done.add((min(i, j), max(i, j)))
                a, b = P[i, :2], P[j, :2]
                if crosses(a, b) or (g not in prop_groups and near_route(a, b)) or (g in prop_groups and near_route(a, b, PROP_FENCE_KEEP_OFF_M)) or (g not in prop_groups and not on_road(np.array([a, (a + b) / 2, b]))):
                    gates += 1               # a gate across the road (a post fence on the road mesh is skipped; a prop fence is always closed: owner 2026-11-16, Ngema km 3.3 gaps)
                    continue
                if g in prop_groups and near_route(a, b):
                    close += 1
                z0, z1 = [min(P[i, 2], P[j, 2]) + h for h in FENCE_H]
                pos.append(np.array([[a[0], a[1], z0], [b[0], b[1], z0], [b[0], b[1], z1], [a[0], a[1], z1]]))
                tri += [[n, n + 1, n + 2], [n, n + 2, n + 3], [n, n + 2, n + 1], [n, n + 3, n + 2]]
                n += 4
                links += 1
    if not tri:
        return []
    d = {"positions": np.concatenate(pos).astype(np.float32), "triangles": np.asarray(tri, np.uint32)}
    d["tri_piece"] = np.zeros(len(d["triangles"]), np.uint16)
    d["tri_slot_sub"] = np.zeros(len(d["triangles"]), np.uint16)
    ms = ic._meshes_from(d, np.ones(len(d["triangles"]), bool), offset, "WrcgFence", lambda t: "PM_WallWood")
    print(f"    wire fences: {links} walls between posts ({gates} links across or beside the road left open; {close} prop-fence walls within {FENCE_KEEP_OFF_M:g} m of the route)")
    return list(ms)


ROCK_NEAR_M = 70.0                 # owner 2026-11-15: stones off the road without collision (was 40)
ROCK_SINK_M = 0.2                  # the species' sink_cm (data/wrcg_vegetation_map.json): the stone sits in the ground
ROCK_SCALE = (5.0, 9.0)            # the species' scale; the instances carry 1.5..2.0 over it (assumed linear, checked by eye)
ROCK_FACTOR = 0.72                 # big rocks +20 % (owner 2026-11-15; was 0.6; the small gc_rock stay at GC_ROCK_FACTOR). owner 2026-11-14: "golpean o frenan demasiado": the obstacle is this much of the stone
GC_ROCK_FACTOR = 0.54              # the smaller ground-cover rocks (gc_rock): 0.85 -> 0.68 -> 0.58 -> 0.50 -> 0.54 (owner, final); the big ones stay at ROCK_FACTOR
GC_ROCK_MIN_H_M = 0.3              # lower ones are driven over
ROCK_MESH_FALLBACK = {"A": (12.0, 6.4, 8.8, 1.1), "B": (16.7, 14.0, 10.0, 0.6)}    # half extents + origin z (cm)


TREE_NEAR_M = 14.0                 # only trees this close to the route get a trunk (owner 2026-11-14)
TREE_RADIUS_M = 0.3                # trunk radius: shortcut, the real one is not measured (scale of the ACR mesh unclear)
TREE_HEIGHT_M = 3.0
TREE_SPECIES = "olive|oak"         # ACR's tree species of the vegetation replay (Kenya's acacias and baobabs map to them)


def _tree_collision(slug, offset):
    """"tree_solid": the vegetation's trees are foliage with no collision. Each one within TREE_NEAR_M of the route gets a
    trunk obstacle: an octagonal prism of TREE_RADIUS_M and TREE_HEIGHT_M on the ground at the instance."""
    import json
    import re
    import numpy as np
    import tools.acrmod.build_stage as bs
    import tools.acrmod.ittiri_container as ic
    text = (WORK / "wrcg" / slug / "vegetation" / "instances.json").read_text(encoding="utf-8")
    trees = [json.loads(m) for m in re.findall(r'\{[^{}]*"species": "(?:%s)"[^{}]*\}' % TREE_SPECIES, text)]
    del text
    R = np.asarray(bs.route_wrcg(bs.load_cfg(slug)), float)[:, :2]
    ang = np.linspace(0, 2 * np.pi, 8, endpoint=False)
    ring = np.c_[np.cos(ang), np.sin(ang)] * TREE_RADIUS_M
    f = []
    for k in range(8):
        a0, a1 = k, (k + 1) % 8
        f += [[a0, a1, a1 + 8], [a0, a1 + 8, a0 + 8]]                # sides
    f += [[16 + 0, 16 + 1 + k, 16 + 2 + k] for k in range(6)]        # top fan, centre at 16 is vertex 8+8
    f = np.asarray(f)
    pos, tri, n = [], [], 0
    for t in trees:
        if np.hypot(R[:, 0] - t["x"], R[:, 1] - t["y"]).min() > TREE_NEAR_M:
            continue
        z0 = float(t.get("z_collision", t["z"])) - 0.1
        v = np.vstack([np.c_[ring, np.full(8, z0)] + [t["x"], t["y"], 0.0],
                       np.c_[ring, np.full(8, z0 + TREE_HEIGHT_M)] + [t["x"], t["y"], 0.0]])
        pos.append(v)
        tri += [x + n for x in (f[:16], f[:16, ::-1])]               # sides only: the top is under the canopy
        n += len(v)
    if not pos:
        return []
    d = {"positions": np.concatenate(pos).astype(np.float32), "triangles": np.concatenate(tri).astype(np.uint32)}
    d["tri_piece"] = np.zeros(len(d["triangles"]), np.uint16)
    d["tri_slot_sub"] = np.zeros(len(d["triangles"]), np.uint16)
    ms = ic._meshes_from(d, np.ones(len(d["triangles"]), bool), offset, "WrcgTree", lambda t: "PM_WallRock")
    print(f"    trees: trunk collision for {len(pos)} trees within {TREE_NEAR_M:.0f} m of the route (of {len(trees)})")
    return list(ms)


def _rock_collision(slug, offset):
    """"rock_solid": the vegetation's stones are foliage with no collision: 'rock' (ACR's SmallLimestone A/B, a metre or
    so wide) and ground cover's gc_rock (B/C/D at scale 2.2..4.5). Each one within ROCK_NEAR_M of the route gets a
    low-poly ellipsoid obstacle, a fraction of the mesh at the instance's scale (round in plan: the yaw convention is
    not checked)."""
    import json
    import re
    import numpy as np
    import tools.acrmod.build_stage as bs
    import tools.acrmod.ittiri_container as ic
    text = (WORK / "wrcg" / slug / "vegetation" / "instances.json").read_text(encoding="utf-8")
    rocks = [json.loads(m) for m in re.findall(r'\{[^{}]*"species": "(?:rock|gc_rock)"[^{}]*\}', text)]
    del text
    mb = dict(ROCK_MESH_FALLBACK)
    try:
        b = json.loads((WORK / "acr" / "rt" / "foliage" / "mesh_bounds.json").read_text(encoding="utf-8"))
        for n in "ABCDEF":
            v = b.get(f"/Game/Props/GreeceProps/GreElaSmallStones/SM_GreElaSmallLimestone{n}")
            if v:
                mb[n] = (v["extent"][0], v["extent"][1], v["extent"][2], v["origin"][2])
    except (OSError, ValueError):
        pass
    R = np.asarray(bs.route_wrcg(bs.load_cfg(slug)), float)[:, :2]
    seg = 8
    lat = np.radians([-50.0, 0.0, 50.0])
    ang = np.linspace(0, 2 * np.pi, seg, endpoint=False)
    unit = np.array([[0, 0, -1.0]] + [[np.cos(l) * np.cos(a), np.cos(l) * np.sin(a), np.sin(l)] for l in lat for a in ang]
                    + [[0, 0, 1.0]])
    f = []
    for k in range(seg):                                           # bottom fan, two bands, top fan
        f.append([0, 1 + (k + 1) % seg, 1 + k])
        for r in (0, 1):
            a0, a1 = 1 + r * seg + k, 1 + r * seg + (k + 1) % seg
            f += [[a0, a1, a1 + seg], [a0, a1 + seg, a0 + seg]]
        f.append([25, 1 + 2 * seg + k, 1 + 2 * seg + (k + 1) % seg])
    f = np.asarray(f)
    pos, tri, n, kept = [], [], 0, {"rock": 0, "gc_rock": 0}
    for r in rocks:
        if np.hypot(R[:, 0] - r["x"], R[:, 1] - r["y"]).min() > ROCK_NEAR_M:
            continue
        gc = r["species"] == "gc_rock"
        ex, ey, ez, oz = mb.get("BCD"[int(r["mesh"]) % 3] if gc else "AB"[int(r["mesh"]) % 2], mb["B"])
        if gc:
            S, fac = float(r["scale"]), GC_ROCK_FACTOR
        else:
            S = ROCK_SCALE[0] + (float(r["scale"]) - 1.5) * (ROCK_SCALE[1] - ROCK_SCALE[0]) / 0.5
            fac = ROCK_FACTOR
        rad, hz = np.sqrt(ex * ey) * S / 100.0 * fac, ez * S / 100.0 * fac
        if gc and 2 * hz - ROCK_SINK_M < GC_ROCK_MIN_H_M:
            continue
        c = np.array([r["x"], r["y"], r["z"] - ROCK_SINK_M + oz * S / 100.0])
        pos.append(c + unit * np.array([rad, rad, hz]))
        tri += [t + n for t in (f, f[:, ::-1])]                    # both faces
        n += len(unit)
        kept[r["species"]] += 1
    if not sum(kept.values()):
        return []
    d = {"positions": np.concatenate(pos).astype(np.float32), "triangles": np.concatenate(tri).astype(np.uint32)}
    d["tri_piece"] = np.zeros(len(d["triangles"]), np.uint16)
    d["tri_slot_sub"] = np.zeros(len(d["triangles"]), np.uint16)
    ms = ic._meshes_from(d, np.ones(len(d["triangles"]), bool), offset, "WrcgRock", lambda t: "PM_WallRock")
    print(f"    rocks: collision for {kept['rock']} stones and {kept['gc_rock']} medium ground-cover rocks within "
          f"{ROCK_NEAR_M:.0f} m of the route (of {len(rocks)})")
    return list(ms)


NET_NEAR_M = 60.0
NET_H = (-0.1, 1.0)               # a net piece's collision: from its attach point's height, bottom and top (m)


def _net_collision(slug, offset):
    """"net_solid": WRCG's net fences (NetCloth: the red plastic net, the large green one) are cloth with no collision;
    each 2 m piece within NET_NEAR_M of the route gets a thin two-sided wall as an obstacle. Tape stays a no-collision."""
    import numpy as np
    import tools.acrmod.build_stage as bs
    import tools.acrmod.cloth_visual as cv
    import tools.acrmod.ittiri_container as ic
    cfg = _cfg(slug) or {}
    items, _ = cv.collect_cloth(cfg["wrcg_level"], near_m=150.0)
    R = np.asarray(bs.route_wrcg(bs.load_cfg(slug)), float)[:, :2]
    pos, tri, n = [], [], 0
    for it in items:
        if it["template"] != "NetCloth":
            continue
        a = np.asarray(it["pos"], float)
        b = a + np.asarray(it["dir"], float) * float(it["size"][0])
        if np.hypot(R[:, 0] - a[0], R[:, 1] - a[1]).min() > NET_NEAR_M:
            continue
        v = np.array([[a[0], a[1], a[2] + NET_H[0]], [b[0], b[1], b[2] + NET_H[0]],
                      [b[0], b[1], b[2] + NET_H[1]], [a[0], a[1], a[2] + NET_H[1]]])
        pos.append(v)
        tri += [[n, n + 1, n + 2], [n, n + 2, n + 3], [n, n + 2, n + 1], [n, n + 3, n + 2]]      # both faces
        n += 4
    if not tri:
        return []
    d = {"positions": np.concatenate(pos).astype(np.float32), "triangles": np.asarray(tri, np.uint32)}
    d["tri_piece"] = np.zeros(len(d["triangles"]), np.uint16)
    d["tri_slot_sub"] = np.zeros(len(d["triangles"]), np.uint16)
    ms = ic._meshes_from(d, np.ones(len(d["triangles"]), bool), offset, "WrcgNet", lambda t: "PM_WallPlasticBarrier")
    print(f"    nets: collision for {n // 4} net pieces within {NET_NEAR_M:.0f} m of the route")
    return list(ms)


def _graph_collision(slug, offset):
    """Collision meshes (baked frame, like the builder's) from the LOD0 meshes of the stage's graph props named in
    graph_props_solid."""
    import numpy as np
    import tools.acrmod.build_stage as bs
    import tools.acrmod.ittiri_container as ic
    import tools.wrcg.p3d_render as pr
    import tools.wrcg.prop_instances as pi
    cfg = _cfg(slug) or {}
    words = [w.upper() for w in cfg.get("graph_props_solid") or []]
    route = np.asarray(bs.route_wrcg(bs.load_cfg(slug)), float)
    k = {"route_xy": route[:, :2], "near_m": 150.0, "startends_stage": cfg.get("startends_stage"), "stage_mask": None}
    collect = getattr(pi.collect_instances, "__wrapped_orig__", None) or pi.collect_instances
    sel = [p for p in _graph_props(slug, cfg["wrcg_level"], ("static", "dynamic", "decor"), k, collect)
           if any(w in (p.psi_name or "").upper() for w in words)]
    try:                                           # the scene's parked vehicles (wr_scene.py) get their collision too
        import wr_scene
        if wr_scene.options(cfg) or cfg.get("rocks"):
            import wr_skinned
            first, _ = collect(cfg["wrcg_level"], ("static", "dynamic", "clutter", "spline", "decor"), route_xy=route[:, :2],
                               near_m=150.0, stage_mask=wr_skinned.stage_mask(cfg.get("stage_id")))
            sel += wr_scene.vehicle_props(first[0] if first else None, cfg) + [p for p in wr_scene.rock_props(first, cfg) if getattr(p, "scene_solid", True)]
    except Exception as e:
        print(f"    scene vehicles: no collision ({type(e).__name__}: {e})")
    solid = [w.upper() for w in cfg.get("solid_by_name") or []]
    if solid:                                      # props of any source (not only the graph's) kept as solid obstacles, from their LOD0 mesh
        try:
            import wr_skinned
            allp, _ = collect(cfg["wrcg_level"], ("static", "dynamic", "clutter", "spline", "decor"), route_xy=route[:, :2],
                              near_m=150.0, stage_mask=wr_skinned.stage_mask(cfg.get("stage_id")))
            sel += [p for p in allp if any(w in (p.psi_name or "").upper() for w in solid)]
        except Exception as e:
            print(f"    solid by name: not added ({type(e).__name__}: {e})")
    if not sel:
        return []
    pos, tri, piece, pms, cache = [], [], [], [], {}
    n = 0
    for i, p in enumerate(sel):
        if p.psi not in cache:
            prop = pr.read_prop(p.psi)
            cache[p.psi] = [(np.asarray(x.matrix, float), np.asarray(x.geom.positions, float).reshape(-1, 3),
                             np.asarray(x.geom.triangles, np.int64).reshape(-1, 3)) for x in prop.parts if x.lod == 0]
        W = np.asarray(p.world, float)
        for M, V, T in cache[p.psi]:
            H = np.c_[V, np.ones(len(V))] @ (W @ M).T
            tri.append(T + n)
            pos.append(H[:, :3])
            piece.append(np.full(len(T), i, np.uint16))
            n += len(V)
        name = (p.psi_name or "").upper()
        pms.append(next((pm for w, pm in GRAPH_PM if w in name), "PM_WallBasic"))
    d = {"positions": np.concatenate(pos).astype(np.float32), "triangles": np.concatenate(tri).astype(np.uint32),
         "tri_piece": np.concatenate(piece)}
    d["tri_slot_sub"] = np.zeros(len(d["triangles"]), np.uint16)
    owner_pm = np.array(pms)
    ms = ic._meshes_from(d, np.ones(len(d["triangles"]), bool), offset, "WrcgGraphProp",
                         lambda t: str(owner_pm[int(d["tri_piece"][t[0]])]))
    import collections
    c = collections.Counter(pms)
    print(f"    graph props: collision for {len(sel)} of them ({len(d['triangles'])} triangles; "
          f"{', '.join(f'{v} {pm}' for pm, v in c.items())})")
    return list(ms)


# Tyre stacks (owner 2026-11-11, Brattby: "los neumáticos tendrían que tener colisión y no romperse"): WRCG's
# TIRESSTACK_*_BRK are decor without collision in the stage's collision export, so the car went through them. Every tyre
# stack within TYRE_NEAR_M of the route gets a collision from its LOD0 mesh (like graph_props_solid), ACR's
# PM_WallTire; the same stacks are added to the visual props if the builder's own collection left any out.
TYRE_RE = r"TIRES?STACK|TYRES?STACK|TIRE_STACK|TYRE_STACK|PNEU"
TYRE_NEAR_M = 60.0


def _tyre_props(slug, collect):
    import re
    import numpy as np
    import tools.acrmod.build_stage as bs
    import wr_skinned
    cfg = _cfg(slug) or {}
    route = np.asarray(bs.route_wrcg(bs.load_cfg(slug)), float)
    out, _ = collect(cfg["wrcg_level"], ("static", "dynamic", "clutter", "spline", "decor"), route_xy=route[:, :2],
                     near_m=TYRE_NEAR_M, stage_mask=wr_skinned.stage_mask(cfg.get("stage_id")))
    return [p for p in out if re.search(TYRE_RE, p.psi_name or "", re.I)]


def _tyre_collision(slug, offset):
    import numpy as np
    import tools.acrmod.ittiri_container as ic
    import tools.wrcg.p3d_render as pr
    import tools.wrcg.prop_instances as pi
    collect = getattr(pi.collect_instances, "__wrapped_orig__", None) or pi.collect_instances
    sel = _tyre_props(slug, collect)
    if not sel:
        return []
    pos, tri, piece, cache, n = [], [], [], {}, 0
    for i, p in enumerate(sel):
        if p.psi not in cache:
            prop = pr.read_prop(p.psi)
            cache[p.psi] = [(np.asarray(x.matrix, float), np.asarray(x.geom.positions, float).reshape(-1, 3),
                             np.asarray(x.geom.triangles, np.int64).reshape(-1, 3)) for x in prop.parts if x.lod == 0]
        W = np.asarray(p.world, float)
        for M, V, T in cache[p.psi]:
            Hh = np.c_[V, np.ones(len(V))] @ (W @ M).T
            tri.append(T + n)
            pos.append(Hh[:, :3])
            piece.append(np.full(len(T), i, np.uint16))
            n += len(V)
    d = {"positions": np.concatenate(pos).astype(np.float32), "triangles": np.concatenate(tri).astype(np.uint32),
         "tri_piece": np.concatenate(piece)}
    d["tri_slot_sub"] = np.zeros(len(d["triangles"]), np.uint16)
    ms = ic._meshes_from(d, np.ones(len(d["triangles"]), bool), offset, "WrcgTyreStack", lambda t: "PM_WallTire")
    print(f"    tyre stacks: collision for {len(sel)} ({len(d['triangles'])} triangles, PM_WallTire)")
    return list(ms)


# Tall posts and signs (owner 2026-11-11, 3rd drive: "hacemos que nada se rompa. Los más pequeños que no tengan
# colisión. Las flechitas pequeñas que no afecten a colisión. Los palos altos o más grandes sí, con colisión"): WRCG's
# signs, marker posts and snow poles are dynamic props there and the builder gives them no collision. Those POLE_MIN_H
# tall or more (road signs, parking and direction signs, snow poles and flag poles) get a collision from their LOD0
# mesh, ACR's PM_WallMetalPole; the small ones (marker posts, medical boards, arrows) stay without.
POLE_RE = (r"/SIGNS/MARKER/|/SIGNS/POLE/|/SIGNS/PLOTS/PLOT_(MEDICAL|RADIO)|/SE_SIGNS/|/ROAD_SIGNS/|/JAPAN_SIGNS/|"
           r"/SE_PANEL/|/FR_PANEL_|/ES_SIGNS/PANEL|/PANELS/|_MAILBOX_|/SIGNS/SIGN_")
POLE_MIN_H = 1.5
# the thin metal sticks of the red-and-white tapes (RAILCLONE/NET_TAPE/STICK*, 1-1.3 m, 4-10 cm across): solid posts, the
# tape itself stays without collision (owner 2026-11-15); "stick_solid": true switches it on (off by default)
STICK_RE = r"/NET_TAPE/STICK"
STICK_MIN_H = 0.5


def _pole_collision(slug, offset):
    import re
    import numpy as np
    import tools.acrmod.build_stage as bs
    import tools.acrmod.ittiri_container as ic
    import tools.wrcg.p3d_render as pr
    import tools.wrcg.prop_instances as pi
    import wr_skinned
    cfg = _cfg(slug) or {}
    collect = getattr(pi.collect_instances, "__wrapped_orig__", None) or pi.collect_instances
    route = np.asarray(bs.route_wrcg(bs.load_cfg(slug)), float)
    out, _ = collect(cfg["wrcg_level"], ("static", "dynamic", "clutter", "spline", "decor"), route_xy=route[:, :2],
                     near_m=TYRE_NEAR_M, stage_mask=wr_skinned.stage_mask(cfg.get("stage_id")))
    import wr_roadside
    sticks = bool(cfg.get("stick_solid", False)) and not wr_roadside.on(cfg, "wrcg_tape_post_physics")      # off by default: it blocked the start (owner 2026-11-15)
    is_stick = lambda p: re.search(STICK_RE, str(p.psi), re.I)
    cand = [p for p in out if (p.category in ("dynamic", "decor", "clutter") and re.search(POLE_RE, str(p.psi), re.I)
                               and not re.search(r"NET_TAPE|PLOT02_", str(p.psi), re.I)) or (sticks and is_stick(p) and not wr_roadside.replaces_stick(ROOT, cfg, p))]
    pos, tri, n, cache, kinds = [], [], 0, {}, {}
    for p in cand:
        if p.psi not in cache:
            prop = pr.read_prop(p.psi)
            parts = [(np.asarray(x.matrix, float), np.asarray(x.geom.positions, float).reshape(-1, 3),
                      np.asarray(x.geom.triangles, np.int64).reshape(-1, 3)) for x in prop.parts if x.lod == 0]
            zs = np.concatenate([(np.c_[V, np.ones(len(V))] @ M.T)[:, 2] for M, V, T in parts]) if parts else np.zeros(1)
            cache[p.psi] = parts if float(np.ptp(zs)) >= (STICK_MIN_H if re.search(STICK_RE, str(p.psi), re.I) else POLE_MIN_H) else None
        if cache[p.psi] is None:
            continue
        W = np.asarray(p.world, float)
        for M, V, T in cache[p.psi]:
            Hh = np.c_[V, np.ones(len(V))] @ (W @ M).T
            tri.append(T + n)
            pos.append(Hh[:, :3])
            n += len(V)
        kinds[p.psi_name] = kinds.get(p.psi_name, 0) + 1
    if not tri:
        return []
    d = {"positions": np.concatenate(pos).astype(np.float32), "triangles": np.concatenate(tri).astype(np.uint32)}
    d["tri_piece"] = np.zeros(len(d["triangles"]), np.uint16)
    d["tri_slot_sub"] = np.zeros(len(d["triangles"]), np.uint16)
    ms = ic._meshes_from(d, np.ones(len(d["triangles"]), bool), offset, "WrcgPost", lambda t: "PM_WallMetalPole")
    print(f"    posts and signs: collision for {sum(kinds.values())} tall ones "
          f"({', '.join(f'{k} {v}' for k, v in sorted(kinds.items()))}); the small ones stay without")
    return list(ms)


# Props on the ground (owner 2026-11-11): a crowd fence at Pietrosella's start "se hunde en el suelo" (the builder's
# terrain is raised to the road beside it), and Brattby's high-voltage pylons stand 2-5 m over the ground ("están
# volando"). A fence or barrier whose foot is more than SINK_M under the ground at its pivot comes up onto it; a
# high-voltage pylon gets its feet on the lowest ground under its legs and is stretched upwards from there so that its
# cross-arms (PYLON_ARM_M up the mesh) stay where the lines hang.
SINK_M = 0.1
FENCE_RE = r"FENCE|BARRIER|BANNER"
PYLON_RE = r"HIGHVOLTAGE_PYLON"
PYLON_ARM_M, PYLON_LEG_M = 57.0, 5.0


def _ground_props(dst, ground, log=print):
    _eprop = lambda e, n: next((p for p in (e.get("Data") or []) if isinstance(p, dict) and p.get("Name") == n), None)
    import math
    import re
    import wr_perf
    level = next(i for i in range(1, len(dst.exports) + 1) if dst.class_name(i) == "Level")
    raised, pylons = 0, []
    for i in range(1, len(dst.exports) + 1):
        e = dst.exp(i)
        name = e.get("ObjectName", "")
        if e.get("OuterIndex") != level or not name.startswith(wr_perf.PROP_PREFIX) or \
                dst.class_name(i) != "StaticMeshActor":
            continue
        stem = re.sub(r"_\d+$", "", name[len(wr_perf.PROP_PREFIX):])
        fence, pylon = re.search(FENCE_RE, stem, re.I), re.search(PYLON_RE, stem, re.I)
        if not (fence or pylon):
            continue
        cp = _eprop(e, "StaticMeshComponent")
        if not cp or not cp.get("Value"):
            continue
        ce = dst.exp(cp["Value"])
        lp = _eprop(ce, "RelativeLocation")
        if not lp or not lp.get("Value"):
            continue
        loc = lp["Value"][0]["Value"]
        x, y, z = float(loc["X"]), float(loc["Y"]), float(loc["Z"])
        if fence:
            g = ground(x, y, z)
            if g is not None and math.isfinite(g) and g - z > SINK_M * 100:
                loc["Z"] = float(g)
                raised += 1
        else:
            gs = [ground(x + dx * PYLON_LEG_M * 100, y + dy * PYLON_LEG_M * 100, z)
                  for dx in (-1, 0, 1) for dy in (-1, 0, 1)]
            gs = [g for g in gs if g is not None and math.isfinite(g)]
            if not gs:
                continue
            g = min(gs) - 20.0
            if abs(z - g) < 30.0:
                continue
            sp = _eprop(ce, "RelativeScale3D")
            if not sp or not sp.get("Value"):                  # scale 1: the property made from the location's
                import copy
                sp = copy.deepcopy(lp)
                sp["Name"] = "RelativeScale3D"
                sp["Value"][0]["Name"] = "RelativeScale3D"
                for q in "XYZ":
                    sp["Value"][0]["Value"][q] = 1.0
                ce["Data"].append(sp)
                dst.add_name("RelativeScale3D")
            s0 = float(sp["Value"][0]["Value"]["Z"])
            arm = PYLON_ARM_M * 100 * s0
            k = (z + arm - g) / arm
            sp["Value"][0]["Value"]["Z"] = s0 * k
            loc["Z"] = float(g)
            pylons.append(round((z - g) / 100, 1))
    if raised or pylons:
        log(f"props on the ground: {raised} fences / barriers raised out of the ground"
            + (f"; {len(pylons)} high-voltage pylons down to it (were {min(pylons)}-{max(pylons)} m above), "
               f"stretched to keep their arms at the lines" if pylons else ""))


_STONE_MI = "/Game/Props/GreeceProps/GreElaSmallStones/MI_GreElaSmallLimestone"
_STONES_MADE = {}


def _stone_materials(mesh):
    """"stone_tint": [r, g, b]: ACR's grey Greek limestones (rock, gc_rock, gc_stone: SM_GreElaSmallLimestone A-F, one shared
    material instance) get a copy of it with Simple_BaseColorTintMultiply = this (linear, 1 = as stock), so the stones are
    sand-coloured like WRCG's Kenya (owner 2026-11-16). None for other meshes or when the stage has no stone_tint."""
    if not mesh or "GreElaSmallLimestone" not in str(mesh):
        return None
    import tempfile
    import tools.acrmod.stagectx as sc
    import wr_snowtrees as st
    slug = sc.cur().slug
    cfg = _cfg(slug) or {}
    light = cfg.get("stone_light", 1.0)                  # OFF by default: the 30 % lighter stones (2026-11-16) "se ven horribles"; a factor > 1 = lighter
    rgb = cfg.get("stone_tint") or ([1.0, 1.0, 1.0] if light and light != 1 else None)
    if not rgb:
        return None
    if light and light != 1:
        rgb = [float(v) * float(light) for v in rgb]
    legacy = next(iter(sorted((WORK / "acr" / "mods").glob(f"*/stages/{slug}/legacy"))), None)
    if legacy is None:
        print(f"    stones: no build folder for {slug}, stock material kept")
        return None
    new = f"/Game/Environments/{cfg['name']}/WrStones/MI_GreElaSmallLimestoneSand"
    if new not in _STONES_MADE:
        try:
            with tempfile.TemporaryDirectory(prefix="wr_stone_") as tmp:
                d = st._asset(_STONE_MI, tmp)
                n = 0
                for p in d["Exports"][0]["Data"]:
                    if p["Name"] != "VectorParameterValues":
                        continue
                    for item in p["Value"]:
                        f = {x["Name"]: x for x in item["Value"]}
                        if next(x["Value"] for x in f["ParameterInfo"]["Value"] if x["Name"] == "Name") == "Simple_BaseColorTintMultiply":
                            f["ParameterValue"]["Value"][0]["Value"].update(R=float(rgb[0]), G=float(rgb[1]), B=float(rgb[2]))
                            n += 1
                st._clone(d, _STONE_MI, new, {}, legacy, tmp)
            _STONES_MADE[new] = n
            print(f"    stones: sand tint x{list(rgb)} on the limestones ({'tint written' if n else 'NO tint parameter found'})")
        except Exception as e:                  # a failed copy must not stop the export: stock stones
            print(f"    stones: {type(e).__name__}: {e}, stock material kept")
            _STONES_MADE[new] = 0
    return [new] if _STONES_MADE[new] else None


def _far_tree_materials(mesh):
    """"far_tree_light": the far forest's impostor materials lightened (wr_fartrees.py); else None."""
    if not mesh:
        return None
    import wr_fartrees
    import tools.acrmod.stagectx as sc
    slug = sc.cur().slug
    cfg = _cfg(slug) or {}
    opts = wr_fartrees.options(cfg)
    if not opts:
        return None
    legacy = next(iter(sorted((WORK / "acr" / "mods").glob(f"*/stages/{slug}/legacy"))), None)
    if legacy is None:
        print(f"    far trees: no build folder for {slug}, stock materials kept")
        return None
    try:
        return wr_fartrees.materials_for(str(mesh).split(".")[0], opts, cfg["name"], legacy, WORK / "acr")
    except Exception as e:                      # a failed copy must not stop the export: stock materials
        print(f"    far trees: {type(e).__name__}: {e}, stock materials kept")
        return None


def _snow_tree_materials(mesh):
    """A snow stage's spruce: our snow copies of its materials, per slot (wr_snowtrees.py); else None."""
    if not mesh:
        return None
    import wr_snowtrees
    import tools.acrmod.stagectx as sc
    slug = sc.cur().slug
    cfg = _cfg(slug) or {}
    if not wr_snowtrees.is_snow(cfg):
        return None
    legacy = next(iter(sorted((WORK / "acr" / "mods").glob(f"*/stages/{slug}/legacy"))), None)
    if legacy is None:
        print(f"    snow trees: no build folder for {slug}, stock materials kept")
        return None
    return wr_snowtrees.materials_for(str(mesh).split(".")[0], cfg["name"], legacy, WORK / "acr")


# --- road crossings (WRCG side) -------------------------------------------------------------------------------------

CROSSING_DIR, ROAD_DIR = "INTERSECTIONBUILDSTEP", "ROADBUILDSTEP"


def _add_crossings():
    """WRCG builds a road crossing as a piece of its own (COMMON/LEVELS/<level>/INTERSECTIONBUILDSTEP/<NODE>.<node id>.PRM,
    placed by its PLM node like a road strip) beside the strips (ROADBUILDSTEP). The level export reads the strips only,
    so a stage had no road (no collision, no asphalt) where it runs through a crossing: on ES2_SPAIN/SS1 Riudecanyes an
    18 m hole a metre deep at s 1494-1508 m (ES2_SS3_Crossroad_1; owner drive 2026-11-09) and two gaps in the roundabout
    (Crossroad_4 and _5, s 6052 and 6130). The crossing pieces are put beside the strips in the extracted game files
    (work/wrcg_fs), where the export finds them like any other piece (by node name, stage mask and distance to the
    route); a crossing whose name is used twice (ES2_SPAIN's two 'New CrossRoad') is left out, as it could be matched
    to the wrong node."""
    import collections
    import shutil
    import tools.wrcg.gamefs as gf
    try:
        levels = Path(gf.files_root()) / "COMMON" / "LEVELS"
    except Exception:
        return
    for src in sorted(levels.glob(f"*/{CROSSING_DIR}")):
        dst = src.parent / ROAD_DIR
        if not dst.is_dir():
            continue
        files = sorted(src.glob("*.PRM"))
        stem = lambda f: f.name.rsplit(".", 2)[0].upper()
        count = collections.Counter(stem(f) for f in files)
        added = []
        for f in files:
            t = dst / f.name
            if count[stem(f)] == 1 and not t.exists():
                shutil.copy2(f, t)
                added.append(stem(f))
        if added:
            print(f"    crossings: {len(added)} road crossing pieces of {src.parent.name} added to the road pieces "
                  f"({', '.join(added)})")


# --- road pieces that are not a regular cross-section grid ----------------------------------------------------------

# WRCG's decals are 0.16 m deep (LEAVES_692: 5.1 x 5.2 x 0.16 m); the builder projects them at least MIN_DEPTH_M 1.2 m,
# so the dirt on Sanremo's road climbed the low stone wall beside it, and at MAX_TEX 1024 it looked coarse (owner
# 2026-11-10). Shallower and sharper here.
DECAL_MIN_DEPTH_M = 0.4
DECAL_MAX_TEX = 2048


# WRCG's tyre-mark decals in the bends (DE_ASPHALTTIREMARKS_*: grey curved streaks, 1.5 m deep) looked like dry leaves
# on the road and streaked the foot of the walls they reached (owner 2026-11-11, Pietrosella: "decals de hojas en el
# suelo, que siguen dando problemas ... quitamos todos estos decals"): left out; our own skid marks stay (wr_skids).
# Only Pietrosella has DE_ASPHALTTIREMARKS; WRCG's other tyre prints (TIRE_PRINT, TIRE_TRACE, ...) stay on every stage.
# Owner 2026-11-12: "lo que quería era quitar los decals de hojas secas en Italia, pero los decals de derrapes de ruedas
# tienen que seguir en todos los tramos": Sanremo's BIRCH_FALL_LEAVES left out too.
DECAL_DROP = r"TIREMARK|TYREMARK|LEAVES"


def _decals_by_stage(recs):
    """Stage build "decal_drop": regex of WRCG decal materials left out (Kenya: TURN_CLEAR and the tyre prints are the pale
    strip across the road), and "decal_min_side_m": a decal whose centre is closer than this to the route centre is left
    out too, so the decals stay at the sides of the road (owner 2026-11-16: decals on, but not the strip)."""
    import re
    import numpy as np
    import tools.acrmod.build_stage as bs
    import tools.acrmod.stagectx as sc
    slug = sc.cur().slug
    cfg = _cfg(slug) or {}
    out = recs
    rx, side = cfg.get("decal_drop"), float(cfg.get("decal_min_side_m") or 0.0)
    if rx:
        out = [r for r in out if not re.search(rx, str(r.get("material", "")), re.I)]
    if side > 0 and out:
        R = np.asarray(bs.route_wrcg(bs.load_cfg(slug)), float)[:, :2]
        out = [r for r in out if np.hypot(R[:, 0] - r["pos"][0], R[:, 1] - r["pos"][1]).min() >= side]
    if len(out) != len(recs):
        print(f"    [{slug}] decals: {len(recs) - len(out)} of {len(recs)} left out (decal_drop {rx!r}, closer than {side:g} m to the route centre), {len(out)} kept")
    return out


def _patch_decals():
    import re
    import tools.acrmod.decal_visual as dv
    dv.MIN_DEPTH_M = min(float(dv.MIN_DEPTH_M), DECAL_MIN_DEPTH_M)
    dv.MAX_TEX = max(int(dv.MAX_TEX), DECAL_MAX_TEX)
    if getattr(dv.collect_decals, "_wr", False):
        return
    orig = dv.collect_decals

    def collect_decals(*a, **k):
        recs = orig(*a, **k)
        try:
            keep = [r for r in recs if not re.search(DECAL_DROP, str(r.get("material", "")), re.I)]
            if len(keep) != len(recs):
                print(f"    decals: {len(recs) - len(keep)} WRCG decals left out (Pietrosella tyre marks that looked like leaves, dry leaves)")
            keep = _decals_by_stage(keep)
            return keep
        except Exception:
            return recs
    collect_decals._wr = True
    dv.collect_decals = collect_decals


# The baked road blends into the terrain over fringe_m (2 m in the builder): a wide, blurred band along every road edge
# (owner 2026-11-10: "los bordes de la carretera ... a veces se ven difuminados cutres"). Narrower here.
ROAD_FRINGE_M = 0.8


def _patch_road_seams():
    """Seams between two sections of one road (Seyabei KE_SS2_ROAD_14 and ROAD_08 km 3.087, owner 2026-11-16: "franjas"): the
    builder's road layers give the outer-edge value (t = 1, opacity 0) to some vertices in the middle of the carriageway
    that belong to no border triangle, so the gravel fades out across the road and the smooth earth under it shows. Such
    vertices (723 on Seyabei, about 40 seams) get t = 0 (interior). Border vertices, piece ends and crossings are untouched."""
    import numpy as np
    import tools.acrmod.ittiri_road_layers as rl
    if getattr(rl.road_layers, "_wr_seams", False):
        return
    orig = rl.road_layers

    def road_layers(*a, **k):
        L = orig(*a, **k)
        try:
            tri, border = np.asarray(L["triangles"]), np.asarray(L["border"], bool)
            on_border = np.zeros(len(L["positions"]), bool)
            on_border[tri[border].ravel()] = True
            t = np.array(L["t"], float)
            bad = (rl.opacity(t) < 0.99) & ~on_border & (np.asarray(L["end_fade"]) >= 0.99)
            try:                                     # stage build "road_solid": [{"m": [from, to], "lateral_m": 3.0}]
                import tools.acrmod.build_stage as bs
                import tools.acrmod.stagectx as sc
                slug = sc.cur().slug
                R = np.asarray(bs.route_wrcg(bs.load_cfg(slug)), float)[:, :2]
                for z in (_cfg(slug) or {}).get("road_solid") or []:
                    a, b = int(z["m"][0]), int(z["m"][1])
                    seg = R[a:b + 1]
                    d = np.hypot(L["positions"][:, None, 0] - seg[None, :, 0], L["positions"][:, None, 1] - seg[None, :, 1]).min(1)
                    hit = (d < float(z.get("lateral_m", 3.0))) & (t > 0.5)
                    bad |= hit
                    print(f"    road layers: {int(hit.sum())} edge vertices across the road made opaque at route m {a}-{b}")
            except Exception as e:
                print(f"    road layers: road_solid not applied ({type(e).__name__}: {e})")
            if bad.any():
                t[bad] = 0.0
                L = dict(L, t=t)
                print(f"    road layers: {int(bad.sum())} vertices in the middle of the road wrongly marked as outer edge (seams between road sections) made opaque")
        except Exception as e:                       # the stock layers are kept
            print(f"    road layers: seam fix not applied ({type(e).__name__}: {e})")
        return L

    road_layers._wr_seams = True
    rl.road_layers = road_layers


def _patch_road_fringe():
    import tools.acrmod.terrain_bake as tb
    if getattr(tb.add_baked_terrain, "_wr", False):
        return
    orig = tb.add_baked_terrain

    def add_baked_terrain(*a, **k):
        k["fringe_m"] = min(float(k.get("fringe_m", 2.0)), ROAD_FRINGE_M)
        return orig(*a, **k)

    add_baked_terrain._wr = True
    tb.add_baked_terrain = add_baked_terrain


def _patch_road_grid(columns=11):
    """The builder's road layers need every road piece as a grid of cross-sections (rows of the same vertex count);
    ES2_SPAIN/SS1 has one piece (1020 vertices, 83 x 47 m, a junction) that is not, and the whole stage failed with
    'no cross-section grid found'. For such a piece only: its vertices sorted along its main axis into rows of
    `columns` (the count of the pieces around it), each row sorted across, the gaps left to the builder's own filling."""
    import numpy as np
    import tools.acrmod.ittiri_road_layers as rl
    if getattr(rl.grid_of, "_wr", False):
        return
    orig = rl.grid_of

    def grid_of(V):
        try:
            return orig(V)
        except ValueError:
            P = np.asarray(V, float)
            xy = P[:, :2] - P[:, :2].mean(0)
            _APPROX.append(np.round(P[:, :2], 3))         # for _special_layouts (its vertices)
            axis = np.linalg.svd(xy, full_matrices=False)[2][0]
            s, t = xy @ axis, xy @ np.array([-axis[1], axis[0]])
            order = np.argsort(s, kind="stable")
            rows = -(-len(P) // columns)
            G = -np.ones((rows, columns), int)
            for r in range(rows):
                part = order[r * columns:(r + 1) * columns]
                part = part[np.argsort(t[part])]
                G[r, :len(part)] = part
            G = rl._fill_missing(G) if (G < 0).any() else G
            print(f"    road layers: a {len(P)}-vertex road piece is no cross-section grid, approximated as "
                  f"{rows} x {columns}")
            return G

    grid_of._wr = True
    rl.grid_of = grid_of
    orig_layers = rl.road_layers

    def road_layers(*a, **k):
        """Triangles of an approximated piece can be degenerate; the road overlay bake inverts every triangle and
        stopped with 'Singular matrix'. Triangles with no area in plan or in road coordinates (u, v) are dropped."""
        L = orig_layers(*a, **k)
        try:
            _special_layouts(L, a[0] if a else k.get("npz") or rl.NPZ)
        except Exception as e:
            print(f"    road layers: rings and crossings left as they are ({type(e).__name__}: {e})")
        try:
            _main_road_wins(L, a[0] if a else k.get("npz") or rl.NPZ)
        except Exception as e:
            print(f"    road layers: side roads kept on the stage's road ({type(e).__name__}: {e})")
        P, T = np.asarray(L["positions"], float), np.asarray(L["triangles"])
        def area(X):
            a_, b_ = X[T[:, 1]] - X[T[:, 0]], X[T[:, 2]] - X[T[:, 0]]
            return np.abs(a_[:, 0] * b_[:, 1] - a_[:, 1] * b_[:, 0]) / 2.0
        uv = np.stack([np.asarray(L["u"], float), np.asarray(L["v"], float)], 1)
        a_xy, a_uv = area(P[:, :2]), area(uv)
        keep = (a_xy > 1e-6 * max(float(np.median(a_xy)), 1e-12)) & (a_uv > 1e-6 * max(float(np.median(a_uv)), 1e-12))
        if not keep.all():
            for key, arr in list(L.items()):          # every per-triangle array (triangles, border, ...)
                if hasattr(arr, "__len__") and not isinstance(arr, (str, dict)) and len(arr) == len(T) != len(P):
                    L[key] = np.asarray(arr)[keep]
            print(f"    road layers: {int((~keep).sum())} degenerate road triangles dropped")
        try:
            _join_road_ends(L, a[0] if a else k.get("npz") or rl.NPZ)
        except Exception as e:
            print(f"    road layers: piece ends kept as they are ({type(e).__name__}: {e})")
        try:
            _drop_tunnel_road(L)
        except Exception as e:
            print(f"    road layers: tunnel road kept ({type(e).__name__}: {e})")
        _clear_internal_road_borders(L)
        return L

    road_layers._wr = True
    rl.road_layers = road_layers


# The road overlay fades every road piece over END_FADE_M (4 m) at an end it takes as open; at a junction the branch
# pieces and the crossing pieces between them (Riudecanyes CROSSROAD_3-6, 1 m long: end_fade 0-0.76, all of it faded)
# came out transparent, the terrain showing through the asphalt (owner 2026-11-10, the roundabouts). An end that meets
# another road piece (a vertex of another piece within JOIN_M of its end row) is not faded; crossing pieces never are.
JOIN_M = 1.0
ROAD_WIDTH_M = 7.0


def _clear_internal_road_borders(layers):
    """Remove the visual fringe at shared edges between surface slots."""
    import numpy as np

    points = np.asarray(layers["positions"], float)
    tris = np.asarray(layers["triangles"])
    if not len(tris):
        return
    edges = np.sort(np.concatenate([tris[:, [0, 1]], tris[:, [1, 2]], tris[:, [2, 0]]]), axis=1)
    opposite = np.concatenate([tris[:, 2], tris[:, 0], tris[:, 1]])
    _, first, count = np.unique(edges, axis=0, return_index=True, return_counts=True)
    boundary = first[count == 1]

    # The WRCG slots have separate vertices for the very same edge.
    _, weld = np.unique(np.rint(points * 1000).astype(np.int64), axis=0, return_inverse=True)
    endpoints = edges[boundary]
    canonical = weld[endpoints]
    reverse = canonical[:, 0] > canonical[:, 1]
    endpoints[reverse] = endpoints[reverse, ::-1]
    canonical = weld[endpoints]
    _, group, edge_count = np.unique(canonical, axis=0, return_inverse=True, return_counts=True)
    start, end = points[endpoints[:, 0], :2], points[endpoints[:, 1], :2]
    edge, interior = end - start, points[opposite[boundary], :2] - start
    side = np.sign(edge[:, 0] * interior[:, 1] - edge[:, 1] * interior[:, 0])
    balanced = np.bincount(group, weights=side) == 0
    shared = (edge_count[group] == 2) & balanced[group] & (side != 0)
    inside = np.setdiff1d(canonical[shared], canonical[~shared])
    mask = np.isin(weld, inside) & (np.asarray(layers["t"]) > 0)
    if mask.any():
        fringe = np.asarray(layers["t"]).copy()
        fringe[mask] = 0.0
        layers["t"] = fringe
        print(f"    road layers: {int(mask.sum())} internal seam vertices no longer faded")


def _piece_of_vertex(L, npz):
    """(npz, positions, triangles, tri_piece, piece per vertex) of the road collision the layers were made from: the
    path given to road_layers, else the stage's own files (the builder passes none and the module default is
    another stage's), the one with as many vertices as the layers."""
    import numpy as np
    P = np.asarray(L["positions"], float)
    cands = [npz] if isinstance(npz, (str, Path)) else []
    try:
        import tools.acrmod.stagectx as sc
        sd = WORK / "wrcg" / sc.cur().slug
        cands += [sd / "collision_all_prm_junctions_v5.npz", sd / "collision_all_prm.npz"]
    except Exception:
        pass
    c = None
    for f in cands:
        try:
            d = np.load(f)
        except (OSError, ValueError):
            continue
        if "tri_piece" in d.files and len(d["positions"]) == len(P):
            c = d
            break
    if c is None:
        print(f"    road layers: no road collision with {len(P)} vertices found for the piece fixes ({cands})")
        return None
    T, tp = c["triangles"], c["tri_piece"].astype(int)
    vp = np.full(len(P), -1, int)
    vp[T.ravel()] = np.repeat(tp, 3)
    return c, P, T, tp, vp


_APPROX = []                    # centres of the road pieces laid out by our grid_of fallback (this process)


def _special_layouts(L, npz):
    """Road coordinates of the road pieces the builder's grid does not fit.
    - Roundabout rings our grid_of fallback laid out (a ring around a hole, no cross-section grid: Riudecanyes ROAD_18,
      s 5866, 701 vertices, radius 6-17 m): u across the ring (radius between its inner and outer edge at that angle),
      v along it (arc length in the stage's v units per metre), t (border) on the mesh's own boundary. Along an axis
      they came out scrambled: the asphalt looked broken (owner 2026-11-10, "el asfalto de las rotondas ... roto de
      textura y/o UVs"). A ring with a real grid (ROAD_22) keeps the builder's.
    - Crossing pieces (CROSSROAD_*, about 1 m long) and the other irregular slots our fallback laid out: plain
      coordinates in plan (u across the road over ROAD_WIDTH_M, v along it), border on the mesh boundary. From the grid
      some of their triangles had no area in (u, v) and were dropped, and their borders were scattered: holes."""
    import numpy as np
    got = _piece_of_vertex(L, npz)
    if got is None:
        return
    c, P, T, tp, vp = got
    u, v, t = (np.asarray(L[k], float).copy() for k in ("u", "v", "t"))
    S = T[:: max(1, len(T) // 20000)]                     # v units per metre on the stage's roads
    A = np.stack([P[S[:, 1], :2] - P[S[:, 0], :2], P[S[:, 2], :2] - P[S[:, 0], :2]], 1)
    b = np.stack([v[S[:, 1]] - v[S[:, 0]], v[S[:, 2]] - v[S[:, 0]]], 1)
    ok = np.abs(np.linalg.det(A)) > 1e-4
    vpm = float(np.median(np.linalg.norm(np.linalg.solve(A[ok], b[ok][..., None])[..., 0], axis=1)))

    def boundary(tris):
        e = np.sort(np.concatenate([tris[:, [0, 1]], tris[:, [1, 2]], tris[:, [2, 0]]]), axis=1)
        uniq, cnt = np.unique(e, axis=0, return_counts=True)
        return np.unique(uniq[cnt == 1].ravel())

    route = _route_xy()

    def plain(vs, tris):
        xy = P[vs, :2] - P[vs, :2].mean(0)
        ax = np.linalg.svd(xy, full_matrices=False)[2]
        a0, a1 = xy @ ax[0], xy @ ax[1]
        bnd = np.isin(vs, boundary(tris))
        if np.ptp(a0) > LONG_PIECE_RATIO * max(np.ptp(a1), 1.0) and np.ptp(a0) > LONG_PIECE_M:
            # a road piece, not a crossing (Sanremo's main pieces, 120 m): u across, v along. Along the stage's route
            # when it follows it (v = route distance, the same on both sides of a joint), else along its own axis;
            # its ends are not borders (each joint showed the terrain through, a line across the road)
            if route is not None:
                s_, off, d_ = _route_coords(route, P[vs, :2])
                if np.median(d_) <= ROUTE_PIECE_M:
                    u[vs] = 0.5 + (off - np.median(off)) / ROAD_WIDTH_M
                    v[vs] = s_ * vpm + 1000.0
                    end = (s_ <= s_.min() + END_ROW_M) | (s_ >= s_.max() - END_ROW_M)
                    t[vs] = (bnd & ~end).astype(float)
                    return "route"
            u[vs] = 0.5 + a1 / ROAD_WIDTH_M
            v[vs] = a0 * vpm + 1000.0
            end = (a0 <= a0.min() + END_ROW_M) | (a0 >= a0.max() - END_ROW_M)
            t[vs] = (bnd & ~end).astype(float)
            return "axis"
        if route is not None:                             # a crossing the stage drives through: along the route
            s_, off, d_ = _route_coords(route, P[vs, :2])
            if np.median(d_) <= 3.0:
                u[vs] = 0.5 + (off - np.median(off)) / ROAD_WIDTH_M
                v[vs] = s_ * vpm + 1000.0
                t[vs] = bnd.astype(float)
                return "crossing on the route"
        u[vs] = 0.5 + a0 / ROAD_WIDTH_M                   # not clipped: a clipped corner has no area
        v[vs] = a1 * vpm + 1000.0
        t[vs] = bnd.astype(float)
        return "crossing"

    groups = []                                           # (label, vertex ids, triangles)
    keymap = {}
    for k_, A_ in enumerate(_APPROX):
        for row in map(tuple, A_):
            keymap[row] = k_
    if keymap:
        slot = np.array([keymap.get(x, -1) for x in map(tuple, np.round(P[:, :2], 3))])
        for k_ in range(len(_APPROX)):
            vs = np.nonzero(slot == k_)[0]
            tris = T[np.all(slot[T] == k_, axis=1)]
            if len(vs) >= 3 and len(tris):
                groups.append((str(c["piece_names"][np.bincount(vp[vs][vp[vs] >= 0]).argmax()]).split(".")[0], vs, tris))
    done = set()
    rings, plains = [], []
    for label, vs, tris in groups:
        xy = P[vs, :2] - P[vs, :2].mean(0)
        r = np.hypot(xy[:, 0], xy[:, 1])
        th = np.arctan2(xy[:, 1], xy[:, 0])
        if len(vs) >= 60 and len(np.unique(np.floor((th + np.pi) / np.radians(10.0)))) >= 33 and r.min() >= 0.25 * r.max():
            nb = 72
            hist = np.histogram(th, bins=nb, range=(-np.pi, np.pi))[0]
            start = -np.pi + (int(np.argmin(hist)) + 0.5) * (2 * np.pi / nb)
            bi = (np.floor((th + np.pi) / (2 * np.pi / nb)).astype(int)) % nb
            rin, rout = np.full(nb, np.inf), np.full(nb, -np.inf)
            for k_ in range(nb):
                m = np.isin(bi, [(k_ - 1) % nb, k_, (k_ + 1) % nb])
                if m.any():
                    rin[k_], rout[k_] = r[m].min(), r[m].max()
            u[vs] = np.clip((r - rin[bi]) / np.maximum(rout[bi] - rin[bi], 0.5), 0.0, 1.0)
            v[vs] = ((th - start) % (2 * np.pi)) * float(np.median(r)) * vpm
            t[vs] = np.isin(vs, boundary(tris)).astype(float)
            rings.append(f"{label} ({len(vs)} vertices, radius {r.min():.0f}-{r.max():.0f} m)")
        else:
            kind = plain(vs, tris)
            plains.append(f"{label} ({len(vs)} vertices, {kind})")
        done.update(vs.tolist())
    for piece in np.unique(tp):
        name = str(c["piece_names"][piece]).upper()
        if not any(w in name for w in ("CROSSROAD", "INTERSECTION")):
            continue
        tris = T[tp == piece]
        vs = np.setdiff1d(np.unique(tris.ravel()), np.fromiter(done, int, len(done)))
        if len(vs) >= 3:
            plain(vs, tris)
            plains.append(name.split(".")[0])
    # every road piece along the route: v = the route distance, so v runs on across the joints (each piece's own v
    # began anew: the asphalt texture jumped at every joint, a line across the road)
    n_route = 0
    if route is not None:
        for piece in np.unique(tp):
            name = str(c["piece_names"][piece]).upper()
            if any(w in name for w in ("CROSSROAD", "INTERSECTION", "ROUNDABOUT")):
                continue
            vs = np.setdiff1d(np.unique(T[tp == piece].ravel()), np.fromiter(done, int, len(done)))
            if len(vs) < 3:
                continue
            s_, off, d_ = _route_coords(route, P[vs, :2])
            if np.median(d_) <= ROUTE_PIECE_M:
                v[vs] = s_ * vpm + 1000.0
                n_route += 1
        if n_route:
            print(f"    road layers: {n_route} road pieces along the route with the route distance as v (no jump at joints)")
    if rings or plains or n_route:
        L["u"], L["v"], L["t"] = u, v, t
    if rings:
        print(f"    road layers: roundabout rings laid out around them: {', '.join(rings)}")
    if plains:
        print(f"    road layers: plain road coordinates for {len(plains)} crossings / irregular slots: {', '.join(plains)}")


# Tunnels (owner 2026-11-11, Pietrosella: "el túnel tiene la carretera por encima"): the road layers are baked onto the
# terrain tiles in plan, so the road inside a tunnel was painted on the hill above it. Road triangles with the terrain
# more than TUNNEL_COVER_M above all their corners are left out of the layers (the tunnel's own mesh is its floor).
TUNNEL_COVER_M = 3.0


def terrain_height_fn(slug=None):
    """(x, y) -> WRCG terrain height (m) of the stage, from its 0.5 m heightfield (nearest sample)."""
    import numpy as np
    import tools.acrmod.stagectx as sc
    slug = slug or sc.cur().slug
    tdir = WORK / "wrcg" / slug / "terrain"
    H = np.load(tdir / "heights_0p5m.npy", mmap_mode="r")
    w = json.loads((tdir / "meta.json").read_text(encoding="utf-8")).get("window") or {}
    ox, oy = (w.get("origin_xy") or (-2048.0, -2048.0))

    def h(x, y):
        j = np.clip(np.round((np.asarray(x, float) - ox) / 0.5).astype(int), 0, H.shape[1] - 1)
        i = np.clip(np.round((np.asarray(y, float) - oy) / 0.5).astype(int), 0, H.shape[0] - 1)
        return np.asarray(H[i, j], float)
    return h


# Water over the road (owner 2026-11-11, Pietrosella: "antes del túnel hay un parche como metalizado en la carretera"):
# WRCG's lake Ocean_9 is at 390.2 m and the road along its shore comes down to 390.0 at s 5400-5426, so ACR's water
# plane lay on the asphalt. Lowering the lake 1 m (1st try) left its banks dry (2nd drive: "el nivel del agua creo que
# no está bien. Debería ir por donde he pintado la línea", the foot of the cliffs): the lake keeps WRCG's level and only
# its water cells (water_visual.water_cells, 4 m) whose centre is within WATER_ROAD_M of road lower than the water +
# WATER_FREEBOARD_M are left out (the road hides what is left of the lake's edge under it). Planes that would lose more
# than WATER_MAX_SHARE of their cells are not a lake brimming over a road (Brattby's lie 30 m over it): left as they are.
WATER_ROAD_M = 3.0
WATER_FREEBOARD_M = 0.3
WATER_DEPTH_M = 1.5                            # road deeper under the plane than this: not a road at the water's edge
WATER_MAX_SHARE = 0.1


def _road_points(slug):
    import numpy as np
    import wr_groundcover as gc
    r = np.load(WORK / "wrcg" / slug / "collision_all_prm.npz")
    return gc._tri_points(r["positions"], r["triangles"], 1.0)


def dry_road_cells(cells, water_z, pts):
    """(the water cells off the road, how many were on it)."""
    import numpy as np
    import wr_groundcover as gc
    c = np.asarray(cells, float)
    if not len(c):
        return cells, 0
    lo, hi = c[:, :2].min(0) - WATER_ROAD_M - 2, c[:, :2].max(0) + WATER_ROAD_M + 2
    q = pts[(pts[:, 0] >= lo[0]) & (pts[:, 0] <= hi[0]) & (pts[:, 1] >= lo[1]) & (pts[:, 1] <= hi[1]) &
            (pts[:, 2] < water_z + WATER_FREEBOARD_M) & (pts[:, 2] > water_z - WATER_DEPTH_M)]
    if not len(q):
        return cells, 0
    g = 1.0
    low = np.zeros((int((hi[1] - lo[1]) / g) + 1, int((hi[0] - lo[0]) / g) + 1), bool)
    low[((q[:, 1] - lo[1]) / g).astype(int), ((q[:, 0] - lo[0]) / g).astype(int)] = True
    d = gc._dist(low, WATER_ROAD_M + g, g)
    d = d[((c[:, 1] - lo[1]) / g).astype(int), ((c[:, 0] - lo[0]) / g).astype(int)]
    on = np.isfinite(d) & (d <= WATER_ROAD_M)
    if not on.any() or on.mean() > WATER_MAX_SHARE:
        return cells, 0
    keep = ~on
    out = cells[keep] if hasattr(cells, "shape") else [x for x, k in zip(cells, keep) if k]
    return out, int(on.sum())


# The start (owner 2026-11-11: "el marshall debería estar parado en el punto de salida, al medio de la carretera
# esperando a que el conductor llegue, después hace unas señales con la mano para que te acerques y después se aparta
# ... Ahora mismo de repente el marshall aparece de golpe al parar al punto de salida"). The builder's start sequence
# follows Hafren South (start_marshal: the car spawns, the sequence's Start trigger START_M = 77 m before the marshal,
# ComeCloser COME_CLOSER_M = 33 m), squeezed into the pre-start section it finds before our route (WRCG's start lane):
# none on Pietrosella, Panzerplatte, Sävar, Brattby and three reverses, so the car spawned 8 m from the marshal with
# both triggers behind it. Now the pre-start goes on backwards along WRCG's road (its full track spline, then the middle
# of the road collision, wr_finish.runoff backward) to PRE_START_M where the road allows.
PRE_START_M = 90.0
PRE_KEEP_M = 48.0                              # stages with a WRCG start lane this long keep it, shorter ones are lengthened to PRE_START_M (owner 2026-11-18: WRC's own start whenever it has at least 48 m; Greece 49, Spain 48.9; was 30)
_PRE = {}


def _patch_prestart():
    import numpy as np
    import tools.acrmod.build_stage as bs
    if getattr(bs.pre_route_wrcg, "_wr", False):
        return
    orig = bs.pre_route_wrcg

    def pre_route_wrcg(cfg, *a, **k):
        pre = orig(cfg, *a, **k)
        try:
            slug = cfg.get("slug")
            P = np.asarray(pre, float).reshape(-1, 3)
            have = float(np.linalg.norm(np.diff(P[:, :2], axis=0), axis=1).sum()) if len(P) > 1 else 0.0
            if not slug or have >= PRE_KEEP_M:                # a start lane of WRCG's own: kept
                return pre
            if slug not in _PRE:
                import wr_finish
                sd = WORK / "wrcg" / slug
                R = np.loadtxt(sd / "route_centerline_1m.csv", delimiter=",", skiprows=1)
                path = np.vstack([P, R[:, 1:4]]) if len(P) else R[:, 1:4]
                Rs = np.column_stack([np.arange(len(path), dtype=float), path])
                back = wr_finish.runoff(sd, Rs, PRE_START_M - have, backward=True)
                _PRE[slug] = np.vstack([back[::-1], P]) if len(back) else P
                n = len(_PRE[slug])
                print(f"    pre-start: {have:.0f} m from the builder, {len(back)} m more backwards along WRCG's road "
                      f"({n} points): the car comes up to the start marshal as on ACR's stages")
            out = _PRE[slug]
            return out.astype(np.asarray(pre).dtype) if hasattr(pre, "dtype") and len(np.asarray(pre)) else out
        except Exception as e:
            print(f"    pre-start: kept as the builder's ({type(e).__name__}: {e})")
            return pre

    pre_route_wrcg._wr = True
    bs.pre_route_wrcg = pre_route_wrcg


def _patch_psi_names():
    """Kenya's level lists a prop instance whose name is a number: psi_excluded's regex search needs a string."""
    import tools.wrcg.prop_instances as pi
    if getattr(pi.psi_excluded, "_wr", False):
        return
    orig = pi.psi_excluded

    def psi_excluded(psi):
        return orig(psi if isinstance(psi, str) else str(psi))
    psi_excluded._wr = True
    pi.psi_excluded = psi_excluded


def _patch_water():
    import numpy as np
    import tools.acrmod.water_visual as wv
    if getattr(wv.water_cells, "_wr", False):
        return
    orig = wv.water_cells
    pts = {}

    def water_cells(node, *a, **k):
        cells = orig(node, *a, **k)
        try:
            import tools.acrmod.stagectx as sc
            slug = sc.cur().slug
            if slug not in pts:
                pts[slug] = _road_points(slug)
            z = float(np.asarray(node["pos"], float).reshape(-1)[2])
            out, n = dry_road_cells(cells, z, pts[slug])
            if n:
                print(f"    water: {n} cells of {node.get('name')} (z {z:.1f}) left off the road, the lake at its level")
            return out
        except Exception as e:
            print(f"    water: road check skipped ({type(e).__name__}: {e})")
            return cells
    water_cells._wr = True
    wv.water_cells = water_cells


def _drop_pacenote_tokens(slug):
    """"pacenote_drop_tokens": ["WATER"]: those words are taken out of the stage's pacenote calls (work/wrcg/<slug>/
    pacenotes.json; the original kept as pacenotes.orig.json, so it is redone from it every build). Owner 2026-11-15:
    Seyabei's co-driver said "water" and there is none in ACR."""
    cfg = _cfg(slug) or {}
    words = {str(w).upper() for w in (cfg["pacenote_drop_tokens"] if "pacenote_drop_tokens" in cfg else ["WATER"])}      # ACR has no water: universal default
    f = WORK / "wrcg" / slug / "pacenotes.json"
    if not words or not f.exists():
        return
    orig = f.with_name("pacenotes.orig.json")
    if not orig.exists():
        orig.write_bytes(f.read_bytes())
    d = json.loads(orig.read_text(encoding="utf-8"))
    n = [0]

    def clean(o):
        if isinstance(o, dict):
            out = {}
            for k, v in o.items():
                if k == "tokens" and isinstance(v, list):
                    n[0] += sum(str(t).upper() in words for t in v)
                    v = [t for t in v if str(t).upper() not in words]
                out[k] = clean(v) if k != "tokens" else v
            return out
        if isinstance(o, list):
            return [clean(x) for x in o]
        return o
    f.write_text(json.dumps(clean(d), ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"    [{slug}] pacenotes: {n[0]} call words left out ({', '.join(sorted(words))})")


def _patch_no_water():
    """"water": false: the stage's WRCG lakes (Ocean_n) are not drawn: ACR has no such puddles, the road stays plain gravel."""
    import tools.acrmod.water_visual as wv
    if getattr(wv.ocean_nodes, "_wr_none", False):
        return
    orig = wv.ocean_nodes

    def ocean_nodes(level, *a, **k):
        try:
            import tools.acrmod.stagectx as sc
            if (_cfg(sc.cur().slug) or {}).get("water", True) is False:
                return []
        except Exception:
            pass
        return orig(level, *a, **k)

    ocean_nodes._wr_none = True
    wv.ocean_nodes = ocean_nodes


def _patch_water_surface():
    """\"water_surface\": the road under the stage's water planes gets that ACR physical material (wr_water.py)."""
    import tools.acrmod.ittiri_container as ic
    if getattr(ic.meshes, "_wr_water", False):
        return
    orig = ic.meshes

    def meshes(offset=(0.0, 0.0, 0.0), *a, **k):
        out = orig(offset, *a, **k)
        try:
            import numpy as np
            import tools.acrmod.bakeddata as bd
            import tools.acrmod.stagectx as sc
            import tools.acrmod.water_visual as wv
            import wr_water
            cfg = _cfg(sc.cur().slug) or {}
            pm = wr_water.water_pm(cfg)
            if not pm:
                return out
            waters = []
            for node in wv.ocean_nodes(cfg["wrcg_level"]):
                cells = np.asarray(wv.water_cells(node))
                if len(cells):
                    waters.append((cells[:, :2], float(np.asarray(node["pos"], float).reshape(-1)[2])))
            adjusted, moved = wr_water.split(out, offset, waters, pm, bd.Mesh)
            if moved:
                print(f"    water: {moved} submerged road triangles use {pm}")
            return adjusted
        except Exception as e:
            print(f"    water: puddle surface skipped ({type(e).__name__}: {e})")
            return out

    meshes._wr_water = True
    ic.meshes = meshes


def _drop_tunnel_road(L):
    import numpy as np
    P, T = np.asarray(L["positions"], float), np.asarray(L["triangles"])
    covered = terrain_height_fn()(P[:, 0], P[:, 1]) - P[:, 2] > TUNNEL_COVER_M
    drop = covered[T].all(1)
    if not drop.any():
        return
    keep = ~drop
    for key, arr in list(L.items()):
        if hasattr(arr, "__len__") and not isinstance(arr, (str, dict)) and len(arr) == len(T) != len(P):
            L[key] = np.asarray(arr)[keep]
    print(f"    road layers: {int(drop.sum())} road triangles inside tunnels left out (they were painted on the hill above)")


# Long irregular road pieces (owner 2026-11-10, Sanremo: "hay unas líneas que cruzan la carretera cada x metros"): the
# planar layout took the piece's main axis as u (across), so on a 120 m piece the asphalt texture's sides repeated every
# ROAD_WIDTH_M along the road, and its whole outline, ends included, was a border (transparent at every joint).
LONG_PIECE_RATIO, LONG_PIECE_M = 2.5, 15.0     # longer than 2.5 x its width and 15 m: a road piece, not a crossing
ROUTE_PIECE_M = 8.0                            # a piece this close to the route (median) takes its distance as v
END_ROW_M = 1.0                                # boundary vertices this close to a piece's ends: joint, not border


_ROUTE_XY = {}


def _route_xy():
    """(s, xy) of the stage's route centreline (WRCG world metres), or None; with the road the car drives before the
    start (pre-start, negative s) and after the end (run-off to the stop control), WRCG's road both ways
    (wr_finish.runoff): the pieces there are laid out along it too."""
    import numpy as np
    try:
        import tools.acrmod.stagectx as sc
        slug = sc.cur().slug
        if slug in _ROUTE_XY:
            return _ROUTE_XY[slug]
        sd = WORK / "wrcg" / slug
        a = np.loadtxt(sd / "route_centerline_1m.csv", delimiter=",", skiprows=1)
        s, xy = a[:, 0], a[:, 1:3]
        try:
            import wr_finish
            back = wr_finish.runoff(sd, a, PRE_START_M + 20.0, backward=True)[:, :2]
            fwd = wr_finish.runoff(sd, a, 200.0)[:, :2]
            s = np.concatenate([-np.arange(len(back), 0, -1, dtype=float) + s[0], s, s[-1] + 1.0 + np.arange(len(fwd))])
            xy = np.vstack([back[::-1], xy, fwd])
        except Exception as e:
            print(f"    road layers: route without its ends ({type(e).__name__}: {e})")
        _ROUTE_XY[slug] = (s, xy)
        return _ROUTE_XY[slug]
    except Exception:
        return None


# Junction mouths (owner 2026-11-11, Pietrosella 3rd drive: "texturas mal orientadas de asfalto" before the start, in
# the village before the climb to the tunnel, at the junction after it): a side road's piece reaches onto the stage's
# road, and the bake drew it there with its own orientation, across the stage's asphalt (Pietrosella: CROSS_01 s 1891,
# OFFROAD04 s 2879 and 4250, the village pieces s 3800-3920, OFFROAD01 s 6250, OFFROAD09 s 6869). Where a piece that is
# not along the route lies on one that is (MAIN_INSET_M inside its edge), it is left out of the layers: the stage's
# road shows there, its side road starts at its edge.
MAIN_INSET_M = 0.6


ROUTE_LANE_HALF_M = 3.0


def _align_on_route(L, P, T, tp, is_main, drop, route, c):
    """The asphalt across the road where the car drives: a route piece whose own u runs along the road in places (the
    flare at a junction: Pietrosella ROAD16 s 850, ROAD10/11 s 2850, ROAD03 s 6850) gets u from its width across the
    route; a side road's piece the route itself crosses (no route piece under it) gets the route's coordinates within
    ROUTE_LANE_HALF_M of the route."""
    import re
    import numpy as np
    u, v = np.asarray(L["u"], float).copy(), np.asarray(L["v"], float).copy()
    A = np.stack([P[T[:, 1], :2] - P[T[:, 0], :2], P[T[:, 2], :2] - P[T[:, 0], :2]], 1)
    ok = np.abs(np.linalg.det(A)) > 1e-6
    bv = np.stack([v[T[:, 1]] - v[T[:, 0]], v[T[:, 2]] - v[T[:, 0]]], 1)
    gv = np.zeros((len(T), 2))
    gv[ok] = np.linalg.solve(A[ok], bv[ok][..., None])[..., 0]
    vpm = float(np.median(np.linalg.norm(gv[ok][:: max(1, int(ok.sum()) // 20000)], axis=1)))
    bu = np.stack([u[T[:, 1]] - u[T[:, 0]], u[T[:, 2]] - u[T[:, 0]]], 1)
    gu = np.zeros((len(T), 2))
    gu[ok] = np.linalg.solve(A[ok], bu[ok][..., None])[..., 0]
    n_main, n_side = [], []
    for piece in np.unique(tp):
        tris = (tp == piece) & ~drop
        if not tris.any():
            continue
        vs = np.unique(T[tris].ravel())
        s_, off, d_ = _route_coords(route, P[vs, :2])
        if is_main[np.argmax(tp == piece)]:
            continue                       # (a route piece keeps its own u: re-made from its width at a junction
            # flare it came out worse, Pietrosella ROAD03 s 6850)
        elif re.search(r"OFFROAD|CROSS|JUNCTION|VILLAGE|INTERSECTION", str(c["piece_names"][piece]), re.I):
            # (side roads only: a stage road piece that leaves the route keeps its own layout, Arganil ROAD_04...)
            lane = d_ <= ROUTE_LANE_HALF_M
            if lane.sum() < 3:
                continue
            u[vs[lane]] = 0.5 + off[lane] / ROAD_WIDTH_M
            v[vs[lane]] = s_[lane] * vpm + 1000.0
            n_side.append(str(c["piece_names"][piece]).split(".")[0])
    if n_main or n_side:
        L["u"], L["v"] = u, v
        print(f"    road layers: asphalt turned along the route on {len(n_main)} route pieces with a junction flare "
              f"({', '.join(n_main[:8])}) and on the lane of {len(n_side)} side pieces the route crosses "
              f"({', '.join(n_side[:8])})")


def _main_road_wins(L, npz):
    import numpy as np
    import wr_groundcover as gc
    got = _piece_of_vertex(L, npz)
    route = _route_xy()
    if got is None or route is None:
        return
    c, P, Tc, tp, vp = got
    T = np.asarray(L["triangles"])
    if len(T) != len(Tc):
        return
    main = set()
    for piece in np.unique(tp):
        name = str(c["piece_names"][piece]).upper()
        if "ROUNDABOUT" in name:
            continue
        vs = np.unique(T[tp == piece].ravel())
        if len(vs) < 3:
            continue
        _, _, d_ = _route_coords(route, P[vs, :2])
        if np.median(d_) <= (3.0 if any(w in name for w in ("CROSS", "INTERSECTION")) else ROUTE_PIECE_M):
            main.add(int(piece))
    if not main:
        return
    is_main = np.isin(tp, list(main))
    lo = P[:, :2].min(0) - 2.0
    shape = tuple((np.ceil((P[:, :2].max(0) + 2.0 - lo) / 0.5).astype(int))[::-1])
    on = gc._raster(gc._tri_points(P, T[is_main], 0.25), lo, shape, 0.5)
    d_out = gc._dist(~on, MAIN_INSET_M + 1.0, 0.5)
    inner = on & ~(np.isfinite(d_out) & (d_out < MAIN_INSET_M))
    cen = P[T].mean(1)[:, :2]
    ii = np.clip(((cen[:, 1] - lo[1]) / 0.5).astype(int), 0, shape[0] - 1)
    jj = np.clip(((cen[:, 0] - lo[0]) / 0.5).astype(int), 0, shape[1] - 1)
    drop = ~is_main & inner[ii, jj]
    _align_on_route(L, P, T, tp, is_main, drop, route, c)
    if not drop.any():
        return
    keep = ~drop
    for key, arr in list(L.items()):
        if hasattr(arr, "__len__") and not isinstance(arr, (str, dict)) and len(arr) == len(T) != len(P):
            L[key] = np.asarray(arr)[keep]
    names = sorted({str(c["piece_names"][p]).split(".")[0] for p in np.unique(tp[drop])})
    print(f"    road layers: {int(drop.sum())} triangles of side roads lying on the stage's road left out "
          f"(the stage's asphalt shows there): {', '.join(names[:12])}{' ...' if len(names) > 12 else ''}")


def _route_coords(route, pts):
    """(s along the route, signed offset across it, distance to it) of points, searched near the points' centre only
    (a hairpin passes the same place twice)."""
    import numpy as np
    s, R = route
    c = pts.mean(0)
    i0 = int(np.argmin(np.hypot(R[:, 0] - c[0], R[:, 1] - c[1])))
    half = float(np.max(np.hypot(*(pts - c).T))) + 30.0
    win = np.nonzero(np.abs(s - s[i0]) <= half)[0]
    Rw, sw = R[win], s[win]
    d = np.hypot(pts[:, None, 0] - Rw[None, :, 0], pts[:, None, 1] - Rw[None, :, 1])
    j = d.argmin(1)
    k = np.clip(j, 1, len(Rw) - 2)
    tan = Rw[k + 1] - Rw[k - 1]
    tan /= np.maximum(np.linalg.norm(tan, axis=1, keepdims=True), 1e-9)
    rel = pts - Rw[j]
    along = (rel * tan).sum(1)
    off = tan[:, 0] * rel[:, 1] - tan[:, 1] * rel[:, 0]
    return sw[j] + along, off, d[np.arange(len(pts)), j]


def _join_road_ends(L, npz):
    import collections
    import numpy as np
    if "end_fade" not in L:
        return
    got = _piece_of_vertex(L, npz)
    if got is None:
        return
    c, P, T, tp, vp = got
    names = c["piece_names"]
    ef = np.asarray(L["end_fade"], float).copy()
    v = np.asarray(L["v"], float)
    cross = np.array([any(w in str(n).upper() for w in ("CROSSROAD", "INTERSECTION", "ROUNDABOUT")) for n in names])
    key = np.floor(P[:, :2] / JOIN_M).astype(np.int64)
    cells = collections.defaultdict(list)
    for i in np.nonzero(vp >= 0)[0]:
        cells[(int(key[i, 0]), int(key[i, 1]))].append(i)

    def joined(idx, piece):
        for i in idx:
            x, y = int(key[i, 0]), int(key[i, 1])
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    for j in cells.get((x + dx, y + dy), ()):
                        if vp[j] != piece and np.hypot(P[j, 0] - P[i, 0], P[j, 1] - P[i, 1]) <= JOIN_M:
                            return True
        return False

    n_cross = n_ends = 0
    for piece in np.unique(vp[vp >= 0]):
        sel = np.nonzero(vp == piece)[0]
        faded = sel[ef[sel] < 0.999]
        if not len(faded):
            continue
        if cross[piece]:
            ef[sel] = 1.0
            n_cross += 1
            continue
        lo, hi = float(v[sel].min()), float(v[sel].max())
        for end_v, other in ((lo, hi), (hi, lo)):
            row = sel[(np.abs(v[sel] - end_v) <= 0.02 * max(hi - lo, 1e-6) + 1e-6) & (ef[sel] < 0.05)]
            if len(row) and joined(row, piece):
                side = faded[np.abs(v[faded] - end_v) < np.abs(v[faded] - other)]
                ef[side] = 1.0
                n_ends += 1
    L["end_fade"] = ef
    # borders (t = 1, transparent) lying on another piece's asphalt: a crossing's sides against the road ends, a
    # ring's openings to its branches. Corners meeting another piece's corner (consecutive pieces) stay borders.
    t = np.asarray(L["t"], float).copy()
    n_border = 0
    for i in np.nonzero((t >= 0.5) & (vp >= 0))[0]:
        x, y = int(key[i, 0]), int(key[i, 1])
        hit = False
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for j in cells.get((x + dx, y + dy), ()):
                    if vp[j] != vp[i] and t[j] < 0.5 and np.hypot(P[j, 0] - P[i, 0], P[j, 1] - P[i, 1]) <= JOIN_M:
                        hit = True
                        break
                if hit:
                    break
            if hit:
                break
        if hit:
            t[i] = 0.0
            n_border += 1
    L["t"] = t
    if n_cross or n_ends or n_border:
        print(f"    road layers: {n_cross} crossing pieces opaque, {n_ends} piece ends meeting another road not faded, "
              f"{n_border} border vertices on another road's asphalt made solid")


# --- props with a sheared transform --------------------------------------------------------------------------------

def _patch_sheared_props():
    """props_visual.actor_transform refuses an instance matrix more than MAX_SHEAR_DEG off square, and one prop of
    ES2_SPAIN/SS1 (21.6 deg) stopped the whole stage. Such a matrix is replaced by its nearest unsheared one: the
    closest rotation (polar decomposition) with the scale along each of its axes."""
    import numpy as np
    import tools.acrmod.props_visual as pv
    if getattr(pv.actor_transform, "_wr", False):
        return
    orig = pv.actor_transform

    def actor_transform(world, *a, **k):
        try:
            return orig(world, *a, **k)
        except ValueError as e:
            if "sheared" not in str(e):
                raise
            M = np.array(world, float)
            A = M[:3, :3]
            U, S, Vt = np.linalg.svd(A)
            R = U @ Vt
            if np.linalg.det(R) < 0:
                U[:, -1] *= -1
                R = U @ Vt
            M[:3, :3] = R @ np.diag(np.diag(R.T @ A))
            print(f"    props: a sheared instance ({e}) straightened")
            return orig(M, *a, **k)

    actor_transform._wr = True
    pv.actor_transform = actor_transform


# --- impact sounds on barriers and walls -----------------------------------------------------------------------------

# WRCG gives guardrails METALSTATIC / METAL and stone walls ROCK; the surface map turns them into ACR driving surfaces
# (PM_SurfaceMetal, PM_SurfaceRock), which carry no impact sound (owner drive: no sound when hitting or scraping a
# barrier). ACR's walls use its PM_Wall* materials. A container mesh that is mostly vertical (area-weighted |normal z|
# under WALL_NZ, Y up in the baked frame) is an obstacle, not something driven on, and gets the wall counterpart of its
# material. Measured on Savalla: all 77 metal and 410 of 430 rock meshes are vertical, no road piece is; grass is left
# alone (12 of its 108 meshes are steep terrain banks).
WALL_NZ = 0.6
WALL_MATERIALS = {
    "PM_SurfaceMetal": "PM_WallMetalGuardrail",
    "PM_SurfaceRock": "PM_WallRock",
    "PM_SurfaceConcrete": "PM_WallConcrete",
    "PM_SurfaceCobblestones": "PM_WallConcrete",
    "PM_WrcgWood": "PM_WallWood",
}


def _patch_wall_materials():
    import numpy as np
    import tools.acrmod.bakeddata as bd
    if getattr(bd.build, "_wr", False):
        return
    orig = bd.build

    def build(meshes, *a, **k):
        changed = {}
        for m in meshes:
            key = str(m.physmat).rsplit("/", 1)[-1].split(".")[0]
            wall = WALL_MATERIALS.get(key)
            if not wall or len(m.indices) == 0:
                continue
            P = np.asarray(m.positions, float).reshape(-1, 3)
            T = np.asarray(m.indices).reshape(-1, 3)
            n = np.cross(P[T[:, 1]] - P[T[:, 0]], P[T[:, 2]] - P[T[:, 0]])
            area = np.linalg.norm(n, axis=1)
            # baked frame is Y up (baked = (x, z, -y))
            nz = np.abs(n[:, 1]) / np.maximum(area, 1e-9)
            if area.sum() > 0 and float((nz * area).sum() / area.sum()) < WALL_NZ:
                m.physmat = wall
                changed[(key, wall)] = changed.get((key, wall), 0) + 1
        if changed:
            print("    walls: " + ", ".join(f"{n} {a}->{b}" for (a, b), n in changed.items()) + " (impact sounds)")
        return orig(meshes, *a, **k)

    build._wr = True
    bd.build = build


# --- RVT and finish marshal, added when the level is saved (after the terrain tiles) ---------------------------------

def _patch_level_save():
    import tools.acrmod.ugraph as ug
    if getattr(ug.UMap.save, "_wr", False):
        return
    orig = ug.UMap.save

    def save(self, path):
        if getattr(self, "_wr_hs", None) is None:
            return orig(self, path)
        if not getattr(self, "_wr_done", False):
            self._wr_done = True
            _late_level(self)
        import wr_perf
        return wr_perf.lean_save(orig, self, path)       # the level's JSON without default fields, compact

    save._wr = True
    ug.UMap.save = save


def _fill_light_positions(cfg, route):
    """Stage build "fill_lights": the "net_fill" rows (wr_lights.net_fill_positions: m, every_m, toward_m, height_m, cd, radius_cm)
    whose "material" is "ROCK" (the level's rock props: MALAYSIA_CLIFF, M_RED_ROCK, ...) or "CROWD" (WRCG's spectator spots).
    Owner 2026-11-16, Ngema m ~105: dark rocks and crowd, "la misma potencia que los plasticos"."""
    import re
    import numpy as np
    import tools.acrmod.build_stage as bs
    import tools.wrcg.prop_instances as pi
    import wr_crowd
    import wr_lights
    import wr_skinned
    need = {str(z.get("material", "")).upper() for z in cfg["fill_lights"]}
    items = []
    if "ROCK" in need:
        out, _ = pi.collect_instances(cfg["wrcg_level"], ("static", "dynamic", "clutter", "spline", "decor"), route_xy=np.asarray(route, float)[:, :2],
                                      near_m=150.0, stage_mask=wr_skinned.stage_mask(cfg.get("stage_id")))
        items += [{"pos": np.asarray(p.world, float)[:3, 3], "material": "ROCK", "scale": float(np.cbrt(abs(np.linalg.det(np.asarray(p.world, float)[:3, :3]))))} for p in out
                  if re.search(r"ROCK|CLIFF|BOULDER", str(p.psi_name), re.I) and "WrcgScene" not in str(p.name)]
    if "CROWD" in need:
        level = cfg["wrcg_level"]
        tag = cfg.get("crowd_tag") or cfg["stage_id"].split("/")[-1]
        plm = WORK / "wrcg_fs" / "WIN32" / "LEVELS" / level / f"{level}.PLM"
        spots = wr_crowd.wrcg_spectators(plm, tag) or (wr_crowd.wrcg_spectators(plm, tag[:-1]) if tag.endswith("R") else [])
        items += [{"pos": np.asarray(p, float)[:3], "material": "CROWD"} for _, p in spots]
    return wr_lights.net_fill_positions(cfg["fill_lights"], items, route)


def _late_level(dst):
    import numpy as np
    import tools.acrmod.build_stage as bs
    import tools.acrmod.ittiri_ground as ig
    import tools.acrmod.props_visual as pv
    import tools.acrmod.stagectx as sc
    slug = sc.cur().slug
    cfg = bs.load_cfg(slug)
    log = lambda s: print(f"    [{cfg['name']}] {s.strip()}")
    route = bs.route_wrcg(cfg)
    shift = bs.stage_shift(cfg, route)
    route_ue = pv.wrcg_world_to_ue(route, shift)
    if cfg.get("greece_gravel_dust"):
        import wr_gravel
        try:
            wr_gravel.add_greek_dust(dst, log)
        except Exception as e:
            log(f"wheel particles: not set ({type(e).__name__}: {e})")
    import wr_roadside
    ground = ig.make_ground_fn(shift)
    if wr_roadside.replace_tape(cfg) or cfg.get("acr_nets") or any(wr_roadside.on(cfg, k) for k in ("brake_boards", "corner_posts")):
        wr_roadside.add(dst, ROOT, cfg, route, shift, ground, log)
    if cfg.get("sign_lighting_m"):
        import wr_lights
        try:
            wr_lights.fix_sign_lighting(dst, ROOT, route, shift, ground, cfg, log=log)
        except Exception as e:
            log(f"sign lighting: not completed ({type(e).__name__}: {e})")
    if cfg.get("water_animated_oceans"):
        import wr_water
        try:
            wr_water.use_animated_water(dst, cfg["water_animated_oceans"], log=log)
        except Exception as e:
            log(f"water: animated material not added ({type(e).__name__}: {e})")
    if cfg.get("sector_fill_m"):
        import wr_lights
        try:
            wr_lights.add_sector_fill(dst, ROOT, route, shift, cfg["sector_fill_m"], cfg, log=log)
        except Exception as e:
            log(f"ACR sector fill: not added ({type(e).__name__}: {e})")
    try:
        import wr_lights
        import wr_scene
        lights = wr_scene.light_positions(cfg)
        if lights:
            log(f"scene: {wr_lights._add_fill_lights(dst, ROOT, shift, lights, 'WrcgSceneFill')} lights for the parked vehicles")
    except Exception as e:
        log(f"scene: lights not added ({type(e).__name__}: {e})")
    if cfg.get("net_fill"):
        try:
            import tools.acrmod.cloth_visual as cv
            import wr_lights
            pos = wr_lights.net_fill_positions(cfg["net_fill"], __import__("wr_roadside")._skip_cloth(getattr(cv.collect_cloth, "original", cv.collect_cloth)(cfg["wrcg_level"], near_m=150.0)[0], cfg), route)
            log(f"net fill: {wr_lights._add_fill_lights(dst, ROOT, shift, pos, 'WrcgNetFill')} lights along {cfg['net_fill']}")
        except Exception as e:
            log(f"net fill: not added ({type(e).__name__}: {e})")
    if cfg.get("fill_lights"):
        try:
            pos = _fill_light_positions(cfg, route)
            log(f"fill lights: {wr_lights._add_fill_lights(dst, ROOT, shift, pos, 'WrcgPropFill')} lights over {len(cfg['fill_lights'])} zones (rocks / crowd)")
        except Exception as e:
            log(f"fill lights: not added ({type(e).__name__}: {e})")
    if cfg.get("rvt"):
        import wr_rvt
        tiles = [i for i in range(1, len(dst.exports) + 1) if dst.exp(i)["ObjectName"].startswith(wr_rvt.TERRAIN_PREFIX)]
        pts = []
        for t in tiles:
            comp = wr_rvt._prop(dst.exp(t), "RootComponent")
            loc = wr_rvt._prop(dst.exp(comp["Value"]), "RelativeLocation") if comp else None
            if loc:
                v = loc["Value"][0]["Value"]
                pts.append((float(v["X"]), float(v["Y"])))
        pts = np.array(pts)
        pad = 25600.0                       # two 128 m tiles: tile origins are a corner or the centre
        lo = (float(pts[:, 0].min() - pad), float(pts[:, 1].min() - pad), float(route_ue[:, 2].min() - 30000.0))
        hi = (float(pts[:, 0].max() + pad), float(pts[:, 1].max() + pad), float(route_ue[:, 2].max() + 30000.0))
        import wr_groundcover
        for pkg in wr_groundcover.RVTS:          # one volume per RVT the grass materials sample
            wr_rvt.add_volume(dst, dst._wr_hs, lo, hi, pkg)
        wr_rvt.add_writers(dst, wr_groundcover.RVTS, pass_type="Never", log=log)
        log(f"RVT volumes {[p.rsplit('/', 1)[-1] for p in wr_groundcover.RVTS]}: "
            f"x {lo[0]:.0f}..{hi[0]:.0f}, y {lo[1]:.0f}..{hi[1]:.0f} cm")
    try:
        import wr_perf
        import tools.acrmod.stagectx as sc
        if _on(sc.cur().slug, "prop_draw_distances"):      # "prop_draw_distances": false = props never culled by size (the first version)
            wr_perf.prop_draw_distances(dst, log=log)      # props: draw distance by size (wr_perf.py)
    except Exception as e:
        log(f"draw distances: not set ({type(e).__name__}: {e})")
    if _SEATS:
        import tools.acrmod.start_marshal as sm
        import wr_crowd
        try:
            wr_crowd.add_seated(dst, sm.MARSHAL_CELL_SRC, _seats_ue(shift), ig.make_ground_fn(shift), log=log,
                                prefix=f"{cfg['name']}Seated")
        except Exception as e:
            log(f"seated people: not added ({type(e).__name__}: {e})")
    if cfg.get("crowd_sit"):          # [{"at": [x, y, z], "n": 2, "spread_m": 1.2, "pose": "Sitting"|"SittingRock"}] WRCG metres: people sitting facing the road
        import math
        import tools.acrmod.start_marshal as sm
        import wr_crowd
        R = np.asarray(route, float)
        by_pose = {}
        for r in cfg["crowd_sit"]:
            c = np.asarray(r["at"], float)
            j = int(np.hypot(R[:, 0] - c[0], R[:, 1] - c[1]).argmin())
            to_road = R[j, :2] - c[:2]
            to_road = to_road / max(float(np.hypot(*to_road)), 1e-6)
            tang = np.array([-to_road[1], to_road[0]])
            n = int(r.get("n", 2))
            for k in range(n):
                q = c[:2] + tang * (k - (n - 1) / 2) * float(r.get("spread_m", 1.2))
                ua, ub = pv.wrcg_world_to_ue(np.array([[q[0], q[1], c[2]], [q[0] + to_road[0], q[1] + to_road[1], c[2]]]), shift)
                by_pose.setdefault(r.get("pose", "Sitting"), []).append(
                    (float(ua[0]), float(ua[1]), float(ua[2]), math.degrees(math.atan2(ub[1] - ua[1], ub[0] - ua[0]))))
        for pose, seats in by_pose.items():
            try:
                wr_crowd.add_seated(dst, sm.MARSHAL_CELL_SRC, seats, ground, log=log, prefix=f"{cfg['name']}{pose}", pose=pose)
            except Exception as e:
                log(f"crowd_sit {pose}: not added ({type(e).__name__}: {e})")
    if cfg.get("escape_reaction"):      # [{"at": [x, y, z], "variant": "HandFree_Right_01", "trigger_m": 50, "chance": 1.0}] WRCG m: ACR's crowd that runs away (wr_escape.py)
        try:
            import math
            import wr_escape
            import wr_scene
            R = np.asarray(route, float)
            s = np.r_[0.0, np.cumsum(np.hypot(*np.diff(R[:, :2], axis=0).T))]
            items = []
            for r in cfg["escape_reaction"]:
                c = np.asarray(r["at"], float)
                j = int(np.hypot(R[:, 0] - c[0], R[:, 1] - c[1]).argmin())
                _, _, nrm = wr_scene.frame(R, s[j])
                side = "left" if float(np.dot(c[:2] - R[j, :2], nrm)) > 0 else "right"
                jt = int(np.abs(s - (s[j] - float(r.get("trigger_m", 50.0)))).argmin())
                (px, py, pz), (tx, ty, tz) = pv.wrcg_world_to_ue(np.array([c, R[jt]]), shift)
                items.append((float(px), float(py), math.degrees(math.atan2(ty - py, tx - px)), (float(tx), float(ty), float(tz)),
                              r.get("variant") or wr_escape.SIDE_DEFAULT[side], float(r.get("chance", 1.0))))
            wr_escape.prepare(WORK / "acr", os.environ["WRCG2ACR_ACR_PAKS"])
            wr_escape.add(dst, WORK / "acr", items, ground, log=log)
        except Exception as e:
            log(f"escape reaction: not added ({type(e).__name__}: {e})")
    if cfg.get("finish_marshal"):
        import wr_finish
        x_ue = wr_finish.finish_layout(dst, slug, cfg, WORK / "wrcg" / slug, shift, log=log)
        wr_finish.add_finish_marshal(dst, WORK / "acr", route_ue if x_ue is None else x_ue, ig.make_ground_fn(shift),
                                     log=log, side_m=cfg.get("finish_marshal_side_m"), along_m=cfg.get("finish_marshal_along_m"),
                                     box_scale=cfg.get("finish_marshal_box"))
    if cfg.get("breakable_signs"):
        import wr_breakables
        try:
            wr_breakables.add(dst, slug, shift, ig.make_ground_fn(shift), log=log)
        except Exception as e:
            log(f"breakable signs: not added ({type(e).__name__}: {e})")
    # (no physical props any more: owner 2026-11-11, "se rompen pero siguen teniendo colisión cuando ya no están.
    # Vamos a simplificar, hacemos que nada se rompa"; tall posts are solid, _pole_collision)
    try:
        _ground_props(dst, ig.make_ground_fn(shift), log)
    except Exception as e:
        log(f"props on the ground: not done ({type(e).__name__}: {e})")
    if cfg.get("replay_cameras"):
        import wr_cameras
        spline_w = np.concatenate([bs.pre_route_wrcg(cfg), route])
        import wr_groundcover
        tdir = WORK / "wrcg" / slug / "terrain"
        H = (np.load(tdir / "heights_0p5m.npy", mmap_mode="r"),
             *wr_groundcover.window(json.loads((tdir / "meta.json").read_text(encoding="utf-8"))))
        occ = wr_cameras.occlusion(WORK / "wrcg" / slug, H, spline_w, log=log)
        # big jumps: route s of the take-off -> s along the camera spline (pre-route + route)
        jumps = cfg.get("camera_focus_m") or wr_cameras.jump_points(WORK / "wrcg" / slug)
        Rc = np.loadtxt(WORK / "wrcg" / slug / "route_centerline_1m.csv", delimiter=",", skiprows=1)
        s_sp = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(spline_w[:, :2], axis=0), axis=1))])
        focus = []
        for j in jumps:
            p = Rc[int(np.argmin(np.abs(Rc[:, 0] - j))), 1:3]
            focus.append(float(s_sp[int(np.argmin(np.hypot(spline_w[:, 0] - p[0], spline_w[:, 1] - p[1])))]))
        if focus:
            log(f"replay cameras: a camera of its own for the big jump{'s' if len(focus) > 1 else ''} at route s "
                f"{', '.join(f'{j:.0f}' for j in jumps)} m")
        wr_cameras.fix(dst, spline_w, pv.wrcg_world_to_ue(spline_w, shift), H,
                       lambda p: pv.wrcg_world_to_ue(p, shift), log=log, occ=occ, focus=focus)
    if cfg.get("lamp_lights"):
        import wr_lights
        mods = WORK / "acr" / "mods"
        roots = [p for p in mods.glob("*/stages/*/legacy")] + [p for p in mods.glob("*/legacy")]
        wr_lights.add_lamp_lights(dst, WORK / "acr", roots, log=log)
    if cfg.get("skids"):
        import wr_skids
        import tools.acrmod.racing_line as rli
        road = np.load(WORK / "wrcg" / slug / "collision_all_prm.npz")
        racing, _ = rli.compute(route, road["positions"], road["triangles"])
        wr_skids.add_skids(dst, WORK / "acr", route_ue, log=log, prefix=f"{cfg['name']}Skid",
                           racing_ue=pv.wrcg_world_to_ue(np.asarray(racing, float), shift))
    tent = False
    if cfg.get("service_park_tent"):                    # Alsace's team tent round the car (wr_servicepark.py)
        try:
            import tools.acrmod.ittiri_ground as ig2
            import wr_servicepark
            tent = wr_servicepark.add(dst, slug, shift, ig2.make_ground_fn(shift), log=log)
        except Exception as e:
            log(f"service park: no tent ({type(e).__name__}: {e})")
    if not tent and cfg.get("service_park_yaw_deg") is not None:
        _turn_service_park(dst, None, log, yaw=float(cfg["service_park_yaw_deg"]))
    elif not tent and cfg.get("service_park_yaw_offset_deg") is not None:
        _turn_service_park(dst, float(cfg["service_park_yaw_offset_deg"]), log)
    if cfg.get("sky"):
        _set_sky(dst, cfg["sky"], log)


def _set_sky(dst, sky, log):
    """The level's sky (BC_DMSky_Candidate_C, cloned from Hafren South) keeps Wales: latitude 52.28, longitude -3.4,
    UTC+0, 3 November. Owner: the time of day should follow the stage's place."""
    import wr_rvt
    want = {"Latitude": sky["latitude"], "Longitude": sky["longitude"], "Time Zone": sky["utc_offset"],
            "Month": sky["month"], "Day": sky["day"]}
    for i in range(1, len(dst.exports) + 1):
        if dst.class_name(i) == "BC_DMSky_Candidate_C":
            e = dst.exp(i)
            for k, v in want.items():
                p = wr_rvt._prop(e, k)
                if p is None:
                    continue
                p["Value"] = int(v) if "Int" in p["$type"] else float(v)
            if sky.get("day_skylight_scale") is not None:
                import wr_lights
                day = wr_lights.set_day_skylight(dst, e, sky["day_skylight_scale"])
                log(f"sky: daytime ambient intensity {day:.3f}")
            log(f"sky: latitude {sky['latitude']}, longitude {sky['longitude']}, UTC{sky['utc_offset']:+d}, "
                f"{sky['day']}/{sky['month']}")


def _turn_service_park(dst, offset, log, yaw=None):
    """The builder gives ServiceParkTargetPoint the road's yaw, like the refuel point; in Hafren South the two differ by
    178 deg (refuel 83.4, service park -94.8) and the owner saw the service-park car the wrong way round.
    yaw: a fixed world yaw instead of road + offset. The service park camera looks in a fixed world direction
    (wr_servicepark.py: Alsace's car at 183.9), so a yaw relative to the road only suits stages that start the way
    Pietrosella does. Owner 2026-11-11: France at 175.6 (road -94.8 + 270) "perfecto", and "la posicion de los coches
    ... tienen que ir como en Francia": every stage at 175.6 (service_park_yaw_deg)."""
    import wr_rvt
    for i in range(1, len(dst.exports) + 1):
        if dst.class_name(i) == "ServiceParkTargetPoint":
            root = dst.exp(wr_rvt._prop(dst.exp(i), "RootComponent")["Value"])
            r = wr_rvt._prop(root, "RelativeRotation")["Value"][0]["Value"]
            old = float(r["Yaw"])
            r["Yaw"] = ((old + offset if yaw is None else yaw) + 180.0) % 360.0 - 180.0
            log(f"service park: yaw {old:.1f} -> {float(r['Yaw']):.1f} deg")
