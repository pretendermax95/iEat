#!/usr/bin/env python3
import json, os, sqlite3, hashlib, secrets, time, re
from pathlib import Path
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from http.cookies import SimpleCookie
from urllib.parse import unquote, urlparse
import threading

AUTH_ATTEMPTS = {}
AUTH_LOCK = threading.Lock()

ROOT = Path(__file__).resolve().parent
DB = Path(os.environ.get('IEAT_DB', str(ROOT / 'data/ieat.sqlite3')))
DB.parent.mkdir(parents=True, exist_ok=True)
def connect():
    c = sqlite3.connect(DB, timeout=20)
    c.row_factory = sqlite3.Row
    c.execute('PRAGMA foreign_keys=ON')
    return c
with connect() as c:
    c.executescript('''CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, name TEXT NOT NULL, email TEXT UNIQUE NOT NULL, phone TEXT NOT NULL, address TEXT NOT NULL, password TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY,user_id INTEGER REFERENCES users(id),expires REAL);
    CREATE TABLE IF NOT EXISTS orders(id INTEGER PRIMARY KEY,user_id INTEGER REFERENCES users(id),items TEXT,total INTEGER,address TEXT,phone TEXT,note TEXT,status TEXT DEFAULT 'Принят',created TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS partners(id INTEGER PRIMARY KEY,name TEXT,phone TEXT,restaurant TEXT,created TEXT DEFAULT CURRENT_TIMESTAMP);''')

photos = ['photo-1568901346375-23c9450c58cd','photo-1628840042765-356cda07504e','photo-1579871494447-9811cf80d66c','photo-1612929633738-8fe44f7ec841','photo-1550547660-d9450f859349','photo-1574071318508-1cdbab80d002','photo-1571877227200-a0d98ea607e9','photo-1569718212165-3a8278d5f624']
raw = [('BBQ Burger','Говядина, хрустящий салат и фирменный соус',25,'burger',1,320),('Пепперони','Пепперони, моцарелла и томатный соус',50,'pizza',2,450),('Калифорния','Лосось, авокадо и сливочный сыр',40,'sushi',3,240),('Вок с курицей','Лапша, курица и свежие овощи',36,'asian',4,350),('Чизбургер','Говядина, двойной сыр и маринованный огурец',29,'burger',1,300),('Маргарита','Моцарелла, томаты и свежий базилик',43,'pizza',2,420),('Тирамису','Нежный маскарпоне, кофе и какао',25,'dessert',2,150),('Рамен','Ароматный бульон, лапша и курица',38,'asian',4,400)]
DISHES = [dict(id=i+1,name=r[0],description=r[1],price=r[2],category=r[3],restaurant=r[4],weight=r[5],image='/images/'+str(i+1)+'.svg') for i,r in enumerate(raw)]
RESTAURANTS = [dict(id=i+1,name=n,cuisine=t,rating=rating,time=tm,image=DISHES[im]['image']) for i,(n,t,rating,tm,im) in enumerate([('Burger Lab','Бургеры · Американская',4.9,'25–35',0),('Pizza Casa','Пицца · Итальянская',4.8,'30–40',1),('Sushi Time','Суши · Японская',4.9,'35–45',2),('Wok House','Лапша · Азиатская',4.7,'25–40',7)])]
def password_hash(p, salt=None):
    salt = salt or secrets.token_hex(16)
    return salt+':'+hashlib.scrypt(p.encode(),salt=salt.encode(),n=16384,r=8,p=1).hex()
