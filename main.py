# ============================================================
# 💀🚀 AI PRO MAX — SAHMK + TWELVE DATA
# 🇸🇦 TASI  : SAHMK ONLY
# 🇺🇸 US    : Twelve Data ONLY
# 🪙 CRYPTO: Twelve Data ONLY
# No SAHMK Historical API is used.
# ============================================================

import os
import asyncio
import time
import json
import sqlite3
from datetime import datetime, timezone
from collections import deque

import aiohttp
from aiohttp import web

# ============================================================
# ⚙️ ENVIRONMENT
# ============================================================

# IMPORTANT: Railway variable is TWELVEDATA_API_KEY
TWELVE_DATA_API_KEY = os.getenv("TWELVEDATA_API_KEY", "").strip()
SAHMK_API_KEY = os.getenv("SAHMK_API_KEY", "").strip()

TASI_TOKEN = os.getenv("TASI_TOKEN", "").strip()
US_TOKEN = os.getenv("US_TOKEN", "").strip()
CRYPTO_TOKEN = os.getenv("CRYPTO_TOKEN", "").strip()

PORT = int(os.getenv("PORT", "8080"))
CHAT_ID = os.getenv("CHAT_ID", "").strip()

# 30 minutes by default. The scanner remains alive 24/7.
SCAN_SECONDS = int(os.getenv("SCAN_SECONDS", "1800"))
MIN_US_PRICE = float(os.getenv("MIN_US_PRICE", "0.15"))

# Twelve Data safety limits. Keep below the user's observed plan limits.
TD_REQUESTS_PER_MINUTE = int(os.getenv("TD_REQUESTS_PER_MINUTE", "7"))
TD_DAILY_BUDGET = int(os.getenv("TD_DAILY_BUDGET", "650"))

# SAHMK Free has 100 requests/day according to the user's current API response.
SAHMK_DAILY_BUDGET = int(os.getenv("SAHMK_DAILY_BUDGET", "90"))
TASI_BATCH_SIZE = int(os.getenv("TASI_BATCH_SIZE", "4"))
US_BATCH_SIZE = int(os.getenv("US_BATCH_SIZE", "4"))
CRYPTO_BATCH_SIZE = int(os.getenv("CRYPTO_BATCH_SIZE", "4"))

REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "30"))
MAX_CONNECTIONS = int(os.getenv("MAX_CONNECTIONS", "10"))
SIGNAL_COOLDOWN = int(os.getenv("SIGNAL_COOLDOWN", "1800"))
NEWS_CACHE_SECONDS = int(os.getenv("NEWS_CACHE_SECONDS", "21600"))

DATA_DIR = os.getenv("DATA_DIR", "/tmp/ai_pro_max")
DB_PATH = os.path.join(DATA_DIR, "market_history.sqlite3")
os.makedirs(DATA_DIR, exist_ok=True)

# ============================================================
# 🧠 MEMORY
# ============================================================

symbols_cache = {"TASI": [], "US": [], "CRYPTO": []}
symbols_cache_time = {"TASI": 0.0, "US": 0.0, "CRYPTO": 0.0}

# Per-symbol in-memory latest history loaded from SQLite.
history_cache = {}
last_signal = {}
news_cache = {}
telegram_chats = {"TASI": set(), "US": set(), "CRYPTO": set()}

scan_number = 0
session = None

# Rotating positions. They intentionally persist only for this process.
rotation = {"TASI": 0, "US": 0, "CRYPTO": 0}

# ============================================================
# 📝 LOG
# ============================================================

def log(message):
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    print(f"{now} UTC | {message}", flush=True)

# ============================================================
# 💾 SQLITE — LOCAL HISTORY BUILDER
# ============================================================

def db_connect():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    with db_connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS candles (
                market TEXT NOT NULL,
                symbol TEXT NOT NULL,
                exchange TEXT NOT NULL DEFAULT '',
                ts INTEGER NOT NULL,
                price REAL NOT NULL,
                high REAL NOT NULL,
                low REAL NOT NULL,
                volume REAL NOT NULL DEFAULT 0,
                PRIMARY KEY (market, symbol, exchange, ts)
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_candles_symbol_ts "
            "ON candles(market, symbol, exchange, ts)"
        )


