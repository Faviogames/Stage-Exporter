"""Local launcher: runs the exporter with our own data and fixes on top of the packaged tool (nothing in it is changed).

  wrcg2acr-worker.exe -m wr ui                        Stage Exporter, our window (wr_ui.py; "WRC to ACR Stage Exporter.exe" opens it)
  wrcg2acr-worker.exe -m wr build-exe                 build WRC to ACR Stage Exporter.exe and its icon
  wrcg2acr-worker.exe -m wr export <slug> [...]       export these stages again (added to the pack if new), keep the rest
  wrcg2acr-worker.exe -m wr remove <slug> [...]       drop stages from the pack (nothing is built again)
  wrcg2acr-worker.exe -m wr pack                      the pack's stages and their last build (wr_pack.py)
  wrcg2acr-worker.exe -m wr app                       the tool's window with our stages and fixes
  wrcg2acr-worker.exe -m wr list [text]               WRCG rally stages (id, name, rally, length, surface)
  wrcg2acr-worker.exe -m wr add <stage id> [--force]  a WRCG stage as a stage build of ours (wr_stages.py)
  wrcg2acr-worker.exe -m wr run <slug> [<slug> ...] [--install] [--wrcg-only]   a pack of exactly these, all built
  wrcg2acr-worker.exe -m wr info
  wrcg2acr-worker.exe -m wr <any worker args>   (used for the child steps)

custom/data/<name>.json replaces the tool's data file <name>.json; custom/data/<name>.merge.json is merged into it
(dicts key by key, everything else replaced). The fixes live in wr_fixes.py.
"""
import importlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(sys.executable).resolve().parent.parent
CUSTOM = ROOT / "custom"
OVERLAY = CUSTOM / "data"

import tools._embedded as _em
import tools.datafiles as _df


def _merge(base, extra):
    if isinstance(base, dict) and isinstance(extra, dict):
        out = dict(base)
        for k, v in extra.items():
            out[k] = _merge(base[k], v) if k in base else v
        return out
    return extra


def load_overlay(names=None):
    """custom/data into the tool's data (all files, or the given relative names, e.g. after a stage was added)."""
    for _p in sorted(OVERLAY.rglob("*.json")):
        _rel = _p.relative_to(OVERLAY).as_posix()
        if names is not None and _rel not in names:
            continue
        if _rel.endswith(".merge.json"):
            _rel = _rel[:-len(".merge.json")] + ".json"
            _data = json.dumps(_merge(_df.load_json(_rel), json.loads(_p.read_text(encoding="utf-8"))), ensure_ascii=False)
            _em.DATA[_rel] = _df.scramble(_data.encode("utf-8"))
        else:
            _em.DATA[_rel] = _df.scramble(_p.read_bytes())


load_overlay()

def _add_ground_cover_species():
    import wr_groundcover
    vm = _df.load_json("wrcg_vegetation_map.json")
    vm["acr_species"].update(wr_groundcover.species_defs())
    for _k, _meshes in wr_groundcover.TREE_MESHES.items():
        if _meshes and _k in vm["acr_species"]:
            vm["acr_species"][_k]["meshes"] = list(_meshes)
    _em.DATA["wrcg_vegetation_map.json"] = _df.scramble(json.dumps(vm, ensure_ascii=False).encode("utf-8"))


_add_ground_cover_species()

# WRCG's PAVE / WETPAVE (cobbles, setts) went to ACR's PM_SurfaceCobblestones, whose KunosPhysicalProperties set
# SurfaceType ST_SNOW: on Riudecanyes the tight downhill corners after the castle (four PAVE stretches, s 2717-3288 m,
# radius 10-19 m, up to -18 %) slid like snow (owner drive 2026-11-09). ACR has one tarmac surface: PM_SurfaceTarmacSmooth.
PAVE_PHYSMAT = "PM_SurfaceTarmacSmooth"


def _fix_surface_map():
    sm = _df.load_json("wrcg_surface_map.json")
    for row in sm["map"]:
        if row.get("surface") in ("PAVE", "WETPAVE"):
            row.update(acr_physmat=PAVE_PHYSMAT, confidence="our version",
                       reason="PM_SurfaceCobblestones is SurfaceType ST_SNOW in ACR (drives like snow); tarmac instead.")
    _em.DATA["wrcg_surface_map.json"] = _df.scramble(json.dumps(sm, ensure_ascii=False).encode("utf-8"))


