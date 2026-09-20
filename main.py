# ============================================================
# AI PRO MAX — ONE FILE / TASI + US + CRYPTO
# Stable / Quota-Protected Edition
# ============================================================
#
# Railway Variables:
# CHAT_ID
# TASI_TOKEN
# US_TOKEN
# CRYPTO_TOKEN
# SAHMK_API_KEY
# TWELVE_DATA_API_KEY
#
# TASI  -> SAHMK only
# US    -> Twelve Data
# CRYPTO-> Twelve Data
#
# IMPORTANT:
# Twelve Data US/CRYPTO requests necessarily consume Twelve Data credits.
# This file minimizes requests, caches data, blocks duplicate requests,
# and uses a hard daily budget below the 800-credit Basic daily limit.
# It does NOT call /api_usage and does NOT request news for every symbol.
# ============================================================

import os
import time
import queue
import threading
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from urllib.parse import quote
from threading import Lock, local

import requests
from PIL import Image, ImageDraw

# ============================================================
# ENVIRONMENT
# ============================================================

CHAT_ID = os.getenv("CHAT_ID", "").strip()
TASI_TOKEN = os.getenv("TASI_TOKEN", "").strip()
US_TOKEN = os.getenv("US_TOKEN", "").strip()
CRYPTO_TOKEN = os.getenv("CRYPTO_TOKEN", "").strip()
SAHMK_API_KEY = os.getenv("SAHMK_API_KEY", "").strip()

TWELVEDATA_API_KEY = (
    os.getenv("TWELVE_DATA_API_KEY", "").strip()
    or os.getenv("TWELVEDATA_API_KEY", "").strip()
)

# ============================================================
# SERVICES / LIMITS
# ============================================================

TWELVE_BASE = "https://api.twelvedata.com"
SAHMK_BASE = "https://api.sahmk.sa/api/v1"
RIYADH = ZoneInfo("Asia/Riyadh")

# Keep a safety margin below the 800/day Basic quota.
TD_DAILY_LIMIT = 700
TD_PER_MINUTE_LIMIT = 8

# Do not use /api_usage: it consumes quota.
# The response headers are used when Twelve Data returns them.
TD_CREDITS_LEFT = None
TD_CREDITS_LEFT_AT = 0.0
TD_RESERVED_TODAY = 0
TD_DAY = None

td_budget_lock = Lock()
td_request_lock = Lock()
td_last_request = 0.0

# Minimum spacing between Twelve Data HTTP requests.
TD_REQUEST_GAP = 0.30

# TASI: 3 calls / 15 minutes during the session.
TASI_SCAN_SECONDS = 15 * 60

# US/CRYPTO scanner cadence.
SCAN_INTERVAL = 60

# 5-minute technical scan.
PRIMARY_TIMEFRAME = "5min"
OUTPUTSIZE = 220

# US universe.
# Keep $0.20+ as requested.
MIN_US_PRICE = 0.20
US_MAX_SYMBOLS = 13414

# Batch size is 8, matching the per-minute credit allowance.
BATCH_SYMBOLS = 8

# We rotate through the whole universe rather than restarting at A.
US_PER_PASS = 8
CRYPTO_PER_PASS = 8

# Cache a symbol's candles for a little longer than the scan interval.
SERIES_CACHE_TTL = 75
SYMBOL_REFRESH_SECONDS = 6 * 60 * 60

# News is expensive compared with candle-only scanning.
NEWS_SCORE_MIN = 80
NEWS_CACHE_TTL = 30 * 60

# ============================================================
# INDICATOR SETTINGS
# ============================================================

EMA_FAST = 10
EMA_MID = 14
EMA_MOMENTUM = 15
EMA_TRIGGER = 25
EMA_SLOW = 50
EMA_LONG = 200

RSI_LENGTH = 14
ATR_LENGTH = 14
VOLUME_LENGTH = 20

MIN_SIGNAL_SCORE = 70

ATR_TARGETS = [1.0, 1.5, 2.0, 3.0, 4.0, 5.0, 6.5, 8.0]
STOP_ATR_MULTIPLIER = 1.5

POSITIVE_WORDS = [
    "beat", "beats", "growth", "profit", "profits", "upgrade",
    "upgraded", "buy", "strong", "positive", "partnership",
    "contract", "approval", "revenue", "surge", "record",
    "raises guidance", "guidance"
]

NEGATIVE_WORDS = [
    "loss", "losses", "downgrade", "downgraded", "sell", "weak",
    "negative", "lawsuit", "decline", "drop", "warning", "debt",
    "offering", "investigation", "risk", "cuts guidance", "guidance cut"
]

# ============================================================
# STATE
# ============================================================

_thread_local = local()

state_lock = Lock()

LAST_SIGNAL = {}
TREND_STATE = {}
REVERSAL_COUNT = {}
ARS_STATE = {}

# Target continuation state:
# key -> {"last_target": float, "next_index": int, "direction": "UP/DOWN"}
TARGET_STATE = {}

NEWS_CACHE = {}

# Symbol universe cache.
symbol_cache_lock = Lock()
SYMBOL_CACHE = {
    "US": {"symbols": [], "updated": 0.0},
    "CRYPTO": {"symbols": [], "updated": 0.0},
}

# Candle cache.
series_cache_lock = Lock()
SERIES_CACHE = {}

# Scanner cursors.
SCAN_CURSORS = {"US": 0, "CRYPTO": 0}

# TASI duplicate state.
TASI_LAST_SENT = {}

# ============================================================
# TELEGRAM QUEUE
# ============================================================

TELEGRAM_QUEUE = queue.Queue(maxsize=5000)


# ============================================================
# HTTP SESSION
# ============================================================

def get_session():
    session = getattr(_thread_local, "session", None)

    if session is None:
        session = requests.Session()
        session.headers.update({
            "User-Agent": "AI-PRO-MAX/Unified-Quota-Protected"
        })

        adapter = requests.adapters.HTTPAdapter(
            pool_connections=10,
            pool_maxsize=10,
            max_retries=0,
        )
        session.mount("https://", adapter)
        session.mount("http://", adapter)

        _thread_local.session = session

    return session


# ============================================================
# TWELVE DATA QUOTA GATE
# ============================================================

def reset_td_day():
    global TD_CREDITS_LEFT, TD_CREDITS_LEFT_AT
    global TD_RESERVED_TODAY, TD_DAY, td_last_request

    today = datetime.now(timezone.utc).date()

    with td_budget_lock:
        if TD_DAY != today:
            TD_DAY = today
            TD_CREDITS_LEFT = None
            TD_CREDITS_LEFT_AT = 0.0
            TD_RESERVED_TODAY = 0

    with td_request_lock:
        td_last_request = 0.0


def td_reserve(cost=1):
    """
    Reserve credits before making a Twelve Data request.
    Never deliberately targets the provider's full 800/day quota.
    """
    global TD_RESERVED_TODAY

    reset_td_day()
    cost = max(1, int(cost))

    with td_budget_lock:
        # If a fresh provider header says less than cost is available,
        # stop immediately.
        if TD_CREDITS_LEFT is not None:
            if (time.time() - TD_CREDITS_LEFT_AT) < 60 and TD_CREDITS_LEFT < cost:
                return False

        if TD_RESERVED_TODAY + cost > TD_DAILY_LIMIT:
            return False

        TD_RESERVED_TODAY += cost
        return True


def td_rate_wait():
    global td_last_request

    with td_request_lock:
        now = time.monotonic()
        wait = TD_REQUEST_GAP - (now - td_last_request)

        if wait > 0:
            time.sleep(wait)

        td_last_request = time.monotonic()


