import requests, re
from bs4 import BeautifulSoup
import os, json, time

# === НАСТРОЙКИ ===
# РЕКОМЕНДУЕМЫЙ ВАРИАНТ: берём из Secrets (добавишь на шаге 4)
TOKEN = os.environ["TELEGRAM_TOKEN"]
CHAT_ID = os.environ["CHAT_ID"]
URLS = os.environ.get("URLS","").split()  # ссылки через пробел

# ЕСЛИ ХОЧЕШЬ ПРОСТО ПРОВЕРИТЬ (НЕБЕЗОПАСНО): раскомментируй 3 строки ниже и поставь свои значения
# TOKEN = "123456:ABC..."      # токен бота от @BotFather
# CHAT_ID = "123456789"        # твой chat_id от @userinfobot
# URLS = ["https://www.dns-shop.ru/product/i1000779/"]  # можно список ссылок

STATE = "last.json"  # тут хранится прошлое значение цен

def send(msg):
    requests.post(
        f"https://api.telegram.org/bot{TOKEN}/sendMessage",
        json={"chat_id": CHAT_ID, "text": msg, "disable_web_page_preview": True},
        timeout=20
    )

def price_from_html(html):
    import json, re
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")

    # 1) <meta itemprop="price" content="...">
    meta = soup.find("meta", {"itemprop": "price"})
    if meta and meta.get("content"):
        try:
            return float(str(meta["content"]).replace(",", "."))
        except:
            pass

    # 2) JSON-LD со структурой offers / price
    for tag in soup.find_all("script", {"type": "application/ld+json"}):
        try:
            data = json.loads(tag.string or "{}")
            items = data if isinstance(data, list) else [data]
            for obj in items:
                if not isinstance(obj, dict):
                    continue
                # Вложенные offers могут быть dict или list
                offers = obj.get("offers")
                if isinstance(offers, dict):
                    p = offers.get("price") or offers.get("lowPrice") or offers.get("highPrice")
                    if p:
                        return float(str(p).replace(",", "."))
                elif isinstance(offers, list):
                    for off in offers:
                        if isinstance(off, dict):
                            p = off.get("price") or off.get("lowPrice") or off.get("highPrice")
                            if p:
                                return float(str(p).replace(",", "."))
        except:
            continue

    # 3) Явный блок цены на странице (часто бывает .product-buy__price)
    block = soup.select_one(".product-buy__price, .product-card-top__buy .price__current, .price__current")
    if block:
        txt = block.get_text(" ", strip=True)
        m = re.search(r"(\d[\d\s.,]{2,})", txt)
        if m:
            num = m.group(1).replace("\xa0", "").replace(" ", "").replace(",", ".")
            try:
                return float(num)
            except:
                pass

    # 4) Фоллбэк: ищем число рядом со словами про цену в общем тексте
    txt = soup.get_text(" ", strip=True)
    m = re.search(r"(?:Цена|Стоимость|за)\D{0,15}(\d[\d\s.,]{2,})\s?(₽|руб|KZT|₸|RUB|BYN)?", txt, re.I)
    if m:
        num = m.group(1).replace("\xa0", "").replace(" ", "").replace(",", ".")
        try:
            return float(num)
        except:
            pass

    return None


def fetch(url):
    # Открываем как реальный Chromium и ждём, пока появится цена
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(
            locale="ru-RU",
            user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/126.0.0.0 Safari/537.36")
        )
        page = ctx.new_page()
        # прогрев — чтобы получить куки города
        page.goto("https://www.dns-shop.ru/", wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(700)  # маленькая человеческая пауза
        # карточка товара
        page.goto(url, wait_until="domcontentloaded", timeout=60000)

        # ждём что-то одно из трёх: meta price / блок цены / JSON-LD
        try:
            page.wait_for_selector('meta[itemprop="price"], .product-buy__price, script[type="application/ld+json"]', timeout=15000)
        except PWTimeout:
            pass  # всё равно заберём контент — вдруг цена есть в тексте

        html = page.content()
        browser.close()
    return price_from_html(html)




def load_state():
    if os.path.exists(STATE):
        return json.load(open(STATE,"r",encoding="utf-8"))
    return {}

def save_state(s):
    json.dump(s, open(STATE,"w",encoding="utf-8"), ensure_ascii=False, indent=2)

def main():
    st = load_state()
    msgs = []
    targets = URLS if isinstance(URLS, list) else URLS  # поддержка и строки, и списка
    for url in targets:
        try:
            price = fetch(url)
        except Exception as e:
            msgs.append(f"⚠️ Не получилось получить цену:\n{url}\n{e}")
            continue
        if price is None:
            msgs.append(f"❓ Цена не найдена:\n{url}")
            continue
        prev = st.get(url, {}).get("price")
        st[url] = {"price": price, "ts": int(time.time())}
        if prev is None:
            msgs.append(f"🆕 Текущая цена: {price}\n{url}")
        elif price != prev:
            arrow = "⬇️" if price < prev else "⬆️"
            msgs.append(f"{arrow} Цена изменилась: была {prev}, стала {price}\n{url}")
        # если не изменилась — молчим
    save_state(st)
    if msgs:
        send("\n\n".join(msgs))

if __name__ == "__main__":
    main()
