"""Final asset conversion for the old 0.3.7 core and ACR 26756580.
The core deliberately keeps its old mapping/templates; only validated output is packed with the new layout.
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORK = ROOT / 'work'
BIN = ROOT / 'bin'
REGISTRY = WORK / 'acr' / 'migrated_levels.json'
TWINS = WORK / 'acr' / 'wr_twins'
OLD_BUILD = '25170642'
NEW_BUILD = '26756580'


def _paks():
    import wr
    return wr._installs()[1] / 'acr' / 'Content' / 'Paks'


def installed_build():
    manifest = _paks().parents[4] / 'appmanifest_3917090.acf'
    match = re.search(r'"buildid"\s+"(\d+)"', manifest.read_text(encoding='utf-8-sig'))
    if not match:
        raise RuntimeError('Cannot identify the installed ACR build')
    return match[1]


def required():
    build = installed_build()
    if build not in (OLD_BUILD, NEW_BUILD):
        raise RuntimeError(f'ACR build {build} is not supported by this compatibility converter; no pack will be installed')
    return build == NEW_BUILD


def prepare():
    if not required():
        return False
    files = ['acr_stage.usmap', 'acr_26756580.usmap', 'acr_affected_classes.json', 'uatool/UaTool.exe',
             'migrate/Migrate.exe', 'migrate/Migrate.dll', 'migrate/Migrate.runtimeconfig.json',
             'migrate/UAssetAPI.dll', 'migrate/Newtonsoft.Json.dll', 'migrate/ZstdSharp.dll']
    missing = [str(BIN / p) for p in files if not (BIN / p).is_file()]
    if missing:
        raise RuntimeError('ACR 0.7 compatibility files missing (install Stage-Exporter-<version>-Instalar.zip, it carries bin/): ' + ', '.join(missing))
    oval_template()
    return True


def oval_template(log=print):
    """The core's BakedDataContainer template is a test asset (tests/FeatureTests/ExampleCutscenesAuthoring) that build
    26756580 no longer ships: the extraction leaves a hole and build_stage dies in UaTool dumpjson. Same class, so the
    smallest stock BakedData (main menu) stands in for it. UNVERIFIED that the core accepts it."""
    dst = WORK / 'acr' / 'legacy_hs' / 'acr' / 'Content' / 'tests' / 'FeatureTests' / 'ExampleCutscenesAuthoring'
    name = 'DA_oval_cutscene_authoringBakedData'
    if (dst / (name + '.uasset')).is_file():
        return
    shipped = BIN / 'oval'
    if all((shipped / (name + e)).is_file() for e in ('.uasset', '.uexp')):
        dst.mkdir(parents=True, exist_ok=True)
        for e in ('.uasset', '.uexp'):
            shutil.copyfile(shipped / (name + e), dst / (name + e))
        log('    BakedData template of the core restored from bin/oval')
        return
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run([str(BIN / 'retoc' / 'retoc.exe'), 'to-legacy', str(_paks()), tmp, '-f', 'DA_MainMenuWalesBakedData',
                        '--version', 'UE5_6', '--no-shaders', '--no-script-objects'], check=True, capture_output=True)
        src = next(Path(tmp).rglob('DA_MainMenuWalesBakedData.uasset'))
        dst.mkdir(parents=True, exist_ok=True)
        for ext in ('.uasset', '.uexp'):
            shutil.copyfile(src.with_suffix(ext), dst / (name + ext))
    log('    BakedData template of the core missing in this ACR build: stock main-menu BakedData used instead')


def _twins(log):
    import wr_mishaders
    paks = _paks()
    stat = (paks / 'pakchunk0-Windows.utoc').stat()
    stamp = f'{NEW_BUILD}:{stat.st_size}:{stat.st_mtime_ns}'
    marker = TWINS / 'stamp.txt'
    if marker.exists() and marker.read_text() == stamp:
        for name in wr_mishaders.OLD.values():
            wr_mishaders._find(TWINS, name)
        return TWINS
    TWINS.mkdir(parents=True, exist_ok=True)
    for name in set(wr_mishaders.OLD.values()):
        result = subprocess.run([str(BIN / 'retoc' / 'retoc.exe'), 'to-legacy', str(paks), str(TWINS), '-f', name,
                                 '--version', 'UE5_6', '--no-shaders', '--no-script-objects'], capture_output=True, text=True)
        if result.returncode:
            raise RuntimeError(f'Cannot refresh material {name}: {(result.stdout + result.stderr)[-600:]}')
        wr_mishaders._find(TWINS, name)
    marker.write_text(stamp)
    return TWINS


def _hash(umap):
    h = hashlib.sha256()
    for p in (umap, umap.with_suffix('.uexp')):
        with p.open('rb') as f:
            for block in iter(lambda: f.read(1024 * 1024), b''):
                h.update(block)
    return h.hexdigest()


def migrate_level(umap, log=print):
    umap = Path(umap)
    REGISTRY.parent.mkdir(parents=True, exist_ok=True)
    # File locks are released by Windows even if an export is cancelled or its process exits.
    import msvcrt
    with (REGISTRY.parent / 'compat-migration.lock').open('a+b') as lock:
        if lock.tell() == 0:
            lock.write(b'0'); lock.flush()
        lock.seek(0)
        msvcrt.locking(lock.fileno(), msvcrt.LK_LOCK, 1)
        try:
            return _migrate_level(umap, log)
        finally:
            lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)


def _migrate_level(umap, log):
    tool, new, aff = BIN / 'migrate' / 'Migrate.exe', BIN / 'acr_26756580.usmap', BIN / 'acr_affected_classes.json'
    try:
        reg = json.loads(REGISTRY.read_text())
    except FileNotFoundError:
        reg = {}
    sha = _hash(umap)
    if sha in reg.get(umap.stem, []):
        log(f'    level {umap.stem}: already in the new layout')
        return False
    with tempfile.TemporaryDirectory(prefix='wr_mig_') as temp:
        tmp = Path(temp)
        for ext in ('.umap', '.uexp'):
            shutil.copy2(umap.with_suffix(ext), (tmp / 'in.umap').with_suffix(ext))
        out = tmp / f'{umap.stem}.umap'
        result = subprocess.run([str(tool), str(tmp / 'in.umap'), str(BIN / 'acr_stage.usmap'), str(new), str(out), str(aff)],
                                capture_output=True, text=True)
        if result.returncode or 'VALIDATED:' not in result.stdout or not out.is_file() or not out.with_suffix('.uexp').is_file():
            raise RuntimeError(f'ACR 0.7 migration FAILED for {umap.stem}; packing cancelled: {(result.stdout + result.stderr)[-1200:]}')
        try:
            for ext in ('.umap', '.uexp'):
                shutil.copy2(out.with_suffix(ext), umap.with_suffix(ext))
        except Exception:
            for ext in ('.umap', '.uexp'):
                shutil.copy2((tmp / 'in.umap').with_suffix(ext), umap.with_suffix(ext))
            raise
        reg.setdefault(umap.stem, []).append(_hash(umap))
        registry_tmp = REGISTRY.with_suffix('.json.tmp')
        registry_tmp.write_text(json.dumps(reg, indent=1))
        os.replace(registry_tmp, REGISTRY)
        log(f'    level {umap.stem} migrated to ACR {NEW_BUILD}: {result.stdout.strip().splitlines()[-1]}')
    return True


def after_build(slug, level, mod='wrcg_stages', log=print):
    if not prepare():
        return
    import wr_mishaders
    # the core bakes a stage into mods/<mod>/stages/<slug>/legacy and only moves it to mods/<mod>/legacy (and the cache) after this step
    legacy = WORK / 'acr' / 'mods' / mod / 'stages' / slug / 'legacy'
    if not legacy.is_dir():
        legacy = WORK / 'acr' / 'mods' / mod / 'legacy'
    wr_mishaders.patch_dir(_twins(log), legacy / 'acr' / 'Content' / 'Environments' / level, log, strict=True)
    umap = legacy / 'acr' / 'Content' / 'Levels' / f'{level}.umap'
    if not umap.is_file():
        raise FileNotFoundError(f'Built level missing before compatibility conversion: {umap}')
    migrate_level(umap, log)


def _folder_name(uasset):
    """The package name in a cooked .uasset's header (FolderName), or None."""
    import struct
    head = Path(uasset).read_bytes()[:300]
    i = head.find(b'/Game/')
    if i < 4:
        return None
    n = struct.unpack('<i', head[i - 4:i])[0]
    return head[i:i + n - 1].decode('latin1') if 0 < n < 250 and head[i + n - 1:i + n] == b'\0' else None