def td_request(endpoint, params=None, credit_cost=1):
    """
    One quota-controlled Twelve Data request.
    No /api_usage call is ever made.
    """
    global TD_CREDITS_LEFT, TD_CREDITS_LEFT_AT

    if not TWELVEDATA_API_KEY:
        return None

    if not td_reserve(credit_cost):
        print(f"🛡️ Twelve Data: request blocked by local quota gate -> {endpoint}")
        return None

    params = dict(params or {})
    params["apikey"] = TWELVEDATA_API_KEY

    session = get_session()

    for attempt in range(3):
        try:
            td_rate_wait()

            response = session.get(
                TWELVE_BASE + endpoint,
                params=params,
                timeout=(10, 30),
            )

            # Twelve Data commonly exposes usage through response headers.
            left = response.headers.get("api-credits-left")
            if left is None:
                left = response.headers.get("api-credits-left-per-minute")

            if left is not None:
                try:
                    with td_budget_lock:
                        TD_CREDITS_LEFT = int(float(left))
                        TD_CREDITS_LEFT_AT = time.time()
                except Exception:
                    pass

            if response.status_code == 429:
                print("🟠 Twelve Data: 429 — request stopped")
                return None

            if response.status_code in (500, 502, 503, 504):
                if attempt < 2:
                    time.sleep(2 ** attempt)
                    continue
                return None

            if response.status_code != 200:
                print(f"🔴 Twelve Data HTTP {response.status_code}: {endpoint}")
                return None

            try:
                data = response.json()
            except ValueError:
                return None

            if isinstance(data, dict):
                status = str(data.get("status", "")).lower()
                if status == "error":
                    print("🔴 Twelve Data:", data.get("message", "error"))
                    return None

            return data

        except (requests.Timeout, requests.ConnectionError) as exc:
            if attempt < 2:
                time.sleep(2 ** attempt)
                continue
            print("🔴 Twelve Data connection:", exc)
            return None

        except Exception as exc:
            print("🔴 Twelve Data:", exc)
            return None

    return None


# ============================================================
# GENERIC INDICATORS
# ============================================================

def ema(values, length):
    if len(values) < length:
        return None

    alpha = 2.0 / (length + 1.0)
    value = sum(values[:length]) / length

    for x in values[length:]:
        value = (x - value) * alpha + value

    return value


def sma(values, length):
    if len(values) < length:
        return None
    return sum(values[-length:]) / length


def rsi(values, length=14):
    if len(values) < length + 1:
        return None

    gains = []
    losses = []

    for i in range(1, len(values)):
        change = values[i] - values[i - 1]

        if change > 0:
            gains.append(change)
            losses.append(0.0)
        else:
            gains.append(0.0)
            losses.append(abs(change))

    avg_gain = sum(gains[:length]) / length
    avg_loss = sum(losses[:length]) / length

    for i in range(length, len(gains)):
        avg_gain = ((avg_gain * (length - 1)) + gains[i]) / length
        avg_loss = ((avg_loss * (length - 1)) + losses[i]) / length

    if avg_loss == 0:
        return 100.0

    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def atr(highs, lows, closes, length=14):
    if len(closes) < length + 1:
        return None

    trs = []

    for i in range(1, len(closes)):
        trs.append(max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        ))

    if len(trs) < length:
        return None

    value = sum(trs[:length]) / length

    for tr_value in trs[length:]:
        value = ((value * (length - 1)) + tr_value) / length

    return value


def vwap(highs, lows, closes, volumes):
    pv = 0.0
    vol = 0.0

    for high, low, close, volume in zip(highs, lows, closes, volumes):
        typical = (high + low + close) / 3.0
        pv += typical * volume
        vol += volume

    if vol <= 0:
        return None

    return pv / vol


# ============================================================
# SERIES / CACHE
# ============================================================

def parse_series_payload(data):
    if not isinstance(data, dict):
        return None

    values = data.get("values")
    if not isinstance(values, list) or not values:
        return None

    candles = []

    # Twelve Data returns newest first. Reverse to oldest -> newest.
    for item in reversed(values):
        try:
            candles.append({
                "datetime": item.get("datetime"),
                "open": float(item["open"]),
                "high": float(item["high"]),
                "low": float(item["low"]),
                "close": float(item["close"]),
                "volume": float(item.get("volume", 0) or 0),
            })
        except (TypeError, ValueError, KeyError):
            continue

    if len(candles) < 100:
        return None

    meta = data.get("meta") or {}

    return {
        "candles": candles,
        "name": str(meta.get("name") or "").strip(),
        "exchange": str(meta.get("exchange") or "").strip(),
    }


def cache_series(symbol, market, interval, series):
    if not series:
        return

    with series_cache_lock:
        SERIES_CACHE[(market, symbol, interval)] = {
            "updated": time.time(),
            "data": series,
        }


def get_cached_series(symbol, market, interval):
    with series_cache_lock:
        item = SERIES_CACHE.get((market, symbol, interval))

        if item and time.time() - item["updated"] < SERIES_CACHE_TTL:
            return item["data"]

    return None


def get_series(symbol, market, interval=PRIMARY_TIMEFRAME):
    cached = get_cached_series(symbol, market, interval)
    if cached:
        return cached

    params = {
        "symbol": symbol,
        "interval": interval,
        "outputsize": OUTPUTSIZE,
        "format": "JSON",
        "adjust": "splits",
    }

    if market == "US":
        params["prepost"] = "true"

    data = td_request(
        "/time_series",
        params,
        credit_cost=1,
    )

    # Some plans/feeds may reject prepost.
    if data is None and market == "US":
        params.pop("prepost", None)
        data = td_request(
            "/time_series",
            params,
            credit_cost=1,
        )

    series = parse_series_payload(data)

    if series:
        cache_series(symbol, market, interval, series)

    return series


def parse_batch_response(data):
    if not isinstance(data, dict):
        return []

    result = []

    for key, value in data.items():
        if isinstance(value, dict) and "values" in value:
            result.append((str(key), value))

    return result


def batch_load_series(symbols, market, interval=PRIMARY_TIMEFRAME):
    """
    Batch request for up to 8 symbols.
    The provider still counts credits per symbol; batching only reduces
    HTTP overhead. We therefore reserve len(batch) credits.
    """
    loaded = 0

    for start in range(0, len(symbols), BATCH_SYMBOLS):
        batch = symbols[start:start + BATCH_SYMBOLS]

        # Do not make a request if the complete batch cannot be reserved.
        cost = len(batch)

        params = {
            "symbol": ",".join(
                quote(str(x), safe="/:.-") for x in batch
            ),
            "interval": interval,
            "outputsize": OUTPUTSIZE,
            "format": "JSON",
            "adjust": "splits",
        }

        if market == "US":
            params["prepost"] = "true"

        data = td_request(
            "/time_series",
            params,
            credit_cost=cost,
        )

        if data is None and market == "US":
            params.pop("prepost", None)
            data = td_request(
                "/time_series",
                params,
                credit_cost=cost,
            )

        if data is None:
            continue

        for key, payload in parse_batch_response(data):
            series = parse_series_payload(payload)
            if series:
                cache_series(key, market, interval, series)
                loaded += 1

    return loaded


# ============================================================
# US / CRYPTO SYMBOL DISCOVERY
# ============================================================

def extract_symbols(data):
    if isinstance(data, dict):
        rows = data.get("data", [])
    elif isinstance(data, list):
        rows = data
    else:
        rows = []

    symbols = []

    for item in rows:
        if isinstance(item, dict) and item.get("symbol"):
            symbols.append(str(item["symbol"]).strip())

    return list(dict.fromkeys(symbols))


def get_us_symbols():
    data = td_request(
        "/stocks",
        {"country": "United States"},
        credit_cost=1,
    )

    symbols = extract_symbols(data)

    if not symbols:
        for exchange in ("NASDAQ", "NYSE", "AMEX"):
            data = td_request(
                "/stocks",
                {"exchange": exchange},
                credit_cost=1,
            )
            symbols.extend(extract_symbols(data))

    return sorted(set(symbols), key=str.upper)[:US_MAX_SYMBOLS]


def get_crypto_symbols():
    data = td_request(
        "/cryptocurrencies",
        {},
        credit_cost=1,
    )

    return sorted(set(extract_symbols(data)), key=str.upper)


