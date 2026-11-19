"""Updater checks, no network and no real installation writes."""
import hashlib,io,json,tempfile,zipfile
from pathlib import Path
import wr_update as u

def main():
 assert u.version('v1.5') < u.version('1.6') < u.version('v1.10')
 for invalid in ['../1.7','v1.7-rc','x']:
  try:u.version(invalid)
  except ValueError:pass
  else:raise AssertionError(invalid)
 def archive(files):
  stream=io.BytesIO()
  with zipfile.ZipFile(stream,'w') as z:
   for name,data in files.items():z.writestr(name,data)
  return stream.getvalue()
 with tempfile.TemporaryDirectory() as tmp:
  root=Path(tmp);(root/'custom').mkdir();(root/'custom/user.json').write_text('mine')
  payload=archive({'Stage Exporter/payload/_internal/wr_update.py':'VERSION="1.7"',
                   'Stage Exporter/payload/custom/user.json':'new default',
                   'Stage Exporter/payload/custom/new.json':'{}'})
  def asset(data):return {'browser_download_url':'unused','size':len(data),'digest':'sha256:'+hashlib.sha256(data).hexdigest()}
  u.request=lambda url:io.BytesIO(payload)
  u.install(asset(payload),root)
  assert (root/'custom/user.json').read_text()=='mine'
  assert (root/'custom/new.json').read_text()=='{}'
  assert (root/'_internal/wr_update.py').exists()
  for bad in ['../escape.py','Stage Exporter/payload/_internal/../../escape.py','Stage Exporter/payload/_internal/evil.exe']:
   payload=archive({bad:'bad'});u.request=lambda url:io.BytesIO(payload)
   try:u.install(asset(payload),root)
   except ValueError:pass
   else:raise AssertionError(bad)
  payload=archive({'Stage Exporter/payload/_internal/wr_update.py':'VERSION="9"'});u.request=lambda url:io.BytesIO(payload)
  bad=asset(payload);bad['digest']='sha256:'+'0'*64
  try:u.install(bad,root)
  except ValueError:pass
  else:raise AssertionError('digest')
  assert (root/'_internal/wr_update.py').read_text()=='VERSION="1.7"'
  payload=archive({'Stage Exporter/payload/_internal/wr_update.py':'VERSION="9"','Stage Exporter/payload/_internal/wr_new.py':'x=1'})
  u.request=lambda url:io.BytesIO(payload)
  copy=u.shutil.copy2
  def fail_copy(src,dest):
   if Path(dest)==root/'_internal/wr_new.py':raise OSError('simulated copy failure')
   return copy(src,dest)
  u.shutil.copy2=fail_copy
  try:
   try:u.install(asset(payload),root)
   except OSError:pass
   else:raise AssertionError('rollback not exercised')
  finally:u.shutil.copy2=copy
  assert (root/'_internal/wr_update.py').read_text()=='VERSION="1.7"'
  assert not (root/'_internal/wr_new.py').exists()
  u.request=lambda url:io.BytesIO(json.dumps({'tag_name':'v1.5','assets':[]}).encode())
  assert u.latest() is None
  u.request=lambda url:io.BytesIO(json.dumps({'tag_name':'v1.7','assets':[{'name':'Stage-Exporter-v1.7.zip','size':10,'browser_download_url':'https://evil.example/test'}]}).encode())
  try:u.latest()
  except ValueError:pass
  else:raise AssertionError('asset URL')
 print('Updater: version comparison, settings preservation, new defaults, archive paths, file allowlist, checksum, release URL OK')
 return 0