def fix_package_names(content, log=print):
    """Assets of our stages whose header names another package (a material instance cloned from a stock one kept the stock
    name: retoc makes the package id from it, so all 36 far-tree materials of Ngema and Seyabei had the ids of ACR's own
    MI_*Impostor, and the stock ones were overridden). Rewritten with their own name; the .uexp is untouched. Idempotent."""
    content = Path(content)
    todo = []
    for ua in content.rglob('*.uasset'):
        if not ua.relative_to(content).parts[1:2] or not ua.relative_to(content).parts[1].startswith('Wrcg'):
            continue
        want = '/Game/' + ua.relative_to(content).with_suffix('').as_posix()
        have = _folder_name(ua)
        if have and have != want:
            todo.append((ua, want))
    if not todo:
        return 0
    import tools.acrmod.common as c
    with tempfile.TemporaryDirectory(prefix='wr_fn_') as temp:
        for ua, want in todo:
            j = Path(temp) / 'a.json'
            c.asset_json(ua, j)
            d = json.loads(j.read_text(encoding='utf-8'))
            d['FolderName'] = want
            c.write_asset(d, Path(temp) / 'a.edit.json', ua)
    log(f'    package names fixed: {len(todo)} asset(s) carried a stock package name (e.g. {todo[0][0].name})')
    return len(todo)


def before_pack(args, log=print):
    """Last barrier before retoc: after-build hooks cannot be bypassed by a cache hit or a direct repack."""
    values = list(map(str, args))
    if not values or Path(values[0]).name.lower() != 'retoc.exe' or 'to-zen' not in values:
        return
    positionals = []
    i = values.index('to-zen') + 1
    while i < len(values):
        if values[i] in ('--version', '--script-cell', '-f', '--filter'):
            i += 2
        elif values[i].startswith('-'):
            i += 1
        else:
            positionals.append(values[i]); i += 1
    if len(positionals) != 2:
        raise RuntimeError('Cannot verify retoc input before packing')
    legacy = Path(positionals[0]).resolve()
    if not legacy.is_relative_to((WORK / 'acr' / 'mods').resolve()):
        return
    fix_package_names(legacy / 'acr' / 'Content', log)     # any ACR build
    if not prepare():
        return
    levels = sorted((legacy / 'acr' / 'Content' / 'Levels').glob('Wrcg*.umap'))
    if not levels:
        raise RuntimeError('No built stage levels found; packing cancelled')
    import wr_mishaders
    wr_mishaders.patch_dir(_twins(log), legacy / 'acr' / 'Content' / 'Environments', log, strict=True)
    for umap in levels:
        migrate_level(umap, log)
    log(f'    ACR {NEW_BUILD} compatibility checked before packing: {len(levels)} level(s)')
