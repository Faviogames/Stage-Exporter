"""Stage Exporter: WRC Generations stages, exported one at a time into Assetto Corsa Rally (our window, wr_pack.py).

Left: WRCG's rallies by country. Centre: the stages of the selected rally (length, surface, whether they are in the
pack, last export). Right: the selected stage, its card and actions: "Exportar tramo" exports it again (added to the
pack if new; a stage build of ours is made for a stage that has none, wr_stages.add) and reuses the last build of every
other stage of the pack; "Quitar del pack" drops it; "Nombre e imagenes"; "Actualizar pack" rewrites the pack's tables
and images without exporting anything. Bottom: progress of the run (phases read from the pipeline's log: WRCG export,
each stage's build steps, packing, installing), time left, details, cancel.
"""
import json
import os
import queue
import re
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

APP = "Stage Exporter"
SUB = "WRC Generations  \u2192  Assetto Corsa Rally"


def _lang():
    """'es' or 'en': custom/lang.json, else the Windows display language."""
    try:
        import wr
        return json.loads((wr.CUSTOM / "lang.json").read_text(encoding="utf-8")).get("lang") or "es"
    except (OSError, ValueError, ImportError):
        pass
    try:
        import ctypes
        return "es" if ctypes.windll.kernel32.GetUserDefaultUILanguage() & 0xFF == 0x0A else "en"
    except Exception:
        return "es"


LANG = _lang()
EN = {'Actualizar pack': 'Update pack', '☑ en el pack': '☑ in the pack', '☐ disponible': '☐ available', 'sin exportar': 'not exported', 'No hay ningún tramo marcado: ¿quitar el pack del juego?': 'No stage is ticked: remove the pack from the game?', 'Creado por @AlbertPalahi, disponible en Patreon': 'Created by @AlbertPalahi, available on Patreon', 'Importar tramo': 'Import stage', 'Logo y descripción': 'Logo and description', 'Exportar tramo': 'Export stage', 'Exportar de nuevo': 'Export again', 'Nombre e imágenes': 'Name and images', 'Guardar como .stage': 'Save as .stage', 'Quitar del pack': 'Remove from pack', 'RALLIES': 'RALLIES', 'Tramos': 'Stages', 'TRAMO': 'STAGE', 'KM': 'KM', 'SUPERFICIE': 'SURFACE', 'ESTADO': 'STATUS', 'EXPORTADO': 'EXPORTED', 'Listo': 'Ready', 'Detalles': 'Details', 'Cancelar': 'Cancel', '  ·  especial': '  ·  special', 'en el pack': 'in the pack', 'no soportado': 'not supported', 'nuevo': 'new', 'asfalto': 'tarmac', 'nieve': 'snow', 'tierra': 'gravel', 'Construido: {x}': 'Built: {x}', 'Aún no exportado': 'Not exported yet', 'WRC Generations no tiene piezas de carretera en este tramo (la calle es parte de un objeto de la ciudad).': 'WRC Generations has no road pieces on this stage (the street is part of a city object).', '{name} no se puede exportar todavía.\n\nEn WRC Generations este tramo no tiene piezas de carretera (la calle es parte de un objeto de terreno de la ciudad).': '{name} cannot be exported yet.\n\nIn WRC Generations this stage has no road pieces (the street is part of a city terrain object).', '¿Exportar {name}?\n\nLos otros {n} tramos del pack se reutilizan tal como están. Al terminar se instala el pack en Assetto Corsa Rally.': 'Export {name}?\n\nThe other {n} stages of the pack are reused as they are. When it finishes, the pack is installed in Assetto Corsa Rally.', '¿Quitar {name} del pack?\n\n': 'Remove {name} from the pack?\n\n', 'No se vuelve a construir ningún tramo; se instala el pack con el resto.': 'No stage is built again; the pack is installed with the rest.', 'Es el único tramo del pack: se quita el pack del juego (cierra el juego antes).': 'It is the only stage of the pack: the pack is removed from the game (close the game first).', '¿Rehacer el pack con los nombres e imágenes actuales?\n\nNo se exporta ningún tramo (aprox. 1 min) y se instala el pack.': 'Rebuild the pack with the current names and images?\n\nNo stage is exported (about 1 min) and the pack is installed.', '¿Cancelar la exportación?\n\nEl pack instalado se queda como estaba.': 'Cancel the export?\n\nThe installed pack stays as it was.', '{name} todavía no está construido: expórtalo primero.': '{name} is not built yet: export it first.', '{name}: guardando {f} (unos minutos, pesa varios GB)...': '{name}: saving {f} (a few minutes, it weighs several GB)...', 'Tramo de Stage Exporter': 'Stage Exporter stage', 'Este fichero no es un tramo de Stage Exporter.\n\n{e}': 'This file is not a Stage Exporter stage.\n\n{e}', '¿Importar el tramo {slug}?\n\nImporta solo ficheros de gente de confianza: el tramo incluye datos que la herramienta carga al construir el pack.': 'Import stage {slug}?\n\nOnly import files from people you trust: the stage includes data the tool loads when it builds the pack.', '\n\nYa tienes {slug}: se sustituye por este.': '\n\nYou already have {slug}: it is replaced by this one.', '{slug}: importado. Pulsa Actualizar pack para instalarlo.': '{slug}: imported. Press Update pack to install it.', 'Importando {slug} (unos minutos)...': 'Importing {slug} (a few minutes)...', 'Hecho: pack instalado en Assetto Corsa Rally': 'Done: pack installed in Assetto Corsa Rally', 'No se ha podido completar (el pack instalado no ha cambiado). Mira los detalles.': 'It could not be completed (the installed pack has not changed). See the details.', 'quedan ~{t}': '~{t} left', '  sin imagen: la de por defecto  ': '  no image: the default one  ', 'Imágenes': 'Images', 'Elegir...': 'Choose...', 'Quitar': 'Remove', 'Tarjeta': 'Card', 'Fondo': 'Background', 'Lobby': 'Lobby', 'Logo': 'Logo', '{name} — nombre e imágenes': '{name} — name and images', 'Nombre en el menú': 'Name in the menu', 'Nombre de la variante': 'Variant name', '{name}: nombre e imágenes guardados (se aplican al exportar o con Actualizar pack)': '{name}: name and images saved (applied when exporting or with Update pack)', 'Se aplican al exportar el tramo o con Actualizar pack (sin exportar).': 'Applied when exporting the stage or with Update pack (no export).', '{country} — logo y descripción': '{country} — logo and description', 'La localización del juego con todos los tramos de este país.': "The game's location with all the stages of this country.", 'Descripción (Historia y curiosidades)': 'Description (History and trivia)', 'Vacío = el texto de siempre. Todos los tramos de este país comparten la descripción.': 'Empty = the usual text. All the stages of this country share the description.', 'Guardar': 'Save', 'Todos los archivos': 'All files', '{country}: descripción guardada (se aplica al exportar o con Actualizar pack)': '{country}: description saved (applied when exporting or with Update pack)', 'Se aplica al exportar o con Actualizar pack (sin exportar).': 'Applied when exporting or with Update pack (no export).', 'Preparando...': 'Preparing...', 'Preparando los archivos de WRC Generations...': 'Preparing the WRC Generations files...', 'Exportando {t} de WRC Generations...': 'Exporting {t} from WRC Generations...', 'Exportando {t} de WRC Generations: {step}...': 'Exporting {t} from WRC Generations: {step}...', 'Construyendo para Assetto Corsa Rally...': 'Building for Assetto Corsa Rally...', 'Reutilizando {t}...': 'Reusing {t}...', 'Construyendo {t}: {step}...': 'Building {t}: {step}...', 'Escribiendo las tablas del juego y las imágenes...': 'Writing the game tables and images...', 'Instalando en Assetto Corsa Rally...': 'Installing in Assetto Corsa Rally...', 'terminando': 'finishing', 'colisiones': 'collisions', 'nivel, salida y meta': 'level, start and finish', 'carretera y terreno': 'road and terrain', 'objetos': 'objects', 'vegetación': 'vegetation', 'detalles': 'details', 'guardando el nivel': 'saving the level', 'notas': 'pacenotes', 'carretera, objetos y colisiones': 'road, objects and collisions', 'terreno': 'terrain', 'texturas': 'textures', 'ajuste del terreno': 'terrain adjustment', 'vegetación y césped': 'vegetation and grass', 'Reinicia Stage Exporter para cambiar el idioma.': 'Restart Stage Exporter to change the language.'}


