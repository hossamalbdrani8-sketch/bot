# ============================================================
# 💀🚀 AI PRO MAX — FULL MARKET ROTATION v4
# TASI + US + CRYPTO + US NEWS
# Telegram: 3 bots / 7 Railway variables only
# ============================================================

import os
import asyncio
import time
import random
from datetime import datetime, timezone

import aiohttp
from aiohttp import web

# ============================================================
# ⚙️ RAILWAY VARIABLES — ONLY THESE 7 ARE REQUIRED
# ============================================================
TWELVE_DATA_API_KEY = os.getenv("TWELVEDATA_API_KEY", "").strip()
TASI_TOKEN = os.getenv("TASI_TOKEN", "").strip()
US_TOKEN = os.getenv("US_TOKEN", "").strip()
CRYPTO_TOKEN = os.getenv("CRYPTO_TOKEN", "").strip()
CHAT_ID = os.getenv("CHAT_ID", "").strip()
SAHMK_API_KEY = os.getenv("SAHMK_API_KEY", "").strip()
SIFTING_API_KEY = os.getenv("SIFTING_API_KEY", "").strip()  # reserved for future Sifting data

PORT = int(os.getenv("PORT", "8080"))
SCAN_SECONDS = int(os.getenv("SCAN_SECONDS", "1800"))  # 30 min rotation; 24/7
MIN_US_PRICE = float(os.getenv("MIN_US_PRICE", "0.15"))
REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "30"))
MAX_CONNECTIONS = int(os.getenv("MAX_CONNECTIONS", "8"))
SIGNAL_COOLDOWN = int(os.getenv("SIGNAL_COOLDOWN", "1800"))
CATALOG_REFRESH_SECONDS = int(os.getenv("SYMBOL_REFRESH_SECONDS", "86400"))

# Twelve Data safety limits (keep a buffer below the user's 8/min and 800/day plan).
TD_MINUTE_LIMIT = int(os.getenv("TD_MINUTE_LIMIT", "7"))
TD_DAILY_BUDGET = int(os.getenv("TD_DAILY_BUDGET", "650"))
TD_WINDOW_SECONDS = 60
TD_DAY_SECONDS = 86400
td_request_times = []

# Rotation sizes. The catalog remains COMPLETE; only a rotating batch is queried each cycle.
# This avoids pretending that a free API quota can query every US/crypto symbol every 2 minutes.
US_BATCH_SIZE = int(os.getenv("US_BATCH_SIZE", "4"))
CRYPTO_BATCH_SIZE = int(os.getenv("CRYPTO_BATCH_SIZE", "4"))
TASI_BATCH_SIZE = int(os.getenv("TASI_BATCH_SIZE", "25"))

# US news cache: news is fetched for a US symbol when a signal is generated, then cached.
NEWS_CACHE_SECONDS = int(os.getenv("NEWS_CACHE_SECONDS", "21600"))
TD_HISTORY_CACHE_SECONDS = int(os.getenv("TD_HISTORY_CACHE_SECONDS", "1500"))

# ============================================================
# 🧠 MEMORY
# ============================================================
symbols_cache = {"TASI": [], "US": [], "CRYPTO": []}
symbols_cache_time = {"TASI": 0.0, "US": 0.0, "CRYPTO": 0.0}
rotation_cursor = {"TASI": 0, "US": 0, "CRYPTO": 0}

history_cache = {}
news_cache = {}
last_signal = {}
telegram_chats = {
    "TASI": {CHAT_ID} if CHAT_ID else set(),
    "US": {CHAT_ID} if CHAT_ID else set(),
    "CRYPTO": {CHAT_ID} if CHAT_ID else set(),
}

scan_number = 0
session = None

# ============================================================
# 📝 LOG
# ============================================================
def log(message):
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    print(f"{now} UTC | {message}", flush=True)

# ============================================================
# 🌐 HTTP SESSION
# ============================================================
async def get_session():
    global session
    if session is None or session.closed:
        timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
        connector = aiohttp.TCPConnector(limit=MAX_CONNECTIONS, ttl_dns_cache=300)
        session = aiohttp.ClientSession(timeout=timeout, connector=connector)
    return session

# ============================================================
# 🔐 TELEGRAM TOKEN ROUTING
# ============================================================
def token_for_market(market):
    return {"TASI": TASI_TOKEN, "US": US_TOKEN, "CRYPTO": CRYPTO_TOKEN}.get(market, "")

