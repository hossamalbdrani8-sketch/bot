
import os
import json
import asyncio
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from html import escape

import aiohttp

# =========================================================
# AI PRO MAX V9.0 — SMART MONEY DASHBOARD
# US | TASI | CRYPTO | TP1-TP8 | AUTO TRACKING
# =========================================================

TD_KEY = os.getenv("TWELVE_DATA_API_KEY") or os.getenv("TWELVEDATA_API_KEY")
SAHMK_KEY = os.getenv("SAHMK_API_KEY")

US_TOKEN = os.getenv("US_TOKEN")
TASI_TOKEN = os.getenv("TASI_TOKEN")
CRYPTO_TOKEN = os.getenv("CRYPTO_TOKEN")

CHAT_ID = os.getenv("CHAT_ID")
US_CHAT_ID = os.getenv("US_CHAT_ID") or CHAT_ID
TASI_CHAT_ID = os.getenv("TASI_CHAT_ID") or CHAT_ID
CRYPTO_CHAT_ID = os.getenv("CRYPTO_CHAT_ID") or CHAT_ID

TD_BASE = "https://api.twelvedata.com"
SAHMK_BASE = "https://api.sahmk.sa/api/v1"

SCAN_SECONDS = int(os.getenv("SCAN_SECONDS", "300"))
TRACK_SECONDS = int(os.getenv("TRACK_SECONDS", "60"))

US_BATCH_SIZE = int(os.getenv("US_BATCH_SIZE", "20"))
CRYPTO_BATCH_SIZE = int(os.getenv("CRYPTO_BATCH_SIZE", "20"))

MIN_US_PRICE = 0.15
MAX_RESULTS = int(os.getenv("MAX_RESULTS", "15"))
MAX_TRACKED = int(os.getenv("MAX_TRACKED", "100"))

SIGNAL_COOLDOWN = 1800
STATE_FILE = "ai_pro_max_state.json"

TIMEZONE = ZoneInfo("Asia/Riyadh")

US_EXCHANGES = {
    "NASDAQ", "NYSE", "NYSE AMERICAN",
    "NYSEAMERICAN", "AMEX"
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

log = logging.getLogger("AI_PRO_MAX_V9")

universe = {"US": [], "CRYPTO": []}
positions = {"US": 0, "CRYPTO": 0}

sent = {}
signals = {}


# =========================================================
# GENERAL
# =========================================================

def now_time():
    return datetime.now(TIMEZONE)


def number(value, default=0.0):
    try:
        result = float(value)
        return result if result == result else default
    except (ValueError, TypeError):
        return default


def fmt(value):
    if value is None:
        return "N/A"
    return f"{value:,.4f}" if abs(value) < 1 else f"{value:,.2f}"


def chunks(items, size):
    for i in range(0, len(items), size):
        yield items[i:i + size]


def load_state():
    global signals, sent

    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        signals = data.get("signals", {})
        sent = data.get("sent", {})

        log.info("Saved signals restored: %s", len(signals))

    except FileNotFoundError:
        log.info("Starting with empty signal history")

    except Exception:
        log.exception("Could not load saved state")


def save_state():
    temp = STATE_FILE + ".tmp"

    try:
        with open(temp, "w", encoding="utf-8") as f:
            json.dump(
                {"signals": signals, "sent": sent},
                f,
                ensure_ascii=False,
                indent=2
            )

        os.replace(temp, STATE_FILE)

    except Exception:
        log.exception("State save failed")


def get_json_data_list(data):
    if not isinstance(data, dict):
        return []

    values = data.get("data", [])

    if isinstance(values, dict):
        values = (
            values.get("results")
            or values.get("items")
            or values.get("candles")
            or []
        )

    return values if isinstance(values, list) else []


# =========================================================
# API
# =========================================================

async def get_json(session, url, params=None, headers=None):
    try:
        async with session.get(
            url,
            params=params,
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=30)
        ) as response:

            data = await response.json(content_type=None)

            if response.status != 200:
                log.warning(
                    "HTTP %s: %s",
                    response.status,
                    str(data)[:200]
                )
                return None

            if isinstance(data, dict):
                if data.get("status") == "error":
                    log.warning("API: %s", str(data)[:200])
                    return None

                if data.get("code") == 429:
                    log.warning("API rate limit")
                    return None

            return data

    except Exception:
        log.exception("API connection error")
        return None


