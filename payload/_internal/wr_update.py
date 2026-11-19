"""GitHub release check on every launch; updates only our add-on, preserving user settings."""
import hashlib
import json
import os
import queue
import re
import shutil
import subprocess
import tempfile
import threading
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath

VERSION = '1.6.1'
REPO = 'Faviogames/Stage-Exporter'
API = f'https://api.github.com/repos/{REPO}/releases/latest'
MAX_ZIP = 50 * 1024 * 1024


def version(tag):
    if not re.fullmatch(r'v?\d+(?:\.\d+)*', str(tag)):
        raise ValueError('Unsupported release version')
    parts = tuple(map(int, tag.lstrip('v').split('.')))
    return parts + (0,) * max(0, 3 - len(parts))


def request(url):
    return urllib.request.urlopen(urllib.request.Request(url, headers={
        'User-Agent': 'Stage-Exporter/' + VERSION, 'Accept': 'application/vnd.github+json'}), timeout=12)


def latest():
    with request(API) as response:
        data = json.loads(response.read(1024 * 1024))
    if data.get('draft') or data.get('prerelease') or version(data['tag_name']) <= version(VERSION):
        return None
    names = [f"Stage-Exporter-{data['tag_name']}-Instalar.zip", f"Stage-Exporter-{data['tag_name']}.zip"]
    asset = next(a for name in names for a in data.get('assets', []) if a['name'] == name)
    expected = f"https://github.com/{REPO}/releases/download/{data['tag_name']}/{asset['name']}"
    if asset.get('browser_download_url') != expected or not 0 < asset['size'] <= MAX_ZIP:
        raise ValueError('Invalid update asset')
    return asset


def install(asset, root):
    """Stage and validate the entire archive, then copy with rollback on failure."""
    with tempfile.TemporaryDirectory(prefix='StageExporter-update-') as tmp:
        tmp = Path(tmp)
        archive = tmp / 'update.zip'
        with request(asset['browser_download_url']) as response, archive.open('wb') as out:
            total = 0
            while block := response.read(65536):
                total += len(block)
                if total > MAX_ZIP:
                    raise ValueError('Update too large')
                out.write(block)
        if total != asset['size']:
            raise ValueError('Incomplete download')
        digest = asset.get('digest') or ''
        if not re.fullmatch(r'sha256:[a-fA-F0-9]{64}', digest):
            raise ValueError('GitHub SHA-256 digest missing')
        if hashlib.sha256(archive.read_bytes()).hexdigest() != digest[7:].lower():
            raise ValueError('Update checksum mismatch')
        staged = []
        seen = set()
        with zipfile.ZipFile(archive) as z:
            if sum(i.file_size for i in z.infolist()) > MAX_ZIP * 3:
                raise ValueError('Expanded update too large')
            for info in z.infolist():
                p = PurePosixPath(info.filename)
                if p.is_absolute() or '..' in p.parts or '\\' in info.filename or ':' in info.filename:
                    raise ValueError('Unsafe update path')
                if info.is_dir():
                    continue
                parts = p.parts[1:] if p.parts[:1] == ('Stage Exporter',) else p.parts
                if len(parts) < 3 or parts[0] != 'payload':
                    continue
                rel = Path(*parts[1:])
                if parts[1] not in ('_internal', 'custom'):
                    raise ValueError('Unexpected update folder')
                if parts[1] == '_internal' and not (
                    len(parts) == 3 and p.name.startswith('wr') and p.suffix == '.py'
                    or parts[2] == 'wr_assets' and p.suffix in ('.ico', '.cs', '.png')):
                    raise ValueError('Unexpected add-on file')
                if parts[1] == 'custom' and p.suffix != '.json':
                    if p.name == 'LEEME.txt':
                        continue
                    raise ValueError('Unexpected settings file')
                dest = root / rel
                if not dest.resolve().is_relative_to(root.resolve()):
                    raise ValueError('Update escapes installation')
                key = str(rel).casefold()
                if key in seen:
                    raise ValueError('Duplicate update file')
                seen.add(key)
                if parts[1] == 'custom' and dest.exists():
                    continue
                src = tmp / 'new' / rel
                src.parent.mkdir(parents=True, exist_ok=True)
                src.write_bytes(z.read(info))
                if src.suffix == '.py':
                    compile(src.read_text(encoding='utf-8-sig'), str(rel), 'exec')
                staged.append((src, dest, tmp / 'backup' / rel))
        if not any(dest == root / '_internal' / 'wr_update.py' for _, dest, _ in staged):
            raise ValueError('Missing updater in release')
        changed = []
        try:
            for src, dest, backup in staged:
                existed = dest.exists()
                if existed:
                    backup.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(dest, backup)
                changed.append((dest, backup, existed))
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dest)
        except Exception:
            for dest, backup, existed in reversed(changed):
                if existed:
                    shutil.copy2(backup, dest)
                else:
                    dest.unlink(missing_ok=True)
            raise


def start(root, app, lang):
    import tkinter as tk
    from tkinter import messagebox
    es = lang == 'es'
    events = queue.Queue()
    progress = None
    close_handler = root.protocol('WM_DELETE_WINDOW')

    def check():
        try:
            events.put(('available', latest()))
        except Exception as exc:
            events.put(('check_failed', str(exc)))

    def update(asset):
        try:
            install(asset, Path(__file__).resolve().parent.parent)
            events.put(('installed', None))
        except Exception as exc:
            events.put(('failed', str(exc)))

    def poll():
        nonlocal progress
        try:
            kind, data = events.get_nowait()
        except queue.Empty:
            root.after(250, poll)
            return
        if kind == 'available' and data:
            if app.busy:
                events.put((kind, data))
                root.after(1000, poll)
                return
            text = (f"Hay una actualización disponible: {data['name']}.\n\n¿Instalarla y reiniciar? Tus ajustes y tramos se conservan." if es else
                    f"An update is available: {data['name']}.\n\nInstall and restart? Your settings and stages will be preserved.")
            if messagebox.askyesno('Stage Exporter', text, parent=root):
                app.busy = True
                root.protocol('WM_DELETE_WINDOW', lambda: None)
                progress = tk.Toplevel(root)
                progress.title('Stage Exporter')
                progress.transient(root)
                progress.protocol('WM_DELETE_WINDOW', lambda: None)
                tk.Label(progress, text='Actualizando, espera...' if es else 'Updating, please wait...', padx=30, pady=25).pack()
                progress.grab_set()
                app.say('Descargando actualización...' if es else 'Downloading update...')
                threading.Thread(target=update, args=(data,), daemon=True).start()
                root.after(250, poll)
        elif kind == 'installed':
            try:
                subprocess.Popen([str(Path(__file__).resolve().parent / 'wrcg2acr-worker.exe'), '-m', 'wr', 'ui'],
                                 cwd=str(Path(__file__).resolve().parent.parent), creationflags=subprocess.CREATE_NO_WINDOW)
            except Exception as exc:
                app.busy = False
                progress.destroy()
                root.protocol('WM_DELETE_WINDOW', close_handler)
                messagebox.showerror('Stage Exporter', str(exc), parent=root)
            else:
                root.destroy()
        elif kind == 'failed':
            app.busy = False
            progress.destroy()
            root.protocol('WM_DELETE_WINDOW', close_handler)
            messagebox.showerror('Stage Exporter', ('No se pudo actualizar: ' if es else 'Update failed: ') + data, parent=root)
        elif kind == 'check_failed':
            app.say(('No se pudo comprobar GitHub: ' if es else 'Could not check GitHub: ') + data)

    threading.Thread(target=check, daemon=True).start()
    root.after(250, poll)
