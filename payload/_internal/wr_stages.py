"""Any WRCG rally stage as a stage build of our version (custom/data/stage_builds/<slug>.json), with all our fixes on.

The packaged tool ships hand-made builds for four gravel stages. A stage of data/wrcg_stage_inventory.json becomes a
whole-spline build like gr_ss3 / es_ss4: its slug is the exporter's (stage_spec.slug), the WRCG tag of its start/end
prefabs and spectator graphs comes from its spline node (ES2_SPAIN/SS1 runs on ES2_SS3_TrackSpline, so its crowd and
prefabs are SS3's), the surface, tyres and length from the inventory, and the place (coordinates for the sky and the
menu, time zone, month of the real rally, weather) from the tables below, by WRCG location folder.
"""
import json
import re
from pathlib import Path

from wr import CUSTOM

# location folder -> (lat, lon, UTC offset (standard), daylight saving (EU/US style), rally month, day, weather row)
PLACES = {
    "ES2_SPAIN": (41.15, 1.05, 1, True, 10, 20, "Greece"),        # RallyRACC Catalunya, Salou
    "ES_SPAIN": (41.15, 1.05, 1, True, 10, 20, "Greece"),
    "SSS_ES_MONTJUIC": (41.36, 2.15, 1, True, 10, 20, "Greece"),
    "MC_MONTECARLO": (44.55, 6.08, 1, False, 1, 25, "MonteCarlo"),  # Alpes-de-Haute-Provence / Hautes-Alpes
    "HR_CROATIA": (45.55, 15.55, 1, True, 4, 22, "Alsace"),
    "JP_JAPAN": (35.0, 137.4, 9, False, 11, 16, "Alsace"),
    "BE_YPRES": (50.82, 2.85, 1, True, 8, 18, "Wales"),
    "DE_DEUTSCHLAND": (49.75, 6.75, 1, True, 8, 20, "Alsace"),
    "SSS_DE_PANZERPLATTE": (49.53, 7.08, 1, True, 8, 20, "Alsace"),
    "FR_FRANCECORSE": (41.85, 8.85, 1, True, 4, 10, "Greece"),
    "IT_SANREMO": (43.85, 7.75, 1, True, 10, 10, "Greece"),
    "GB_WALESGB": (53.3, -3.85, 0, True, 10, 4, "Wales"),
    "SSS_TK_MARMARIS": (36.85, 28.27, 3, False, 9, 15, "Greece"),
    "TK_TURKEY": (36.85, 28.27, 3, False, 9, 15, "Greece"),
    "GR_ACROPOLIS": (38.5, 22.4, 2, True, 9, 7, "Greece"),
    "MX_MEXICO": (21.02, -101.26, -6, False, 3, 16, "Greece"),
    "PT2_PORTUGAL": (41.45, -8.17, 0, True, 5, 12, "Greece"),
    "IT_ITALIASARDEGNA": (40.62, 8.54, 1, True, 6, 2, "Greece"),
    "SSS_IT_ITTIRI": (40.62, 8.54, 1, True, 6, 2, "Greece"),
    "EE_ESTONIA": (58.3, 26.7, 2, True, 7, 16, "Alsace"),
    "SSS_EE_TARTU": (58.38, 26.72, 2, True, 7, 16, "Alsace"),
    "KE_KENYA": (-0.7, 36.4, 3, False, 6, 23, "Greece"),
    "SSS_KE_KASARANI": (-1.22, 36.89, 3, False, 6, 23, "Greece"),
    "FI_FINLAND": (62.24, 25.75, 2, True, 8, 2, "Alsace"),
    "SE_SWEDEN": (64.75, 20.95, 1, True, 2, 15, "Livigno"),
    "NO_NORWAY": (60.8, 11.1, 1, True, 2, 20, "Livigno"),
    "CL_CHILE": (-36.8, -73.05, -4, True, 9, 28, "Wales"),
    "AR_ARGENTINA": (-31.4, -64.2, -3, False, 4, 25, "Greece"),
    "NZ_NEWZEALAND": (-37.8, 175.3, 12, True, 9, 29, "Wales"),
    "NZ_NEW_ZEALAND": (-37.8, 175.3, 12, True, 9, 29, "Wales"),
    "FI2_FINLAND": (62.24, 25.75, 2, True, 8, 2, "Alsace"),
    "SSS_FI_HARJU": (62.24, 25.75, 2, True, 8, 2, "Alsace"),
    "SE2_SWEDEN": (63.83, 20.26, 1, True, 2, 15, "Livigno"),         # Umea
    "SSS_AR_FERNET_BRANCA": (-31.4, -64.2, -3, False, 4, 25, "Greece"),
    "SSS_MX_AUTODROMO_LEON": (21.1, -101.7, -6, False, 3, 16, "Greece"),
    "SSS_PT_LOUSADA": (41.28, -8.28, 0, True, 5, 12, "Greece"),
}