# ============================================================
# 🌐 GENERIC JSON GET
# ============================================================
async def http_json(url, params=None, headers=None):
    s = await get_session()
    async with s.get(url, params=params or {}, headers=headers or {}) as response:
        body = await response.text()
        try:
            data = await response.json(content_type=None)
        except Exception:
            raise RuntimeError(f"HTTP {response.status}: {body[:300]}")
        if response.status != 200:
            msg = data.get("message", body[:500]) if isinstance(data, dict) else body[:500]
            raise RuntimeError(f"HTTP {response.status}: {msg}")
        if isinstance(data, dict) and data.get("status") == "error":
            raise RuntimeError(str(data.get("message", "API error")))
        return data

# ============================================================
# 📡 TWELVE DATA
# ============================================================
async def twelve(endpoint, params=None):
    if not TWELVE_DATA_API_KEY:
        raise RuntimeError("متغير TWELVEDATA_API_KEY غير موجود")

    # Hard safety gate: never intentionally exceed the user's Twelve Data plan.
    # We keep one credit/minute and 150 credits/day as a safety buffer.
    while True:
        now = time.time()
        td_request_times[:] = [t for t in td_request_times if now - t < TD_DAY_SECONDS]

        if len(td_request_times) >= TD_DAILY_BUDGET:
            raise RuntimeError(
                f"Twelve Data daily safety budget reached ({TD_DAILY_BUDGET}); request skipped"
            )

        recent = [t for t in td_request_times if now - t < TD_WINDOW_SECONDS]
        if len(recent) < TD_MINUTE_LIMIT:
            td_request_times.append(now)
            break

        sleep_for = max(0.5, TD_WINDOW_SECONDS - (now - min(recent)) + 0.1)
        log(f"⏳ Twelve Data rate-limit: انتظار {sleep_for:.1f} ثانية")
        await asyncio.sleep(sleep_for)

    query = dict(params or {})
    query["apikey"] = TWELVE_DATA_API_KEY
    return await http_json("https://api.twelvedata.com/" + endpoint.lstrip("/"), query)

# ============================================================
# 🇸🇦 SAHMK
# ============================================================
async def sahmk(endpoint, params=None):
    if not SAHMK_API_KEY:
        raise RuntimeError("متغير SAHMK_API_KEY غير موجود")
    headers = {"X-API-Key": SAHMK_API_KEY}
    return await http_json("https://api.sahmk.sa/api/v1/" + endpoint.lstrip("/"), params, headers)

# ============================================================
# 📦 CATALOG HELPERS
# ============================================================
def extract_rows(data):
    if isinstance(data, list):
        return data
    if not isinstance(data, dict):
        return []
    for key in ("data", "values", "results", "list"):
        if isinstance(data.get(key), list):
            return data[key]
    return []

# ============================================================
# 🇺🇸 COMPLETE US STOCK CATALOG
# ============================================================
async def get_all_us_symbols():
    log("📋 تحميل القائمة الكاملة للأسهم الأمريكية من Twelve Data")
    all_rows = []
    page = 1
    seen_pages = set()

    while page <= 1000:
        data = await twelve("stocks", {
            "country": "United States",
            "type": "Common Stock",
            "page": page,
        })
        rows = extract_rows(data)
        if not rows or page in seen_pages:
            break
        seen_pages.add(page)
        all_rows.extend(rows)

        # Twelve Data exposes count per page; stop when a short page is returned.
        if len(rows) < 100:
            break
        page += 1

    unique = {}
    for item in all_rows:
        if not isinstance(item, dict):
            continue
        symbol = str(item.get("symbol", "")).strip().upper()
        country = str(item.get("country", "")).strip().lower()
        typ = str(item.get("type", "")).strip().lower()
        if not symbol or country not in ("united states", "us", "usa"):
            continue
        if typ and typ != "common stock":
            continue
        unique[symbol] = {
            "symbol": symbol,
            "name": str(item.get("name", symbol)).strip(),
            "exchange": str(item.get("exchange", "")).strip(),
            "mic_code": str(item.get("mic_code", "")).strip(),
            "country": str(item.get("country", "")).strip(),
        }

    rows = list(unique.values())
    rows.sort(key=lambda x: x["symbol"])
    log(f"✅ US: تم تحميل {len(rows)} سهم أمريكي كاملًا")
    return rows

