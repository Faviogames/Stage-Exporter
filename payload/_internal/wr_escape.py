"""Escaping crowd: ACR's own BC_CrowdEscapeReaction_C (owner 2026-11-18: "público que reacciona y sale corriendo").

The actor is a crowd character (CrowdSkeletalMeshComponent root) with a SplineTrigger child actor (SplineEventTrigger) that
stands on the road 35-85 m ahead of him, in his own frame: when the car passes it he plays the "Reaction" (Waiting -> Enter ->
Run) and runs off. 12 configs (DA_Escape_<HandFree|Phone|Camera>_<Left|Right>...), baked in the actor (Config + the
CrowdReactionNew animation), so a variant is a copy of a stock actor with that config. The only stock examples are Greece
Elatia's 9 tiny cells (GreeceS3Elatia/_Generated_/<cell>), extracted once from ACR's paks (retoc to-legacy).
Stage build "escape_reaction": [{"at": [x, y, z] WRCG m, "variant": "HandFree_Right_01", "trigger_m": 50}]
  variant: any DA_Escape_ suffix (default: the Right ones on the left side of the road, the Left ones on the right, i.e.
  running away from the road - the side of Left / Right is the character's, unchecked in game); trigger_m: the trigger is
  put on the route this far before the person (he faces it); chance: EnableChance of the blueprint (0.5 by default: half of
  ACR's own people never react; here 1.0 unless the stage says otherwise).
Not checked in game.
"""
import copy
import json
import math
import shutil
import tempfile

from pathlib import Path

import numpy as np

import wr_finish as wf

LEVEL_DIR = "Levels/GreeceS3Elatia/_Generated_/"
CELLS = ("0RB44HDVM0PJNMPFN42542UPH 1697DX4GDIPJDU4SRR6PEJ78T 5QSJ461SY8MU166H3F7ETXGPZ 7O6RQS49XLV8TNUGCNBY2FKFD "
         "BXMZOHDX7LRJFJIAAE05M4SE0 E7QBHK6LKXXZUY0041JXH2F53 EBL88G1SCGUXGWXCG2CO71HOU").split()
ACTOR_CLASS = "BC_CrowdEscapeReaction_C"
DEFAULT_CONFIG = "DA_Escape_HandFree_Left_01"      # the blueprint's own: stock actors without a Config property have it
SIDE_DEFAULT = {"left": "HandFree_Right_01", "right": "HandFree_Left_01"}     # of the road, as the driver sees it


def _dir(work_acr):
    return Path(work_acr) / "wr_escape"


def prepare(work_acr, paks):
    """Extracts, once, the stock cells that hold the actor (retoc to-legacy + UaTool)."""
    import tools.acrmod.common as c
    d = _dir(work_acr)
    d.mkdir(parents=True, exist_ok=True)
    for cell in CELLS:
        out = d / f"{cell}.json"
        if out.exists():
            continue
        tmp = Path(tempfile.mkdtemp(prefix="wr_escape_"))
        try:
            c.retoc("to-legacy", paks, str(tmp), "-f", cell, "--version", "UE5_6", "--no-shaders")
            c.asset_json(tmp / "acr" / "Content" / (LEVEL_DIR + cell + ".umap"), out)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


def _prop(e, name):
    return next((p for p in (e.get("Data") or []) if isinstance(p, dict) and p.get("Name") == name), None)


def _body(cell, i):
    return next(c for c in range(1, len(cell.exports) + 1)
                if cell.exp(c).get("OuterIndex") == i and cell.class_name(c) == "CrowdSkeletalMeshComponent")


def variants(work_acr, U):
    """{config name: (cell JSON path, actor export index)}: the actors whose body has a RelativeRotation to set."""
    found = {}
    for f in sorted(_dir(work_acr).glob("*.json")):
        cell = U(json.loads(f.read_text(encoding="utf-8")))
        for i in range(1, len(cell.exports) + 1):
            if cell.class_name(i) != ACTOR_CLASS:
                continue
            if _prop(cell.exp(_body(cell, i)), "RelativeRotation") is None:
                continue
            found.setdefault(_cfg_name(cell, i), (f, i))
    return found


def _cfg_name(cell, i):
    """The DA_Escape_* name of actor export i (no Config property = the blueprint's default)."""
    p = _prop(cell.exp(i), "Config")
    if not p or not isinstance(p.get("Value"), int) or p["Value"] >= 0:
        return DEFAULT_CONFIG
    return str(cell.j["Imports"][-p["Value"] - 1]["ObjectName"])


def _set_chance(dst, e, chance):
    """The blueprint's EnableChance (a double, 0.5 in the class defaults: the reaction only plays that often)."""
    p = _prop(e, "EnableChance")
    if p is None:
        p = {"$type": "UAssetAPI.PropertyTypes.Objects.DoublePropertyData, UAssetAPI", "Name": "EnableChance", "ArrayIndex": 0,
             "PropertyGuid": None, "IsZero": False, "PropertyTagFlags": "None", "PropertyTypeName": None,
             "PropertyTagExtensions": "NoExtension", "Value": 0.0}
        e["Data"].append(p)
        dst.add_name("EnableChance")
    p["Value"] = float(chance)


