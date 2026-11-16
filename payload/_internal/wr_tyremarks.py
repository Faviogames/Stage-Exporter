"""Tyre marks along the racing line, baked into the road of the terrain tiles, the way ACR's Munster has them.

Munster has almost no skid decals (3 procedural strips and ~48 tyre-mark patches at a few spots): its marks come from
the asphalt material (MI_MunsterAsphalt1, AsphaltTyreMarks_*), which lays T_TyreMarks_M (1024 x 4096, long streaks in
each of R, G, B) over a band TRAJ_WIDTH_M wide along the ideal line, repeating every TRAJ_LEN_M, stronger where the
road's vertex colour says. Our road is baked into the terrain tiles from WRCG's asphalt texture, so the marks are baked
the same way: the tool's racing line (racing_line.compute), T_TyreMarks_M from ACR (decoded once), and an intensity
along the line from its curvature (corners and the braking before them, a little on straights). Owner 2026-11-09: the
skid decals (many short strands) looked repeated and small; they are replaced by these (stage build "tyre_marks").

The bake runs in worker processes: build_stage's terrain_bake._bake_job is replaced by bake_job here (so the workers
import this module, which wraps terrain_bake.road_overlay in them), the data goes in an npz named by WR_TYRE_NPZ, and
the terrain-tile cache keys get its salt; which stage's data (work/acr/wr_tyre_current.json) is read per tile, since the
workers may serve several stages.
"""
import math
import os
from pathlib import Path

import numpy as np

TRAJ_WIDTH_M = 5.5          # ACR's trajectory band (acr_road_uv.TRAJ_WIDTH_M)
TRAJ_LEN_M = 101.2          # one T_TyreMarks_M repeat along it (acr_road_uv.TRAJ_LEN_M)
DARKEN = 0.85               # rubber: road colour times (1 - DARKEN * mark); 0.65 baked only ~8 % darker
STREAK_LO, STREAK_SPAN = 0.04, 0.3   # the mask's streaks (0-0.68, mean 0.15) stretched to 0-1: first bake too faint
BASE = 0.25                 # intensity on straights
CORNER_R_M = (35.0, 180.0)  # full intensity under the first radius, base over the second
BRAKE_M = 30.0              # marks start this far before a corner
STEP_M = 0.5
ENV_NPZ, ENV_SALT = "WR_TYRE_NPZ", "WR_TYRE_SALT"
MASK_PKG = "Materials/General/SharedTextures/T_TyreMarks_M"


# --- the data (parent) -----------------------------------------------------------------------------------------------