def public_user(u): return {k:u[k] for k in ('id','name','email','phone','address')}
class Handler(SimpleHTTPRequestHandler):
    def __init__(self,*a,**kw): super().__init__(*a,directory=str(ROOT),**kw)
    def log_message(self,fmt,*args): pass
    def reply(self,data,status=200,cookie=None):
        body=json.dumps(data,ensure_ascii=False).encode()
        self.send_response(status); self.send_header('Content-Type','application/json; charset=utf-8'); self.send_header('Cache-Control','no-store')
        if cookie: self.send_header('Set-Cookie',cookie)
        self.end_headers(); self.wfile.write(body)
    def user(self,c):
        cookie=SimpleCookie()
        try: cookie.load(self.headers.get('Cookie',''))
        except Exception: return None
        token=cookie.get('ieat_session')
        return c.execute('SELECT u.* FROM users u JOIN sessions s ON u.id=s.user_id WHERE s.token=? AND s.expires>?',(token.value if token else '',time.time())).fetchone()
    def do_GET(self):
        if self.path=='/api/catalog': return self.reply(dict(dishes=DISHES,restaurants=RESTAURANTS,demo=True))
        if self.path in ('/api/me','/api/orders'):
            with connect() as c:
                u=self.user(c)
                if self.path=='/api/me': return self.reply(dict(user=public_user(u) if u else None))
                if not u: return self.reply({'error':'Войдите в аккаунт'},401)
                rows=c.execute('SELECT * FROM orders WHERE user_id=? ORDER BY id DESC',(u['id'],)).fetchall()
                return self.reply([dict(dict(r),items=json.loads(r['items'])) for r in rows])
        if self.path.startswith('/api/'): return self.reply({'error':'Не найдено'},404)
        path=unquote(urlparse(self.path).path)
        target=(ROOT / path.lstrip('/')).resolve()
        allowed = path in ('/','/index.html') or (target.is_relative_to(ROOT) and target.is_file() and any(target.is_relative_to(ROOT/folder) for folder in ('css','js','images')))
        if not allowed:
            return self.reply({'error':'Не найдено'},404)
        return super().do_GET()
    def do_POST(self):
        try:
            origin=self.headers.get('Origin')
            if (origin and urlparse(origin).netloc != self.headers.get('Host')) or self.headers.get('Sec-Fetch-Site')=='cross-site': return self.reply({'error':'Запрос отклонён'},403)
            length=int(self.headers.get('Content-Length',0))
            if length>32768: return self.reply({'error':'Запрос слишком большой'},413)
            data=json.loads(self.rfile.read(length))
            if not isinstance(data,dict): raise ValueError()
            with connect() as c:
                u=self.user(c)
                if self.path in ('/api/register','/api/login'):
                    with AUTH_LOCK:
                        now=time.time(); client=self.client_address[0]
                        for key in list(AUTH_ATTEMPTS):
                            if not AUTH_ATTEMPTS[key] or AUTH_ATTEMPTS[key][-1]<now-900: del AUTH_ATTEMPTS[key]
                        attempts=[t for t in AUTH_ATTEMPTS.get(client,[]) if t>now-900]
                        if len(attempts)>=30: return self.reply({'error':'Слишком много попыток. Повторите через 15 минут'},429)
                        AUTH_ATTEMPTS[client]=attempts+[now]
                    email=str(data.get('email','')).strip().lower(); p=str(data.get('password',''))
                    if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',email) or not 8<=len(p)<=128: return self.reply({'error':'Введите email и пароль от 8 до 128 символов'},400)
                    if self.path=='/api/register':
                        name=str(data.get('name','')).strip()
                        if not 2<=len(name)<=80: return self.reply({'error':'Имя должно содержать от 2 до 80 символов'},400)
                        try: c.execute('INSERT INTO users(name,email,phone,address,password) VALUES(?,?,?,?,?)',(name,email,'','',password_hash(p)))
                        except sqlite3.IntegrityError: return self.reply({'error':'Этот email уже зарегистрирован'},409)
                    u=c.execute('SELECT * FROM users WHERE email=?',(email,)).fetchone()
                    if not u or not secrets.compare_digest(u['password'],password_hash(p,u['password'].split(':')[0])): return self.reply({'error':'Неверный email или пароль'},401)
                    token=secrets.token_urlsafe(32); c.execute('INSERT INTO sessions VALUES(?,?,?)',(token,u['id'],time.time()+604800)); c.commit()
                    return self.reply({'user':public_user(u)},cookie=f'ieat_session={token}; HttpOnly; SameSite=Lax; Path=/; Max-Age=604800')
                if self.path=='/api/logout':
                    cookie=SimpleCookie(); cookie.load(self.headers.get('Cookie','')); token=cookie.get('ieat_session')
                    if token: c.execute('DELETE FROM sessions WHERE token=?',(token.value,))
                    c.commit(); return self.reply({'ok':True},cookie='ieat_session=; HttpOnly; SameSite=Lax; Path=/; Max-Age=0')
                if self.path=='/api/partners':
                    fields=[str(data.get(k,'')).strip() for k in ('name','phone','restaurant')]
                    if not all(fields) or not re.fullmatch(r'\+?[\d\s()-]{9,20}',fields[1]) or any(len(x)>150 for x in fields): return self.reply({'error':'Заполните название, имя и корректный телефон'},400)
                    c.execute('INSERT INTO partners(name,phone,restaurant) VALUES(?,?,?)',fields); c.commit(); return self.reply({'ok':True},201)
                if not u: return self.reply({'error':'Войдите в аккаунт'},401)
                if self.path=='/api/profile':
                    fields=[str(data.get(k,'')).strip() for k in ('name','phone','address')]
                    if not 2<=len(fields[0])<=80 or not re.fullmatch(r'\+?[\d\s()-]{9,20}',fields[1]) or not 5<=len(fields[2])<=300: return self.reply({'error':'Проверьте имя, телефон и адрес'},400)
                    c.execute('UPDATE users SET name=?,phone=?,address=? WHERE id=?',(*fields,u['id'])); c.commit(); return self.reply({'user':public_user(c.execute('SELECT * FROM users WHERE id=?',(u['id'],)).fetchone())})
                if self.path=='/api/orders':
                    items=data.get('items',[]); address=str(data.get('address','')).strip(); phone=str(data.get('phone','')).strip(); note=str(data.get('note','')).strip()
                    if not isinstance(items,list) or not 1<=len(items)<=30 or not 5<=len(address)<=300 or not re.fullmatch(r'\+?[\d\s()-]{9,20}',phone) or len(note)>500: return self.reply({'error':'Проверьте корзину, адрес и телефон'},400)
                    checked=[]; seen=set()
                    for item in items:
                        if not isinstance(item,dict): raise ValueError()
                        dish=next((d for d in DISHES if d['id']==item.get('id')),None); qty=item.get('qty')
                        if not dish or type(qty) is not int or not 1<=qty<=20 or dish['id'] in seen: return self.reply({'error':'Некорректное количество блюда'},400)
                        seen.add(dish['id']); checked.append(dict(id=dish['id'],name=dish['name'],price=dish['price'],qty=qty))
                    subtotal=sum(i['price']*i['qty'] for i in checked); total=subtotal+(0 if subtotal>=150 else 15)
                    cur=c.execute('INSERT INTO orders(user_id,items,total,address,phone,note) VALUES(?,?,?,?,?,?)',(u['id'],json.dumps(checked,ensure_ascii=False),total,address,phone,note)); c.commit()
                    return self.reply({'id':cur.lastrowid,'total':total,'status':'Принят'},201)
                if self.path=='/api/orders/cancel':
                    cur=c.execute("UPDATE orders SET status='Отменён' WHERE id=? AND user_id=? AND status='Принят'",(data.get('id'),u['id'])); c.commit()
                    if not cur.rowcount: return self.reply({'error':'Заказ не найден или уже отменён'},409)
                    return self.reply({'ok':True})
                return self.reply({'error':'Не найдено'},404)
        except (ValueError,TypeError,KeyError): return self.reply({'error':'Некорректные данные'},400)
        except Exception: return self.reply({'error':'Ошибка сервера. Попробуйте позже'},500)
if __name__=='__main__':
    port=int(os.environ.get('PORT','8000'))
    print(f'iEat running on port {port}',flush=True)
    ThreadingHTTPServer(('0.0.0.0',port),Handler).serve_forever()