EN.update({
    'Liberar espacio…': 'Free up space…', 'Liberar espacio': 'Free up space',
    'No hay nada que liberar: ningún tramo construido en la caché.': 'Nothing to free: no built stage in the cache.',
    'Borra la caché de los tramos marcados. Se conservan sus nombres, imágenes y descripciones. Un tramo borrado sin copia .stage hay que exportarlo de nuevo (40 min o más); con copia, se importa en unos minutos. Los borrados salen del pack: pulsa Actualizar pack después.':
        'Deletes the cache of the ticked stages. Their names, images and descriptions are kept. A stage deleted without a .stage copy must be exported again (40 min or more); with a copy it imports in a few minutes. Deleted stages leave the pack: press Update pack afterwards.',
    '✔ tiene copia .stage': '✔ has a .stage copy', '⚠ SIN copia .stage': '⚠ NO .stage copy',
    'Se liberarían {gb:.1f} GB': '{gb:.1f} GB would be freed',
    'Sin copia .stage: {l}.\n\nSi los borras hay que exportarlos de nuevo. ¿Continuar?': 'No .stage copy: {l}.\n\nIf you delete them you must export them again. Continue?',
    'Borrar caché': 'Delete cache',
})


def T(es):
    """The Spanish text, or its English one when the window is in English."""
    return EN.get(es, es) if LANG == "en" else es


BG, PANEL, PANEL2, BORDER = "#0f1216", "#161a20", "#1c2129", "#272d36"
TEXT, MUTED, DIM = "#e8ebef", "#8b94a3", "#5b6472"
ACCENT, ACCENT_H, ACCENT_D = "#ff6b2c", "#ff8550", "#c94d17"
OK, WARN, DANGER = "#3ecf8e", "#f5b041", "#ef5350"

COUNTRY_ES = {"Spain": "Espa\u00f1a", "Greece": "Grecia", "Italy": "Italia", "France": "Francia", "Mexico": "M\u00e9xico",
              "Portugal": "Portugal", "Finland": "Finlandia", "Sweden": "Suecia", "Norway": "Noruega",
              "Estonia": "Estonia", "Croatia": "Croacia", "Japan": "Jap\u00f3n", "Kenya": "Kenia", "Chile": "Chile",
              "Argentina": "Argentina", "New Zealand": "Nueva Zelanda", "Belgium": "B\u00e9lgica",
              "Germany": "Alemania", "Turkey": "Turqu\u00eda", "Monaco": "M\u00f3naco", "Wales": "Gales",
              "United Kingdom": "Reino Unido"}
BETA = {"KE_KENYA", "BE_YPRES"}                      # levels still being tried: their stages show "(BETA)" in the list
SURFACE_ES = {"Tarmac": "asfalto", "Snow": "nieve", "Gravel": "tierra"}
REGION_ES = {"Sardinia": "Cerdeña", "Corsica": "Córcega", "Sanremo": "Sanremo"}


def _region(s):
    """'ITALY - SANREMO' -> 'Sanremo' (WRCG has two Italian rallies)."""
    c = str(s.get("country_en") or "")
    return c.split(" - ", 1)[1].strip().title() if " - " in c else ""


def _inventory():
    import wr_stages
    import tools.wrcg.stage_spec as ss
    rows = []
    for s in wr_stages.inventory():
        if s.get("category") != "rally_stage":
            continue
        L = (s.get("length_m") or {}).get("sections_cfg") or 0
        country = wr_stages.country_name(s.get("country_en"))
        rows.append({"id": s["id"], "slug": ss.slug(s["id"]),
                     "name": (s.get("stage_name_en") or s["id"]) + (" (BETA)" if s["location_folder"] in BETA else ""),
                     "ok": wr_stages.supported(s), "km": L / 1000.0,
                     "surface": SURFACE_ES.get(wr_stages.surface(s), "tierra"),
                     "loc": s["location_folder"], "rally": s.get("rally_name_en") or s["location_folder"],
                     "country": s.get("country_en") or "", "country_es": (COUNTRY_ES.get(country, country) if LANG == "es" else country)
                     + (("  ·  " + (REGION_ES.get(_region(s), _region(s)) if LANG == "es" else _region(s))) if _region(s) else ""),
                     "sss": s["location_folder"].startswith("SSS_")})
    return rows


def _has_build(slug):
    import tools.datafiles as df
    return bool(list(df.names(f"stage_builds/{slug}.json")))


def _clean(line):
    """Pipeline log lines without the original tool's name."""
    return re.sub(r"Sando Rally Stage Export Tool [\d.]+:?\s*", "Pack: ", str(line)).replace("Sando Rally", APP)


# --- progress from the pipeline's log --------------------------------------------------------------------------------

BUILD_STEPS = [("collision container", 0.05, "colisiones"), ("level shell, gameplay, marshal", 0.12, "nivel, salida y meta"),
               ("road layers + terrain tiles", 0.55, "carretera y terreno"), ("props", 0.72, "objetos"),
               ("vegetation", 0.80, "vegetación"), ("dressing, cloth, decals, water", 0.85, "detalles"),
               ("level save", 0.97, "guardando el nivel"), ("pacenotes", 1.0, "notas")]
WRCG_STEPS = [("export_stage.py", 0.05, "carretera, objetos y colisiones"), ("tools.wrcg.terrain export", 0.35, "terreno"),
              ("tools.wrcg.textures export", 0.5, "texturas"), ("ittiri_terrain adjust", 0.65, "ajuste del terreno"),
              ("vegetation_replay", 0.75, "vegetación y césped"), ("tools.wrcg.vegetation ", 0.75, "vegetación")]


