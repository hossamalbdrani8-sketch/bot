# ============================================================
# 💀🚀 AI PRO MAX — FINAL MARKET HUNTER
# 🇸🇦 TASI  : SAHMK ONLY
# 🇺🇸 US    : Twelve Data ONLY
# 🪙 CRYPTO: Twelve Data ONLY
# 🚫 NO LOCAL HISTORY / NO SAHMK HISTORICAL API
# ============================================================

import os
import asyncio
import time
import random
from datetime import datetime, timezone
from collections import deque

import aiohttp
from aiohttp import web

# ============================================================
# ⚙️ ENVIRONMENT
# ============================================================

TWELVE_DATA_API_KEY = os.getenv("TWELVEDATA_API_KEY", "").strip()
SAHMK_API_KEY = os.getenv("SAHMK_API_KEY", "").strip()
SIFTING_API_KEY = os.getenv("SIFTING_API_KEY", "").strip()  # reserved; not used

TASI_TOKEN = os.getenv("TASI_TOKEN", "").strip()
US_TOKEN = os.getenv("US_TOKEN", "").strip()
CRYPTO_TOKEN = os.getenv("CRYPTO_TOKEN", "").strip()
CHAT_ID = os.getenv("CHAT_ID", "").strip()
PORT = int(os.getenv("PORT", "8080"))

# Continuous scanner settings.
SCAN_SECONDS = int(os.getenv("SCAN_SECONDS", "1800"))
MIN_US_PRICE = float(os.getenv("MIN_US_PRICE", "0.15"))

# User's current Twelve Data observed limits: keep a safety margin.
TD_REQUESTS_PER_MINUTE = int(os.getenv("TD_REQUESTS_PER_MINUTE", "7"))
TD_DAILY_BUDGET = int(os.getenv("TD_DAILY_BUDGET", "650"))

# SAHMK Free dashboard shows 100/day. Use all 100 unless the user overrides it.
SAHMK_DAILY_BUDGET = int(os.getenv("SAHMK_DAILY_BUDGET", "100"))

# Batch sizes are deliberately small because each US/crypto symbol uses a
# Twelve Data time-series request and each TASI symbol uses one SAHMK quote.
TASI_BATCH_SIZE = int(os.getenv("TASI_BATCH_SIZE", "50"))
US_BATCH_SIZE = int(os.getenv("US_BATCH_SIZE", "4"))
CRYPTO_BATCH_SIZE = int(os.getenv("CRYPTO_BATCH_SIZE", "4"))

REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "30"))
MAX_CONNECTIONS = int(os.getenv("MAX_CONNECTIONS", "10"))
SIGNAL_COOLDOWN = int(os.getenv("SIGNAL_COOLDOWN", "1800"))
NEWS_CACHE_SECONDS = int(os.getenv("NEWS_CACHE_SECONDS", "21600"))

# ============================================================
# 🧠 RUNTIME MEMORY ONLY
# ============================================================

symbols_cache = {"TASI": [], "US": [], "CRYPTO": []}
symbols_cache_time = {"TASI": 0.0, "US": 0.0, "CRYPTO": 0.0}
last_signal = {}
news_cache = {}
position_state = {}
telegram_chats = {"TASI": set(), "US": set(), "CRYPTO": set()}
rotation = {"TASI": 0, "US": 0, "CRYPTO": 0}
us_order = []
crypto_order = []
scan_number = 0
last_tasi_full_scan = 0.0
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
                        f"{self.name}: تم بلوغ ميزانية اليوم {self.daily_budget} طلب"
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
# 🌐 API CLIENTS
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
# 📦 CATALOG HELPERS — COMPLETE LISTS
# ============================================================

def extract_rows(data):
    if isinstance(data, list):
        return data
    if not isinstance(data, dict):
        return []
    for key in ("data", "values", "results", "companies", "cryptocurrencies", "stocks"):
        value = data.get(key)
        if isinstance(value, list):
            return value
    return []


def unique_items(items):
    out = {}
    for item in items:
        key = (item["symbol"], item.get("exchange", ""))
        out[key] = item
    return list(out.values())


async def get_tasi_symbols():
    """Load the TASI company directory from SAHMK, excluding ETFs/non-equities."""
    symbols = []
    limit = 100
    offset = 0
    while len(symbols) < 500:
        data = await sahmk("companies/", {"market": "TASI", "limit": limit, "offset": offset})
        rows = extract_rows(data)
        if not rows:
            break
        for item in rows:
            if not isinstance(item, dict) or item.get("is_etf"):
                continue
            security_type = str(item.get("security_type", "")).upper()
            if security_type not in ("", "EQUITY", "STOCK", "COMMON_STOCK"):
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
    result = list(unique.values())
    # Keep the provider's actual symbol; only sort the catalog for stable rotation.
    result.sort(key=lambda x: x["symbol"])
    return result