def save_observation(market, item, quote):
    try:
        price = float(quote.get("close", 0))
    except Exception:
        return
    if price <= 0:
        return

    # Quote endpoint may not provide OHLCV. We build a synthetic bar from the
    # observed price. This is intentionally local and does NOT call Historical.
    try:
        high = float(quote.get("high", price) or price)
    except Exception:
        high = price
    try:
        low = float(quote.get("low", price) or price)
    except Exception:
        low = price
    try:
        volume = float(quote.get("volume", 0) or 0)
    except Exception:
        volume = 0.0

    ts = int(time.time() // 1800 * 1800)
    symbol = item["symbol"]
    exchange = item.get("exchange", "")

    with db_connect() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO candles
            (market, symbol, exchange, ts, price, high, low, volume)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (market, symbol, exchange, ts, price, high, low, volume),
        )


def load_local_history(market, item, limit=160):
    symbol = item["symbol"]
    exchange = item.get("exchange", "")
    with db_connect() as conn:
        rows = conn.execute(
            """
            SELECT ts, price, high, low, volume
            FROM candles
            WHERE market=? AND symbol=? AND exchange=?
            ORDER BY ts DESC LIMIT ?
            """,
            (market, symbol, exchange, limit),
        ).fetchall()

    rows.reverse()
    return [
        {
            "datetime": datetime.fromtimestamp(r[0], tz=timezone.utc).isoformat(),
            "close": str(r[1]),
            "high": str(r[2]),
            "low": str(r[3]),
            "volume": str(r[4]),
        }
        for r in rows
    ]

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
# 🚦 RATE LIMITER
# ============================================================

class RateLimiter:
    def __init__(self, per_minute, daily_budget, name):
        self.per_minute = max(1, per_minute)
        self.daily_budget = max(1, daily_budget)
        self.name = name
        self.minute_calls = deque()
        self.day_key = datetime.now(timezone.utc).date().isoformat()
        self.daily_calls = 0
        self.lock = asyncio.Lock()

    async def acquire(self):
        async with self.lock:
            while True:
                now = time.monotonic()
                while self.minute_calls and now - self.minute_calls[0] >= 60:
                    self.minute_calls.popleft()

                day = datetime.now(timezone.utc).date().isoformat()
                if day != self.day_key:
                    self.day_key = day
                    self.daily_calls = 0

                if self.daily_calls >= self.daily_budget:
                    raise RuntimeError(
                        f"{self.name}: تم بلوغ ميزانية اليوم "
                        f"{self.daily_budget} طلب"
                    )

                if len(self.minute_calls) < self.per_minute:
                    self.minute_calls.append(now)
                    self.daily_calls += 1
                    return

                wait = max(0.5, 60 - (now - self.minute_calls[0]) + 0.2)
                await asyncio.sleep(wait)

    def status(self):
        now = time.monotonic()
        while self.minute_calls and now - self.minute_calls[0] >= 60:
            self.minute_calls.popleft()
        return len(self.minute_calls), self.daily_calls, self.daily_budget


td_limiter = RateLimiter(TD_REQUESTS_PER_MINUTE, TD_DAILY_BUDGET, "Twelve Data")
sahmk_limiter = RateLimiter(8, SAHMK_DAILY_BUDGET, "SAHMK")

# ============================================================
# 🌐 TWELVE DATA — US + CRYPTO ONLY
# ============================================================

async def twelve(endpoint, params=None):
    if not TWELVE_DATA_API_KEY:
        raise RuntimeError("متغير TWELVEDATA_API_KEY غير موجود")

    await td_limiter.acquire()
    s = await get_session()
    query = dict(params or {})
    query["apikey"] = TWELVE_DATA_API_KEY
    url = "https://api.twelvedata.com/" + endpoint.lstrip("/")

    async with s.get(url, params=query) as response:
        body = await response.text()
        try:
            data = await response.json(content_type=None)
        except Exception:
            raise RuntimeError(f"Twelve Data HTTP {response.status}: {body[:300]}")
        if response.status != 200:
            raise RuntimeError(f"Twelve Data HTTP {response.status}: {body[:500]}")
        if isinstance(data, dict) and data.get("status") == "error":
            raise RuntimeError(str(data.get("message", "خطأ غير معروف")))
        return data

# ============================================================
# 🇸🇦 SAHMK — TASI ONLY
# ============================================================