_fix_surface_map()

_popen_init = subprocess.Popen.__init__
SERIAL_ENV = "WR_SERIAL"


def _init(self, args, *a, **k):
    # every child step of the pipeline goes through this launcher too, so it sees the same data and fixes
    if isinstance(args, (list, tuple)) and args and Path(str(args[0])).name.lower() == "wrcg2acr-worker.exe" \
            and list(args[1:3]) != ["-m", "wr"]:
        args = [args[0], "-m", "wr", *args[1:]]
    # --serial (export): the builder's own option, one stage at a time. 2026-11-11: three stages built in parallel
    # failed twice on shared files (work/acr/tex/rt/T_WrcgRoadSimpleB.json, work/acr/rt/foliage/mesh_bounds.json:
    # "Permission denied" while another build wrote them)
    if os.environ.get(SERIAL_ENV) and isinstance(args, (list, tuple)) and "tools.acrmod.build_stage" in map(str, args) \
            and "--serial" not in map(str, args):
        args = [*args, "--serial"]
    return _popen_init(self, args, *a, **k)


subprocess.Popen.__init__ = _init


def _step(argv):
    # same as the packaged entry: skip interpreter flags, -m <module> or a tools/... script path
    i = 0
    while i < len(argv) and argv[i].startswith("-") and argv[i] != "-m":
        i += 2 if argv[i] == "-X" else 1
    if argv[i] == "-m":
        name, rest = argv[i + 1], argv[i + 2:]
    else:
        p = Path(argv[i])
        name, rest = ".".join(["tools", p.parent.name, p.stem]), argv[i + 1:]
    sys.argv = [name, *rest]
    if "WRCG2ACR_WRCG_INSTALL" not in os.environ:
        # a step started by hand, not by the pipeline: give it the pipeline's environment (WRCG side only)
        import tools.exporter.pipeline as pl
        os.environ.update(pl._env(*_installs(), None))
    mod = importlib.import_module(name)
    import wr_fixes
    wr_fixes.before(name, rest)
    rc = mod.main()
    if not rc:
        wr_fixes.after(name, rest)
    return rc


def main():
    argv = sys.argv[1:]
    import tools.exporter.pipeline as pl
    _patch_run(pl)
    if argv[:1] == ["info"]:
        print("stages:", list(pl.stages()))
        return 0
    if argv[:1] == ["list"]:                      # WRCG rally stages, optionally filtered: list catalunya
        import wr_stages
        wr_stages.listing(" ".join(argv[1:]))
        return 0
    if argv[:1] == ["add"]:                       # add ES2_SPAIN/SS1 [--force]
        import wr_stages
        for sid in [a for a in argv[1:] if not a.startswith("--")]:
            wr_stages.add(sid, force="--force" in argv)
        return 0
    if argv[:1] == ["app"]:                       # the tool's window, with our stages and fixes
        import tools.exporter.app as app
        app.TITLE = "Stage Exporter (classic)"
        raise SystemExit(app.main())
    if argv[:1] == ["build-exe"]:                 # WRC to ACR Stage Exporter.exe (launcher) and its icon
        raise SystemExit(build_exe())
    if argv[:1] == ["ui"]:                        # our window: stages by location, export one at a time
        import wr_ui
        raise SystemExit(wr_ui.main())
    if argv[:1] in (["export"], ["remove"]):      # export <slug> ...: export these again, keep the rest of the pack
        import wr_pack
        slugs = [a for a in argv[1:] if not a.startswith("--")]
        fn = wr_pack.export if argv[0] == "export" else wr_pack.remove
        if "--keep-wrcg" in argv:                 # their WRCG export as it is: only the ACR build again
            os.environ[wr_pack.KEEP_WRCG_ENV] = "1"
        if "--serial" in argv:                    # the stages built one at a time
            os.environ[SERIAL_ENV] = "1"
        raise SystemExit(0 if fn(slugs, install="--no-install" not in argv) else 1)
    if argv[:1] == ["repack"]:                    # the pack again from the last builds (tables, pack, install)
        import wr_pack
        raise SystemExit(0 if wr_pack.run([], wr_pack.stages(), install="--no-install" not in argv) else 1)
    if argv[:1] == ["pack"]:
        import wr_pack
        for s in wr_pack.stages():
            print(f"{s:<16} last build {wr_pack.last_built(s) or '-'}{'' if wr_pack.built(s) else ' (not in the cache)'}")
        return 0
    if argv[:1] == ["run"]:                       # run <slug> ...: a pack of exactly these, all exported again
        slugs = [a for a in argv[1:] if not a.startswith("--")]
        if "--wrcg-only" in argv:
            raise SystemExit(0 if pl.run(*_installs(), slugs, install=False, log=print, wrcg_only=True) else 1)
        import wr_pack
        out = wr_pack.run(slugs, slugs, install="--install" in argv)
        if out and "--install" in argv:
            wr_pack.save(slugs)
        raise SystemExit(0 if out else 1)
    raise SystemExit(_step(argv))


