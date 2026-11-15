"""Setup of our version on a copy of Sando Rally's Stage Export Tool (run by INSTALAR.bat after it copies our files):
    _internal\\wrcg2acr-worker.exe -m wr_setup

1. custom/installs.json: the WRC Generations and Assetto Corsa Rally folders, found in the Steam libraries (asked for
   when not found).
2. The stock ACR data some of our improvements copy from (in work/acr, made from the user's own ACR install, nothing
   of the game is shipped):
     - Hafren South's finish cell (stop marshal at the finish, wr_finish.py),
     - Monte Carlo S1's lamp cell and its light blueprint (night lights on the street lamps, wr_lights.py),
     - Munster's skid decal cell (wr_skids.py),
     - the RuntimeVirtualTextures property template (grass taking the ground colour, wr_rvt.py; a property shape only).
   Each one is the level cell converted with the tool's own retoc and UaTool: byte-identical to ours (checked).
3. WRC to ACR Stage Exporter.exe, the window's launcher.
"""
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(sys.executable).resolve().parent.parent
CUSTOM = ROOT / "custom"
WORK = ROOT / "work"
WRCG_DIR = "WRC Generations - The FIA WRC Official Game"
ACR_DIR = "Assetto Corsa Rally"
CELLS = [("wr_cells_legacy", "Levels/WalesS4HafrenSouth/_Generated_/9XYWDVYVYCEUG004BCIGGGZ1X", "meta (comisario de parada)"),
         ("wr_stock_cells", "Levels/MonteCarloS1Bollene/_Generated_/1ETRLVT1729OA30AHK5CGZOQ7", "farolas"),
         ("wr_alsace", "Levels/AlsaceS2Munster/_Generated_/1XXMH9FJVC7ZDS8TC9W2RQY3Z", "derrapes y señales rompibles"),
         ("wr_servicepark", "Levels/AlsaceServicePark", "carpa del parque de asistencia")]
PROP_RVT = {"$type": "UAssetAPI.PropertyTypes.Objects.ArrayPropertyData, UAssetAPI", "ArrayType": "ObjectProperty",
            "Name": "RuntimeVirtualTextures", "ArrayIndex": 0, "PropertyGuid": None, "IsZero": False,
            "PropertyTagFlags": "None", "PropertyTypeName": None, "PropertyTagExtensions": "NoExtension",
            "Value": [{"$type": "UAssetAPI.PropertyTypes.Objects.ObjectPropertyData, UAssetAPI", "Name": "0",
                       "ArrayIndex": 0, "PropertyGuid": None, "IsZero": False, "PropertyTagFlags": "None",
                       "PropertyTypeName": None, "PropertyTagExtensions": "NoExtension", "Value": -163}]}