async def sahmk(endpoint, params=None):
    if not SAHMK_API_KEY:
        raise RuntimeError("متغير SAHMK_API_KEY غير موجود")

    await sahmk_limiter.acquire()
    s = await get_session()
    url = "https://api.sahmk.sa/api/v1/" + endpoint.lstrip("/")
    headers = {"X-API-Key": SAHMK_API_KEY, "Accept": "application/json"}

    async with s.get(url, params=params or {}, headers=headers) as response:
        body = await response.text()
        try:
            data = await response.json(content_type=None)
        except Exception:
            raise RuntimeError(f"SAHMK HTTP {response.status}: {body[:300]}")
        if response.status != 200:
            raise RuntimeError(f"SAHMK HTTP {response.status}: {body[:500]}")
        return data

# ============================================================
# 📦 CATALOG HELPERS
# ============================================================

def extract_rows(data):
    if isinstance(data, list):
        return data
    if not isinstance(data, dict):
        return []
    for key in ("data", "values", "results", "companies"):
        value = data.get(key)
        if isinstance(value, list):
            return value
    return []


async def get_tasi_symbols():
    symbols = []
    limit = 100
    offset = 0
    while len(symbols) < 500:
        data = await sahmk("companies/", {"market": "TASI", "limit": limit, "offset": offset})
        rows = extract_rows(data)
        if not rows:
            break
        for item in rows:
            if not isinstance(item, dict):
                continue
            if item.get("is_etf"):
                continue
            if str(item.get("security_type", "")).upper() not in ("", "EQUITY", "STOCK", "COMMON_STOCK"):
                continue
            symbol = str(item.get("symbol", "")).strip()
            if symbol:
                symbols.append({
                    "symbol": symbol,
                    "name": str(item.get("name_ar") or item.get("name_en") or symbol).strip(),
                    "exchange": "TASI",
                })
        if len(rows) < limit:
            break
        offset += limit
    unique = {}
    for item in symbols:
        unique[item["symbol"]] = item
    return list(unique.values())


async def get_us_symbols():
    data = await twelve("stocks", {"country": "United States", "type": "Common Stock", "page": 1})
    rows = extract_rows(data)
    out = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        symbol = str(item.get("symbol", "")).strip()
        if not symbol:
            continue
        out.append({
            "symbol": symbol,
            "name": str(item.get("name", symbol)).strip(),
            "exchange": str(item.get("exchange", "")).strip(),
        })
    return unique_items(out)


async def get_crypto_symbols():
    data = await twelve("cryptocurrencies", {"page": 1})
    rows = extract_rows(data)
    out = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        symbol = str(item.get("symbol", "")).strip()
        if not symbol:
            continue
        exchanges = item.get("available_exchanges") or []
        out.append({
            "symbol": symbol,
            "name": str(item.get("currency_base", symbol)).strip(),
            "exchange": str(exchanges[0]).strip() if exchanges else "",
        })
    return unique_items(out)


def unique_items(items):
    out = {}
    for item in items:
        out[(item["symbol"], item.get("exchange", ""))] = item
    return list(out.values())


async def load_market_symbols(market, force=False):
    now = time.time()
    refresh = 86400
    if not force and symbols_cache[market] and now - symbols_cache_time[market] < refresh:
        return
    try:
        if market == "TASI":
            symbols = await get_tasi_symbols()
        elif market == "US":
            symbols = await get_us_symbols()
        else:
            symbols = await get_crypto_symbols()
        symbols_cache[market] = symbols
        symbols_cache_time[market] = now
        log(f"✅ {market}: تم تحميل {len(symbols)} رمز")
    except Exception as exc:
        log(f"ℹ️ {market}: تعذر تحميل القائمة: {exc}")


async def load_symbols(force=False):
    # TASI catalog is SAHMK. US/Crypto catalogs are Twelve Data.
    await asyncio.gather(
        load_market_symbols("TASI", force),
        load_market_symbols("US", force),
        load_market_symbols("CRYPTO", force),
        return_exceptions=True,
    )

# ============================================================
# 💰 QUOTES
# ============================================================

async def get_tasi_quote(item):
    symbol = item["symbol"]
    try:
        data = await sahmk(f"quote/{symbol}/")
        if isinstance(data, dict):
            payload = data.get("data", data)
            if isinstance(payload, dict):
                return normalize_quote(payload, item)
        return None
    except Exception as exc:
        log(f"ℹ️ SAHMK Quote TASI {symbol}: {exc}")
        return None


