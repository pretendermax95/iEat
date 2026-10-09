import urllib.request, xml.etree.ElementTree as ET, hashlib, zipfile, os
from pathlib import Path
root=Path(os.environ.get('IEAT_TOOLCHAIN','/workspace/android-toolchain'))
root.mkdir(parents=True,exist_ok=True)
with urllib.request.urlopen('https://dl.google.com/android/repository/repository2-1.xml',timeout=30) as r:xml=ET.fromstring(r.read())
for package,target in [('build-tools;35.0.0','build-tools'),('platforms;android-35','platform')]:
 p=next(p for p in xml.findall('remotePackage') if p.get('path')==package)
 archives=p.find('archives').findall('archive');a=next(a for a in archives if a.findtext('host-os') in (None,'linux'))
 complete=a.find('complete');url='https://dl.google.com/android/repository/'+complete.findtext('url');check=complete.find('checksum');dest=root/(target+'.zip')
 print('Downloading',package,flush=True)
 with urllib.request.urlopen(url,timeout=120) as r,dest.open('wb') as f:
  while chunk:=r.read(1024*1024):f.write(chunk)
 actual=hashlib.new(check.get('type','sha1'),dest.read_bytes()).hexdigest();assert actual==check.text.strip(),(actual,check.text)
 print('Checksum verified',package,flush=True)
 with zipfile.ZipFile(dest) as z:z.extractall(root/target)
url='https://repo.maven.apache.org/maven2/org/eclipse/jdt/ecj/3.40.0/ecj-3.40.0.jar'
with urllib.request.urlopen(url,timeout=30) as r:data=r.read()
with urllib.request.urlopen(url+'.sha1',timeout=30) as r:expected=r.read().decode().strip()
assert hashlib.sha1(data).hexdigest()==expected
(root/'ecj.jar').write_bytes(data)
print('Compiler verified',flush=True)