def _decode_bc1(buf, w, h):
    b = np.frombuffer(buf, np.uint8)[: w * h // 2].reshape(h // 4, w // 4, 8)
    c0 = b[..., 0].astype(np.uint16) | (b[..., 1].astype(np.uint16) << 8)
    c1 = b[..., 2].astype(np.uint16) | (b[..., 3].astype(np.uint16) << 8)

    def rgb(c):
        return np.stack([((c >> 11) & 31) * 255 / 31, ((c >> 5) & 63) * 255 / 63, (c & 31) * 255 / 31], -1)

    p0, p1 = rgb(c0), rgb(c1)
    four = (c0 > c1)[..., None]
    pal = np.stack([p0, p1, np.where(four, (2 * p0 + p1) / 3, (p0 + p1) / 2), np.where(four, (p0 + 2 * p1) / 3, 0)], 2)
    bits = b[..., 4:8].copy().view(np.uint32)[..., 0]
    idx = np.stack([(bits >> (2 * k)) & 3 for k in range(16)], -1)
    px = np.take_along_axis(pal, idx[..., None].repeat(3, -1).astype(np.int64), axis=2)
    return px.reshape(h // 4, w // 4, 4, 4, 3).transpose(0, 2, 1, 3, 4).reshape(h, w, 3).astype(np.uint8)


def mask(work_acr):
    """T_TyreMarks_M (4096 rows along, 1024 across, RGB), extracted from ACR once into work/acr/wr_tyre."""
    root = Path(work_acr) / "wr_tyre"
    npy = root / "T_TyreMarks_M.npy"
    if npy.exists():
        return np.load(npy)
    ubulk = root / "acr" / "Content" / (MASK_PKG + ".ubulk")
    if not ubulk.exists():
        import subprocess
        import tools.acrmod.common as c
        c.retoc("to-legacy", os.environ["WRCG2ACR_ACR_PAKS"], str(root), "-f", "T_TyreMarks_M", "--version", "UE5_6",
                "--no-shaders")
    img = _decode_bc1(ubulk.read_bytes(), 1024, 4096)
    np.save(npy, img)
    return img


def line_data(route, road_P, road_T):
    """Racing line resampled every STEP_M: xy, s, unit tangent, intensity."""
    import tools.acrmod.racing_line as rl
    line, _ = rl.compute(route, road_P, road_T)
    P = np.asarray(line, float)[:, :2]
    s = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(P, axis=0), axis=1))])
    g = np.arange(0.0, s[-1], STEP_M)
    xy = np.stack([np.interp(g, s, P[:, 0]), np.interp(g, s, P[:, 1])], 1)
    t = np.gradient(xy, axis=0)
    t /= np.maximum(np.linalg.norm(t, axis=1), 1e-9)[:, None]
    hd = np.unwrap(np.arctan2(t[:, 1], t[:, 0]))
    k = int(10 / STEP_M)
    hd_s = np.convolve(hd, np.ones(2 * k + 1) / (2 * k + 1), mode="same")
    radius = 1.0 / np.maximum(np.abs(np.gradient(hd_s) / STEP_M), 1e-6)
    w = np.clip((CORNER_R_M[1] - radius) / (CORNER_R_M[1] - CORNER_R_M[0]), 0.0, 1.0)
    b = int(BRAKE_M / STEP_M)                                 # braking: the corner's weight shifted back
    w = np.maximum(w, np.concatenate([w[b:], np.zeros(b)]) * 0.8)
    k = int(8 / STEP_M)
    w = np.convolve(w, np.ones(2 * k + 1) / (2 * k + 1), mode="same")
    inten = BASE + (1.0 - BASE) * np.clip(w, 0, 1)
    return {"xy": xy, "s": g, "t": t, "w": inten}


def prepare(out_npz, route, road_P, road_T, work_acr):
    d = line_data(route, road_P, road_T)
    np.savez(out_npz, mask=mask(work_acr), **d)
    return d


# --- the marks on a tile (workers) -----------------------------------------------------------------------------------

_DATA = {}