async def get_td_quote(item, market):
    params = {"symbol": item["symbol"]}
    if item.get("exchange"):
        params["exchange"] = item["exchange"]
    try:
        data = await twelve("quote", params)
        if isinstance(data, dict):
            return normalize_quote(data, item)
    except Exception as exc:
        log(f"ℹ️ Twelve Quote {market} {item['symbol']}: {exc}")
    return None


def normalize_quote(data, item):
    def first(*keys, default=0):
        for key in keys:
            if key in data and data[key] not in (None, ""):
                return data[key]
        return default

    return {
        "symbol": str(first("symbol", default=item["symbol"])),
        "name": str(first("name", "company_name", default=item.get("name", item["symbol"]))),
        "close": first("close", "price", "last", "current_price", default=0),
        "open": first("open", default=0),
        "high": first("high", "day_high", default=0),
        "low": first("low", "day_low", default=0),
        "volume": first("volume", "day_volume", default=0),
        "percent_change": first("percent_change", "change_percent", default=0),
    }

# ============================================================
# 📊 LOCAL HISTORY / INDICATORS
# ============================================================

def ema(values, period):
    if len(values) < period:
        return None
    value = sum(values[:period]) / period
    mult = 2 / (period + 1)
    for x in values[period:]:
        value = (x - value) * mult + value
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
    return 100 - (100 / (1 + ag / al))


def atr(data, period=14):
    if len(data) < period + 1:
        return None
    trs = []
    prev = None
    for row in data:
        high = float(row["high"])
        low = float(row["low"])
        close = float(row["close"])
        tr = high - low if prev is None else max(high - low, abs(high - prev), abs(low - prev))
        trs.append(tr)
        prev = close
    value = sum(trs[:period]) / period
    for tr in trs[period:]:
        value = ((value * (period - 1)) + tr) / period
    return value


def support_resistance(data):
    recent = data[-30:]
    highs = [float(x["high"]) for x in recent]
    lows = [float(x["low"]) for x in recent]
    return (min(lows), max(highs)) if highs and lows else (None, None)


def volume_strength(data):
    if len(data) < 21:
        return 1.0
    vals = [float(x.get("volume", 0)) for x in data[-21:-1] if float(x.get("volume", 0)) > 0]
    if not vals:
        return 1.0
    avg = sum(vals) / len(vals)
    current = float(data[-1].get("volume", 0))
    return current / avg if avg else 1.0


def analyze(market, quote, history):
    try:
        price = float(quote["close"])
    except Exception:
        return None
    if price <= 0 or len(history) < 20:
        return None
    if market == "US" and price < MIN_US_PRICE:
        return None

    closes = [float(x["close"]) for x in history]
    ema8 = ema(closes, 8)
    ema21 = ema(closes, 21)
    ema50 = ema(closes, 50) if len(closes) >= 50 else None
    rsi14 = rsi(closes, 14)
    atr14 = atr(history, 14)
    support, resistance = support_resistance(history)
    vol = volume_strength(history)
    if any(x is None for x in (ema8, ema21, rsi14, atr14)):
        return None

    buy = sell = 0
    if price > ema8: buy += 1
    else: sell += 1
    if ema8 > ema21: buy += 1
    else: sell += 1
    if ema50 is not None:
        if ema21 > ema50: buy += 1
        else: sell += 1
    if rsi14 >= 55: buy += 1
    elif rsi14 <= 45: sell += 1
    if support is not None and price > support: buy += 1
    if resistance is not None and price < resistance: sell += 1
    if vol >= 1.5:
        if buy >= sell: buy += 1
        else: sell += 1

    total = max(1, buy + sell)
    buy_power = round(buy / total * 100)
    sell_power = round(sell / total * 100)
    if buy_power >= 75:
        signal, strength, trend = "BUY", buy_power, "صاعد قوي"
    elif sell_power >= 75:
        signal, strength, trend = "SELL", sell_power, "هابط قوي"
    else:
        return None

    targets = []
    for m in (1, 1.5, 2, 2.5, 3, 3.5, 4, 4.5):
        targets.append(price + atr14 * m if signal == "BUY" else price - atr14 * m)

    return {
        "market": market,
        "symbol": quote["symbol"],
        "name": quote["name"],
        "price": price,
        "change": float(quote.get("percent_change", 0) or 0),
        "signal": signal,
        "strength": strength,
        "buy_power": buy_power,
        "sell_power": sell_power,
        "volume": vol,
        "ema8": ema8,
        "ema21": ema21,
        "ema50": ema50,
        "rsi": rsi14,
        "atr": atr14,
        "support": support,
        "resistance": resistance,
        "trend": trend,
        "targets": targets,
    }

