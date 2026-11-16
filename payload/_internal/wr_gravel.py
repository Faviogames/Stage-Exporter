"""Loutraki's wheel particles and a local gravel grip comparison."""
import numpy as np

MANAGER_CLASS = "BC_VehicleParticlesManager_C"
GREEK_PARTICLES = "DA_WheelSurfaceParticlesConfig_Greece"
GRAVEL_HARD = "PM_SurfaceGravelHard"
GRAVEL_FINE = "PM_SurfaceGravelFine"


def patch_grip(cfg_for_slug):
    from tools.acrmod import build_stage as bs, ittiri_container as ic, stagectx as sc

    if getattr(ic.meshes, "_wr_gravel", False):
        return
    original = ic.meshes

    def meshes(offset=(0.0, 0.0, 0.0), *args, **kwargs):
        result = original(offset, *args, **kwargs)
        try:
            slug = sc.cur().slug
            cfg = cfg_for_slug(slug) or {}
            zone = cfg.get("gravel_grip_trial_m")
            if zone:
                route = bs.route_wrcg(bs.load_cfg(slug))
                width = float(cfg.get("road_width_m") or 7.0)
                result, changed = softer_section(result, offset, route, zone, width / 2)
                print(f"    gravel grip trial {zone} m: {changed} triangles {GRAVEL_HARD} -> {GRAVEL_FINE}")
        except Exception as e:
            print(f"    gravel grip trial skipped ({type(e).__name__}: {e})")
        return result

    meshes._wr_gravel = True
    ic.meshes = meshes


def add_greek_dust(dst, log=print):
    import wr_perf
    import wr_roadside as roadside

    level = roadside._level(dst)
    manager = next((i for i in range(1, len(dst.exports) + 1)
                    if dst.exp(i)["OuterIndex"] == level and dst.class_name(i) == MANAGER_CLASS), None)
    if manager is None:
        raise ValueError("the level has no vehicle particles manager")
    actor = dst.exp(manager)
    old = roadside._value(dst, manager, "WheelSurfaceParticlesConfig")
    config = dst.ensure_import(((f"/Game/Data/Vehicles/Common/{GREEK_PARTICLES}", "/Script/CoreUObject", "Package"),
                                (GREEK_PARTICLES, "/Script/acr", "WheelSurfaceParticlesConfiguration")))
    wr_perf._put(dst, actor, "WheelSurfaceParticlesConfig", "ObjectPropertyData", config)
    if roadside._value(dst, manager, "WheelSurfaceParticlesConfig") != config:
        raise ValueError("the vehicle particles manager does not expose serializable properties")
    for field, refs in actor.items():
        if old and field.endswith("Dependencies") and refs:
            actor[field] = [config if ref == old else ref for ref in refs]
    refs = actor.setdefault("CreateBeforeSerializationDependencies", [])
    if config not in refs:
        refs.append(config)
    dst._add_export_names(actor)
    log("wheel particles: native Greece dusty gravel")


def softer_section(meshes, offset, route, zone, half_width):
    from tools.acrmod.bakeddata import Mesh
    from wr_roadside import _route_samples

    start, end = zone
    xy = _route_samples(route)[0][:, :2]
    if not 0 <= start < end < len(xy):
        raise ValueError(f"gravel grip interval {zone} is outside the route")
    window = xy[start:end + 1]
    lo, hi = window.min(axis=0) - half_width, window.max(axis=0) + half_width
    origin = np.asarray(offset)
    out, changed = [], 0
    for mesh in meshes:
        if mesh.physmat != GRAVEL_HARD:
            out.append(mesh)
            continue
        positions = np.asarray(mesh.positions).reshape(-1, 3)
        triangles = np.asarray(mesh.indices).reshape(-1, 3)
        centres = positions[triangles].mean(axis=1) - origin
        points = np.column_stack((centres[:, 0], -centres[:, 2]))
        candidates = np.flatnonzero(((lo <= points) & (points <= hi)).all(axis=1))
        selected = np.zeros(len(triangles), dtype=bool)
        for begin in range(0, len(candidates), 128):
            ids = candidates[begin:begin + 128]
            distance2 = ((points[ids, None, :] - xy[None, :, :]) ** 2).sum(axis=2)
            nearest = distance2.argmin(axis=1)
            selected[ids] = ((start <= nearest) & (nearest <= end)
                             & (distance2[np.arange(len(ids)), nearest] <= half_width ** 2))
        if not selected.any():
            out.append(mesh)
            continue
        owner = mesh.owner
        if not selected.all():
            out.append(Mesh(mesh.positions, triangles[~selected].ravel().tolist(), GRAVEL_HARD, owner))
            owner += "GripTrial"
        out.append(Mesh(mesh.positions, triangles[selected].ravel().tolist(), GRAVEL_FINE, owner))
        changed += int(selected.sum())
    return out, changed
