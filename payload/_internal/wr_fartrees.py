"""Lighter far trees (owner 2026-11-15, Seyabei km 3: the distant tree masses and hillside showed almost black).

The far forest (wr_groundcover far_pine / far_oak / far_maple / far_olive: ACR's Aleppo pine, Smoketree, Black maple and
Olive trees) is seen from far away as the stock impostor, whose material M_Impostor darkens the baked ambient occlusion:
AO Pow Pre 2.1, AO Min 0.05. Universal (owner 2026-11-15, after Seyabei): stage build "far_tree_light" (true by default, false = off, or {"ao_min": 0.45, "ao_pow": 1.3}) gives each of those meshes copies
of its impostor material (and of the impostor's LOD-transition child) with those two values, written into the stage's
content like the snow trees' (wr_snowtrees.py); the other slots keep the stock materials. Not checked in game: whether
the impostor is what is black (the leaf LOD and the billboard are not touched), and the right values.
"""
import tempfile
from pathlib import Path

import wr_snowtrees as st

DEFAULTS = {"ao_min": 0.45, "ao_pow": 1.3}
MESHES = {f"/Game/Foliage/Trees/{d}/SM_{d}0{i}" for d, ns in
          (("AleppoPine", (1, 2, 3)), ("Smoketree", (1,)), ("Blackmaple", (1, 2)), ("Olivetree", (1, 2, 3))) for i in ns}
OUT_DIR = "WrFarTrees"
_made = {}


def options(cfg):
    o = (cfg or {}).get("far_tree_light", True)             # universal: on unless a stage sets false
    return dict(DEFAULTS, **o) if isinstance(o, dict) else (dict(DEFAULTS) if o else None)


def _set_scalars(d, values):
    n = 0
    for p in d["Exports"][0]["Data"]:
        if p["Name"] != "ScalarParameterValues":
            continue
        for s in p["Value"]:
            f = {x["Name"]: x for x in s["Value"]}
            name = next(x["Value"] for x in f["ParameterInfo"]["Value"] if x["Name"] == "Name")
            if name in values:
                f["ParameterValue"]["Value"] = float(values[name])
                n += 1
    return n


def materials_for(mesh_pkg, opts, stage_name, out_legacy, work_acr, log=print):
    """Material per slot of a far-forest tree: lightened impostor copies, the rest stock; None for other meshes."""
    if mesh_pkg not in MESHES:
        return None
    key = (mesh_pkg, str(out_legacy))
    if key in _made:
        return _made[key]
    out_dir = f"/Game/Environments/{stage_name}/{OUT_DIR}"
    values = {"AO Min": opts["ao_min"], "AO Pow Pre": opts["ao_pow"]}
    with tempfile.TemporaryDirectory(prefix="wr_fartree_") as tmp:
        slots = st._slots(mesh_pkg, tmp, Path(work_acr) / "wr_snowtrees" / "slots.json")
        infos = {pkg: (lambda d: (d,) + st._info(d))(st._asset(pkg, tmp)) for pkg in dict.fromkeys(slots) if pkg}
        imp = {pkg for pkg in infos if pkg.endswith("Impostor")}
        imp |= {pkg for pkg in infos if infos[pkg][1] in imp}                 # the impostor's LOD-transition child
        ours = {pkg: f"{out_dir}/{pkg.rsplit('/', 1)[-1]}Light" for pkg in imp}
        for pkg, new in ours.items():
            d, parent, _ = infos[pkg]
            if pkg.endswith("Impostor"):                   # the transition child inherits them from its parent copy
                _set_scalars(d, values)
            st._clone(d, pkg, new, {parent: ours[parent]} if parent in ours else {}, out_legacy, tmp)
    mats = [ours.get(p, p) for p in slots]
    log(f"    far trees: {mesh_pkg.rsplit('/', 1)[-1]} with {len(ours)} lighter impostor materials (AO min {opts['ao_min']}, pow {opts['ao_pow']})")
    _made[key] = mats
    return mats


def main():
    assert options({}) == DEFAULTS and options({"far_tree_light": False}) is None
    assert options({"far_tree_light": {"ao_min": 0.3}})["ao_pow"] == 1.3
    d = {"Exports": [{"Data": [{"Name": "ScalarParameterValues", "Value": [{"Value": [
        {"Name": "ParameterInfo", "Value": [{"Name": "Name", "Value": "AO Min"}]},
        {"Name": "ParameterValue", "Value": 0.05}]}]}]}]}
    assert _set_scalars(d, {"AO Min": 0.4}) == 1
    assert d["Exports"][0]["Data"][0]["Value"][0]["Value"][1]["Value"] == 0.4
    print("wr_fartrees self-check ok")


if __name__ == "__main__":
    main()