# ============================================================
# 🔢 FORMAT
# ============================================================

def number(value):
    if value is None:
        return "—"
    v = float(value)
    if abs(v) >= 1000:
        return f"{v:,.2f}"
    if abs(v) >= 1:
        return f"{v:.2f}"
    return f"{v:.10f}".rstrip("0").rstrip(".")

# ============================================================
# 📩 TELEGRAM
# ============================================================

async def telegram_send(token, chat_id, text):
    if not token or not chat_id:
        return False
    s = await get_session()
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        async with s.post(url, json={"chat_id": chat_id, "text": text, "disable_web_page_preview": True}) as response:
            return response.status == 200
    except Exception as exc:
        log(f"ℹ️ Telegram: {exc}")
        return False


def token_for_market(market):
    return {"TASI": TASI_TOKEN, "US": US_TOKEN, "CRYPTO": CRYPTO_TOKEN}.get(market, "")


def startup_message(market):
    names = {
        "TASI": "🇸🇦 TASI SENTINEL",
        "US": "🇺🇸 US MARKET HUNTER",
        "CRYPTO": "🪙 CRYPTO HUNTER",
    }
    sources = {
        "TASI": "SAHMK فقط — بدون Historical API",
        "US": "Twelve Data فقط",
        "CRYPTO": "Twelve Data فقط",
    }
    return (
        f"💀🚀 AI PRO MAX\n\n"
        f"{names[market]}\n\n"
        "✅ البوت يعمل 24/7\n"
        f"📡 مصدر البيانات: {sources[market]}\n"
        "🧠 EMA / RSI / ATR / دعم / مقاومة / حجم\n"
        "🎯 TP1 → TP8\n"
        "🚫 منع تكرار الإشارة\n"
        "💾 TASI يبني التاريخ محليًا تدريجيًا"
    )


async def send_signal(signal):
    market = signal["market"]
    token = token_for_market(market)
    if not token:
        return
    arrow = "🟢⬆️" if signal["signal"] == "BUY" else "🔴⬇️"
    title = "شراء قوي" if signal["signal"] == "BUY" else "بيع قوي"
    market_name = {"TASI": "🇸🇦 TASI", "US": "🇺🇸 US", "CRYPTO": "🪙 CRYPTO"}[market]
    targets = []
    for i, t in enumerate(signal["targets"], 1):
        pct = ((t / signal["price"] - 1) * 100) if signal["signal"] == "BUY" else ((1 - t / signal["price"]) * 100)
        targets.append(f"TP{i}: {number(t)} ({pct:+.1f}%)")
    text = (
        "💀🚀 AI PRO MAX SIGNAL\n\n"
        f"{market_name}\n{signal['symbol']} — {signal['name']}\n\n"
        f"{arrow} {title}\n"
        f"💰 السعر: {number(signal['price'])}\n"
        f"📈 التغير: {signal['change']:+.2f}%\n"
        f"🎯 القوة: {signal['strength']}/100\n"
        f"🟢 شراء: {signal['buy_power']}% | 🔴 بيع: {signal['sell_power']}%\n"
        f"📊 حجم: {signal['volume']:.1f}x\n\n"
        f"EMA8: {number(signal['ema8'])}\nEMA21: {number(signal['ema21'])}\nEMA50: {number(signal['ema50'])}\n"
        f"RSI14: {number(signal['rsi'])}\nATR14: {number(signal['atr'])}\n\n"
        f"🛡️ دعم: {number(signal['support'])}\n🔺 مقاومة: {number(signal['resistance'])}\n"
        f"📊 الاتجاه: {signal['trend']}\n\n🎯 الأهداف:\n" + "\n".join(targets)
    )
    chats = list(telegram_chats[market])
    if not chats and CHAT_ID:
        chats = [CHAT_ID]
    await asyncio.gather(*[telegram_send(token, c, text) for c in chats], return_exceptions=True)