# ============================================================
# 🪙 COMPLETE CRYPTO CATALOG
# ============================================================
async def get_all_crypto_symbols():
    log("📋 تحميل القائمة الكاملة للعملات الرقمية من Twelve Data")
    all_rows = []
    page = 1

    while page <= 1000:
        data = await twelve("cryptocurrencies", {"page": page})
        rows = extract_rows(data)
        if not rows:
            break
        all_rows.extend(rows)
        if len(rows) < 100:
            break
        page += 1

    unique = {}
    for item in all_rows:
        if not isinstance(item, dict):
            continue
        symbol = str(item.get("symbol", "")).strip().upper()
        if not symbol:
            continue
        available = item.get("available_exchanges", [])
        if not isinstance(available, list):
            available = []
        unique[symbol] = {
            "symbol": symbol,
            "name": str(item.get("currency_base", symbol)).strip(),
            "exchange": str(available[0]).strip() if available else "",
            "mic_code": "",
            "country": "",
        }

    rows = list(unique.values())
    rows.sort(key=lambda x: x["symbol"])
    log(f"✅ CRYPTO: تم تحميل {len(rows)} عملة/زوج متاحًا في الكتالوج")
    return rows

# ============================================================
# 🇸🇦 COMPLETE TASI CATALOG — ACTIVE EQUITIES ONLY
# ============================================================
async def get_all_tasi_symbols():
    log("📋 تحميل قائمة TASI الكاملة من SAHMK")
    all_rows = []
    offset = 0
    limit = 100

    while offset < 5000:
        data = await sahmk("companies/", {
            "market": "TASI",
            "limit": limit,
            "offset": offset,
        })
        rows = data.get("results", []) if isinstance(data, dict) else []
        if not rows:
            break
        all_rows.extend(rows)
        total = int(data.get("total", len(all_rows))) if isinstance(data, dict) else len(all_rows)
        offset += len(rows)
        if offset >= total or len(rows) < limit:
            break

    unique = {}
    for item in all_rows:
        if not isinstance(item, dict):
            continue
        symbol = str(item.get("symbol", "")).strip()
        if not symbol:
            continue
        if str(item.get("status", "active")).lower() != "active":
            continue
        if str(item.get("security_type", "Equity")).lower() != "equity":
            continue
        if item.get("is_etf") is True:
            continue
        unique[symbol] = {
            "symbol": symbol,
            "name": str(item.get("name_ar", item.get("name_en", symbol))).strip(),
            "name_en": str(item.get("name_en", symbol)).strip(),
            "exchange": "TASI",
            "mic_code": "",
            "country": "Saudi Arabia",
        }

    rows = list(unique.values())
    rows.sort(key=lambda x: int(x["symbol"]) if x["symbol"].isdigit() else x["symbol"])
    log(f"✅ TASI: تم تحميل {len(rows)} شركة نشطة")
    return rows

# ============================================================
# 🔄 LOAD / REFRESH CATALOGS
# ============================================================
async def load_market_symbols(market, force=False):
    now = time.time()
    if (not force and symbols_cache[market] and
            now - symbols_cache_time[market] < CATALOG_REFRESH_SECONDS):
        return
    try:
        if market == "US":
            rows = await get_all_us_symbols()
        elif market == "CRYPTO":
            rows = await get_all_crypto_symbols()
        else:
            rows = await get_all_tasi_symbols()
        symbols_cache[market] = rows
        symbols_cache_time[market] = now
        rotation_cursor[market] %= max(len(rows), 1)
    except Exception as exc:
        log(f"ℹ️ {market}: تعذر تحميل القائمة: {exc}")

async def load_symbols(force=False):
    await asyncio.gather(*(load_market_symbols(m, force) for m in ("TASI", "US", "CRYPTO")), return_exceptions=True)

# ============================================================
# 🎲 ROTATION — US RANDOM LETTER A→Z
# ============================================================
def next_batch(market, size):
    rows = symbols_cache.get(market, [])
    if not rows:
        return []

    if market == "US":
        # Start at a random A-Z letter so the scanner never gets stuck at A.
        letter = random.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
        candidates = [x for x in rows if x["symbol"][:1].upper() == letter]
        if not candidates:
            candidates = rows
        # Randomize within the chosen letter, then continue normally.
        random.shuffle(candidates)
        batch = candidates[:size]
        # If this letter has fewer names, fill from a rotating global position.
        if len(batch) < size:
            start = rotation_cursor[market] % len(rows)
            for item in rows[start:] + rows[:start]:
                if item not in batch:
                    batch.append(item)
                    if len(batch) >= size:
                        break
        rotation_cursor[market] = (rotation_cursor[market] + size) % len(rows)
        log(f"🎲 US rotation: حرف {letter} | {', '.join(x['symbol'] for x in batch)}")
        return batch

    start = rotation_cursor[market] % len(rows)
    batch = []
    for i in range(min(size, len(rows))):
        batch.append(rows[(start + i) % len(rows)])
    rotation_cursor[market] = (start + len(batch)) % len(rows)
    return batch