async def get_paginated_twelve_catalog(endpoint, base_params=None, max_pages=1000):
    """Read every available page from a Twelve Data catalog."""
    rows_all = []
    params_base = dict(base_params or {})
    for page in range(1, max_pages + 1):
        params = dict(params_base)
        params["page"] = page
        data = await twelve(endpoint, params)
        rows = extract_rows(data)
        if not rows:
            break
        rows_all.extend(rows)
        # The docs expose count/page; stop on a short final page.
        if len(rows) < 100:
            break
    return rows_all


async def get_us_symbols():
    rows = await get_paginated_twelve_catalog(
        "stocks",
        {"country": "United States", "type": "Common Stock"},
    )
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
    out = unique_items(out)
    out.sort(key=lambda x: x["symbol"].upper())
    return out


async def get_crypto_symbols():
    rows = await get_paginated_twelve_catalog("cryptocurrencies")
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
            "name": str(item.get("currency_base") or item.get("name") or symbol).strip(),
            "exchange": str(exchanges[0]).strip() if exchanges else "",
        })
    out = unique_items(out)
    out.sort(key=lambda x: x["symbol"].upper())
    return out


async def load_market_symbols(market, force=False):
    now = time.time()
    if not force and symbols_cache[market] and now - symbols_cache_time[market] < 86400:
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

        if market == "US":
            global us_order
            us_order = build_random_alphabet_order(symbols)
            rotation["US"] = 0
        elif market == "CRYPTO":
            global crypto_order
            crypto_order = list(range(len(symbols)))
            random.shuffle(crypto_order)
            rotation["CRYPTO"] = 0

        log(f"✅ {market}: تم تحميل {len(symbols)} رمز")
    except Exception as exc:
        log(f"ℹ️ {market}: تعذر تحميل القائمة: {exc}")


async def load_symbols(force=False):
    await asyncio.gather(
        load_market_symbols("TASI", force),
        load_market_symbols("US", force),
        load_market_symbols("CRYPTO", force),
        return_exceptions=True,
    )

# ============================================================
# 🎲 ORDER — US STARTS AT RANDOM LETTER, NOT ALWAYS A
# ============================================================

def build_random_alphabet_order(items):
    """Create an A→Z alphabetical traversal with a random starting point."""
    if not items:
        return []
    sorted_items = sorted(range(len(items)), key=lambda i: items[i]["symbol"].upper())
    start = random.randrange(len(sorted_items))
    return sorted_items[start:] + sorted_items[:start]


def next_order_batch(market, size):
    items = symbols_cache.get(market, [])
    if not items:
        return []
    if market == "US":
        order = us_order or list(range(len(items)))
    elif market == "CRYPTO":
        order = crypto_order or list(range(len(items)))
    else:
        order = list(range(len(items)))
    pos = rotation[market] % len(order)
    idxs = [order[(pos + i) % len(order)] for i in range(min(size, len(order)))]
    rotation[market] = (pos + len(idxs)) % len(order)
    return [items[i] for i in idxs]

# ============================================================
# 💰 QUOTES / TIME SERIES
# ============================================================


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
        "previous_close": first("previous_close", "prev_close", default=0),
        "value": first("value", "turnover", default=0),
        "bid": first("bid", default=0),
        "ask": first("ask", default=0),
    }


async def get_tasi_quotes_bulk(items):
    """SAHMK Free supports bulk quotes up to 50 symbols per request.
    This lets the bot cover the complete TASI catalog without spending one
    daily API call per stock.
    """
    if not items:
        return {}
    result = {}
    for start in range(0, len(items), 50):
        chunk = items[start:start + 50]
        symbols = ",".join(x["symbol"] for x in chunk)
        try:
            data = await sahmk("quotes/", {"symbols": symbols})
            rows = data.get("quotes", []) if isinstance(data, dict) else []
            by_symbol = {str(x.get("symbol", "")).strip(): x for x in rows if isinstance(x, dict)}
            for item in chunk:
                payload = by_symbol.get(item["symbol"])
                if payload:
                    result[item["symbol"]] = normalize_quote(payload, item)
        except Exception as exc:
            log(f"ℹ️ SAHMK Bulk TASI {start + 1}-{start + len(chunk)}: {exc}")
    return result


