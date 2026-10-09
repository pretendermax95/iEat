"""Validate the development APK in an already booted Android emulator.
Requires Python websockets and SDK platform-tools. Clears emulator app data.
Never run on a user's physical device.
"""
import asyncio,json,os,subprocess,time,urllib.request,uuid
from pathlib import Path
import websockets
ADB=os.environ.get('IEAT_ADB','/workspace/android-toolchain/sdk/platform-tools/adb')
SERIAL=os.environ.get('IEAT_EMULATOR','emulator-5554')
assert SERIAL.startswith('emulator-'),'Test only supports isolated emulators'
def adb(*args,check=True):return subprocess.run([ADB,'-s',SERIAL,*args],capture_output=True,text=True,check=check).stdout.strip()
base=Path(__file__).resolve().parents[2]
apk=base/'releases/iEat-1.0.0-debug.apk'
for _ in range(900):
 if adb('shell','getprop','sys.boot_completed',check=False)=='1':break
 time.sleep(1)
else:raise RuntimeError('Emulator did not finish booting')
print('Android booted',flush=True)
adb('install','-r',str(apk));adb('shell','pm','clear','com.ieat.app');adb('shell','am','start','-n','com.ieat.app/.MainActivity')
for _ in range(120):
 sockets=adb('shell','cat','/proc/net/unix')
 names=[line.split()[-1].lstrip('@') for line in sockets.splitlines() if 'webview_devtools_remote_' in line]
 if names:break
 time.sleep(1)
else:raise RuntimeError('WebView did not start')
adb('forward','tcp:9222','localabstract:'+names[0])
for _ in range(60):
 try:
  with urllib.request.urlopen('http://127.0.0.1:9222/json') as r:targets=json.loads(r.read())
  if targets:break
 except OSError:pass
 time.sleep(1)
async def test():
 async with websockets.connect(targets[0]['webSocketDebuggerUrl'],max_size=10_000_000) as ws:
  sequence=0
  async def evaluate(expression):
   nonlocal sequence
   sequence+=1;identifier=sequence
   await ws.send(json.dumps({'id':identifier,'method':'Runtime.evaluate','params':{'expression':expression,'returnByValue':True,'awaitPromise':True}}))
   while True:
    result=json.loads(await ws.recv())
    if result.get('id')==identifier:
     if 'error' in result or 'exceptionDetails' in result.get('result',{}):raise AssertionError(result)
     return result['result']['result'].get('value')
  for _ in range(100):
   if await evaluate("document.querySelectorAll('.dish').length===8"):break
   await asyncio.sleep(.2)
  else:raise AssertionError('Catalog did not load')
  assert await evaluate("typeof window.IEatNative.request==='function'")
  await evaluate("document.querySelector('[data-category=pizza]').click()")
  assert await evaluate("document.querySelectorAll('.dish').length")==2
  await evaluate("reset();add(1);add(1);add(2)")
  assert await evaluate("document.getElementById('cartCount').textContent")=='3'
  await evaluate("openAuth('register')")
  email='android-'+uuid.uuid4().hex+'@example.com'
  await evaluate("document.querySelector('[name=name]').value='Android Test';document.querySelector('[name=email]').value="+json.dumps(email)+";document.querySelector('[name=password]').value='android-password-2026';document.querySelector('#authForm').requestSubmit()")
  for _ in range(100):
   if await evaluate("user!==null"):break
   await asyncio.sleep(.1)
  assert await evaluate('user.name')=='Android Test'
  await evaluate("checkout();document.querySelector('[name=address]').value='Худжанд, тестовый дом 10';document.querySelector('[name=phone]').value='+992900000000';document.querySelector('#checkoutForm').requestSubmit()")
  for _ in range(100):
   if await evaluate("document.querySelector('#viewOrders')!==null"):break
   await asyncio.sleep(.1)
  assert await evaluate("document.querySelector('#viewOrders')!==null")
  assert await evaluate("(async()=>{const o=await api('orders');return o[0].total})()") ==115
  assert await evaluate("(async()=>{let o=await api('orders');await api('orders/cancel',{id:o[0].id});o=await api('orders');return o[0].status})()")=='Отменён'
  assert await evaluate("(async()=>{const r=await api('profile',{name:'Mobile User',phone:'+992900000000',address:'Худжанд, тестовая улица 15'});user=r.user;return user.name})()")=='Mobile User'
  await evaluate("api('partners',{name:'Test',phone:'+992900000000',restaurant:'Android Restaurant'})")
  await evaluate("api('logout',{})")
  await asyncio.sleep(1)
  assert await evaluate("(async()=>{try{await api('login',{email:"+json.dumps(email)+",password:'wrong-password'});return false}catch(e){return e.message.includes('Неверный')}})()")
  await asyncio.sleep(1)
  assert await evaluate("(async()=>{const r=await api('login',{email:"+json.dumps(email)+",password:'android-password-2026'});user=r.user;return user.name})()")=='Mobile User'
  await evaluate("modal.close();profileButton();window.scrollTo(0,0)")
  assert await evaluate('document.documentElement.scrollWidth<=window.innerWidth')
  assert await evaluate('Array.from(document.images).every(i=>i.complete&&i.naturalWidth>0)')
  print('PASS: Android catalog, filters, cart, native registration/login, local orders, totals, cancellation, profile, partners, mobile layout',flush=True)
asyncio.run(test())
subprocess.run([ADB,'-s',SERIAL,'shell','screencap','-p','/sdcard/ieat.png'],check=True)
subprocess.run([ADB,'-s',SERIAL,'pull','/sdcard/ieat.png','/workspace/artifacts/ieat-android.png'],check=True)
