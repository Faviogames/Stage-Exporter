"""Our pack: the stages kept installed, exported one at a time.

custom/pack.json {"stages": [slug, ...]} lists the stages of the installed pack, in pack order (a new stage goes last).
  export(slugs)  adds the stages to the pack if they are not in it, exports them again (WRCG export + ACR build) and
                 takes every other stage of the pack as it was last built; then packs and installs.
  remove(slugs)  drops stages from the pack and packs the rest (none is built again), then installs.
The pipeline always builds a pack of all the pack's stages (ACR's tables list them all); for a stage that is not being
exported again (WR_REBUILD in the environment lists the ones that are):
  - pipeline.export_wrcg is skipped: its WRCG export (work/wrcg/<slug>) stays,
  - buildcache.stage_key gives the key of its last build (work/wr_pack_keys.json), so build_stage restores that build
    from the build cache (work/acr/cache/stage/<key>: the stage's files and its table data) instead of building it,
  - buildcache.prune never drops those entries.
A stage whose last build is not in the cache any more is built again from its WRCG export.
Owner 2026-11-09: exporting one stage rebuilt all of them (40 min for five).
"""
import json
import os
import shutil
import time
from pathlib import Path

from wr import CUSTOM, ROOT

PACK = CUSTOM / "pack.json"
KEYS = ROOT / "work" / "wr_pack_keys.json"
CACHE = ROOT / "work" / "acr" / "cache"
KEEP = ROOT / "work" / "wr_keep"          # outside the cache: its pruning walks the whole cache folder
ENV = "WR_REBUILD"
KEEP_WRCG_ENV = "WR_KEEP_WRCG"
RUN_ENV = "WR_RUN_ID"


def stages():
    try:
        return list(json.loads(PACK.read_text(encoding="utf-8")).get("stages") or [])
    except (OSError, ValueError):
        return []


def save(slugs):
    PACK.write_text(json.dumps({"_comment": "Stages of the installed pack, in pack order (wr_pack.py).",
                                "stages": list(dict.fromkeys(slugs))}, indent=1), encoding="utf-8")


