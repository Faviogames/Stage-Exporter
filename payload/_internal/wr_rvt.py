"""Runtime virtual texture for the ground-cover materials.

ACR's grass materials (M_GrassNew children with UseRVTBaseColor, e.g. MI_GreenGrassLong02_HalfDry_RVT_Munster) take their
base colour from the level's RVT; without one (none of our levels had one) they sample nothing and render dark. Munster
renders its terrain tiles into RVT_Munster (BaseColor) with its terrain master. Here:
  - RVT volumes over the terrain (RVT_Munster and the two Greek RVTs the Greek grass samples), cloned by the builder's
    own rvt.add_rvt_volume from Hafren South;
  - one RVT-only copy of every terrain tile (VirtualTextureRenderPassType Never: drawn into the RVT, not on screen) with a
    Munster terrain material instance (M_TerrainMaster_light: Alsace grass / dried grass / dirt layers and its snow layer),
    so the grass picks up an ACR ground colour, and snow in snowy weather. The visible terrain is unchanged.
"""
import copy
import json
from pathlib import Path

RVT_PKG = "/Game/Environments/AlsaceS2Munster/VirtualTexture/RVT_Munster"
WRITER_MI = "/Game/Environments/AlsaceS2Munster/TerrainMaterialInstances/MI_Terrain9MatBlend1005"
WRITER_PREFIX = "WrcgRvtWriter_"
TERRAIN_PREFIX = "WrcgTerrain_"
PROP_RVT = Path(__file__).resolve().parent.parent / "work" / "acr" / "wr_prop_rvt.json"


def _key(pkg, cls):
    name = pkg.rsplit("/", 1)[-1]
    return ((pkg, "/Script/CoreUObject", "Package"), (name, "/Script/Engine", cls))


def _prop(e, name):
    return next((p for p in e.get("Data") or [] if p.get("Name") == name), None)


def _set(e, prop):
    data = e["Data"]
    for i, p in enumerate(data):
        if p.get("Name") == prop["Name"]:
            data[i] = prop
            return
    data.append(prop)


def _obj_array(name, idx, tmpl):
    p = copy.deepcopy(tmpl)
    p["Name"] = name
    item = copy.deepcopy(p["Value"][0])
    item["Value"] = idx
    p["Value"] = [item]
    return p


def _enum(name, enum_type, value):
    return {"$type": "UAssetAPI.PropertyTypes.Objects.EnumPropertyData, UAssetAPI", "EnumType": enum_type,
            "InnerType": "ByteProperty", "Name": name, "ArrayIndex": 0, "PropertyGuid": None, "IsZero": False,
            "PropertyTagFlags": "None", "PropertyTypeName": None, "PropertyTagExtensions": "NoExtension", "Value": value}


def _bool(name, value):
    return {"$type": "UAssetAPI.PropertyTypes.Objects.BoolPropertyData, UAssetAPI", "Name": name, "ArrayIndex": 0,
            "PropertyGuid": None, "IsZero": False, "PropertyTagFlags": "None", "PropertyTypeName": None,
            "PropertyTagExtensions": "NoExtension", "Value": value}


def add_volume(dst, src, lo_cm, hi_cm, pkg=RVT_PKG):
    """One RuntimeVirtualTextureVolume for RVT asset pkg (a level may hold several, one per RVT asset)."""
    import tools.acrmod.rvt as rvt
    n0 = len(dst.exports)
    rvt.RVT_PKG = pkg                          # the builder's helper reads it when it makes the import
    out = rvt.add_rvt_volume(dst, src, lo_cm, hi_cm)
    for i in range(n0 + 1, len(dst.exports) + 1):
        if dst.class_name(i) == "RuntimeVirtualTextureVolume":
            name = "WrcgRvtVolume_" + pkg.rsplit("/", 1)[-1]   # the clones would all keep Hafren's actor name
            dst.add_name(name)
            dst.exp(i)["ObjectName"] = name
    return out


def add_writers(dst, rvt_pkgs=(RVT_PKG,), pass_type="Never", log=print):
    tmpl = json.loads(PROP_RVT.read_text())
    level = next(i for i in range(1, len(dst.exports) + 1) if dst.class_name(i) == "Level")
    rvt_idx = [dst.ensure_import(_key(p, "RuntimeVirtualTexture")) for p in rvt_pkgs]
    mi_i = dst.ensure_import(_key(WRITER_MI, "MaterialInstanceConstant"))
    tiles = [i for i in range(1, len(dst.exports) + 1)
             if dst.exp(i)["ObjectName"].startswith(TERRAIN_PREFIX) and dst.class_name(i) == "StaticMeshActor"]
    for i in tiles:
        m = dst.clone(dst, i, level)
        a = m[i]
        name = WRITER_PREFIX + dst.exp(i)["ObjectName"][len(TERRAIN_PREFIX):]
        dst.add_name(name)
        dst.exp(a)["ObjectName"] = name
        dst.register_actor(level, a)
        comp = _prop(dst.exp(a), "StaticMeshComponent")["Value"]
        e = dst.exp(comp)
        _set(e, _obj_array("OverrideMaterials", mi_i, tmpl))
        p = _obj_array("RuntimeVirtualTextures", rvt_idx[0], tmpl)
        p["Value"] += [dict(p["Value"][0], Name=str(j), Value=v) for j, v in enumerate(rvt_idx[1:], 1)]
        _set(e, p)
        _set(e, _enum("VirtualTextureRenderPassType", "ERuntimeVirtualTextureMainPassType", pass_type))
        _set(e, _bool("CastShadow", False))
        for n in ("OverrideMaterials", "RuntimeVirtualTextures", "VirtualTextureRenderPassType", "CastShadow"):
            dst.add_name(n)
        dst.add_name("ERuntimeVirtualTextureMainPassType")
        dst.add_name(pass_type)
    log(f"    RVT: {len(tiles)} RVT-only terrain copies with {WRITER_MI.rsplit('/', 1)[-1]} -> "
        f"{', '.join(p.rsplit('/', 1)[-1] for p in rvt_pkgs)}")
    return len(tiles)
