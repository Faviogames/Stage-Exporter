"""Animate selected WRCG water meshes and identify submerged road in the ACR build."""
import numpy as np

WATER_MAX_DEPTH_M = 1.0
WATER_MIN_DEPTH_M = 0.02


def water_pm(cfg):
    value = (cfg or {}).get("water_surface")
    return value.strip() or None if isinstance(value, str) else None


def under_water(centroids_xyz, cells_xy, level_z, cell_m=4.0, band=WATER_MAX_DEPTH_M):
    """Boolean mask of the triangle centroids (world metres) inside a water cell and below its visible water level."""
    out = np.zeros(len(centroids_xyz), bool)
    h = cell_m / 2.0
    depth = level_z - centroids_xyz[:, 2]
    near = (depth >= WATER_MIN_DEPTH_M) & (depth <= band)
    for q in cells_xy:
        out |= near & (np.abs(centroids_xyz[:, 0] - q[0]) <= h) & (np.abs(centroids_xyz[:, 1] - q[1]) <= h)
    return out


def split(meshes, offset, waters, pm, mesh_cls):
    """meshes (baked frame (x, z, -y) + offset) with the triangles under `waters` [(cells_xy, z)] moved to new meshes of
    physical material `pm`; returns (meshes, number of triangles moved)."""
    ox, oy, oz = (float(v) for v in offset)
    out, moved, n = [], 0, 0
    for m in meshes:
        P = np.asarray(m.positions, float).reshape(-1, 3)
        T = np.asarray(m.indices, np.int64).reshape(-1, 3)
        c = P[T].mean(1)
        world = np.c_[c[:, 0] - ox, -(c[:, 2] - oz), c[:, 1] - oy]
        wet = np.zeros(len(T), bool)
        for cells, z in waters:
            wet |= under_water(world, cells, z)
        if not wet.any() or m.physmat == pm:
            out.append(m)
            continue
        dry = mesh_cls(m.positions, T[~wet].ravel().tolist(), m.physmat, m.owner) if (~wet).any() else None
        n += 1
        if dry is not None:
            out.append(dry)
        out.append(mesh_cls(m.positions, T[wet].ravel().tolist(), pm, f"{m.owner}Puddle{n}"))
        moved += int(wet.sum())
    return out, moved

def use_animated_water(dst, oceans, log=print):
    """Use the stock ACR material with moving normals on selected WRCG water actors."""
    import json

    import wr_finish
    import wr_rvt

    prefixes = tuple(f"WrcgWater_{name}_" for name in oceans)
    components = []
    for i in range(1, len(dst.exports) + 1):
        if dst.class_name(i) == "StaticMeshActor" and dst.exp(i)["ObjectName"].startswith(prefixes):
            _, c, _ = wr_finish._mesh_of(dst, i)
            if c:
                components.append(c)
    if not components:
        return 0
    template = json.loads(wr_rvt.PROP_RVT.read_text(encoding="utf-8-sig"))
    idx = dst.ensure_import(wr_rvt._key("/Game/Environments/RallyShared/Materials/M_Water", "Material"))
    for c in components:
        component = dst.exp(c)
        wr_rvt._set(component, wr_rvt._obj_array("OverrideMaterials", idx, template))
        dst._add_export_names(component)
    log(f"water: ACR animated water material on {len(components)} meshes ({', '.join(oceans)})")
    return len(components)


def main():      # self-check on a synthetic road piece
    class M:
        def __init__(self, positions, indices, physmat, owner="o"):
            self.positions, self.indices, self.physmat, self.owner = positions, indices, physmat, owner
    # two triangles at world y 0 and y 20 (baked: x, z, -y); water cell at (0, 0), level 5
    pos = [0, 5, 0, 1, 5, 0, 0, 5, -1,   0, 5, -20, 1, 5, -20, 0, 5, -21]
    m = M(pos, [0, 1, 2, 3, 4, 5], "PM_SurfaceGravelFine")
    out, moved = split([m], (0, 0, 0), [([(0.3, -0.3)], 5.1)], "PM_SurfaceGrass", M)
    assert moved == 1 and sorted(x.physmat for x in out) == ["PM_SurfaceGrass", "PM_SurfaceGravelFine"], out
    assert [len(x.indices) for x in out] == [3, 3]
    assert water_pm({}) is None and water_pm({"water_surface": True}) is None
    assert water_pm({"water_surface": "PM_SurfaceGravelFine"}) == "PM_SurfaceGravelFine"
    assert under_water(np.array([[0, 5, 5.02], [0, 5, 4.95], [0, 5, 3.5]]), [(0, 5)], 5.0).tolist() == [False, True, False]
    print("wr_water self-check ok")


if __name__ == "__main__":
    main()