def get_symbols(market, loader):
    now = time.time()

    with symbol_cache_lock:
        item = SYMBOL_CACHE[market]

        if item["symbols"] and now - item["updated"] < SYMBOL_REFRESH_SECONDS:
            return list(item["symbols"])

    symbols = loader()

    if symbols:
        with symbol_cache_lock:
            SYMBOL_CACHE[market] = {
                "symbols": list(symbols),
                "updated": now,
            }

    return symbols


# ============================================================
# TECHNICAL HELPERS
# ============================================================

def support_resistance(candles):
    if len(candles) < 30:
        return None, None

    recent = candles[-50:]

    return (
        min(c["low"] for c in recent),
        max(c["high"] for c in recent),
    )


def calculate_trend(candles):
    closes = [c["close"] for c in candles]

    e10 = ema(closes, EMA_FAST)
    e14 = ema(closes, EMA_MID)
    e15 = ema(closes, EMA_MOMENTUM)
    e25 = ema(closes, EMA_TRIGGER)
    e50 = ema(closes, EMA_SLOW)
    e200 = ema(closes, EMA_LONG)

    if None in (e10, e14, e15, e25, e50, e200):
        return "NEUTRAL"

    bullish = 0
    bearish = 0

    checks = [
        e10 > e14,
        e14 > e25,
        e15 > e25,
        e50 > e200,
        closes[-1] > e200,
    ]

    bullish = sum(checks)
    bearish = len(checks) - bullish

    if bullish >= 3:
        return "UP"

    if bearish >= 3:
        return "DOWN"

    return "NEUTRAL"


def persistent_trend(market, symbol, current):
    key = f"{market}:{symbol}"

    if current == "NEUTRAL":
        with state_lock:
            return TREND_STATE.get(key, "NEUTRAL")

    with state_lock:
        previous = TREND_STATE.get(key)

        if previous is None:
            TREND_STATE[key] = current
            REVERSAL_COUNT[key] = 0
            return current

        if previous == current:
            REVERSAL_COUNT[key] = 0
            return previous

        count = REVERSAL_COUNT.get(key, 0) + 1
        REVERSAL_COUNT[key] = count

        if count >= 2:
            TREND_STATE[key] = current
            REVERSAL_COUNT[key] = 0
            return current

        return previous


def calculate_power(candles):
    recent = candles[-20:]

    buy = 0.0
    sell = 0.0

    has_volume = sum(c["volume"] for c in recent) > 0

    for c in recent:
        if has_volume:
            amount = c["volume"]
        else:
            amount = 1.0

        if c["close"] > c["open"]:
            buy += amount
        elif c["close"] < c["open"]:
            sell += amount
        else:
            buy += amount * 0.5
            sell += amount * 0.5

    total = buy + sell

    if total <= 0:
        return 50.0, 50.0

    return buy / total * 100.0, sell / total * 100.0


def volume_strength(candles):
    volumes = [c["volume"] for c in candles]

    if len(volumes) < VOLUME_LENGTH + 1:
        return 1.0

    if sum(volumes[-VOLUME_LENGTH:]) <= 0:
        return 1.0

    average = sma(volumes[:-1], VOLUME_LENGTH)

    if not average:
        return 1.0

    return volumes[-1] / average


def detect_smart_movements(candles, trend, volume_ratio, buy_power,
                           sell_power, atr_value, rsi_value):
    recent = candles[-20:]

    if len(recent) < 10:
        return {
            "maker": 0,
            "speculators": False,
            "accumulation": False,
            "unusual": False,
        }

    closes = [c["close"] for c in recent]
    ranges = [abs(c["high"] - c["low"]) for c in recent]

    avg_range = sum(ranges[:-1]) / max(1, len(ranges) - 1)
    current_range = ranges[-1]

    price_move = (
        (closes[-1] - closes[0]) / closes[0] * 100
        if closes[0] else 0
    )

    unusual = (
        (volume_ratio >= 2.0 and abs(price_move) >= 1.0)
        or volume_ratio >= 3.0
    )

    accumulation = (
        volume_ratio >= 1.5
        and buy_power >= 58
        and (
            trend == "UP"
            or (rsi_value is not None and rsi_value < 60)
        )
    )

    speculators = (
        (volume_ratio >= 2.0 and abs(price_move) >= 2.0)
        or (
            avg_range > 0
            and current_range >= avg_range * 1.8
        )
    )

    maker = 0

    if unusual and buy_power >= 65:
        maker = 1
    elif unusual and sell_power >= 65:
        maker = -1
    elif accumulation:
        maker = 1

    return {
        "maker": maker,
        "speculators": speculators,
        "accumulation": accumulation,
        "unusual": unusual,
    }


# ============================================================
# PINE-LIKE SIGNAL ENGINE
# ============================================================

def pine_sma_series(values, length):
    out = [None] * len(values)

    if len(values) < length:
        return out

    for i in range(length - 1, len(values)):
        out[i] = sum(values[i-length+1:i+1]) / length

    return out


def pine_ema_series(values, length):
    out = [None] * len(values)

    if len(values) < length:
        return out

    value = sum(values[:length]) / length
    out[length - 1] = value

    alpha = 2.0 / (length + 1.0)

    for i in range(length, len(values)):
        value = (values[i] - value) * alpha + value
        out[i] = value

    return out


def cross_over(a, b, i):
    return (
        i > 0
        and a[i] is not None
        and b[i] is not None
        and a[i-1] is not None
        and b[i-1] is not None
        and a[i] > b[i]
        and a[i-1] <= b[i-1]
    )


def cross_under(a, b, i):
    return (
        i > 0
        and a[i] is not None
        and b[i] is not None
        and a[i-1] is not None
        and b[i-1] is not None
        and a[i] < b[i]
        and a[i-1] >= b[i-1]
    )


def confirmed_pivots(values, left=5, right=5, is_high=False):
    pivots = []

    for i in range(left, len(values) - right):
        window = values[i-left:i+right+1]

        if is_high and values[i] == max(window):
            pivots.append(i)

        if not is_high and values[i] == min(window):
            pivots.append(i)

    return pivots


