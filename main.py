
# ============================================================
# 💀🚀 AI PRO MAX — FINAL MARKET HUNTER
# 🇺🇸 US | 🇸🇦 TASI | 🪙 CRYPTO
# Twelve Data + SAHMK ONLY
# ============================================================

import os
import asyncio
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

import aiohttp

# -------------------- الإعدادات --------------------

TWELVE_API_KEY = (
    os.getenv("TWELVE_DATA_API_KEY")
    or os.getenv("TWELVEDATA_API_KEY")
)

SAHMK_API_KEY = os.getenv("SAHMK_API_KEY")

CHAT_ID = os.getenv("CHAT_ID")
US_TOKEN = os.getenv("US_TOKEN")
CRYPTO_TOKEN = os.getenv("CRYPTO_TOKEN")
TASI_TOKEN = os.getenv("TASI_TOKEN") or US_TOKEN

US_SYMBOLS = os.getenv("US_SYMBOLS", "AAPL,TSLA,NVDA,AMD,PLTR").split(",")
CRYPTO_SYMBOLS = os.getenv(
    "CRYPTO_SYMBOLS",
    "BTC/USD,ETH/USD,SOL/USD,XRP/USD"
).split(",")

SCAN_SECONDS = int(os.getenv("SCAN_SECONDS", "300"))
TASI_SCAN_SECONDS = int(os.getenv("TASI_SCAN_SECONDS", "1800"))

US_MIN_VOLUME_RATIO = float(os.getenv("US_MIN_VOLUME_RATIO", "1.8"))
CRYPTO_MIN_VOLUME_RATIO = float(os.getenv("CRYPTO_MIN_VOLUME_RATIO", "1.8"))
MIN_SCORE = int(os.getenv("MIN_SCORE", "65"))

TD_BASE = "https://api.twelvedata.com"
SAHMK_BASE = "https://api.sahmk.sa/api/v1"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

# منع تكرار التنبيه لنفس السهم
sent_signals = {}

# -------------------- أدوات عامة --------------------

def clean_symbols(items):
    return list(dict.fromkeys(
        x.strip().upper() for x in items if x.strip()
    ))


US_SYMBOLS = clean_symbols(US_SYMBOLS)
CRYPTO_SYMBOLS = clean_symbols(CRYPTO_SYMBOLS)


def number(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def ema(values, period):
    if len(values) < period:
        return None

    multiplier = 2 / (period + 1)
    result = sum(values[:period]) / period

    for value in values[period:]:
        result = (value * multiplier) + (
            result * (1 - multiplier)
        )

    return result


def calculate_rsi(values, period=14):
    if len(values) <= period:
        return 50

    gains = []
    losses = []

    for i in range(1, len(values)):
        change = values[i] - values[i - 1]
        gains.append(max(change, 0))
        losses.append(abs(min(change, 0)))

    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period

    if avg_loss == 0:
        return 100

    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def volume_ratio(volumes):
    if len(volumes) < 21:
        return 0

    previous = sum(volumes[-21:-1]) / 20

    if previous <= 0:
        return 0

    return volumes[-1] / previous


def calculate_vwap(rows):
    total_value = 0
    total_volume = 0

    for row in rows:
        typical = (
            number(row.get("high")) +
            number(row.get("low")) +
            number(row.get("close"))
        ) / 3

        vol = number(row.get("volume"))

        total_value += typical * vol
        total_volume += vol

    if total_volume == 0:
        return 0

    return total_value / total_volume


def support_resistance(rows):
    previous = rows[-21:-1]

    if not previous:
        return 0, 0

    support = min(number(x.get("low")) for x in previous)
    resistance = max(number(x.get("high")) for x in previous)

    return support, resistance


def signal_cooldown(symbol, signal, seconds=1800):
    key = f"{symbol}:{signal}"
    now = datetime.now().timestamp()

    previous = sent_signals.get(key, 0)

    if now - previous < seconds:
        return False

    sent_signals[key] = now
    return True


# -------------------- HTTP --------------------

async def get_json(session, url, params=None, headers=None):
    try:
        async with session.get(
            url,
            params=params,
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=20)
        ) as response:

            data = await response.json(content_type=None)

            if response.status != 200:
                logging.warning("HTTP %s: %s", response.status, data)
                return None

            if isinstance(data, dict) and data.get("status") == "error":
                logging.warning("API error: %s", data.get("message"))
                return None

            if isinstance(data, dict) and data.get("code"):
                logging.warning("API error: %s", data)
                return None

            return data

    except Exception as error:
        logging.warning("Request error: %s", error)
        return None


# -------------------- تيليجرام --------------------

