"""A stage as one file (.stage): Stage Studio's "Exportar como .stage" / "Importar tramo".

The file is a zip of the stage's last build (its entry in the build cache, which wr_pack builds the pack from without
WRCG's export), its stage build and its menu images. Importing puts the entry in the cache, the build and images in
custom/, and the stage in the pack; "Aplicar al pack" then builds one pack with every stage, so there are never two
packs whose menu tables fight over the same assets (2026-11-14).
The entry holds a pickle (result.pkl) that the build loads: import only .stage files from people you trust.
"""
import json
import re
import shutil
import zipfile
from pathlib import Path

import wr_images
import wr_pack
from wr import CUSTOM

FORMAT = 1
META = "stage.json"
SLUG = re.compile(r"^[a-z0-9_]{1,40}$")
KEY = re.compile(r"^stage/[0-9a-f]{32}$")
ROW = re.compile(r"^Wrcg[A-Za-z0-9]{1,40}$")
COUNTRY_IMG = re.compile(r"country_images/(logo|background)(\.\w+)")


def _country_row(cfg_text):
    try:
        import wr_fixes
        return wr_fixes.location_of(json.loads(cfg_text))[0]
    except Exception:
        return None                       # the stage still saves; it just carries no country data


def export_stage(slug, dest, log=print):
    if not wr_pack.built(slug):
        raise ValueError(f"{slug} has no build in the cache: export it first")
    k = wr_pack.keys()[slug]
    entry = wr_pack._entry(k["key"])
    cfg = CUSTOM / "data" / "stage_builds" / f"{slug}.json"
    if cfg.exists():
        cfg_text = cfg.read_text(encoding="utf-8")
    else:
        import tools.datafiles as df
        cfg_text = json.dumps(df.load_json(f"stage_builds/{slug}.json"), ensure_ascii=False, indent=1)
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED, compresslevel=1) as z:
        z.writestr(META, json.dumps({"format": FORMAT, "slug": slug, "key": k["key"], "time": k.get("time")}))
        z.writestr("stage_build.json", cfg_text)
        for p in sorted((CUSTOM / "images" / slug).glob("*")):
            z.write(p, f"images/{p.name}")
        row = _country_row(cfg_text)                         # the country's description, logo and background, if set
        if row:
            imgs = [(slot, p) for slot in wr_images.LOC_SLOTS if (p := wr_images.find(wr_images.IMAGES / row, slot))]
            text = wr_images.location_text(row) or ""
            if text or imgs:
                z.writestr("country.json", json.dumps({"row": row, "description": text}, ensure_ascii=False))
                for slot, p in imgs:
                    z.write(p, f"country_images/{slot}{p.suffix.lower()}")
        files = [p for p in entry.rglob("*") if p.is_file()]
        for i, p in enumerate(files, 1):
            z.write(p, "cache/" + p.relative_to(entry).as_posix())
            if i % 2000 == 0:
                log(f"  {i}/{len(files)} files")
    log(f"{slug}: saved {dest} ({Path(dest).stat().st_size / 2 ** 30:.2f} GB)")


def peek(src):
    """The slug and key of a .stage file, checked; raises ValueError for anything else."""
    with zipfile.ZipFile(src) as z:
        meta = json.loads(z.read(META))
    if meta.get("format") != FORMAT or not SLUG.match(str(meta.get("slug"))) or not KEY.match(str(meta.get("key"))):
        raise ValueError("not a Stage Studio stage file")
    return meta


def _extract(z, prefix, dest, skip_existing=False):
    """Members under prefix into dest; a name that would land outside dest stops the import (zip-slip)."""
    base = Path(dest).resolve()
    for n in z.namelist():
        if not n.startswith(prefix) or n.endswith("/"):
            continue
        t = (base / n[len(prefix):]).resolve()
        if not t.is_relative_to(base):
            raise ValueError(f"unsafe path in the file: {n}")
        if skip_existing and t.exists():
            continue
        t.parent.mkdir(parents=True, exist_ok=True)
        with z.open(n) as f, open(t, "wb") as o:
            shutil.copyfileobj(f, o)


def import_stage(src, log=print):
    meta = peek(src)
    slug, key = meta["slug"], meta["key"]
    entry = wr_pack._entry(key)
    with zipfile.ZipFile(src) as z:
        if (entry / "manifest.json").exists():
            log(f"{slug}: its build is already in the cache")
        else:
            part = entry.with_name(entry.name + ".part")         # a cut import leaves no half entry
            shutil.rmtree(part, ignore_errors=True)
            try:
                _extract(z, "cache/", part)
                if not (part / "manifest.json").exists():
                    raise ValueError("the file has no build manifest")
                shutil.rmtree(entry, ignore_errors=True)
                part.rename(entry)
            finally:
                shutil.rmtree(part, ignore_errors=True)
        cfg = CUSTOM / "data" / "stage_builds" / f"{slug}.json"
        if "stage_build.json" in z.namelist():           # the build in the cache was made with this one: names included
            new = z.read("stage_build.json")
            if not cfg.exists() or cfg.read_bytes() != new:
                cfg.parent.mkdir(parents=True, exist_ok=True)
                if cfg.exists():
                    shutil.copy2(cfg, cfg.with_suffix(".json.bak"))
                cfg.write_bytes(new)
        _extract(z, "images/", CUSTOM / "images" / slug, skip_existing=True)   # your own images stay
        if "country.json" in z.namelist():               # country data only fills what is empty here
            c = json.loads(z.read("country.json"))
            row = str(c.get("row"))
            if ROW.match(row):
                if c.get("description") and not wr_images.location_text(row):
                    wr_images.set_location_text(row, c["description"])
                for n in z.namelist():
                    m = COUNTRY_IMG.fullmatch(n)
                    if m and m.group(2) in wr_images.EXTS and not wr_images.find(wr_images.IMAGES / row, m.group(1)):
                        t = wr_images.IMAGES / row / (m.group(1) + m.group(2))
                        t.parent.mkdir(parents=True, exist_ok=True)
                        t.write_bytes(z.read(n))
    ks = wr_pack.keys()
    ks[slug] = {"key": key, "time": meta.get("time") or ""}
    wr_pack._save_keys(ks)
    pack = wr_pack.stages()
    if slug not in pack:
        wr_pack.save(pack + [slug])
    log(f"{slug}: imported; press Aplicar al pack to build the pack with it")
    return slug
