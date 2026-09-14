# ============================================================
# AI PRO MAX — TASI + US + CRYPTO
# Stable / Low-Connection Edition
# ============================================================

import os
import time
import threading
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock, local

import requests
from PIL import Image, ImageDraw

# ============================================================
# VARIABLES — Railway
# ============================================================

TWELVEDATA_API_KEY = os.getenv("TWELVEDATA_API_KEY", "").strip()
CHAT_ID = os.getenv("CHAT_ID", "").strip()

TASI_TOKEN = os.getenv("TASI_TOKEN", "").strip()
US_TOKEN = os.getenv("US_TOKEN", "").strip()
CRYPTO_TOKEN = os.getenv("CRYPTO_TOKEN", "").strip()

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

# لا نفتح آلاف الاتصالات معًا
MAX_WORKERS = 4

# الحد الأدنى بين طلبات TwelveData
REQUEST_GAP = 0.25

# إعادة المحاولة عند 429 / أخطاء مؤقتة
MAX_RETRIES = 3

# بعد انتهاء دفعة الفحص، يبدأ التالي
SCAN_INTERVAL = 120

# تحديث قوائم الرموز كل 6 ساعات بدل طلبها كل دورتين
SYMBOL_REFRESH_SECONDS = 21600

PRIMARY_TIMEFRAME = "15min"
OUTPUTSIZE = 220

# 🇺🇸 لا ترسل/تعتمد إشارات للأسهم الأمريكية الأقل من 0.20$
# جميع الأسهم من 0.20$ فأعلى تبقى ضمن الفحص.
MIN_US_PRICE = 0.20
US_MAX_SYMBOLS = 13402

EMA_FAST = 8
EMA_MID = 21
EMA_SLOW = 50
EMA_LONG = 200

RSI_LENGTH = 14
ATR_LENGTH = 14
VOLUME_LENGTH = 20

MIN_SIGNAL_SCORE = 70

ATR_TARGETS = [
    1.0, 1.5, 2.0, 2.5,
    3.0, 3.5, 4.0, 5.0
]

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

symbol_cache_lock = Lock()
SYMBOL_CACHE = {
    "TASI": {"symbols": [], "updated": 0},
    "US": {"symbols": [], "updated": 0},
    "CRYPTO": {"symbols": [], "updated": 0},
}

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


def td_request(endpoint, params=None):
    """
    طلب آمن:
    - Session reuse
    - Rate limit
    - Retry
    - معالجة 429
    - لا يفتح آلاف الاتصالات
    """
    if not TWELVEDATA_API_KEY:
        return None

    params = dict(params or {})
    params["apikey"] = TWELVEDATA_API_KEY

    session = get_session()

    for attempt in range(MAX_RETRIES):
        try:
            rate_wait()

            response = session.get(
                BASE_URL + endpoint,
                params=params,
                timeout=(10, 30),
            )

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

def get_series(symbol, market, interval=PRIMARY_TIMEFRAME):
    params = {
        "symbol": symbol,
        "interval": interval,
        "outputsize": OUTPUTSIZE,
        "format": "JSON",
    }

    # 🇺🇸 الأمريكي يعمل بلا أي قيد زمني: قبل السوق + أثناء السوق + بعد الإغلاق.
    # prepost=true لطلب بيانات الجلسات الممتدة عند دعمها من خطة TwelveData.
    # إذا كانت الخطة تدعم TwelveData Extended Hours.
    # لا توجد أي بوابة زمنية هنا؛ البوت يبقى شغال 24/7.
    if market == "US":
        params["prepost"] = "true"

    data = td_request("/time_series", params)

    # إذا كانت الخطة لا تدعم prepost، نرجع تلقائيًا للبيانات العادية
    # بدل توقف الفحص بالكامل.
    if data is None and market == "US":
        params.pop("prepost", None)
        data = td_request("/time_series", params)

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
                # Extended-hours bars may not contain volume.
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

    e8 = ema(closes, EMA_FAST)
    e21 = ema(closes, EMA_MID)
    e50 = ema(closes, EMA_SLOW)
    e200 = ema(closes, EMA_LONG)

    if None in (e8, e21, e50, e200):
        return "NEUTRAL"

    current = closes[-1]

    bullish = 0
    bearish = 0

    if e8 > e21:
        bullish += 1
    else:
        bearish += 1

    if e21 > e50:
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
    key = f"{market}:{symbol}"

    with state_lock:
        previous = TREND_STATE.get(key)

        if current_trend == "NEUTRAL":
            return previous or "NEUTRAL"

        TREND_STATE[key] = current_trend
        return current_trend


