"""Ground cover and far forest on WRCG's own terrain layers.

Ground cover. WRCG draws most of its grass from the terrain at run time, so the replay of its baked instances leaves the
ground near the road bare. Reference, ACR's Munster (Alsace S2) PCG grass in its grass zones, per m2: Greengrass_Extended
1.7, Ribwort 1.5, GreengrassLong02 1.0 (scale ~2.6), Willow 0.95, Sorrel 0.6, with the RVT materials of the level. Every
0.5 m terrain texel gets the densities of its two WRCG layers blended by the splat weight, faded with the distance to the
route; a plant is kept only if its whole footprint (mesh radius x scale) stays off the road and the props, and it stands on
the lowest point of the adjusted terrain mesh (terrain_mesh_adj.npz, what ACR draws) under its footprint. Owner drive
2026-11-09: tufts spilled onto the asphalt (root 0.6 m off the road, GreengrassLong02 x2.6 is 3 m wide) and floated on the
banks (heights of the unadjusted WRCG terrain); more kinds of grass, taller and shorter. Next drive: denser and closer to
the asphalt, grass following the slope (wr_fixes raises the builder's 12 deg tilt limit).

Far forest. WRCG has no tree instances beyond the replay band (700 m), its far hills are bare terrain; ACR's SpeedTree
trees switch to their impostor (2D) LOD at distance, so trees are scattered on the vegetated layers from 550 m to the edge
of the terrain window.

The instances are appended to work/wrcg/<slug>/vegetation/instances.json, so the builder places them like the replayed
ones. species_defs() goes into the vegetation map (wr.py); MATERIALS is applied by wr_fixes to the HISMs (one per species).
"""
import csv
import json
import math
from pathlib import Path

import numpy as np

TEXEL = 0.5
ORIGIN = -2048.0                               # the 0.5 m window of a rally level; small ones (SSS arenas) differ


def window(meta):
    """(x0, y0) of the terrain's 0.5 m products (heights, splat) from its meta.json. Panzerplatte (an SSS) is a
    2 km square from -1024 m, the rally levels 4 km from -2048 m."""
    w = meta.get("window") or meta.get("heights_0p5m") or {}
    o = w.get("origin_xy") or (ORIGIN, ORIGIN)
    return float(o[0]), float(o[1])
# Owner 2026-11-10, after ACR's own Greek stages: "pon siempre césped corto en las inmediaciones del asfalto combinado con
# césped y plantas más altas, tiene que estar lleno ... falta vegetación y piedras ... las montañas lejanas tienen que
# estar bien llenas de árboles 2D ... tienes que entrar en los tramos y decir wow cuánta vegetación". So: a verge along
# the road edge (VERGE_*: every species denser the closer to the asphalt, short grass on the bare gravel verges too),
# stones along the edges (gc_stone / gc_rock), a wider band, and the far forest several times denser. Room for it: the
# level JSON is now written lean (wr_perf.lean_save, ~45 % of its old size).
FULL_M, FADE_M, MAX_M = 25.0, 50.0, 80.0      # full density to 25 m from the route, 35 % at 50 m, none beyond 80 m
FAR_SHARE = 0.35
OUTER_M = 35.0                                 # beyond this from the route only the wide patches and the shrubs
VERGE_M = 6.0                                  # verge: up to 6 m from the road edge...
VERGE_GAIN, VERGE_DECAY_M = 2.5, 2.5           # ...densities x (1 + 2.5 exp(-d / 2.5)): x3.5 at the asphalt, x1.9 at 3 m
ROAD_CLEAR_M = 0.15                            # bare margin between a plant's footprint and the road collision
PROP_CLEAR_M = 0.3
FOOTPRINT = 0.55                               # share of the mesh's xy radius that must clear the road (thin blade tips)
# Walls (owner 2026-11-11, Pietrosella: grass at the foot of the big stone wall "dejando formas feas", a willow hanging
# out over a wall top): shrubs and the wide grass patches keep their whole footprint off the props (walls are props'
# collision), the small plants half of it as before.
WIDE_FOOT_M = 1.2


def _prop_share(d, foot):
    import numpy as np
    if d["kind"] == "shrub":
        return np.ones_like(foot)
    if d["kind"] == "grass":
        return np.where(foot > WIDE_FOOT_M, 1.0, 0.5)
    return np.full_like(foot, 0.5)
# the level JSON must stay under ~1 G characters (UaTool reads it as one .NET string): ~370 characters per instance in
# the lean JSON, so 1.2 M instances with the trees and the rest of the level keep a wide margin
CAP_TOTAL = 1_400_000
MIN_REST = 0.35                                # over the cap: the band away from the verge down to this first
# owner 2026-11-10, Arganil: "los bordes de la carretera siguen vacíos ... en caminos de tierra le podemos dar más
# margen a las plantas para crecer un poco más cerca de la pista, y que se tiñan con el color del suelo". Small grass
# may stand on the outer EDGE_IN_M of a gravel / dirt road's collision (no collision of its own; tarmac stays clean)
SOFT_SURFACE = r"gravel|dirt|sand|grass|mud|leaves"
EDGE_IN_M = 0.6
RIM_FOOT_M = 0.45
# the far forest (impostor trees) from 150 m, full from 350 m: between the ground cover and 550 m the hills had
# only WRCG's trees (owner 2026-11-10: "zonas montañosas o con montículos ... me falta mucha más vida vegetal")
FAR_START_M, FAR_FULL_M = 150.0, 350.0
FAR_CLEAR_M = 8.0                              # no far tree this close to a road or a prop (now that they come nearer)
FAR_CELL = 4.0
FAR_CAP = 200_000

G = "/Game/Foliage/GroundCover/"
T = "/Game/Foliage/Trees/"
MUN = "_RVT_Munster"


def _sp(kind, meshes, scale, cull, sink=5, slope=45, align=True, mats=None, note=""):
    return {"kind": kind, "meshes": meshes, "scale": scale, "cull_end_cm": cull, "sink_cm": sink, "max_slope_deg": slope,
            "align_to_normal": align, "mats": mats, "note": note}