def can_send(signal):
    key = (signal["market"], signal["symbol"], signal["signal"])
    now = time.time()
    if now - last_signal.get(key, 0) < SIGNAL_COOLDOWN:
        return False
    last_signal[key] = now
    return True

# ============================================================
# 🔍 PROCESS ONE SYMBOL
# ============================================================

async def process_symbol(market, item):
    if market == "TASI":
        quote = await get_tasi_quote(item)
    else:
        quote = await get_td_quote(item, market)
    if not quote:
        return
    try:
        price = float(quote["close"])
    except Exception:
        return
    if price <= 0:
        return
    if market == "US" and price < MIN_US_PRICE:
        return

    # Save every observation locally. This is the replacement for SAHMK Historical.
    save_observation(market, item, quote)
    history = load_local_history(market, item)
    history_cache[(market, item["symbol"], item.get("exchange", ""))] = history

    signal = analyze(market, quote, history)
    if signal and can_send(signal):
        await send_signal(signal)

# ============================================================
# 🔄 ROTATING BATCHES
# ============================================================

def next_batch(market, size):
    items = symbols_cache.get(market, [])
    if not items:
        return []
    pos = rotation[market] % len(items)
    batch = []
    for i in range(min(size, len(items))):
        batch.append(items[(pos + i) % len(items)])
    rotation[market] = (pos + len(batch)) % len(items)
    return batch


def shuffled_us_batch(size):
    # Random starting point across the alphabetic catalog, then rotate.
    items = symbols_cache.get("US", [])
    if not items:
        return []
    if rotation["US"] == 0:
        import random
        letter = random.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
        matches = [i for i, x in enumerate(items) if x["symbol"].upper().startswith(letter)]
        if matches:
            rotation["US"] = matches[0]
    return next_batch("US", size)


async def scan_market_batch(market, batch):
    if not batch:
        log(f"ℹ️ {market}: لا توجد رموز للدفعة")
        return
    log(f"🔎 {market}: فحص دفعة {len(batch)} رمز")
    # Sequential calls prevent bursts and protect API quotas.
    for item in batch:
        try:
            await process_symbol(market, item)
        except Exception as exc:
            log(f"ℹ️ {market} {item.get('symbol','')}: {exc}")

# ============================================================
# 🔄 FULL SCAN
# ============================================================

async def full_scan():
    global scan_number
    scan_number += 1
    started = time.monotonic()
    log("=" * 60)
    log(f"💀🚀 AI PRO MAX SCAN #{scan_number}")
    log("=" * 60)

    await load_symbols(force=False)

    # TASI uses SAHMK only; no historical endpoint.
    tasi_batch = next_batch("TASI", TASI_BATCH_SIZE)
    us_batch = shuffled_us_batch(US_BATCH_SIZE)
    crypto_batch = next_batch("CRYPTO", CRYPTO_BATCH_SIZE)

    await scan_market_batch("TASI", tasi_batch)
    await scan_market_batch("US", us_batch)
    await scan_market_batch("CRYPTO", crypto_batch)

    td_min, td_day, td_budget = td_limiter.status()
    sm_min, sm_day, sm_budget = sahmk_limiter.status()
    elapsed = time.monotonic() - started
    log(f"📊 Twelve Data: {td_day}/{td_budget} اليوم | {td_min}/{TD_REQUESTS_PER_MINUTE} آخر دقيقة")
    log(f"📊 SAHMK: {sm_day}/{sm_budget} اليوم")
    log(f"💾 TASI التاريخ المحلي: {DB_PATH}")
    log(f"✅ انتهت الدورة خلال {elapsed:.2f} ثانية")

# ============================================================
# ❤️ HEALTH
# ============================================================

async def health(request):
    td_min, td_day, td_budget = td_limiter.status()
    sm_min, sm_day, sm_budget = sahmk_limiter.status()
    return web.json_response({
        "status": "ok",
        "system": "AI PRO MAX",
        "sources": {"TASI": "SAHMK", "US": "Twelve Data", "CRYPTO": "Twelve Data"},
        "historical_api_tasi": False,
        "scan_seconds": SCAN_SECONDS,
        "symbols": {k: len(v) for k, v in symbols_cache.items()},
        "twelve_data": {"minute": td_min, "day": td_day, "budget": td_budget},
        "sahmk": {"day": sm_day, "budget": sm_budget},
        "database": DB_PATH,
    })