# ============================================================
# ARS
# ============================================================

def calculate_ars(candles):
    closes = [c["close"] for c in candles]

    if len(closes) < 50:
        return 50

    e8 = ema(closes, 8)
    e21 = ema(closes, 21)
    e50 = ema(closes, 50)

    score = 50
    current = closes[-1]

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

    return max(0, min(100, score))


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
    if not atr_value or atr_value <= 0:
        return []

    result = []

    for multiplier in ATR_TARGETS:
        if direction == "UP":
            result.append(price + atr_value * multiplier)
        else:
            result.append(price - atr_value * multiplier)

    return result


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
# ANALYSIS
# ============================================================

def analyze_symbol(symbol, market):
    series = get_series(symbol, market)

    if not series:
        return None

    candles = series["candles"]
    company_name = series.get("name") or ""

    closes = [c["close"] for c in candles]
    highs = [c["high"] for c in candles]
    lows = [c["low"] for c in candles]
    volumes = [c["volume"] for c in candles]

    price = closes[-1]

    # 🇺🇸 نطاق الأمريكي المطلوب: 0.20$ فأعلى
    # لا يوجد قيد ساعات: قبل السوق + أثناء السوق + بعد الإغلاق + 24/7.
    if market == "US" and price < MIN_US_PRICE:
        return None

    previous_close = closes[-2] if len(closes) >= 2 else None

    e8 = ema(closes, EMA_FAST)
    e21 = ema(closes, EMA_MID)
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
    trend = persistent_trend(market, symbol, raw_trend)

    score = 50

    if e8 is not None:
        score += 5 if price > e8 else -5

    if e8 is not None and e21 is not None:
        score += 7 if e8 > e21 else -7

    if e21 is not None and e50 is not None:
        score += 7 if e21 > e50 else -7

    if e50 is not None and e200 is not None:
        score += 7 if e50 > e200 else -7

    if vwap_value is not None:
        score += 7 if price > vwap_value else -7

    if rsi_value is not None:
        if 50 <= rsi_value <= 70:
            score += 8
        elif 30 <= rsi_value < 50:
            score += 2
        elif rsi_value < 30:
            score += 5
        elif rsi_value > 70:
            score -= 3

    score += 8 if buy_power > sell_power else -8

    if volume_ratio >= 1.5:
        score += 5

    score = max(0, min(100, score))

    if (
        trend == "UP"
        and score >= MIN_SIGNAL_SCORE
        and buy_power >= sell_power
    ):
        signal = "BUY"
        signal_text = "🟢 شراء قوي"

    elif (
        trend == "DOWN"
        and score <= 45
        and sell_power >= buy_power
    ):
        signal = "SELL"
        signal_text = "🔴 بيع قوي"

    else:
        signal = "WAIT"
        signal_text = "⚪ انتظار"

    targets = []

    if signal != "WAIT":
        direction = "UP" if signal == "BUY" else "DOWN"
        targets = calculate_targets(
            price,
            atr_value,
            direction,
        )

    # الأخبار فقط عند وجود إشارة قوية
    if market == "US" and signal != "WAIT":
        news = news_sentiment(symbol)
    else:
        news = "⚪ غير متاح"

    return {
        "symbol": symbol,
        "name": company_name,
        "market": market,
        "price": price,
        "previous_close": previous_close,
        "ema8": e8,
        "ema21": e21,
        "ema50": e50,
        "ema200": e200,
        "rsi": rsi_value,
        "atr": atr_value,
        "vwap": vwap_value,
        "support": support,
        "resistance": resistance,
        "ars": ars,
        "buy_power": buy_power,
        "sell_power": sell_power,
        "volume_ratio": volume_ratio,
        "trend": trend,
        "score": score,
        "signal": signal,
        "signal_text": signal_text,
        "news": news,
        "targets": targets,
    }


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