def marks(x0, y0, size_m, px, alpha=None):
    """Mark strength (px, px) for a tile (north-up: row 0 at y0 + size_m, column 0 at x0); 0 where none."""
    d = _data()
    out = np.zeros((px, px), np.float32)
    if d is None:
        return out
    xy, s, t, w, M = d["xy"], d["s"], d["t"], d["w"], d["mask"]
    half = TRAJ_WIDTH_M / 2.0
    cell = size_m / px
    near = np.where((xy[:, 0] > x0 - half - 1) & (xy[:, 0] < x0 + size_m + half + 1) &
                    (xy[:, 1] > y0 - half - 1) & (xy[:, 1] < y0 + size_m + half + 1))[0]
    if not len(near):
        return out
    best = np.full((px, px), np.inf, np.float32)
    for i in near:                                      # each line sample paints its slice of the band
        cx, cy = xy[i]
        tx, ty = t[i]
        r = half + 2 * STEP_M
        j0, j1 = int(math.floor((cx - r - x0) / cell)), int(math.ceil((cx + r - x0) / cell))
        i0, i1 = int(math.floor((y0 + size_m - (cy + r)) / cell)), int(math.ceil((y0 + size_m - (cy - r)) / cell))
        j0, j1, i0, i1 = max(j0, 0), min(j1, px), max(i0, 0), min(i1, px)
        if j1 <= j0 or i1 <= i0:
            continue
        jj, ii = np.meshgrid(np.arange(j0, j1), np.arange(i0, i1))
        X = x0 + (jj + 0.5) * cell - cx
        Y = y0 + size_m - (ii + 0.5) * cell - cy
        along = X * tx + Y * ty
        across = -X * ty + Y * tx
        inside = (np.abs(along) <= STEP_M * 1.5) & (np.abs(across) <= half)   # slices overlap: no gaps outside a bend
        if alpha is not None:
            inside &= alpha[i0:i1, j0:j1] > 0.01
        if not inside.any():
            continue
        u = np.clip(((across[inside] / TRAJ_WIDTH_M) + 0.5) * (M.shape[1] - 1), 0, M.shape[1] - 1).astype(int)
        v = (((s[i] + along[inside]) / TRAJ_LEN_M) % 1.0 * (M.shape[0] - 1)).astype(int)
        streak = np.clip((1.0 - M[v, u, 0] / 255.0 - STREAK_LO) / STREAK_SPAN, 0, 1)   # R's dark streaks = rubber
        edge = np.cos(np.clip(np.abs(across[inside]) / half, 0, 1) * math.pi / 2) ** 0.5
        val = (streak * edge * w[i]).astype(np.float32)
        sub_o = out[i0:i1, j0:j1]
        sub_b = best[i0:i1, j0:j1]
        dist = np.abs(along[inside]).astype(np.float32)
        closer = dist < sub_b[inside]
        o = sub_o[inside]
        bb = sub_b[inside]
        o[closer], bb[closer] = val[closer], dist[closer]
        sub_o[inside], sub_b[inside] = o, bb
    return out


def apply(rgb, alpha, x0, y0, size_m, px):
    m = marks(x0, y0, size_m, px, alpha)
    if not m.any():
        return rgb
    f = (1.0 - DARKEN * np.clip(m, 0, 1))
    return (rgb * f[..., None]).astype(rgb.dtype) if rgb.dtype != np.uint8 else \
        np.clip(rgb.astype(np.float32) * f[..., None] + 0.5, 0, 255).astype(np.uint8)


# --- wiring (build_stage's process and its bake workers) --------------------------------------------------------------

def _root():
    return Path(__file__).resolve().parent.parent


CURRENT = "wr_tyre_current.json"        # work/acr/<this>: the stage being baked (the workers outlive one stage)


def _current_file():
    return _root() / "work" / "acr" / CURRENT


def _set_current(npz, salt):
    import json
    _current_file().write_text(json.dumps({"npz": str(npz) if npz else None, "salt": salt or ""}))


def _current():
    import json
    try:
        return json.loads(_current_file().read_text())
    except (OSError, ValueError):
        return {"npz": None, "salt": ""}


def _data():
    cur = _current()
    p = cur.get("npz")
    if "path" not in _DATA or _DATA["path"] != p:
        _DATA["path"] = p
        _DATA["d"] = dict(np.load(p)) if p and Path(p).exists() else None
    return _DATA.get("d")


_ORIG = {}


def _patch_worker():
    """In any process: road_overlay draws the marks; the terrain-tile cache keys carry the current salt."""
    import tools.acrmod.buildcache as bc
    import tools.acrmod.terrain_bake as tb
    if not getattr(tb.road_overlay, "_wr", False):
        orig_ro = tb.road_overlay

        def road_overlay(x0, y0, size_m, px, ov, mips, *a, **k):
            res = orig_ro(x0, y0, size_m, px, ov, mips, *a, **k)        # (rgb, alpha) or (rgb, alpha, more)
            if _data() is not None and isinstance(res, tuple) and len(res) >= 2:
                res = (apply(res[0], res[1], x0, y0, size_m, px),) + tuple(res[1:])
            return res

        road_overlay._wr = True
        tb.road_overlay = road_overlay
    if not getattr(bc.key, "_wr", False):
        orig_key = bc.key

        def key(kind, *parts, **k):
            salt = _current().get("salt") if str(kind).startswith("terrain") else ""
            if kind == "terrain-tile":
                parts += ("wr_internal_road_borders_v1",)
            if salt:
                parts += ("wr_tyre", salt)
            return orig_key(kind, *parts, **k)

        key._wr = True
        bc.key = key


