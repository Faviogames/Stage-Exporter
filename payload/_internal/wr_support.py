"""ACR's own support vehicles beside the stage (owner 2026-11-14: "vehículos de asistencia" among what ACR offers).

BC_Ambulance_C, BC_SecurityCarA_C, BC_ServiceTruck_C, BC_VanA_C, BC_SuvA_C: Monte Carlo's actors, each a normal export
with its components, copied from the stock cells into our level the way the builder clones (UMap.clone). They stand
behind the biggest spectator clusters, away from the road (SETBACK_M beyond the cluster's centre, nose along the road),
so they do not touch the racing line.
Stage build "support_vehicles": {"ambulance": 1, "security": 1, "van": 1}: how many of each, the largest clusters first.
Not checked in game: the vehicles are physical actors (they can be pushed); lights stay as in the stock cell.
"""
import copy
import math
import shutil
import tempfile
from pathlib import Path

import numpy as np

import wr_finish as wf

LEVEL_DIR = "Levels/MonteCarloS1Bollene/_Generated_/"
KINDS = {                                          # kind -> (cell, actor class)
    "ambulance": ("2ZJSG0K5SVN1GSJDNGPQJUAMZ", "BC_Ambulance_C"),
    "security": ("2ZJSG0K5SVN1GSJDNGPQJUAMZ", "BC_SecurityCarA_C"),
    "truck": ("1NHBZUP73ATQTYQOJ9DL4PH54", "BC_ServiceTruck_C"),
    "van": ("1NHBZUP73ATQTYQOJ9DL4PH54", "BC_VanA_C"),
    "suv": ("1NHBZUP73ATQTYQOJ9DL4PH54", "BC_SuvA_C"),
}
SETBACK_M = 8.0
CLUSTER_M = 8.0
MIN_PEOPLE = 6


def _json(work_acr, cell):
    return Path(work_acr) / "wr_support" / f"{cell}.json"


def prepare(work_acr, paks, kinds):
    import tools.acrmod.common as c
    for cell in {KINDS[k][0] for k in kinds if k in KINDS}:
        out = _json(work_acr, cell)
        if out.exists():
            continue
        out.parent.mkdir(parents=True, exist_ok=True)
        tmp = Path(tempfile.mkdtemp(prefix="wr_support_"))
        try:
            c.retoc("to-legacy", paks, str(tmp), "-f", cell, "--version", "UE5_6", "--no-shaders")
            c.asset_json(tmp / "acr" / "Content" / (LEVEL_DIR + cell + ".umap"), out)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


def places(spots_ue, route_ue, want):
    """[(kind, xy cm, yaw deg)]: the largest clusters of spectators first, SETBACK_M away from the road."""
    S = np.asarray(spots_ue, float)[:, :2]
    R = np.asarray(route_ue, float)[:, :2]
    cells = {}
    for p in S:
        cells.setdefault((int(p[0] // (CLUSTER_M * 100)), int(p[1] // (CLUSTER_M * 100))), []).append(p)
    big = sorted((v for v in cells.values() if len(v) >= MIN_PEOPLE), key=len, reverse=True)
    queue = [k for k, n in want.items() for _ in range(int(n)) if k in KINDS]
    out, used = [], []
    for kind, pts in zip(queue, big):
        c = np.mean(pts, axis=0)
        i = int(np.hypot(R[:, 0] - c[0], R[:, 1] - c[1]).argmin())
        if any(np.hypot(*(c - u)) < 1500 for u in used):
            continue
        away = c - R[i]
        away /= max(float(np.hypot(*away)), 1.0)
        t = R[min(i + 3, len(R) - 1)] - R[max(i - 3, 0)]
        out.append((kind, c + away * SETBACK_M * 100, math.degrees(math.atan2(t[1], t[0]))))
        used.append(c)
    return out


def add(dst, work_acr, plan, ground, log=print):
    U = type(dst)
    cells = {}
    level = next(i for i in range(1, len(dst.exports) + 1) if dst.class_name(i) == "Level")
    n = 0
    for kind, xy, yaw in plan:
        cell_id, cls = KINDS[kind]
        if cell_id not in cells:
            import json
            cells[cell_id] = U(json.loads(_json(work_acr, cell_id).read_text(encoding="utf-8")))
        cell = cells[cell_id]
        src = next(i for i in range(1, len(cell.exports) + 1) if cell.class_name(i) == cls)
        cell_level = next(i for i in range(1, len(cell.exports) + 1) if cell.class_name(i) == "Level")
        mapping = dst.clone(cell, src, level, preset={cell_level: level})
        actor = mapping[src]
        uname = f"WrcgSupport_{n}_{cls}"                    # a copy of the same kind would share the stock name
        dst.exp(actor)["ObjectName"] = uname
        dst.add_name(uname)
        dst.register_actor(level, actor)
        root = next(p for p in dst.exp(actor)["Data"] if p.get("Name") == "RootComponent")["Value"]
        comp = dst.exp(root)
        loc = wf._vec(comp, "RelativeLocation")
        loc["X"], loc["Y"], loc["Z"] = float(xy[0]), float(xy[1]), float(ground(float(xy[0]), float(xy[1]), 0.0)) + 2.0
        rot = wf._vec(comp, "RelativeRotation")
        rot["Pitch"], rot["Yaw"], rot["Roll"] = 0.0, float(yaw), 0.0
        for d in mapping.values():
            dst._add_export_names(dst.exp(d))
        n += 1
    log(f"    support vehicles: {n} placed behind the spectator clusters ({', '.join(k for k, _, _ in plan)})")
    return n


def main():     # self-check on synthetic data
    spots = np.vstack([np.c_[5000 + np.arange(10) * 20.0, np.full(10, 900.0)], np.c_[9000 + np.arange(8) * 20.0, np.full(8, -800.0)]])
    route = np.c_[np.arange(0, 12000, 100.0), np.zeros(120)]
    p = places(spots, route, {"ambulance": 1, "van": 1})
    assert [k for k, _, _ in p] == ["ambulance", "van"], p
    assert p[0][1][1] > 900 + 700 and p[1][1][1] < -800 - 700 and abs(p[0][2]) < 1, p     # away from the road, along it
    print("wr_support self-check ok")


if __name__ == "__main__":
    main()
