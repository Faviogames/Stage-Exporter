"""Reads back a built stage of our version from the pack: tyres / weather rows, and what our fixes put in the level.

  wrcg2acr-worker.exe -m wr_verify [<build name, e.g. WrcgEsSS1>]   (default WrcgEsSS4)
"""
import base64
import collections
import json
import math
import os
from pathlib import Path


def _data_names(o, out, tagged=False):
    """Names a table's rows write: name values and soft paths (unversioned packages write no property names or struct
    types; the stock tables keep those past NamesReferencedFromExportDataCount), plus those when tagged."""
    if isinstance(o, dict):
        t = str(o.get("$type", ""))
        if tagged:
            for k in ("Name", "StructType"):
                if isinstance(o.get(k), str):
                    out.add(o[k])
        if "NamePropertyData" in t and isinstance(o.get("Value"), str):
            out.add(o["Value"])
        if "FTopLevelAssetPath" in t:
            for k in ("PackageName", "AssetName"):
                if isinstance(o.get(k), str):
                    out.add(o[k])
        for v in o.values():
            _data_names(v, out, tagged)
    elif isinstance(o, list):
        for v in o:
            _data_names(v, out, tagged)


def check_tables(leg, out):
    """Every data table of the pack: its rows may only use the first NamesReferencedFromExportDataCount names of the
    package, else ACR stops at start-up ('Bad name index 36/35', DT_TracksLocationsLogos, 2026-11-09); a row name that
    reads back as a number is such a reference too."""
    import tools.acrmod.common as c
    bad = []
    tables = sorted((leg / "Data").rglob("DT_*.uasset"))
    for f in tables:
        j = out / f"tbl_{f.stem}.json"
        c.asset_json(f, j)
        d = json.load(open(j, encoding="utf-8"))
        count, nm = d.get("NamesReferencedFromExportDataCount"), d["NameMap"]
        rows = [x for x in d["Exports"] if "Table" in x]
        used = set()
        tagged = not d.get("IsUnversioned", True)
        for x in rows:
            used.update(str(r["Name"]) for r in x["Table"]["Data"])
            _data_names(x["Table"]["Data"], used, tagged)
        past = sorted(n for n in used if n in nm and isinstance(count, int) and nm.index(n) >= count)
        numeric = [r["Name"] for x in rows for r in x["Table"]["Data"] if str(r["Name"]).isdigit()]
        if past or numeric:
            bad.append(f"{f.stem}: names past the count {past}, numeric rows {numeric}")
    print(f"tables: {len(tables)} checked, " + ("all good" if not bad else "PROBLEMS: " + "; ".join(bad)))
    return not bad