# =========================================================
# TELEGRAM
# =========================================================

async def telegram_send(session, token, chat_id, message):
    if not token or not chat_id:
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"

    try:
        async with session.post(
            url,
            json={
                "chat_id": chat_id,
                "text": message,
                "parse_mode": "HTML",
                "disable_web_page_preview": True
            },
            timeout=aiohttp.ClientTimeout(total=25)
        ) as response:

            result = await response.json(content_type=None)

            if response.status == 200 and result.get("ok"):
                return True

            log.error("Telegram error: %s", str(result)[:300])

    except Exception:
        log.exception("Telegram delivery error")

    return False


def bot_details(market):
    if market == "US":
        return US_TOKEN, US_CHAT_ID

    if market == "TASI":
        return TASI_TOKEN, TASI_CHAT_ID

    return CRYPTO_TOKEN, CRYPTO_CHAT_ID


async def send_market(session, market, message):
    token, chat = bot_details(market)
    return await telegram_send(session, token, chat, message)


async def startup(session):
    bots = [
        ("US", "🇺🇸 الماسح الأمريكي"),
        ("TASI", "🇸🇦 الماسح السعودي"),
        ("CRYPTO", "🪙 ماسح العملات الرقمية")
    ]

    for market, name in bots:
        token, chat = bot_details(market)

        if token and chat:
            await send_market(
                session,
                market,
                (
                    "💀🚀 <b>AI PRO MAX V9.0</b>\n"
                    "━━━━━━━━━━━━━━━━━━━━\n"
                    f"🟢 <b>{name}</b>\n"
                    "تم تشغيل النظام بنجاح\n"
                    "📡 الماسح الفني جاهز\n"
                    "🎯 متابعة الأهداف TP1-TP8\n"
                    "💾 حفظ واستعادة الإشارات\n"
                    f"🕒 <code>{now_time():%Y-%m-%d %H:%M:%S}</code>"
                )
            )


# =========================================================
# TECHNICAL INDICATORS
# =========================================================

def ema(values, period):
    if len(values) < period:
        return None

    result = sum(values[:period]) / period
    alpha = 2 / (period + 1)

    for value in values[period:]:
        result = value * alpha + result * (1 - alpha)

    return result


def calculate_vwap(rows):
    total_value = 0
    total_volume = 0

    for row in rows:
        volume = number(row.get("volume"))

        if volume <= 0:
            continue

        typical = (
            row["high"] + row["low"] + row["close"]
        ) / 3

        total_value += typical * volume
        total_volume += volume

    return total_value / total_volume if total_volume else None


def normalize_candles(data):
    if not isinstance(data, dict):
        return []

    values = data.get("values", [])

    if not isinstance(values, list):
        return []

    rows = []

    for item in reversed(values):
        close = number(item.get("close"))

        if close <= 0:
            continue

        rows.append({
            "open": number(item.get("open")),
            "high": number(item.get("high")),
            "low": number(item.get("low")),
            "close": close,
            "volume": number(item.get("volume"))
        })

    return rows


def analyze(rows):
    if len(rows) < 50:
        return None

    closes = [r["close"] for r in rows]
    price = closes[-1]
    previous = closes[-2]

    if price <= 0:
        return None

    averages = {
        10: ema(closes, 10),
        14: ema(closes, 14),
        25: ema(closes, 25),
        50: ema(closes, 50)
    }

    if any(v is None for v in averages.values()):
        return None

    volumes = [r["volume"] for r in rows]

    avg_volume = (
        sum(volumes[-21:-1]) / 20
        if len(volumes) >= 21 else 0
    )

    current_volume = volumes[-1]

    activity = (
        current_volume / avg_volume
        if avg_volume > 0 else 0
    )

    change = (
        (price - previous) / previous * 100
        if previous > 0 else 0
    )

    return {
        "price": price,
        "change": change,
        "volume": current_volume,
        "liquidity": price * current_volume,
        "activity": activity,
        "vwap": calculate_vwap(rows),
        "ema": averages,
        "rising": (
            averages[10] > averages[14] >
            averages[25] > averages[50]
        ),
        "high": max(r["high"] for r in rows[-20:]),
        "low": min(r["low"] for r in rows[-20:])
    }