def bake_job(job):
    """terrain_bake._bake_job in the bake workers (pickled by name, so they import this module)."""
    import tools.acrmod.terrain_bake as tb
    _patch_worker()
    orig = _ORIG.get("bake_job") or tb._bake_job
    if orig is bake_job:
        raise RuntimeError("wr_tyremarks: original _bake_job lost")
    return orig(job)


BAKE_WORKER_GB = 2.8        # largest bake process seen (2026-11-14, 32 GB PC): 2.8 GB; WR_BAKE_WORKERS sets the count
BAKE_WORKER_MAX = 8         # 8 x 2.8 GB + the build process still fits in 32 GB; more would page


def bake_workers():
    """Bake worker count from the CPU and the memory free now. 2026-11-14: with 24 workers the commit limit (RAM +
    page file) ran out and a worker failed to allocate 96 MiB while 18 GB of RAM were free, so the count follows the
    smaller of free RAM and free commit."""
    env = os.environ.get("WR_BAKE_WORKERS", "")
    if env.isdigit() and int(env) > 0:
        return int(env)
    try:
        import ctypes

        class MemStatus(ctypes.Structure):
            _fields_ = [("length", ctypes.c_ulong), ("load", ctypes.c_ulong)] + \
                       [(n, ctypes.c_ulonglong) for n in ("tot_phys", "avail_phys", "tot_commit", "avail_commit",
                                                          "tot_virt", "avail_virt", "avail_ext")]
        m = MemStatus()
        m.length = ctypes.sizeof(m)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
        free_gb = min(m.avail_phys, m.avail_commit) / 2 ** 30
        by_memory = int(free_gb * 0.8 / BAKE_WORKER_GB)
    except Exception:
        by_memory = 4                       # shortcut: memory not readable, a safe middle; fix if it ever shows
    return max(2, min(BAKE_WORKER_MAX, (os.cpu_count() or 4) // 2, by_memory))


def patch_build(stage_info, log=print):
    """build_stage's process: before a stage's terrain is baked, the mark data for it (or none)."""
    import hashlib
    import tools.acrmod.terrain_bake as tb
    if getattr(tb.add_baked_terrain, "_wr", False):
        return
    _ORIG["bake_job"] = tb._bake_job
    tb._bake_job = bake_job
    _patch_worker()
    orig = tb.add_baked_terrain

    def add_baked_terrain(*a, **k):
        si = stage_info()
        cfg = si[0] if si else {}
        if cfg.get("tyre_marks"):
            import tools.acrmod.build_stage as bs
            S = _root() / "work" / "wrcg" / cfg["slug"]
            road = np.load(S / "collision_all_prm.npz")
            npz = S / "tyre_marks.npz"
            d = prepare(npz, bs.route_wrcg(cfg), road["positions"], road["triangles"], _root() / "work" / "acr")
            salt = hashlib.md5(npz.read_bytes()).hexdigest() + f"/{DARKEN}/{BASE}"
            _set_current(npz, salt)
            log(f"    tyre marks: along the racing line ({d['s'][-1]:.0f} m), T_TyreMarks_M over {TRAJ_WIDTH_M} m, "
                f"intensity {BASE:.2f} on straights to 1 in corners, baked into the road")
        else:
            _set_current(None, "")
        _DATA.clear()
        if k.get("workers") is None:
            k["workers"] = bake_workers()
            log(f"    terrain bake: {k['workers']} worker processes")
        try:
            return orig(*a, **k)
        finally:
            _set_current(None, "")

    add_baked_terrain._wr = True
    tb.add_baked_terrain = add_baked_terrain