async def get_tasi_quote(item):
    try:
        data = await sahmk(f"quote/{item['symbol']}/")
        payload = data.get("data", data) if isinstance(data, dict) else None
        if isinstance(payload, dict):
            return normalize_quote(payload, item)
    except Exception as exc:
        log(f"ℹ️ SAHMK Quote TASI {item['symbol']}: {exc}")
    return None


async def get_td_market_data(item, market):
    # 250 daily bars gives enough data for EMA200 and the rest of the engine.
    params = {
        "symbol": item["symbol"],
        "interval": "1day",
        "outputsize": 250,
        "order": "desc",
    }
    if item.get("exchange"):
        params["exchange"] = item["exchange"]
    try:
        data = await twelve("time_series", params)
        values = data.get("values", []) if isinstance(data, dict) else []
        if not values:
            return None, []
        values = list(reversed(values))
        last = values[-1]
        quote = normalize_quote({
            "symbol": data.get("meta", {}).get("symbol", item["symbol"]),
            "name": item.get("name", item["symbol"]),
            "close": last.get("close", 0),
            "open": last.get("open", 0),
            "high": last.get("high", 0),
            "low": last.get("low", 0),
            "volume": last.get("volume", 0),
            "previous_close": values[-2].get("close", 0) if len(values) > 1 else 0,
        }, item)
        try:
            prev = float(quote.get("previous_close", 0) or 0)
            close = float(quote.get("close", 0) or 0)
            quote["percent_change"] = ((close / prev) - 1) * 100 if prev > 0 else 0
        except Exception:
            pass
        return quote, values
    except Exception as exc:
        log(f"ℹ️ Twelve Data Time Series {market} {item['symbol']}: {exc}")
        return None, []

# ============================================================
# 📊 TECHNICAL ENGINE — NO LOCAL HISTORY
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
        high = float(row.get("high", row.get("close", 0)))
        low = float(row.get("low", row.get("close", 0)))
        close = float(row.get("close", 0))
        tr = high - low if prev is None else max(high - low, abs(high - prev), abs(low - prev))
        trs.append(tr)
        prev = close
    value = sum(trs[:period]) / period
    for tr in trs[period:]:
        value = ((value * (period - 1)) + tr) / period
    return value


def support_resistance(data):
    recent = data[-30:]
    highs = [float(x.get("high", x.get("close", 0))) for x in recent]
    lows = [float(x.get("low", x.get("close", 0))) for x in recent]
    return (min(lows), max(highs)) if highs and lows else (None, None)


def volume_ratio(data, window=20):
    if len(data) < window + 1:
        return 1.0
    vals = [float(x.get("volume", 0) or 0) for x in data[-window-1:-1]]
    vals = [x for x in vals if x > 0]
    current = float(data[-1].get("volume", 0) or 0)
    if not vals or current <= 0:
        return 1.0
    return current / (sum(vals) / len(vals))


def vwap(data, window=20):
    recent = data[-window:]
    pv = 0.0
    vv = 0.0
    for row in recent:
        h = float(row.get("high", row.get("close", 0)) or 0)
        l = float(row.get("low", row.get("close", 0)) or 0)
        c = float(row.get("close", 0) or 0)
        vol = float(row.get("volume", 0) or 0)
        typical = (h + l + c) / 3
        pv += typical * vol
        vv += vol
    return pv / vv if vv > 0 else None


def power(data):
    row = data[-1]
    h = float(row.get("high", row.get("close", 0)) or 0)
    l = float(row.get("low", row.get("close", 0)) or 0)
    o = float(row.get("open", row.get("close", 0)) or 0)
    c = float(row.get("close", 0) or 0)
    span = max(h - l, abs(c) * 0.000001, 1e-12)
    body = c - o
    position = (c - l) / span
    buy = 50 + (body / span) * 25 + (position - 0.5) * 50
    buy = max(0, min(100, buy))
    return round(buy), round(100 - buy)


def movement_labels(data, vol_ratio, buy_power, sell_power):
    row = data[-1]
    h = float(row.get("high", row.get("close", 0)) or 0)
    l = float(row.get("low", row.get("close", 0)) or 0)
    o = float(row.get("open", row.get("close", 0)) or 0)
    c = float(row.get("close", 0) or 0)
    span = max(h - l, abs(c) * 0.000001, 1e-12)
    body_ratio = abs(c - o) / span
    labels = []
    if vol_ratio >= 2.5 and body_ratio >= 0.65:
        labels.append("🐋 حركة صنّاع السهم")
    if vol_ratio >= 1.7 and body_ratio >= 0.45:
        labels.append("⚡️ حركة مضاربين قوية")
    if vol_ratio >= 2.0:
        labels.append("🔎 رصد حركة غير اعتيادية")
    if vol_ratio >= 1.5 and buy_power >= 65:
        labels.append("💰💰 عمليات التجميع")
    return labels