async def telegram_send(session, token, message):
    if not token or not CHAT_ID:
        logging.warning("Telegram token or CHAT_ID missing")
        return

    url = f"https://api.telegram.org/bot{token}/sendMessage"

    payload = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }

    try:
        async with session.post(
            url,
            json=payload,
            timeout=aiohttp.ClientTimeout(total=20)
        ) as response:

            result = await response.json(content_type=None)

            if not result.get("ok"):
                logging.warning("Telegram error: %s", result)

    except Exception as error:
        logging.error("Telegram send failed: %s", error)


# -------------------- Twelve Data --------------------

async def get_td_candles(session, symbol, market):
    if not TWELVE_API_KEY:
        return None

    params = {
        "symbol": symbol,
        "interval": "5min",
        "outputsize": 80,
        "apikey": TWELVE_API_KEY
    }

    # بيانات ما قبل السوق وما بعده للأسهم الأمريكية
    if market == "US":
        params["prepost"] = "true"

    data = await get_json(
        session,
        f"{TD_BASE}/time_series",
        params=params
    )

    if not data or not isinstance(data, dict):
        return None

    values = data.get("values")

    if not values or not isinstance(values, list):
        return None

    # Twelve Data يعيد الأحدث أولاً
    return list(reversed(values))


async def analyze_td_symbol(session, symbol, market):
    rows = await get_td_candles(session, symbol, market)

    if not rows or len(rows) < 25:
        return

    closes = [number(x.get("close")) for x in rows]
    highs = [number(x.get("high")) for x in rows]
    lows = [number(x.get("low")) for x in rows]
    volumes = [number(x.get("volume")) for x in rows]

    price = closes[-1]
    previous_price = closes[-2]

    if price <= 0:
        return

    ema9 = ema(closes, 9)
    ema21 = ema(closes, 21)
    rsi = calculate_rsi(closes)
    vwap = calculate_vwap(rows)
    vol_ratio = volume_ratio(volumes)

    support, resistance = support_resistance(rows)

    score = 0
    reasons = []

    # اتجاه المتوسطات
    if ema9 and ema21 and ema9 > ema21:
        score += 15
        reasons.append("تقاطع متوسطات إيجابي")

    # السعر فوق VWAP
    if vwap and price > vwap:
        score += 15
        reasons.append("السعر أعلى VWAP")

    # السيولة النسبية
    min_ratio = (
        US_MIN_VOLUME_RATIO if market == "US"
        else CRYPTO_MIN_VOLUME_RATIO
    )

    if vol_ratio >= min_ratio:
        score += 20
        reasons.append(f"حجم تداول مرتفع ×{vol_ratio:.1f}")

    # RSI
    if 50 <= rsi <= 75:
        score += 10
        reasons.append(f"RSI إيجابي {rsi:.1f}")

    # اختراق المقاومة
    breakout = resistance > 0 and price > resistance

    if breakout:
        score += 25
        reasons.append("اختراق مقاومة")

    # بداية حركة صاعدة
    early_move = (
        ema9 is not None
        and ema21 is not None
        and price > ema9
        and previous_price <= ema9
    )

    if early_move:
        score += 10
        reasons.append("بداية انطلاقة محتملة")

    # قوة الشمعة
    candle_range = highs[-1] - lows[-1]

    if candle_range > 0:
        close_position = (price - lows[-1]) / candle_range

        if close_position >= 0.75:
            score += 5
            reasons.append("إغلاق قريب من أعلى الشمعة")

    if score < MIN_SCORE:
        return

    signal = "اختراق مؤكد" if breakout else "إشارة مبكرة"

    if not signal_cooldown(symbol, signal):
        return

    # ATR مبسط لحساب مستويات المتابعة
    ranges = [
        highs[i] - lows[i]
        for i in range(max(0, len(rows) - 14), len(rows))
    ]

    atr = sum(ranges) / max(len(ranges), 1)

    stop = price - (atr * 1.5)
    targets = [
        price + (atr * multiplier)
        for multiplier in range(1, 9)
    ]

    currency = "USD"

    message = (
        f"💀🚀 <b>AI PRO MAX — MARKET HUNTER</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🌍 السوق: {market}\n"
        f"📌 الرمز: <b>{symbol}</b>\n"
        f"💰 السعر: {price:.6f} {currency}\n"
        f"🎯 الإشارة: <b>{signal}</b>\n"
        f"⭐ قوة الإشارة: {score}/100\n"
        f"📊 RSI: {rsi:.1f}\n"
        f"💹 حجم التداول: ×{vol_ratio:.2f}\n"
        f"📈 VWAP: {vwap:.6f}\n"
        f"🟢 الدعم: {support:.6f}\n"
        f"🔴 المقاومة: {resistance:.6f}\n"
        f"🛑 وقف متابعة: {stop:.6f}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📍 <b>أسباب الإشارة:</b>\n"
    )

    for reason in reasons:
        message += f"• {reason}\n"

    message += "\n🎯 <b>الأهداف الفنية:</b>\n"

    for index, target in enumerate(targets, 1):
        message += f"TP{index}: {target:.6f}\n"

    message += (
        "\n⚠️ هذه إشارة تحليل فني وليست توصية شراء.\n"
        "لا يوجد تنفيذ صفقات تلقائي."
    )

    token = US_TOKEN if market == "US" else CRYPTO_TOKEN

    await telegram_send(session, token, message)


