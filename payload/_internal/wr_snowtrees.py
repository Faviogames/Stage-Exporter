"""Snow stages: snow-covered ACR trees.

Owner 2026-11-10 (Sävar): "los árboles no son de nieve". WRCG's Swedish trees came out as ACR's Aleppo pines (no snow
layer at all). ACR's Monte Carlo spruce has one (M_SpeedTree / M_Impostor / MI_BillboardTree with EnableSnowLayer and
SnowLayer_EnableVertexHeightSnowMasking: snow from 400 m to 1200 m of world height, SnowLayer_VertexHightMaskingParams
R 40000 G 120000 cm); our stages sit lower (Sävar 300-420 m), so its snow hardly shows. The bare larch has the layer
without the height mask (always snowy).

On a snow stage (acr_surface Snow): pine -> SM_SpruceMonteCarlo (SPRUCE) and oak -> SM_LarchBare01-02 (patch_species); a
spruce whose materials have the height mask gets copies of its snow materials (leaf, impostor, billboard and their LOD-transition children) with the height
mask moved below any ground (MASK), written into the stage's content, and its HISMs override their materials with them
(materials_for). The copies keep the stock static switches, so they use the stock shaders.
"""
import json
import tempfile
from pathlib import Path

# 02 and 04-08 have the snow layer without the height mask (always snowy, stock materials); 01 has the mask (our copies);
# 03 has no leaves. The builder takes the first meshes of a species (Sävar: three).
SPRUCE = [f"/Game/Foliage/Trees/SpruceMonteCarlo/SM_SpruceMonteCarlo0{k}" for k in (2, 4, 5, 6, 7, 8, 1)]
LARCH = ["/Game/Foliage/Trees/LarchBare/SM_LarchBare01", "/Game/Foliage/Trees/LarchBare/SM_LarchBare02"]
SPECIES = {"pine": SPRUCE, "oak": LARCH}
SNOW_PARAM = "SnowLayer_VertexHightMaskingParams"
MASK = {"R": -200000.0, "G": 1000.0}          # full snow at any height, whether G is the top or the width of the ramp
OUT_DIR = "WrSnowTrees"
_made = {}


def is_snow(cfg):
    return (cfg or {}).get("acr_surface") == "Snow"


def patch_species(log=print):
    """The vegetation map of this process: the snow species' meshes (a snow stage's own build process only)."""
    import tools._embedded as em
    import tools.datafiles as df
    vm = df.load_json("wrcg_vegetation_map.json")
    for k, meshes in SPECIES.items():
        if k in vm.get("acr_species", {}):
            vm["acr_species"][k] = dict(vm["acr_species"][k], meshes=list(meshes))
    em.DATA["wrcg_vegetation_map.json"] = df.scramble(json.dumps(vm, ensure_ascii=False).encode("utf-8"))
    log(f"    snow trees: pine -> SpruceMonteCarlo x{len(SPRUCE)}, oak -> LarchBare x{len(LARCH)}")


def _rel(pkg):
    return pkg[len("/Game/"):] if pkg.startswith("/Game/") else pkg.lstrip("/")


def _asset(pkg, tmp):
    import tools.acrmod.common as c
    root = c.stock_legacy(_rel(pkg))
    ua = Path(root) / "acr" / "Content" / (_rel(pkg) + ".uasset")
    return c.asset_json(ua, Path(tmp) / (pkg.rsplit("/", 1)[-1] + ".json"))


