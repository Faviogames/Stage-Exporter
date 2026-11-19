"""Time penalty for running into the crowd, made by the game itself (owner 2026-11-14: "penalice 20 s minimo").

ACR's CurveCut penalty comes from BC_RacePenaltyPolicyPropsCollision: a car that touches an actor tagged
Penalty.CurveCut.Cone (BC_CornerCutting_Cone, Alsace's cones) is penalised. The stock tables set that policy's time to 0
s (Light and Realistic), so two things are needed (report of the REA subagent, paks read with retoc/uatool):
  1. cones along the front of each crowd cluster: the cone actor is copied from a stock Munster cell into our level, its
     mesh hidden in game (collision stays), standing between the spectators and the road;
  2. the stock table DA_RacePenaltyDataFreePractice (our stages are Free Practice only) written again in our pak with the
     two PropsCollision times at PENALTY_S.
Stage build "crowd_penalty": true switches the cones on; the table goes in with every pack (it only matters if a cone is
touched; Alsace's own cones then cost PENALTY_S in Free Practice too).
Not checked in game: that the tag on the cloned actor (it comes from the blueprint's defaults) is enough to trigger.
"""
import base64
import copy
import json
import os
import shutil
import tempfile

from pathlib import Path

import numpy as np

import wr_finish as wf

PENALTY_S = 20.0
CELL = "AlsaceS2Munster/_Generated_/8SSEL1J4U0KQWCDN5SX29T6UW"        # holds 5 BC_CornerCutting_Cone_C actors
CONE_CLASS_IMPORT = "BC_CornerCutting_Cone_C"
TABLE = "DA_RacePenaltyDataFreePractice"
TABLE_DIR = "Data/Gameplay/RacePenalties"
RAW_SIZE, RAW_HEADER = 90, bytes.fromhex("00043c0214 03".replace(" ", ""))
REF_AT = (6, 10, 14, 22)                 # RootComponent, two component refs, the array element
GUID_AT = 58                             # 16 bytes: the actor's GUID (a copy would share it)
SIDE_M = 1.0                             # the cone stands this far from the spectator, toward the road
CELL_M = 3.0                             # one cone per cell of this size
FINISH_CELL_M = 1.5                      # cone spacing in the last FINISH_DENSE_M route points (about metres)
FINISH_DENSE_M = 150
MAX_CONES = 500                          # the automatic clusters come last in the spots: 160 ended before them (owner test 2026-11-14)


def _paths(work_acr):
    d = Path(work_acr) / "wr_penalty"
    return d, d / "cone_cell.json", d / f"{TABLE}.json"


def prepare(work_acr, paks):
    """Extracts, once, the cone's cell and the penalty table from ACR's own paks (retoc to-legacy + UaTool)."""
    import tools.acrmod.common as c
    d, cell_json, table_json = _paths(work_acr)
    d.mkdir(parents=True, exist_ok=True)
    for out, name, rel in ((cell_json, CELL.rsplit("/", 1)[-1], "Levels/" + CELL + ".umap"),
                           (table_json, TABLE, TABLE_DIR + "/" + TABLE + ".uasset")):
        if out.exists():
            continue
        tmp = Path(tempfile.mkdtemp(prefix="wr_penalty_"))
        try:
            c.retoc("to-legacy", paks, str(tmp), "-f", name, "--version", "UE5_6", "--no-shaders")
            c.asset_json(tmp / "acr" / "Content" / rel, out)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


# --- 1. the table ----------------------------------------------------------------------------------------------------

def edit_table(j, seconds=PENALTY_S):
    """Sets the TimePenalty of the effects PropsCollision's EffectsMap points to; returns how many."""
    E = j["Exports"]
    pol = next(e for e in E if "PropsCollision" in e["ObjectName"])
    n = 0
    for ent in next(p for p in pol["Data"] if p["Name"] == "EffectsMap")["Value"]:
        tgt = E[ent[1]["Value"] - 1]
        for p in tgt.get("Data") or []:
            if p.get("Name") == "TimePenalty":
                p["Value"] = float(seconds)
                n += 1
    return n


def write_table(write_asset, work_acr, out_uasset_dir):
    """Called when the pack's tables are written: our version of the stock table goes next to them."""
    d, _, table_json = _paths(work_acr)
    if not table_json.exists():
        return False
    j = json.loads(table_json.read_text(encoding="utf-8"))
    if edit_table(j) < 1:
        return False
    out = Path(out_uasset_dir) / TABLE_DIR / f"{TABLE}.uasset"
    out.parent.mkdir(parents=True, exist_ok=True)
    write_asset(j, d / f"{TABLE}.edit.json", out)
    return True


# --- 2. the cones ----------------------------------------------------------------------------------------------------