# ============================================================
# 💰 QUOTES
# ============================================================
async def get_us_quote(item):
    params = {"symbol": item["symbol"]}
    if item.get("exchange"):
        params["exchange"] = item["exchange"]
    try:
        return await twelve("quote", params)
    except Exception as exc:
        log(f"ℹ️ US quote {item['symbol']}: {exc}")
        return None

async def get_crypto_quote(item):
    params = {"symbol": item["symbol"]}
    if item.get("exchange"):
        params["exchange"] = item["exchange"]
    try:
        return await twelve("quote", params)
    except Exception as exc:
        log(f"ℹ️ CRYPTO quote {item['symbol']}: {exc}")
        return None

async def get_tasi_quote(item):
    try:
        data = await sahmk(f"quote/{item['symbol']}/")
        if isinstance(data, dict) and "price" in data:
            return {
                "symbol": item["symbol"],
                "name": data.get("name", item.get("name", item["symbol"])),
                "close": data.get("price"),
                "percent_change": data.get("change_percent", 0),
                "volume": data.get("volume", 0),
            }
    except Exception as exc:
        log(f"ℹ️ TASI quote {item['symbol']}: {exc}")
    return None

# ============================================================
# 📈 HISTORY
# ============================================================
async def get_td_history(item, market):
    key = (market, item["symbol"], item.get("exchange", ""))
    cached = history_cache.get(key)
    now = time.time()
    if cached and now - cached["time"] < TD_HISTORY_CACHE_SECONDS:
        return cached["data"]
    params = {"symbol": item["symbol"], "interval": "1day", "outputsize": 100}
    if item.get("exchange"):
        params["exchange"] = item["exchange"]
    try:
        data = await twelve("time_series", params)
        values = data.get("values", []) if isinstance(data, dict) else []
        values = list(reversed(values))
        history_cache[key] = {"data": values, "time": now}
        return values
    except Exception as exc:
        log(f"ℹ️ تاريخ {market} {item['symbol']}: {exc}")
        return []

async def get_tasi_history(item):
    key = ("TASI", item["symbol"], "TASI")
    cached = history_cache.get(key)
    now = time.time()
    if cached and now - cached["time"] < 21600:
        return cached["data"]
    try:
        data = await sahmk(f"historical/{item['symbol']}/", {
            "interval": "1d", "limit": 100, "offset": 0
        })
        values = data.get("data", data.get("results", [])) if isinstance(data, dict) else []
        if isinstance(values, dict):
            values = values.get("data", [])
        history_cache[key] = {"data": values, "time": now}
        return values
    except Exception as exc:
        log(f"ℹ️ تاريخ TASI {item['symbol']}: {exc}")
        return []

# ============================================================
# 📊 TECHNICALS
# ============================================================
def ema(values, period):
    if len(values) < period:
        return None
    value = sum(values[:period]) / period
    k = 2 / (period + 1)
    for x in values[period:]:
        value = (x - value) * k + value
    return value

def rsi(values, period=14):
    if len(values) <= period:
        return None
    gains, losses = [], []
    for i in range(1, len(values)):
        d = values[i] - values[i - 1]
        gains.append(max(d, 0))
        losses.append(max(-d, 0))
    ag = sum(gains[:period]) / period
    al = sum(losses[:period]) / period
    for i in range(period, len(gains)):
        ag = ((ag * (period - 1)) + gains[i]) / period
        al = ((al * (period - 1)) + losses[i]) / period
    if al == 0:
        return 100.0
    return 100 - 100 / (1 + ag / al)

def atr(rows, period=14):
    if len(rows) < period + 1:
        return None
    trs = []
    prev = None
    for row in rows:
        try:
            h, l, c = float(row["high"]), float(row["low"]), float(row["close"])
        except Exception:
            continue
        if prev is None:
            tr = h - l
        else:
            tr = max(h - l, abs(h - prev), abs(l - prev))
        trs.append(tr)
        prev = c
    if len(trs) < period:
        return None
    value = sum(trs[:period]) / period
    for tr in trs[period:]:
        value = ((value * (period - 1)) + tr) / period
    return value

def support_resistance(rows):
    recent = rows[-30:]
    highs, lows = [], []
    for row in recent:
        try:
            highs.append(float(row["high"]))
            lows.append(float(row["low"]))
        except Exception:
            pass
    return (min(lows), max(highs)) if highs and lows else (None, None)