def trend_states(price, ema10, ema25, ema50, ema200):
    long = "🟢 طويل المدى" if ema200 is not None and price >= ema200 else "🔴 طويل المدى"
    short = "🟢 قصير المدى" if ema10 is not None and ema25 is not None and ema10 >= ema25 else "🔴 قصير المدى"
    return long, short


def analyze(market, quote, history):
    if not history:
        return None
    try:
        price = float(quote.get("close", 0) or 0)
    except Exception:
        return None
    if price <= 0 or (market == "US" and price < MIN_US_PRICE):
        return None

    closes = [float(x.get("close", 0)) for x in history if float(x.get("close", 0) or 0) > 0]
    if len(closes) < 25:
        return None

    ema10 = ema(closes, 10)
    ema14 = ema(closes, 14)
    ema15 = ema(closes, 15)
    ema25 = ema(closes, 25)
    ema50 = ema(closes, 50)
    ema200 = ema(closes, 200)
    rsi14 = rsi(closes, 14)
    atr14 = atr(history, 14)
    support, resistance = support_resistance(history)
    vol_ratio = volume_ratio(history)
    vwap20 = vwap(history, 20)
    buy_power, sell_power = power(history)
    long_state, short_state = trend_states(price, ema10, ema25, ema50, ema200)

    buy = sell = 0
    if ema10 is not None and price >= ema10: buy += 1
    elif ema10 is not None: sell += 1
    if ema14 is not None and price >= ema14: buy += 1
    elif ema14 is not None: sell += 1
    if ema15 is not None and price >= ema15: buy += 1
    elif ema15 is not None: sell += 1
    if ema25 is not None and price >= ema25: buy += 1
    elif ema25 is not None: sell += 1
    if ema50 is not None:
        if price >= ema50: buy += 1
        else: sell += 1
    if ema200 is not None:
        if price >= ema200: buy += 1
        else: sell += 1
    if rsi14 is not None:
        if rsi14 >= 55: buy += 2
        elif rsi14 <= 45: sell += 2
    if vwap20 is not None:
        if price >= vwap20: buy += 1
        else: sell += 1
    if buy_power >= 60: buy += 1
    elif sell_power >= 60: sell += 1
    if vol_ratio >= 1.5:
        if buy_power >= sell_power: buy += 1
        else: sell += 1

    total = max(1, buy + sell)
    buy_score = round(buy / total * 100)
    sell_score = round(sell / total * 100)

    # Signal threshold; neutral symbols do not spam Telegram.
    if buy_score >= 70 and buy_score > sell_score:
        signal, strength = "BUY", buy_score
        trend = "صاعد قوي"
    elif sell_score >= 70 and sell_score > buy_score:
        signal, strength = "SELL", sell_score
        trend = "هابط قوي"
    else:
        return None

    if atr14 is None or atr14 <= 0:
        atr14 = max(price * 0.01, 0.00000001)

    # Dynamic TP ladder. It is extended beyond TP8 while the same trend remains.
    targets = [price + atr14 * m if signal == "BUY" else price - atr14 * m
               for m in (1, 1.5, 2, 2.5, 3, 3.5, 4, 4.5)]

    return {
        "market": market,
        "symbol": quote.get("symbol", ""),
        "name": quote.get("name", quote.get("symbol", "")),
        "price": price,
        "change": float(quote.get("percent_change", 0) or 0),
        "signal": signal,
        "strength": strength,
        "buy_power": buy_power,
        "sell_power": sell_power,
        "volume": float(quote.get("volume", 0) or 0),
        "volume_ratio": vol_ratio,
        "vwap": vwap20,
        "ema10": ema10,
        "ema14": ema14,
        "ema15": ema15,
        "ema25": ema25,
        "ema50": ema50,
        "ema200": ema200,
        "rsi": rsi14,
        "atr": atr14,
        "support": support,
        "resistance": resistance,
        "trend": trend,
        "long_state": long_state,
        "short_state": short_state,
        "movement_labels": movement_labels(history, vol_ratio, buy_power, sell_power),
        "targets": targets,
        "mode": "FULL_TECHNICAL",
    }