def _steam_libraries():
    """steamapps/common folders of every Steam library on this PC."""
    roots = []
    try:
        import winreg
        for hive, key in ((winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam"),
                          (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam")):
            try:
                with winreg.OpenKey(hive, key) as k:
                    for name in ("SteamPath", "InstallPath"):
                        try:
                            roots.append(Path(winreg.QueryValueEx(k, name)[0]))
                        except OSError:
                            pass
            except OSError:
                pass
    except ImportError:
        pass
    roots += [Path(r"C:\Program Files (x86)\Steam"), Path(r"C:\Program Files\Steam")]
    libs = []
    for r in roots:
        vdf = r / "steamapps" / "libraryfolders.vdf"
        if vdf.exists():
            for line in vdf.read_text(encoding="utf-8", errors="ignore").splitlines():
                parts = line.strip().split('"')
                if len(parts) >= 4 and parts[1] == "path":
                    libs.append(Path(parts[3].replace("\\\\", "\\")) / "steamapps" / "common")
        libs.append(r / "steamapps" / "common")
    for d in "CDEFGH":                                       # common places when Steam is not found
        libs.append(Path(f"{d}:/SteamLibrary/steamapps/common"))
    out = []
    for p in libs:
        if p not in out and p.exists():
            out.append(p)
    return out


def _ok_acr(p):
    return (p / "acr" / "Content" / "Paks").is_dir()


def _ask(what, check):
    while True:
        s = input(f"  Carpeta de {what} (pégala y pulsa Intro): ").strip().strip('"')
        if s and check(Path(s)):
            return Path(s)
        print("  No parece la carpeta correcta, prueba otra vez.")


def installs():
    f = CUSTOM / "installs.json"
    try:
        cfg = json.loads(f.read_text(encoding="utf-8"))
        w, a = Path(cfg["wrcg"]), Path(cfg["acr"])
        if w.is_dir() and _ok_acr(a):
            print(f"  Juegos (custom/installs.json): {w} | {a}")
            return w, a
    except (OSError, ValueError, KeyError):
        pass
    libs = _steam_libraries()
    w = next((l / WRCG_DIR for l in libs if (l / WRCG_DIR).is_dir()), None)
    a = next((l / ACR_DIR for l in libs if _ok_acr(l / ACR_DIR)), None)
    if w is None:
        print("  No encuentro WRC Generations en Steam.")
        w = _ask("WRC Generations", lambda p: p.is_dir())
    if a is None:
        print("  No encuentro Assetto Corsa Rally en Steam.")
        a = _ask("Assetto Corsa Rally", _ok_acr)
    CUSTOM.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps({"wrcg": str(w).replace("\\", "/"), "acr": str(a).replace("\\", "/")}, indent=1),
                 encoding="utf-8")
    print(f"  WRC Generations: {w}\n  Assetto Corsa Rally: {a}")
    return w, a


def _box_body(c, paks):
    """wr_assets/box_body_template.json (wr_breakables): the box of ACR's plastic barrier's body
    (SM_PlasticBarrierAFix), from this PC's own ACR."""
    assets = Path(__file__).resolve().parent / "wr_assets"
    tmpl = assets / "box_body_template.json"
    if tmpl.exists():
        return
    tmp = Path(tempfile.mkdtemp(prefix="wr_setup_"))
    try:
        c.retoc("to-legacy", paks, str(tmp), "-f", "SM_PlasticBarrierAFix", "--version", "UE5_6", "--no-shaders")
        f = next(tmp.rglob("SM_PlasticBarrierAFix.uasset"))
        c.asset_json(f, tmp / "m.json")
        j = json.loads((tmp / "m.json").read_text(encoding="utf-8"))
        body = next(e for e in j["Exports"] if "BodySetup" in e["ObjectName"])
        agg = next(p for p in body["Data"] if p.get("Name") == "AggGeom")
        tmpl.write_text(json.dumps(agg, separators=(",", ":")), encoding="utf-8")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    print("Stage Exporter: preparando las mejoras\n")
    print("1/3 Juegos")
    w, a = installs()
    import wr
    import tools.exporter.pipeline as pl
    os.environ.update(pl._env(w, a, a / "acr" / "Content" / "Paks"))
    import tools.acrmod.common as c
    paks = os.environ["WRCG2ACR_ACR_PAKS"]

    print("\n2/3 Datos de Assetto Corsa Rally que usan las mejoras (de tu propia instalación)")
    acr = WORK / "acr"
    for folder, rel, what in CELLS:
        out = acr / folder / "acr" / "Content" / (rel + ".json")
        if out.exists():
            print(f"  {what}: ya estaba")
            continue
        tmp = Path(tempfile.mkdtemp(prefix="wr_setup_"))
        try:
            c.retoc("to-legacy", paks, str(tmp), "-f", rel.rsplit("/", 1)[-1], "--version", "UE5_6", "--no-shaders")
            out.parent.mkdir(parents=True, exist_ok=True)
            c.asset_json(tmp / "acr" / "Content" / (rel + ".umap"), out)
            print(f"  {what}: listo")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    _box_body(c, paks)
    print("  colisión de las señales que se rompen: listo")
    rvt = acr / "wr_prop_rvt.json"
    if not rvt.exists():
        acr.mkdir(parents=True, exist_ok=True)
        rvt.write_text(json.dumps(PROP_RVT), encoding="utf-8")
    print("  color del césped (RVT): listo")
    import wr_lights
    wr_lights._light_props(acr)                               # the lamp's light blueprint
    print("  luz de las farolas: listo")

    print("\n3/3 WRC to ACR Stage Exporter.exe")
    rc = wr.build_exe()
    print("\nTodo listo. Abre 'WRC to ACR Stage Exporter.exe' en la carpeta de la herramienta." if rc == 0 else
          "\nLas mejoras están instaladas; WRC to ACR Stage Exporter.exe no se pudo crear (la herramienta se puede usar con "
          "_internal\\wrcg2acr-worker.exe -m wr ...).")
    return 0