def volume_strength(rows):
    if len(rows) < 21:
        return 1.0
    vols = []
    for row in rows[-21:-1]:
        try:
            v = float(row.get("volume", 0))
            if v > 0: vols.append(v)
        except Exception:
            pass
    if not vols:
        return 1.0
    avg = sum(vols) / len(vols)
    try:
        current = float(rows[-1].get("volume", 0))
    except Exception:
        return 1.0
    return current / avg if avg > 0 else 1.0

# ============================================================
# 🧠 ANALYZE
# ============================================================
def analyze(market, quote, rows):
    try:
        price = float(quote.get("close", quote.get("price", 0)))
        change = float(quote.get("percent_change", quote.get("change_percent", 0)))
    except Exception:
        return None
    if price <= 0 or len(rows) < 60:
        return None
    if market == "US" and price < MIN_US_PRICE:
        return None

    clean, closes = [], []
    for row in rows:
        try:
            c = float(row["close"])
            h = float(row["high"])
            l = float(row["low"])
            if c > 0 and h > 0 and l > 0:
                clean.append(row)
                closes.append(c)
        except Exception:
            pass
    if len(closes) < 60:
        return None

    series = closes + [price]
    e8, e21, e50 = ema(series, 8), ema(series, 21), ema(series, 50)
    r14, a14 = rsi(series, 14), atr(clean, 14)
    support, resistance = support_resistance(clean)
    vol = volume_strength(clean)
    if any(x is None for x in (e8, e21, e50, r14, a14)):
        return None

    buy = sell = 0
    buy += price > e8
    sell += price <= e8
    buy += e8 > e21
    sell += e8 <= e21
    buy += e21 > e50
    sell += e21 <= e50
    if r14 >= 55: buy += 1
    elif r14 <= 45: sell += 1
    if support is not None:
        buy += price > support
        sell += price <= support
    if resistance is not None:
        buy += price >= resistance
        sell += price < resistance
    if vol >= 1.5:
        if buy >= sell: buy += 1
        else: sell += 1

    total = max(buy + sell, 1)
    buy_power = round(buy / total * 100)
    sell_power = round(sell / total * 100)
    if buy_power >= 75:
        signal, strength, trend = "BUY", buy_power, "صاعد قوي"
    elif sell_power >= 75:
        signal, strength, trend = "SELL", sell_power, "هابط قوي"
    else:
        return None

    targets = []
    for m in (1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5):
        targets.append(price + a14 * m if signal == "BUY" else price - a14 * m)

    return {
        "market": market,
        "symbol": str(quote.get("symbol", "")),
        "name": quote.get("name", quote.get("name_ar", quote.get("symbol", ""))),
        "price": price, "change": change, "signal": signal,
        "strength": strength, "buy_power": buy_power, "sell_power": sell_power,
        "volume": vol, "ema8": e8, "ema21": e21, "ema50": e50,
        "rsi": r14, "atr": a14, "support": support, "resistance": resistance,
        "trend": trend, "targets": targets,
    }

# ============================================================
# 📰 US NEWS — Twelve Data press releases
# ============================================================
def classify_news(title):
    t = (title or "").lower()
    strong_positive = [
        "record revenue", "raises guidance", "raised guidance", "beats estimates",
        "beats expectations", "strong results", "strong earnings", "acquisition completed",
        "approved", "fda approval", "major contract", "major partnership", "strategic partnership",
        "buyback", "share repurchase", "dividend increase", "profit rises", "revenue rises",
    ]
    strong_negative = [
        "lowers guidance", "cuts guidance", "misses estimates", "misses expectations",
        "investigation", "lawsuit", "fraud", "bankruptcy", "default", "recall",
        "layoffs", "profit falls", "revenue falls", "downgrade", "warning", "restatement",
    ]
    positive = ["partnership", "contract", "launches", "launch", "expands", "agreement", "growth", "upgrade"]
    negative = ["delay", "risk", "decline", "loss", "concern", "probe", "resigns", "resignation"]
    if any(k in t for k in strong_negative): return "🔴 سلبي قوي"
    if any(k in t for k in strong_positive): return "🟢 إيجابي قوي"
    if any(k in t for k in negative): return "🔴 سلبي"
    if any(k in t for k in positive): return "🟢 إيجابي"
    return "⚪ محايد"

async def get_us_news(symbol):
    cached = news_cache.get(symbol)
    now = time.time()
    if cached and now - cached["time"] < NEWS_CACHE_SECONDS:
        return cached["items"]
    try:
        data = await twelve("press_releases", {
            "symbol": symbol,
            "limit": 3,
        })
        rows = extract_rows(data)
        items = []
        for row in rows[:3]:
            if not isinstance(row, dict):
                continue
            title = str(row.get("title", row.get("headline", row.get("name", "")))).strip()
            if not title:
                continue
            items.append({"title": title, "sentiment": classify_news(title)})
        news_cache[symbol] = {"time": now, "items": items}
        return items
    except Exception as exc:
        log(f"ℹ️ أخبار US {symbol}: {exc}")
        return []