def analyze_tasi_first_scan(quote):
    """SAHMK Free has no historical endpoint. Use only current quote data.
    No EMA/RSI/ATR values are invented.
    """
    try:
        price = float(quote.get("close", 0) or 0)
        op = float(quote.get("open", price) or price)
        high = float(quote.get("high", price) or price)
        low = float(quote.get("low", price) or price)
        change = float(quote.get("percent_change", 0) or 0)
    except Exception:
        return None
    if price <= 0:
        return None
    span = max(high - low, price * 0.0001)
    pos = max(0.0, min(1.0, (price - low) / span))
    body = price - op
    buy = sell = 0
    if change >= 1.0: buy += 2
    elif change <= -1.0: sell += 2
    if body > 0: buy += 1
    elif body < 0: sell += 1
    if pos >= 0.70: buy += 1
    elif pos <= 0.30: sell += 1
    if buy < 3 and sell < 3:
        return None
    if buy >= 3 and buy > sell:
        signal, strength = "BUY", min(99, 70 + buy * 6)
        trend = "صاعد — أول فحص"
        bp, sp = 82, 18
    elif sell >= 3 and sell > buy:
        signal, strength = "SELL", min(99, 70 + sell * 6)
        trend = "هابط — أول فحص"
        bp, sp = 18, 82
    else:
        return None
    proxy = max(span, price * 0.005)
    targets = [price + proxy * m if signal == "BUY" else price - proxy * m
               for m in (0.5, .75, 1, 1.25, 1.5, 1.75, 2, 2.25)]
    return {
        "market": "TASI", "symbol": quote.get("symbol", ""),
        "name": quote.get("name", quote.get("symbol", "")), "price": price,
        "change": change, "signal": signal, "strength": strength,
        "buy_power": bp, "sell_power": sp, "volume": float(quote.get("volume", 0) or 0),
        "volume_ratio": None, "vwap": None, "ema10": None, "ema14": None,
        "ema15": None, "ema25": None, "ema50": None, "ema200": None,
        "rsi": None, "atr": None, "support": low, "resistance": high,
        "trend": trend, "long_state": "🟡 أول فحص", "short_state": "🟡 أول فحص",
        "movement_labels": [], "targets": targets, "mode": "TASI_FIRST_SCAN",
    }

# ============================================================
# 📰 US NEWS — TWELVE DATA
# ============================================================

POSITIVE_WORDS = {
    "beat", "beats", "growth", "grows", "profit", "profits", "record", "upgrade",
    "raises", "raised", "surge", "surges", "strong", "approval", "approved", "deal",
    "contract", "partnership", "launch", "buyback", "dividend", "positive", "revenue"
}
NEGATIVE_WORDS = {
    "miss", "misses", "loss", "losses", "downgrade", "cuts", "cut", "drop", "drops",
    "fall", "falls", "weak", "warning", "lawsuit", "investigation", "recall", "debt",
    "negative", "layoff", "bankruptcy", "offering", "dilution"
}


def classify_news(title):
    t = (title or "").lower()
    pos = sum(1 for w in POSITIVE_WORDS if w in t)
    neg = sum(1 for w in NEGATIVE_WORDS if w in t)
    if pos >= 2 and pos > neg:
        return "🟢 إيجابي قوي"
    if neg >= 2 and neg > pos:
        return "🔴 سلبي قوي"
    if pos > neg:
        return "🟢 إيجابي"
    if neg > pos:
        return "🔴 سلبي"
    return "🟡 محايد"


async def get_us_news(symbol):
    cached = news_cache.get(symbol)
    now = time.time()
    if cached and now - cached["time"] < NEWS_CACHE_SECONDS:
        return cached["items"]

    # Twelve Data exposes company press releases; use the symbol filter.
    # If the account/plan does not expose this endpoint, the signal continues
    # without inventing news.
    try:
        data = await twelve("press_releases", {"symbol": symbol, "outputsize": 5})
        rows = extract_rows(data)
        items = []
        for row in rows[:5]:
            if not isinstance(row, dict):
                continue
            title = str(row.get("title") or row.get("headline") or row.get("text") or "").strip()
            if not title:
                continue
            items.append({
                "title": title,
                "classification": classify_news(title),
                "date": str(row.get("date") or row.get("datetime") or "").strip(),
            })
        news_cache[symbol] = {"time": now, "items": items}
        return items
    except Exception as exc:
        log(f"ℹ️ US news {symbol}: {exc}")
        news_cache[symbol] = {"time": now, "items": []}
        return []

