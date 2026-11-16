"""Lighter ground cover (owner 2026-11-16, Ngema: grass and stones dark in some sectors, "como con los arboles").

ACR's grass (the *_RVT_Munster / Greece RVT material instances of wr_groundcover.SPECIES) is a child of a stock grass
instance (MI_Grass...) that darkens the blades' base with baked ambient occlusion: AO Min 0.6, AO Max 0.8-0.9 and
"AO Color Intensity" up to 5. Like the far trees (wr_fartrees.py), each such pair gets copies written into the stage's
content (Environments/<name>/WrGrass): the parent with AO Min / AO Max raised and AO Color Intensity scaled, the RVT
child pointing at that copy. Stage build "grass_light": OFF by default (the first try, 2026-11-16, was not liked); true or
{"ao_min": 0.85, "ao_max": 1.0, "ao_color": 0.5}. A parameter the parent does not have is left as it is.
Not checked in game: the values, and that the occlusion (not the sun or the shadows) is what makes the grass dark.
"""
import copy
import tempfile

import wr_snowtrees as st

DEFAULTS = {"ao_min": 0.85, "ao_max": 1.0, "ao_color": 0.5}      # ao_color: factor on "AO Color Intensity"
OUT_DIR = "WrGrass"
_made = {}


def options(cfg):
    o = (cfg or {}).get("grass_light", False)          # OFF by default: owner 2026-11-16, "un fracaso"
    return dict(DEFAULTS, **o) if isinstance(o, dict) else (dict(DEFAULTS) if o else None)


def _set(d, o):
    """Writes the options into the ScalarParameterValues that exist; returns how many were changed."""
    n = 0
    for p in d["Exports"][0]["Data"]:
        if p["Name"] != "ScalarParameterValues":
            continue
        seen = set()
        for s in p["Value"]:
            f = {x["Name"]: x for x in s["Value"]}
            name = next(x["Value"] for x in f["ParameterInfo"]["Value"] if x["Name"] == "Name")
            v = f["ParameterValue"]
            if name == "AO Min":
                v["Value"] = max(float(v["Value"]), o["ao_min"])
            elif name == "AO Max":
                v["Value"] = max(float(v["Value"]), o["ao_max"])
            elif name == "AO Color Intensity":
                v["Value"] = float(v["Value"]) * o["ao_color"]
            else:
                continue
            n += 1
            seen.add(name)
        for want, val in (("AO Min", o["ao_min"]), ("AO Max", o["ao_max"])):      # the parent did not set it: write it (the shared MI_Grass' own is darker)
            if want not in seen and p["Value"]:
                new = copy.deepcopy(p["Value"][0])
                f = {x["Name"]: x for x in new["Value"]}
                next(x for x in f["ParameterInfo"]["Value"] if x["Name"] == "Name")["Value"] = want
                f["ParameterValue"]["Value"] = float(val)
                p["Value"].append(new)
                for nm in (want,):
                    if nm not in d["NameMap"]:
                        d["NameMap"].append(nm)
                n += 1
    return n


def materials_for(mats, o, stage_name, out_legacy, log=print):
    """The RVT grass materials `mats` with lighter copies; the list unchanged for one that cannot be copied."""
    out = []
    with tempfile.TemporaryDirectory(prefix="wr_grass_") as tmp:
        for m in mats:
            key = (m, str(out_legacy))
            if key not in _made:
                try:
                    d = st._asset(m, tmp)
                    parent, _ = st._info(d)
                    new_child = f"/Game/Environments/{stage_name}/{OUT_DIR}/{m.rsplit('/', 1)[-1]}Light"
                    if parent and parent.startswith("/Game/Foliage"):
                        pd = st._asset(parent, tmp)
                        new_parent = f"/Game/Environments/{stage_name}/{OUT_DIR}/{parent.rsplit('/', 1)[-1]}Light"
                        if _set(pd, o):
                            for nm in (new_parent, new_parent.rsplit("/", 1)[-1]):     # the stock name may differ in case: make sure ours is known
                                if nm not in pd["NameMap"]:
                                    pd["NameMap"].append(nm)
                            st._clone(pd, parent, new_parent, {}, out_legacy, tmp)
                            for nm in (new_child, new_child.rsplit("/", 1)[-1]):
                                if nm not in d["NameMap"]:
                                    d["NameMap"].append(nm)
                            st._clone(d, m, new_child, {parent: new_parent}, out_legacy, tmp)
                            _made[key] = new_child
                except Exception as e:                 # one grass that cannot be copied keeps its stock material
                    log(f"    grass light: {m.rsplit('/', 1)[-1]} kept ({type(e).__name__}: {e})")
                _made.setdefault(key, m)
            out.append(_made[key])
    return out


def main():     # self-check on a synthetic material
    d = {"Exports": [{"Data": [{"Name": "ScalarParameterValues", "Value": [
        {"Value": [{"Name": "ParameterInfo", "Value": [{"Name": "Name", "Value": n}]}, {"Name": "ParameterValue", "Value": v}]}
        for n, v in (("AO Min", 0.6), ("AO Max", 0.9), ("AO Color Intensity", 5.0), ("Roughness", 0.8))]}]}]}
    assert _set(d, DEFAULTS) == 3
    vals = {next(x["Value"] for x in s["Value"][0]["Value"]): s["Value"][1]["Value"] for s in d["Exports"][0]["Data"][0]["Value"]}
    assert vals == {"AO Min": 0.85, "AO Max": 1.0, "AO Color Intensity": 2.5, "Roughness": 0.8}, vals
    assert options({}) is None and options({"grass_light": True}) == DEFAULTS
    print("wr_grasslight self-check ok")


if __name__ == "__main__":
    main()
