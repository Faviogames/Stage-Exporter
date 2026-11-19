import io,json,hashlib,tempfile,zipfile,subprocess
from pathlib import Path
import wr_update as current

def main():
 repo=Path('Stage-Exporter').resolve()
 source=subprocess.check_output(['git','-c','safe.directory='+str(repo),'-C',str(repo),'show','v1.6:payload/_internal/wr_update.py'],encoding='utf-8')
 old={};exec(source,old)
 assert old['VERSION']=='1.6' and current.VERSION=='1.6.1'
 assets=[];downloads={}
 for suffix in ['', '-Instalar']:
  name='Stage-Exporter-v1.6.1'+suffix+'.zip';data=Path('release',name).read_bytes()
  url='https://github.com/Faviogames/Stage-Exporter/releases/download/v1.6.1/'+name
  downloads[url]=data;assets.append({'name':name,'size':len(data),'digest':'sha256:'+hashlib.sha256(data).hexdigest(),'browser_download_url':url})
  with zipfile.ZipFile(io.BytesIO(data)) as z:
   top={p.split('/')[0] for p in z.namelist()}
   assert top==({'payload','INSTALAR.bat','PUT ME INSIDE SANDO.EXE.txt','QUICK_GUIDE.txt'} if suffix else {'Stage Exporter'})
 meta=json.dumps({'tag_name':'v1.6.1','assets':assets}).encode()
 def request(url):return io.BytesIO(meta if url==current.API else downloads[url])
 old['request']=request;current.request=request
 legacy_asset=old['latest']();assert legacy_asset['name']=='Stage-Exporter-v1.6.1.zip'
 with tempfile.TemporaryDirectory() as tmp:
  root=Path(tmp);(root/'work').mkdir();(root/'work/keep.txt').write_text('stage cache');(root/'custom').mkdir();(root/'custom/pack.json').write_text('my stages')
  old['install'](legacy_asset,root)
  assert (root/'_internal/wr_update.py').read_bytes()==Path('_internal/wr_update.py').read_bytes()
  new={};exec((root/'_internal/wr_update.py').read_text(encoding='utf-8-sig'),new)
  new['VERSION']='1.6';new['request']=request
  flat_asset=new['latest']();assert flat_asset['name'].endswith('-Instalar.zip')
  new['install'](flat_asset,root)
  assert (root/'custom/pack.json').read_text()=='my stages'
  assert (root/'work/keep.txt').read_text()=='stage cache'
  for p in Path('Stage-Exporter/payload/_internal').glob('wr*.py'):assert (root/'_internal'/p.name).read_bytes()==p.read_bytes()
 print('Published 1.6 updater -> 1.6.1 compatibility ZIP -> flat ZIP: OK; all modules and user data preserved')
 return 0