# ============================================================
# 🔢 NUMBER — high precision for tiny crypto prices
# ============================================================
def number(value, market=None):
    if value is None:
        return "—"
    try:
        v = float(value)
    except Exception:
        return "—"
    if market == "CRYPTO" and abs(v) < 1:
        if v == 0:
            return "0"
        return f"{v:.10f}".rstrip("0").rstrip(".")
    if abs(v) >= 1000:
        return f"{v:,.2f}"
    if abs(v) >= 1:
        return f"{v:.2f}"
    return f"{v:.4f}"

# ============================================================
# 📩 TELEGRAM
# ============================================================
async def telegram_send(token, chat_id, text):
    if not token or not chat_id:
        return False
    try:
        s = await get_session()
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        async with s.post(url, json={"chat_id": chat_id, "text": text, "disable_web_page_preview": True}) as response:
            return response.status == 200
    except Exception as exc:
        log(f"ℹ️ Telegram: {exc}")
        return False

# ============================================================
# 📣 SIGNAL MESSAGE
# ============================================================
async def send_signal(signal, news=None):
    market = signal["market"]
    token = token_for_market(market)
    if not token:
        return
    if signal["signal"] == "BUY":
        arrow, title = "🟢⬆️", "شراء قوي"
    else:
        arrow, title = "🔴⬇️", "بيع قوي"

    market_name = {"TASI": "🇸🇦 السوق السعودي (TASI)", "US": "🇺🇸 السوق الأمريكي (US)", "CRYPTO": "🪙 العملات الرقمية (CRYPTO)"}[market]
    targets = []
    for i, target in enumerate(signal["targets"], 1):
        pct = ((target / signal["price"] - 1) * 100) if signal["signal"] == "BUY" else ((1 - target / signal["price"]) * 100)
        targets.append(f"TP{i}: {number(target, market)} ({pct:+.1f}%)")

    text = (
        "💀🚀 AI PRO MAX SIGNAL\n\n"
        f"{market_name}\n\n"
        f"{signal['symbol']}\n{signal['name']}\n\n"
        f"{arrow} {title}\n\n"
        f"💰 السعر: {number(signal['price'], market)}\n"
        f"📈 التغير: {signal['change']:+.2f}%\n"
        f"🎯 قوة الإشارة: {signal['strength']}/100\n"
        f"🟢 قوة الشراء: {signal['buy_power']}%\n"
        f"🔴 قوة البيع: {signal['sell_power']}%\n"
        f"📊 قوة الحجم: {signal['volume']:.1f}x\n\n"
        f"EMA 8: {number(signal['ema8'], market)}\n"
        f"EMA 21: {number(signal['ema21'], market)}\n"
        f"EMA 50: {number(signal['ema50'], market)}\n"
        f"RSI 14: {signal['rsi']:.2f}\n"
        f"ATR 14: {number(signal['atr'], market)}\n\n"
        f"🛡️ الدعم: {number(signal['support'], market)}\n"
        f"🔺 المقاومة: {number(signal['resistance'], market)}\n"
        f"📊 الاتجاه: {signal['trend']}\n\n"
        "🎯 أهداف ATR الثمانية:\n" + "\n".join(targets)
    )

    if market == "US":
        text += "\n\n📰 الأخبار الأمريكية للسهم:\n"
        if news:
            for item in news:
                text += f"{item['sentiment']} — {item['title']}\n"
        else:
            text += "⚪ لا توجد أخبار حديثة متاحة من المصدر الآن\n"

    chats = list(telegram_chats[market])
    await asyncio.gather(*(telegram_send(token, chat, text) for chat in chats), return_exceptions=True)

# ============================================================
# 🚫 DUPLICATE SIGNAL CONTROL
# ============================================================
def can_send(signal):
    key = (signal["market"], signal["symbol"], signal["signal"])
    now = time.time()
    previous = last_signal.get(key, 0)
    if now - previous < SIGNAL_COOLDOWN:
        return False
    last_signal[key] = now
    return True