COUNTRY_FIX = {"MONTE CARLO": "Monaco", "GREAT BRITAIN": "United Kingdom"}


def country_name(country_en):
    """ACR-side country of a WRCG country name: 'ITALY - SANREMO' -> 'Italy', 'MONTE CARLO' -> 'Monaco'."""
    c = str(country_en or "").split(" - ")[0].strip().upper()
    c = COUNTRY_FIX.get(c, c)
    return " ".join(w.capitalize() for w in c.replace("_", " ").split())
DEFAULT_PLACE = (45.0, 5.0, 1, True, 6, 15, "Greece")
TERRAIN_FAR_GRADES = [[300, 256], [800, 128]]


def place(location_folder):
    return PLACES.get(location_folder, DEFAULT_PLACE)


def utc_offset(location_folder, month):
    """UTC offset on the rally's month, daylight saving included (northern: Apr-Oct, southern: Oct-Mar)."""
    lat, _, std, dst, *_ = place(location_folder)
    if not dst:
        return std
    summer = 4 <= month <= 10 if lat >= 0 else (month >= 10 or month <= 3)
    return std + (1 if summer else 0)


ALLOWED = CUSTOM / "data" / "allowed_stages.json"


def allowed():
    """The WRCG stage ids this installation offers (custom/data/allowed_stages.json: the stages we made and checked,
    shipped with the installer for Sando), or None: every stage."""
    try:
        return set(json.loads(ALLOWED.read_text(encoding="utf-8"))["stages"])
    except (OSError, ValueError, KeyError, TypeError):
        return None


def inventory():
    """WRCG's stages; with an allowed list, only those (the window, `wr list` and `wr add` see no other)."""
    import tools.datafiles as df
    stages = df.load_json("wrcg_stage_inventory.json")["stages"]
    ok = allowed()
    return stages if ok is None else [s for s in stages if s["id"] in ok]


def wrcg_tag(stage):
    """The tag WRCG's prefabs and spectator graphs of this stage use: from the spline node (ES2_SS3_TrackSpline -> SS3)."""
    node = (stage.get("route") or {}).get("spline_node") or ""
    tok = node.split("_TrackSpline")[0].split("_")[-1]           # ES2_SS3_TrackSpline -> SS3, ES2_ES2_... -> ES2
    return tok if re.fullmatch(r"(SS|ES)\d+R?", tok) else stage["id"].split("/")[-1]


def surface(stage):
    """ACR surface of a WRCG stage: Snow when RALLIES.CFG says snow (Sweden, Norway...), else Tarmac when mostly paved."""
    rc = stage.get("rallies_cfg_surface") or {}
    if "SNOW" in str(rc.get("primary", "")).upper() or "SNOW" in str(rc.get("tyre_type", "")).upper():
        return "Snow"
    return "Tarmac" if ((stage.get("surface_sections") or {}).get("paved_pct") or 0) >= 50 else "Gravel"


def build_name(stage):
    parts = stage["location_folder"].split("_")
    if parts[0] == "SSS" and len(parts) > 2:                         # SSS_ES_MONTJUIC/SSS -> WrcgEsMontjuic
        return "Wrcg" + parts[1][:2].title() + "".join(w.title() for w in parts[2:])
    cc = parts[0][:2].title()                                        # ES2_SPAIN/SS1 -> WrcgEsSS1
    return "Wrcg" + cc + stage["id"].split("/")[-1].replace("_", "")


def supported(stage):
    """The exporter builds the road from WRCG's road pieces (PRM); a level without them (city super specials such as
    SSS_ES_MONTJUIC: the street is part of a city terrain object) cannot be exported yet."""
    return ((stage.get("road_assets") or {}).get("prm_files") or 0) > 0


