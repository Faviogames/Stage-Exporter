"""Menu names and images of our stages and locations (owner 2026-11-09: set them in the importer).

Images live in custom/images:
  <slug>/card.png        1720 x 448   the stage's card (DT_TracksVariants VariantImage)
  <slug>/background.png  1325 x 922   the stage's background (DT_Tracks TrackImage and LobbyTrackImage)
  <slug>/lobby.png        170 x 100   the stage's lobby image (DT_TracksVariants LobbyVariantImage)
  <location row>/logo.png        485 x 218   the location's logo (DT_TracksLocationsLogos), e.g. WrcgSpain
  <location row>/background.png  406 x 737   the location's background (DT_TracksLocationsBackgrounds)
store() fits a picture to its size (scaled to cover, centred crop). They are applied when the pack's tables are written
(wr_fixes), so a change needs only a repack: the stage textures go to /Game/Data/UITextures/Tracks/Wrcg as the tool
writes its menu textures (B8G8R8A8, no mips, TEXTUREGROUP_UI, TC_EditorIcon) with rows of their own in
DT_TracksTextures; a location's go through the tool's own _card_image with a texture name per location.
"""
import copy
import io
import json
from pathlib import Path

import numpy as np

from wr import CUSTOM

IMAGES = CUSTOM / "images"
SLOTS = {"card": (1720, 448), "background": (1325, 922), "lobby": (170, 100)}
LOC_SLOTS = {"logo": (485, 218), "background": (406, 737)}
DESCRIPTIONS = CUSTOM / "descriptions.json"     # ACR location row -> text of its "History and trivia" panel


def location_text(row):
    try:
        return json.loads(DESCRIPTIONS.read_text(encoding="utf-8")).get(row) or None
    except (OSError, ValueError):
        return None