def telegram_send_animation(token, gif_path, caption):
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
                },
                files={"animation": gif_file},
                timeout=(10, 60),
            )
        return response.ok
    except Exception:
        return False


def telegram_send_direction(token, result):
    """Send a looping direction animation once when a new trend signal starts."""
    if result["trend"] == "UP":
        caption = "🟢 <b>اتجاه صاعد مستمر</b>\n⬆️ يستمر حتى ينتهي/ينعكس الاتجاه"
        return telegram_send_animation(token, UP_GIF, caption)

    if result["trend"] == "DOWN":
        caption = "🔴 <b>اتجاه هابط مستمر</b>\n⬇️ يستمر حتى ينتهي/ينعكس الاتجاه"
        return telegram_send_animation(token, DOWN_GIF, caption)

    return False


def telegram_send(token, message):
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

    lines = [
        "💀🚀 <b>AI PRO MAX SIGNAL</b>",
        "",
        f"{market_name}",
        f"<b>{symbol}</b>",
    ]

    if company_name and company_name.lower() != result["symbol"].lower():
        lines.append(f"{company_name}")

    lines.extend([
        "",
        f"{signal_badge}    🎯 قوة الإشارة: <b>{result['score']}/100</b>",
        "",
        f"💰 <b>السعر:</b> {fmt(result['price'])}" + (f"  ({change_pct:+.2f}%)" if change_pct is not None else ""),
        f"📊 <b>VWAP:</b> {fmt(result['vwap'])}  {vwap_text}",
        f"🧠 <b>RSI 14:</b> {fmt(result['rsi'])}",
        f"📐 <b>ATR 14:</b> {fmt(result['atr'])}",
        "",
        f"📈 <b>EMA 8:</b> {fmt(result['ema8'])}    <b>EMA 21:</b> {fmt(result['ema21'])}",
        f"📈 <b>EMA 50:</b> {fmt(result['ema50'])}    <b>EMA 200:</b> {fmt(result['ema200'])}",
        "",
        f"🟢 <b>قوة الشراء:</b> {pct(result['buy_power'])}",
        f"🔴 <b>قوة البيع:</b> {pct(result['sell_power'])}",
        f"📦 <b>قوة الحجم:</b> {result['volume_ratio']:.2f}x",
        "",
        f"🛡️ <b>الدعم:</b> {fmt(result['support'])}",
        f"🚧 <b>المقاومة:</b> {fmt(result['resistance'])}",
        f"{trend_icon} <b>اتجاه السوق:</b> {trend_text}",
        f"🧭 <b>ARS:</b> {result['ars']}/100",
    ])

    if market == "US":
        lines.append(f"📰 <b>أخبار السهم:</b> {result['news']}")
        lines.append("🕒 <b>الوضع:</b> قبل السوق / أثناء السوق / بعد الإغلاق — الفحص مستمر 24/7")
    elif market == "TASI":
        lines.append("🕒 <b>الوضع:</b> المزاد / التداول / ما بعد الإغلاق — الفحص مستمر 24/7")
    else:
        lines.append("🕒 <b>الوضع:</b> سوق يعمل 24/7")

    if result["targets"]:
        lines.extend([
            "",
            "🎯 <b>أهداف ATR — 8 أهداف</b>",
        ])

        for i, target in enumerate(result["targets"], 1):
            if result["price"]:
                change = (target - result["price"]) / result["price"] * 100
            else:
                change = 0

            lines.append(f"TP{i}: <b>{fmt(target)}</b> ({change:+.2f}%)")

    lines.extend([
        "",
        "🤖 <b>الفحص تلقائي بالكامل</b>",
        "🔄 الاتجاه يستمر حتى ظهور انعكاس مؤكد",
        f"⏱️ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
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
    data = td_request(
        "/stocks",
        {"exchange": "TADAWUL"},
    )

    return _extract_symbols(data)[:375]


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

    return _extract_symbols(data)


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
# MARKET SCANNER
# ============================================================

def scan_market(symbols, market, token):
    if not symbols:
        print(f"[{market}] لا توجد رموز للفحص")
        return

    total = len(symbols)

    print(
        f"[{market}] بدء الفحص: {total} رمز | "
        f"Workers={MAX_WORKERS}"
    )

    completed = 0
    signals = 0

    # دفعات صغيرة:
    # لا نضع آلاف Future objects في الذاكرة دفعة واحدة.
    BATCH_SIZE = MAX_WORKERS * 10

    for start in range(0, total, BATCH_SIZE):
        batch = symbols[start:start + BATCH_SIZE]

        with ThreadPoolExecutor(
            max_workers=MAX_WORKERS
        ) as executor:

            jobs = {
                executor.submit(
                    analyze_symbol,
                    symbol,
                    market,
                ): symbol
                for symbol in batch
            }

            for job in as_completed(jobs):
                completed += 1

                try:
                    result = job.result()

                    if not result:
                        continue

                    if should_send(result):
                        # اتجاه متحرك: الأخضر يستمر مع الاتجاه الصاعد،
                        # والأحمر يستمر مع الاتجاه الهابط حتى تتغير الحالة.
                        telegram_send_direction(token, result)

                        message = build_message(result)

                        if telegram_send(token, message):
                            signals += 1

                            print(
                                f"[{market}] 📲 "
                                f"{result['symbol']} "
                                f"{result['signal']} "
                                f"{result['score']}/100"
                            )

                except Exception as error:
                    print(
                        f"[{market}] تحليل خطأ: {error}"
                    )

        if completed % 100 == 0 or completed == total:
            print(
                f"[{market}] progress "
                f"{completed}/{total} | "
                f"signals={signals}"
            )

    print(
        f"[{market}] انتهى الفحص | "
        f"فحص={total} | إشارات مرسلة={signals}"
    )


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

            scan_market(
                symbols,
                market,
                token,
            )

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
            + datetime.now().strftime(
                "%Y-%m-%d %H:%M:%S"
            )
        )
        time.sleep(300)


# ============================================================
# START
# ============================================================

def main():
    print("=" * 68)
    print("💀🚀 AI PRO MAX — STABLE EDITION")
    print("🇸🇦 TASI 375 — 24/7")
    print("🇺🇸 US MARKET — FULL US | $0.20+ | 24/7 | PRE + REGULAR + POST")
    print("🪙 CRYPTO MARKET — FULL | 24/7")
    print("=" * 68)

    if not TWELVEDATA_API_KEY:
        print("❌ TWELVEDATA_API_KEY غير موجود")
        return

    if not CHAT_ID:
        print("❌ CHAT_ID غير موجود")
        return

    print("🟢 TWELVEDATA_API_KEY: OK")
    print("🟢 CHAT_ID: OK")

    if ensure_direction_gifs():
        print("🟢 Telegram Direction GIFs: OK | 🟢 UP + 🔴 DOWN | LOOP")

    print("🇸🇦 TASI TOKEN:", "OK" if TASI_TOKEN else "MISSING")
    print("🇺🇸 US TOKEN:", "OK" if US_TOKEN else "MISSING")
    print("🪙 CRYPTO TOKEN:", "OK" if CRYPTO_TOKEN else "MISSING")

    threading.Thread(
        target=heartbeat,
        daemon=True,
    ).start()

    threading.Thread(
        target=market_loop,
        args=("TASI", TASI_TOKEN, get_tasi_symbols),
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