def pine_indicator_parity(candles):
    closes = [c["close"] for c in candles]
    opens = [c["open"] for c in candles]
    highs = [c["high"] for c in candles]
    lows = [c["low"] for c in candles]
    volumes = [c["volume"] for c in candles]

    n = len(candles)
    i = n - 1

    ema7 = pine_ema_series(closes, 7)
    ema14 = pine_ema_series(closes, 14)
    ema25 = pine_ema_series(closes, 25)
    ema50 = pine_ema_series(closes, 50)
    ema180 = pine_ema_series(closes, 180)
    ema320 = pine_ema_series(closes, 320)
    ema380 = pine_ema_series(closes, 380)
    ema200 = pine_ema_series(closes, 200)

    rsi_series = [
        rsi(closes[:j+1], 14)
        for j in range(n)
    ]

    atr_series = [
        atr(
            highs[:j+1],
            lows[:j+1],
            closes[:j+1],
            14
        )
        for j in range(n)
    ]

    atr_sma20 = pine_sma_series(
        [x if x is not None else 0.0 for x in atr_series],
        20
    )

    bull_ema = (
        all(x is not None for x in
            (ema7[i], ema14[i], ema25[i], ema50[i]))
        and ema7[i] > ema14[i] > ema25[i] > ema50[i]
    )

    bear_ema = (
        all(x is not None for x in
            (ema7[i], ema14[i], ema25[i], ema50[i]))
        and ema7[i] < ema14[i] < ema25[i] < ema50[i]
    )

    vol_filter = (
        atr_series[i] is not None
        and atr_sma20[i] is not None
        and atr_series[i] > atr_sma20[i]
    )

    strong_buy = cross_over(closes, ema25, i) and bull_ema and vol_filter
    strong_sell = cross_under(closes, ema25, i) and bear_ema and vol_filter

    # Doji breakout.
    waiting = False
    doji_high = None
    doji_low = None
    wait_bars = 0
    doji_buy = False
    doji_sell = False

    for j in range(n):
        body = abs(closes[j] - opens[j])
        rng = highs[j] - lows[j]
        is_doji = rng > 0 and body <= rng * 0.10

        if is_doji and not waiting:
            waiting = True
            doji_high = highs[j]
            doji_low = lows[j]
            wait_bars = 0

        if waiting:
            wait_bars += 1

        buy_now = (
            waiting
            and doji_high is not None
            and closes[j] > doji_high
        )

        sell_now = (
            waiting
            and doji_low is not None
            and closes[j] < doji_low
        )

        if buy_now or sell_now:
            doji_buy = buy_now
            doji_sell = sell_now
            waiting = False
            doji_high = None
            doji_low = None
            wait_bars = 0
        elif wait_bars >= 10:
            waiting = False
            doji_high = None
            doji_low = None
            wait_bars = 0

    # Hidden divergence.
    hidden_bull = False
    hidden_bear = False

    low_pivots = confirmed_pivots(lows, 5, 5, False)
    high_pivots = confirmed_pivots(highs, 5, 5, True)

    if len(low_pivots) >= 2:
        p1, p2 = low_pivots[-2], low_pivots[-1]

        if rsi_series[p1] is not None and rsi_series[p2] is not None:
            hidden_bull = (
                lows[p2] > lows[p1]
                and rsi_series[p2] < rsi_series[p1]
            )

    if len(high_pivots) >= 2:
        p1, p2 = high_pivots[-2], high_pivots[-1]

        if rsi_series[p1] is not None and rsi_series[p2] is not None:
            hidden_bear = (
                highs[p2] < highs[p1]
                and rsi_series[p2] > rsi_series[p1]
            )

    volume_sma20 = pine_sma_series(volumes, 20)

    ema_buy_filter = (
        ema200[i] is not None
        and closes[i] > ema200[i]
    )

    ema_sell_filter = (
        ema200[i] is not None
        and closes[i] < ema200[i]
    )

    rsi_buy_filter = (
        rsi_series[i] is not None
        and rsi_series[i] > 50
    )

    rsi_sell_filter = (
        rsi_series[i] is not None
        and rsi_series[i] < 50
    )

    volume_filter = (
        volume_sma20[i] is not None
        and volumes[i] > volume_sma20[i]
    )

    final_buy = (
        (doji_buy or hidden_bull)
        and ema_buy_filter
        and rsi_buy_filter
        and volume_filter
    )

    final_sell = (
        (doji_sell or hidden_bear)
        and ema_sell_filter
        and rsi_sell_filter
        and volume_filter
    )

    # Golden Candle PRO.
    avg_volume = pine_sma_series(volumes, 20)

    golden_first = False
    golden_active = False

    for j in range(n):
        rng = highs[j] - lows[j]
        body = abs(closes[j] - opens[j])

        body_ratio = body / rng if rng > 0 else 0
        bull_candle = closes[j] > opens[j]
        strong_body = body_ratio >= 0.45

        ema_bull = (
            ema7[j] is not None
            and ema25[j] is not None
            and ema7[j] > ema25[j]
        )

        price_bull = (
            ema7[j] is not None
            and closes[j] > ema7[j]
        )

        rsi_bull = (
            rsi_series[j] is not None
            and rsi_series[j] >= 50
        )

        volume_bull = (
            volumes[j] <= 0
            or (
                avg_volume[j] is not None
                and volumes[j] >= avg_volume[j] * 1.10
            )
        )

        early_rise = (
            bull_candle
            and strong_body
            and price_bull
            and rsi_bull
            and volume_bull
            and (
                cross_over(closes, ema7, j)
                or cross_over(ema7, ema25, j)
                or (
                    j > 0
                    and closes[j] > highs[j-1]
                    and closes[j-1] <= opens[j-1]
                )
            )
        )

        if early_rise:
            golden_active = True

        trend_break = (
            (
                ema7[j] is not None
                and closes[j] < ema7[j]
            )
            or (
                ema7[j] is not None
                and ema25[j] is not None
                and ema7[j] < ema25[j]
            )
            or (
                rsi_series[j] is not None
                and rsi_series[j] < 45
            )
        )

        if trend_break:
            golden_active = False

        if j == n - 1:
            golden_first = early_rise

    golden_continue = golden_active and not golden_first

    # VWAP series / crossover.
    vwap_series = []

    pv = 0.0
    volume_sum = 0.0

    for j in range(n):
        typical = (highs[j] + lows[j] + closes[j]) / 3.0
        pv += typical * volumes[j]
        volume_sum += volumes[j]

        v = pv / volume_sum if volume_sum > 0 else None
        vwap_series.append(v)

    vwap_buy = False
    vwap_sell = False

    if (
        i > 0
        and vwap_series[i] is not None
        and vwap_series[i-1] is not None
    ):
        avg_vol = avg_volume[i]

        strong_volume = (
            volumes[i] > avg_vol * 1.10
            if avg_vol is not None
            else True
        )

        vwap_buy = (
            closes[i] > vwap_series[i]
            and closes[i-1] <= vwap_series[i-1]
            and strong_volume
        )

        vwap_sell = (
            closes[i] < vwap_series[i]
            and closes[i-1] >= vwap_series[i-1]
            and strong_volume
        )

    return {
        "final_buy": final_buy,
        "final_sell": final_sell,
        "doji_buy": doji_buy,
        "doji_sell": doji_sell,
        "hidden_bull": hidden_bull,
        "hidden_bear": hidden_bear,
        "strong_buy": strong_buy,
        "strong_sell": strong_sell,
        "golden_first": golden_first,
        "golden_continue": golden_continue,
        "golden_active": golden_active,
        "vwap_buy": vwap_buy,
        "vwap_sell": vwap_sell,
        "rsi": rsi_series[i],
        "ema7": ema7[i],
        "ema14": ema14[i],
        "ema25": ema25[i],
        "ema50": ema50[i],
        "ema180": ema180[i],
        "ema320": ema320[i],
        "ema380": ema380[i],
        "ema200": ema200[i],
        "volume_sma20": volume_sma20[i],
        "vwap": vwap_series[i],
    }


# ============================================================
# ANALYSIS
# ============================================================

def calculate_targets(price, atr_value, direction, count=8):
    if not price or not atr_value or atr_value <= 0:
        return []

    result = []

    multipliers = list(ATR_TARGETS)

    while len(multipliers) < count:
        # Expanding continuation levels after TP8.
        next_multiplier = multipliers[-1] + max(
            1.5,
            multipliers[-1] * 0.25
        )
        multipliers.append(next_multiplier)

    for multiplier in multipliers[:count]:
        if direction == "UP":
            result.append(price + atr_value * multiplier)
        else:
            result.append(price - atr_value * multiplier)

    return result


def calculate_stop_loss(price, atr_value, support, resistance, direction):
    if not price or not atr_value or atr_value <= 0:
        return None

    if direction == "UP":
        atr_stop = price - atr_value * STOP_ATR_MULTIPLIER

        if support is not None and support < price:
            structural = support - atr_value * 0.25
            return max(0.0, min(atr_stop, structural))

        return max(0.0, atr_stop)

    atr_stop = price + atr_value * STOP_ATR_MULTIPLIER

    if resistance is not None and resistance > price:
        structural = resistance + atr_value * 0.25
        return max(0.0, max(atr_stop, structural))

    return max(0.0, atr_stop)