class Progress:
    def __init__(self, again, pack, keep_wrcg, names, titles):
        self.names, self.titles = names, titles               # build name -> slug, slug -> display name
        self.w, self.f = {"prep": 2.0, "pack": 8.0}, {}
        n = max(len(again), 1)
        for s in pack:
            self.w[("wrcg", s)] = 25.0 / n if (s in again and not keep_wrcg) else 0.3
            self.w[("build", s)] = 62.0 / n if s in again else 1.0
        self.f = {k: 0.0 for k in self.w}
        self.label, self.t0, self.failed = T("Preparando..."), time.time(), False

    def _t(self, slug):
        return self.titles.get(slug, slug)

    def _set(self, key, v):
        if key in self.f:
            self.f[key] = max(self.f[key], v)

    def feed(self, line):
        l = line.strip()
        if l.startswith("WRCG files:"):
            self.f["prep"], self.label = 1.0, T("Preparando los archivos de WRC Generations...")
        m = re.match(r"^\[(\w+)\]\s*(.*)$", l)
        if m and ("wrcg", m.group(1)) in self.f:
            slug, rest = m.group(1), m.group(2)
            if "WRCG export kept" in rest or "WRCG export done" in rest:
                self._set(("wrcg", slug), 1.0)
            elif rest.startswith("WRCG export"):
                self._set(("wrcg", slug), 0.02)
                self.label = T("Exportando {t} de WRC Generations...").format(t=self._t(slug))
            for key, frac, es in WRCG_STEPS:
                if key in rest:
                    self._set(("wrcg", slug), frac)
                    self.label = T("Exportando {t} de WRC Generations: {step}...").format(t=self._t(slug), step=T(es))
        if "building the ACR pack" in l:
            for k in self.f:
                if k[0] == "wrcg":
                    self.f[k] = 1.0
            self.label = T("Construyendo para Assetto Corsa Rally...")
        m = re.search(r"\[(\w+)\] unchanged:", l)
        if m:
            self._set(("build", m.group(1)), 1.0)
            self.label = T("Reutilizando {t}...").format(t=self._t(m.group(1)))
        m = re.match(r"^building (\w+) \(", l)
        if m:
            self._set(("build", m.group(1)), 0.02)
            self.label = T("Construyendo {t}: {step}...").format(t=self._t(m.group(1)), step=T(BUILD_STEPS[0][2]))
        m = re.search(r"\[(Wrcg\w+)\] step (.+?): [\d.]+ s", l)
        if m and m.group(1) in self.names:
            slug = self.names[m.group(1)]
            for i, (key, frac, es) in enumerate(BUILD_STEPS):
                if m.group(2) == key:
                    self._set(("build", slug), frac)
                    nxt = BUILD_STEPS[i + 1][2] if i + 1 < len(BUILD_STEPS) else "terminando"
                    self.label = T("Construyendo {t}: {step}...").format(t=self._t(slug), step=T(nxt))
        m = re.search(r"\[(\w+)\] built in", l)
        if m:
            self._set(("build", m.group(1)), 1.0)
        if l.startswith("locations:") or l.startswith("menu images"):
            self._set("pack", 0.1)
            self.label = T("Escribiendo las tablas del juego y las imágenes...")
        if "tools.acrmod.install uninstall" in l:
            self._set("pack", 0.3)
            self.label = T("Instalando en Assetto Corsa Rally...")
        if "tools.acrmod.install install" in l:
            self._set("pack", 0.5)
        if l.startswith("installed wrcg_stages") or "installed into" in l:
            self._set("pack", 0.95)
        if l.startswith("pack:"):
            self._set("pack", 1.0)
        if "stage build failed" in l or l.startswith("ERROR"):
            self.failed = True

    def pct(self):
        tot = sum(self.w.values())
        return sum(self.w[k] * self.f[k] for k in self.w) / tot if tot else 0.0

    def eta(self):
        p, el = self.pct(), time.time() - self.t0
        return el * (1.0 - p) / p if p > 0.04 else None


def _short(stamp):
    """'2026-11-09 20:40' -> '09/11 20:40'."""
    m = re.match(r"\d{4}-(\d\d)-(\d\d) (\d\d:\d\d)", str(stamp or ""))
    return f"{m.group(2)}/{m.group(1)} {m.group(3)}" if m else (stamp or "")


def _fmt(sec):
    sec = int(sec)
    return f"{sec // 60} min {sec % 60:02d} s" if sec >= 60 else f"{sec} s"


# --- the window --------------------------------------------------------------------------------------------------------

