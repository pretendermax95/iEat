"""Run against a local iEat server: IEAT_URL=http://127.0.0.1:8000 python3 tests/smoke.py."""
import os, uuid, shutil
from playwright.sync_api import sync_playwright
base=os.environ.get('IEAT_URL','http://127.0.0.1:8000')
with sync_playwright() as p:
 browser=p.chromium.launch(headless=True,executable_path=shutil.which('chromium'),args=['--no-sandbox'])
 context=browser.new_context(viewport={'width':1440,'height':1000})
 page=context.new_page(); errors=[]
 page.on('pageerror',lambda e:errors.append(str(e)))
 page.goto(base); page.wait_for_selector('.dish')
 assert page.locator('.dish').count()==8
 page.locator('[data-category="pizza"]').click(); assert page.locator('.dish').count()==2
 page.locator('#resetFilters').click();page.locator('#searchInput').fill('рамен');assert page.locator('.dish').count()==1
 page.locator('#resetFilters').click();page.locator('[data-favorite="1"]').click();page.locator('[data-category="favorites"]').click();assert page.locator('.dish').count()==1
 page.reload();page.wait_for_selector('.dish');assert page.locator('[data-favorite="1"]').get_attribute('aria-pressed')=='true'
 page.locator('[data-restaurant="1"]').click();assert page.locator('.dish').count()==2
 page.locator('#resetFilters').click();page.locator('.dish [data-add="1"]').click();page.locator('.dish [data-add="2"]').click()
 page.locator('#cartBtn').click();page.locator('[data-quantity="1"][data-delta="1"]').click();assert page.locator('#cartCount').inner_text()=='3'
 page.locator('#toCheckout').click();page.locator('#registerTab').click()
 email='smoke-'+uuid.uuid4().hex+'@example.com'
 page.locator('[name=name]').fill('Тестовый клиент');page.locator('[name=email]').fill(email);page.locator('[name=password]').fill('test-password-2026');page.locator('#authForm button[type=submit]').click()
 page.wait_for_selector('#checkoutForm');page.locator('[name=address]').fill('Худжанд, улица Ленина, дом 10');page.locator('[name=phone]').fill('+992 900000000');page.locator('[name=note]').fill('Позвонить у подъезда');page.locator('#checkoutForm button[type=submit]').click()
 page.wait_for_selector('#viewOrders');assert '115 с.' in page.locator('#modalContent').inner_text();assert page.locator('#cartCount').inner_text()=='0'
 page.locator('#viewOrders').click();page.wait_for_selector('[data-cancel]');page.locator('[data-cancel]').click();page.wait_for_function("document.querySelector('.badge')?.textContent==='Отменён'")
 page.locator('[data-repeat]').click();assert page.locator('#cartCount').inner_text()=='3';page.locator('#closeModal').click()
 page.locator('#profileBtn').click();page.locator('[name=name]').fill('Обновлённое имя');page.locator('[name=phone]').fill('+992 900000000');page.locator('[name=address]').fill('Худжанд, улица 20');page.locator('#profileForm button[type=submit]').click();page.wait_for_function("document.querySelector('#profileBtn').textContent==='Обновлённое имя'")
 page.locator('#logout').click();page.wait_for_function("document.querySelector('#profileBtn').textContent==='Войти'")
 page.locator('#profileBtn').click();page.locator('[name=email]').fill(email);page.locator('[name=password]').fill('wrong-password');page.locator('#authForm button[type=submit]').click();page.wait_for_function("document.querySelector('.error').textContent==='Неверный email или пароль'")
 page.locator('[name=password]').fill('test-password-2026');page.locator('#authForm button[type=submit]').click();page.wait_for_function("!document.querySelector('#modal').open")
 page.locator('#partnerBtn').click();page.locator('[name=restaurant]').fill('Тестовый ресторан');page.locator('[name=name]').fill('Партнёр');page.locator('[name=phone]').fill('+992 900000000');page.locator('#partnerForm button[type=submit]').click();page.wait_for_function("document.querySelector('#modalContent').textContent.includes('Заявка сохранена')");page.locator('#closeModal').click()
 page.reload();page.wait_for_selector('.dish');assert page.locator('#cartCount').inner_text()=='3';assert page.locator('#profileBtn').inner_text()=='Обновлённое имя'
 assert page.evaluate("Array.from(document.images).every(i=>i.complete&&i.naturalWidth>0)")
 page.screenshot(path='/tmp/ieat-desktop.png',full_page=True)
 page.set_viewport_size({'width':390,'height':844});page.screenshot(path='/tmp/ieat-mobile.png',full_page=True)
 assert page.evaluate('document.documentElement.scrollWidth<=window.innerWidth')
 page.locator('#cartBtn').click();assert page.locator('#toCheckout').is_visible();page.keyboard.press('Escape');assert not page.locator('#modal').evaluate('(el)=>el.open')
 other=browser.new_context();r=other.request.get(base+'/api/orders');assert r.status==401
 assert other.request.get(base+'/server.py').status==404
 assert context.request.post(base+'/api/orders',data={'items':[{'id':1,'qty':-1}],'address':'Худжанд, дом 10','phone':'+992900000000'}).status==400
 assert not errors,errors
 browser.close()
 print('PASS: catalog, search, filters, favorites, cart, registration, checkout, cancellation, repeat, profile, login, partner, persistence, mobile, access controls')