# =========================================================
# SIGNAL TARGETS TP1 - TP8
# =========================================================

def create_signal(market, item, result, currency):
    entry = result["price"]

    recent_range = result["high"] - result["low"]

    risk = max(
        entry * 0.015,
        recent_range * 0.35
    )

    targets = [
        round(entry + risk * i, 8)
        for i in range(1, 9)
    ]

    stop = round(entry - risk, 8)

    return {
        "market": market,
        "symbol": item["symbol"],
        "name": item["name"],
        "currency": currency,
        "entry": entry,
        "price": entry,
        "change": result["change"],
        "volume": result["volume"],
        "liquidity": result["liquidity"],
        "activity": result["activity"],
        "vwap": result["vwap"],
        "ema": result["ema"],
        "rising": result["rising"],
        "high": result["high"],
        "low": result["low"],
        "stop": stop,
        "targets": targets,
        "hits": [False] * 8,
        "stop_hit": False,
        "created": now_time().isoformat(),
        "updated": now_time().isoformat()
    }


# =========================================================
# PROFESSIONAL DASHBOARD
# =========================================================

def build_message(signal):
    e = signal["ema"]

    change = signal["change"]
    activity = signal["activity"]
    vwap = signal["vwap"]

    market_names = {
        "US": "🇺🇸 السوق الأمريكي",
        "TASI": "🇸🇦 السوق السعودي",
        "CRYPTO": "🪙 العملات الرقمية"
    }

    direction = (
        "🟢 اتجاه صاعد"
        if signal["rising"]
        else "🟡 اتجاه غير مكتمل"
    )

    vwap_state = (
        "🟢 أعلى VWAP"
        if vwap is not None and signal["price"] > vwap
        else "🔴 أسفل VWAP"
        if vwap is not None
        else "⚪ غير متاح"
    )

    if activity >= 3:
        activity_state = "🔥 نشاط استثنائي"
    elif activity >= 2:
        activity_state = "🟢 نشاط مرتفع"
    elif activity >= 1:
        activity_state = "🟡 نشاط طبيعي"
    else:
        activity_state = "⚪ نشاط منخفض"

    bar = "🟩" * min(10, max(0, int(activity * 2)))
    bar += "⬛" * (10 - min(10, max(0, int(activity * 2))))

    ema_state = (
        "🟢 ترتيب EMA صاعد"
        if e[10] > e[14] > e[25] > e[50]
        else "🟡 ترتيب EMA غير مكتمل"
    )

    target_lines = []

    for i, target in enumerate(signal["targets"]):
        check = "✅" if signal["hits"][i] else "⬜"

        target_lines.append(
            f"{check} TP{i+1}: <b>{fmt(target)}</b>"
        )

    hit_count = sum(signal["hits"])

    return (
        "💀 <b>AI PRO MAX V9.0</b> 🚀\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "       <b>SMART MONEY DASHBOARD</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"

        f"🌍 <b>{market_names[signal['market']]}</b>\n"
        f"📌 <b>{escape(str(signal['symbol']))}</b>\n"
        f"🏢 {escape(str(signal['name']))}\n\n"

        "━━━━━━━━━━━━━━━━━━━━\n"
        "💰 <b>السعر والأداء</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"

        f"💵 الدخول: <b>{fmt(signal['entry'])} {signal['currency']}</b>\n"
        f"📍 السعر الحالي: <b>{fmt(signal['price'])}</b>\n"
        f"📈 التغير: <b>{change:+.2f}%</b>\n"
        f"📊 حجم التداول: <b>{signal['volume']:,.0f}</b>\n"
        f"💸 قيمة التداول: <b>{signal['liquidity']:,.2f}</b>\n\n"

        "━━━━━━━━━━━━━━━━━━━━\n"
        "⚡ <b>السيولة والنشاط</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"

        f"🔥 النشاط: <b>x{activity:.2f}</b>\n"
        f"{bar}\n"
        f"{activity_state}\n\n"

        "━━━━━━━━━━━━━━━━━━━━\n"
        "📡 <b>VWAP</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"

        f"القيمة: <b>{fmt(vwap)}</b>\n"
        f"{vwap_state}\n\n"

        "━━━━━━━━━━━━━━━━━━━━\n"
        "📈 <b>المتوسطات EMA</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"

        f"EMA 10: <b>{fmt(e[10])}</b>\n"
        f"EMA 14: <b>{fmt(e[14])}</b>\n"
        f"EMA 25: <b>{fmt(e[25])}</b>\n"
        f"EMA 50: <b>{fmt(e[50])}</b>\n"
        f"{ema_state}\n"
        f"{direction}\n\n"

        "━━━━━━━━━━━━━━━━━━━━\n"
        "🎯 <b>الأهداف السعرية</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"

        + "\n".join(target_lines) + "\n\n"

        "━━━━━━━━━━━━━━━━━━━━\n"
        "🛡 <b>إدارة المخاطر</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"

        f"🔴 وقف الخسارة: <b>{fmt(signal['stop'])}</b>\n"
        f"🔺 المقاومة: <b>{fmt(signal['high'])}</b>\n"
        f"🟢 الدعم: <b>{fmt(signal['low'])}</b>\n\n"

        f"🏆 الأهداف المحققة: <b>{hit_count}/8</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🤖 <b>AI PRO MAX AUTO TRACKER</b>\n"
        f"🕒 <code>{now_time():%Y-%m-%d %H:%M:%S}</code>\n"
        "⚠️ تحليل آلي وليس توصية استثمارية."
    )