ASIDE_PREFIX = "wr_previous_"


def _patch_run(pl):
    """The pipeline refuses to start while our pack is installed (it links ACR's stock paks past it, which fails across
    drives): the installed pack is renamed aside first (same folder, instant), dropped once a new one is installed,
    and put back if the export fails or installs nothing."""
    if getattr(pl.run, "_wr", False):
        return
    orig = pl.run

    def run(wrcg, acr, slugs, *a, **k):
        paks = Path(acr) / "acr" / "Content" / "Paks"
        mods = paks / "~mods"                    # the pack lives here (owner 2026-11-16: works in ~mods); the core installs into Paks
        dirs = [d for d in (paks, mods) if d.exists()]
        # a run cut short (owner 2026-11-10: the PC restarted during an export) left the pack aside: it goes back first
        for g in [x for d in dirs for x in d.glob(ASIDE_PREFIX + pl.OWN_PACK_PREFIX + "*.bak")]:
            f = g.with_name(g.name[len(ASIDE_PREFIX):-len(".bak")])
            if not f.exists():
                g.rename(f)
        aside = []
        for f in [x for d in dirs for x in d.glob(pl.OWN_PACK_PREFIX + "*")]:
            # a name the pipeline does not take for our pack and an extension ACR does not load
            g = f.with_name(ASIDE_PREFIX + f.name + ".bak")
            if g.exists():
                g.unlink()
            f.rename(g)
            aside.append((g, f))
        try:
            out = orig(wrcg, acr, slugs, *a, **k)
        except BaseException:
            for g, f in aside:
                if not f.exists():
                    g.rename(f)
            raise
        fresh = list(paks.glob(pl.OWN_PACK_PREFIX + "*")) if paks.exists() else []
        if fresh:                                # newly installed in Paks: moved to ~mods
            mods.mkdir(exist_ok=True)
            for f in fresh:
                (mods / f.name).unlink(missing_ok=True)
                shutil.move(str(f), str(mods / f.name))
        for g, f in aside:
            if fresh:                            # a new pack was installed: the old one goes
                g.unlink(missing_ok=True)
            elif not f.exists():                 # nothing installed (--wrcg-only, no --install): the old one goes back
                g.rename(f)
        return out

    run._wr = True
    pl.run = run


def _installs():
    cfg = json.loads((CUSTOM / "installs.json").read_text())
    return Path(cfg["wrcg"]), Path(cfg["acr"])


def build_exe():
    """WRC to ACR Stage Exporter.exe: a small Windows launcher (C#, the .NET Framework compiler that ships with Windows) that opens
    our window without a console, with our icon."""
    import wr_images
    assets = ROOT / "_internal" / "wr_assets"
    ico = wr_images.app_icon(assets / "stage_studio.ico")
    csc = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Microsoft.NET" / "Framework64" / "v4.0.30319" / "csc.exe"
    if not csc.exists():
        print(f"csc.exe not found ({csc})")
        return 1
    r = subprocess.run([str(csc), "-nologo", "-target:winexe", "-optimize+", "-r:System.Windows.Forms.dll",
                        f"-win32icon:{ico}", f"-out:{ROOT / 'WRC to ACR Stage Exporter.exe'}", str(assets / "StageStudio.cs")],
                       capture_output=True, text=True)
    print(r.stdout.strip() or f"built {ROOT / 'WRC to ACR Stage Exporter.exe'}")
    return r.returncode
