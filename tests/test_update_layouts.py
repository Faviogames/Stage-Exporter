import io,hashlib,tempfile,zipfile
from pathlib import Path
import wr_update as u

def main():
 def pack(files):
  b=io.BytesIO()
  with zipfile.ZipFile(b,'w') as z:
   for n,text in files.items():z.writestr(n,text)
  return b.getvalue()
 def asset(data):return {'browser_download_url':'unused','size':len(data),'digest':'sha256:'+hashlib.sha256(data).hexdigest()}
 for prefix in ['payload/','Stage Exporter/payload/']:
  data=pack({prefix+'_internal/wr_update.py':'VERSION="9"',prefix+'custom/user.json':'{}'})
  u.request=lambda url:io.BytesIO(data)
  with tempfile.TemporaryDirectory() as t:
   root=Path(t);(root/'custom').mkdir();(root/'custom/user.json').write_text('mine')
   u.install(asset(data),root)
   assert (root/'_internal/wr_update.py').exists() and (root/'custom/user.json').read_text()=='mine'
 for files in [{'payload/_internal/../../evil.py':'bad'},{'payload/_internal/evil.exe':'bad'}, {'payload/_internal/wr_update.py':'x=1','Stage Exporter/payload/_internal/wr_update.py':'x=2'}]:
  data=pack(files);u.request=lambda url:io.BytesIO(data)
  with tempfile.TemporaryDirectory() as t:
   try:u.install(asset(data),Path(t))
   except ValueError:pass
   else:raise AssertionError(files)
 print('Flat and legacy formats, user settings, path and duplicate rejection OK')
 return 0