def analyze_us_crypto(symbol, market):
    series = get_series(symbol, market, PRIMARY_TIMEFRAME)

    if not series:
        return None

    candles = series["candles"]
    closes = [c["close"] for c in candles]
    highs = [c["high"] for c in candles]
    lows = [c["low"] for c in candles]
    volumes = [c["volume"] for c in candles]

    if len(closes) < 100:
        return None

    price = closes[-1]
    previous_close = closes[-2]

    if market == "US" and price < MIN_US_PRICE:
        return None

    e10 = ema(closes, EMA_FAST)
    e14 = ema(closes, EMA_MID)
    e15 = ema(closes, EMA_MOMENTUM)
    e25 = ema(closes, EMA_TRIGGER)
    e50 = ema(closes, EMA_SLOW)
    e200 = ema(closes, EMA_LONG)

    rsi_value = rsi(closes, RSI_LENGTH)
    atr_value = atr(highs, lows, closes, ATR_LENGTH)
    vwap_value = vwap(highs, lows, closes, volumes)

    support, resistance = support_resistance(candles)
    buy_power, sell_power = calculate_power(candles)
    volume_ratio = volume_strength(candles)

    raw_trend = calculate_trend(candles)
    trend = persistent_trend(market, symbol, raw_trend)

    pine = pine_indicator_parity(candles)

    if pine["final_buy"]:
        signal = "BUY"
        signal_text = "🟢 شراء قوي — SMART BUY"
    elif pine["final_sell"]:
        signal = "SELL"
        signal_text = "🔴 بيع قوي — SMART SELL"
    elif pine["golden_first"]:
        signal = "BUY"
        signal_text = "🟡 شراء — GOLDEN CANDLE"
    elif pine["vwap_buy"]:
        signal = "BUY"
        signal_text = "🟢 شراء — VWAP"
    elif pine["vwap_sell"]:
        signal = "SELL"
        signal_text = "🔴 بيع — VWAP"
    elif pine["strong_buy"]:
        signal = "BUY"
        signal_text = "🟢 شراء قوي — EMA"
    elif pine["strong_sell"]:
        signal = "SELL"
        signal_text = "🔴 بيع قوي — EMA"
    else:
        signal = "WAIT"
        signal_text = "⚪ انتظار"

    # Score with VWAP deliberately important.
    score = 0

    if e10 is not None and e14 is not None:
        if (
            signal == "BUY" and e10 > e14
        ) or (
            signal == "SELL" and e10 < e14
        ):
            score += 10

    if e14 is not None and e25 is not None:
        if (
            signal == "BUY" and e14 > e25
        ) or (
            signal == "SELL" and e14 < e25
        ):
            score += 10

    if e25 is not None and e50 is not None:
        if (
            signal == "BUY" and e25 > e50
        ) or (
            signal == "SELL" and e25 < e50
        ):
            score += 10

    if e50 is not None and e200 is not None:
        if (
            signal == "BUY" and e50 > e200
        ) or (
            signal == "SELL" and e50 < e200
        ):
            score += 10

    if rsi_value is not None:
        if (
            signal == "BUY" and rsi_value >= 55
        ) or (
            signal == "SELL" and rsi_value <= 45
        ):
            score += 10

    # VWAP = 15 points.
    if vwap_value is not None:
        if (
            signal == "BUY" and price > vwap_value
        ) or (
            signal == "SELL" and price < vwap_value
        ):
            score += 15

    if (
        signal == "BUY" and buy_power >= 55
    ) or (
        signal == "SELL" and sell_power >= 55
    ):
        score += 10

    if volume_ratio >= 1.20:
        score += 10

    if (
        signal == "BUY" and pine.get("golden_first")
    ) or (
        signal == "SELL" and pine.get("strong_sell")
    ):
        score += 5

    score = min(100, int(score))

    smart = detect_smart_movements(
        candles,
        trend,
        volume_ratio,
        buy_power,
        sell_power,
        atr_value,
        rsi_value,
    )

    targets = []
    stop_loss = None

    if signal != "WAIT":
        direction = "UP" if signal == "BUY" else "DOWN"
        targets = calculate_targets(
            price,
            atr_value,
            direction,
            8,
        )

        stop_loss = calculate_stop_loss(
            price,
            atr_value,
            support,
            resistance,
            direction,
        )

    return {
        "symbol": symbol,
        "name": series.get("name") or "",
        "market": market,
        "price": price,
        "previous_close": previous_close,
        "entry_price": price,
        "ema10": e10,
        "ema14": e14,
        "ema15": e15,
        "ema25": e25,
        "ema50": e50,
        "ema200": e200,
        "rsi": rsi_value,
        "atr": atr_value,
        "vwap": vwap_value,
        "support": support,
        "resistance": resistance,
        "buy_power": buy_power,
        "sell_power": sell_power,
        "volume_ratio": volume_ratio,
        "trend": trend,
        "score": score,
        "signal": signal,
        "signal_text": signal_text,
        "targets": targets,
        "stop_loss": stop_loss,
        "smart": smart,
        "pine": pine,
        "timeframe": PRIMARY_TIMEFRAME,
        "news": "⚪ لم تُفحص بعد",
    }


# ============================================================
# NEWS — ONLY FOR STRONG SIGNALS
# ============================================================

def news_sentiment(symbol):
    now = time.time()

    cached = NEWS_CACHE.get(symbol)

    if cached and now - cached["time"] < NEWS_CACHE_TTL:
        return cached["value"]

    data = td_request(
        "/news",
        {
            "symbol": symbol,
            "limit": 10,
        },
        credit_cost=1,
    )

    if not data:
        value = "⚪ غير متاح"
        NEWS_CACHE[symbol] = {"time": now, "value": value}
        return value

    if isinstance(data, dict):
        articles = data.get("news", [])
    elif isinstance(data, list):
        articles = data
    else:
        articles = []

    positive = 0
    negative = 0

    for article in articles:
        if not isinstance(article, dict):
            continue

        text = (
            str(article.get("title", ""))
            + " "
            + str(article.get("description", ""))
        ).lower()

        positive += sum(
            1 for word in POSITIVE_WORDS if word in text
        )

        negative += sum(
            1 for word in NEGATIVE_WORDS if word in text
        )

    if positive > negative:
        value = "🟢 إيجابي"
    elif negative > positive:
        value = "🔴 سلبي"
    else:
        value = "⚪ محايد"

    NEWS_CACHE[symbol] = {"time": now, "value": value}
    return value


# ============================================================
# TARGET CONTINUATION
# ============================================================

def update_target_state(result):
    """
    TP1..TP8 are generated initially.
    Once price reaches the last target, a new target is opened.
    The process can continue for strong/momentum moves.
    """
    if result["signal"] not in ("BUY", "SELL"):
        return None

    key = f"{result['market']}:{result['symbol']}"
    direction = "UP" if result["signal"] == "BUY" else "DOWN"

    price = result["price"]
    atr_value = result["atr"]

    if not atr_value or atr_value <= 0:
        return None

    with state_lock:
        state = TARGET_STATE.get(key)

        if state is None or state.get("direction") != direction:
            initial = calculate_targets(
                result["entry_price"],
                atr_value,
                direction,
                8,
            )

            if not initial:
                return None

            TARGET_STATE[key] = {
                "direction": direction,
                "last_target": initial[-1],
                "next_multiplier": 9.5,
                "highest_reached": 0,
            }

            return {
                "new_target": None,
                "reached": 0,
            }

        last_target = state["last_target"]

        reached = False

        if direction == "UP" and price >= last_target:
            reached = True

        if direction == "DOWN" and price <= last_target:
            reached = True

        if not reached:
            return None

        multiplier = state["next_multiplier"]

        if direction == "UP":
            new_target = price + atr_value * 1.25
        else:
            new_target = price - atr_value * 1.25

        state["last_target"] = new_target
        state["next_multiplier"] = multiplier + 1.5
        state["highest_reached"] += 1

        return {
            "new_target": new_target,
            "reached": state["highest_reached"],
        }


# ============================================================
# TELEGRAM
# ============================================================

DIRECTION_GIF_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "telegram_gifs"
)

UP_GIF = os.path.join(DIRECTION_GIF_DIR, "green_up.gif")
DOWN_GIF = os.path.join(DIRECTION_GIF_DIR, "red_down.gif")