def main():
    import sys
    NAME = sys.argv[1] if len(sys.argv) > 1 else "WrcgEsSS4"
    import wr
    import tools.exporter.pipeline as pl
    os.environ.update(pl._env(*wr._installs(), None))
    import tools.acrmod.common as c
    import tools.acrmod.vegetation_visual as vv
    leg = wr.ROOT / "work/acr/mods/wrcg_stages/legacy/acr/Content"
    out = Path(os.environ["TEMP"]) / "wr_verify"
    out.mkdir(exist_ok=True)
    sel = leg / "Data/Database/Main/TrackSelection"
    tables_ok = check_tables(leg, out)
    for name, row, fields in (("DT_TracksVariants", NAME + "Full", ("CarSetupDefaultSurfaceType", "TireCompounds")),
                              ("DT_Tracks", NAME, ("WeatherTypesDistribution",))):
        c.asset_json(sel / f"{name}.uasset", out / f"{name}.json")
        d = json.load(open(out / f"{name}.json", encoding="utf-8"))
        r = next(x for x in d["Exports"][0]["Table"]["Data"] if x["Name"] == row)
        m = {p["Name"]: p for p in r["Value"]}
        print(name, row, {f: m[f]["Value"][1]["Value"] for f in fields})

    c.asset_json(leg / f"Levels/{NAME}.umap", out / f"{NAME}.json")
    d = json.load(open(out / f"{NAME}.json", encoding="utf-8"))
    ex, im = d["Exports"], d["Imports"]
    nm = lambda i: (ex[i - 1]["ObjectName"] if i > 0 else im[-i - 1]["ObjectName"]) if i else None
    cls = lambda e: nm(e["ClassIndex"])
    props = lambda e: {p["Name"]: p for p in e["Data"]} if isinstance(e.get("Data"), list) else {}
    cnt = collections.Counter(cls(e) for e in ex)

    # spectators: element facing vs the road (+Y forward, relative to a yaw-0 root)
    sp = [e for e in ex if cls(e) == "BC_CrowdSystemSpawnerBakedActor_C"]
    people = sum(len(next(f for f in props(e)["BakedSpawnData"]["Value"] if f["Name"] == "Elements")["Value"]) for e in sp)
    tags = {props(e)["Tags"]["Value"][0]["Value"] for e in sp}
    print(f"crowd: {len(sp)} spawners, {people} spectators, {len(tags)} distinct ids, "
          f"{cnt.get('BC_CrowdManagedAmbientSound_C', 0)} crowd sounds, manager {cnt.get('BC_CrowdSystemManager_Wales_C')}")

    # finish marshal
    fm = [e for e in ex if cls(e) == "BC_StopMarshalEndSequence_C"]
    print(f"finish marshal: {len(fm)} ({[e['ObjectName'] for e in fm]}), start marshal {cnt.get('BC_StopMarshalStartSequence_C')}")

    # RVT
    vol = [e for e in ex if cls(e) == "RuntimeVirtualTextureComponent"]
    print("RVT volume:", [nm(props(e)["VirtualTexture"]["Value"]) for e in vol])
    writers = [e for e in ex if e["ObjectName"].startswith("WrcgRvtWriter_")]
    wc = [ex[props(e)["StaticMeshComponent"]["Value"] - 1] for e in writers]
    print(f"RVT writers: {len(writers)}, pass {collections.Counter(props(x)['VirtualTextureRenderPassType']['Value'] for x in wc)}, "
          f"material {collections.Counter(nm(props(x)['OverrideMaterials']['Value'][0]['Value']) for x in wc)}, "
          f"rvts {collections.Counter(tuple(nm(v['Value']) for v in props(x)['RuntimeVirtualTextures']['Value']) for x in wc)}")

    # vegetation HISMs: instances per mesh, materials
    rows = collections.defaultdict(lambda: [0, set()])
    owner = lambda e: ex[e["OuterIndex"] - 1]["ObjectName"]
    for e in ex:
        if cls(e) != "HierarchicalInstancedStaticMeshComponent" or not e.get("Extras"):
            continue
        p = props(e)
        mesh = nm(p["StaticMesh"]["Value"]) if "StaticMesh" in p else None
        n = len(vv.parse_hism_extras(base64.b64decode(e["Extras"]))["matrices"])
        mats = tuple(nm(x["Value"]) for x in p["OverrideMaterials"]["Value"]) if "OverrideMaterials" in p else None
        key = owner(e).replace("WrcgVeg_", "")
        rows[key][0] += n
        rows[key][1].add((mesh, mats))
    tot = sum(v[0] for v in rows.values())
    print(f"vegetation: {tot} instances in {len(rows)} HISM actors")
    for key, (n, mats) in sorted(rows.items(), key=lambda kv: -kv[1][0]):
        print(f"   {key:<26} {n:>7}  {sorted(map(str, mats))[:1]}")

    # v4: lights, skids, cameras, flares, service park
    print("lamp lights:", cnt.get("BP_MonBolStreetLampB3_LightOnly_C"), "| skid decals:",
          sum(1 for e in ex if e["ObjectName"].startswith(NAME + "Skid_")))
    cams = [e for e in ex if cls(e) == "TvCameraComponent"]
    trk = collections.Counter(str(next((f["Value"] for f in props(e)["TrackingSettings"]["Value"] if f["Name"] == "bEnableTracking"), None))
                              if "TrackingSettings" in props(e) else "no settings" for e in cams)
    zk = [len(props(e)["ZoomSettings"]["Value"]) for e in cams if "ZoomSettings" in props(e)] or [0]
    print(f"replay cameras: {len(cams)}, tracking {dict(trk)}, zoom keys {min(zk)}-{max(zk)}")
    fl = sum(1 for e in sp for el in next(f for f in props(e)["BakedSpawnData"]["Value"] if f["Name"] == "Elements")["Value"]
             for a in next(q for q in el["Value"] if q["Name"] == "AdditionalMeshes")["Value"]
             if any(x.get("Value") == "Smoke" for x in a["Value"]))
    print("spectators with flares:", fl)
    s = next(e for e in ex if cls(e) == "ServiceParkTargetPoint")
    r = props(ex[props(s)["RootComponent"]["Value"] - 1])["RelativeRotation"]["Value"][0]["Value"]
    print("service park yaw:", round(float(r["Yaw"]), 1))
