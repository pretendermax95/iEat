import unittest, subprocess, tempfile, os, socket, time, urllib.request, urllib.error, http.cookiejar, json
from pathlib import Path

class API(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory()
        with socket.socket() as s:s.bind(('127.0.0.1',0));port=s.getsockname()[1]
        cls.base=f'http://127.0.0.1:{port}'
        root=Path(__file__).resolve().parents[1]
        cls.proc=subprocess.Popen(['python3',str(root/'server.py')],env={**os.environ,'PORT':str(port),'IEAT_DB':cls.tmp.name+'/test.sqlite3'},stdout=subprocess.DEVNULL)
        for _ in range(100):
            try:urllib.request.urlopen(cls.base+'/api/catalog',timeout=1);break
            except (OSError,urllib.error.URLError):time.sleep(.05)
        else:raise RuntimeError('Server did not start')
    @classmethod
    def tearDownClass(cls):cls.proc.terminate();cls.proc.wait(timeout=5);cls.tmp.cleanup()
    def setUp(self):self.client=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()),urllib.request.ProxyHandler({}))
    def request(self,path,data=None,client=None):
        req=urllib.request.Request(self.base+path,data=json.dumps(data).encode() if data is not None else None,headers={'Content-Type':'application/json'} if data is not None else {})
        try:r=(client or self.client).open(req);return r.status,json.loads(r.read())
        except urllib.error.HTTPError as e:return e.code,json.loads(e.read())
    def register(self,email='a@example.com'):
        return self.request('/api/register',{'name':'Test User','email':email,'password':'long-test-password'})
    def test_01_catalog_and_private_files(self):
        status,data=self.request('/api/catalog');self.assertEqual(status,200);self.assertEqual(len(data['dishes']),8)
        for path in ['/server.py','/data/ieat.sqlite3','/images/../server.py','/images/%2e%2e/data/ieat.sqlite3','/images/']:
            self.assertEqual(self.request(path)[0],404,path)
    def test_02_authentication(self):
        self.assertEqual(self.request('/api/orders')[0],401)
        self.assertEqual(self.register('auth@example.com')[0],200)
        self.assertEqual(self.register('auth@example.com')[0],409)
        self.assertEqual(self.request('/api/logout',{})[0],200)
        self.assertIsNone(self.request('/api/me')[1]['user'])
        self.assertEqual(self.request('/api/login',{'email':'auth@example.com','password':'bad-password'})[0],401)
        self.assertEqual(self.request('/api/login',{'email':'auth@example.com','password':'long-test-password'})[0],200)
    def test_03_orders_totals_and_ownership(self):
        self.register('orders@example.com')
        body={'items':[{'id':1,'qty':2,'price':1}],'address':'Test Street 10','phone':'+992900000000','note':'test','total':1}
        status,o=self.request('/api/orders',body);self.assertEqual(status,201);self.assertEqual(o['total'],65)
        outsider=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()),urllib.request.ProxyHandler({}))
        self.request('/api/register',{'name':'Other','email':'other@example.com','password':'long-test-password'},outsider)
        self.assertEqual(self.request('/api/orders',client=outsider)[1],[])
        self.assertEqual(self.request('/api/orders/cancel',{'id':o['id']},outsider)[0],409)
        self.assertEqual(self.request('/api/orders/cancel',{'id':o['id']})[0],200)
        self.assertEqual(self.request('/api/orders')[1][0]['status'],'Отменён')
        body['items']=[{'id':2,'qty':3}];self.assertEqual(self.request('/api/orders',body)[1]['total'],150)
    def test_04_validation(self):
        self.register('validation@example.com')
        body={'address':'Test Street 10','phone':'+992900000000'}
        for items in [[],[{'id':1,'qty':0}],[{'id':1,'qty':21}],[{'id':99,'qty':1}],[{'id':1,'qty':True}],[{'id':1,'qty':1},{'id':1,'qty':1}]]:
            self.assertEqual(self.request('/api/orders',{**body,'items':items})[0],400)
        self.assertEqual(self.request('/api/profile',{'name':'A','phone':'bad','address':'X'})[0],400)
        self.assertEqual(self.request('/api/partners',{'name':'Test','phone':'bad','restaurant':'Test'})[0],400)
    def test_05_profile_and_partners(self):
        self.register('profile@example.com')
        status,data=self.request('/api/profile',{'name':'New Name','phone':'+992900000000','address':'New Street 15'})
        self.assertEqual(status,200);self.assertEqual(data['user']['name'],'New Name')
        self.assertEqual(self.request('/api/me')[1]['user']['address'],'New Street 15')
        self.assertEqual(self.request('/api/partners',{'name':'Partner','phone':'+992900000000','restaurant':'Restaurant'})[0],201)

if __name__=='__main__':unittest.main()