def cone_points(spots_ue, route_ue, near_m=(3.0, 120.0), cell_m=None):
    """One point per CELL_M cell (cell_m overrides it), SIDE_M from a spectator toward the road (UE cm)."""
    S = np.asarray(spots_ue, float)[:, :2]
    R = np.asarray(route_ue, float)[:, :2]
    seen, out = set(), []
    for p in S:
        d = np.hypot(R[:, 0] - p[0], R[:, 1] - p[1])
        i = int(d.argmin())
        if not (near_m[0] * 100 <= d[i] <= near_m[1] * 100):
            continue
        cell = cell_m or (FINISH_CELL_M if i >= len(R) - FINISH_DENSE_M else CELL_M)       # the finish crowd: a denser wall of cones (owner 2026-11-16: walked through)
        k = (cell, int(p[0] // (cell * 100)), int(p[1] // (cell * 100)))
        if k in seen:
            continue
        seen.add(k)
        v = (R[i] - p) / max(d[i], 1.0)
        out.append(p + v * SIDE_M * 100)
        if len(out) >= MAX_CONES:
            break
    return np.asarray(out)


def _bool_prop(template, name):
    p = copy.deepcopy(template)
    p["Name"], p["Value"] = name, True
    return p


def add_cones(dst, work_acr, points_ue, ground, log=print):
    _, cell_json, _ = _paths(work_acr)
    if not cell_json.exists() or not len(points_ue):
        log("    crowd penalty: no cone data, skipped")
        return 0
    U = type(dst)
    cell = U(json.loads(cell_json.read_text(encoding="utf-8")))
    src = next(i for i in range(1, len(cell.exports) + 1) if cell.class_name(i) == CONE_CLASS_IMPORT)
    raw0 = base64.b64decode(cell.exp(src)["Data"])
    if len(raw0) != RAW_SIZE or raw0[:6] != RAW_HEADER:
        log("    crowd penalty: unexpected raw layout of the cone actor, skipped")
        return 0
    level = next(i for i in range(1, len(dst.exports) + 1) if dst.class_name(i) == "Level")
    cell_level = next(i for i in range(1, len(cell.exports) + 1) if cell.class_name(i) == "Level")
    comps = [i for i in range(1, len(cell.exports) + 1) if cell.exp(i).get("OuterIndex") == src]
    n = 0
    for k, xy in enumerate(points_ue):
        name = f"WrcgPenaltyCone_{k}"
        e = copy.deepcopy(cell.exp(src))
        e["ObjectName"] = name
        dst.add_name(name)
        e["OuterIndex"] = level
        for key in ("ClassIndex", "TemplateIndex", "SuperIndex"):
            e[key] = wf._remap_ref(e[key], {}, cell, dst) if e[key] < 0 else 0
        dst.exports.append(e)
        actor = len(dst.exports)
        mapping = {src: actor, cell_level: level}
        for c in comps:
            if c not in mapping:
                mapping.update(dst.clone(cell, c, actor, preset=dict(mapping)))
        b = bytearray(raw0)
        for o in REF_AT:
            wf.struct.pack_into("<i", b, o, wf._remap_ref(wf._i32(b, o), mapping, cell, dst))
        b[GUID_AT:GUID_AT + 16] = os.urandom(16)
        e["Data"] = base64.b64encode(bytes(b)).decode()
        for key in ("SerializationBeforeSerializationDependencies", "CreateBeforeSerializationDependencies",
                    "SerializationBeforeCreateDependencies"):
            e[key] = [wf._remap_ref(i, mapping, cell, dst) for i in e.get(key) or []]
        e["CreateBeforeCreateDependencies"] = [level]
        dst.register_actor(level, actor)
        mesh = next(mapping[c] for c in comps if "StaticMeshComponent" in str(cell.class_name(c)))
        data = dst.exp(mesh)["Data"]
        loc = wf._vec(dst.exp(mesh), "RelativeLocation")
        loc["X"], loc["Y"], loc["Z"] = float(xy[0]), float(xy[1]), float(ground(float(xy[0]), float(xy[1]), 0.0)) + 5.0
        tmpl = next(p for c in comps for p in cell.exp(c).get("Data") or [] if p.get("Name") == "bNetAddressable")
        data += [_bool_prop(tmpl, "bHiddenInGame"), _bool_prop(tmpl, "bVisible")]
        data[-1]["Value"] = False
        for s, d in mapping.items():
            if s != cell_level:
                dst._add_export_names(dst.exp(d))
        n += 1
    log(f"    crowd penalty: {n} hidden cones in front of the spectators (CurveCut, {PENALTY_S:g} s once the table is in)")
    return n


def main():     # self-check on synthetic data: the table edit and the cone points
    j = {"Exports": [{"ObjectName": "BC_RacePenaltyPolicyPropsCollision_C_1",
                      "Data": [{"Name": "EffectsMap", "Value": [[{"Value": "L"}, {"Value": 2}], [{"Value": "R"}, {"Value": 3}]]}]},
                     {"ObjectName": "x", "Data": [{"Name": "TimePenalty", "Value": 0.0}]},
                     {"ObjectName": "y", "Data": [{"Name": "TimePenalty", "Value": 0.0}]}]}
    assert edit_table(j) == 2 and j["Exports"][1]["Data"][0]["Value"] == PENALTY_S
    route = np.c_[np.arange(0, 20000, 100.0), np.zeros(200)]
    spots = np.array([[5000.0, 600.0, 0], [5050.0, 610.0, 0], [5000.0, 1e5, 0], [9000.0, -700.0, 0]])
    pts = cone_points(spots, route)
    assert len(pts) == 2, pts                          # two cells in range, the far spot ignored
    assert abs(pts[0][1] - 500.0) < 5 and abs(pts[1][1] + 600.0) < 5      # 1 m closer to the road
    print("wr_penalty self-check ok")


if __name__ == "__main__":
    main()
