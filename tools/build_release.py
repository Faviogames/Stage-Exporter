"""Build the direct manual ZIP and the compatibility ZIP required by the published 1.6 updater."""
import json,zipfile
from pathlib import Path

def main():
 repo=Path(__file__).resolve().parents[1]
 scope={};exec((repo/'payload/_internal/wr_update.py').read_text(encoding='utf-8-sig'),scope)
 tag='v'+scope['VERSION'];out=repo.parent/'release';out.mkdir(exist_ok=True)
 for p in (repo/'payload').rglob('*.py'):compile(p.read_text(encoding='utf-8-sig'),str(p),'exec')
 for p in (repo/'payload/custom').rglob('*.json'):json.loads(p.read_text(encoding='utf-8-sig'))
 for suffix,prefix in [('-Instalar',''),('','Stage Exporter/')]:
  dest=out/f'Stage-Exporter-{tag}{suffix}.zip'
  with zipfile.ZipFile(dest,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
   for source,name in [('INSTALAR.bat','INSTALAR.bat'),('README_INSTALLER.txt','PUT ME INSIDE SANDO.EXE.txt'),('QUICK_GUIDE.txt','QUICK_GUIDE.txt')]:
    z.write(repo/source,prefix+name)
   for p in sorted((repo/'payload').rglob('*')):
    if p.is_file() and '__pycache__' not in p.parts and p.suffix not in ('.pyc','.bak') and not (prefix and p.relative_to(repo/'payload').parts[0]=='bin'):   # 1.6.x updaters reject payload/bin: only the manual ZIP carries it
     z.write(p,prefix+p.relative_to(repo).as_posix())
  with zipfile.ZipFile(dest) as z:assert z.testzip() is None
  print(dest.name,dest.stat().st_size,'bytes')
 return 0