# ============================================================
# 🎯 TARGET STATE — TP1..TP8 THEN TP9..TPn
# ============================================================

def register_position(signal):
    key = (signal["market"], signal["symbol"])
    old = position_state.get(key)
    if old and old.get("signal") == signal["signal"]:
        old["price"] = signal["price"]
        old["atr"] = signal.get("atr") or old.get("atr") or max(signal["price"] * .01, 1e-12)
        old["targets"] = signal["targets"]
        return old
    state = {
        "signal": signal["signal"],
        "price": signal["price"],
        "atr": signal.get("atr") or max(signal["price"] * .01, 1e-12),
        "last_reached": 0,
        "targets": list(signal["targets"]),
    }
    position_state[key] = state
    return state


def target_value(state, n):
    base = state["price"]
    atr_value = state["atr"]
    # Existing TP1..TP8 are in state; after TP8 continue every 0.5 ATR.
    if n <= len(state["targets"]):
        return state["targets"][n - 1]
    mult = 4.5 + (n - 8) * 0.5
    return base + atr_value * mult if state["signal"] == "BUY" else base - atr_value * mult


def reached_targets(state, price):
    reached = state["last_reached"]
    while True:
        nxt = reached + 1
        target = target_value(state, nxt)
        hit = price >= target if state["signal"] == "BUY" else price <= target
        if not hit:
            break
        reached = nxt
        if nxt > 200:
            break
    return reached

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
    names = {"TASI": "🇸🇦 TASI SENTINEL", "US": "🇺🇸 US MARKET HUNTER", "CRYPTO": "🪙 CRYPTO HUNTER"}
    sources = {"TASI": "SAHMK فقط — بدون Historical API", "US": "Twelve Data فقط", "CRYPTO": "Twelve Data فقط"}
    return (
        "💀🚀 AI PRO MAX\n\n"
        f"{names[market]}\n\n"
        "✅ البوت يعمل 24/7\n"
        f"📡 مصدر البيانات: {sources[market]}\n"
        "🧠 EMA 10/14/15/25/50/200 / RSI14 / ATR14 / VWAP\n"
        "📦 Volume / 📊 Volume Ratio\n"
        "🟢 قوة الشراء / 🔴 قوة البيع\n"
        "🛡️ الدعم / 🚧 المقاومة\n"
        "🎯 TP1 → TP8 → TP9 → TP10 → …\n"
        "🚫 منع تكرار الإشارة\n"
    )


def pct_target(price, target, signal):
    if signal == "BUY":
        return ((target / price) - 1) * 100
    return (1 - target / price) * 100


def signal_text(signal, news=None):
    market = signal["market"]
    market_name = {"TASI": "🇸🇦 TASI", "US": "🇺🇸 US", "CRYPTO": "🪙 CRYPTO"}[market]
    arrow = "🟢⬆️" if signal["signal"] == "BUY" else "🔴⬇️"
    title = "شراء قوي" if signal["signal"] == "BUY" else "بيع قوي"

    lines = [
        "💀🚀 AI PRO MAX SIGNAL",
        "",
        market_name,
        f"{signal['symbol']} — {signal['name']}",
        "",
        f"{arrow} {title}",
        f"💰 السعر: {number(signal['price'])}",
        f"📈 التغير: {signal['change']:+.2f}%",
        f"🎯 القوة: {signal['strength']}/100",
        "",
        f"{signal['long_state']} - {signal['short_state']}",
        "",
    ]

    for label in signal.get("movement_labels", []):
        lines.append(label)
    if signal.get("movement_labels"):
        lines.append("")

    lines += [
        f"📦 Volume: {format_volume(signal.get('volume', 0))}",
        f"📊 Volume Ratio: {number(signal.get('volume_ratio')) if signal.get('volume_ratio') is not None else '—'}x",
        f"VWAP: {number(signal.get('vwap'))}",
        f"RSI 14: {number(signal.get('rsi'))}",
        f"ATR 14: {number(signal.get('atr'))}",
        "",
        f"EMA 10: {number(signal.get('ema10'))}",
        f"EMA 14: {number(signal.get('ema14'))}",
        f"EMA 15: {number(signal.get('ema15'))}",
        f"EMA 25: {number(signal.get('ema25'))}",
        f"EMA 50: {number(signal.get('ema50'))}",
        f"EMA 200: {number(signal.get('ema200'))}",
        "",
        f"🟢 قوة الشراء: {signal['buy_power']}%",
        f"🔴 قوة البيع: {signal['sell_power']}%",
        "",
        f"🛡️ الدعم: {number(signal.get('support'))}",
        f"🚧 المقاومة: {number(signal.get('resistance'))}",
    ]

    lines += ["", "🎯 الأهداف:"]
    for i, target in enumerate(signal["targets"], 1):
        lines.append(f"🎯 TP{i}: {number(target)} ({pct_target(signal['price'], target, signal['signal']):+.1f}%)")

    if news:
        lines += ["", "📰 أخبار السهم — Twelve Data:"]
        for item in news[:5]:
            lines.append(f"{item['classification']} — {item['title']}")

    return "\n".join(lines)