def set_location_text(row, text):
    try:
        d = json.loads(DESCRIPTIONS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        d = {}
    if text:
        d[row] = text
    else:
        d.pop(row, None)
    DESCRIPTIONS.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
TEX_DIR = "/Game/Data/UITextures/Tracks/Wrcg"
TEXTURES_TABLE = "Data/Database/Main/TrackSelection/DT_TracksTextures"
EXTS = (".png", ".jpg", ".jpeg", ".webp", ".bmp")


def location_row(country):
    """ACR location row of a WRCG country name (same as wr_fixes.location_of): 'SPAIN' -> WrcgSpain."""
    import wr_stages
    return "Wrcg" + "".join(wr_stages.country_name(country).split())


def find(folder, slot):
    for ext in EXTS:
        p = Path(folder) / f"{slot}{ext}"
        if p.exists():
            return p
    return None


def fitted(src, size):
    """The picture scaled to cover size and centre-cropped, as RGBA."""
    from PIL import Image
    im = Image.open(src).convert("RGBA")
    w, h = size
    k = max(w / im.width, h / im.height)
    im = im.resize((max(w, round(im.width * k)), max(h, round(im.height * k))), Image.LANCZOS)
    x, y = (im.width - w) // 2, (im.height - h) // 2
    return im.crop((x, y, x + w, y + h))


def store(src, folder, slot, size):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    for ext in EXTS:
        old = folder / f"{slot}{ext}"
        if old.exists():
            old.unlink()
    out = folder / f"{slot}.png"
    fitted(src, size).save(out)
    return out


def png_bytes(src, size):
    b = io.BytesIO()
    fitted(src, size).save(b, "PNG")
    return b.getvalue()


# --- stage images: textures + DT_TracksTextures rows ------------------------------------------------------------------

def _use_name(asset, name):
    """name in the asset's name map, inside NamesReferencedFromExportDataCount (see wr_fixes._add_names)."""
    nm = asset["NameMap"]
    count = asset.get("NamesReferencedFromExportDataCount")
    if not isinstance(count, int) or not 0 <= count <= len(nm):
        if name not in nm:
            nm.append(name)
        return
    if name in nm[:count]:
        return
    if name in nm:
        nm.remove(name)
    nm.insert(count, name)
    asset["NamesReferencedFromExportDataCount"] = count + 1


def write_stage_images(out_legacy, stages, log=print):
    """stages: [(track row, slug)]. Writes the textures and DT_TracksTextures into out_legacy; returns
    {track row: {slot: DT_TracksTextures row}} for the stages that have images."""
    import tempfile
    import tools.acrmod.common as c
    import tools.acrmod.texture_writer as tw
    out_legacy = Path(out_legacy)
    rows, made = {}, []
    with tempfile.TemporaryDirectory(prefix="wr_img_") as tmp:
        for track, slug in stages:
            for slot, size in SLOTS.items():
                src = find(IMAGES / slug, slot) or find(IMAGES / slug.removesuffix("r"), slot)   # reverse (es_ss1r) uses es_ss1's
                if src is None:
                    continue
                png = Path(tmp) / f"{track}_{slot}.png"
                fitted(src, size).save(png)
                tex = f"T_{track}_{slot.capitalize()}"
                tw.write_texture(out_legacy, f"{TEX_DIR}/{tex}", image=str(png), fmt="B8G8R8A8", srgb=True, mips=False,
                                 lod_group="TEXTUREGROUP_UI", compression="TC_EditorIcon", never_stream=True)
                row = f"{track}_{slot.capitalize()}"
                rows.setdefault(track, {})[slot] = row
                made.append((row, f"{TEX_DIR}/{tex}", tex))
        if not made:
            return rows
        base = c.stock_legacy(TEXTURES_TABLE) / "acr" / "Content" / (TEXTURES_TABLE + ".uasset")
        j = Path(tmp) / "DT_TracksTextures.json"
        asset = c.asset_json(base, j)
        data = asset["Exports"][0]["Table"]["Data"]
        proto = next(r for r in data if r["Name"] == "Bollene_Lobby")
        have = {r["Name"] for r in data}
        for row, pkg, tex in made:
            r = copy.deepcopy(proto)
            r["Name"] = row
            path = r["Value"][0]["Value"]["AssetPath"]
            path["PackageName"], path["AssetName"] = pkg, tex
            if row in have:
                data[:] = [x for x in data if x["Name"] != row]
            data.append(r)
            for n in (row, pkg, tex):
                _use_name(asset, n)
        out = out_legacy / "acr" / "Content" / (TEXTURES_TABLE + ".uasset")
        out.parent.mkdir(parents=True, exist_ok=True)
        c.write_asset(asset, Path(tmp) / "DT_TracksTextures.edit.json", out)
    log(f"    menu images: {len(made)} stage images ({', '.join(sorted(rows))})")
    return rows


def set_ref(asset, prop, row):
    """A DataTable row reference (struct with Row) of a row export set to row (its name made usable)."""
    f = next((p for p in prop["Value"] if p["Name"] == "Row"), None)
    if f is not None:
        f["Value"] = row
        _use_name(asset, row)


# --- our own artwork (no third-party branding): app icon, default location logo / background ------------------------

ACCENT = (255, 107, 44)
DARK = (15, 18, 22)
PANEL = (23, 27, 33)
FONTS = "C:/Windows/Fonts/"


def _font(names, size):
    from PIL import ImageFont
    for n in names:
        try:
            return ImageFont.truetype(FONTS + n, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _road(draw, w, h, width, color, dash=None, k=1.0):
    """A vertical S-curve road through a w x h box (supersampled drawing)."""
    import math as m
    pts = [(w * (0.5 + 0.2 * k * m.sin(t * m.pi * 1.6 - 0.5)), h * (1.1 - 1.2 * t)) for t in [i / 80 for i in range(81)]]
    draw.line(pts, fill=color, width=width, joint="curve")
    if dash:
        for i in range(2, 80, 8):
            draw.line(pts[i:i + 4], fill=dash, width=max(2, width // 10))


def app_icon(path):
    """Stage Exporter's icon: an orange rally road on a dark rounded square (multi-size .ico)."""
    from PIL import Image, ImageDraw
    S = 1024
    base = Image.new("RGBA", (S, S), PANEL + (255,))
    d = ImageDraw.Draw(base)
    _road(d, S, S, 170, ACCENT + (255,), dash=(255, 240, 225, 255), k=1.15)
    for i in range(4):                                     # a little chequered flag
        for j in range(3):
            if (i + j) % 2 == 0:
                d.rectangle([660 + i * 56, 170 + j * 56, 716 + i * 56, 226 + j * 56], fill=(236, 239, 243, 255))
    d.line([(660, 170), (660, 430)], fill=(236, 239, 243, 255), width=18)
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle([24, 24, S - 24, S - 24], radius=230, fill=255)
    im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    im.paste(base, (0, 0), mask)
    ImageDraw.Draw(im).rounded_rectangle([24, 24, S - 24, S - 24], radius=230, outline=(44, 51, 61, 255), width=16)
    im = im.resize((256, 256), Image.LANCZOS)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    im.save(path, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    return path


def default_location(slot, title):
    """A location's logo (485 x 218) or background (406 x 737) when it has none of its own: 'Imported <Country>'."""
    from PIL import Image, ImageDraw
    country = title.replace("[MOD] ", "").replace("Imported ", "").upper()
    if slot == "logo":
        W, H, k = 485, 218, 3
        im = Image.new("RGBA", (W * k, H * k), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        d.rounded_rectangle([0, 0, W * k - 1, H * k - 1], radius=26 * k, fill=PANEL + (255,))
        d.rounded_rectangle([22 * k, 30 * k, 34 * k, (H - 30) * k], radius=6 * k, fill=ACCENT + (255,))
        d.text((58 * k, 46 * k), "MOD", font=_font(["bahnschrift.ttf", "segoeuib.ttf"], 30 * k), fill=(139, 148, 163, 255))
        size = 74 if len(country) <= 9 else 58 if len(country) <= 13 else 44
        d.text((54 * k, 84 * k), country, font=_font(["segoeuib.ttf"], size * k), fill=(236, 239, 243, 255))
        d.text((58 * k, (H - 46) * k), "WRC GENERATIONS STAGES", font=_font(["bahnschrift.ttf", "segoeui.ttf"], 20 * k),
               fill=ACCENT + (255,))
        return im.resize((W, H), Image.LANCZOS)
    W, H, k = 406, 737, 2
    im = Image.new("RGB", (W * k, H * k), DARK)
    d = ImageDraw.Draw(im)
    for y in range(H * k):                                  # dark gradient
        t = y / (H * k)
        c = tuple(int(a + (b - a) * t) for a, b in zip((44, 50, 60), DARK))
        d.line([(0, y), (W * k, y)], fill=c)
    _road(d, W * k, H * k, 120, (70, 52, 44), dash=(96, 80, 70), k=0.6)
    d.text((34 * k, (H - 120) * k), country, font=_font(["segoeuib.ttf"], 40 * k), fill=(236, 239, 243))
    d.rectangle([34 * k, (H - 64) * k, 120 * k, (H - 58) * k], fill=ACCENT)
    return im.resize((W, H), Image.LANCZOS)


def default_location_png(slot, title):
    b = io.BytesIO()
    default_location(slot, title).save(b, "PNG")
    return b.getvalue()