EXT, LONG = G + "GreenGrassLongExtended01/", G + "GreenGrassLong02/"
STONES = "/Game/Props/GreeceProps/GreElaSmallStones/"
SPECIES = {
    # ACR Munster grass, three tints of both meshes (RVT_Munster)
    "gc_ext_green": _sp("grass", [EXT + "SM_Greengrass_Extended_long_01"], [0.6, 1.15], 15000,
                        mats=[EXT + "Generated/MI_GreengrassLongExtended" + MUN, EXT + "Generated/MI_GreenGrassLongExtended_LOD" + MUN]),
    "gc_ext_halfdry": _sp("grass", [EXT + "SM_Greengrass_Extended_long_01"], [0.6, 1.15], 15000,
                          mats=[EXT + "Generated/MI_GreenGrassLongExtended_HalfDry" + MUN, EXT + "Generated/MI_GreenGrassLongExtended_HalfDry_LOD" + MUN]),
    "gc_ext_dry": _sp("grass", [EXT + "SM_Greengrass_Extended_long_01"], [0.6, 1.15], 15000,
                      mats=[EXT + "Generated/MI_GreenGrassLongExtended_Dry" + MUN, EXT + "Generated/MI_GreenGrassLongExtended_Dry_LOD" + MUN]),
    "gc_long_green": _sp("grass", [LONG + "SM_GreengrassLong02"], [1.4, 2.9], 15000,
                         mats=[LONG + "Generated/MI_GreenGrassLong02" + MUN, LONG + "Generated/MI_GreenGrassLong02_LOD" + MUN]),
    "gc_long_halfdry": _sp("grass", [LONG + "SM_GreengrassLong02"], [1.4, 2.9], 15000,
                           mats=[LONG + "Generated/MI_GreenGrassLong02_HalfDry" + MUN, LONG + "Generated/MI_GreenGrassLong02_HalfDry_LOD" + MUN]),
    "gc_long_dry": _sp("grass", [LONG + "SM_GreengrassLong02"], [1.4, 2.9], 15000,
                       mats=[LONG + "Generated/MI_GreenGrassLong02_Dry" + MUN, LONG + "Generated/MI_GreenGrassLong02_Dry_LOD" + MUN]),
    "gc_ribwort": _sp("grass", [G + "Ribwort/SM_Ribwort_01"], [0.8, 1.8], 15000,
                      mats=[G + "Ribwort/Generated/MI_Ribwort" + MUN, G + "Ribwort/MI_Ribwort"]),
    # ACR Greece grass (RVT_GreeceS3Elatia / RVT_GreeceS4Loutraki)
    "gc_clump": _sp("grass", [G + "Greece/GrassClump/SM_GrassClump_01"], [0.7, 1.4], 12000,
                    mats=[G + "Greece/GrassClump/Generated/MI_GrassClump01_RVT_GreeceS3Elatia"]),
    "gc_field": _sp("grass", [G + "Greece/FieldGrass/SM_FieldGrass_01"], [0.8, 1.6], 12000,
                    mats=[G + "Greece/FieldGrass/Generated/MI_FieldGrass01_RVT_GreeceS4Loutraki"]),
    "gc_wild": _sp("grass", [G + "WildGrass/SM_WildGrassElatia01Wide"], [0.7, 1.3], 15000,
                   mats=[G + "WildGrass/Generated/MI_WildGrassElatia01_RVT_GreeceS3Elatia"]),
    # their own colours
    "gc_straw": _sp("grass", [G + "Greece/DryStrawGrass/SM_DryStrawGrass_01"], [0.8, 1.6], 12000),
    "gc_tall": _sp("grass", [G + "Greece/GrassTall/SM_GrassTall_01"], [0.8, 1.4], 15000),
    "gc_high": _sp("grass", [G + "Greece/HighGrass/SM_HighGrass_01"], [0.8, 1.3], 15000),
    "gc_starwort": _sp("grass", [G + "Greece/Starwort/SM_Starwort_01"], [0.8, 1.3], 12000),
    "gc_sorrel": _sp("grass", [G + "Sorrel/SM_Sorrel_01"], [0.8, 1.3], 15000),
    "gc_flower": _sp("grass", [G + "FlowerPlant01/SM_Flowerplant01"], [1.3, 2.6], 15000),
    "gc_willow": _sp("shrub", [G + "Willow/SM_Willow_01"], [1.0, 1.9], 30000, slope=40, align=False),
    "gc_broom": _sp("shrub", [G + f"BroomCreeper/SM_BroomCreeper0{i}" for i in range(1, 6)], [0.8, 1.3], 20000, slope=55),
    # stones along the road edges: ACR's small Greek limestones (0.2-0.7 m), pebbles and a few rocks
    "gc_stone": _sp("rock", [STONES + f"SM_GreElaSmallLimestone{c}" for c in "ABCEF"], [0.6, 2.0], 8000, sink=3, slope=60),
    "gc_rock": _sp("rock", [STONES + f"SM_GreElaSmallLimestone{c}" for c in "BCD"], [2.2, 4.5], 20000, sink=8, slope=50),
    # far forest: impostor LODs at distance
    "far_pine": _sp("tree", [T + f"AleppoPine/SM_AleppoPine0{i}" for i in (1, 2, 3)], [0.7, 1.05], 0, sink=30, slope=45, align=False),
    "far_oak": _sp("tree", [T + "Smoketree/SM_Smoketree01"], [0.8, 1.15], 0, sink=30, slope=45, align=False),
    "far_maple": _sp("tree", [T + f"Blackmaple/SM_Blackmaple0{i}" for i in (1, 2)], [0.8, 1.1], 0, sink=30, slope=45, align=False),
    "far_olive": _sp("tree", [T + f"Olivetree/SM_Olivetree0{i}" for i in (1, 2, 3)], [0.5, 0.7], 0, sink=20, slope=30, align=False),
}
MATERIALS = {k: v["mats"] for k, v in SPECIES.items() if v["mats"]}
# by mesh too: the WRCG grass replayed with the same ACR meshes (grass_green = SM_GrassClump_01, grass_straw =
# SM_FieldGrass_01 + ...) kept the stock materials, which read the Greek levels' own RVT, absent here: dark grass
# (owner 2026-11-10, Arganil: 69555 grass_green clumps)
MESH_MATERIALS = {}
for _v in SPECIES.values():
    if _v["mats"] and len(_v["meshes"]) == 1:
        MESH_MATERIALS.setdefault(_v["meshes"][0], _v["mats"])

# "ground_cover_style": "greece" in a stage build: the Munster grasses give way to the Greek ones (Elatia / Loutraki
# grass, owner 2026-11-10 for Arganil: "vegetación ... de Grecia en Elatia o Loutraki")
# (Arganil, 2nd drive: "que se tiñan con el color del suelo": the straw, which has its own colour, gives way to the
# Greek grasses that take the ground's colour from the RVT)
STYLES = {"greece": {"gc_ext_green": "gc_clump", "gc_ext_halfdry": "gc_field", "gc_ext_dry": "gc_field",
                     "gc_long_green": "gc_wild", "gc_long_halfdry": "gc_wild", "gc_long_dry": "gc_wild",
                     "gc_ribwort": "gc_clump", "gc_sorrel": "gc_clump", "gc_straw": "gc_field"}}
STYLE = {}
STYLE_NAME = [None]
RVTS = ["/Game/Environments/AlsaceS2Munster/VirtualTexture/RVT_Munster",
        "/Game/Environments/GreeceS3Elatia/VirtualTexture/RVT_GreeceS3Elatia",
        "/Game/Environments/GreeceS4Loutraki/VirtualTexture/RVT_GreeceS4Loutraki"]

# per m2, by WRCG terrain layer
GRASS = {"gc_ext_green": 0.45, "gc_ext_halfdry": 0.45, "gc_long_green": 0.25, "gc_long_halfdry": 0.25, "gc_ribwort": 0.7,
         "gc_clump": 0.45, "gc_field": 0.4, "gc_wild": 0.3, "gc_tall": 0.12, "gc_sorrel": 0.25, "gc_starwort": 0.12,
         "gc_flower": 0.05, "gc_willow": 0.22, "gc_broom": 0.06}
DRY = {"gc_ext_halfdry": 0.45, "gc_ext_dry": 0.45, "gc_long_halfdry": 0.25, "gc_long_dry": 0.4, "gc_straw": 0.55,
       "gc_clump": 0.3, "gc_wild": 0.3, "gc_high": 0.12, "gc_ribwort": 0.25, "gc_sorrel": 0.08, "gc_flower": 0.03,
       "gc_willow": 0.12, "gc_broom": 0.18}
GRAVEL_GRASS = {"gc_ext_dry": 0.35, "gc_long_dry": 0.25, "gc_straw": 0.4, "gc_clump": 0.3, "gc_ribwort": 0.15,
                "gc_broom": 0.18}
FOREST = {"gc_ext_green": 0.3, "gc_ribwort": 0.25, "gc_clump": 0.2, "gc_starwort": 0.1, "gc_willow": 0.2, "gc_broom": 0.12}
BARE = {"gc_straw": 0.1, "gc_clump": 0.05, "gc_broom": 0.08}
LAYER_DENSITY = {"Grass": GRASS, "Grass_Dry": DRY, "Grass_Yellow": DRY, "Gravel_Grass": GRAVEL_GRASS,
                 "Gravel_Dry_Grass": GRAVEL_GRASS, "gravel_forest": FOREST, "Scarp": BARE, "Scarp_2": BARE,
                 "Rock_1": BARE, "Dry_Mud": BARE, "Dry_Mud_2": BARE, "LimeStone": BARE,
                 "Gravel": {}, "Tarmac": {}}    # grey gravel verges and paved areas read as road: nothing on them