def format_volume(value):
    try:
        v = float(value or 0)
    except Exception:
        return "0"
    if abs(v) >= 1_000_000_000:
        return f"{v / 1_000_000_000:.2f}B"
    if abs(v) >= 1_000_000:
        return f"{v / 1_000_000:.2f}M"
    if abs(v) >= 1_000:
        return f"{v / 1_000:.2f}K"
    return f"{v:.0f}"


def number(value):
    if value is None:
        return "—"
    try:
        v = float(value)
    except Exception:
        return "—"
    if abs(v) >= 1000:
        return f"{v:,.2f}"
    if abs(v) >= 1:
        return f"{v:.2f}"
    return f"{v:.10f}".rstrip("0").rstrip(".")


async def send_signal(signal):
    market = signal["market"]
    token = token_for_market(market)
    if not token:
        return
    news = await get_us_news(signal["symbol"]) if market == "US" else []
    text = signal_text(signal, news)
    chats = list(telegram_chats[market]) or ([CHAT_ID] if CHAT_ID else [])
    results = await asyncio.gather(
        *[telegram_send(token, c, text) for c in chats], return_exceptions=True
    )
    sent = sum(1 for r in results if r is True)
    log(f"📩 Telegram {market} {signal['symbol']}: تم إرسال {sent}/{len(chats)}")


async def send_target_update(signal, reached):
    if reached <= 0:
        return
    state = position_state[(signal["market"], signal["symbol"])]
    token = token_for_market(signal["market"])
    if not token:
        return
    direction = "استمرار الصعود" if state["signal"] == "BUY" else "استمرار الهبوط"
    lines = [
        "💀🚀 AI PRO MAX TARGET UPDATE",
        "",
        {"TASI": "🇸🇦 TASI", "US": "🇺🇸 US", "CRYPTO": "🪙 CRYPTO"}[signal["market"]],
        f"{signal['symbol']} — {signal['name']}",
        "",
        f"{'🟢 UP' if state['signal'] == 'BUY' else '🔴 DOWN'}",
        "↓",
    ]
    for n in range(1, reached + 1):
        lines.append(f"TP{n} ✅")
        lines.append("↓")
    lines.append(f"{direction}")
    lines.append("↓")
    for n in range(reached + 1, reached + 4):
        lines.append(f"TP{n}: {number(target_value(state, n))}")
    text = "\n".join(lines)
    chats = list(telegram_chats[signal["market"]]) or ([CHAT_ID] if CHAT_ID else [])
    await asyncio.gather(*[telegram_send(token, c, text) for c in chats], return_exceptions=True)
    log(f"🎯 {signal['market']} {signal['symbol']}: وصل TP{reached}")


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

async def process_symbol(market, item, prefetched_quote=None):
    if market == "TASI":
        quote = prefetched_quote if prefetched_quote is not None else await get_tasi_quote(item)
        if not quote:
            return
        try:
            price = float(quote.get("close", 0) or 0)
        except Exception:
            return
        if price <= 0:
            return
        # TASI Free: immediate snapshot signal; no local history.
        signal = analyze_tasi_first_scan(quote)
    else:
        quote, history = await get_td_market_data(item, market)
        if not quote or not history:
            return
        try:
            price = float(quote.get("close", 0) or 0)
        except Exception:
            return
        if price <= 0:
            return
        if market == "US" and price < MIN_US_PRICE:
            return
        signal = analyze(market, quote, history)

    if not signal:
        return

    state = register_position(signal)
    reached = reached_targets(state, signal["price"])
    if reached > state["last_reached"]:
        state["last_reached"] = reached
        await send_target_update(signal, reached)

    if can_send(signal):
        await send_signal(signal)

# ============================================================
# 🔄 SCAN
# ============================================================