def _slots(mesh_pkg, tmp, cache_file):
    """[material package per slot] of a stock static mesh (cached in work/acr/wr_snowtrees/slots.json)."""
    try:
        cache = json.loads(cache_file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        cache = {}
    if mesh_pkg not in cache:
        d = _asset(mesh_pkg, tmp)
        im = d["Imports"]
        e = next(x for x in d["Exports"] if any(p.get("Name") == "StaticMaterials" for p in x.get("Data") or []))
        out = []
        for s in next(p for p in e["Data"] if p["Name"] == "StaticMaterials")["Value"]:
            mi = next((x.get("Value") for x in s["Value"] if x["Name"] == "MaterialInterface"), 0)
            name = im[-mi - 1]["ObjectName"] if isinstance(mi, int) and mi < 0 else None
            pkg = im[im[-mi - 1]["OuterIndex"] * -1 - 1]["ObjectName"] if name else None
            out.append(pkg)
        cache[mesh_pkg] = out
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(json.dumps(cache, indent=1), encoding="utf-8")
    return cache[mesh_pkg]


def _info(d):
    """(parent package, has the snow height mask) of a material instance asset JSON."""
    im = d["Imports"]
    e = d["Exports"][0]
    par = next((p["Value"] for p in e["Data"] if p["Name"] == "Parent"), 0)
    parent = im[-im[-par - 1]["OuterIndex"] - 1]["ObjectName"] if par < 0 else None
    has = any(p["Name"] == "VectorParameterValues" and SNOW_PARAM in json.dumps(p) for p in e["Data"])
    return parent, has


def _clone(d, src_pkg, new_pkg, parent_map, out_legacy, tmp, tex_map=None):
    """A copy of a stock material instance under new_pkg: its parent (parent_map) and textures (tex_map: stock texture
    package -> ours) replaced, the snow height mask moved below any ground."""
    import tools.acrmod.common as c
    old_name, new_name = src_pkg.rsplit("/", 1)[-1], new_pkg.rsplit("/", 1)[-1]
    nm = d["NameMap"]
    for i, n in enumerate(nm):
        if n == src_pkg:
            nm[i] = new_pkg
        elif n == old_name:
            nm[i] = new_name
    d["Exports"][0]["ObjectName"] = new_name
    for imp in d["Imports"]:                                  # the parent and the textures: ours
        for old, new in list(parent_map.items()) + list((tex_map or {}).items()):
            for o, n in ((old, new), (old.rsplit("/", 1)[-1], new.rsplit("/", 1)[-1])):
                if imp["ObjectName"] == o:
                    imp["ObjectName"] = n
                    if n not in nm:
                        nm.append(n)
    masked = False
    for p in d["Exports"][0]["Data"]:
        if p["Name"] != "VectorParameterValues":
            continue
        for s in p["Value"]:
            f = {x["Name"]: x for x in s["Value"]}
            name = next(x["Value"] for x in f["ParameterInfo"]["Value"] if x["Name"] == "Name")
            if name == SNOW_PARAM:
                f["ParameterValue"]["Value"][0]["Value"].update(MASK)
                masked = True
    d["FolderName"] = new_pkg      # the package name retoc takes the package id from: left as the stock one, every copy collided with the stock asset
    out = Path(out_legacy) / "acr" / "Content" / (_rel(new_pkg) + ".uasset")
    out.parent.mkdir(parents=True, exist_ok=True)
    c.write_asset(d, Path(tmp) / (new_name + ".edit.json"), out)
    return masked


# Snow that stays: ACR's tree snow layer is dynamic weather (MPC_Environment.global_snow, raised while it snows and
# melted by the temperature, DA_*WeatherLocationConfig), so in clear weather the spruces showed no snow at all (owner
# 2026-11-10, Sävar: "árboles sin nieve"). Their colour textures get frosted copies: leaves FROST_LEAF of the way to
# SNOW_RGB everywhere (their alpha, the needles, kept), the impostor / billboard views more at the top of each view.
SNOW_RGB = (0.93, 0.95, 0.97)
FROST_LEAF = 0.5
FROST_VIEW = (0.3, 0.75)                       # bottom, top of each impostor / billboard view
COLOR_PARAMS = ("ColorOpacity", "BaseColor", "Color")
_TEX = {}


def _texture_params(d):
    im = d["Imports"]
    out = {}
    for p in d["Exports"][0]["Data"]:
        if p["Name"] != "TextureParameterValues":
            continue
        for s in p["Value"]:
            f = {x["Name"]: x["Value"] for x in s["Value"]}
            nm = next(x["Value"] for x in f["ParameterInfo"] if x["Name"] == "Name")
            v = f["ParameterValue"]
            if v and v < 0:
                out[nm] = im[-im[-v - 1]["OuterIndex"] - 1]["ObjectName"]
    return out


def _stock_rgba(pkg):
    """Top mip of a stock texture as RGBA uint8 (DXT1 / DXT5 / BC7 in its .ubulk)."""
    import struct
    import numpy as np
    from PIL import Image
    import tools.acrmod.common as c
    rel = _rel(pkg)
    root = Path(c.stock_legacy(rel)) / "acr" / "Content"
    ue = (root / (rel + ".uexp")).read_bytes()
    i = ue.find(b"PF_")
    fmt = ue[i:ue.index(b"\x00", i)].decode()
    sx, sy = struct.unpack_from("<ii", ue, i - 16)
    n, bpp = {"PF_DXT1": (1, 0.5), "PF_DXT5": (3, 1), "PF_BC7": (7, 1)}[fmt]
    ub = root / (rel + ".ubulk")
    data = ub.read_bytes() if ub.exists() else b""
    while sx > 4 and len(data) < int(sx * sy * bpp):   # the top mips may live in an optional container: the first here
        sx, sy = sx // 2, sy // 2
    if len(data) < int(sx * sy * bpp):
        raise ValueError(f"{pkg}: no mip data found")
    img = Image.frombytes("RGBA", (sx, sy), data[:int(sx * sy * bpp)], "bcn", n)
    return np.asarray(img).copy(), fmt


# Owner 2026-11-10 (Sävar, after the frosted copies): "los árboles desaparecen bastante cerca de cámara y pierden calidad
# muy rápido". Two causes: (1) the impostor / billboard colour textures (4096) have only their small mips in the files
# we can read (impostor 512, billboard ~256: the top mips sit in an optional container), so the frosted copies were
# that small; (2) the leaf copy got new mips averaged by the writer, which thin the needles' alpha (the stock mips keep
# their coverage), so the foliage faded out a little away. Now only the leaves are frosted, from the stock mips one by
# one (alpha as stock), and the impostors / billboards stay stock (full resolution, no frost far away).
CLIP = 85                                      # alpha cut of the leaf material (~0.33)


def _stock_mips(pkg):
    """The stock mips of a texture found in its .ubulk, top first, as RGBA uint8 arrays."""
    import struct
    import numpy as np
    from PIL import Image
    import tools.acrmod.common as c
    rel = _rel(pkg)
    root = Path(c.stock_legacy(rel)) / "acr" / "Content"
    ue = (root / (rel + ".uexp")).read_bytes()
    i = ue.find(b"PF_")
    fmt = ue[i:ue.index(b"\x00", i)].decode()
    sx, sy = struct.unpack_from("<ii", ue, i - 16)
    n, block = {"PF_DXT1": (1, 8), "PF_DXT5": (3, 16), "PF_BC7": (7, 16)}[fmt]
    ub = root / (rel + ".ubulk")
    data = ub.read_bytes() if ub.exists() else b""
    size = lambda w, h: max(1, (w + 3) // 4) * max(1, (h + 3) // 4) * block
    w, h = sx, sy
    while w > 4 and size(w, h) > len(data):             # the top mips may live elsewhere: start where the data does
        w, h = w // 2, h // 2
    out, off = [], 0
    while w >= 4 and h >= 4 and off + size(w, h) <= len(data):
        out.append(np.asarray(Image.frombytes("RGBA", (w, h), data[off:off + size(w, h)], "bcn", n)).copy())
        off += size(w, h)
        w, h = w // 2, h // 2
    if not out:
        raise ValueError(f"{pkg}: no mip data found")
    return out


def _keep_coverage(mip, coverage):
    """Scale a mip's alpha so the share of texels above CLIP stays as in the top mip."""
    import numpy as np
    al = mip[..., 3].astype(np.float32)
    lo, hi = 1.0, 8.0
    for _ in range(20):
        s = (lo + hi) / 2
        if float((np.clip(al * s, 0, 255) >= CLIP).mean()) < coverage:
            lo = s
        else:
            hi = s
    mip = mip.copy()
    mip[..., 3] = np.clip(al * hi, 0, 255).astype(np.uint8)
    return mip


def _frosted(pkg, kind, out_dir, out_legacy, tmp):
    """Our frosted copy of a stock leaf colour texture (cached per stage), its package: every stock mip with its colour
    FROST_LEAF of the way to SNOW_RGB and its alpha untouched; the smallest mips (not in the .ubulk) made from the last
    one with the needles' coverage kept."""
    import numpy as np
    import tools.acrmod.texture_writer as tw
    key = (pkg, str(out_legacy))
    if key in _TEX:
        return _TEX[key]
    snow = np.array(SNOW_RGB, np.float32) * 255.0
    mips = []
    for m in _stock_mips(pkg):
        m = m.copy()
        m[..., :3] = np.clip(m[..., :3].astype(np.float32) * (1.0 - FROST_LEAF) + snow * FROST_LEAF + 0.5, 0, 255).astype(np.uint8)
        mips.append(m)
    coverage = float((mips[-1][..., 3] >= CLIP).mean())     # the stock mips raise it as they shrink: keep the last
    for m in tw.make_mip_chain(mips[-1], srgb=True, normal=False)[1:]:
        mips.append(_keep_coverage(m, coverage))
    new_pkg = f"{out_dir}/{pkg.rsplit('/', 1)[-1]}Frost"
    orig, used = tw.make_mip_chain, []

    def chain(rgba, *a, **k):                  # the writer's mip chain: ours
        used.append(True)
        return mips
    tw.make_mip_chain = chain
    try:
        # _write_texture: write_texture caches by image and served v16's copy (its averaged mips) for the same image
        tw._write_texture(Path(out_legacy) / "acr" / "Content", new_pkg, image=mips[0], fmt="BC7", srgb=True, mips=True)
    finally:
        tw.make_mip_chain = orig
    if not used:
        raise RuntimeError("texture writer did not take the stock mips")
    _TEX[key] = new_pkg
    return new_pkg


def materials_for(mesh_pkg, stage_name, out_legacy, work_acr, log=print):
    """Material per slot for a snow-stage spruce: frosted copies of its leaf, impostor and billboard materials (and of
    their LOD-transition children), the bark as it is; None for other meshes."""
    if mesh_pkg not in SPRUCE:
        return None
    key = (mesh_pkg, str(out_legacy))
    if key in _made:
        return _made[key]
    out_dir = f"/Game/Environments/{stage_name}/{OUT_DIR}"
    with tempfile.TemporaryDirectory(prefix="wr_snow_") as tmp:
        slots = _slots(mesh_pkg, tmp, Path(work_acr) / "wr_snowtrees" / "slots.json")
        infos = {}
        for pkg in slots:
            if pkg and pkg not in infos:
                d = _asset(pkg, tmp)
                infos[pkg] = (d,) + _info(d)
        # the leaf materials (ColorOpacity) and their LOD-transition children; impostors / billboards stay stock
        leafy = {pkg for pkg in infos if "Bark" not in pkg and "ColorOpacity" in _texture_params(infos[pkg][0])}
        leafy |= {pkg for pkg in infos if "Bark" not in pkg and infos[pkg][1] in leafy}
        ours = {pkg: f"{out_dir}/{pkg.rsplit('/', 1)[-1]}Snow" for pkg in infos if pkg in leafy}
        n_tex = 0
        for pkg, new in ours.items():
            d, parent, has = infos[pkg]
            tex_map = {}
            for param, tex in _texture_params(d).items():
                if param == "ColorOpacity":
                    tex_map[tex] = _frosted(tex, "leaf", out_dir, out_legacy, tmp)
                    n_tex += 1
            _clone(d, pkg, new, {parent: ours[parent]} if parent in ours else {}, out_legacy, tmp, tex_map)
    mats = [ours.get(p, p) for p in slots]
    log(f"    snow trees: {mesh_pkg.rsplit('/', 1)[-1]} with {len(ours)} frosted material copies "
        f"({len({k for k in _TEX if k[1] == str(out_legacy)})} frosted textures in the stage)")
    _made[key] = mats
    return mats