# far trees per hectare, and the species mix
# other levels' layer names, by keyword (first match wins)
LAYER_KEYWORDS = [(r"tarmac|asphalt|road|pave|concrete|kerb|snow|ice", {}), (r"forest|wood|leaves|needle", FOREST),
                  (r"gravel.*grass|grass.*gravel", GRAVEL_GRASS), (r"dry|yellow|straw|burnt", DRY),
                  (r"grass|meadow|moss|green|field", GRASS), (r"gravel|dirt|mud|sand|soil|ground", BARE),
                  (r"rock|scarp|stone|cliff|lime|granite", BARE)]


def _layer_class(name):
    import re
    d = LAYER_DENSITY.get(name)
    return d if d is not None else next((d_ for pat, d_ in LAYER_KEYWORDS if re.search(pat, name, re.I)), BARE)


def layer_density(name):
    import re
    d = LAYER_DENSITY.get(name)
    if d is None:
        d = next((d_ for pat, d_ in LAYER_KEYWORDS if re.search(pat, name, re.I)), BARE)
    if not STYLE:
        return d
    out = {}
    for k, v in d.items():                      # the style's species take the others' share
        out[STYLE.get(k, k)] = out.get(STYLE.get(k, k), 0.0) + v
    return out


# the verge of the bare gravel layers (nothing on them elsewhere): short dry grass up to the edge, fading by VERGE_M
VERGE_MIX = {"gc_clump": 0.9, "gc_field": 0.7, "gc_ribwort": 0.35, "gc_straw": 0.25, "gc_tall": 0.15, "gc_broom": 0.1}
VERGE_LAYER = r"gravel|dirt|mud|sand|soil|ground|scarp|rock|lime"
NO_STONES = r"tarmac|asphalt|pave|concrete|kerb|snow|ice"
# per m2: stones at the edge (decaying over STONE_DECAY_M), a few further out up to STONE_M from the route
STONE_EDGE, STONE_DECAY_M, STONE_BASE, STONE_M = 0.35, 1.2, 0.012, 20.0
ROCK_BAND, ROCK_BASE = (1.5, 8.0), (0.02, 0.003)
OUTER = {"gc_ext_green", "gc_ext_halfdry", "gc_ext_dry", "gc_wild", "gc_long_green", "gc_long_halfdry", "gc_long_dry",
         "gc_high", "gc_starwort", "gc_willow", "gc_broom"}
FAR_DENSITY_HA = {"gravel_forest": 260, "Grass": 90, "Grass_Dry": 75, "Grass_Yellow": 60, "Gravel_Grass": 75,
                  "Gravel_Dry_Grass": 60, "Scarp": 25, "Scarp_2": 25, "Rock_1": 15, "LimeStone": 15, "Dry_Mud": 10,
                  "Dry_Mud_2": 10}
FAR_MIX = {"far_pine": 0.6, "far_oak": 0.2, "far_maple": 0.1, "far_olive": 0.1}


def species_defs():
    """acr_species entries for the vegetation map."""
    out = {}
    for k, v in SPECIES.items():
        out[k] = {"kind": v["kind"], "stands_for": [], "meshes": v["meshes"], "scale": v["scale"],
                  "road_clearance_m": ROAD_CLEAR_M, "max_route_dist_m": 5000 if v["kind"] == "tree" else MAX_M,
                  "max_slope_deg": v["max_slope_deg"], "max_instances": 2_000_000, "sink_cm": v["sink_cm"],
                  "align_to_normal": v["align_to_normal"], "cull_end_cm": v["cull_end_cm"],
                  "_note": "wr_groundcover.py" + (" (far forest, impostor LODs)" if k.startswith("far_") else "")}
    return out


def _layers(meta):
    import ast
    L = meta["layers"]
    if isinstance(L, str):
        L = ast.literal_eval(L)
    return {int(k): v["name"] for k, v in L.items() if k.isdigit()}


def _raster(pts, lo, shape, cell):
    m = np.zeros(shape, bool)
    j = np.floor((pts[:, 0] - lo[0]) / cell).astype(int)
    i = np.floor((pts[:, 1] - lo[1]) / cell).astype(int)
    ok = (i >= 0) & (i < shape[0]) & (j >= 0) & (j < shape[1])
    m[i[ok], j[ok]] = True
    return m


def _dist(mask, reach_m, cell=TEXEL):
    import tools.wrcg.vegetation as vg
    return np.asarray(vg._edt_capped(mask, int(math.ceil(reach_m / cell)) + 1), float) * cell