# ============================================================
# 📲 TELEGRAM WEBHOOKS
# ============================================================

async def telegram_webhook(request):
    path = request.path.lower()
    if path.endswith("/telegram/tasi"):
        market = "TASI"
    elif path.endswith("/telegram/us"):
        market = "US"
    elif path.endswith("/telegram/crypto"):
        market = "CRYPTO"
    else:
        return web.Response(status=200)
    token = token_for_market(market)
    if not token:
        return web.Response(status=200)
    try:
        update = await request.json()
    except Exception:
        return web.Response(status=200)
    message = update.get("message", {})
    chat = message.get("chat", {})
    chat_id = chat.get("id")
    if chat_id is None:
        return web.Response(status=200)
    telegram_chats[market].add(int(chat_id))
    if str(message.get("text", "")).startswith("/start"):
        await telegram_send(token, chat_id, startup_message(market))
    return web.Response(status=200)


async def set_webhook(market, token, base_url):
    if not token:
        return
    url = f"https://api.telegram.org/bot{token}/setWebhook"
    webhook_url = f"{base_url.rstrip('/')}/telegram/{market.lower()}"
    try:
        s = await get_session()
        async with s.post(url, json={"url": webhook_url, "drop_pending_updates": True}) as response:
            body = await response.text()
            log(f"Telegram Webhook {market}: HTTP {response.status} {body[:120]}")
    except Exception as exc:
        log(f"ℹ️ Webhook {market}: {exc}")


async def start_server():
    app = web.Application()
    app.router.add_get("/", health)
    app.router.add_get("/health", health)
    app.router.add_post("/telegram/tasi", telegram_webhook)
    app.router.add_post("/telegram/us", telegram_webhook)
    app.router.add_post("/telegram/crypto", telegram_webhook)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
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
        wait = max(1, SCAN_SECONDS - int(elapsed))
        log(f"⏱️ الدورة القادمة خلال {wait} ثانية")
        await asyncio.sleep(wait)

# ============================================================
# 🚀 MAIN
# ============================================================

async def main():
    init_db()
    log("=" * 60)
    log("💀🚀 AI PRO MAX — SAHMK + TWELVE DATA")
    log("🇸🇦 TASI: SAHMK ONLY")
    log("🇺🇸 US: Twelve Data ONLY")
    log("🪙 CRYPTO: Twelve Data ONLY")
    log("🚫 TASI Historical API: DISABLED")
    log("🟢 النظام يعمل 24/7")
    log(f"⏱️ الفحص كل {SCAN_SECONDS} ثانية")
    log(f"🇸🇦 TASI batch: {TASI_BATCH_SIZE}")
    log(f"🇺🇸 US batch: {US_BATCH_SIZE}")
    log(f"🪙 Crypto batch: {CRYPTO_BATCH_SIZE}")
    log(f"🛡️ Twelve Data limit: {TD_REQUESTS_PER_MINUTE}/minute, {TD_DAILY_BUDGET}/day")
    log(f"🛡️ SAHMK limit: {SAHMK_DAILY_BUDGET}/day")
    log("=" * 60)

    if not TWELVE_DATA_API_KEY:
        log("ℹ️ مفتاح TWELVEDATA_API_KEY غير موجود")
    if not SAHMK_API_KEY:
        log("ℹ️ مفتاح SAHMK_API_KEY غير موجود")

    runner = await start_server()
    domain = os.getenv("RAILWAY_PUBLIC_DOMAIN", "").strip() or os.getenv("RAILWAY_STATIC_URL", "").strip()
    if domain:
        if not domain.startswith("http"):
            domain = "https://" + domain
        await asyncio.gather(
            set_webhook("TASI", TASI_TOKEN, domain),
            set_webhook("US", US_TOKEN, domain),
            set_webhook("CRYPTO", CRYPTO_TOKEN, domain),
        )
    else:
        log("ℹ️ لا يوجد Railway Public Domain")
    try:
        if CHAT_ID:
            telegram_chats["TASI"].add(int(CHAT_ID))
            telegram_chats["US"].add(int(CHAT_ID))
            telegram_chats["CRYPTO"].add(int(CHAT_ID))
    except Exception:
        pass
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