# -------------------- SAHMK — السوق السعودي --------------------

def extract_market_rows(data, possible_keys):
    if not isinstance(data, dict):
        return []

    for key in possible_keys:
        value = data.get(key)

        if isinstance(value, list):
            return value

    return []


async def scan_tasi(session):
    if not SAHMK_API_KEY:
        logging.warning("SAHMK_API_KEY missing")
        return

    headers = {"X-API-Key": SAHMK_API_KEY}

    gainers_data = await get_json(
        session,
        f"{SAHMK_BASE}/market/gainers/",
        params={"limit": 20, "index": "TASI"},
        headers=headers
    )

    volume_data = await get_json(
        session,
        f"{SAHMK_BASE}/market/volume/",
        params={"limit": 20, "index": "TASI"},
        headers=headers
    )

    gainers = extract_market_rows(
        gainers_data,
        ["gainers", "results", "data"]
    )

    volume_leaders = extract_market_rows(
        volume_data,
        ["volume", "leaders", "results", "data"]
    )

    # جمع الرموز من القائمتين
    selected = {}

    for item in gainers + volume_leaders:
        symbol = str(item.get("symbol", "")).strip()

        if not symbol:
            continue

        selected[symbol] = item

    for symbol, item in selected.items():
        price = number(item.get("price"))
        change = number(item.get("change_percent"))
        volume = number(item.get("volume"))
        name = item.get("name") or item.get("name_en") or symbol

        if price <= 0:
            continue

        # لا نرسل كل الأسهم؛ نركز على الارتفاع والنشاط
        if change < 2 and volume <= 0:
            continue

        if not signal_cooldown(f"TASI_{symbol}", "market_activity"):
            continue

        message = (
            f"🇸🇦 <b>AI PRO MAX — TASI HUNTER</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"📌 السهم: <b>{name}</b>\n"
            f"🔢 الرمز: {symbol}\n"
            f"💰 السعر: {price:.3f} ريال\n"
            f"📈 التغير: {change:+.2f}%\n"
            f"💹 حجم التداول: {volume:,.0f}\n"
            f"⭐ التصنيف: سهم نشط / ارتفاع ملحوظ\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"⚠️ بيانات النشاط لا تثبت وحدها دخول سيولة صافية.\n"
            f"⚠️ الأسعار قد تكون متأخرة حسب باقة SAHMK."
        )

        await telegram_send(session, TASI_TOKEN, message)


# -------------------- مراقبة الأسواق --------------------

async def scan_market(session, symbols, market):
    semaphore = asyncio.Semaphore(3)

    async def worker(symbol):
        async with semaphore:
            await analyze_td_symbol(session, symbol, market)

    await asyncio.gather(
        *(worker(symbol) for symbol in symbols),
        return_exceptions=True
    )


async def main():
    if not CHAT_ID:
        raise RuntimeError("CHAT_ID غير موجود في متغيرات البيئة")

    if not TWELVE_API_KEY:
        raise RuntimeError("TWELVE_DATA_API_KEY غير موجود")

    logging.info("AI PRO MAX MARKET HUNTER STARTED")

    last_tasi_scan = 0

    connector = aiohttp.TCPConnector(limit=10)

    async with aiohttp.ClientSession(
        connector=connector
    ) as session:

        while True:
            cycle_start = datetime.now().timestamp()

            try:
                # الأمريكي: يعمل الماسح طوال اليوم
                if US_SYMBOLS:
                    await scan_market(
                        session,
                        US_SYMBOLS,
                        "US"
                    )

                # الكريبتو: يعمل 24/7
                if CRYPTO_SYMBOLS:
                    await scan_market(
                        session,
                        CRYPTO_SYMBOLS,
                        "CRYPTO"
                    )

                # تاسي: فاصل مستقل لتقليل استهلاك API
                now = datetime.now().timestamp()

                if now - last_tasi_scan >= TASI_SCAN_SECONDS:
                    await scan_tasi(session)
                    last_tasi_scan = now

            except Exception:
                logging.exception("Main scan error")

            elapsed = datetime.now().timestamp() - cycle_start
            sleep_time = max(5, SCAN_SECONDS - elapsed)

            logging.info(
                "Scan complete. Next scan in %.0f seconds",
                sleep_time
            )

            await asyncio.sleep(sleep_time)


if __name__ == "__main__":
    asyncio.run(main())
