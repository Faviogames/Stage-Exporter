"""ACR build 26756580 (2026-11-19) recompiled its shaders: the material instances the core cloned from ACR's own (MI_ResidentialWallA1,
MI_MonBolStoneWallB, MI_SaverneMeshDecals0203Drainage1) carry the serialized shader map of the OLD build, its hashes are no longer in the game's
shader library and every WRCG material fell back to the grey default (WorldGrid). Fix: replace the tail of each such .uexp (the shader map, from
byte CUT of the twin on) with the one of the twin in the new game. Idempotent: after the patch the tail hash is the twin's.
Usage: python wr_mishaders.py <dir-with-twins-extracted> <stage cache dir or legacy dir> ...  (see patch_dir)"""
import json
import os
import sys
from pathlib import Path

# first 8 bytes of the 20-byte hash before the package tag at the end of the .uexp -> twin material name
OLD = {"05e0091af50a8727": "MI_MonBolStoneWallB", "6f59f9908a005ff2": "MI_ResidentialWallA1", "47246928109fb407": "MI_SaverneMeshDecals0203Drainage1",
       "0fb9f2edbee3f12d": "MI_SmallFencesABarbedWire"}


# offsets measured on the 2026-11-19 clones (first byte after the properties); used when no clone of the twin's exact length is at hand
CUTS = {"05e0091af50a8727": 703, "6f59f9908a005ff2": 399, "47246928109fb407": 461, "0fb9f2edbee3f12d": 495}


def _find(root, name):
    for p in Path(root).rglob(name + ".uexp"):
        return p.read_bytes()
    raise FileNotFoundError(name)


def _cut(twin, sample):
    """Offset where the shader map starts: just after the last difference in the property area (first 1000 bytes) between a same-length
    clone and its twin."""
    last = 0
    for i in range(min(1000, len(twin))):
        if twin[i] != sample[i]:
            last = i + 1
    return last + 8


def _is_mi(uasset):
    return b"Default__MaterialInstanceConstant" in uasset.read_bytes()


def _files(d):
    """(uasset path, uexp path) of every asset in a stage cache dir (manifest.json) or a legacy tree."""
    d = Path(d)
    man = d / "manifest.json"
    if man.exists():
        m = json.loads(man.read_text(encoding="utf-8"))["files"]
        for k, f in m.items():
            if k.endswith(".uasset") and k[:-7] + ".uexp" in m:
                yield d / f, d / m[k[:-7] + ".uexp"]
    else:
        for a in d.rglob("*.uasset"):
            yield a, a.with_suffix(".uexp")


def patch_dir(twins_root, d, log=print, strict=False):
    twins = {n: _find(twins_root, n) for n in OLD.values()}
    todo = []
    for ua, ux in _files(d):
        if ux.exists() and _is_mi(ua):
            b = ux.read_bytes()
            if b[-24:-4][:8].hex() in OLD:
                todo.append((ux, b))
    cuts = dict(CUTS)
    for ux, b in todo:                                     # the cut comes from a clone with the twin's exact length
        sig = b[-24:-4][:8].hex()
        if sig not in cuts and len(b) == len(twins[OLD[sig]]):
            cuts[sig] = _cut(twins[OLD[sig]], b)
    n_done = left = 0
    for ux, b in todo:
        sig = b[-24:-4][:8].hex()
        if sig not in cuts:
            left += 1
            continue
        t = twins[OLD[sig]]
        L = len(t) - cuts[sig]
        if len(b) - L < 200:
            left += 1
            continue
        ux.write_bytes(b[:len(b) - L] + t[-L:])
        n_done += 1
    log(f"material shader maps refreshed: {n_done} in {d} ({left} left)")
    if strict and left:
        raise RuntimeError(f"Cannot refresh {left} old material shader maps in {d}; packing cancelled")
    return n_done


if __name__ == "__main__":
    for dd in sys.argv[2:]:
        patch_dir(sys.argv[1], dd)