async def scan_market_batch(market, batch):
    if not batch:
        log(f"ℹ️ {market}: لا توجد رموز للدفعة")
        return
    log(f"🔎 {market}: فحص دفعة {len(batch)} رمز")
    if market == "TASI":
        quotes = await get_tasi_quotes_bulk(batch)
        for item in batch:
            try:
                await process_symbol("TASI", item, quotes.get(item["symbol"]))
            except Exception as exc:
                log(f"ℹ️ TASI {item.get('symbol','')}: {exc}")
        return
    for item in batch:
        try:
            await process_symbol(market, item)
        except Exception as exc:
            log(f"ℹ️ {market} {item.get('symbol', '')}: {exc}")


async def full_scan():
    global scan_number, last_tasi_full_scan
    scan_number += 1
    started = time.monotonic()
    log("=" * 60)
    log(f"💀🚀 AI PRO MAX SCAN #{scan_number}")
    log("=" * 60)

    await load_symbols(force=False)

    # 🇸🇦 TASI: complete catalog every ~2 hours. The Free SAHMK quota is
    # 100/day; 374 symbols need 8 bulk requests, so 12 full passes/day
    # plus the 4 catalog requests fit exactly inside that quota.
    now = time.time()
    if now - last_tasi_full_scan >= 7200 or last_tasi_full_scan == 0:
        tasi_items = symbols_cache.get("TASI", [])
        for start in range(0, len(tasi_items), 50):
            await scan_market_batch("TASI", tasi_items[start:start + 50])
        last_tasi_full_scan = now
    else:
        log("⏭️ TASI: الجولة الكاملة القادمة كل ساعتين حسب حصة SAHMK")

    # 🇺🇸 US + 🪙 CRYPTO: continuous rotating scan. US starts from a random
    # alphabetical point, then continues A→Z and wraps around.
    us_batch = next_order_batch("US", US_BATCH_SIZE)
    crypto_batch = next_order_batch("CRYPTO", CRYPTO_BATCH_SIZE)
    await scan_market_batch("US", us_batch)
    await scan_market_batch("CRYPTO", crypto_batch)

    td_min, td_day, td_budget = td_limiter.status()
    sm_min, sm_day, sm_budget = sahmk_limiter.status()
    elapsed = time.monotonic() - started
    log(f"📊 Twelve Data: {td_day}/{td_budget} اليوم | {td_min}/{TD_REQUESTS_PER_MINUTE} آخر دقيقة")
    log(f"📊 SAHMK: {sm_day}/{sm_budget} اليوم")
    log(f"📦 القوائم: TASI={len(symbols_cache['TASI'])} | US={len(symbols_cache['US'])} | CRYPTO={len(symbols_cache['CRYPTO'])}")
    log(f"✅ انتهت الدورة خلال {elapsed:.2f} ثانية")

# ============================================================
# ❤️ HEALTH
# ============================================================

async def health(request):
    td_min, td_day, td_budget = td_limiter.status()
    sm_min, sm_day, sm_budget = sahmk_limiter.status()
    return web.json_response({
        "status": "ok",
        "system": "AI PRO MAX FINAL",
        "sources": {"TASI": "SAHMK", "US": "Twelve Data", "CRYPTO": "Twelve Data"},
        "historical_api_tasi": False,
        "local_history": False,
        "scan_seconds": SCAN_SECONDS,
        "min_us_price": MIN_US_PRICE,
        "symbols": {k: len(v) for k, v in symbols_cache.items()},
        "twelve_data": {"minute": td_min, "day": td_day, "budget": td_budget},
        "sahmk": {"day": sm_day, "budget": sm_budget},
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
    log("=" * 60)
    log("💀🚀 AI PRO MAX — FINAL")
    log("🇸🇦 TASI: SAHMK ONLY — 374 catalog target — no Historical API")
    log("🇺🇸 US: Twelve Data ONLY — full catalog — price >= $0.15")
    log("🪙 CRYPTO: Twelve Data ONLY — full catalog")
    log("🚫 LOCAL HISTORY: REMOVED COMPLETELY")
    log("🟢 النظام يعمل 24/7")
    log(f"⏱️ الفحص كل {SCAN_SECONDS} ثانية")
    log(f"🛡️ Twelve Data: {TD_REQUESTS_PER_MINUTE}/minute, {TD_DAILY_BUDGET}/day")
    log(f"🛡️ SAHMK: {SAHMK_DAILY_BUDGET}/day")
    log(f"🇺🇸 US minimum price: ${MIN_US_PRICE}")
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

    if CHAT_ID:
        try:
            chat = int(CHAT_ID)
            for market in telegram_chats:
                telegram_chats[market].add(chat)
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