def keys():
    try:
        return json.loads(KEYS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save_keys(k):
    KEYS.parent.mkdir(parents=True, exist_ok=True)
    KEYS.write_text(json.dumps(k, indent=1), encoding="utf-8")


def rebuild_set():
    """None: no pack run (every stage built as the tool does); else the slugs to export again ('*': all)."""
    v = os.environ.get(ENV)
    return None if v is None else {s for s in v.split(",") if s}


def _again(slug):
    r = rebuild_set()
    return r is None or "*" in r or slug in r


def _entry(key):
    return CACHE / key if "/" in key else CACHE / "stage" / key


def built(slug):
    """The cache entry of the stage's last build, if it is still there."""
    k = keys().get(slug)
    return k and _entry(k["key"]).is_dir() and (_entry(k["key"]) / "manifest.json").exists()


def cache_bytes(slug):
    k = keys().get(slug)
    return sum(p.stat().st_size for p in _entry(k["key"]).rglob("*") if p.is_file()) if k and built(slug) else 0


def free_cache(slugs, log=print):
    """Deletes the cache entry of each stage (it is no longer built, so it leaves the pack); names and images stay."""
    ks = keys()
    for s in slugs:
        k = ks.pop(s, None)
        if k:
            shutil.rmtree(_entry(k["key"]), ignore_errors=True)
            log(f"{s}: cache deleted")
    _save_keys(ks)
    save([s for s in stages() if s not in slugs])


def last_built(slug):
    k = keys().get(slug)
    return k.get("time") if k else None


# --- pipeline side (the launcher's process) --------------------------------------------------------------------------

def patch_pipeline(pl):
    if getattr(pl.export_wrcg, "_wr", False):
        return
    orig = pl.export_wrcg

    def export_wrcg(slug, cfg, env, log, *a, **k):
        keep = not _again(slug) or os.environ.get(KEEP_WRCG_ENV)        # --keep-wrcg: ACR build only
        if keep and ((ROOT / "work" / "wrcg" / slug / "index.json").exists() or built(slug)):   # built: an imported .stage
            log(f"[{slug}] WRCG export kept (stage not exported again)")
            return None
        return orig(slug, cfg, env, log, *a, **k)

    export_wrcg._wr = True
    pl.export_wrcg = export_wrcg


def run(slugs_again, pack, log=print, install=True):
    """Build and install the pack `pack`, exporting `slugs_again` again and reusing the others."""
    import wr
    import tools.exporter.pipeline as pl
    wr._patch_run(pl)
    patch_pipeline(pl)
    os.environ[ENV] = ",".join(slugs_again) or ","
    os.environ[RUN_ENV] = str(time.time())
    try:
        t = time.time()
        out = pl.run(*wr._installs(), list(pack), install=install, log=log)
        log(f"pack: {', '.join(pack)} ({', '.join(slugs_again) or 'none'} exported again) in {(time.time() - t) / 60:.1f} min")
        return out
    finally:
        os.environ.pop(ENV, None)
        os.environ.pop(RUN_ENV, None)


def export(slugs, log=print, install=True):
    pack = stages()
    pack += [s for s in slugs if s not in pack]
    out = run(slugs, pack, log, install)
    if out:
        save(pack)
    return out


def uninstall_all(log=print):
    """Takes the whole pack out of ACR (the tool's own uninstall) and empties pack.json: removing the last stage
    (2026-11-11, Sando's test with Savallà alone: "Quitar del pack" stopped with 'the pack would be empty')."""
    import subprocess
    import sys
    import wr
    import tools.exporter.pipeline as pl
    w, a = wr._installs()
    env = dict(os.environ)
    env.update(pl._env(w, a, a / "acr" / "Content" / "Paks"))
    r = subprocess.run([sys.executable, "-m", "tools.acrmod.install", "uninstall", pl.INSTALL_NAME], env=env,
                       capture_output=True, text=True)
    for line in (r.stdout + r.stderr).splitlines():
        log(line)
    if r.returncode != 0:
        log("the pack could not be taken out of the game (is it running?)")
        return False
    save([])
    log("pack removed from the game: no stage of ours is installed now")
    return True


def remove(slugs, log=print, install=True):
    pack = [s for s in stages() if s not in slugs]
    if not pack:
        return uninstall_all(log)
    out = run([], pack, log, install)
    if out:
        save(pack)
    return out


# --- build side (build_stage's process) ------------------------------------------------------------------------------

def patch_cache():
    import tools.acrmod.buildcache as bc
    if getattr(bc.stage_key, "_wr", False):
        return
    orig_key, orig_prune = bc.stage_key, bc.prune

    def stage_key(slug, before, *a, **k):
        ks = keys()
        if rebuild_set() is not None and not _again(slug) and built(slug):
            print(f"    [{slug}] last build reused ({ks[slug].get('time', '?')})")
            return ks[slug]["key"]
        key = orig_key(slug, before, *a, **k)
        if rebuild_set() is not None and _again(slug):
            salt = os.environ.get(RUN_ENV, "")                      # one fresh build per run
            key = key.rsplit("/", 1)[0] + "/" + bc.digest(key, "wr", salt) if "/" in key else bc.digest(key, "wr", salt)
        ks[slug] = {"key": key, "time": time.strftime("%Y-%m-%d %H:%M")}
        _save_keys(ks)
        return key

    def prune(*a, **k):
        """The pack's entries are moved out of the cache while it is pruned."""
        moved = []
        for old_keep in (KEEP, CACHE / "wr_keep"):                 # left by an interrupted prune
            for p in old_keep.glob("*") if old_keep.exists() else []:
                if not (CACHE / "stage" / p.name).exists():
                    shutil.move(str(p), str(CACHE / "stage" / p.name))
        KEEP.mkdir(parents=True, exist_ok=True)
        try:
            for v in keys().values():
                e = _entry(v["key"])
                if e.is_dir():
                    shutil.move(str(e), str(KEEP / e.name))
                    moved.append((KEEP / e.name, e))
            return orig_prune(*a, **k)
        finally:
            for src, dst in moved:
                if src.exists() and not dst.exists():
                    shutil.move(str(src), str(dst))

    stage_key._wr = prune._wr = True
    bc.stage_key = stage_key
    bc.prune = prune