# =========================================================
# SEND NEW SIGNAL
# =========================================================

async def publish_signal(session, market, item, result, currency):
    key = market + ":" + item["symbol"]

    now = now_time().timestamp()
    last_sent = number(sent.get(key, 0))

    if now - last_sent < SIGNAL_COOLDOWN:
        return

    if key in signals:
        old = signals[key]

        # Do not replace an active signal before it finishes
        if not old.get("stop_hit") and not all(old.get("hits", [])):
            return

    signal = create_signal(market, item, result, currency)

    signals[key] = signal
    sent[key] = now

    save_state()

    message = build_message(signal)

    if not await send_market(session, market, message):
        log.warning("Signal delivery failed: %s", key)


# =========================================================
# PRICE TRACKING
# =========================================================

async def get_td_price(session, symbol):
    data = await get_json(
        session,
        f"{TD_BASE}/price",
        params={
            "symbol": symbol,
            "apikey": TD_KEY
        }
    )

    if not isinstance(data, dict):
        return None

    price = number(data.get("price"))

    return price if price > 0 else None


async def get_saudi_price(session, symbol):
    today = now_time().date()

    data = await get_json(
        session,
        f"{SAHMK_BASE}/historical/{symbol}/",
        params={
            "interval": "5min",
            "from": today.isoformat(),
            "to": today.isoformat(),
            "limit": 5,
            "offset": 0
        },
        headers={"X-API-Key": SAHMK_KEY}
    )

    values = get_json_data_list(data)

    if not values:
        return None

    values.sort(
        key=lambda x: str(x.get("datetime", x.get("date", "")))
    )

    price = number(values[-1].get("close"))

    return price if price > 0 else None


async def fetch_signal_price(session, signal):
    market = signal["market"]
    symbol = signal["symbol"]

    if market in ("US", "CRYPTO"):
        return await get_td_price(session, symbol)

    if market == "TASI":
        return await get_saudi_price(session, symbol)

    return None