def ensure_direction_gifs():
    try:
        os.makedirs(DIRECTION_GIF_DIR, exist_ok=True)

        def create(path, direction, title):
            if os.path.exists(path):
                return

            frames = []

            for i in range(8):
                img = Image.new(
                    "RGB",
                    (420, 260),
                    (18, 18, 24),
                )

                draw = ImageDraw.Draw(img)

                pulse = i if i <= 4 else 8 - i

                if direction == "up":
                    points = [
                        (210, 40 - pulse * 2),
                        (90, 155 - pulse * 2),
                        (160, 155 - pulse * 2),
                        (160, 215),
                        (260, 215),
                        (260, 155 - pulse * 2),
                        (330, 155 - pulse * 2),
                    ]
                    fill = (40, 220, 100)
                    label = "UP"
                else:
                    points = [
                        (90, 95 + pulse * 2),
                        (160, 95 + pulse * 2),
                        (160, 45),
                        (260, 45),
                        (260, 95 + pulse * 2),
                        (330, 95 + pulse * 2),
                        (210, 220 + pulse * 2),
                    ]
                    fill = (240, 55, 65)
                    label = "DOWN"

                draw.polygon(points, fill=fill)
                draw.text((145, 15), title, fill=(245, 245, 245))
                draw.text((175, 225), label, fill=fill)

                frames.append(img)

            frames[0].save(
                path,
                save_all=True,
                append_images=frames[1:],
                duration=140,
                loop=0,
                optimize=True,
            )

        create(UP_GIF, "up", "AI PRO MAX")
        create(DOWN_GIF, "down", "AI PRO MAX")

        return True

    except Exception as exc:
        print("⚠️ GIF:", exc)
        return False


def tradingview_url(result):
    symbol = str(result.get("symbol", "")).strip()

    if not symbol:
        return None

    return (
        "https://www.tradingview.com/chart/?symbol="
        + quote(symbol, safe="")
    )


def telegram_markup(url):
    if not url:
        return None

    import json

    return json.dumps({
        "inline_keyboard": [[
            {
                "text": "📈 فتح في TradingView",
                "url": url,
            }
        ]]
    }, ensure_ascii=False)


def telegram_send_animation(
    token,
    gif_path,
    caption,
    url=None,
):
    if (
        not token
        or not CHAT_ID
        or not os.path.exists(gif_path)
    ):
        return False

    try:
        session = get_session()

        with open(gif_path, "rb") as fh:
            response = session.post(
                f"https://api.telegram.org/bot{token}/sendAnimation",
                data={
                    "chat_id": CHAT_ID,
                    "caption": caption,
                    "parse_mode": "HTML",
                    "reply_markup": telegram_markup(url)
                    if url else None,
                },
                files={"animation": fh},
                timeout=(10, 60),
            )

        return response.ok

    except Exception:
        return False


def telegram_send(token, text, url=None):
    if not token or not CHAT_ID:
        return False

    try:
        response = get_session().post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data={
                "chat_id": CHAT_ID,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
                "reply_markup": telegram_markup(url)
                if url else None,
            },
            timeout=(10, 30),
        )

        return response.ok

    except Exception:
        return False


def send_direction(token, result):
    if result["trend"] == "UP":
        return telegram_send_animation(
            token,
            UP_GIF,
            "🟢 <b>اتجاه صاعد مستمر</b>\n⬆️ مستمر حتى انعكاس مؤكد",
            tradingview_url(result),
        )

    if result["trend"] == "DOWN":
        return telegram_send_animation(
            token,
            DOWN_GIF,
            "🔴 <b>اتجاه هابط مستمر</b>\n⬇️ مستمر حتى انعكاس مؤكد",
            tradingview_url(result),
        )

    return False


def send_smart_animation(token, result):
    maker = result.get("smart", {}).get("maker", 0)

    if not maker:
        return False

    if maker > 0:
        path = UP_GIF
        caption = "🐋 ↑ حركة صنّاع السهم"
    else:
        path = DOWN_GIF
        caption = "🐋 ↓ حركة صنّاع السهم"

    return telegram_send_animation(
        token,
        path,
        caption,
        tradingview_url(result),
    )


# ============================================================
# MESSAGE
# ============================================================

def fmt(value):
    if value is None:
        return "-"

    value = float(value)

    if abs(value) >= 1_000_000_000:
        return f"{value / 1_000_000_000:.2f}B"

    if abs(value) >= 1_000_000:
        return f"{value / 1_000_000:.2f}M"

    if abs(value) >= 1_000:
        return f"{value / 1_000:.2f}K"

    if abs(value) >= 1:
        return f"{value:.4f}"

    return f"{value:.6f}"


def pct(value):
    return "-" if value is None else f"{float(value):.1f}%"