# ============================================================
# 🔍 PROCESS ONE SYMBOL
# ============================================================
async def process_symbol(market, item):
    if market == "TASI":
        # TASI is 100% SAHMK — Twelve Data is never used here.
        quote = await get_tasi_quote(item)
        if not quote:
            return
        rows = await get_tasi_history(item)
    else:
        # US + CRYPTO use Twelve Data only. One time_series call provides
        # current/latest OHLCV plus the historical data needed by the analyzer.
        rows = await get_td_history(item, market)
        if not rows or len(rows) < 2:
            return
        try:
            latest = rows[-1]
            previous = rows[-2]
            price = float(latest.get("close", 0))
            previous_close = float(previous.get("close", 0))
            if price <= 0:
                return
            if market == "US" and price < MIN_US_PRICE:
                return
            change = ((price - previous_close) / previous_close * 100) if previous_close else 0.0
            quote = {
                "symbol": item["symbol"],
                "name": item.get("name", item["symbol"]),
                "close": price,
                "percent_change": change,
            }
        except Exception as exc:
            log(f"ℹ️ تجهيز {market} {item.get('symbol','')}: {exc}")
            return

    if not rows:
        return
    signal = analyze(market, quote, rows)
    if not signal or not can_send(signal):
        return

    news = await get_us_news(signal["symbol"]) if market == "US" else None
    await send_signal(signal, news)

# ============================================================
# 🔎 MARKET SCAN
# ============================================================
async def scan_market(market, batch_size):
    rows = next_batch(market, batch_size)
    if not rows:
        log(f"ℹ️ {market}: لا توجد رموز محملة")
        return
    log(f"🔎 {market}: فحص {len(rows)} من {len(symbols_cache[market])} رمز في هذه الدورة")
    sem = asyncio.Semaphore(2)
    async def worker(item):
        async with sem:
            try:
                await process_symbol(market, item)
            except Exception as exc:
                log(f"ℹ️ {market} {item.get('symbol','')}: {exc}")
    await asyncio.gather(*(worker(x) for x in rows), return_exceptions=True)

# ============================================================
# 🔄 FULL 24/7 ROTATION
# ============================================================
async def full_scan():
    global scan_number
    scan_number += 1
    started = time.monotonic()
    log("=" * 64)
    log(f"💀🚀 AI PRO MAX SCAN #{scan_number}")
    log("=" * 64)
    await load_symbols(False)
    # All three markets are continuously rotated 24/7.
    await asyncio.gather(
        scan_market("TASI", TASI_BATCH_SIZE),
        scan_market("US", US_BATCH_SIZE),
        scan_market("CRYPTO", CRYPTO_BATCH_SIZE),
        return_exceptions=True,
    )
    log(f"✅ انتهت الدورة خلال {time.monotonic() - started:.2f} ثانية")

# ============================================================
# 🤖 START MESSAGE
# ============================================================
def startup_message(market):
    names = {"TASI": "🇸🇦 السوق السعودي", "US": "🇺🇸 السوق الأمريكي", "CRYPTO": "🪙 العملات الرقمية"}
    return (
        "💀🚀 AI PRO MAX\n\n"
        "✅ البوت يعمل 24/7\n"
        "🔄 فحص تلقائي ودوران مستمر\n"
        f"📊 السوق: {names[market]}\n\n"
        "🧠 EMA 8 / 21 / 50\n"
        "📊 RSI 14 / ATR 14 / Volume\n"
        "🛡️ دعم ومقاومة\n"
        "🎯 8 أهداف ATR\n"
        "🚫 منع تكرار الإشارات\n"
        + ("📰 أخبار السهم الأمريكية مع تصنيف إيجابي/سلبي\n" if market == "US" else "")
    )

# ============================================================
# 📲 TELEGRAM WEBHOOK
# ============================================================
async def telegram_webhook(request):
    path = request.path.lower()
    if path.endswith("/telegram/tasi"): market = "TASI"
    elif path.endswith("/telegram/us"): market = "US"
    elif path.endswith("/telegram/crypto"): market = "CRYPTO"
    else: return web.Response(status=200)
    token = token_for_market(market)
    if not token: return web.Response(status=200)
    try: update = await request.json()
    except Exception: return web.Response(status=200)
    message = update.get("message", {})
    chat_id = message.get("chat", {}).get("id")
    if chat_id is None: return web.Response(status=200)
    telegram_chats[market].add(str(chat_id))
    if str(message.get("text", "")).startswith("/start"):
        await telegram_send(token, chat_id, startup_message(market))
    return web.Response(status=200)