async def track_one_signal(session, key, signal):
    if signal.get("stop_hit"):
        return

    if all(signal.get("hits", [])):
        return

    price = await fetch_signal_price(session, signal)

    if price is None or price <= 0:
        return

    old_hits = list(signal["hits"])
    old_stop = signal.get("stop_hit", False)

    signal["price"] = price
    signal["updated"] = now_time().isoformat()

    for i, target in enumerate(signal["targets"]):
        if price >= target:
            signal["hits"][i] = True

    if price <= signal["stop"]:
        signal["stop_hit"] = True

    changed = (
        old_hits != signal["hits"]
        or old_stop != signal["stop_hit"]
    )

    if not changed:
        return

    save_state()

    hit_count = sum(signal["hits"])

    if signal["stop_hit"]:
        status = (
            "🔴 <b>تم الوصول إلى وقف الخسارة</b>\n"
            "تم إيقاف متابعة هذه الإشارة."
        )

    elif hit_count == 8:
        status = (
            "🏆 <b>اكتملت جميع الأهداف TP1-TP8</b>\n"
            "🎉 تم تحقيق الأهداف الثمانية."
        )

    else:
        status = (
            f"🎯 <b>تم تحقيق هدف جديد!</b>\n"
            f"🏆 الأهداف المحققة: {hit_count}/8"
        )

    message = (
        "🚨 <b>AI PRO MAX — تحديث الإشارة</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"📌 <b>{escape(str(signal['symbol']))}</b>\n"
        f"💰 السعر الحالي: <b>{fmt(price)}</b>\n"
        f"{status}\n\n"
        + build_message(signal)
    )

    await send_market(session, signal["market"], message)

    log.info(
        "Signal updated %s | price %s | hits %s",
        key, price, hit_count
    )


async def tracker_loop(session):
    semaphore = asyncio.Semaphore(3)

    while True:
        try:
            active = [
                (key, signal)
                for key, signal in list(signals.items())
                if not signal.get("stop_hit")
                and not all(signal.get("hits", []))
            ]

            async def worker(key, signal):
                async with semaphore:
                    try:
                        await track_one_signal(session, key, signal)
                    except Exception:
                        log.exception("Tracker failed: %s", key)

            await asyncio.gather(
                *(worker(key, signal) for key, signal in active)
            )

            await asyncio.sleep(TRACK_SECONDS)

        except Exception:
            log.exception("Tracker loop error")
            await asyncio.sleep(30)


# =========================================================
# US MARKET — DISCOVERY
# =========================================================

async def load_us_universe(session):
    data = await get_json(
        session,
        f"{TD_BASE}/stocks",
        params={
            "country": "United States",
            "format": "JSON",
            "apikey": TD_KEY
        }
    )

    items = data.get("data", []) if isinstance(data, dict) else data

    if not isinstance(items, list):
        return

    selected = {}

    for item in items:
        if not isinstance(item, dict):
            continue

        symbol = str(item.get("symbol", "")).strip().upper()
        exchange = str(item.get("exchange", "")).strip().upper()
        name = str(item.get("name", symbol))

        if not symbol or exchange not in US_EXCHANGES:
            continue

        if item.get("country") not in (None, "", "United States"):
            continue

        if item.get("type") and item["type"] not in (
            "Common Stock", "American Depositary Receipt"
        ):
            continue

        selected[symbol] = {
            "symbol": symbol,
            "name": name
        }

    universe["US"] = list(selected.values())

    log.info("US symbols loaded: %s", len(universe["US"]))


async def scan_us_symbol(session, item):
    data = await get_json(
        session,
        f"{TD_BASE}/time_series",
        params={
            "symbol": item["symbol"],
            "interval": "5min",
            "outputsize": 100,
            "prepost": "true",
            "apikey": TD_KEY
        }
    )

    rows = normalize_candles(data)

    result = analyze(rows)

    if not result or result["price"] < MIN_US_PRICE:
        return None

    return {
        "symbol": item["symbol"],
        "name": item["name"],
        "result": result
    }


async def us_loop(session):
    if not US_TOKEN or not US_CHAT_ID or not TD_KEY:
        log.error("US settings incomplete")
        return

    await load_us_universe(session)

    while not universe["US"]:
        await asyncio.sleep(60)
        await load_us_universe(session)

    while True:
        try:
            items = universe["US"]

            start = positions["US"]

            batch = items[start:start + US_BATCH_SIZE]

            if len(batch) < US_BATCH_SIZE:
                batch += items[:US_BATCH_SIZE - len(batch)]

            positions["US"] = (
                start + US_BATCH_SIZE
            ) % len(items)

            semaphore = asyncio.Semaphore(3)

            async def worker(item):
                async with semaphore:
                    try:
                        return await scan_us_symbol(session, item)
                    except Exception:
                        log.exception(
                            "US scan failed: %s",
                            item["symbol"]
                        )
                        return None

            results = await asyncio.gather(
                *(worker(item) for item in batch)
            )

            results = [x for x in results if x]

            results.sort(
                key=lambda x: x["result"]["change"],
                reverse=True
            )

            for item in results[:MAX_RESULTS]:
                await publish_signal(
                    session, "US", item["symbol"] and {
                        "symbol": item["symbol"],
                        "name": item["name"]
                    },
                    item["result"], "USD"
                )

            log.info(
                "US scanned %s | signals %s",
                len(batch), len(results)
            )

            await asyncio.sleep(SCAN_SECONDS)

        except Exception:
            log.exception("US loop error")
            await asyncio.sleep(60)