def _tri_points(P, T, step=0.5):
    """Points over triangles, no farther apart than `step` (m): each triangle gets the barycentric grid of the level its
    longest edge needs, all triangles of one level at once. The tool's sampler goes triangle by triangle: 1995 of the
    2074 s of Arganil's ground cover (owner 2026-11-10: "este exportador ... es bastante poco eficiente")."""
    if len(T) == 0:
        return np.zeros((0, 3))
    P = np.asarray(P, np.float32).reshape(-1, 3)
    T = np.asarray(T, np.int64).reshape(-1, 3)
    A, B, C = P[T[:, 0]], P[T[:, 1]], P[T[:, 2]]
    edge = np.maximum.reduce([np.linalg.norm(B - A, axis=1), np.linalg.norm(C - B, axis=1), np.linalg.norm(A - C, axis=1)])
    level = np.clip(np.ceil(edge / step).astype(np.int64), 1, 512)
    out = []
    for k in np.unique(level):
        idx = np.nonzero(level == k)[0]
        i, j = np.meshgrid(np.arange(k + 1), np.arange(k + 1), indexing="ij")
        keep = i + j <= k
        w1 = (i[keep] / k).astype(np.float32)
        w2 = (j[keep] / k).astype(np.float32)
        w0 = 1.0 - w1 - w2
        chunk = max(1, 4_000_000 // len(w0))
        for s in range(0, len(idx), chunk):
            q = idx[s:s + chunk]
            pts = A[q, None, :] * w0[None, :, None] + B[q, None, :] * w1[None, :, None] + C[q, None, :] * w2[None, :, None]
            out.append(pts.reshape(-1, 3))
    return np.concatenate(out)


def _radius_xy(meshes, bounds_json):
    """xy radius (m) of the widest mesh, from the builder's bounds cache (SM_Greengrass_Extended_long_01 is an 8 m patch)."""
    b = json.loads(Path(bounds_json).read_text()) if Path(bounds_json).exists() else {}
    r = [math.hypot(b[m]["extent"][0], b[m]["extent"][1]) / 100.0 for m in meshes if m in b]
    return max(r) if r else 1.0


def _height(meshes, bounds_json):
    b = json.loads(Path(bounds_json).read_text()) if Path(bounds_json).exists() else {}
    h = [2.0 * b[m]["extent"][2] / 100.0 for m in meshes if m in b]
    return max(max(h) if h else 0.3, 0.05)


# Laying a plant on the ground (owner drive 2026-11-09: grass still floating on the banks beside the road). The plant's
# height and tilt used to come from one point (bilinear height, +-0.5 m gradient), and its tilt was capped at 40 deg:
# the wide patches (Munster's long grass: 2.5-4.8 m radius) stuck out over a bank whose slope changes or is steeper.
# Now the ground is sampled under the whole footprint (centre and two rings, FIT_SHARE of the mesh radius), a plane is
# fitted (tilt up to MAX_TILT_DEG, the builder's limit is raised to match), the plant is lowered until no sample is more
# than FLOAT_TOL_M under it (nothing in the air), and a plant that would then be buried by more than BURY_SHARE of its
# height somewhere is tried at half size, then dropped.
FIT_SHARE = 0.8
MAX_TILT_DEG = 60.0
FLOAT_TOL_M = 0.04
BURY_SHARE = 0.5
_RING = np.array([[0.0, 0.0]] + [[math.cos(a), math.sin(a)] for a in np.linspace(0, 2 * math.pi, 8, endpoint=False)] +
                 [[0.5 * math.cos(a + math.pi / 8), 0.5 * math.sin(a + math.pi / 8)]
                  for a in np.linspace(0, 2 * math.pi, 8, endpoint=False)])


def _bilinear(hgt, wlo, x, y):
    u = np.clip((x - wlo[0]) / TEXEL - 0.5, 0, hgt.shape[1] - 1.001)
    v = np.clip((y - wlo[1]) / TEXEL - 0.5, 0, hgt.shape[0] - 1.001)
    u0, v0 = u.astype(int), v.astype(int)
    du, dv = u - u0, v - v0
    return (hgt[v0, u0] * (1 - du) * (1 - dv) + hgt[v0, u0 + 1] * du * (1 - dv) +
            hgt[v0 + 1, u0] * (1 - du) * dv + hgt[v0 + 1, u0 + 1] * du * dv)


def _fit_ground(hgt, wlo, x, y, radius, height, max_slope_deg):
    """(z at the centre, normal x, y, z, fits) for plants at x, y with the given footprint radius and height (m)."""
    if len(x) == 0:
        e = np.zeros(0)
        return e, e, e, e, np.zeros(0, bool)
    dx = _RING[None, :, 0] * radius[:, None]
    dy = _RING[None, :, 1] * radius[:, None]
    g = _bilinear(hgt, wlo, x[:, None] + dx, y[:, None] + dy)
    a = g.mean(1)                                            # the ring is symmetric: least squares in closed form
    b = (g * dx).sum(1) / np.maximum((dx * dx).sum(1), 1e-9)
    c = (g * dy).sum(1) / np.maximum((dy * dy).sum(1), 1e-9)
    grad = np.hypot(b, c)
    slope = np.degrees(np.arctan(grad))
    k = np.where(slope > MAX_TILT_DEG, math.tan(math.radians(MAX_TILT_DEG)) / np.maximum(grad, 1e-9), 1.0)
    b, c = b * k, c * k
    r = g - (a[:, None] + b[:, None] * dx + c[:, None] * dy)     # ground minus plane: < 0 = plant in the air
    shift = np.maximum(0.0, -r.min(1) - FLOAT_TOL_M)
    bury = r.max(1) + shift
    ok = (bury <= np.maximum(0.12, BURY_SHARE * height)) & (slope <= max_slope_deg)
    nn = np.sqrt(b * b + c * c + 1.0)
    return a - shift, -b / nn, -c / nn, 1.0 / nn, ok


# Meadow ring: owner 2026-11-10 "que nunca haya zonas de textura verde sin plantas". The near band fades out by MAX_M,
# the grass is drawn to 150 m (its cull): from MEADOW_FROM_M to MEADOW_M the vegetated layers get the wide grass patches
# (Munster's 6 m Greengrass_Extended, the 3.8 m Greek wild grass), enough of them to cover the ground, on a 1 m grid.
MEADOW_FROM_M, MEADOW_FULL_M, MEADOW_M = 45.0, 60.0, 150.0
MEADOW_CELL = 1.0
MEADOW_MIX = {"grass": {"gc_ext_green": 0.036, "gc_ext_halfdry": 0.022, "gc_willow": 0.004},
              "dry": {"gc_ext_halfdry": 0.028, "gc_ext_dry": 0.03, "gc_broom": 0.005},
              "forest": {"gc_ext_green": 0.032, "gc_broom": 0.004}}
MEADOW_STYLE = {"greece": {"gc_ext_green": ("gc_wild", 1.8), "gc_ext_halfdry": ("gc_wild", 1.8),
                           "gc_ext_dry": ("gc_wild", 1.8)}}


def _meadow(names, sp, H, meta, rt, road, extra, rng, style_name, log):
    """[(species, x, y, z, scale, nx, ny, nz)] of the meadow ring."""
    import re
    ox, oy = window(meta)
    nrows, ncols = sp["a"].shape
    step = int(MEADOW_CELL / TEXEL)
    lo = np.maximum(np.floor((rt[:, :2].min(0) - MEADOW_M - 5 - (ox, oy)) / MEADOW_CELL).astype(int), 0)
    hi = np.minimum(np.ceil((rt[:, :2].max(0) + MEADOW_M + 5 - (ox, oy)) / MEADOW_CELL).astype(int),
                    [ncols // step, nrows // step])
    shape = (hi[1] - lo[1], hi[0] - lo[0])
    mlo = (ox + lo[0] * MEADOW_CELL, oy + lo[1] * MEADOW_CELL)
    d_route = _dist(_raster(rt, mlo, shape, MEADOW_CELL), MEADOW_M + 5, MEADOW_CELL)
    ramp = np.clip((d_route - MEADOW_FROM_M) / (MEADOW_FULL_M - MEADOW_FROM_M), 0.0, 1.0)
    ramp[~np.isfinite(d_route) | (d_route > MEADOW_M)] = 0.0
    d_road = _dist(_raster(_tri_points(road["positions"], road["triangles"]), mlo, shape, MEADOW_CELL), 8.0, MEADOW_CELL)
    d_prop = _dist(_raster(_tri_points(extra["positions"], extra["triangles"]), mlo, shape, MEADOW_CELL), 6.0, MEADOW_CELL)
    sl = (slice(lo[1] * step, hi[1] * step, step), slice(lo[0] * step, hi[0] * step, step))
    a, b = sp["a"][sl][:shape[0], :shape[1]], sp["b"][sl][:shape[0], :shape[1]]
    w = sp["w"][sl][:shape[0], :shape[1]].astype(np.float32) / 255.0

    def cls(ln):
        c = _layer_class(ln)
        return "forest" if c is FOREST else "grass" if c is GRASS else "dry" if c in (DRY, GRAVEL_GRASS) else None
    style = MEADOW_STYLE.get(style_name or "", {})
    dens = {}
    for li, ln in names.items():
        for k, v in MEADOW_MIX.get(cls(ln), {}).items():
            k2, f = style.get(k, (k, 1.0))
            dens.setdefault(k2, np.zeros(256, np.float32))[li] += v * f
    bounds = Path(__file__).resolve().parents[1] / "work" / "acr" / "rt" / "foliage" / "mesh_bounds.json"
    rows, total, stats = [], 0, []
    for k, lut in dens.items():
        d = SPECIES[k]
        e = (lut[a] * w + lut[b] * (1.0 - w)) * ramp * MEADOW_CELL * MEADOW_CELL
        cnt = rng.poisson(e)
        iy, ix = np.nonzero(cnt)
        iy, ix = np.repeat(iy, cnt[iy, ix]), np.repeat(ix, cnt[iy, ix])
        slo_, shi_ = d["scale"]
        sc = slo_ + (shi_ - slo_) * rng.random(len(ix)) ** 1.3
        r_xy = _radius_xy(d["meshes"], bounds)
        foot = FOOTPRINT * r_xy * sc
        keep = (d_road[iy, ix] >= ROAD_CLEAR_M + foot) & (d_prop[iy, ix] >= PROP_CLEAR_M + _prop_share(d, foot) * foot)
        drawn = len(keep)
        iy, ix, sc = iy[keep], ix[keep], sc[keep]
        x = mlo[0] + (ix + rng.random(len(ix))) * MEADOW_CELL
        y = mlo[1] + (iy + rng.random(len(iy))) * MEADOW_CELL
        h_m = _height(d["meshes"], bounds)
        z, nx, ny, nz, ok = _fit_ground(H, (ox, oy), x, y, FIT_SHARE * r_xy * sc, h_m * sc, d["max_slope_deg"])
        retry = ~ok                                        # a patch that does not fit the slope: tried at half size
        if retry.any():
            s2 = sc[retry] * 0.5
            z2, nx2, ny2, nz2, ok2 = _fit_ground(H, (ox, oy), x[retry], y[retry], FIT_SHARE * r_xy * s2, h_m * s2,
                                                 d["max_slope_deg"])
            idx = np.where(retry)[0]
            for arr, new in ((z, z2), (nx, nx2), (ny, ny2), (nz, nz2), (sc, s2)):
                arr[idx] = np.where(ok2, new, arr[idx])
            ok[idx] = ok2
        rows.append((k, x[ok], y[ok], z[ok], sc[ok], nx[ok], ny[ok], nz[ok]))
        total += int(ok.sum())
        stats.append(f"{k} {int(ok.sum())}/{drawn}")
    log(f"meadow ring {MEADOW_FROM_M:.0f}-{MEADOW_M:.0f} m: {total} grass patches (kept/drawn: {', '.join(stats)})")
    return rows


# Tunnels (owner 2026-11-11, Pietrosella: "pon vegetación si puedes arriba del puente, arbustos y algún árbol que se vea
# frondoso"): road collision with the terrain more than TUNNEL_COVER_M above it is a tunnel; it does not keep plants
# off the hill above, and that hill gets TUNNEL_SHRUBS and TUNNEL_TREES (per m2 of an 8 m band, TUNNEL_BAND_M, around
# the tunnel). 2nd drive: "ha quedado muy concentrada ... no hace falta incrementar la cantidad, con que la distribuyas
# más a lo largo de esta montaña": the same number of plants spread over the hill within TUNNEL_SPREAD_M of the tunnel
# (where the ground is TUNNEL_COVER_M above the tunnel road).
TUNNEL_COVER_M = 3.0
TUNNEL_BAND_M = 8.0
TUNNEL_SPREAD_M = 45.0
TUNNEL_MIN_M = 30                              # route metres under the hill
TUNNEL_SHRUBS = {"gc_willow": 0.12, "gc_broom": 0.08, "gc_clump": 0.5, "gc_field": 0.3}
TUNNEL_TREES = {"far_oak": 0.007, "far_maple": 0.007}          # ACR's Smoketree and Black maple: leafy
TUNNEL_CLEAR_M = {"shrub": 1.0, "grass": 0.5, "tree": 6.0}      # from the open road and the props (+ the footprint)


def _covered(P, T, H, origin):
    z = _bilinear(H, origin, np.asarray(P[:, 0], float), np.asarray(P[:, 1], float))
    return ((z - P[:, 2]) > TUNNEL_COVER_M)[T].all(1)


def _open_road(road, H, origin):
    """The road collision without its tunnel triangles (as a dict like the npz), and the tunnel triangles."""
    P, T = road["positions"], road["triangles"]
    tun = _covered(P, T, H, origin)
    out = {k: road[k] for k in road.files}
    out["triangles"] = T[~tun]
    for k in ("tri_surface", "tri_piece", "tri_slot_sub"):
        if k in out and len(out[k]) == len(T):
            out[k] = out[k][~tun]
    return out, T[tun]


def _open_extra(extra, tunnel_pts, H, origin):
    """The prop collision without what is buried in the hill over a tunnel (its walls and roof): plants above."""
    P, T = extra["positions"], extra["triangles"]
    out = {k: extra[k] for k in extra.files}
    if not len(tunnel_pts) or not len(T):
        return out
    lo = tunnel_pts[:, :2].min(0) - TUNNEL_SPREAD_M - 10
    hi = tunnel_pts[:, :2].max(0) + TUNNEL_SPREAD_M + 10
    c = P[T].mean(1)
    near = (c[:, 0] >= lo[0]) & (c[:, 0] <= hi[0]) & (c[:, 1] >= lo[1]) & (c[:, 1] <= hi[1])
    out["triangles"] = T[~(near & _covered(P, T, H, origin))]
    return out


def _tunnel_cover(P, T, road, extra, H, origin, rng, log):
    """[(species, x, y, z, scale, nx, ny, nz)] of shrubs, grass and trees on the hill above the tunnels."""
    pts = _tri_points(P, T, 1.0)
    lo = pts[:, :2].min(0) - TUNNEL_SPREAD_M - 2
    hi = pts[:, :2].max(0) + TUNNEL_SPREAD_M + 2
    cell = 1.0
    shape = (int((hi[1] - lo[1]) / cell) + 1, int((hi[0] - lo[0]) / cell) + 1)
    d_tun = _dist(_raster(pts, lo, shape, cell), TUNNEL_SPREAD_M + 1, cell)
    band = np.isfinite(d_tun) & (d_tun <= TUNNEL_BAND_M)
    spread = np.isfinite(d_tun) & (d_tun <= TUNNEL_SPREAD_M)
    gy, gx = np.nonzero(spread)                    # the hill: ground above the tunnel road under its nearest point
    cx, cy = lo[0] + (gx + 0.5) * cell, lo[1] + (gy + 0.5) * cell
    hill = _bilinear(H, origin, cx, cy) - _nearest_z(pts[::4], cx, cy) > TUNNEL_COVER_M
    spread[gy[~hill], gx[~hill]] = False
    k_area = float(band.sum()) / max(float(spread.sum()), 1.0)    # the 8 m band's numbers, spread
    reach = max(TUNNEL_CLEAR_M.values()) + 5
    d_open = _dist(_raster(_tri_points(road["positions"], road["triangles"]), lo, shape, cell), reach, cell)
    d_prop = _dist(_raster(_tri_points(extra["positions"], extra["triangles"]), lo, shape, cell), reach, cell)
    d_any = np.minimum(np.where(np.isfinite(d_open), d_open, 1e3), np.where(np.isfinite(d_prop), d_prop, 1e3))
    iy, ix = np.nonzero(spread)
    rows = []
    bounds = Path(__file__).resolve().parents[1] / "work" / "acr" / "rt" / "foliage" / "mesh_bounds.json"
    for k0, dens in list(TUNNEL_SHRUBS.items()) + list(TUNNEL_TREES.items()):
        k = STYLE.get(k0, k0) if STYLE.get(k0, k0) in SPECIES else k0
        d = SPECIES[k]
        free = d_any[iy, ix] >= TUNNEL_CLEAR_M[d["kind"]]
        jy, jx = iy[free], ix[free]
        n = rng.poisson(dens * k_area * cell * cell, len(jx))
        sel = np.repeat(np.arange(len(jx)), n)
        x = lo[0] + (jx[sel] + rng.random(len(sel))) * cell
        y = lo[1] + (jy[sel] + rng.random(len(sel))) * cell
        slo, shi = d["scale"]
        sc = slo + (shi - slo) * rng.random(len(sel))
        if d["kind"] == "tree":
            g = _bilinear(H, origin, x[:, None] + _RING[None, :, 0] * 1.5, y[:, None] + _RING[None, :, 1] * 1.5)
            ok = (g.max(1) - g.min(1)) / 3.0 <= math.tan(math.radians(d["max_slope_deg"]))
            z = g.min(1) - d["sink_cm"] / 100.0
            ones = np.ones(int(ok.sum()))
            rows.append((k, x[ok], y[ok], z[ok], sc[ok], 0 * ones, 0 * ones, ones))
        else:
            r_xy = _radius_xy(d["meshes"], bounds)
            z, nx, ny, nz, ok = _fit_ground(H, origin, x, y, FIT_SHARE * r_xy * sc, _height(d["meshes"], bounds) * sc,
                                            d["max_slope_deg"])
            ok &= d_any[jy[sel], jx[sel]] >= TUNNEL_CLEAR_M[d["kind"]] + FOOTPRINT * r_xy * sc   # its whole footprint
            rows.append((k, x[ok], y[ok], z[ok], sc[ok], nx[ok], ny[ok], nz[ok]))
    log(f"above tunnels ({int(spread.sum())} m2 of hill within {TUNNEL_SPREAD_M:.0f} m): "
        f"{', '.join(f'{r[0]} {len(r[1])}' for r in rows)}")
    return rows


# Gaps in the road collision (owner 2026-11-11, Pietrosella: grass "en este paso roto en la carretera" leaving the
# village, s 4320, and where he stopped on grass in the left turn after the tunnel, s 6262): at junctions WRCG's road
# pieces leave holes the route drives over (6-8 m between the pieces, the mouth between the stage and a side road), and
# the plants only kept off the road collision. Now also off the road closed over GAP_CLOSE_M (the holes and mouths
# between pieces) and off ROUTE_LANE_M either side of the route centreline (where it is not inside a tunnel).
GAP_CLOSE_M = 6.5
ROUTE_LANE_M = 3.0


def _road_gaps(on_road, rt, H, origin, wlo, shape, log=print):
    """Texels off the road collision that are part of the road: holes, junction mouths, the route's own lane."""
    d1 = _dist(on_road, GAP_CLOSE_M + 1.0)
    dil = np.isfinite(d1) & (d1 <= GAP_CLOSE_M)
    d2 = _dist(~dil, GAP_CLOSE_M + 1.0)
    closed = ~(np.isfinite(d2) & (d2 <= GAP_CLOSE_M))
    up = _bilinear(H, origin, rt[:, 0], rt[:, 1]) - rt[:, 2] <= TUNNEL_COVER_M
    # the lane only where the route itself is off the road collision (a hole it drives over): along a narrow gravel
    # road it would have taken the verge plants at the edge (Arganil, owner: "deja que crezcan más cerca")
    d_on = _dist(on_road, 2.0)
    ri = np.clip(((rt[:, 1] - wlo[1]) / TEXEL).astype(int), 0, shape[0] - 1)
    rj = np.clip(((rt[:, 0] - wlo[0]) / TEXEL).astype(int), 0, shape[1] - 1)
    off = up & ~(np.isfinite(d_on[ri, rj]) & (d_on[ri, rj] <= 1.0))
    lane = _dist(_raster(rt[off], wlo, shape, TEXEL), ROUTE_LANE_M + 1.0)
    lane = np.isfinite(lane) & (lane <= ROUTE_LANE_M)
    out = (closed | lane) & ~on_road
    log(f"ground cover: {int(out.sum() * TEXEL * TEXEL)} m2 of road gaps, junction mouths and route lane kept bare")
    return out


# The road before the start and after the finish (owner 2026-11-11, 2nd drive: "me ha faltado vegetación en todas partes
# en el inicio del tramo donde aparece la vista inicial del coche antes de arrancar e ir al punto de la salida"): the
# car now spawns up to 90 m before our route (wr_fixes._patch_prestart) and stops past its end (the run-off to the stop
# control), where the plants, laid round the route, thinned out. They are laid round the road GC_BEFORE_M before and
# GC_AFTER_M after it too (WRCG's road, wr_finish.runoff).
GC_BEFORE_M, GC_AFTER_M = 110.0, 160.0


def _with_ends(stage_dir, rt, log=print):
    try:
        import wr_finish
        R = np.column_stack([np.arange(len(rt), dtype=float), rt])
        back = wr_finish.runoff(stage_dir, R, GC_BEFORE_M, backward=True)
        fwd = wr_finish.runoff(stage_dir, R, GC_AFTER_M)
        log(f"ground cover: round the road {len(back)} m before the route and {len(fwd)} m after it too")
        return np.vstack([back[::-1].reshape(-1, 3), rt, fwd.reshape(-1, 3)])
    except Exception as e:
        log(f"ground cover: round the route only ({type(e).__name__}: {e})")
        return rt


def _nearest_z(pts, x, y):
    """z of the nearest of pts (N, 3) to each (x, y)."""
    best, z = np.full(len(x), np.inf), np.zeros(len(x))
    for k in range(0, len(pts), 100):
        blk = pts[k:k + 100]
        dd = np.hypot(x[:, None] - blk[None, :, 0], y[:, None] - blk[None, :, 1])
        j = dd.argmin(1)
        m = dd[np.arange(len(j)), j]
        upd = m < best
        best[upd], z[upd] = m[upd], blk[j[upd], 2]
    return z


def _pebbles(stage_dir):
    """"ground_cover_pebbles": factor on the small pale limestones (gc_stone, ACR's Greek ones) of the stage build; Kenya's
    red earth showed them as white patches (owner 2026-11-14). Default 1."""
    try:
        import tools.datafiles as df
        return float((df.load_json(f"stage_builds/{Path(stage_dir).name}.json") or {}).get("ground_cover_pebbles", 1.0))
    except Exception:
        return 1.0


def generate(stage_dir, seed=7, log=print):
    stage_dir = Path(stage_dir)
    tdir = stage_dir / "terrain"
    meta = json.loads((tdir / "meta.json").read_text())
    names = _layers(meta)
    sp = np.load(tdir / "splat_0p5m.npz")
    H = np.load(tdir / "heights_0p5m.npy", mmap_mode="r")
    rt = np.array([[float(x) for x in r] for r in list(csv.reader(open(stage_dir / "route_centerline_1m.csv")))[1:]])[:, 1:4]
    rt = _with_ends(stage_dir, rt, log)
    rng = np.random.default_rng(seed)

    # ---- near band, 0.5 m texels
    ox, oy = window(meta)
    org = np.array([ox, oy])
    nrows, ncols = sp["a"].shape
    lo = np.floor((rt[:, :2].min(0) - MAX_M - 5 - org) / TEXEL).astype(int)
    hi = np.ceil((rt[:, :2].max(0) + MAX_M + 5 - org) / TEXEL).astype(int)
    lo, hi = np.maximum(lo, 0), np.minimum(hi, [ncols, nrows])
    j0, i0, j1, i1 = lo[0], lo[1], hi[0], hi[1]
    shape = (i1 - i0, j1 - j0)
    wlo = (ox + j0 * TEXEL, oy + i0 * TEXEL)
    d_route = _dist(_raster(rt, wlo, shape, TEXEL), MAX_M + 5)
    road, tunnel_T = _open_road(np.load(stage_dir / "collision_all_prm.npz"), H, (ox, oy))
    import re
    on_road = _raster(_tri_points(road["positions"], road["triangles"], 0.25), wlo, shape, TEXEL)
    no_plants = _road_gaps(on_road, rt, H, (ox, oy), wlo, shape, log)
    d_road = _dist(on_road | no_plants, VERGE_M + 4.0)
    # the outer rim of the gravel / dirt roads (EDGE_IN_M inside their edge): small plants may grow there
    rim = np.zeros(shape, bool)
    if "tri_surface" in road and "surface_names" in road:
        soft_ids = [i for i, n in enumerate(road["surface_names"]) if re.search(SOFT_SURFACE, str(n), re.I)]
        soft = np.isin(road["tri_surface"], soft_ids)
        if soft.any():
            on_soft = _raster(_tri_points(road["positions"], road["triangles"][soft], 0.25), wlo, shape, TEXEL)
            rim = on_soft & (_dist(~on_road, EDGE_IN_M + 1.0) <= EDGE_IN_M)
    extra = _open_extra(np.load(stage_dir / "collision_extra.npz"),
                        _tri_points(road["positions"], tunnel_T, 2.0) if len(tunnel_T) else np.zeros((0, 3)), H, (ox, oy))
    d_prop = _dist(_raster(_tri_points(extra["positions"], extra["triangles"]), wlo, shape, TEXEL), 5.0)

    # ground = the adjusted terrain mesh ACR draws (mean height per texel), the WRCG heightfield where it has no sample
    tm = np.load(tdir / "terrain_mesh_adj.npz")
    P, Tt = tm["positions"], tm["triangles"]
    c = P[Tt].mean(1)
    ci = np.clip(((c[:, 1] - wlo[1]) / TEXEL).astype(int), 0, shape[0] - 1)
    cj = np.clip(((c[:, 0] - wlo[0]) / TEXEL).astype(int), 0, shape[1] - 1)
    inside = (c[:, 0] >= wlo[0]) & (c[:, 1] >= wlo[1]) & (c[:, 0] < wlo[0] + shape[1] * TEXEL) & \
             (c[:, 1] < wlo[1] + shape[0] * TEXEL)
    near_tri = inside & (d_route[ci, cj] <= MAX_M + 4)
    pts = _tri_points(P, Tt[near_tri], 0.35)
    gi = np.floor((pts[:, 1] - wlo[1]) / TEXEL).astype(int)
    gj = np.floor((pts[:, 0] - wlo[0]) / TEXEL).astype(int)
    ok = (gi >= 0) & (gi < shape[0]) & (gj >= 0) & (gj < shape[1])
    flat = gi[ok] * shape[1] + gj[ok]
    s = np.bincount(flat, pts[ok, 2], shape[0] * shape[1])
    n = np.bincount(flat, None, shape[0] * shape[1])
    hgt = np.asarray(H[i0:i1, j0:j1], float)               # texel centres approximated by the corner samples
    have = n > 0
    hgt.reshape(-1)[have] = s[have] / n[have]

    fade = np.where(d_route <= FULL_M, 1.0,
                    np.where(d_route <= FADE_M, 1.0 - (1.0 - FAR_SHARE) * (d_route - FULL_M) / (FADE_M - FULL_M),
                             np.where(d_route <= MAX_M, FAR_SHARE * (MAX_M - d_route) / (MAX_M - FADE_M), 0.0)))
    fade[(d_road < ROAD_CLEAR_M) & ~rim] = 0.0

    a = sp["a"][i0:i1, j0:j1]
    b = sp["b"][i0:i1, j0:j1]
    w = sp["w"][i0:i1, j0:j1].astype(np.float32) / 255.0
    dr = np.where(np.isfinite(d_road), d_road, 1e3)
    verge = 1.0 + VERGE_GAIN * np.exp(-np.maximum(dr, 0.0) / VERGE_DECAY_M)        # denser the closer to the asphalt
    edge = np.clip(1.0 - dr / VERGE_M, 0.0, 1.0)                                    # 1 at the asphalt, 0 at VERGE_M
    outer = d_route > OUTER_M

    def by_layer(f):
        lut = np.zeros(256, np.float32)
        for li, ln in names.items():
            lut[li] = f(ln)
        return lut[a] * w + lut[b] * (1.0 - w)
    bare_verge = by_layer(lambda ln: 1.0 if not layer_density(ln) and re.search(VERGE_LAYER, ln, re.I)
                          and not re.search(NO_STONES, ln, re.I) else 0.0)
    stony = by_layer(lambda ln: 0.0 if re.search(NO_STONES, ln, re.I) else 1.0)
    near_species = sorted({k for d in list(LAYER_DENSITY.values()) + [d for _, d in LAYER_KEYWORDS] for k in d}
                          | {STYLE.get(k, k) for k in VERGE_MIX} | {"gc_stone", "gc_rock"})
    expected = {}
    for k in near_species:
        if k == "gc_stone":
            e = (STONE_EDGE * np.exp(-dr / STONE_DECAY_M) + STONE_BASE * (d_route <= STONE_M)) * stony * _pebbles(stage_dir)
        elif k == "gc_rock":
            e = (ROCK_BASE[0] * ((dr >= ROCK_BAND[0]) & (dr <= ROCK_BAND[1])) + ROCK_BASE[1] * (d_route <= STONE_M)) * stony
        else:
            lut = np.zeros(256, np.float32)
            for li, ln in names.items():
                lut[li] = layer_density(ln).get(k, 0.0)
            e = (lut[a] * w + lut[b] * (1.0 - w)) * fade * verge
            e = e + sum(v for kk, v in VERGE_MIX.items() if STYLE.get(kk, kk) == k) * bare_verge * edge
            if k not in OUTER and STYLE.get(k, k) not in OUTER:
                e = np.where(outer, 0.0, e)
        on_rim_ok = rim if SPECIES[k]["kind"] in ("grass", "shrub") else np.zeros(shape, bool)
        e = np.where((d_road < ROAD_CLEAR_M) & ~on_rim_ok, 0.0, e)
        expected[k] = e * (TEXEL * TEXEL)
    # over the cap the band away from the road gives way first (down to MIN_REST), the verge last
    zone = (dr <= VERGE_M + 2.0) | rim
    t_v = sum(float(e[zone].sum()) for e in expected.values())
    t_r = sum(float(e[~zone].sum()) for e in expected.values())
    k_v, k_r = 1.0, 1.0
    if t_v + t_r > CAP_TOTAL:
        if t_v + MIN_REST * t_r <= CAP_TOTAL:
            k_r = (CAP_TOTAL - t_v) / max(t_r, 1.0)
        else:
            k_r = MIN_REST
            k_v = max(0.2, (CAP_TOTAL - MIN_REST * t_r) / max(t_v, 1.0))
    k_map = np.where(zone, k_v, k_r)
    k_scale = (k_v * t_v + k_r * t_r) / max(t_v + t_r, 1.0)

    rows, counts, dropped = [], {}, 0
    refit = [0, 0]                                         # made smaller to fit, dropped for not fitting
    for k in near_species:
        d = SPECIES[k]
        r_xy = _radius_xy(d["meshes"], stage_dir.parent.parent / "acr" / "rt" / "foliage" / "mesh_bounds.json")
        cnt = rng.poisson(expected[k] * k_map)
        iy, ix = np.nonzero(cnt)
        reps = cnt[iy, ix]
        iy, ix = np.repeat(iy, reps), np.repeat(ix, reps)
        slo, shi = d["scale"]
        sc = slo + (shi - slo) * rng.random(len(ix)) ** 1.3          # more short ones than tall ones
        foot = FOOTPRINT * r_xy * sc
        soft_ok = rim[iy, ix] & (foot <= RIM_FOOT_M) & (d["kind"] in ("grass", "shrub"))
        keep = ((d_road[iy, ix] >= ROAD_CLEAR_M + foot) | soft_ok) & (d_prop[iy, ix] >= PROP_CLEAR_M + _prop_share(d, foot) * foot)
        dropped += int((~keep).sum())
        iy, ix, sc = iy[keep], ix[keep], sc[keep]
        fx, fy = rng.random(len(ix)), rng.random(len(iy))
        x = wlo[0] + (ix + fx) * TEXEL
        y = wlo[1] + (iy + fy) * TEXEL
        # the plant laid on the ground over its whole footprint (_fit_ground); a plant that does not fit is tried at
        # half its size, then dropped
        h_m = _height(d["meshes"], stage_dir.parent.parent / "acr" / "rt" / "foliage" / "mesh_bounds.json")
        z, nx, ny, nz, ok = _fit_ground(hgt, wlo, x, y, FIT_SHARE * r_xy * sc, h_m * sc, d["max_slope_deg"])
        retry = ~ok & (sc * 0.5 >= 0.3)
        if retry.any():
            s2 = sc[retry] * 0.5
            z2, nx2, ny2, nz2, ok2 = _fit_ground(hgt, wlo, x[retry], y[retry], FIT_SHARE * r_xy * s2, h_m * s2,
                                                 d["max_slope_deg"])
            idx = np.where(retry)[0]
            for arr, new in ((z, z2), (nx, nx2), (ny, ny2), (nz, nz2), (sc, s2)):
                arr[idx] = np.where(ok2, new, arr[idx])
            ok[idx] = ok2
            refit[0] += int(ok2.sum())
        dropped += int((~ok).sum())
        refit[1] += int((~ok).sum())
        rows.append((k, x[ok], y[ok], z[ok], sc[ok], nx[ok], ny[ok], nz[ok]))
        counts[k] = int(ok.sum())
    # ---- above tunnels: shrubs and leafy trees on the hill (the tunnel road no longer counts as road there)
    # (only the stage's own tunnels: road the route takes under the hill for TUNNEL_MIN_M at least; a side road's few
    # triangles under a bank, Arganil s 7555 or Paleohori's off-road, get nothing)
    under = rt[_bilinear(H, (ox, oy), rt[:, 0], rt[:, 1]) - rt[:, 2] > TUNNEL_COVER_M]
    if len(tunnel_T) and len(under) >= TUNNEL_MIN_M:
        c_t = road["positions"][tunnel_T].mean(1)
        near_t = _raster(under, wlo, shape, TEXEL)
        d_t = _dist(near_t, 16.0)
        ii = np.clip(((c_t[:, 1] - wlo[1]) / TEXEL).astype(int), 0, shape[0] - 1)
        jj = np.clip(((c_t[:, 0] - wlo[0]) / TEXEL).astype(int), 0, shape[1] - 1)
        tunnel_T = tunnel_T[np.isfinite(d_t[ii, jj]) & (d_t[ii, jj] <= 15.0)]
    else:
        tunnel_T = tunnel_T[:0]
    if len(tunnel_T):
        try:
            for r in _tunnel_cover(road["positions"], tunnel_T, road, extra, H, (ox, oy), rng, log):
                rows.append(r)
                counts[r[0]] = counts.get(r[0], 0) + len(r[1])
        except Exception as e:
            log(f"above tunnels: nothing added ({type(e).__name__}: {e})")
    near_n = sum(counts.values())

    # ---- meadow ring (wide grass patches out to the grass's cull distance)
    meadow_n = 0
    try:
        mrows = _meadow(names, sp, H, meta, rt, road, extra, rng, STYLE_NAME[0], log)
        rows += mrows
        meadow_n = sum(len(r[1]) for r in mrows)
    except Exception as e:
        log(f"meadow ring: not added ({type(e).__name__}: {e})")

    # ---- far forest, 4 m cells over the whole terrain window
    nf = int(min(nrows, ncols) * TEXEL / FAR_CELL)
    flo = (ox, oy)
    d_far = _dist(_raster(rt, flo, (nf, nf), FAR_CELL), FAR_FULL_M + 20, FAR_CELL)
    ramp = np.clip((d_far - FAR_START_M) / (FAR_FULL_M - FAR_START_M), 0.0, 1.0)
    ramp[~np.isfinite(d_far)] = 1.0
    for P_, T_ in ((road["positions"], road["triangles"]), (extra["positions"], extra["triangles"])):
        if len(T_):
            near_ = _dist(_raster(_tri_points(P_, T_), flo, (nf, nf), FAR_CELL), FAR_CLEAR_M, FAR_CELL)
            ramp[np.isfinite(near_) & (near_ <= FAR_CLEAR_M)] = 0.0
    step = int(FAR_CELL / TEXEL)
    fa, fb = sp["a"][::step, ::step][:nf, :nf], sp["b"][::step, ::step][:nf, :nf]
    fw = sp["w"][::step, ::step][:nf, :nf].astype(np.float32) / 255.0
    lut = np.zeros(256, np.float32)
    for li, ln in names.items():
        cls = _layer_class(ln)                   # the unstyled class: the far forest compares by identity
        ha = FAR_DENSITY_HA.get(ln, 260 if cls is FOREST else 90 if cls is GRASS else 75 if cls is DRY else
                                60 if cls is GRAVEL_GRASS else 12 if cls is BARE else 0)
        lut[li] = ha / 10000.0
    fexp = (lut[fa] * fw + lut[fb] * (1.0 - fw)) * ramp * FAR_CELL * FAR_CELL
    fexp *= min(1.0, FAR_CAP / max(float(fexp.sum()), 1.0))
    cnt = rng.poisson(fexp)
    iy, ix = np.nonzero(cnt)
    iy, ix = np.repeat(iy, cnt[iy, ix]), np.repeat(ix, cnt[iy, ix])
    x = ox + (ix + rng.random(len(ix))) * FAR_CELL
    y = oy + (iy + rng.random(len(iy))) * FAR_CELL
    hi_ = np.clip(((y - oy) / TEXEL).astype(int), 1, H.shape[0] - 2)
    hj_ = np.clip(((x - ox) / TEXEL).astype(int), 1, H.shape[1] - 2)
    zf = np.minimum.reduce([H[hi_, hj_], H[hi_ + 1, hj_], H[hi_, hj_ + 1], H[hi_ - 1, hj_], H[hi_, hj_ - 1]])
    sl = np.degrees(np.arctan(np.hypot(H[hi_, hj_ + 1] - H[hi_, hj_ - 1], H[hi_ + 1, hj_] - H[hi_ - 1, hj_]) / (2 * TEXEL)))
    kinds = rng.choice(list(FAR_MIX), size=len(x), p=list(FAR_MIX.values()))
    for k in FAR_MIX:
        d = SPECIES[k]
        m = (kinds == k) & (sl <= d["max_slope_deg"])
        slo, shi = d["scale"]
        sc = slo + (shi - slo) * rng.random(int(m.sum()))
        ones = np.ones(int(m.sum()))
        rows.append((k, x[m], y[m], zf[m], sc, 0 * ones, 0 * ones, ones))
        counts[k] = int(m.sum())

    out = []
    for k, x, y, z, sc, nx, ny, nz in rows:
        nm = len(SPECIES[k]["meshes"])
        mi = rng.integers(0, nm, len(x))
        yaw = rng.random(len(x)) * 360.0
        for q in range(len(x)):
            out.append({"species": k, "mesh": int(mi[q]), "x": round(float(x[q]), 3), "y": round(float(y[q]), 3),
                        "z": round(float(z[q]), 3), "z_collision": round(float(z[q]), 3),
                        "yaw_deg": round(float(yaw[q]), 1), "scale": round(float(sc[q]), 3),
                        "normal": [round(float(nx[q]), 4), round(float(ny[q]), 4), round(float(nz[q]), 4)],
                        "src": "wr_groundcover", "max_visible_m": -1.0})
    log(f"ground cover: {near_n} plants of {len(near_species)} kinds ({dropped} dropped: footprint on the road or a "
        f"prop, or not fitting the ground ({refit[1]}); {refit[0]} made smaller to fit)"
        f"{'' if k_scale >= 1 else f', densities x{k_v:.2f} on the verge and x{k_r:.2f} beyond for the {CAP_TOTAL} cap'}"
        f"; {int(rim.sum() * TEXEL * TEXEL)} m2 of gravel road rim open to grass; "
        f"meadow: {meadow_n} patches; "
        f"far forest: {len(out) - near_n - meadow_n} trees from {FAR_START_M:.0f} m "
        f"({', '.join(f'{k} {counts[k]}' for k in FAR_MIX)})")
    return out


def append(stage_dir, log=print):
    try:
        import tools.datafiles as df
        cfg = df.load_json(f"stage_builds/{Path(stage_dir).name}.json")
    except Exception:
        cfg = {}
    STYLE.clear()
    STYLE.update(STYLES.get(cfg.get("ground_cover_style"), {}))
    STYLE_NAME[0] = cfg.get("ground_cover_style")
    if STYLE:
        log(f"ground cover: {cfg.get('ground_cover_style')} style ({', '.join(f'{a}->{b}' for a, b in STYLE.items())})")
    p = Path(stage_dir) / "vegetation" / "instances.json"
    d = json.loads(p.read_text(encoding="utf-8"))
    d["instances"] = [r for r in d["instances"] if r.get("src") != "wr_groundcover"] + generate(stage_dir, log=log)
    if cfg.get("service_park_tent"):                       # the service park tent's clearing (wr_servicepark.py)
        try:
            import wr_servicepark
            n0 = len(d["instances"])
            d["instances"] = wr_servicepark.clear_plants(d["instances"], stage_dir)
            log(f"service park: {n0 - len(d['instances'])} plants off the tent's clearing")
        except Exception as e:
            log(f"service park: plants kept on the clearing ({type(e).__name__}: {e})")
    p.write_text(json.dumps(d), encoding="utf-8")
