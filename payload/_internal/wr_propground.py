"""Tyre stacks that hang in the air (owner 2026-11-20, Ngema m 3076: a TIRESSTACK_GROUP_SIGN_02 floated).

WRCG puts each prop at the height of its own terrain; ACR's ground under it is up to 0.9 m lower (Ngema: 0.31 m under the one
the owner saw, 0.9 m under others), and the group is 4.8 m long, so on a slope the far end hangs too. The models start at z = 0
(measured), so the fix is only the height: each tyre stack (TYRE_RE) is moved to the lowest ACR ground under its length (3
samples), when that differs by more than TOL_M and less than MAX_M. Universal; stage key "tyre_ground": false = off.
Idempotent (it compares with the ground each time). Only the drawn prop moves: the collision of the stack is built separately.
Not driven in game.
"""
import re

import numpy as np

SPAN_M = 4.8              # length of the TIRESSTACK_GROUP_SIGN_* models (local +x; the NEUTRAL ones +y)
TOL_M = 0.03
MAX_M = 1.5
_ctx = {}


def _ground(slug):
    if slug not in _ctx:
        import tools.acrmod.build_stage as bs
        import tools.acrmod.ittiri_ground as ig
        import wr_fixes
        cfg = wr_fixes._cfg(slug)
        shift = bs.stage_shift(cfg, bs.route_wrcg(cfg))
        _ctx[slug] = (shift, ig.make_ground_fn(shift))
    return _ctx[slug]


def settle(insts, slug, tyre_re, log=print):
    """insts with the tyre stacks' world matrices set to the ACR ground; returns the same list."""
    import tools.acrmod.props_visual as pv
    todo = [p for p in insts if re.search(tyre_re, p.psi_name or "", re.I)]
    if not todo:
        return insts
    shift, ground = _ground(slug)
    moved, worst = 0, 0.0
    for p in todo:
        w = np.asarray(p.world, float)
        axis = w[:3, 1] if "NEUTRAL" in (p.psi_name or "").upper() else w[:3, 0]
        pts = np.array([w[:3, 3] + axis * t for t in (0.0, SPAN_M / 2, SPAN_M)])
        ue = pv.wrcg_world_to_ue(pts, shift)
        low = min(float(ground(x, y, z)) for x, y, z in ue)
        d = (low - float(ue[0][2])) / 100.0                    # UE cm -> m (WRCG metres)
        if TOL_M < abs(d) <= MAX_M:
            w[2, 3] += d
            p.world = w
            moved += 1
            worst = max(worst, abs(d))
    if moved:
        log(f"    tyre stacks: {moved} of {len(todo)} set on the ground (up to {worst:.2f} m)")
    return insts