class App:
    def __init__(self, root):
        import wr_pack
        self.pack = wr_pack
        self.root = root
        self.q = queue.Queue()
        self.busy = False
        self.progress = None
        self.preview = None
        root.title(APP)
        root.geometry("1280x800")
        root.minsize(1100, 680)
        root.configure(bg=BG)
        self._fonts()
        self._styles()
        self.stages = _inventory()
        self.by_id = {s["id"]: s for s in self.stages}
        self.locs = {}
        for s in self.stages:
            self.locs.setdefault(s["loc"], []).append(s)
        self._layout()
        self.fill_locations()
        root.after(150, self.pump)

    # --- look ---------------------------------------------------------------------------------------------------------
    def _fonts(self):
        fam = set(self.root.tk.splitlist(self.root.tk.call("font", "families")))   # (no tkinter.font in the bundle)
        pick = lambda *names: next((n for n in names if n in fam), "Segoe UI")
        self.f_ui = pick("Segoe UI Variable Text", "Segoe UI")
        self.f_head = pick("Bahnschrift", "Segoe UI Variable Display", "Segoe UI")
        self.f_mono = pick("Cascadia Mono", "Consolas")

    def _styles(self):
        st = ttk.Style(self.root)
        st.theme_use("clam")
        f = (self.f_ui, 10)
        st.configure(".", background=BG, foreground=TEXT, font=f, bordercolor=BORDER, focuscolor=ACCENT)
        st.configure("Treeview", background=PANEL, fieldbackground=PANEL, foreground=TEXT, rowheight=34, borderwidth=0,
                     font=(self.f_ui, 10))
        st.map("Treeview", background=[("selected", "#2a2f38")], foreground=[("selected", TEXT)])
        st.configure("Treeview.Heading", background=PANEL2, foreground=MUTED, relief="flat", borderwidth=0,
                     font=(self.f_ui, 9, "bold"), padding=(10, 8))
        st.map("Treeview.Heading", background=[("active", PANEL2)])
        st.layout("Treeview", [("Treeview.treearea", {"sticky": "nswe"})])
        st.configure("Vertical.TScrollbar", background=PANEL2, troughcolor=PANEL, bordercolor=PANEL, arrowcolor=MUTED,
                     relief="flat", gripcount=0)
        st.configure("Accent.Horizontal.TProgressbar", troughcolor=PANEL2, background=ACCENT, bordercolor=PANEL2,
                     lightcolor=ACCENT, darkcolor=ACCENT, thickness=10)
        for name, bg, fg, hov in (("Accent.TButton", ACCENT, "#ffffff", ACCENT_H), ("Ghost.TButton", PANEL2, TEXT, "#2a3039"),
                                  ("Danger.TButton", PANEL2, DANGER, "#2a3039")):
            st.configure(name, background=bg, foreground=fg, borderwidth=0, focusthickness=0, padding=(16, 9),
                         font=(self.f_ui, 10, "bold" if name == "Accent.TButton" else "normal"), relief="flat")
            st.map(name, background=[("disabled", "#2a2f36"), ("pressed", ACCENT_D if name == "Accent.TButton" else BORDER),
                                     ("active", hov)], foreground=[("disabled", DIM)])
        st.configure("TEntry", fieldbackground=PANEL2, foreground=TEXT, insertcolor=TEXT, bordercolor=BORDER, padding=6)

    def _label(self, parent, text="", size=10, color=TEXT, bold=False, head=False, bg=None, **kw):
        return tk.Label(parent, text=text, bg=bg or parent["bg"], fg=color,
                        font=(self.f_head if head else self.f_ui, size, "bold" if bold else "normal"), **kw)

    # --- layout -------------------------------------------------------------------------------------------------------
    def _layout(self):
        r = self.root
        head = tk.Frame(r, bg=BG, height=72)
        head.pack(fill="x", padx=22, pady=(16, 8))
        try:
            from PIL import Image, ImageTk
            ico = Image.open(_assets() / "stage_studio.ico").convert("RGBA").resize((40, 40), Image.LANCZOS)
            self._ico = ImageTk.PhotoImage(ico)
            tk.Label(head, image=self._ico, bg=BG).pack(side="left", padx=(0, 12))
        except Exception:
            pass
        tl = tk.Frame(head, bg=BG)
        tl.pack(side="left")
        self._label(tl, APP, 20, head=True, bold=True).pack(anchor="w")
        self._label(tl, SUB, 10, MUTED).pack(anchor="w")
        hr = tk.Frame(head, bg=BG)
        hr.pack(side="right")
        self.b_repack = ttk.Button(hr, text=T("Actualizar pack"), style="Ghost.TButton", command=self.repack)
        self.b_repack.pack(side="right")
        self.b_import = ttk.Button(hr, text=T("Importar tramo"), style="Accent.TButton", command=self.import_stage_file)
        self.b_import.pack(side="right", padx=(0, 8))
        ttk.Button(hr, text="English" if LANG == "es" else "Español", style="Ghost.TButton", command=self.toggle_lang).pack(
            side="right", padx=(0, 8))

        body = tk.Frame(r, bg=BG)
        body.pack(fill="both", expand=True, padx=22)
        # rallies
        left = tk.Frame(body, bg=PANEL, width=300, highlightthickness=1, highlightbackground=BORDER)
        left.pack(side="left", fill="y")
        left.pack_propagate(False)
        self._label(left, T("RALLIES"), 9, MUTED, bold=True).pack(anchor="w", padx=16, pady=(14, 6))
        self.loc_tv = ttk.Treeview(left, columns=("n",), show="tree", selectmode="browse")
        self.loc_tv.column("#0", width=230)
        self.loc_tv.column("n", width=44, anchor="e")
        self.loc_tv.tag_configure("pack", foreground=ACCENT)
        self.loc_tv.tag_configure("sss", foreground=MUTED)
        self.loc_tv.pack(fill="both", expand=True, padx=6)
        self.loc_tv.bind("<<TreeviewSelect>>", lambda e: self.show_stages())
        ttk.Button(left, text=T("Logo y descripción"), style="Ghost.TButton", command=self.location_images).pack(
            fill="x", padx=12, pady=12)
        # detail
        right = tk.Frame(body, bg=PANEL, width=340, highlightthickness=1, highlightbackground=BORDER)
        right.pack(side="right", fill="y")
        right.pack_propagate(False)
        self.card = tk.Label(right, bg=PANEL2)
        self.card.pack(fill="x", padx=14, pady=(14, 10))
        self.d_name = self._label(right, "", 17, head=True, bold=True, wraplength=290, justify="left")
        self.d_name.pack(anchor="w", padx=16)
        self.d_rally = self._label(right, "", 10, MUTED, wraplength=290, justify="left")
        self.d_rally.pack(anchor="w", padx=16)
        self.badges = tk.Frame(right, bg=PANEL)
        self.badges.pack(anchor="w", padx=14, pady=10)
        self.d_info = self._label(right, "", 10, MUTED, wraplength=290, justify="left")
        self.d_info.pack(anchor="w", padx=16)
        btns = tk.Frame(right, bg=PANEL)
        btns.pack(side="bottom", fill="x", padx=14, pady=14)
        self.b_export = ttk.Button(btns, text=T("Exportar tramo"), style="Accent.TButton", command=self.export)
        self.b_export.pack(fill="x")
        self.b_info = ttk.Button(btns, text=T("Nombre e imágenes"), style="Ghost.TButton", command=self.stage_info)
        self.b_info.pack(fill="x", pady=(8, 0))
        self.b_stagefile = ttk.Button(btns, text=T("Guardar como .stage"), style="Ghost.TButton",
                                      command=self.export_stage_file)
        self.b_stagefile.pack(fill="x", pady=(8, 0))
        self.b_remove = ttk.Button(btns, text=T("Quitar del pack"), style="Danger.TButton", command=self.remove)
        self.b_remove.pack(fill="x", pady=(8, 0))

        # stages
        mid = tk.Frame(body, bg=PANEL, highlightthickness=1, highlightbackground=BORDER)
        mid.pack(side="left", fill="both", expand=True, padx=14)
        self.title = self._label(mid, T("Tramos"), 15, head=True, bold=True)
        self.title.pack(anchor="w", padx=16, pady=(12, 0))
        self.subtitle = self._label(mid, "", 10, MUTED)
        self.subtitle.pack(anchor="w", padx=16, pady=(0, 8))
        cols = ("km", "surface", "pack", "last")
        self.st_tv = ttk.Treeview(mid, columns=cols, show="tree headings", selectmode="browse")
        for c, t, w, a in (("#0", T("TRAMO"), 200, "w"), ("km", T("KM"), 52, "e"), ("surface", T("SUPERFICIE"), 114, "w"),
                           ("pack", T("ESTADO"), 132, "w"), ("last", T("EXPORTADO"), 120, "w")):
            self.st_tv.heading(c, text=t, anchor=a)
            self.st_tv.column(c, width=w, anchor=a, stretch=c == "#0")
        self.st_tv.tag_configure("pack", foreground=ACCENT)
        self.st_tv.tag_configure("off", foreground=DIM)
        self.st_tv.pack(fill="both", expand=True, padx=6, pady=(0, 8))
        self.st_tv.bind("<<TreeviewSelect>>", lambda e: self.show_detail())
        self.st_tv.bind("<Button-1>", self.toggle_pack, add="+")
        self.st_tv.bind("<Double-1>", lambda e: None if self.st_tv.identify_column(e.x) == "#3" else self.export())
        # progress
        foot = tk.Frame(r, bg=PANEL, highlightthickness=1, highlightbackground=BORDER)
        foot.pack(fill="x", padx=22, pady=(14, 18))
        row1 = tk.Frame(foot, bg=PANEL)
        row1.pack(fill="x", padx=16, pady=(12, 6))
        self.p_label = self._label(row1, T("Listo"), 11, bold=True)
        self.p_label.pack(side="left")
        self.b_log = tk.Label(row1, text=T("Detalles") + " \u25be", bg=PANEL, fg=MUTED, cursor="hand2", font=(self.f_ui, 9))
        self.b_log.pack(side="right")
        self.b_log.bind("<Button-1>", lambda e: self.toggle_log())
        b_free = tk.Label(row1, text=T("Liberar espacio…"), bg=PANEL, fg=MUTED, cursor="hand2", font=(self.f_ui, 9))
        b_free.pack(side="right", padx=(0, 14))
        b_free.bind("<Button-1>", lambda e: self.free_space())
        self.b_cancel = ttk.Button(row1, text=T("Cancelar"), style="Danger.TButton", command=self.cancel)
        self.p_time = self._label(row1, "", 10, MUTED)
        self.p_time.pack(side="right", padx=12)
        self.bar = ttk.Progressbar(foot, style="Accent.Horizontal.TProgressbar", maximum=1000, mode="determinate")
        self.bar.pack(fill="x", padx=16, pady=(0, 6))
        self._label(foot, T("Creado por @AlbertPalahi, disponible en Patreon"), 9, DIM).pack(anchor="e", padx=16, pady=(0, 8))
        self.logf = tk.Frame(foot, bg=PANEL)
        self.log = tk.Text(self.logf, height=10, wrap="none", bg=BG, fg=MUTED, insertbackground=TEXT, relief="flat",
                           font=(self.f_mono, 9), highlightthickness=0, padx=10, pady=8)
        sb = ttk.Scrollbar(self.logf, command=self.log.yview, style="Vertical.TScrollbar")
        self.log.configure(yscrollcommand=sb.set)
        self.log.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.log_open = False

    # --- lists --------------------------------------------------------------------------------------------------------
    def fill_locations(self, keep=None):
        pack = set(self.pack.stages())
        self.loc_tv.delete(*self.loc_tv.get_children())
        order = sorted(self.locs, key=lambda k: (-sum(s["slug"] in pack for s in self.locs[k]),
                                                 self.locs[k][0]["sss"], self.locs[k][0]["country_es"]))
        for k in order:
            st = self.locs[k]
            n = sum(s["slug"] in pack for s in st)
            name = st[0]["country_es"] + (T("  ·  especial") if st[0]["sss"] else "")
            self.loc_tv.insert("", "end", iid=k, text="   " + name, values=(f"{n}/{len(st)}" if n else str(len(st)),),
                               tags=("pack",) if n else (("sss",) if st[0]["sss"] else ()))
        sel = keep or (order[0] if order else None)
        if sel:
            self.loc_tv.selection_set(sel)
            self.loc_tv.see(sel)

    def show_stages(self, keep=None):
        sel = self.loc_tv.selection()
        if not sel:
            return
        pack = set(self.pack.stages())
        st = sorted(self.locs[sel[0]], key=lambda s: s["id"])
        self.title.config(text=st[0]["country_es"])
        self.subtitle.config(text=st[0]["rally"])
        self.st_tv.delete(*self.st_tv.get_children())
        for s in st:
            inp = s["slug"] in pack
            built = bool(self.pack.built(s["slug"]))
            state = T("☑ en el pack") if inp else (T("☐ disponible") if built else (
                T("no soportado") if not s["ok"] else T("sin exportar")))
            last = _short(self.pack.last_built(s["slug"])) if built else ""
            self.st_tv.insert("", "end", iid=s["id"], text="   " + s["name"],
                              values=(f"{s['km']:.1f}", T(s["surface"]), state, last or ""),
                              tags=("pack",) if inp else (("off",) if not s["ok"] else ()))
        first = keep if keep and self.st_tv.exists(keep) else (st[0]["id"] if st else None)
        if first:
            self.st_tv.selection_set(first)
        self.show_detail()

    def selected(self):
        return [self.by_id[i] for i in self.st_tv.selection()]

    def show_detail(self):
        import wr_images
        sel = self.selected()
        for w in self.badges.winfo_children():
            w.destroy()
        if not sel:
            self.b_stagefile.state(["disabled"])
            return
        s = sel[0]
        inp = s["slug"] in set(self.pack.stages())
        self.d_name.config(text=s["name"])
        self.d_rally.config(text=f"{s['rally']}  \u00b7  {s['id']}")
        for txt, col in ((f"{s['km']:.1f} km", MUTED), (T(s["surface"]), {"asfalto": "#9aa7ff", "nieve": "#9ee7ff"}.get(s["surface"], WARN)),
                         ((T("en el pack"), OK) if inp else ((T("no soportado"), DANGER) if not s["ok"] else (T("nuevo"), MUTED)))):
            tk.Label(self.badges, text=f" {txt} ", bg=PANEL2, fg=col, font=(self.f_ui, 9, "bold"), padx=6, pady=3).pack(
                side="left", padx=(0, 6))
        last = self.pack.last_built(s["slug"]) if self.pack.built(s["slug"]) else None
        info = (T("Construido: {x}").format(x=_short(last)) if last else T("Aún no exportado")) if s["ok"] else \
            T("WRC Generations no tiene piezas de carretera en este tramo (la calle es parte de un objeto de la ciudad).")
        self.d_info.config(text=info)
        self._card(s, wr_images.find(wr_images.IMAGES / s["slug"], "card"))
        self.b_export.config(text=T("Exportar de nuevo") if inp else T("Exportar tramo"))
        self.b_export.state(["!disabled"] if s["ok"] and not self.busy else ["disabled"])
        self.b_remove.state(["!disabled"] if inp and not self.busy else ["disabled"])
        self.b_stagefile.state(["!disabled"] if self.pack.built(s["slug"]) and not self.busy else ["disabled"])

    def _card(self, s, path):
        from PIL import Image, ImageDraw, ImageFont, ImageTk
        W, H = 310, 120
        if path is not None:
            im = Image.open(path).convert("RGB")
            k = max(W / im.width, H / im.height)
            im = im.resize((int(im.width * k) + 1, int(im.height * k) + 1), Image.LANCZOS)
            x, y = (im.width - W) // 2, (im.height - H) // 2
            im = im.crop((x, y, x + W, y + H))
        else:
            im = Image.new("RGB", (W, H), (28, 33, 41))
            d = ImageDraw.Draw(im)
            for i in range(H):
                t = i / H
                d.line([(0, i), (W, i)], fill=(int(36 - 14 * t), int(42 - 16 * t), int(52 - 18 * t)))
            d.rectangle([0, H - 4, W, H], fill=(255, 107, 44))
            try:
                fnt = ImageFont.truetype("C:/Windows/Fonts/segoeuib.ttf", 22)
            except OSError:
                fnt = ImageFont.load_default()
            d.text((16, H - 44), s["name"].upper()[:24], font=fnt, fill=(232, 235, 239))
        self.preview = ImageTk.PhotoImage(im)
        self.card.config(image=self.preview)

    # --- actions ------------------------------------------------------------------------------------------------------
    def export(self):
        sel = self.selected()
        if not sel or self.busy:
            return
        s = sel[0]
        if not s["ok"]:
            messagebox.showwarning(APP, T("{name} no se puede exportar todavía.\n\nEn WRC Generations este tramo no tiene piezas de carretera (la calle es parte de un objeto de terreno de la ciudad).").format(name=s["name"]))
            return
        others = [p for p in self.pack.stages() if p != s["slug"]]
        if not messagebox.askyesno(APP, T("¿Exportar {name}?\n\nLos otros {n} tramos del pack se reutilizan tal como están. Al terminar se instala el pack en Assetto Corsa Rally.").format(name=s["name"], n=len(others))):
            return
        self.start(lambda: self._export([s]), again=[s["slug"]], pack=self.pack.stages() + ([] if s["slug"] in self.pack.stages() else [s["slug"]]))

    def _export(self, sel):
        import wr
        import wr_stages
        added = []
        for s in sel:
            if not _has_build(s["slug"]):
                wr_stages.add(s["id"])
                added.append(f"stage_builds/{s['slug']}.json")
        if added:
            wr.load_overlay(added)
        return self.pack.export([s["slug"] for s in sel], log=self.say)

    def remove(self):
        sel = [s for s in self.selected() if s["slug"] in self.pack.stages()]
        if not sel or self.busy:
            return
        rest = [p for p in self.pack.stages() if p != sel[0]["slug"]]
        if not messagebox.askyesno(APP, T("¿Quitar {name} del pack?\n\n").format(name=sel[0]["name"]) + (
                T("No se vuelve a construir ningún tramo; se instala el pack con el resto.") if rest else
                T("Es el único tramo del pack: se quita el pack del juego (cierra el juego antes)."))):
            return
        self.start(lambda: self.pack.remove([sel[0]["slug"]], log=self.say), again=[], pack=rest)

    def toggle_pack(self, e):
        """A click on the status of a built stage ticks it in / out of the pack (built by Actualizar pack)."""
        if self.busy or self.st_tv.identify_region(e.x, e.y) != "cell" or self.st_tv.identify_column(e.x) != "#3":
            return
        iid = self.st_tv.identify_row(e.y)
        s = self.by_id.get(iid)
        if not s or not self.pack.built(s["slug"]):
            return
        stages = self.pack.stages()
        self.pack.save([x for x in stages if x != s["slug"]] if s["slug"] in stages else stages + [s["slug"]])
        loc = self.loc_tv.selection()
        self.fill_locations(loc[0] if loc else None)
        self.show_stages(iid)

    def repack(self):
        if self.busy:
            return
        if not self.pack.stages():
            if messagebox.askyesno(APP, T("No hay ningún tramo marcado: ¿quitar el pack del juego?")):
                self.start(lambda: self.pack.uninstall_all(log=self.say), again=[], pack=[])
            return
        if messagebox.askyesno(APP, T("¿Rehacer el pack con los nombres e imágenes actuales?\n\nNo se exporta ningún tramo (aprox. 1 min) y se instala el pack.")):
            self.start(lambda: self.pack.run([], self.pack.stages(), log=self.say), again=[], pack=self.pack.stages())

    def free_space(self):
        """Dialog to delete the build cache (~3 GB each) of chosen stages; a stage with a .stage file next to the tool is safe."""
        import wr
        if self.busy:
            return
        rows = []
        for s in self.stages:
            n = self.pack.cache_bytes(s["slug"])
            if n:
                rows.append((s, n, (wr.ROOT / f"{s['slug']}.stage").exists()))
        if not rows:
            messagebox.showinfo(APP, T("No hay nada que liberar: ningún tramo construido en la caché."))
            return
        dlg = tk.Toplevel(self.root, bg=PANEL)
        dlg.title(T("Liberar espacio"))
        dlg.transient(self.root)
        dlg.grab_set()
        tk.Label(dlg, bg=PANEL, fg=TEXT, justify="left", font=(self.f_ui, 10), wraplength=520,
                 text=T("Borra la caché de los tramos marcados. Se conservan sus nombres, imágenes y descripciones. "
                        "Un tramo borrado sin copia .stage hay que exportarlo de nuevo (40 min o más); con copia, "
                        "se importa en unos minutos. Los borrados salen del pack: pulsa Actualizar pack después.")
                 ).pack(anchor="w", padx=18, pady=(16, 8))
        vars_ = []
        for s, n, has in rows:
            v = tk.BooleanVar(value=False)
            vars_.append((s["slug"], n, v))
            tk.Checkbutton(dlg, variable=v, bg=PANEL, fg=OK if has else WARN, selectcolor=BG, activebackground=PANEL,
                           activeforeground=TEXT, font=(self.f_ui, 10), anchor="w", command=lambda: total(),
                           text=f"{s['name']}   {n / 2 ** 30:.1f} GB   " +
                                (T("✔ tiene copia .stage") if has else T("⚠ SIN copia .stage"))
                           ).pack(fill="x", padx=18)
        lbl = tk.Label(dlg, bg=PANEL, fg=MUTED, font=(self.f_ui, 10))
        lbl.pack(anchor="w", padx=18, pady=(10, 4))

        def total():
            lbl.config(text=T("Se liberarían {gb:.1f} GB").format(gb=sum(n for _, n, v in vars_ if v.get()) / 2 ** 30))
        total()

        def go():
            sel = [(sl, n) for sl, n, v in vars_ if v.get()]
            if not sel:
                return
            risky = [sl for sl, _ in sel if not (wr.ROOT / f"{sl}.stage").exists()]
            if risky and not messagebox.askyesno(APP, T("Sin copia .stage: {l}.\n\nSi los borras hay que exportarlos de nuevo. ¿Continuar?").format(l=", ".join(risky)), parent=dlg):
                return
            dlg.destroy()
            self._file_job(lambda: self.pack.free_cache([sl for sl, _ in sel], log=self.say),
                           after=lambda: (self.fill_locations(), self.show_stages()))

        bt = tk.Frame(dlg, bg=PANEL)
        bt.pack(fill="x", padx=18, pady=(4, 16))
        ttk.Button(bt, text=T("Borrar caché"), style="Danger.TButton", command=go).pack(side="right")
        ttk.Button(bt, text=T("Cancelar"), style="Ghost.TButton", command=dlg.destroy).pack(side="right", padx=8)

    def _file_job(self, fn, after=None):
        """fn in a thread, the buttons off meanwhile; after() back in the window when it is done."""
        self.busy = True
        for b in (self.b_export, self.b_remove, self.b_repack, self.b_import, self.b_stagefile):
            b.state(["disabled"])

        def work():
            try:
                fn()
            except Exception as e:
                self.say(f"ERROR: {e}")
            finally:
                def end():
                    self.busy = False
                    for b in (self.b_export, self.b_remove, self.b_repack, self.b_import, self.b_stagefile):
                        b.state(["!disabled"])
                    if after:
                        after()
                self.root.after(0, end)

        threading.Thread(target=work, daemon=True).start()

    def export_stage_file(self):
        import wr
        import wr_stagefile
        sel = self.selected()
        if not sel or self.busy:
            return
        s = sel[0]
        if not self.pack.built(s["slug"]):
            messagebox.showinfo(APP, T("{name} todavía no está construido: expórtalo primero.").format(name=s["name"]))
            return
        f = filedialog.asksaveasfilename(defaultextension=".stage", initialfile=f"{s['slug']}.stage",
                                         filetypes=[(T("Tramo de Stage Exporter"), "*.stage")],
                                         initialdir=str(wr.ROOT))
        if f:
            self.say(T("{name}: guardando {f} (unos minutos, pesa varios GB)...").format(name=s["name"], f=f))
            self._file_job(lambda: wr_stagefile.export_stage(s["slug"], f, log=self.say))

    def import_stage_file(self):
        import wr
        import wr_stagefile
        if self.busy:
            return
        f = filedialog.askopenfilename(initialdir=str(wr.ROOT), filetypes=[(T("Tramo de Stage Exporter"), "*.stage"),
                                                                           (T("Todos los archivos"), "*.*")])
        if not f:
            return
        try:
            meta = wr_stagefile.peek(f)
        except Exception as e:
            messagebox.showerror(APP, T("Este fichero no es un tramo de Stage Exporter.\n\n{e}").format(e=e))
            return
        slug = meta["slug"]
        old = self.pack.keys().get(slug)
        if not messagebox.askyesno(APP, T("¿Importar el tramo {slug}?\n\nImporta solo ficheros de gente de confianza: el tramo incluye datos que la herramienta carga al construir el pack.").format(slug=slug)
                                        + (T("\n\nYa tienes {slug}: se sustituye por este.").format(slug=slug) if old else "")):
            return

        def after():
            wr.load_overlay([f"stage_builds/{slug}.json"])
            self.show_stages()
            self.say(T("{slug}: importado. Pulsa Actualizar pack para instalarlo.").format(slug=slug))

        self.say(T("Importando {slug} (unos minutos)...").format(slug=slug))
        self._file_job(lambda: wr_stagefile.import_stage(f, log=self.say), after)

    def toggle_lang(self):
        import wr
        (wr.CUSTOM / "lang.json").write_text(json.dumps({"lang": "en" if LANG == "es" else "es"}), encoding="utf-8")
        messagebox.showinfo(APP, T("Reinicia Stage Exporter para cambiar el idioma."))

    def cancel(self):
        if self.busy and messagebox.askyesno(APP, T("¿Cancelar la exportación?\n\nEl pack instalado se queda como estaba.")):
            import tools.exporter.pipeline as pl
            self.say("Cancelando...")
            pl.stop()

    def start(self, fn, again, pack):
        if self.busy:
            return
        import tools.datafiles as df
        names, titles = {}, {s["slug"]: s["name"] for s in self.stages}
        for n in df.names("stage_builds/*.json"):
            try:
                c = df.load_json(n)
                names[c["name"]] = c["slug"]
            except Exception:
                pass
        for s in self.stages:
            names.setdefault(f"Wrcg_{s['slug']}", s["slug"])
        self.progress = Progress(again, pack, bool(os.environ.get("WR_KEEP_WRCG")), names, titles)
        self.busy = True
        self.log.delete("1.0", "end")
        for b in (self.b_export, self.b_remove, self.b_repack):
            b.state(["disabled"])
        self.b_cancel.pack(side="right", padx=(12, 0))
        self.bar["value"] = 0
        t0 = time.time()
        # every run's details also go to work/logs/stagestudio_<date>.log (to send when something goes wrong)
        try:
            logs = Path(__file__).resolve().parents[1] / "work" / "logs"
            logs.mkdir(parents=True, exist_ok=True)
            self.logpath = logs / f"stagestudio_{time.strftime('%Y%m%d_%H%M%S')}.log"
        except Exception:
            self.logpath = None

        def work():
            try:
                self.say(f"Stage Exporter: {time.strftime('%Y-%m-%d %H:%M:%S')}, pack {pack}, exported again {again}")
                out = fn()
                self.say(f"result: {out!r}")
                self.q.put(("done", bool(out), time.time() - t0))
            except BaseException as e:
                import traceback
                self.say(traceback.format_exc())
                self.q.put(("log", f"ERROR: {e!r}"))
                self.q.put(("done", False, time.time() - t0))

        threading.Thread(target=work, daemon=True).start()

    def say(self, line):
        lines = [_clean(l) for l in str(line).splitlines()]
        for l in lines:
            self.q.put(("log", l))
        if getattr(self, "logpath", None):
            try:
                with open(self.logpath, "a", encoding="utf-8") as f:
                    f.write("\n".join(lines) + "\n")
            except OSError:
                pass

    def toggle_log(self):
        self.log_open = not self.log_open
        if self.log_open:
            self.logf.pack(fill="both", padx=16, pady=(0, 14))
            self.b_log.config(text=T("Detalles") + " \u25b4")
        else:
            self.logf.pack_forget()
            self.b_log.config(text=T("Detalles") + " \u25be")

    def pump(self):
        try:
            for _ in range(400):
                m = self.q.get_nowait()
                if m[0] == "log":
                    self.log.insert("end", m[1] + "\n")
                    self.log.see("end")
                    if self.progress:
                        self.progress.feed(m[1])
                else:
                    self.finish(m[1], m[2])
        except queue.Empty:
            pass
        if self.busy and self.progress:
            p = self.progress
            self.bar["value"] = int(p.pct() * 1000)
            eta = p.eta()
            self.p_label.config(text=p.label, fg=TEXT)
            self.p_time.config(text=f"{p.pct():.0%}  \u00b7  {_fmt(time.time() - p.t0)}"
                                    + ("  \u00b7  " + T("quedan ~{t}").format(t=_fmt(eta)) if eta else ""))
        self.root.after(200, self.pump)

    def finish(self, ok, secs):
        self.busy = False
        self.b_cancel.pack_forget()
        self.b_repack.state(["!disabled"])
        if ok:
            self.bar["value"] = 1000
            self.p_label.config(text=T("Hecho: pack instalado en Assetto Corsa Rally"), fg=OK)
        else:
            self.p_label.config(text=T("No se ha podido completar (el pack instalado no ha cambiado). Mira los detalles."),
                                fg=DANGER)
            if not self.log_open:
                self.toggle_log()
        self.p_time.config(text=_fmt(secs))
        keep_loc = self.loc_tv.selection()
        keep_st = self.st_tv.selection()
        self.fill_locations(keep_loc[0] if keep_loc else None)
        self.show_stages(keep_st[0] if keep_st else None)

    # --- names and images ---------------------------------------------------------------------------------------------
    def _dialog(self, title):
        dlg = tk.Toplevel(self.root, bg=PANEL)
        dlg.title(title)
        dlg.transient(self.root)
        try:
            dlg.iconbitmap(str(_assets() / "stage_studio.ico"))
        except Exception:
            pass
        return dlg

    def _slot_row(self, dlg, r, label, folder, slot, size):
        import wr_images
        from PIL import Image, ImageTk
        self._label(dlg, label, 10, bold=True).grid(row=r, column=0, sticky="w", padx=16, pady=6)
        self._label(dlg, f"{size[0]} x {size[1]}", 9, MUTED).grid(row=r, column=0, sticky="sw", padx=16)
        pv = tk.Label(dlg, bg=PANEL2, fg=MUTED, font=(self.f_ui, 9))
        pv.grid(row=r, column=1, sticky="w", padx=8, pady=6)

        def show():
            p = wr_images.find(folder, slot)
            if p is None:
                pv.configure(image="", text=T("  sin imagen: la de por defecto  "), width=36, height=4)
                return
            im = Image.open(p)
            im.thumbnail((300, 110))
            pv.image = ImageTk.PhotoImage(im)
            pv.configure(image=pv.image, text="", width=0, height=0)

        def pick():
            f = filedialog.askopenfilename(parent=dlg, title=label,
                                           filetypes=[(T("Imágenes"), "*.png *.jpg *.jpeg *.webp *.bmp")])
            if f:
                wr_images.store(f, folder, slot, size)
                show()
                self.show_detail()

        def clear():
            p = wr_images.find(folder, slot)
            if p is not None:
                p.unlink()
            show()
            self.show_detail()

        ttk.Button(dlg, text=T("Elegir..."), style="Ghost.TButton", command=pick).grid(row=r, column=2, padx=4)
        ttk.Button(dlg, text=T("Quitar"), style="Ghost.TButton", command=clear).grid(row=r, column=3, padx=(4, 16))
        show()

    def stage_info(self):
        import wr
        import wr_images
        import wr_stages
        import tools.datafiles as df
        sel = self.selected()
        if not sel:
            return
        s = sel[0]
        if not _has_build(s["slug"]):
            wr_stages.add(s["id"])
            wr.load_overlay([f"stage_builds/{s['slug']}.json"])
        cfg = df.load_json(f"stage_builds/{s['slug']}.json")
        dlg = self._dialog(T("{name} — nombre e imágenes").format(name=s["name"]))
        self._label(dlg, s["name"], 16, head=True, bold=True).grid(row=0, column=0, columnspan=4, sticky="w", padx=16, pady=(14, 4))
        self._label(dlg, T("Nombre en el menú"), 10, MUTED).grid(row=1, column=0, sticky="w", padx=16, pady=4)
        e_track = ttk.Entry(dlg, width=52)
        e_track.insert(0, cfg.get("track_name") or "")
        e_track.grid(row=1, column=1, columnspan=3, sticky="we", padx=(8, 16))
        self._label(dlg, T("Nombre de la variante"), 10, MUTED).grid(row=2, column=0, sticky="w", padx=16, pady=4)
        e_stage = ttk.Entry(dlg, width=52)
        e_stage.insert(0, cfg.get("stage_name") or "")
        e_stage.grid(row=2, column=1, columnspan=3, sticky="we", padx=(8, 16))
        folder = wr_images.IMAGES / s["slug"]
        if s["slug"].endswith("r"):                    # a reverse (es_ss1r) opens with its forward stage's images
            import shutil
            base = wr_images.IMAGES / s["slug"][:-1]
            for slot in wr_images.SLOTS:
                src = wr_images.find(base, slot)
                if src and not wr_images.find(folder, slot):
                    folder.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, folder / src.name)
        for r, (slot, label) in enumerate((("card", T("Tarjeta")), ("background", T("Fondo")), ("lobby", T("Lobby"))), start=3):
            self._slot_row(dlg, r, label, folder, slot, wr_images.SLOTS[slot])

        def save():
            p = wr.CUSTOM / "data" / "stage_builds" / f"{s['slug']}.json"
            data = json.loads(p.read_text(encoding="utf-8")) if p.exists() else dict(cfg)
            data["track_name"], data["stage_name"] = e_track.get().strip(), e_stage.get().strip()
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
            wr.load_overlay([f"stage_builds/{s['slug']}.json"])
            dlg.destroy()
            self.say(T("{name}: nombre e imágenes guardados (se aplican al exportar o con Actualizar pack)").format(name=s["name"]))

        self._label(dlg, T("Se aplican al exportar el tramo o con Actualizar pack (sin exportar)."), 9, MUTED).grid(
            row=6, column=0, columnspan=3, sticky="w", padx=16, pady=(8, 14))
        ttk.Button(dlg, text=T("Guardar"), style="Accent.TButton", command=save).grid(row=6, column=3, sticky="e",
                                                                                  padx=16, pady=(8, 14))

    def location_images(self):
        import wr_images
        sel = self.loc_tv.selection()
        if not sel:
            return
        st = self.locs[sel[0]][0]
        row = wr_images.location_row(st["country"])
        import wr_stages
        country = wr_stages.country_name(st["country"])
        dlg = self._dialog(T("{country} — logo y descripción").format(country=st["country_es"]))
        self._label(dlg, f"[MOD] {country}", 16, head=True, bold=True).grid(row=0, column=0, columnspan=4, sticky="w",
                                                                              padx=16, pady=(14, 0))
        self._label(dlg, T("La localización del juego con todos los tramos de este país."), 10, MUTED).grid(
            row=1, column=0, columnspan=4, sticky="w", padx=16, pady=(0, 6))
        for r, (slot, label) in enumerate((("logo", T("Logo")), ("background", T("Fondo"))), start=2):
            self._slot_row(dlg, r, label, wr_images.IMAGES / row, slot, wr_images.LOC_SLOTS[slot])
        self._label(dlg, T("Descripción (Historia y curiosidades)"), 10, bold=True).grid(
            row=4, column=0, columnspan=4, sticky="w", padx=16, pady=(8, 2))
        txt = tk.Text(dlg, width=62, height=7, wrap="word", bg=PANEL2, fg=TEXT, insertbackground=TEXT, relief="flat",
                      font=(self.f_ui, 10))
        txt.insert("1.0", wr_images.location_text(row) or "")
        txt.grid(row=5, column=0, columnspan=4, sticky="we", padx=16)
        self._label(dlg, T("Vacío = el texto de siempre. Todos los tramos de este país comparten la descripción."),
                    9, MUTED).grid(row=6, column=0, columnspan=4, sticky="w", padx=16, pady=(2, 0))

        def save():
            wr_images.set_location_text(row, txt.get("1.0", "end").strip())
            dlg.destroy()
            self.say(T("{country}: descripción guardada (se aplica al exportar o con Actualizar pack)").format(country=country))

        self._label(dlg, T("Se aplica al exportar o con Actualizar pack (sin exportar)."), 9, MUTED).grid(
            row=7, column=0, columnspan=3, sticky="w", padx=16, pady=(8, 14))
        ttk.Button(dlg, text=T("Guardar"), style="Accent.TButton", command=save).grid(row=7, column=3, sticky="e",
                                                                                  padx=16, pady=(8, 14))


def _assets():
    return Path(__file__).resolve().parent / "wr_assets"


def main():
    import sys
    import wr
    import tools.exporter.pipeline as pl
    w, a = wr._installs()
    os.environ.update({k: v for k, v in pl._env(w, a, None).items() if k not in os.environ})
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("StageStudio.WRCG2ACR")
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    root = tk.Tk()
    try:
        ico = _assets() / "stage_studio.ico"
        if not ico.exists():
            import wr_images
            wr_images.app_icon(ico)
        root.iconbitmap(str(ico))
    except Exception:
        pass
    app = App(root)

    class _Out:                                     # print() of the hooks into the window's details too
        def __init__(self, stream):
            self.stream = stream

        def write(self, s):
            for line in str(s).splitlines():
                if line.strip():
                    app.say(line)
            if self.stream:
                try:
                    self.stream.write(s)
                except Exception:
                    pass

        def flush(self):
            if self.stream:
                try:
                    self.stream.flush()
                except Exception:
                    pass

    sys.stdout = _Out(sys.stdout)
    root.mainloop()
    return 0