# =========================================================
# CRYPTO MARKET — 24/7
# =========================================================

async def load_crypto_universe(session):
    data = await get_json(
        session,
        f"{TD_BASE}/cryptocurrencies",
        params={"apikey": TD_KEY}
    )

    items = data.get("data", []) if isinstance(data, dict) else data

    if not isinstance(items, list):
        return

    selected = {}

    for item in items:
        if not isinstance(item, dict):
            continue

        symbol = str(item.get("symbol", "")).strip().upper()

        if "/" not in symbol:
            continue

        base, quote = symbol.split("/", 1)

        if quote not in ("USD", "USDT") or not base:
            continue

        selected[symbol] = {
            "symbol": symbol,
            "name": item.get("currency_base", base)
        }

    universe["CRYPTO"] = list(selected.values())

    log.info("Crypto pairs loaded: %s", len(universe["CRYPTO"]))


async def scan_crypto_symbol(session, item):
    data = await get_json(
        session,
        f"{TD_BASE}/time_series",
        params={
            "symbol": item["symbol"],
            "interval": "5min",
            "outputsize": 100,
            "apikey": TD_KEY
        }
    )

    rows = normalize_candles(data)
    result = analyze(rows)

    if not result:
        return None

    return {
        "symbol": item["symbol"],
        "name": item["name"],
        "result": result
    }


async def crypto_loop(session):
    if not CRYPTO_TOKEN or not CRYPTO_CHAT_ID or not TD_KEY:
        log.error("Crypto settings incomplete")
        return

    await load_crypto_universe(session)

    while not universe["CRYPTO"]:
        await asyncio.sleep(60)
        await load_crypto_universe(session)

    while True:
        try:
            items = universe["CRYPTO"]

            start = positions["CRYPTO"]

            batch = items[start:start + CRYPTO_BATCH_SIZE]

            if len(batch) < CRYPTO_BATCH_SIZE:
                batch += items[:CRYPTO_BATCH_SIZE - len(batch)]

            positions["CRYPTO"] = (
                start + CRYPTO_BATCH_SIZE
            ) % len(items)

            semaphore = asyncio.Semaphore(3)

            async def worker(item):
                async with semaphore:
                    try:
                        return await scan_crypto_symbol(session, item)
                    except Exception:
                        log.exception(
                            "Crypto scan failed: %s",
                            item["symbol"]
                        )
                        return None

            results = await asyncio.gather(
                *(worker(item) for item in batch)
            )

            results = [x for x in results if x]

            results.sort(
                key=lambda x: x["result"]["change"],
                reverse=True
            )

            for item in results[:MAX_RESULTS]:
                await publish_signal(
                    session,
                    "CRYPTO",
                    {
                        "symbol": item["symbol"],
                        "name": item["name"]
                    },
                    item["result"],
                    "USD"
                )

            log.info(
                "CRYPTO scanned %s | signals %s",
                len(batch), len(results)
            )

            await asyncio.sleep(SCAN_SECONDS)

        except Exception:
            log.exception("Crypto loop error")
            await asyncio.sleep(60)


# =========================================================
# SAUDI MARKET — SAHMK
# =========================================================

def saudi_market_active():
    now = now_time()

    if now.weekday() not in (6, 0, 1, 2, 3):
        return False

    return (
        now.hour > 10 or (now.hour == 10 and now.minute >= 0)
    ) and (
        now.hour < 15
    )


