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
    soup = BeautifulSoup(html, "html.parser")
    # 1) meta itemprop=price
    meta = soup.find("meta", {"itemprop": "price"})
    if meta and meta.get("content"):
        try: return float(str(meta["content"]).replace(",", "."))
        except: pass
    # 2) JSON-LD offers.price
    for tag in soup.find_all("script", {"type":"application/ld+json"}):
        try:
            data = json.loads(tag.string or "{}")
            items = data if isinstance(data, list) else [data]
            for obj in items:
                offers = isinstance(obj, dict) and obj.get("offers")
                if isinstance(offers, dict):
                    p = offers.get("price") or offers.get("lowPrice") or offers.get("highPrice")
                    if p: return float(str(p).replace(",", "."))
        except: pass
    # 3) эвристика по тексту
    txt = soup.get_text(" ", strip=True)
    m = re.search(r"(\d[\d\s.,]{2,})\s?(₽|руб|KZT|₸|RUB|BYN)", txt, re.I)
    if m:
        num = m.group(1).replace("\xa0","").replace(" ","").replace(",", ".")
        try: return float(num)
        except: pass
    return None

def fetch(url):
    r = requests.get(url, headers={"User-Agent":"Mozilla/5.0"}, timeout=30)
    r.raise_for_status()
    return price_from_html(r.text)

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