def _remap_data(x, mapping, cell, dst):
    """Every object reference in a property tree (the actor's components) moved to the new level's exports / imports."""
    if isinstance(x, dict):
        if "ObjectPropertyData" in str(x.get("$type", "")) and isinstance(x.get("Value"), int) and x["Value"]:
            x["Value"] = wf._remap_ref(x["Value"], mapping, cell, dst)
        for v in x.values():
            if isinstance(v, (dict, list)):
                _remap_data(v, mapping, cell, dst)
    elif isinstance(x, list):
        for v in x:
            _remap_data(v, mapping, cell, dst)


def _set_vec(e, name, vals):
    v = _prop(e, name)["Value"][0]["Value"]
    for k, x in zip(("X", "Y", "Z") if "X" in v else ("Pitch", "Yaw", "Roll"), vals):
        v[k] = float(x)


def add(dst, work_acr, items, ground, log=print, prefix="WrcgEscape"):
    """items: [(x, y, facing_deg, trigger_xyz, variant[, chance])] in UE cm (facing: world yaw the person looks toward)."""
    U = type(dst)
    table = variants(work_acr, U)
    level = next(i for i in range(1, len(dst.exports) + 1) if dst.class_name(i) == "Level")
    n = 0
    for k, (x, y, face, trig, variant, *rest) in enumerate(items):
        want = variant if variant.startswith("DA_Escape_") else "DA_Escape_" + variant
        if want not in table:
            log(f"    escape reaction: no stock actor with {want} (have {', '.join(sorted(table))}), skipped")
            continue
        path, src = table[want]
        cell = U(json.loads(Path(path).read_text(encoding="utf-8")))
        cell_level = next(i for i in range(1, len(cell.exports) + 1) if cell.class_name(i) == "Level")
        # the actor export by hand (as wr_finish: the SplineTrigger child actor and the actor refer to each other, so clone
        # cannot take the actor whole), its components cloned under it with the actor pre-mapped
        name = f"{prefix}_{k}"
        e = copy.deepcopy(cell.exp(src))
        e["ObjectName"] = name
        dst.add_name(name)
        e["OuterIndex"] = level
        for key in ("ClassIndex", "TemplateIndex", "SuperIndex"):
            e[key] = wf._remap_ref(e[key], {}, cell, dst) if e[key] < 0 else 0
        dst.exports.append(e)
        actor = len(dst.exports)
        mapping = {src: actor, cell_level: level}
        for c in [i for i in range(1, len(cell.exports) + 1) if cell.exp(i).get("OuterIndex") == src]:
            if c not in mapping:
                mapping.update(dst.clone(cell, c, actor, preset=dict(mapping)))
        _remap_data(e.get("Data"), mapping, cell, dst)
        for key in ("SerializationBeforeSerializationDependencies", "CreateBeforeSerializationDependencies",
                    "SerializationBeforeCreateDependencies"):
            e[key] = [wf._remap_ref(i, mapping, cell, dst) for i in e.get(key) or []]
        e["CreateBeforeCreateDependencies"] = [level]
        _set_chance(dst, e, rest[0] if rest else 1.0)
        dst.register_actor(level, actor)
        for s, d in mapping.items():                       # the SplineTrigger child actor lives in the level too
            if s not in (src, cell_level) and cell.exp(s).get("OuterIndex") == cell_level:
                dst.register_actor(level, d)
        body = mapping[_body(cell, src)]
        z = ground(float(x), float(y), float(trig[2]))
        z = float(trig[2]) if z is None or not math.isfinite(z) else float(z)
        _set_vec(dst.exp(body), "RelativeLocation", (x, y, z))
        yaw = face - 90.0                                  # the characters look along their local +Y
        _set_vec(dst.exp(body), "RelativeRotation", (0.0, yaw, 0.0))
        r = math.radians(-yaw)
        dx, dy = float(trig[0]) - x, float(trig[1]) - y
        local = (dx * math.cos(r) - dy * math.sin(r), dx * math.sin(r) + dy * math.cos(r), float(trig[2]) - z)
        child = next(mapping[c] for c in mapping if cell.class_name(c) == "ChildActorComponent")
        _set_vec(dst.exp(child), "RelativeLocation", local)
        for s, d in mapping.items():
            if s != cell_level:
                dst._add_export_names(dst.exp(d))
        n += 1
        log(f"    escape reaction: {want} at ({x / 100:.0f}, {y / 100:.0f}), trigger {math.hypot(local[0], local[1]) / 100:.0f} m ahead "
            f"({len(mapping)} exports)")
    return n


def main():
    assert SIDE_DEFAULT["left"] != SIDE_DEFAULT["right"]
    print("wr_escape self-check ok")


if __name__ == "__main__":
    main()