async def sahmk_get(session, endpoint, params=None):
    return await get_json(
        session,
        f"{SAHMK_BASE}/{endpoint}/",
        params=params or {},
        headers={"X-API-Key": SAHMK_KEY}
    )


async def scan_saudi_symbol(session, item):
    symbol = str(item.get("symbol", "")).strip()

    if not symbol:
        return None

    today = now_time().date()
    start = today - timedelta(days=180)

    data = await sahmk_get(
        session,
        f"historical/{symbol}",
        {
            "interval": "5min",
            "from": start.isoformat(),
            "to": today.isoformat(),
            "limit": 500,
            "offset": 0
        }
    )

    values = get_json_data_list(data)

    rows = []

    for x in values:
        rows.append({
            "open": number(x.get("open")),
            "high": number(x.get("high")),
            "low": number(x.get("low")),
            "close": number(x.get("close")),
            "volume": number(x.get("volume"))
        })

    result = analyze(rows)

    if not result:
        return None

    return {
        "symbol": symbol,
        "name": item.get("name", symbol),
        "result": result
    }


async def saudi_loop(session):
    if not TASI_TOKEN or not TASI_CHAT_ID or not SAHMK_KEY:
        log.error("TASI settings incomplete")
        return

    while True:
        try:
            if not saudi_market_active():
                await asyncio.sleep(60)
                continue

            gainers, volume, value = await asyncio.gather(
                sahmk_get(
                    session, "market/gainers",
                    {"limit": 50, "index": "TASI"}
                ),
                sahmk_get(
                    session, "market/volume",
                    {"limit": 50, "index": "TASI"}
                ),
                sahmk_get(
                    session, "market/value",
                    {"limit": 50, "index": "TASI"}
                )
            )

            selected = {}

            for data, key_name in (
                (gainers, "gainers"),
                (volume, "volume"),
                (value, "value")
            ):
                if not isinstance(data, dict):
                    continue

                values = data.get(
                    key_name,
                    data.get("data", [])
                )

                if isinstance(values, dict):
                    values = values.get("results", [])

                if not isinstance(values, list):
                    continue

                for item in values:
                    if isinstance(item, dict):
                        symbol = str(
                            item.get("symbol", "")
                        ).strip()

                        if symbol:
                            selected[symbol] = item

            semaphore = asyncio.Semaphore(3)

            async def worker(item):
                async with semaphore:
                    try:
                        return await scan_saudi_symbol(
                            session, item
                        )
                    except Exception:
                        log.exception(
                            "Saudi scan failed: %s",
                            item.get("symbol")
                        )
                        return None

            results = await asyncio.gather(
                *(worker(item) for item in selected.values())
            )

            results = [x for x in results if x]

            results.sort(
                key=lambda x: x["result"]["change"],
                reverse=True
            )

            for item in results[:MAX_RESULTS]:
                await publish_signal(
                    session,
                    "TASI",
                    {
                        "symbol": item["symbol"],
                        "name": item["name"]
                    },
                    item["result"],
                    "SAR"
                )

            log.info(
                "TASI scanned %s | results %s",
                len(selected), len(results)
            )

            await asyncio.sleep(SCAN_SECONDS)

        except Exception:
            log.exception("TASI loop error")
            await asyncio.sleep(60)


# =========================================================
# MAIN — INDEPENDENT WORKERS
# =========================================================

async def main():
    load_state()

    connector = aiohttp.TCPConnector(
        limit=20,
        ttl_dns_cache=300
    )

    timeout = aiohttp.ClientTimeout(total=40)

    async with aiohttp.ClientSession(
        connector=connector,
        timeout=timeout
    ) as session:

        await startup(session)

        tasks = [
            asyncio.create_task(us_loop(session)),
            asyncio.create_task(saudi_loop(session)),
            asyncio.create_task(crypto_loop(session)),
            asyncio.create_task(tracker_loop(session))
        ]

        log.info(
            "AI PRO MAX V9.0 — ALL SYSTEMS STARTED"
        )

        await asyncio.gather(*tasks)


if __name__ == "__main__":
    try:
        asyncio.run(main())

    except KeyboardInterrupt:
        save_state()
        log.warning("AI PRO MAX stopped manually")

    except Exception:
        save_state()
        log.exception("Fatal system error")
