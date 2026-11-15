"""WRCG's animals as props (owner 2026-11-14: Kenya's flamingos and giraffes; cows he saw at the start are WRCG's BUFFALO).

The level's animals are nodes under <tag>/<..>_<tag>_GRAPH/ANIMALS: BUFFALO01_n, FLAMINGO_n, GIRAFE_n, ... The base
collector leaves them out ('/CHARACTERS/' is in prop_instances.EXCLUDE_PSI_PATTERNS) and flamingos and giraffes are not
mesh nodes at all (their model comes through a public graphic bank), so the instances are made here from the nodes by name:
  FLAMINGO_<n> -> FLAMINGO_01 / FLAMINGO_02 PSI (the bank's two meshes, by parity), GIRAFE_<n> -> GIRAFE,
  BUFFALO01_<n> -> BUFFALO03.
Stage build "animals": {"tag": "SS2", "types": ["FLAMINGO", "GIRAFE"], "near_m": 150, "max": 80}. The flamingos are static
meshes; giraffes and buffalo are skinned and stand in their bind pose, frozen (shortcut: no animation, no collision).
"""
import copy
import re

import numpy as np

from wr import ROOT

DIR = "DATA:/GRAPH/CHARACTERS/ANIMALS/"
MESH = {"FLAMINGO": lambda n: f"FLAMINGO_0{1 + n % 2}", "GIRAFE": lambda n: "GIRAFE", "BUFFALO01": lambda n: "BUFFALO03"}
NAME = re.compile(r"(?i)^(FLAMINGO|GIRAFE|BUFFALO01)_(\d+)$")


def instances(level, template, route_xy, gp):
    import tools.wrcg.plm as plm
    import tools.wrcg.plm_props as pp
    nodes = plm.Plm(ROOT / "work" / "wrcg_fs" / "WIN32" / "LEVELS" / level / f"{level}.PLM").nodes()
    tag = gp["tag"]
    want = {t.upper() for t in gp.get("types") or ["FLAMINGO", "GIRAFE"]}
    want |= {"BUFFALO01"} if "BUFFALO" in want else set()
    near = float(gp.get("near_m", 150.0))
    graphs = re.compile(rf"^{re.escape(tag)}/\w*_{re.escape(tag)}_GRAPHS?$", re.I)
    R = np.asarray(route_xy, float)[:, :2]
    stack, parent, out = [], {}, []
    for n in nodes:
        while stack and stack[-1].depth >= n.depth:
            stack.pop()
        parent[n.index] = stack[-1] if stack else None
        stack.append(n)
    for n in nodes:
        m = NAME.match(n.name)
        if not m or m.group(1).upper() not in want:
            continue
        chain, q = [], n
        while q is not None:
            chain.append(q)
            q = parent[q.index]
        if not any(x.name.upper() == "ANIMALS" for x in chain) or not any(graphs.match(x.name) for x in chain):
            continue
        w = np.eye(4)
        for q in chain:
            w = np.asarray(pp.node_matrix(q.pos, q.rot, q.scale)) @ w
        if np.hypot(R[:, 0] - w[0, 3], R[:, 1] - w[1, 3]).min() > near:
            continue
        kind, k = m.group(1).upper(), int(m.group(2))
        name = MESH[kind](k)
        p = copy.copy(template)
        for a, v in (("category", "static"), ("name", n.name), ("node_id", str(n.node_id)), ("parent_name", chain[1].name),
                     ("path", "/".join(x.name for x in reversed(chain))), ("psi", f"{DIR}{name}.PSI"),
                     ("psi_name", name), ("spawner_id", None), ("world", w)):
            setattr(p, a, v)
        out.append(p)
    return out[: int(gp.get("max", 80))]


def main():     # self-check of the name mapping
    assert NAME.match("FLAMINGO_118") and NAME.match("GIRAFE_3") and NAME.match("BUFFALO01_52") and not NAME.match("ZEBRA_1")
    assert MESH["FLAMINGO"](7) == "FLAMINGO_02" and MESH["FLAMINGO"](8) == "FLAMINGO_01"
    print("wr_animals self-check ok")


if __name__ == "__main__":
    main()