def config(stage):
    import tools.wrcg.stage_spec as ss
    slug = ss.slug(stage["id"])
    lat, lon, _, _, month, day, weather = place(stage["location_folder"])
    surf = surface(stage)
    paved = surf == "Tarmac"
    name = build_name(stage)
    title = stage.get("stage_name_en") or stage["id"]
    rally = (stage.get("rally_name_en") or stage["location_folder"]).replace("–", "-")
    tag = wrcg_tag(stage)
    return {
        "_comment": "Generated by our version (wr_stages.py) from the WRCG inventory; edit freely.",
        "slug": slug, "name": name, "wrcg_level": stage["location_folder"], "stage_id": stage["id"],
        "kind": "spline", "anchor": "route_centre",
        "track_name": title,
        "variant_row": name + "Full", "stage_name": title, "short_name": "Full",
        "start_lat_lon": [lat, lon], "weather_row": weather, "road_width_m": 7.0, "road_roughness": 235,
        "vegetation": True, "props": {"include": ["static", "dynamic", "spline", "decor"]},
        "dressing": False, "dressing_boards": False, "gantry_region": "Greece", "decals": True,
        "pre_start_m": 50.0, "start_marshal": True, "terrain_far_grades": TERRAIN_FAR_GRADES,
        "startends_stage": tag, "crowd_tag": tag, "decal_min_roughness": 0.75, "decal_mark_opacity": 0.5,
        "acr_surface": surf, "weather_distribution": weather,
        "air_temperature_c": -5.0 if surf == "Snow" else 20.0, "crowd": True, "ground_cover": True, "rvt": True, "finish_marshal": True,
        "replay_cameras": True, "lamp_lights": True, "skids": paved, "tyre_marks": False,
        "service_park_yaw_deg": 175.6,
        # owner 2026-11-12: soft dry tarmac tyres suggested and the car's tarmac setup on every tarmac stage
        **({"car_setup": "Tarmac", "tyre_degradation": "Low"} if surf == "Tarmac" else {}),
        "skinned_meshes": True, **({"road_albedo": 0.6} if paved else {}),
        # universal rules (owner 2026-11-15; the code defaults them on, written out so a stage can switch one off):
        "net_solid": True, "fence_solid": True, "rock_solid": True, "tree_solid": True, "own_spawners_only": True,
        "auto_crowd": True, "crowd_penalty": True, "support_vehicles": {"ambulance": 1, "security": 1},
        "brake_boards": True, "far_tree_light": True,
        "corner_posts": True,
        "wrcg_tape_post_physics": True,
        "wrcg_ad_board_physics": True,
        "sky": {"latitude": lat, "longitude": lon, "utc_offset": utc_offset(stage["location_folder"], month),
                "month": month, "day": day},
        "manual_notes": [f"{stage['id']}: {title}, {stage.get('rally_name_en')}, "
                         f"{(stage.get('length_m') or {}).get('sections_cfg') or 0:.0f} m, "
                         f"{'tarmac' if paved else 'gravel'}; WRCG tag {tag}."],
        "export": {"vegetation": "replay", "ui_name": f"{title} ({rally})",
                   "release": True},
    }


def add(stage_id, force=False):
    st = next((s for s in inventory() if s["id"] == stage_id), None)
    if st is None:
        if allowed() is not None:
            raise SystemExit(f"{stage_id!r} is not one of the stages of this installation (see: wrcg2acr-worker.exe -m wr list)")
        raise SystemExit(f"unknown WRCG stage {stage_id!r} (see: wrcg2acr-worker.exe -m wr list)")
    cfg = config(st)
    p = CUSTOM / "data" / "stage_builds" / f"{cfg['slug']}.json"
    if p.exists() and not force:
        print(f"{p.name} exists already (use --force to regenerate it)")
        return cfg["slug"]
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(cfg, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"added {stage_id} as {cfg['slug']}: {cfg['export']['ui_name']}, {cfg['acr_surface'].lower()}, "
          f"sky {cfg['sky']}")
    return cfg["slug"]


def listing(pattern=""):
    rows = []
    for s in inventory():
        if s.get("category") != "rally_stage" or (pattern and pattern.lower() not in json.dumps(s, ensure_ascii=False).lower()):
            continue
        L = (s.get("length_m") or {}).get("sections_cfg") or 0
        paved = ((s.get("surface_sections") or {}).get("paved_pct") or 0)
        rows.append((s["id"], s.get("stage_name_en") or "", s.get("rally_name_en") or "", L, paved))
    for r in sorted(rows):
        print(f"{r[0]:<28} {r[1][:26]:<26} {r[2][:34]:<34} {r[3] / 1000:5.2f} km  {'asfalto' if r[4] >= 50 else 'tierra'}")