def esc(value):
    return (
        str(value if value is not None else "-")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def build_message(result):
    market = result["market"]

    market_name = {
        "US": "🇺🇸 السوق الأمريكي (US)",
        "CRYPTO": "🪙 العملات الرقمية (CRYPTO)",
    }.get(market, market)

    symbol = esc(result["symbol"])

    if result["signal"] == "BUY":
        signal_badge = "🟢 <b>شراء قوي</b>"
    elif result["signal"] == "SELL":
        signal_badge = "🔴 <b>بيع قوي</b>"
    else:
        signal_badge = "⚪ <b>انتظار</b>"

    if result["trend"] == "UP":
        trend_text = "🟢 صعود — مستمر حتى انعكاس مؤكد"
    elif result["trend"] == "DOWN":
        trend_text = "🔴 هبوط — مستمر حتى انعكاس مؤكد"
    else:
        trend_text = "⚪ محايد"

    smart = result.get("smart", {})
    pine = result.get("pine", {})

    movement_lines = []

    if smart.get("maker", 0) > 0:
        movement_lines.append("🐋 <b>↑ حركة صنّاع السهم</b>")
    elif smart.get("maker", 0) < 0:
        movement_lines.append("🐋 <b>↓ حركة صنّاع السهم</b>")

    if smart.get("speculators"):
        movement_lines.append("⚡ <b>حركة مضاربين قوية</b>")

    if smart.get("unusual"):
        movement_lines.append("🔎 <b>رصد حركة غير اعتيادية</b>")

    if smart.get("accumulation"):
        movement_lines.append("💰 <b>عمليات التجميع</b>")

    vwap_value = result.get("vwap")

    if vwap_value is None:
        vwap_text = "⚪ غير متاح"
    elif result["price"] > vwap_value:
        vwap_text = "🟢 فوق VWAP"
    else:
        vwap_text = "🔴 تحت VWAP"

    rsi_value = pine.get("rsi")

    if rsi_value is None:
        rsi_text = "⚪ غير متاح"
    elif rsi_value > 50:
        rsi_text = "🟢 أعلى 50"
    else:
        rsi_text = "🔴 أقل 50"

    if pine.get("golden_first"):
        golden = "🟡 <b>مؤكدة — صعود</b>"
    elif pine.get("golden_continue"):
        golden = "🟡 <b>استمرارية صعود</b>"
    else:
        golden = "🟡 غير مؤكدة"

    if pine.get("final_buy"):
        ai_text = "SMART BUY"
    elif pine.get("final_sell"):
        ai_text = "SMART SELL"
    else:
        ai_text = "لا توجد إشارة نهائية"

    change_pct = None

    if result.get("previous_close") not in (None, 0):
        change_pct = (
            (result["price"] - result["previous_close"])
            / result["previous_close"]
            * 100
        )

    lines = [
        "💀🚀 <b>AI PRO MAX SIGNAL</b>",
        "",
        market_name,
        f"<b>{symbol}</b>",
        "",
        f"{signal_badge}    🎯 قوة الإشارة: <b>{result['score']}/100</b>",
    ]

    if movement_lines:
        lines.extend(["", *movement_lines])

    lines.extend([
        "",
        f"🔄 <b>الاستمرارية:</b> {trend_text}",
        "",
        "🧩 <b>تأكيد المؤشرات</b>",
        f"🧠 RSI 14: <b>{fmt(rsi_value)}</b>  {rsi_text}",
        f"🟡 الشمعة الذهبية: {golden}",
        f"🤖 AI PRO MAX: <b>{ai_text}</b>",
        "",
        f"💰 <b>السعر:</b> {fmt(result['price'])}"
        + (
            f"  ({change_pct:+.2f}%)"
            if change_pct is not None else ""
        ),
        f"📊 <b>VWAP:</b> {fmt(vwap_value)}  {vwap_text}",
        f"🧠 <b>RSI 14:</b> {fmt(result['rsi'])}",
        f"📐 <b>ATR 14:</b> {fmt(result['atr'])}",
        f"🛑 <b>وقف الخسارة:</b> {fmt(result['stop_loss'])}",
        "",
        f"📈 <b>EMA 10:</b> {fmt(result['ema10'])}",
        f"📈 <b>EMA 14:</b> {fmt(result['ema14'])}",
        f"📈 <b>EMA 15:</b> {fmt(result['ema15'])}",
        f"📈 <b>EMA 25:</b> {fmt(result['ema25'])}",
        f"📈 <b>EMA 50:</b> {fmt(result['ema50'])}",
        f"📈 <b>EMA 200:</b> {fmt(result['ema200'])}",
        "",
        f"🟢 <b>قوة الشراء:</b> {pct(result['buy_power'])}",
        f"🔴 <b>قوة البيع:</b> {pct(result['sell_power'])}",
        f"📦 <b>قوة الحجم:</b> {result['volume_ratio']:.2f}x",
        "",
        f"🛡️ <b>الدعم:</b> {fmt(result['support'])}",
        f"🚧 <b>المقاومة:</b> {fmt(result['resistance'])}",
        f"📊 <b>اتجاه السوق:</b> {trend_text}",
    ])

    # News only for a strong signal.
    if result["score"] >= NEWS_SCORE_MIN:
        lines.append(
            f"📰 <b>أخبار السهم:</b> {result.get('news', '⚪ غير متاحة')}"
        )

    # Initial targets.
    if result.get("targets"):
        lines.extend([
            "",
            "🎯 <b>أهداف ATR — 8 أهداف</b>",
        ])

        for idx, target in enumerate(result["targets"], 1):
            change = (
                (target - result["price"])
                / result["price"]
                * 100
                if result["price"] else 0
            )

            lines.append(
                f"TP{idx}: <b>{fmt(target)}</b> ({change:+.2f}%)"
            )

        lines.append(
            "♾️ <b>بعد TP8:</b> الأهداف تفتح تلقائيًا "
            "مع استمرار الاتجاه والحركة."
        )

    lines.extend([
        "",
        "🟢/🔴 الاتجاه يستمر حتى انعكاس مؤكد.",
        f"⏱️ {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC",
    ])

    return "\n".join(lines)


def build_continuation_message(result, target_info):
    direction = "صعود" if result["signal"] == "BUY" else "هبوط"

    if result["signal"] == "BUY":
        icon = "🟢"
    else:
        icon = "🔴"

    new_target = target_info.get("new_target")

    return (
        "🚀 <b>AI PRO MAX — استمرار الحركة</b>\n\n"
        f"{icon} <b>{esc(result['symbol'])}</b>\n"
        f"🔄 الاتجاه: <b>{direction} مستمر</b>\n"
        f"🎯 تم الوصول إلى مستوى الهدف السابق\n"
        f"♾️ <b>هدف جديد:</b> {fmt(new_target)}\n"
        f"📊 <b>VWAP:</b> {fmt(result['vwap'])} "
        + (
            "🟢 فوق VWAP"
            if result["price"] > result["vwap"]
            else "🔴 تحت VWAP"
            if result["vwap"] is not None
            else "⚪ غير متاح"
        )
        + "\n"
        f"💰 السعر الحالي: <b>{fmt(result['price'])}</b>\n"
        f"🎯 قوة الإشارة: <b>{result['score']}/100</b>\n"
        "\n"
        "⚠️ الهدف التالي ديناميكي ويتحرك مع استمرار الاتجاه."
    )


# ============================================================
# DUPLICATE CONTROL
# ============================================================

def should_send(result):
    if result["signal"] == "WAIT":
        return False

    if result["score"] < MIN_SIGNAL_SCORE:
        return False

    key = f"{result['market']}:{result['symbol']}"

    current = (
        result["signal"],
        result["trend"],
    )

    with state_lock:
        previous = LAST_SIGNAL.get(key)

        if previous == current:
            return False

        LAST_SIGNAL[key] = current

    return True


# ============================================================
# TELEGRAM WORKER
# ============================================================

def enqueue(token, result):
    try:
        TELEGRAM_QUEUE.put_nowait(
            ("SIGNAL", token, result)
        )
        return True
    except queue.Full:
        print("🔴 Telegram queue full")
        return False


def enqueue_continuation(token, result, target_info):
    try:
        TELEGRAM_QUEUE.put_nowait(
            ("CONTINUATION", token, result, target_info)
        )
        return True
    except queue.Full:
        return False


def telegram_worker():
    while True:
        item = TELEGRAM_QUEUE.get()

        try:
            if item is None:
                return

            kind = item[0]

            if kind == "SIGNAL":
                _, token, result = item

                # ① Direction animation.
                send_direction(token, result)

                # ② Smart-movement animation only if detected.
                # Kept separate so the main signal remains clean.
                # It does not block the technical message.
                if result.get("smart", {}).get("maker", 0):
                    send_smart_animation(token, result)

                # News only for strong signals and only once per cache window.
                if result["score"] >= NEWS_SCORE_MIN:
                    result["news"] = news_sentiment(result["symbol"])

                message = build_message(result)

                telegram_send(
                    token,
                    message,
                    tradingview_url(result),
                )

            elif kind == "CONTINUATION":
                _, token, result, target_info = item

                message = build_continuation_message(
                    result,
                    target_info,
                )

                telegram_send(
                    token,
                    message,
                    tradingview_url(result),
                )

        except Exception as exc:
            print("🔴 Telegram worker:", exc)

        finally:
            TELEGRAM_QUEUE.task_done()


# ============================================================
# TASI / SAHMK
# ============================================================

sahmk_session = requests.Session()
sahmk_session.headers.update({
    "X-API-Key": SAHMK_API_KEY,
    "Accept-Encoding": "gzip",
    "User-Agent": "TASI-AI-PRO-MAX/Unified/1.0",
})


def sahmk(path, params=None):
    if not SAHMK_API_KEY:
        return None

    try:
        response = sahmk_session.get(
            SAHMK_BASE + path,
            params=params or {},
            timeout=(10, 30),
        )

        if response.status_code == 429:
            print("🟠 SAHMK: 429 — waiting")
            return None

        if response.status_code != 200:
            print(
                f"🔴 SAHMK HTTP {response.status_code}: {path}"
            )
            return None

        data = response.json()

        if isinstance(data, dict) and data.get("error"):
            print("🔴 SAHMK:", data.get("error"))
            return None

        return data

    except Exception as exc:
        print("🔴 SAHMK:", exc)
        return None


def market_is_active():
    now = datetime.now(RIYADH)

    # Sunday -> Thursday.
    if now.weekday() not in (6, 0, 1, 2, 3):
        return False

    minutes = now.hour * 60 + now.minute

    return (
        9 * 60 + 30
        <= minutes
        < 15 * 60
    )


def extract(rows_key, data):
    if not isinstance(data, dict):
        return []

    rows = data.get(rows_key, [])

    return rows if isinstance(rows, list) else []


def tasi_collect():
    # Exactly 3 market calls per cycle.
    summary = sahmk(
        "/market/summary/",
        {
            "index": "TASI",
            "data_mode": "delayed",
        },
    )

    gainers = sahmk(
        "/market/gainers/",
        {
            "index": "TASI",
            "limit": 50,
            "data_mode": "delayed",
        },
    )

    losers = sahmk(
        "/market/losers/",
        {
            "index": "TASI",
            "limit": 50,
            "data_mode": "delayed",
        },
    )

    return (
        summary,
        extract("gainers", gainers),
        extract("losers", losers),
    )


def tasi_score(row):
    try:
        change = abs(float(
            row.get("change_percent", 0) or 0
        ))

        volume = float(
            row.get("volume", 0) or 0
        )
    except Exception:
        return 0

    score = min(70, change * 7)

    if volume > 10_000_000:
        score += 20
    elif volume > 3_000_000:
        score += 15
    elif volume > 1_000_000:
        score += 10
    elif volume > 250_000:
        score += 5

    return int(max(0, min(100, score)))


def tasi_alert(token, row, direction):
    symbol = str(row.get("symbol", "")).strip()

    if not symbol:
        return

    try:
        change = float(
            row.get("change_percent", 0) or 0
        )
    except Exception:
        change = 0.0

    # Do not spam small moves.
    if abs(change) < 2.0:
        return

    key = f"{symbol}:{direction}"

    old = TASI_LAST_SENT.get(key)

    if old is not None and abs(change - old) < 1.0:
        return

    TASI_LAST_SENT[key] = change

    if direction == "UP":
        badge = "🟢 <b>حركة صاعدة</b> ↗️"
    else:
        badge = "🔴 <b>حركة هابطة</b> ↘️"

    price = row.get("price", "-")
    volume = row.get("volume", 0)

    text = (
        "💀🚀 <b>AI PRO MAX — تاسي</b>\n"
        "🇸🇦 <b>SAHMK</b>\n\n"
        f"📌 <b>{esc(symbol)}</b>\n"
        f"{badge}   🎯 <b>{tasi_score(row)}/100</b>\n"
        f"💰 السعر: <b>{esc(price)}</b>\n"
        f"📊 التغير: <b>{change:+.2f}%</b>\n"
        f"📦 الحجم: <b>{volume:,}</b>\n\n"
        "🔄 <b>رصد آلي من SAHMK</b>\n"
        f"🕒 {datetime.now(RIYADH).strftime('%Y-%m-%d %H:%M:%S')}"
    )

    telegram_send(
        token,
        text,
        None,
    )


def tasi_cycle():
    print("=" * 60)
    print("🇸🇦 TASI — SAHMK ONLY")
    print(datetime.now(RIYADH).strftime("%Y-%m-%d %H:%M:%S"))

    summary, gainers, losers = tasi_collect()

    if summary:
        print(
            "🟢 TASI:",
            summary.get("index_value", "-"),
            "| change=",
            summary.get("index_change_percent", "-"),
            "| mood=",
            summary.get("market_mood", "-"),
        )

    print(
        f"🟢 Gainers: {len(gainers)} | "
        f"🔴 Losers: {len(losers)}"
    )

    if gainers:
        try:
            best_up = max(
                gainers,
                key=lambda x: float(
                    x.get("change_percent", 0) or 0
                ),
            )
            tasi_alert(
                TASI_TOKEN,
                best_up,
                "UP",
            )
        except Exception as exc:
            print("🔴 TASI gainers:", exc)

    if losers:
        try:
            best_down = min(
                losers,
                key=lambda x: float(
                    x.get("change_percent", 0) or 0
                ),
            )
            tasi_alert(
                TASI_TOKEN,
                best_down,
                "DOWN",
            )
        except Exception as exc:
            print("🔴 TASI losers:", exc)


# ============================================================
# US / CRYPTO SCANNER
# ============================================================

def scanner_cycle(market, token, loader):
    if not token:
        print(f"⚠️ {market}: Telegram token missing")
        return

    symbols = get_symbols(market, loader)

    if not symbols:
        print(f"⚠️ {market}: symbol universe unavailable")
        return

    total = len(symbols)

    with state_lock:
        cursor = SCAN_CURSORS.get(market, 0) % total

    per_pass = (
        US_PER_PASS
        if market == "US"
        else CRYPTO_PER_PASS
    )

    selected = [
        symbols[(cursor + i) % total]
        for i in range(min(per_pass, total))
    ]

    with state_lock:
        SCAN_CURSORS[market] = (
            cursor + len(selected)
        ) % total

    # One batch request = up to 8 symbols, but still reserves
    # one Twelve Data credit per symbol.
    loaded = batch_load_series(
        selected,
        market,
        PRIMARY_TIMEFRAME,
    )

    print(
        f"[{market}] 🔄 {cursor + 1}"
        f"→{cursor + len(selected)}/{total} "
        f"| loaded={loaded}"
    )

    # Analyze from cache. This does not make another candle request.
    for symbol in selected:
        try:
            result = analyze_us_crypto(
                symbol,
                market,
            )

            if not result:
                continue

            if should_send(result):
                enqueue(
                    token,
                    result,
                )

            # Continuation after TP8 and beyond.
            continuation = update_target_state(result)

            if continuation and continuation.get("new_target"):
                enqueue_continuation(
                    token,
                    result,
                    continuation,
                )

        except Exception as exc:
            print(
                f"[{market}] 🔴 {symbol}: {exc}"
            )


# ============================================================
# THREADS
# ============================================================

def tasi_loop():
    while True:
        try:
            if market_is_active():
                tasi_cycle()
            else:
                print(
                    "⏸️ TASI خارج الجلسة — "
                    "الخدمة مستمرة وتنتظر."
                )
        except Exception as exc:
            print("🔴 TASI loop:", exc)

        time.sleep(TASI_SCAN_SECONDS)


def us_crypto_loop(market, token, loader):
    while True:
        try:
            # Do not touch Twelve Data if the local daily budget is closed.
            reset_td_day()

            with td_budget_lock:
                blocked = (
                    TD_RESERVED_TODAY >= TD_DAILY_LIMIT
                )

            if blocked:
                print(
                    f"🛡️ {market}: Twelve Data daily "
                    "budget reached — waiting for UTC day reset."
                )
            else:
                scanner_cycle(
                    market,
                    token,
                    loader,
                )

        except Exception as exc:
            print(
                f"🔴 {market} loop:",
                exc,
            )

        time.sleep(SCAN_INTERVAL)


def heartbeat():
    while True:
        reset_td_day()

        with td_budget_lock:
            reserved = TD_RESERVED_TODAY
            left = TD_CREDITS_LEFT

        print(
            "💀🚀 AI PRO MAX 24/7 | "
            f"TD reserved={reserved}/{TD_DAILY_LIMIT} | "
            f"provider-left={left}"
        )

        time.sleep(300)


# ============================================================
# MAIN
# ============================================================

def main():
    print("=" * 72)
    print("💀🚀 AI PRO MAX — UNIFIED TASI + US + CRYPTO")
    print("🇸🇦 TASI -> SAHMK ONLY")
    print("🇺🇸 US -> TWELVE DATA")
    print("🪙 CRYPTO -> TWELVE DATA")
    print("🛡️ TWELVE DATA LOCAL DAILY BUDGET:", TD_DAILY_LIMIT)
    print("📊 VWAP: HIGH PRIORITY")
    print("🎯 TP1..TP8 + DYNAMIC TP9+")
    print("=" * 72)

    missing = []

    if not CHAT_ID:
        missing.append("CHAT_ID")

    if not TASI_TOKEN:
        missing.append("TASI_TOKEN")

    if not US_TOKEN:
        missing.append("US_TOKEN")

    if not CRYPTO_TOKEN:
        missing.append("CRYPTO_TOKEN")

    if not SAHMK_API_KEY:
        missing.append("SAHMK_API_KEY")

    if not TWELVEDATA_API_KEY:
        missing.append("TWELVE_DATA_API_KEY")

    if missing:
        print(
            "❌ Railway Variables missing:",
            ", ".join(missing),
        )
        return

    print("🟢 Railway Variables: OK")

    if ensure_direction_gifs():
        print("🟢 Direction GIFs: OK")

    threading.Thread(
        target=telegram_worker,
        daemon=True,
        name="TelegramWorker",
    ).start()

    threading.Thread(
        target=heartbeat,
        daemon=True,
        name="Heartbeat",
    ).start()

    threading.Thread(
        target=tasi_loop,
        daemon=True,
        name="TASI",
    ).start()

    threading.Thread(
        target=us_crypto_loop,
        args=(
            "US",
            US_TOKEN,
            get_us_symbols,
        ),
        daemon=True,
        name="US",
    ).start()

    threading.Thread(
        target=us_crypto_loop,
        args=(
            "CRYPTO",
            CRYPTO_TOKEN,
            get_crypto_symbols,
        ),
        daemon=True,
        name="CRYPTO",
    ).start()

    print("🚀 ALL THREE MARKETS STARTED")

    while True:
        time.sleep(60)


if __name__ == "__main__":
    main()