# ============================================================
# ❤️ HEALTH
# ============================================================
async def health(request):
    return web.json_response({
        "status": "ok",
        "system": "AI PRO MAX",
        "markets": ["TASI", "US", "CRYPTO"],
        "continuous_rotation": True,
        "scan_seconds": SCAN_SECONDS,
        "min_us_price": MIN_US_PRICE,
        "symbols": {m: len(symbols_cache[m]) for m in symbols_cache},
        "telegram": {"TASI": bool(TASI_TOKEN), "US": bool(US_TOKEN), "CRYPTO": bool(CRYPTO_TOKEN)},
        "twelve_data": bool(TWELVE_DATA_API_KEY),
        "twelve_data_minute_limit": TD_MINUTE_LIMIT,
        "twelve_data_daily_budget": TD_DAILY_BUDGET,
        "twelve_data_used_since_start": len(td_request_times),
        "sahmk": bool(SAHMK_API_KEY),
    })

# ============================================================
# 🔗 WEBHOOK SETUP
# ============================================================
async def set_webhook(market, token, base_url):
    if not token or not base_url:
        return
    url = f"https://api.telegram.org/bot{token}/setWebhook"
    webhook_url = f"{base_url.rstrip('/')}/telegram/{market.lower()}"
    try:
        s = await get_session()
        async with s.post(url, json={"url": webhook_url, "drop_pending_updates": True}) as response:
            if response.status == 200:
                log(f"Telegram Webhook: {market.lower()} ON")
            else:
                log(f"ℹ️ Telegram Webhook {market.lower()}: HTTP {response.status}")
    except Exception as exc:
        log(f"ℹ️ Webhook {market}: {exc}")

# ============================================================
# 🌐 SERVER
# ============================================================
async def start_server():
    app = web.Application()
    app.router.add_get("/", health)
    app.router.add_get("/health", health)
    app.router.add_post("/telegram/tasi", telegram_webhook)
    app.router.add_post("/telegram/us", telegram_webhook)
    app.router.add_post("/telegram/crypto", telegram_webhook)
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", PORT).start()
    log(f"🚀 AI PRO MAX يعمل على PORT {PORT}")
    return runner

# ============================================================
# 🔁 24/7 LOOP
# ============================================================
async def scanner_loop():
    await asyncio.sleep(3)
    while True:
        started = time.monotonic()
        try:
            await full_scan()
        except Exception as exc:
            log(f"ℹ️ خطأ في دورة الفحص: {exc}")
        elapsed = time.monotonic() - started
        wait = max(5, SCAN_SECONDS - int(elapsed))
        log(f"⏱️ الدورة القادمة خلال {wait} ثانية")
        await asyncio.sleep(wait)

# ============================================================
# 🚀 MAIN
# ============================================================
async def main():
    log("=" * 64)
    log("💀🚀 AI PRO MAX — FULL MARKET ROTATION")
    log("=" * 64)
    log(f"🤖 TASI BOT: {'ON' if TASI_TOKEN else 'OFF'}")
    log(f"🤖 US BOT: {'ON' if US_TOKEN else 'OFF'}")
    log(f"🤖 CRYPTO BOT: {'ON' if CRYPTO_TOKEN else 'OFF'}")
    log(f"🔑 Twelve Data: {'ON' if TWELVE_DATA_API_KEY else 'OFF'}")
    log(f"🔑 SAHMK: {'ON' if SAHMK_API_KEY else 'OFF'}")
    log(f"📰 US NEWS: Twelve Data press releases")
    log(f"💵 US minimum price: ${MIN_US_PRICE:.2f}")
    log(f"🔄 rotation: every {SCAN_SECONDS} seconds")
    log(f"🛡️ Twelve Data safety: {TD_MINUTE_LIMIT}/minute | {TD_DAILY_BUDGET}/24h")
    log("🇸🇦 TASI source: SAHMK only")
    log("🇺🇸 US source: Twelve Data only")
    log("🪙 CRYPTO source: Twelve Data only")
    log("📚 US catalog: FULL / random A-Z")
    log("📚 TASI catalog: FULL active equities")
    log("📚 CRYPTO catalog: FULL available catalog")
    log("=" * 64)

    runner = await start_server()
    base = os.getenv("RAILWAY_PUBLIC_DOMAIN", "").strip() or os.getenv("RAILWAY_STATIC_URL", "").strip()
    if base:
        if not base.startswith("http"):
            base = "https://" + base
        await asyncio.gather(
            set_webhook("TASI", TASI_TOKEN, base),
            set_webhook("US", US_TOKEN, base),
            set_webhook("CRYPTO", CRYPTO_TOKEN, base),
        )
    else:
        log("ℹ️ لا يوجد Railway Public Domain")

    try:
        await scanner_loop()
    finally:
        await runner.cleanup()
        if session and not session.closed:
            await session.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass