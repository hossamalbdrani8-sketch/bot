# ============================================================
# AI PRO MAX — TASI + US + CRYPTO
# Stable / Low-Connection Edition
# ============================================================

import os
import time
import threading
import queue
import random
from datetime import datetime, timezone
from urllib.parse import quote
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock, local

import requests
from PIL import Image, ImageDraw

# ============================================================
# 🔐 RAILWAY VARIABLES — لا توجد أسرار داخل الكود
# ============================================================

CHAT_ID = os.getenv("CHAT_ID", "").strip()
CRYPTO_TOKEN = os.getenv("CRYPTO_TOKEN", "").strip()
TASI_TOKEN = os.getenv("TASI_TOKEN", "").strip()
US_TOKEN = os.getenv("US_TOKEN", "").strip()

TWELVEDATA_API_KEY = (
    os.getenv("TWELVE_DATA_API_KEY", "").strip()
    or os.getenv("TWELVEDATA_API_KEY", "").strip()
)

# المتغيران موجودان في Railway ونبقيهما كما هما حتى لو كان المحرك
# الحالي يعتمد Twelve Data للفحص الفني الموحد.
SIFTING_API_KEY = os.getenv("SIFTING_API_KEY", "").strip()
SAHMK_API_KEY = os.getenv("SAHMK_API_KEY", "").strip()

# ============================================================
# TELEGRAM DIRECTION ANIMATION
# ============================================================
DIRECTION_GIF_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "telegram_gifs")
UP_GIF = os.path.join(DIRECTION_GIF_DIR, "green_up.gif")
DOWN_GIF = os.path.join(DIRECTION_GIF_DIR, "red_down.gif")


# ============================================================
# SETTINGS
# ============================================================

BASE_URL = "https://api.twelvedata.com"
SAHMK_BASE = "https://api.sahmk.sa/api/v1"

# TASI: SAHMK current quote; Twelve Data remains the technical-history engine.
SAHMK_QUOTE_CACHE = {}
SAHMK_QUOTE_CACHE_TTL = 120
SAHMK_QUOTE_LOCK = Lock()

# لا نفتح آلاف الاتصالات معًا
MAX_WORKERS = 4

# الحد الأدنى بين طلبات TwelveData
REQUEST_GAP = 0.25

# إعادة المحاولة عند 429 / أخطاء مؤقتة
MAX_RETRIES = 3

# بعد انتهاء دفعة الفحص، يبدأ التالي
SCAN_INTERVAL = 300  # دورة 5 دقائق

# تحديث قوائم الرموز كل 6 ساعات بدل طلبها كل دورتين
SYMBOL_REFRESH_SECONDS = 21600

PRIMARY_TIMEFRAME = "5min"
# الفحص الكامل يبدأ بـ 5 دقائق. الأطر الأعلى تُستخدم للتأكيد فقط عند ظهور إشارة.
SIGNAL_TIMEFRAMES = ("5min", "15min", "30min", "1h", "4h")
OUTPUTSIZE = 220

# 🇺🇸 لا ترسل/تعتمد إشارات للأسهم الأمريكية الأقل من 0.20$
# جميع الأسهم من 0.20$ فأعلى تبقى ضمن الفحص.
MIN_US_PRICE = 0.15
US_MAX_SYMBOLS = 13414
TASI_MAX_SYMBOLS = 374

# Batch: يقلل عدد الاتصالات، ولا يلغي احتساب رصيد كل رمز.
BATCH_SYMBOLS = 8
# Twelve Data Basic: 8 API credits/minute. لا نحجز رصيداً من الدفعة؛
# البوابة الزمنية تنتظر الدقيقة التالية تلقائياً عند وصول الرصيد إلى الصفر.
CREDIT_RESERVE = 0

# 🔎 FAST FILTER — يقلل الفحص العميق قبل تشغيل الأطر الستة
FAST_FILTER_LIMIT = {"TASI": 120, "US": 400, "CRYPTO": 300}
FAST_FILTER_MIN_MOVE = {"TASI": 0.25, "US": 0.50, "CRYPTO": 0.35}

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

# ثمانية أهداف متدرجة تسمح للأسهم ذات القفزات الكبيرة بالاستمرار.
ATR_TARGETS = [
    1.0, 1.5, 2.0, 3.0,
    4.0, 5.0, 6.5, 8.0
]
STOP_ATR_MULTIPLIER = 1.5

# الأخبار لا تُطلب لكل الأسهم.
# تطلب فقط عندما تكون إشارة فنية قوية.
NEWS_ON_STRONG_SIGNAL_ONLY = True

POSITIVE_WORDS = [
    "beat", "beats", "growth", "profit", "profits",
    "upgrade", "upgraded", "buy", "strong", "positive",
    "partnership", "contract", "approval", "revenue",
    "surge", "record", "raises guidance", "guidance"
]

NEGATIVE_WORDS = [
    "loss", "losses", "downgrade", "downgraded", "sell",
    "weak", "negative", "lawsuit", "decline", "drop",
    "warning", "debt", "offering", "investigation",
    "risk", "cuts guidance", "guidance cut"
]

# ============================================================
# GLOBAL STATE
# ============================================================

_thread_local = local()

request_lock = Lock()
last_request_time = 0.0

state_lock = Lock()
LAST_SIGNAL = {}
TREND_STATE = {}
REVERSAL_COUNT = {}

symbol_cache_lock = Lock()
SYMBOL_CACHE = {
    "TASI": {"symbols": [], "updated": 0},
    "US": {"symbols": [], "updated": 0},
    "CRYPTO": {"symbols": [], "updated": 0},
}

# نتيجة /time_series المحملة بالـ Batch.
SERIES_CACHE = {}
series_cache_lock = Lock()

# آخر رصيد Credits معروف من رؤوس Twelve Data. لا يتم استدعاء /api_usage
# حتى لا نستهلك رصيدًا إضافيًا.
API_CREDITS_LEFT = None
API_CREDITS_LOCK = Lock()
TD_CREDIT_GATE_LOCK = Lock()
TD_NEXT_SLOT = 0.0
TD_DAILY_RESERVED = 0
TD_DAILY_LIMIT = 800
# يوم UTC الذي ينتمي إليه الرصيد المعروف. عند دخول يوم جديد تُعاد الحالة إلى None
# حتى يسمح البوت بأول طلب، ثم يقرأ الرصيد الجديد من رأس Twelve Data.
API_CREDITS_DAY = None
API_CREDITS_LEFT_AT = 0.0

def reset_credit_state_if_new_utc_day():
    global API_CREDITS_LEFT, API_CREDITS_DAY, API_CREDITS_LEFT_AT, TD_NEXT_SLOT, TD_DAILY_RESERVED
    today_utc = datetime.now(timezone.utc).date()
    with API_CREDITS_LOCK:
        if API_CREDITS_DAY != today_utc:
            API_CREDITS_DAY = today_utc
            API_CREDITS_LEFT = None
            API_CREDITS_LEFT_AT = 0.0
            TD_DAILY_RESERVED = 0
            TD_NEXT_SLOT = 0.0
            print(f"🛡️ Twelve Data: يوم UTC جديد {today_utc} — إعادة تهيئة حالة الحصة وانتظار أول رد لتحديث الرصيد")

# 🇺🇸 Stock split cache — لا نطلب التقسيم لكل الأسهم في كل دورة
SPLIT_CACHE_TTL = 86400
split_cache_lock = Lock()
SPLIT_CACHE = {}

# ============================================================
# INSTANT TELEGRAM QUEUE
# ============================================================
# إرسال الإشارة يتم في مسار مستقل حتى لا يتوقف فحص السوق بانتظار Telegram.
TELEGRAM_QUEUE = queue.Queue(maxsize=5000)

def telegram_worker():
    while True:
        item = TELEGRAM_QUEUE.get()
        if item is None:
            TELEGRAM_QUEUE.task_done()
            break
        token, result = item
        try:
            telegram_send_direction(token, result)
            telegram_send_smart_animation(token, result)
            message = build_message(result)
            if telegram_send(token, message, build_tradingview_url(result)):
                print(
                    f"[{result['market']}] 📲 {result['symbol']} "
                    f"{result['signal']} {result['score']}/100 — أُرسلت فوراً"
                )
        except Exception as error:
            print(f"[TELEGRAM] إرسال خطأ: {error}")
        finally:
            TELEGRAM_QUEUE.task_done()

def enqueue_signal(token, result):
    try:
        TELEGRAM_QUEUE.put_nowait((token, result))
        return True
    except queue.Full:
        print("[TELEGRAM] ⚠️ قائمة الإرسال ممتلئة — تم تجاوز الإشارة")
        return False

# ============================================================
# HTTP SESSION
# ============================================================

def get_session():
    """
    Session مستقل لكل worker thread.
    هذا يعيد استخدام TCP connections بدل إنشاء اتصال جديد لكل طلب.
    """
    session = getattr(_thread_local, "session", None)

    if session is None:
        session = requests.Session()
        session.headers.update({
            "User-Agent": "AI-PRO-MAX/Stable"
        })
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=MAX_WORKERS + 2,
            pool_maxsize=MAX_WORKERS + 2,
            max_retries=0,
        )
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        _thread_local.session = session

    return session


def rate_wait():
    global last_request_time

    with request_lock:
        now = time.monotonic()
        wait = REQUEST_GAP - (now - last_request_time)

        if wait > 0:
            time.sleep(wait)

        last_request_time = time.monotonic()


def sahmk_request(endpoint, params=None):
    """SAHMK REST client for Saudi market quotes. Uses existing Railway key only."""
    if not SAHMK_API_KEY:
        return None
    try:
        response = requests.get(
            SAHMK_BASE + endpoint,
            params=params or {},
            headers={"X-API-Key": SAHMK_API_KEY},
            timeout=(10, 20),
        )
        if response.status_code != 200:
            return None
        data = response.json()
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def get_sahmk_quote(symbol):
    now = time.time()
    with SAHMK_QUOTE_LOCK:
        cached = SAHMK_QUOTE_CACHE.get(str(symbol))
        if cached and now - cached["updated"] < SAHMK_QUOTE_CACHE_TTL:
            return cached["data"]

    data = sahmk_request(f"/quote/{quote(str(symbol), safe='')}/", {"data_mode": "delayed"})
    if not data:
        return None

    try:
        result = {
            "symbol": str(data.get("symbol") or symbol),
            "name": str(data.get("name") or data.get("name_en") or ""),
            "price": float(data["price"]),
            "volume": float(data.get("volume", 0) or 0),
            "change": float(data.get("change", 0) or 0),
            "change_percent": float(data.get("change_percent", 0) or 0),
            "updated_at": data.get("updated_at"),
            "is_delayed": bool(data.get("is_delayed", True)),
        }
    except (TypeError, ValueError, KeyError):
        return None

    with SAHMK_QUOTE_LOCK:
        SAHMK_QUOTE_CACHE[str(symbol)] = {"updated": now, "data": result}
    return result


def _wait_for_td_minute_credit(required=1):
    """
    بوابة مركزية واحدة لـ Twelve Data.
    كل Batch من 8 رموز يحجز خانة زمنية واحدة، بالتتابع، بدل أن
    تتنافس خيوط TASI/US/CRYPTO وتطبع انتظاراً متكرراً.
    """
    global TD_NEXT_SLOT, TD_DAILY_RESERVED
    required = max(1, int(required or 1))
    reset_credit_state_if_new_utc_day()

    while True:
        with API_CREDITS_LOCK:
            left = API_CREDITS_LEFT
            left_at = API_CREDITS_LEFT_AT
            # الرصيد 0 قد يكون من الدقيقة السابقة؛ لا نسمح له بمنع أول طلب في الدقيقة الجديدة.
            stale_minute = left is not None and left_at > 0 and (time.time() - left_at) >= 60.0
            if left is not None and left < required and not stale_minute:
                now = time.time()
                wait_seconds = 60.0 - (now % 60.0) + 0.15
                print(f"🕐 Twelve Data: المتبقي {left} لا يكفي لطلب يحتاج {required} — انتظار {wait_seconds:.1f}s للدقيقة التالية")
            elif TD_DAILY_RESERVED + required > TD_DAILY_LIMIT:
                print(f"🛡️ Twelve Data: تم حجز الحد اليومي {TD_DAILY_RESERVED}/{TD_DAILY_LIMIT} — إيقاف طلبات جديدة حتى يوم UTC التالي")
                return False
            else:
                now = time.time()
                slot = max(now, TD_NEXT_SLOT)
                TD_NEXT_SLOT = slot + 60.0
                TD_DAILY_RESERVED += required
                wait_seconds = max(0.0, slot - now)
                if wait_seconds > 0.1:
                    print(f"🕐 Twelve Data: حجز Batch مركزي — الانتظار {wait_seconds:.1f}s")
                break

        time.sleep(min(wait_seconds, 60.0))

    if wait_seconds > 0:
        time.sleep(wait_seconds)
    return True


def td_request(endpoint, params=None):
    """
    طلب آمن:
    - Session reuse
    - Rate limit
    - بوابة 8 credits/minute على مستوى كل الطلبات
    - Retry
    - معالجة 429
    - لا يفتح آلاف الاتصالات
    """
    if not TWELVEDATA_API_KEY:
        return None

    params = dict(params or {})
    params["apikey"] = TWELVEDATA_API_KEY

    session = get_session()

    # Batch /time_series يستهلك credit لكل رمز، حتى مع HTTP request واحد.
    credit_cost = 1
    if endpoint == "/time_series":
        raw_symbols = str(params.get("symbol", ""))
        credit_cost = max(1, len([x for x in raw_symbols.split(",") if x.strip()]))

    for attempt in range(MAX_RETRIES):
        try:
            # يمنع أكثر من worker من استهلاك نفس الدقيقة بالتوازي.
            with TD_CREDIT_GATE_LOCK:
                if not _wait_for_td_minute_credit(credit_cost):
                    return None
                rate_wait()

                response = session.get(
                    BASE_URL + endpoint,
                    params=params,
                    timeout=(10, 30),
                )

                left = response.headers.get("api-credits-left")
                if left is not None:
                    try:
                        with API_CREDITS_LOCK:
                            global API_CREDITS_LEFT, API_CREDITS_LEFT_AT
                            API_CREDITS_LEFT = int(float(left))
                            API_CREDITS_LEFT_AT = time.time()
                    except Exception:
                        pass

                if response.status_code == 429:
                    retry_after = response.headers.get("Retry-After")
                    try:
                        delay = float(retry_after)
                    except Exception:
                        delay = min(10, 2 ** attempt)

                    time.sleep(delay)
                    continue

                if response.status_code in (500, 502, 503, 504):
                    time.sleep(min(10, 2 ** attempt))
                    continue

                if response.status_code != 200:
                    return None

                try:
                    data = response.json()
                except ValueError:
                    return None

                if isinstance(data, dict):
                    status = str(data.get("status", "")).lower()

                    if status == "error":
                        return None

                    if data.get("code") in (429, "429"):
                        time.sleep(min(10, 2 ** attempt))
                        continue

                return data

        except (requests.Timeout, requests.ConnectionError):
            if attempt < MAX_RETRIES - 1:
                time.sleep(min(10, 2 ** attempt))
            else:
                return None

        except Exception:
            return None

    return None


# ============================================================
# INDICATORS
# ============================================================

def ema(values, length):
    if len(values) < length:
        return None

    multiplier = 2 / (length + 1)
    result = sum(values[:length]) / length

    for value in values[length:]:
        result = ((value - result) * multiplier) + result

    return result


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
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
        trs.append(tr)

    if len(trs) < length:
        return None

    value = sum(trs[:length]) / length

    for tr in trs[length:]:
        value = ((value * (length - 1)) + tr) / length

    return value


def vwap(highs, lows, closes, volumes):
    cumulative_pv = 0.0
    cumulative_volume = 0.0

    for high, low, close, volume in zip(
        highs, lows, closes, volumes
    ):
        typical = (high + low + close) / 3.0
        cumulative_pv += typical * volume
        cumulative_volume += volume

    if cumulative_volume <= 0:
        return None

    return cumulative_pv / cumulative_volume


# ============================================================
# PRICE DATA
# ============================================================

def _parse_series_payload(data):
    """Convert a Twelve Data single/batch time_series response to our candle format."""
    if not isinstance(data, dict):
        return None
    values = data.get("values")
    if not values:
        return None
    candles = []
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


def _cache_series(symbol, market, interval, series):
    if not series:
        return
    with series_cache_lock:
        SERIES_CACHE[(market, symbol, interval)] = {
            "updated": time.time(),
            "data": series,
        }


def _get_cached_series(symbol, market, interval):
    with series_cache_lock:
        item = SERIES_CACHE.get((market, symbol, interval))
        if item and time.time() - item["updated"] < SCAN_INTERVAL + 120:
            return item["data"]
    return None


def get_series(symbol, market, interval=PRIMARY_TIMEFRAME):
    cached = _get_cached_series(symbol, market, interval)
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

    data = td_request("/time_series", params)
    if data is None and market == "US":
        params.pop("prepost", None)
        data = td_request("/time_series", params)

    series = _parse_series_payload(data)
    if series:
        _cache_series(symbol, market, interval, series)
    return series


def _batch_response_items(data):
    """Yield (symbol, payload) from Twelve Data query-string batch responses."""
    if not isinstance(data, dict):
        return []
    # Some responses can be wrapped; normal batch responses are keyed by symbol.
    items = []
    for key, value in data.items():
        if isinstance(value, dict) and "values" in value:
            items.append((str(key), value))
    return items


def batch_load_series(symbols, market, interval=PRIMARY_TIMEFRAME):
    """Load symbols in 8-symbol batches, respecting Twelve Data's 8 credits/minute."""
    if not symbols:
        return 0

    reset_credit_state_if_new_utc_day()
    loaded = 0

    for start in range(0, len(symbols), BATCH_SYMBOLS):
        batch = symbols[start:start + BATCH_SYMBOLS]

        # لا نوقف بسبب api-credits-left=0؛ td_request ينتظر الدقيقة التالية.
        params = {
            "symbol": ",".join(quote(str(x), safe="/:.-") for x in batch),
            "interval": interval,
            "outputsize": OUTPUTSIZE,
            "format": "JSON",
            "adjust": "splits",
        }
        if market == "US":
            params["prepost"] = "true"

        data = td_request("/time_series", params)
        if data is None and market == "US":
            params.pop("prepost", None)
            data = td_request("/time_series", params)

        if data is None:
            with API_CREDITS_LOCK:
                daily_exhausted = TD_DAILY_RESERVED >= TD_DAILY_LIMIT
            if daily_exhausted:
                print(f"[{market}] 🛑 Twelve Data: الحصة اليومية مستهلكة — إيقاف دورة السوق الحالية")
                break

        for key, payload in _batch_response_items(data):
            series = _parse_series_payload(payload)
            if series:
                _cache_series(key, market, interval, series)
                loaded += 1

        print(f"[{market}] 📦 Batch {min(start + len(batch), len(symbols))}/{len(symbols)} | loaded={loaded}")

        # لا نعيد طلباً فورياً بعد استهلاك الـ8 credits؛ البوابة الزمنية
        # في td_request ستنتظر تلقائياً حتى الدقيقة التالية.

    return loaded


# ============================================================
# SUPPORT / RESISTANCE
# ============================================================

def support_resistance(candles):
    if len(candles) < 30:
        return None, None

    recent = candles[-50:]
    highs = [c["high"] for c in recent]
    lows = [c["low"] for c in recent]

    return min(lows), max(highs)


# ============================================================
# TREND
# ============================================================

def calculate_trend(candles):
    closes = [c["close"] for c in candles]

    e10 = ema(closes, EMA_FAST)
    e14 = ema(closes, EMA_MID)
    e15 = ema(closes, EMA_MOMENTUM)
    e25 = ema(closes, EMA_TRIGGER)
    e50 = ema(closes, EMA_SLOW)
    e200 = ema(closes, EMA_LONG)

    if None in (e10, e14, e25, e50, e200):
        return "NEUTRAL"

    current = closes[-1]

    bullish = 0
    bearish = 0

    if e10 > e14:
        bullish += 1
    else:
        bearish += 1

    if e14 > e25:
        bullish += 1
    else:
        bearish += 1

    if e15 > e25:
        bullish += 1
    else:
        bearish += 1

    if e50 > e200:
        bullish += 1
    else:
        bearish += 1

    if current > e200:
        bullish += 1
    else:
        bearish += 1

    if bullish >= 3:
        return "UP"

    if bearish >= 3:
        return "DOWN"

    return "NEUTRAL"


def persistent_trend(market, symbol, current_trend):
    """Keep UP/DOWN active until a confirmed two-cycle reversal."""
    key = f"{market}:{symbol}"
    if current_trend == "NEUTRAL":
        with state_lock:
            return TREND_STATE.get(key, "NEUTRAL")

    with state_lock:
        previous = TREND_STATE.get(key)
        if previous is None:
            TREND_STATE[key] = current_trend
            REVERSAL_COUNT[key] = 0
            return current_trend

        if current_trend == previous:
            REVERSAL_COUNT[key] = 0
            return previous

        count = REVERSAL_COUNT.get(key, 0) + 1
        REVERSAL_COUNT[key] = count
        if count >= 2:
            TREND_STATE[key] = current_trend
            REVERSAL_COUNT[key] = 0
            return current_trend

        return previous


# ============================================================
# ARS — HIDDEN INTERNAL LEVEL ENGINE
# ============================================================

ARS_LEVELS = [20, 30, 40, 50, 60, 80, 100]

def calculate_ars(candles):
    """
    ARS داخلي فقط. لا يظهر في Telegram.
    القراءة محصورة بين 20 و100، مع مستويات مراقبة:
    20 / 30 / 40 / 50 / 60 / 80 / 100.
    """
    closes = [c["close"] for c in candles]

    if len(closes) < 50:
        return 50

    e8 = ema(closes, 8)
    e21 = ema(closes, 21)
    e50 = ema(closes, 50)
    current = closes[-1]

    score = 50

    if e8 > e21:
        score += 15
    else:
        score -= 15

    if e21 > e50:
        score += 15
    else:
        score -= 15

    if current > e50:
        score += 10
    else:
        score -= 10

    return max(20, min(100, score))


def nearest_ars_level(value):
    return min(ARS_LEVELS, key=lambda level: abs(level - value))


def ars_ladder_bias(ars_value, previous_ars=None):
    """
    قراءة مستويات ARS من 20 إلى 100 داخليًا.
    عند الصعود: متابعة تجاوز المستويات.
    عند الهبوط: متابعة كسر المستويات والارتداد منها.
    لا يُعرض هذا في الإشعار.
    """
    level = nearest_ars_level(ars_value)
    if previous_ars is None:
        return 0, level

    if ars_value > previous_ars:
        return 1, level
    if ars_value < previous_ars:
        return -1, level
    return 0, level


# ============================================================
# DIVERGENCE — REGULAR + HIDDEN (HIDDEN FROM TELEGRAM)
# ============================================================

def _pivot_lows(values, left=3, right=3):
    result = []
    for i in range(left, len(values) - right):
        window = values[i-left:i+right+1]
        if values[i] == min(window):
            result.append((i, values[i]))
    return result


def _pivot_highs(values, left=3, right=3):
    result = []
    for i in range(left, len(values) - right):
        window = values[i-left:i+right+1]
        if values[i] == max(window):
            result.append((i, values[i]))
    return result


def detect_divergence(candles, rsi_value):
    """
    يكشف Regular/Hidden Divergence بين السعر وRSI من القمم والقيعان
    المؤكدة. النتيجة داخلية فقط ولا تظهر في Telegram.
    """
    closes = [c["close"] for c in candles]
    if len(closes) < 60 or rsi_value is None:
        return {"regular_bull": False, "regular_bear": False,
                "hidden_bull": False, "hidden_bear": False}

    # RSI series كاملة بنفس ترتيب الشموع
    rsi_series = []
    for end_i in range(15, len(closes) + 1):
        value = rsi(closes[:end_i], RSI_LENGTH)
        rsi_series.append(value if value is not None else 50.0)
    pad = len(closes) - len(rsi_series)
    rsi_full = [50.0] * pad + rsi_series

    lows = _pivot_lows(closes)
    highs = _pivot_highs(closes)

    result = {
        "regular_bull": False,
        "regular_bear": False,
        "hidden_bull": False,
        "hidden_bear": False,
    }

    if len(lows) >= 2:
        (i1, p1), (i2, p2) = lows[-2], lows[-1]
        r1, r2 = rsi_full[i1], rsi_full[i2]
        result["regular_bull"] = p2 < p1 and r2 > r1
        result["hidden_bull"] = p2 > p1 and r2 < r1

    if len(highs) >= 2:
        (i1, p1), (i2, p2) = highs[-2], highs[-1]
        r1, r2 = rsi_full[i1], rsi_full[i2]
        result["regular_bear"] = p2 > p1 and r2 < r1
        result["hidden_bear"] = p2 < p1 and r2 > r1

    return result


def trendline_bias(candles):
    """
    قراءة اتجاه خطوط الترند من آخر قمتين/قاعين، داخلي فقط.
    """
    closes = [c["close"] for c in candles]
    lows = _pivot_lows(closes)
    highs = _pivot_highs(closes)

    bias = 0

    if len(lows) >= 2:
        (_, l1), (_, l2) = lows[-2], lows[-1]
        if l2 > l1:
            bias += 1
        elif l2 < l1:
            bias -= 1

    if len(highs) >= 2:
        (_, h1), (_, h2) = highs[-2], highs[-1]
        if h2 > h1:
            bias += 1
        elif h2 < h1:
            bias -= 1

    return max(-2, min(2, bias))


# ============================================================
# SMART MOVEMENT / SMART-MONEY PROXY (INFERRED)
# ============================================================

def detect_smart_movements(candles, trend, volume_ratio, buy_power, sell_power,
                           atr_value, rsi_value):
    """
    استدلال احتمالي لتحركات كبيرة/تجميع من السعر والحجم.
    لا يعني رصد هوية صندوق بعينه؛ هو Proxy تقني.
    """
    recent = candles[-20:]
    if len(recent) < 10:
        return {"maker": 0, "speculators": False, "accumulation": False, "unusual": False}

    closes = [c["close"] for c in recent]
    opens = [c["open"] for c in recent]
    ranges = [abs(c["high"] - c["low"]) for c in recent]
    avg_range = sum(ranges[:-1]) / max(1, len(ranges) - 1)
    current_range = ranges[-1]
    price_move = (closes[-1] - closes[0]) / closes[0] * 100 if closes[0] else 0

    unusual = (volume_ratio >= 2.0 and abs(price_move) >= 1.0) or (volume_ratio >= 3.0)

    # تجميع احتمالي: حجم قوي مع ضغط شرائي واتجاه/سلوك سعر متماسك.
    accumulation = (
        volume_ratio >= 1.5
        and buy_power >= 58
        and (trend == "UP" or (rsi_value is not None and rsi_value < 60))
    )

    # حركة مضاربين: اندفاع سعري + توسع نطاق/حجم.
    speculators = (
        (volume_ratio >= 2.0 and abs(price_move) >= 2.0)
        or (avg_range > 0 and current_range >= avg_range * 1.8)
    )

    # سهم صغير متحرك لصنّاع السهم: نستخدم Proxy قوي وليس ادعاء معرفة جهة محددة.
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
# BUY / SELL POWER
# ============================================================

def calculate_power(candles):
    recent = candles[-20:]

    # أثناء ما قبل/بعد السوق قد لا تعيد TwelveData حجمًا للشموع الممتدة.
    # في هذه الحالة نستخدم قوة الحركة السعرية بدل أن تصبح القوة 0/0.
    volume_available = sum(c["volume"] for c in recent) > 0

    buy_volume = 0.0
    sell_volume = 0.0

    if volume_available:
        for candle in recent:
            volume = candle["volume"]

            if candle["close"] > candle["open"]:
                buy_volume += volume
            elif candle["close"] < candle["open"]:
                sell_volume += volume
            else:
                buy_volume += volume * 0.5
                sell_volume += volume * 0.5
    else:
        # fallback سعري للـ extended hours
        for candle in recent:
            if candle["close"] > candle["open"]:
                buy_volume += 1.0
            elif candle["close"] < candle["open"]:
                sell_volume += 1.0
            else:
                buy_volume += 0.5
                sell_volume += 0.5

    total = buy_volume + sell_volume

    if total <= 0:
        return 50.0, 50.0

    return (
        buy_volume / total * 100,
        sell_volume / total * 100,
    )


def volume_strength(candles):
    volumes = [c["volume"] for c in candles]

    # Extended-hours قد لا تحتوي على volume.
    if sum(volumes[-VOLUME_LENGTH:]) <= 0:
        return 1.0

    if len(volumes) < VOLUME_LENGTH + 1:
        return 1.0

    average = sma(volumes[:-1], VOLUME_LENGTH)

    if not average or average <= 0:
        return 1.0

    return volumes[-1] / average


# ============================================================
# TARGETS
# ============================================================

def calculate_targets(price, atr_value, direction):
    if not atr_value or atr_value <= 0 or not price or price <= 0:
        return []

    result = []
    for multiplier in ATR_TARGETS:
        if direction == "UP":
            result.append(price + atr_value * multiplier)
        else:
            result.append(price - atr_value * multiplier)
    return result


def calculate_stop_loss(price, atr_value, support, resistance, direction):
    """ATR + structure stop. The wider protective level is used to avoid noise."""
    if not price or not atr_value or atr_value <= 0:
        return None
    atr_stop = price - atr_value * STOP_ATR_MULTIPLIER if direction == "UP" else price + atr_value * STOP_ATR_MULTIPLIER
    if direction == "UP" and support is not None and support < price:
        structural = support - atr_value * 0.25
        return round(max(0.0, min(atr_stop, structural)), 10)
    if direction == "DOWN" and resistance is not None and resistance > price:
        structural = resistance + atr_value * 0.25
        return round(max(0.0, max(atr_stop, structural)), 10)
    return round(max(0.0, atr_stop), 10)


# ============================================================
# NEWS
# ============================================================

def news_sentiment(symbol):
    data = td_request(
        "/news",
        {
            "symbol": symbol,
            "limit": 10,
        },
    )

    if not data:
        return "⚪ محايد"

    if isinstance(data, dict):
        articles = data.get("news", [])
    elif isinstance(data, list):
        articles = data
    else:
        articles = []

    if not articles:
        return "⚪ محايد"

    positive = 0
    negative = 0

    for article in articles:
        if not isinstance(article, dict):
            continue

        text = (
            str(article.get("title", "")) + " " +
            str(article.get("description", ""))
        ).lower()

        positive += sum(1 for word in POSITIVE_WORDS if word in text)
        negative += sum(1 for word in NEGATIVE_WORDS if word in text)

    if positive > negative:
        return "🟢 إيجابي"

    if negative > positive:
        return "🔴 سلبي"

    return "⚪ محايد"


# ============================================================
# PINE INDICATOR PARITY — RSI / AI PRO MAX / GOLDEN CANDLE
# ============================================================

def _pine_sma_series(values, length):
    out = [None] * len(values)
    if len(values) < length:
        return out
    for i in range(length - 1, len(values)):
        window = values[i - length + 1:i + 1]
        valid = [x for x in window if x is not None]
        out[i] = sum(valid) / len(valid) if valid else None
    return out


def _pine_ema_series(values, length):
    out = [None] * len(values)
    if len(values) < length:
        return out
    seed = sum(values[:length]) / length
    out[length - 1] = seed
    alpha = 2.0 / (length + 1.0)
    prev = seed
    for i in range(length, len(values)):
        prev = (values[i] - prev) * alpha + prev
        out[i] = prev
    return out


def _cross_over(a, b, i):
    return i > 0 and a[i] is not None and b[i] is not None and a[i - 1] is not None and b[i - 1] is not None and a[i] > b[i] and a[i - 1] <= b[i - 1]


def _cross_under(a, b, i):
    return i > 0 and a[i] is not None and b[i] is not None and a[i - 1] is not None and b[i - 1] is not None and a[i] < b[i] and a[i - 1] >= b[i - 1]


def _confirmed_pivots(values, left=5, right=5, is_high=False):
    pivots = []
    for i in range(left, len(values) - right):
        window = values[i-left:i+right+1]
        if is_high:
            if values[i] == max(window):
                pivots.append(i)
        else:
            if values[i] == min(window):
                pivots.append(i)
    return pivots


def _pine_indicator_parity(candles):
    """
    Reproduces the signal-bearing logic from the supplied Pine file.
    Visual objects/labels are intentionally not reproduced in Telegram.
    """
    closes = [c["close"] for c in candles]
    opens = [c["open"] for c in candles]
    highs = [c["high"] for c in candles]
    lows = [c["low"] for c in candles]
    volumes = [c.get("volume", 0.0) or 0.0 for c in candles]
    n = len(candles)

    # --------------------------------------------------------
    # RSI / EMA block from the supplied AI PRO MAX script
    # EMA 7 / 14 / 25 / 50 / 180 / 320 / 380
    # --------------------------------------------------------
    ema7 = _pine_ema_series(closes, 7)
    ema14 = _pine_ema_series(closes, 14)
    ema25 = _pine_ema_series(closes, 25)
    ema50 = _pine_ema_series(closes, 50)
    ema180 = _pine_ema_series(closes, 180)
    ema320 = _pine_ema_series(closes, 320)
    ema380 = _pine_ema_series(closes, 380)

    rsi_series = []
    for i in range(n):
        rsi_series.append(rsi(closes[:i + 1], 14))

    # Strong BUY/SELL from EMA3(25) + volatility filter.
    atr_series = []
    for i in range(n):
        atr_series.append(atr(highs[:i + 1], lows[:i + 1], closes[:i + 1], 14))
    atr_sma20 = _pine_sma_series([x if x is not None else 0.0 for x in atr_series], 20)

    strong_buy = False
    strong_sell = False
    if n:
        i = n - 1
        bull_ema = all(x is not None for x in (ema7[i], ema14[i], ema25[i], ema50[i])) and ema7[i] > ema14[i] > ema25[i] > ema50[i]
        bear_ema = all(x is not None for x in (ema7[i], ema14[i], ema25[i], ema50[i])) and ema7[i] < ema14[i] < ema25[i] < ema50[i]
        vol_filter = atr_series[i] is not None and atr_sma20[i] is not None and atr_series[i] > atr_sma20[i]
        strong_buy = _cross_over(closes, ema25, i) and bull_ema and vol_filter
        strong_sell = _cross_under(closes, ema25, i) and bear_ema and vol_filter

    # --------------------------------------------------------
    # Doji waiting/breakout logic — exact stateful behavior
    # --------------------------------------------------------
    waiting = False
    doji_high = None
    doji_low = None
    wait_bars = 0
    doji_buy = False
    doji_sell = False
    for i in range(n):
        body = abs(closes[i] - opens[i])
        rng = highs[i] - lows[i]
        is_doji = rng > 0 and body <= rng * 0.10

        if is_doji and not waiting:
            waiting = True
            doji_high = highs[i]
            doji_low = lows[i]
            wait_bars = 0

        if waiting:
            wait_bars += 1
            if wait_bars >= 10:
                waiting = False
                doji_high = None
                doji_low = None
                wait_bars = 0

        buy_now = waiting and doji_high is not None and closes[i] > doji_high
        sell_now = waiting and doji_low is not None and closes[i] < doji_low
        if buy_now or sell_now:
            doji_buy = buy_now
            doji_sell = sell_now
            waiting = False
            doji_high = None
            doji_low = None
            wait_bars = 0

    # --------------------------------------------------------
    # Hidden divergence: pivot length 5, price vs RSI
    # --------------------------------------------------------
    hidden_bull = False
    hidden_bear = False
    low_pivots = _confirmed_pivots(lows, 5, 5, is_high=False)
    high_pivots = _confirmed_pivots(highs, 5, 5, is_high=True)

    if len(low_pivots) >= 2:
        p1, p2 = low_pivots[-2], low_pivots[-1]
        if rsi_series[p1] is not None and rsi_series[p2] is not None:
            hidden_bull = lows[p2] > lows[p1] and rsi_series[p2] < rsi_series[p1]

    if len(high_pivots) >= 2:
        p1, p2 = high_pivots[-2], high_pivots[-1]
        if rsi_series[p1] is not None and rsi_series[p2] is not None:
            hidden_bear = highs[p2] < highs[p1] and rsi_series[p2] > rsi_series[p1]

    # --------------------------------------------------------
    # Smart Filters — exactly as supplied
    # EMA200, RSI >/< 50, volume > SMA20
    # --------------------------------------------------------
    ema200_series = _pine_ema_series(closes, 200)
    volume_sma20 = _pine_sma_series(volumes, 20)
    i = n - 1
    ema_buy_filter = ema200_series[i] is not None and closes[i] > ema200_series[i]
    ema_sell_filter = ema200_series[i] is not None and closes[i] < ema200_series[i]
    rsi_buy_filter = rsi_series[i] is not None and rsi_series[i] > 50
    rsi_sell_filter = rsi_series[i] is not None and rsi_series[i] < 50
    volume_filter = volume_sma20[i] is not None and volumes[i] > volume_sma20[i]

    final_buy = (doji_buy or hidden_bull) and ema_buy_filter and rsi_buy_filter and volume_filter
    final_sell = (doji_sell or hidden_bear) and ema_sell_filter and rsi_sell_filter and volume_filter

    # --------------------------------------------------------
    # Golden Candle PRO — exact conditions from the supplied file
    # EMA 7 / EMA 25 / RSI14 / body 45% / volume 1.10x / avg20
    # --------------------------------------------------------
    g_ema_fast = ema7
    g_ema_slow = ema25
    g_rsi = rsi_series
    g_avg_volume = _pine_sma_series(volumes, 20)

    golden_first = False
    golden_continue = False
    golden_active = False

    for j in range(n):
        rng = highs[j] - lows[j]
        body = abs(closes[j] - opens[j])
        body_ratio = body / rng if rng > 0 else 0.0
        bull_candle = closes[j] > opens[j]
        strong_body = body_ratio >= 0.45
        ema_bull = g_ema_fast[j] is not None and g_ema_slow[j] is not None and g_ema_fast[j] > g_ema_slow[j]
        price_bull = g_ema_fast[j] is not None and closes[j] > g_ema_fast[j]
        rsi_bull = g_rsi[j] is not None and g_rsi[j] >= 50
        # Pine: na(volume) OR volume >= avgVolume*1.10.
        volume_bull = volumes[j] <= 0 or (g_avg_volume[j] is not None and volumes[j] >= g_avg_volume[j] * 1.10)

        crossover_close_fast = _cross_over(closes, g_ema_fast, j)
        crossover_fast_slow = _cross_over(g_ema_fast, g_ema_slow, j)
        previous_bear_break = j > 0 and closes[j] > highs[j - 1] and closes[j - 1] <= opens[j - 1]

        early_rise = (
            bull_candle and strong_body and price_bull and rsi_bull and volume_bull and
            (crossover_close_fast or crossover_fast_slow or previous_bear_break)
        )

        if early_rise:
            golden_active = True

        trend_break = (
            (g_ema_fast[j] is not None and closes[j] < g_ema_fast[j]) or
            (g_ema_fast[j] is not None and g_ema_slow[j] is not None and g_ema_fast[j] < g_ema_slow[j]) or
            (g_rsi[j] is not None and g_rsi[j] < 45)
        )
        if trend_break:
            golden_active = False

        if j == n - 1:
            golden_first = early_rise
            golden_continue = golden_active and not golden_first

    # --------------------------------------------------------
    # VWAP crossover signal from the supplied script
    # --------------------------------------------------------
    vwap_series = []
    cum_pv = 0.0
    cum_vol = 0.0
    for j in range(n):
        vol = volumes[j]
        typical = (highs[j] + lows[j] + closes[j]) / 3.0
        cum_pv += typical * vol
        cum_vol += vol
        v = cum_pv / cum_vol if cum_vol > 0 else None
        vwap_series.append(v)

    vwap_buy = False
    vwap_sell = False
    if i > 0 and vwap_series[i] is not None and vwap_series[i - 1] is not None:
        avg_vol = g_avg_volume[i]
        strong_volume = volumes[i] > avg_vol * 1.10 if avg_vol is not None else True
        vwap_buy = closes[i] > vwap_series[i] and closes[i - 1] <= vwap_series[i - 1] and strong_volume
        vwap_sell = closes[i] < vwap_series[i] and closes[i - 1] >= vwap_series[i - 1] and strong_volume

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
        "ema200": ema200_series[i],
        "volume_sma20": volume_sma20[i],
        "vwap": vwap_series[i],
    }


# ============================================================
# ANALYSIS
# ============================================================

def _analyze_symbol_interval(symbol, market, interval):
    """Analyze one symbol on one of the approved signal timeframes."""
    series = get_series(symbol, market, interval=interval)
    if not series:
        return None

    candles = series["candles"]
    company_name = series.get("name") or ""
    closes = [c["close"] for c in candles]
    highs = [c["high"] for c in candles]
    lows = [c["low"] for c in candles]
    volumes = [c["volume"] for c in candles]

    if not closes:
        return None
    price = closes[-1]
    previous_close = closes[-2] if len(closes) >= 2 else None

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
    ars = calculate_ars(candles)
    buy_power, sell_power = calculate_power(candles)
    volume_ratio = volume_strength(candles)
    raw_trend = calculate_trend(candles)

    pine = _pine_indicator_parity(candles)

    if pine["final_buy"]:
        signal, signal_text = "BUY", "🟢 شراء قوي — SMART BUY"
    elif pine["final_sell"]:
        signal, signal_text = "SELL", "🔴 بيع قوي — SMART SELL"
    elif pine["golden_first"]:
        signal, signal_text = "BUY", "🟡 شراء — GOLDEN CANDLE"
    elif pine["vwap_buy"]:
        signal, signal_text = "BUY", "🟢 شراء — VWAP"
    elif pine["vwap_sell"]:
        signal, signal_text = "SELL", "🔴 بيع — VWAP"
    elif pine["strong_buy"]:
        signal, signal_text = "BUY", "🟢 شراء قوي — EMA"
    elif pine["strong_sell"]:
        signal, signal_text = "SELL", "🔴 بيع قوي — EMA"
    else:
        signal, signal_text = "WAIT", "⚪ انتظار"

    # 🇸🇦 TASI لا يستخدم Twelve Data هنا. مسار TASI المنفصل أدناه يعتمد SAHMK فقط.

    # Score 0-100: trend + momentum + VWAP + volume + breakout + candle/RSI.
    score = 0
    if e10 is not None and e14 is not None:
        score += 12 if ((signal == "BUY" and e10 > e14) or (signal == "SELL" and e10 < e14)) else 0
    if e14 is not None and e25 is not None:
        score += 12 if ((signal == "BUY" and e14 > e25) or (signal == "SELL" and e14 < e25)) else 0
    if e25 is not None and e50 is not None:
        score += 12 if ((signal == "BUY" and e25 > e50) or (signal == "SELL" and e25 < e50)) else 0
    if e50 is not None and e200 is not None:
        score += 12 if ((signal == "BUY" and e50 > e200) or (signal == "SELL" and e50 < e200)) else 0
    if rsi_value is not None:
        score += 12 if ((signal == "BUY" and rsi_value >= 55) or (signal == "SELL" and rsi_value <= 45)) else 0
    if vwap_value is not None:
        score += 12 if ((signal == "BUY" and price > vwap_value) or (signal == "SELL" and price < vwap_value)) else 0
    score += 12 if ((signal == "BUY" and buy_power >= 55) or (signal == "SELL" and sell_power >= 55)) else 0
    score += 8 if volume_ratio >= 1.20 else 0
    score += 8 if ((signal == "BUY" and pine.get("golden_first")) or (signal == "SELL" and pine.get("strong_sell"))) else 0
    score = min(100, int(score))

    # Keep trend state per symbol, but do not overwrite it six times in one pass.
    trend = raw_trend
    key = f"{market}:{symbol}"
    with state_lock:
        previous_ars = TREND_STATE.get(key + ":ARS")
        TREND_STATE[key + ":ARS"] = ars
    trend = persistent_trend(market, symbol, trend)
    ars_bias, ars_level = ars_ladder_bias(ars, previous_ars)
    divergence = {
        "regular_bull": False,
        "regular_bear": False,
        "hidden_bull": pine["hidden_bull"],
        "hidden_bear": pine["hidden_bear"],
    }
    trendline = trendline_bias(candles)
    smart = detect_smart_movements(
        candles, trend, volume_ratio, buy_power, sell_power, atr_value, rsi_value
    )

    targets = []
    stop_loss = None
    if signal != "WAIT":
        direction = "UP" if signal == "BUY" else "DOWN"
        targets = calculate_targets(price, atr_value, direction)
        stop_loss = calculate_stop_loss(price, atr_value, support, resistance, direction)

    return {
        "symbol": symbol, "name": company_name, "market": market,
        "price": price, "entry_price": price, "previous_close": previous_close,
        "ema10": e10, "ema14": e14, "ema15": e15, "ema25": e25, "ema50": e50, "ema200": e200,
        "rsi": rsi_value, "atr": atr_value, "vwap": vwap_value,
        "support": support, "resistance": resistance, "ars": ars,
        "ars_level": ars_level, "buy_power": buy_power, "sell_power": sell_power,
        "volume_ratio": volume_ratio, "trend": trend, "score": score,
        "signal": signal, "signal_text": signal_text, "news": "⚪ غير متاح",
        "split_info": None, "targets": targets, "stop_loss": stop_loss, "divergence": divergence,
        "trendline_bias": trendline, "smart": smart, "pine": pine,
        "timeframe": interval,
        "indicator_triggers": [label for label, active in (
            ("SMART BUY", pine["final_buy"]), ("SMART SELL", pine["final_sell"]),
            ("GOLDEN CANDLE", pine["golden_first"]),
            ("GOLDEN CONTINUATION", pine["golden_continue"]),
            ("VWAP BUY", pine["vwap_buy"]), ("VWAP SELL", pine["vwap_sell"]),
            ("STRONG BUY", pine["strong_buy"]), ("STRONG SELL", pine["strong_sell"]),
        ) if active],
    }


def analyze_symbol(symbol, market):
    """Full 5m market pass first; higher timeframes are confirmation only after a 5m signal."""
    primary = _analyze_symbol_interval(symbol, market, "5min")
    if not primary or primary["signal"] == "WAIT":
        return None

    # Strong signal: verify with the higher timeframes already requested.
    for interval in ("15min", "30min", "1h", "4h"):
        result = _analyze_symbol_interval(symbol, market, interval)
        if result and result["signal"] != "WAIT":
            if market == "US":
                result["news"] = news_sentiment(symbol)
                result["split_info"] = detect_local_split_from_daily(symbol)
            return result

    if market == "US":
        primary["news"] = news_sentiment(symbol)
        primary["split_info"] = detect_local_split_from_daily(symbol)
    return primary


# ============================================================
# 🇺🇸 STOCK SPLITS
# ============================================================

def detect_local_split_from_daily(symbol):
    """Quota-safe split detector from unadjusted daily history.
    It identifies a probable split/reverse-split date and factor; it does not invent ticker changes.
    """
    if not symbol:
        return None
    cache_key = f"LOCAL_SPLIT:{symbol}"
    now = time.time()
    with split_cache_lock:
        cached = SPLIT_CACHE.get(cache_key)
        if cached and now - cached.get("updated", 0) < SPLIT_CACHE_TTL:
            return cached.get("data")
    params = {
        "symbol": symbol,
        "interval": "1day",
        "outputsize": 260,
        "adjust": "none",
        "format": "JSON",
    }
    data = td_request("/time_series", params)
    values = data.get("values", []) if isinstance(data, dict) else []
    events = []
    try:
        rows = list(reversed(values))
        for i in range(1, len(rows)):
            prev = float(rows[i-1].get("close"))
            cur = float(rows[i].get("close"))
            if prev <= 0 or cur <= 0:
                continue
            ratio = cur / prev
            candidates = [(2, 1/2), (3, 1/3), (4, 1/4), (5, 1/5), (10, 1/10), (1/2, 2), (1/3, 3), (1/4, 4), (1/5, 5), (1/10, 10)]
            best = min(candidates, key=lambda x: abs(ratio - x[1]))
            factor = best[0]
            expected = best[1]
            if abs(ratio - expected) / max(abs(expected), 1e-9) <= 0.08:
                events.append({
                    "date": rows[i].get("datetime"),
                    "ratio": ratio,
                    "factor": factor,
                    "description": f"{factor}-for-1" if factor >= 1 else f"1-for-{int(round(1/factor))}",
                    "ticker_after": symbol,
                    "source": "detected_from_unadjusted_history",
                })
    except Exception:
        events = []
    result = events[-1] if events else None
    with split_cache_lock:
        SPLIT_CACHE[cache_key] = {"updated": now, "data": result}
    return result


def get_stock_split(symbol):
    """Get latest known split/reverse-split for a US symbol.
    Cached for 24h so the scanner does not request /splits every 2 minutes.
    Twelve Data may require a Grow/Venture plan for this endpoint.
    """
    if not symbol:
        return None

    now = time.time()
    with split_cache_lock:
        cached = SPLIT_CACHE.get(symbol)
        if cached and now - cached.get("updated", 0) < SPLIT_CACHE_TTL:
            return cached.get("data")

    data = td_request("/splits", {"symbol": symbol})
    split_data = None

    if isinstance(data, dict):
        events = data.get("splits") or []
        if events:
            # Latest event first when available; otherwise sort by date.
            events = sorted(
                [e for e in events if isinstance(e, dict)],
                key=lambda e: str(e.get("date", "")),
                reverse=True,
            )
            if events:
                e = events[0]
                split_data = {
                    "date": e.get("date"),
                    "description": e.get("description"),
                    "ratio": e.get("ratio"),
                    "from_factor": e.get("from_factor"),
                    "to_factor": e.get("to_factor"),
                }

    with split_cache_lock:
        SPLIT_CACHE[symbol] = {"updated": now, "data": split_data}

    return split_data


# ============================================================
# FORMAT
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

    return f"{value:.4f}"


def pct(value):
    if value is None:
        return "-"
    return f"{value:.1f}%"


# ============================================================
# TELEGRAM
# ============================================================

def ensure_direction_gifs():
    """Create looping green/red direction GIFs locally once at startup."""
    try:
        os.makedirs(DIRECTION_GIF_DIR, exist_ok=True)

        def make_gif(path, direction, title):
            if os.path.exists(path):
                return

            frames = []
            size = (420, 260)

            for i in range(8):
                img = Image.new("RGB", size, (18, 18, 24))
                draw = ImageDraw.Draw(img)

                # pulsing arrow size
                pulse = i if i <= 4 else 8 - i
                if direction == "up":
                    cx, cy = 210, 125 - pulse * 5
                    points = [
                        (210, 45 - pulse * 2),
                        (95, 165 - pulse * 2),
                        (165, 165 - pulse * 2),
                        (165, 215),
                        (255, 215),
                        (255, 165 - pulse * 2),
                        (325, 165 - pulse * 2),
                    ]
                    label = "UP"
                    fill = (40, 220, 100)
                else:
                    cx, cy = 210, 135 + pulse * 5
                    points = [
                        (95, 95 + pulse * 2),
                        (165, 95 + pulse * 2),
                        (165, 45),
                        (255, 45),
                        (255, 95 + pulse * 2),
                        (325, 95 + pulse * 2),
                        (210, 215 + pulse * 2),
                    ]
                    label = "DOWN"
                    fill = (240, 55, 65)

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

        make_gif(UP_GIF, "up", "AI PRO MAX")
        make_gif(DOWN_GIF, "down", "AI PRO MAX")
        return True
    except Exception as error:
        print(f"⚠️ تعذر إنشاء GIF الاتجاه: {error}")
        return False


def build_tradingview_url(result):
    """Build a TradingView chart URL for the symbol in the Telegram alert."""
    market = str(result.get("market", "")).upper()
    symbol = str(result.get("symbol", "")).strip()
    if not symbol:
        return None

    if market == "TASI":
        tv_symbol = f"TADAWUL:{symbol}"
    else:
        tv_symbol = symbol

    return "https://www.tradingview.com/chart/?symbol=" + quote(tv_symbol, safe="")


def tradingview_markup(url):
    """Telegram inline button: open the exact TradingView chart."""
    if not url:
        return None
    import json
    return json.dumps({
        "inline_keyboard": [[
            {"text": "📈 فتح في TradingView", "url": url}
        ]]
    }, ensure_ascii=False)


def telegram_send_animation(token, gif_path, caption, tradingview_url=None):
    if not token or not CHAT_ID or not os.path.exists(gif_path):
        return False

    session = get_session()
    url = f"https://api.telegram.org/bot{token}/sendAnimation"

    try:
        with open(gif_path, "rb") as gif_file:
            response = session.post(
                url,
                data={
                    "chat_id": CHAT_ID,
                    "caption": caption,
                    "parse_mode": "HTML",
                    "reply_markup": tradingview_markup(tradingview_url) if tradingview_url else None,
                },
                files={"animation": gif_file},
                timeout=(10, 60),
            )
        return response.ok
    except Exception:
        return False


def telegram_send_smart_animation(token, result):
    """Send one small animated arrow only when a smart movement is detected."""
    smart = result.get("smart", {})
    maker = smart.get("maker", 0)
    if not maker:
        return False

    direction = "up" if maker > 0 else "down"
    path = UP_GIF if direction == "up" else DOWN_GIF
    caption = "🐋 ↑ حركة صنّاع السهم" if maker > 0 else "🐋 ↓ حركة صنّاع السهم"
    return telegram_send_animation(token, path, caption, build_tradingview_url(result))


def telegram_send_direction(token, result):
    """Send a looping direction animation once when a new trend signal starts."""
    if result["trend"] == "UP":
        caption = "🟢 <b>اتجاه صاعد مستمر</b>\n⬆️ يستمر حتى ينتهي/ينعكس الاتجاه"
        return telegram_send_animation(token, UP_GIF, caption, build_tradingview_url(result))

    if result["trend"] == "DOWN":
        caption = "🔴 <b>اتجاه هابط مستمر</b>\n⬇️ يستمر حتى ينتهي/ينعكس الاتجاه"
        return telegram_send_animation(token, DOWN_GIF, caption, build_tradingview_url(result))

    return False


def telegram_send(token, message, tradingview_url=None):
    if not token or not CHAT_ID:
        return False

    # Telegram أيضاً يستخدم Session معاد الاستخدام
    session = get_session()

    url = f"https://api.telegram.org/bot{token}/sendMessage"

    try:
        response = session.post(
            url,
            data={
                "chat_id": CHAT_ID,
                "text": message,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
                "reply_markup": tradingview_markup(tradingview_url) if tradingview_url else None,
            },
            timeout=(10, 30),
        )
        return response.ok
    except Exception:
        return False


# ============================================================
# MESSAGE
# ============================================================

def escape_html(value):
    text = str(value if value is not None else "-")
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def build_message(result):
    market = result["market"]

    names = {
        "TASI": "🇸🇦 السوق السعودي (TASI)",
        "US": "🇺🇸 السوق الأمريكي (US)",
        "CRYPTO": "🪙 العملات الرقمية (CRYPTO)",
    }

    market_name = names.get(market, market)
    symbol = escape_html(result["symbol"])
    company_name = escape_html(result.get("name") or "")

    if result["trend"] == "UP":
        trend_text = "🟢 صاعد قوي"
        trend_icon = "📈"
    elif result["trend"] == "DOWN":
        trend_text = "🔴 هابط قوي"
        trend_icon = "📉"
    else:
        trend_text = "⚪ محايد"
        trend_icon = "↔️"

    if result["vwap"] is not None:
        vwap_text = (
            "🟢 فوق VWAP"
            if result["price"] > result["vwap"]
            else "🔴 تحت VWAP"
        )
    else:
        vwap_text = "⚪ VWAP غير متاح"

    change_pct = None
    if result.get("previous_close") not in (None, 0):
        change_pct = (result["price"] - result["previous_close"]) / result["previous_close"] * 100

    if result["signal"] == "BUY":
        signal_badge = "🟢 <b>شراء قوي</b>"
    elif result["signal"] == "SELL":
        signal_badge = "🔴 <b>بيع قوي</b>"
    else:
        signal_badge = "⚪ <b>انتظار</b>"

    smart = result.get("smart", {})
    movement_lines = []

    if smart.get("maker", 0) > 0:
        movement_lines.append("🐋 <b>↑ حركة صنّاع السهم</b>")
    elif smart.get("maker", 0) < 0:
        movement_lines.append("🐋 <b>↓ حركة صنّاع السهم</b>")

    if smart.get("speculators"):
        movement_lines.append("⚡ <b>حركة مضاربين قوية</b>")

    if smart.get("accumulation"):
        movement_lines.append("💰 <b>عمليات التجميع ✅</b>")

    if smart.get("unusual"):
        movement_lines.append("🔎 <b>رصد حركة غير اعتيادية</b>")

    lines = [
        "💀🚀 <b>AI PRO MAX SIGNAL</b>",
        "",
        f"{market_name}",
        f"<b>{symbol}</b>",
    ]

    lines.extend([
        "",
        f"{signal_badge}    🎯 قوة الإشارة: <b>{result['score']}/100</b>",
    ])

    # هذه هي العناصر المطلوبة فقط لإشعارات الحركة.
    if movement_lines:
        lines.extend(["", *movement_lines])

    pine = result.get("pine", {})
    indicator_lines = [
        "",
        "🧩 <b>تأكيد المؤشرات</b>",
        f"🧠 RSI 14: <b>{fmt(pine.get('rsi'))}</b>  " + ("🟢 أعلى 50" if (pine.get("rsi") is not None and pine.get("rsi") > 50) else "🔴 أقل 50" if pine.get("rsi") is not None else "⚪ غير متاح"),
        f"🟡 الشمعة الذهبية: <b>{'مؤكدة' if pine.get('golden_first') else 'استمرارية' if pine.get('golden_continue') else 'غير مؤكدة'}</b>",
        f"🤖 AI PRO MAX: <b>{'SMART BUY' if pine.get('final_buy') else 'SMART SELL' if pine.get('final_sell') else 'لا توجد إشارة نهائية'}</b>",
    ]
    lines.extend(indicator_lines)
    lines.extend([
        "",
        f"💰 <b>دخول:</b> {fmt(result.get('entry_price') or result['price'])}" + (f"  ({change_pct:+.2f}%)" if change_pct is not None else ""),
        f"🛑 <b>وقف الخسارة:</b> {fmt(result.get('stop_loss'))}",
        f"📊 <b>VWAP:</b> {fmt(result['vwap'])}  {vwap_text}",
        f"🧠 <b>RSI 14:</b> {fmt(result['rsi'])}",
        f"📐 <b>ATR 14:</b> {fmt(result['atr'])}",
        "",
        f"📈 <b>EMA 10:</b> {fmt(result.get('ema10'))}    <b>EMA 14:</b> {fmt(result.get('ema14'))}",
        f"📈 <b>EMA 15:</b> {fmt(result.get('ema15'))}    <b>EMA 25:</b> {fmt(result.get('ema25'))}",
        f"📈 <b>EMA 50:</b> {fmt(result.get('ema50'))}    <b>EMA 200:</b> {fmt(result.get('ema200'))}",
        "",
        f"🟢 <b>قوة الشراء:</b> {pct(result['buy_power'])}",
        f"🔴 <b>قوة البيع:</b> {pct(result['sell_power'])}",
        f"📦 <b>قوة الحجم:</b> {result['volume_ratio']:.2f}x",
        "",
        f"🛡️ <b>الدعم:</b> {fmt(result['support'])}",
        f"🚧 <b>المقاومة:</b> {fmt(result['resistance'])}",
        f"{trend_icon} <b>اتجاه السوق:</b> {trend_text}",
    ])

    if market == "US":
        lines.append(f"📰 <b>أخبار السهم:</b> {result['news']}")

        split_info = result.get("split_info")
        if split_info:
            lines.extend([
                "",
                "✂️ <b>تقسيم السهم</b>",
                f"📅 التاريخ: <b>{escape_html(split_info.get('date') or '-')}</b>",
                f"🔢 النسبة: <b>{escape_html(split_info.get('description') or '-')}</b>",
                f"📊 النسبة السعرية المرصودة: <b>{fmt(split_info.get('ratio'))}</b>",
                f"🏷️ الرمز بعد التقسيم: <b>{escape_html(split_info.get('ticker_after') or result['symbol'])}</b>",
            ])

    if result["targets"]:
        lines.extend(["", "🎯 <b>أهداف ATR — 8 أهداف</b>"])

        for i, target in enumerate(result["targets"], 1):
            change = (target - result["price"]) / result["price"] * 100 if result["price"] else 0
            lines.append(f"TP{i}: <b>{fmt(target)}</b> ({change:+.2f}%)")
        if result["targets"] and result.get("atr"):
            last = result["targets"][-1]
            extra = last + result["atr"] * 2 if result["signal"] == "BUY" else last - result["atr"] * 2
            lines.append(f"♾️ <b>استمرارية بعد TP8:</b> {fmt(extra)} → مع استمرار الاتجاه")

    if result.get("tasi_note"):
        lines.extend(["", f"ℹ️ {escape_html(result['tasi_note'])}"])

    lines.extend([
        "",
        "🟢/🔴 السهم المتحرك يستمر حتى انعكاس مؤكد (دورتان متتاليتان)",
        f"⏱️ {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')}",
    ])

    return "\n".join(lines)


# ============================================================
# DUPLICATE CONTROL
# ============================================================

def should_send(result):
    if result["signal"] == "WAIT":
        return False

    key = f"{result['market']}:{result['symbol']}"

    current_state = (
        result["signal"],
        result["trend"],
    )

    with state_lock:
        previous = LAST_SIGNAL.get(key)

        if previous == current_state:
            return False

        LAST_SIGNAL[key] = current_state

    return True


# ============================================================
# SYMBOL DISCOVERY
# ============================================================

def _extract_symbols(data):
    if isinstance(data, dict):
        values = data.get("data", [])
    elif isinstance(data, list):
        values = data
    else:
        values = []

    symbols = []

    for item in values:
        if not isinstance(item, dict):
            continue

        symbol = item.get("symbol")

        if symbol:
            symbols.append(str(symbol).strip())

    return list(dict.fromkeys(symbols))


def get_tasi_symbols():
    """TASI catalog from SAHMK only. Never falls back to Twelve Data."""
    symbols = []
    offset = 0
    page_size = 200
    while len(symbols) < TASI_MAX_SYMBOLS:
        data = sahmk_request("/companies/", {"market": "TASI", "limit": page_size, "offset": offset})
        if not isinstance(data, dict):
            break
        results = data.get("results") or []
        if not results:
            break
        before = len(symbols)
        for item in results:
            if not isinstance(item, dict):
                continue
            if str(item.get("status", "active")).lower() != "active":
                continue
            if str(item.get("security_type", "Equity")).lower() != "equity":
                continue
            if item.get("symbol"):
                symbols.append(str(item["symbol"]).strip())
        symbols = list(dict.fromkeys(symbols))
        total = int(data.get("total") or 0)
        offset += len(results)
        if offset >= total or len(results) < page_size or len(symbols) == before:
            break
    return sorted(set(symbols), key=str.upper)[:TASI_MAX_SYMBOLS]


def get_us_symbols():
    """
    🇺🇸 السوق الأمريكي: 13,402 رمز بالضبط كحد أعلى.
    نطلب قائمة الولايات المتحدة كاملة من TwelveData، ثم نرتبها ونأخذ
    أول 13,402 رمز بشكل ثابت حتى لا يتغير العدد عشوائياً بين الدورات.
    إذا تعذر فلتر الدولة، نستخدم البورصات الرئيسية كخطة احتياطية.
    """
    data = td_request(
        "/stocks",
        {"country": "United States"},
    )
    symbols = _extract_symbols(data)

    if not symbols:
        symbols = []
        for exchange in ("NASDAQ", "NYSE", "AMEX"):
            data = td_request(
                "/stocks",
                {"exchange": exchange},
            )
            symbols.extend(_extract_symbols(data))

    symbols = sorted(set(symbols), key=str.upper)
    return symbols[:US_MAX_SYMBOLS]


def get_crypto_symbols():
    data = td_request(
        "/cryptocurrencies",
        {},
    )

    return sorted(set(_extract_symbols(data)), key=str.upper)


# ============================================================
# SYMBOL CACHE
# ============================================================

def get_symbols(market, loader):
    now = time.time()

    with symbol_cache_lock:
        cached = SYMBOL_CACHE[market]

        if (
            cached["symbols"]
            and now - cached["updated"] < SYMBOL_REFRESH_SECONDS
        ):
            return list(cached["symbols"])

    symbols = loader()

    if symbols:
        with symbol_cache_lock:
            SYMBOL_CACHE[market] = {
                "symbols": list(symbols),
                "updated": now,
            }

    return symbols


# ============================================================
# 🔎 FAST FILTER
# ============================================================

def fast_filter_symbol(symbol, market):
    """
    مرحلة أولى خفيفة: تستخدم 15min فقط لاختيار الرموز الأكثر نشاطًا.
    لا تصدر أي إشارة Telegram هنا؛ الفحص العميق هو الذي يقرر الإشارة.
    """
    series = get_series(symbol, market, interval="15min")
    if not series:
        return None

    candles = series.get("candles") or []
    if len(candles) < 30:
        return None

    closes = [c["close"] for c in candles]
    volumes = [c.get("volume", 0.0) or 0.0 for c in candles]
    price = closes[-1]
    prev = closes[-2] if len(closes) > 1 else price
    if price <= 0 or prev <= 0:
        return None

    move = abs(price - prev) / prev * 100.0
    lookback = min(20, len(closes) - 1)
    base = closes[-1 - lookback]
    move_window = abs(price - base) / base * 100.0 if base > 0 else 0.0

    last_vol = volumes[-1]
    avg_vol = sum(volumes[-21:-1]) / max(1, len(volumes[-21:-1])) if len(volumes) >= 21 else 0.0
    volume_ratio = (last_vol / avg_vol) if avg_vol > 0 else 1.0

    ema8 = ema(closes, 8)
    ema21 = ema(closes, 21)
    trend_bonus = 0.0
    if ema8 is not None and ema21 is not None:
        if ema8 > ema21:
            trend_bonus = 1.0
        elif ema8 < ema21:
            trend_bonus = 1.0

    threshold = FAST_FILTER_MIN_MOVE.get(market, 0.5)
    active = (
        move >= threshold
        or move_window >= threshold * 1.5
        or volume_ratio >= 1.5
    )

    if not active:
        return None

    score = move * 2.0 + move_window + max(0.0, volume_ratio - 1.0) * 5.0 + trend_bonus
    return {
        "symbol": symbol,
        "score": score,
        "move": move,
        "move_window": move_window,
        "volume_ratio": volume_ratio,
    }


def build_fast_candidates(symbols, market):
    """Run the light first pass and return only the strongest candidates."""
    total = len(symbols)
    limit = FAST_FILTER_LIMIT.get(market, 300)
    candidates = []
    completed = 0
    batch_size = MAX_WORKERS * 10

    print(f"[{market}] 🔎 FAST FILTER بدء | {total} رمز | limit={limit}")

    for start in range(0, total, batch_size):
        batch = symbols[start:start + batch_size]
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            jobs = {executor.submit(fast_filter_symbol, symbol, market): symbol for symbol in batch}
            for job in as_completed(jobs):
                completed += 1
                try:
                    item = job.result()
                    if item:
                        candidates.append(item)
                except Exception as error:
                    print(f"[{market}] FAST FILTER error: {error}")

        if completed % 100 == 0 or completed == total:
            print(f"[{market}] FAST FILTER progress {completed}/{total} | candidates={len(candidates)}")

    candidates.sort(key=lambda x: x["score"], reverse=True)
    selected = [x["symbol"] for x in candidates[:limit]]
    print(f"[{market}] 🎯 FAST FILTER انتهى | {total} → {len(selected)} مرشح للفحص العميق")
    return selected


# ============================================================
# MARKET SCANNER
# ============================================================

def scan_tasi_sahmk(symbols, token):
    """Quota-safe TASI scan using SAHMK market-wide endpoints and cached quotes.
    Free SAHMK does not expose historical OHLCV, so full RSI/ATR history is not fabricated.
    """
    if not token or not symbols:
        return
    candidates = {}
    for endpoint in ("/market/gainers/", "/market/losers/", "/market/volume/", "/market/value/"):
        data = sahmk_request(endpoint, {"limit": 25, "index": "TASI"})
        rows = (data or {}).get("results") or (data or {}).get("data") or []
        if isinstance(rows, list):
            for row in rows:
                if not isinstance(row, dict):
                    continue
                sym = str(row.get("symbol") or row.get("ticker") or "").strip()
                if sym:
                    candidates[sym] = row
    # Keep only TASI catalog symbols and randomize the order.
    allowed = set(symbols)
    selected = [s for s in candidates if s in allowed]
    random.shuffle(selected)
    print(f"[TASI] 🇸🇦 SAHMK market scan | candidates={len(selected)} | history=unavailable on Free")
    for symbol in selected:
        q = get_sahmk_quote(symbol)
        if not q:
            continue
        change = float(q.get("change_percent", 0) or 0)
        if abs(change) < 1.0:
            continue
        signal = "BUY" if change > 0 else "SELL"
        trend = "UP" if change > 0 else "DOWN"
        score = min(100, int(60 + min(40, abs(change) * 8)))
        result = {
            "market": "TASI", "symbol": symbol, "name": q.get("name") or symbol,
            "price": q.get("price"), "entry_price": q.get("price"), "previous_close": None,
            "ema10": None, "ema14": None, "ema15": None, "ema25": None, "ema50": None, "ema200": None,
            "rsi": None, "atr": None, "vwap": None, "support": None, "resistance": None,
            "ars": None, "ars_level": None, "buy_power": None, "sell_power": None, "volume_ratio": None,
            "trend": persistent_trend("TASI", symbol, trend), "score": score, "signal": signal,
            "signal_text": "🟢 حركة إيجابية — SAHMK" if signal == "BUY" else "🔴 حركة سلبية — SAHMK",
            "news": "⚪ غير متاح", "split_info": None, "targets": [], "stop_loss": None,
            "divergence": {}, "trendline_bias": 0,
            "smart": {"maker": 0, "speculators": abs(change) >= 3, "accumulation": change >= 1.5, "unusual": abs(change) >= 3},
            "pine": {}, "timeframe": "market", "indicator_triggers": [],
            "tasi_note": "السعر والحركة من SAHMK؛ المؤشرات التاريخية غير متاحة على الخطة المجانية.",
        }
        if should_send(result):
            enqueue_signal(token, result)


def scan_market(symbols, market, token):
    if not symbols:
        print(f"[{market}] لا توجد رموز للفحص")
        return

    if market == "TASI":
        scan_tasi_sahmk(symbols, token)
        return

    # فحص كامل A→Z مع ترتيب عشوائي جديد في كل دورة.
    symbols = list(symbols)
    random.shuffle(symbols)
    total = len(symbols)
    print(f"[{market}] 🧠 فحص كامل A→Z عشوائي: {total} رمز | Batch={BATCH_SYMBOLS} | 5min أولاً")

    batch_load_series(symbols, market, "5min")

    completed = 0
    signals = 0
    BATCH_SIZE = MAX_WORKERS * 10

    for start in range(0, total, BATCH_SIZE):
        batch = symbols[start:start + BATCH_SIZE]
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            jobs = {executor.submit(analyze_symbol, symbol, market): symbol for symbol in batch}
            for job in as_completed(jobs):
                completed += 1
                try:
                    result = job.result()
                    if result and should_send(result):
                        if enqueue_signal(token, result):
                            signals += 1
                except Exception as error:
                    print(f"[{market}] تحليل خطأ: {error}")
        if completed % 100 == 0 or completed == total:
            print(f"[{market}] progress {completed}/{total} | signals={signals}")

    print(f"[{market}] انتهى الفحص | فحص={completed} | إشارات={signals}")


# ============================================================
# MARKET LOOP
# ============================================================

def market_loop(market, token, loader):
    while True:
        try:
            symbols = get_symbols(market, loader)

            print(
                f"💀 {market}: تم تحميل "
                f"{len(symbols)} رمز"
            )

            # لا يوجد FAST FILTER ولا ترتيب عشوائي: الفحص كامل A→Z.
            scan_market(symbols, market, token)

        except Exception as error:
            print(
                f"[{market}] loop error: {error}"
            )

        time.sleep(SCAN_INTERVAL)


# ============================================================
# HEARTBEAT
# ============================================================

def heartbeat():
    while True:
        print(
            "💀🚀 AI PRO MAX يعمل 24/7 | "
            + datetime.now(timezone.utc).strftime(
                "%Y-%m-%d %H:%M:%S"
            )
        )
        time.sleep(300)


# ============================================================
# START
# ============================================================

def main():
    print("=" * 68)
    print("💀🚀 AI PRO MAX — INSTANT SIGNAL EDITION")
    print("🇺🇸 US MARKET — 13,414 SYMBOLS | $0.15+ | A→Z | 24/7 | PRE + REGULAR + POST")
    print("🪙 CRYPTO MARKET — FULL | 24/7")
    print("🇸🇦 TASI — مفصول إلى TASI.py في خدمة Railway مستقلة")
    print("⏱️ الدورة: كل 5 دقائق | 5m كامل ثم تأكيد 15m → 30m → 1h → 4h | Batch + حماية الحصة")
    print("=" * 68)

    if not TWELVEDATA_API_KEY:
        print("❌ TWELVEDATA_API_KEY غير موجود")
        return

    if not CHAT_ID:
        print("❌ CHAT_ID غير موجود")
        return

    print("🟢 Twelve Data API: OK | 🇺🇸 US + 🪙 CRYPTO فقط")
    print("🟢 SAHMK API: OK | 🇸🇦 TASI فقط — بدون Twelve Data")
    print("🟢 CHAT_ID: OK")

    if ensure_direction_gifs():
        print("🟢 Telegram Direction GIFs: OK | 🟢 UP + 🔴 DOWN | LOOP")

    print("🇺🇸 US TOKEN:", "OK" if US_TOKEN else "MISSING")
    print("🪙 CRYPTO TOKEN:", "OK" if CRYPTO_TOKEN else "MISSING")
    print("🇸🇦 TASI: OFF هنا — يعمل من TASI.py المستقل")

    threading.Thread(
        target=telegram_worker,
        daemon=True,
        name="TelegramInstantSender",
    ).start()
    print("⚡ Telegram Instant Sender: ON")

    threading.Thread(
        target=heartbeat,
        daemon=True,
    ).start()

    threading.Thread(
        target=market_loop,
        args=("US", US_TOKEN, get_us_symbols),
        daemon=True,
    ).start()

    threading.Thread(
        target=market_loop,
        args=("CRYPTO", CRYPTO_TOKEN, get_crypto_symbols),
        daemon=True,
    ).start()

    while True:
        time.sleep(60)


if __name__ == "__main__":
    main()