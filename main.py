
import os
import io
import asyncio
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

import aiohttp
from PIL import Image, ImageDraw, ImageFont
import arabic_reshaper
from bidi.algorithm import get_display

# ==================================================
# AI PRO MAX V7.0 — MARKET HUNTER
# ==================================================

TD_KEY = os.getenv("TWELVE_DATA_API_KEY") or os.getenv("TWELVEDATA_API_KEY")
SAHMK_KEY = os.getenv("SAHMK_API_KEY")
SAHMK_BASE = os.getenv("SAHMK_BASE", "https://api.sahmk.sa/api/v1").rstrip("/")

CHAT_ID = os.getenv("CHAT_ID")
US_TOKEN = os.getenv("US_TOKEN")
CRYPTO_TOKEN = os.getenv("CRYPTO_TOKEN")
TASI_TOKEN = os.getenv("TASI_TOKEN") or US_TOKEN

SCAN_SECONDS = 60
MIN_US_PRICE = 0.15
COOLDOWN = 1800
MAX_WORKERS = 3
TD_BASE = "https://api.twelvedata.com"

US_SYMBOLS = [
    x.strip().upper()
    for x in os.getenv("US_SYMBOLS", "AAPL,TSLA,NVDA,AMD,PLTR").split(",")
    if x.strip()
]
CRYPTO_SYMBOLS = [
    x.strip().upper()
    for x in os.getenv(
        "CRYPTO_SYMBOLS", "BTC/USD,ETH/USD,SOL/USD,XRP/USD"
    ).split(",")
    if x.strip()
]

TZ = ZoneInfo("Asia/Riyadh")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)
log = logging.getLogger("AI_PRO_MAX")

sent_alerts = {}
active_signals = {}


# ==================================================
# HELPERS
# ==================================================

def num(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def fmt(value):
    if value is None:
        return "—"
    return f"{value:,.4f}" if abs(value) < 1 else f"{value:,.2f}"


def rtl(value):
    try:
        return get_display(arabic_reshaper.reshape(str(value)))
    except Exception:
        return str(value)


def font(size, bold=False):
    paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
        if bold else
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    ]
    for path in paths:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            pass
    return ImageFont.load_default()


def normalize(rows):
    result = []
    for r in rows or []:
        if not isinstance(r, dict):
            continue

        low = {str(k).lower(): v for k, v in r.items()}

        close = num(low.get("close", low.get("price", low.get("last"))))
        if close <= 0:
            continue

        op = num(low.get("open"), close)
        high = num(low.get("high"), max(op, close))
        low_price = num(low.get("low"), min(op, close))
        volume = num(
            low.get("volume", low.get("vol", low.get("v")))
        )

        result.append({
            "open": op,
            "high": high,
            "low": low_price,
            "close": close,
            "volume": volume,
            "datetime": str(low.get("datetime", ""))
        })

    return result


def ema(values, period):
    if len(values) < period:
        return None

    result = sum(values[:period]) / period
    alpha = 2 / (period + 1)

    for value in values[period:]:
        result = value * alpha + result * (1 - alpha)

    return result


# ==================================================
# MARKET ANALYSIS
# ==================================================

def analyze(rows):
    if len(rows) < 55:
        return None

    closes = [r["close"] for r in rows]
    price = closes[-1]

    e10 = ema(closes, 10)
    e14 = ema(closes, 14)
    e25 = ema(closes, 25)
    e50 = ema(closes, 50)

    # VWAP لليوم الحالي فقط
    today = rows[-1]["datetime"][:10]
    today_rows = [
        r for r in rows
        if r["datetime"][:10] == today and r["volume"] > 0
    ]

    total_value = 0.0
    total_volume = 0.0

    for r in today_rows:
        typical = (r["high"] + r["low"] + r["close"]) / 3
        total_value += typical * r["volume"]
        total_volume += r["volume"]

    vwap = total_value / total_volume if total_volume else None

    # الحجم الفعلي والنشاط
    last_volume = rows[-1]["volume"]
    previous_volumes = [r["volume"] for r in rows[-21:-1]]
    average_volume = (
        sum(previous_volumes) / len(previous_volumes)
        if previous_volumes else 0
    )

    volume_ratio = (
        last_volume / average_volume
        if average_volume > 0 else 0
    )

    liquidity = price * last_volume

    # اتجاه المتوسطات
    ema_bullish = (
        e10 > e14 > e25 > e50
    )

    above_vwap = vwap is not None and price > vwap

    bullish = ema_bullish and above_vwap

    high_volume = volume_ratio >= 1.2

    # لا نستخدم نقاط 65 ولا شروط RSI
    # الإشارة عند الاتجاه الصاعد أو ارتفاع الحجم
    signal = bullish or high_volume

    support = min(r["low"] for r in rows[-30:])
    resistance = max(r["high"] for r in rows[-30:])

    return {
        "price": price,
        "ema10": e10,
        "ema14": e14,
        "ema25": e25,
        "ema50": e50,
        "vwap": vwap,
        "volume": last_volume,
        "average_volume": average_volume,
        "volume_ratio": volume_ratio,
        "liquidity": liquidity,
        "bullish": bullish,
        "high_volume": high_volume,
        "signal": signal,
        "support": support,
        "resistance": resistance
    }


# ==================================================
# API
# ==================================================

async def get_json(session, url, params=None, headers=None):
    try:
        async with session.get(
            url,
            params=params,
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=25)
        ) as response:
            data = await response.json(content_type=None)

            if response.status != 200:
                log.error("API HTTP %s: %s", response.status, str(data)[:300])
                return None

            if isinstance(data, dict) and (
                data.get("status") == "error"
                or data.get("code") == 400
                or data.get("message") and not data.get("values")
            ):
                log.error("API returned error: %s", str(data)[:300])
                return None

            return data

    except Exception:
        log.exception("API connection error")
        return None


async def get_candles(session, symbol, market):
    params = {
        "symbol": symbol,
        "interval": "1min",
        "outputsize": 500,
        "apikey": TD_KEY,
        "order": "asc"
    }

    # بيانات ما قبل وبعد التداول الأمريكي
    if market == "US":
        params["prepost"] = "true"

    data = await get_json(
        session,
        f"{TD_BASE}/time_series",
        params
    )

    if not isinstance(data, dict):
        return []

    return normalize(data.get("values", []))


# ==================================================
# MARKET MOVERS
# ==================================================

async def get_movers(session, market):
    params = {
        "direction": "gainers",
        "outputsize": 50,
        "apikey": TD_KEY
    }

    if market == "US":
        params["country"] = "USA"
        params["price_greater_than"] = "0.1499"

    data = await get_json(
        session,
        f"{TD_BASE}/market_movers/{'stocks' if market == 'US' else 'crypto'}",
        params
    )

    if not isinstance(data, dict):
        return []

    values = data.get("values", [])

    filtered = []

    for item in values:
        symbol = str(item.get("symbol", "")).upper()
        exchange = str(item.get("exchange", "")).upper()
        price = num(item.get("last"))

        if not symbol:
            continue

        if market == "US":
            if price < MIN_US_PRICE:
                continue

            if any(x in exchange for x in (
                "OTC", "PINK", "GREY", "OTCQB", "OTCQX"
            )):
                continue

        filtered.append(item)

    return filtered


# ==================================================
# SAHMK
# ==================================================

async def get_tasi_movers(session):
    if not SAHMK_KEY:
        return []

    headers = {"X-API-Key": SAHMK_KEY}

    results = {}

    for endpoint in ("gainers", "volume"):
        data = await get_json(
            session,
            f"{SAHMK_BASE}/market/{endpoint}/",
            {"limit": 50, "market": "TASI"},
            headers
        )

        if not isinstance(data, dict):
            continue

        items = data.get("data", data.get("results", []))

        if isinstance(items, dict):
            items = (
                items.get("results")
                or items.get("items")
                or items.get("candles")
                or []
            )

        for item in items or []:
            if isinstance(item, dict):
                symbol = str(
                    item.get("symbol") or item.get("ticker") or ""
                ).strip()

                if symbol:
                    results[symbol] = item

    return list(results.values())


async def get_tasi_candles(session, symbol):
    if not SAHMK_KEY:
        return []

    headers = {"X-API-Key": SAHMK_KEY}

    data = await get_json(
        session,
        f"{SAHMK_BASE}/historical/{symbol}/",
        {
            "interval": "1min",
            "limit": 500,
            "offset": 0
        },
        headers
    )

    if not isinstance(data, dict):
        return []

    rows = data.get("data", [])

    if isinstance(rows, dict):
        rows = (
            rows.get("results")
            or rows.get("items")
            or rows.get("candles")
            or []
        )

    return normalize(rows)


# ==================================================
# DASHBOARD
# ==================================================

def make_dashboard(market, symbol, m, entry, stop, targets):
    W, H = 1400, 1740

    img = Image.new("RGB", (W, H), (8, 14, 23))
    d = ImageDraw.Draw(img)

    green = (0, 235, 145)
    red = (255, 75, 90)
    gold = (255, 195, 65)
    white = (240, 245, 250)
    muted = (150, 170, 185)
    panel = (18, 31, 43)

    title = font(52, True)
    head = font(37, True)
    body = font(30, True)
    small = font(24)

    def box(y1, y2):
        d.rounded_rectangle(
            (30, y1, W - 30, y2),
            radius=24,
            fill=panel,
            outline=(35, 75, 90),
            width=3
        )

    def right(y, text, f=body, color=white):
        d.text((W-65, y), rtl(text), font=f, fill=color, anchor="ra")

    box(25, 165)
    d.text((65, 55), "AI PRO MAX V7.0", font=title, fill=green)
    right(110, "MARKET HUNTER", head)

    box(190, 390)
    right(220, f"{market} | {symbol}", head, gold)
    d.text((65, 295), fmt(m["price"]), font=title, fill=green)

    trend = "صاعد 🚀" if m["bullish"] else "ارتفاع حجم التداول" if m["high_volume"] else "مراقبة"
    right(340, f"الاتجاه: {trend}", body, green)

    box(415, 900)
    right(445, "المؤشرات الفنية", head, gold)

    values = [
        ("EMA 10", fmt(m["ema10"])),
        ("EMA 14", fmt(m["ema14"])),
        ("EMA 25", fmt(m["ema25"])),
        ("EMA 50", fmt(m["ema50"])),
        ("VWAP", fmt(m["vwap"])),
        ("الحجم الفعلي", f'{m["volume"]:,.0f}'),
        ("متوسط الحجم", f'{m["average_volume"]:,.0f}'),
        ("نشاط الحجم", f'x{m["volume_ratio"]:.2f}'),
        ("السيولة", f'{m["liquidity"]:,.2f}'),
    ]

    for i, (label, value) in enumerate(values):
        y = 515 + i * 40
        right(y, f"{label}: {value}", body, white)

    box(925, 1110)
    right(955, "الدعم والمقاومة", head, gold)
    right(1020, f"المقاومة: {fmt(m['resistance'])}", body, red)
    right(1070, f"الدعم: {fmt(m['support'])}", body, green)

    box(1135, 1600)
    right(1165, "الدخول والأهداف", head, gold)
    right(1225, f"الدخول: {fmt(entry)}", body, green)
    right(1270, f"وقف الخسارة 2%: {fmt(stop)}", body, red)

    for i, target in enumerate(targets):
        col = i % 2
        row = i // 2
        x = 75 if col == 0 else 735
        y = 1330 + row * 62

        d.rounded_rectangle(
            (x, y, x+580, y+50),
            radius=12,
            fill=(10, 43, 35),
            outline=(0, 120, 80),
            width=2
        )

        d.text(
            (x+20, y+7),
            f"TP{i+1}",
            font=small,
            fill=green
        )

        d.text(
            (x+550, y+7),
            fmt(target),
            font=small,
            fill=white,
            anchor="ra"
        )

    right(1650, datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S الرياض"), small, muted)

    output = io.BytesIO()
    img.save(output, format="PNG", optimize=True)
    output.seek(0)
    return output


# ==================================================
# TELEGRAM
# ==================================================

async def send_text(session, token, message):
    if not token or not CHAT_ID:
        return False

    try:
        async with session.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={
                "chat_id": CHAT_ID,
                "text": message,
                "parse_mode": "HTML"
            }
        ) as response:
            data = await response.json(content_type=None)
            if not data.get("ok"):
                log.error("Telegram text error: %s", data)
            return bool(data.get("ok"))

    except Exception:
        log.exception("Telegram text failed")
        return False


async def send_photo(session, token, photo, caption):
    if not token or not CHAT_ID:
        return False

    form = aiohttp.FormData()
    form.add_field("chat_id", str(CHAT_ID))
    form.add_field("caption", caption[:1000])
    form.add_field(
        "photo",
        photo.getvalue(),
        filename="AI_PRO_MAX_V7.png",
        content_type="image/png"
    )

    try:
        async with session.post(
            f"https://api.telegram.org/bot{token}/sendPhoto",
            data=form
        ) as response:
            data = await response.json(content_type=None)

            if not data.get("ok"):
                log.error("Telegram photo error: %s", data)

            return bool(data.get("ok"))

    except Exception:
        log.exception("Telegram photo failed")
        return False


# ==================================================
# TARGET FOLLOW-UP
# ==================================================

async def update_targets(session, token, key, price):
    signal = active_signals.get(key)
    if not signal:
        return

    for i, target in enumerate(signal["targets"]):
        if not signal["hit"][i] and price >= target:
            signal["hit"][i] = True

            await send_text(
                session,
                token,
                f"💀🚀 <b>تحقق الهدف TP{i+1}</b>\n"
                f"السهم: {signal['symbol']}\n"
                f"السعر الحالي: {fmt(price)}\n"
                f"الهدف: {fmt(target)}\n"
                "✅ تم تحقيق الهدف"
            )

    if not signal["stopped"] and price <= signal["stop"]:
        signal["stopped"] = True
        await send_text(
            session,
            token,
            f"🛑 <b>وصل السعر إلى وقف الخسارة</b>\n"
            f"{signal['symbol']}\n"
            f"السعر: {fmt(price)}"
        )


# ==================================================
# PROCESS STOCK
# ==================================================

async def process_symbol(session, market, symbol, token):
    try:
        if market == "TASI":
            rows = await get_tasi_candles(session, symbol)
        else:
            rows = await get_candles(session, symbol, market)

        if len(rows) < 55:
            log.info("%s %s: candles not enough (%s)", market, symbol, len(rows))
            return False

        m = analyze(rows)
        if not m:
            return False

        price = m["price"]

        if market == "US" and price < MIN_US_PRICE:
            return False

        key = f"{market}:{symbol}"

        # تحديث الأهداف حتى لو لم تظهر إشارة جديدة
        await update_targets(session, token, key, price)

        if not m["signal"]:
            return False

        now = datetime.now().timestamp()

        if now - sent_alerts.get(key, 0) < COOLDOWN:
            return False

        entry = price
        stop = entry * 0.98
        targets = [entry * (1 + 0.02 * i) for i in range(1, 9)]

        active_signals[key] = {
            "symbol": symbol,
            "entry": entry,
            "stop": stop,
            "targets": targets,
            "hit": [False] * 8,
            "stopped": False
        }

        dashboard = make_dashboard(
            market, symbol, m, entry, stop, targets
        )

        caption = (
            f"💀🚀 <b>AI PRO MAX V7.0</b>\n"
            f"📌 السهم: {symbol}\n"
            f"💰 الدخول: {fmt(entry)}\n"
            f"📊 الحجم: {m['volume']:,.0f}\n"
            f"💧 السيولة: {m['liquidity']:,.2f}\n"
            f"🔥 النشاط: x{m['volume_ratio']:.2f}\n"
            f"📈 الاتجاه: {'صاعد' if m['bullish'] else 'ارتفاع حجم'}\n"
            f"🛑 الوقف: {fmt(stop)}\n"
            "🎯 الأهداف TP1–TP8 داخل الصورة"
        )

        sent = await send_photo(session, token, dashboard, caption)

        if sent:
            sent_alerts[key] = now
            log.info("SIGNAL SENT %s %s", market, symbol)
            return True

        return False

    except Exception:
        log.exception("PROCESS ERROR %s %s", market, symbol)
        return False


# ==================================================
# SCANNER
# ==================================================

async def scan_market(session, market):
    if market == "TASI":
        items = await get_tasi_movers(session)
        token = TASI_TOKEN

    else:
        items = await get_movers(session, market)
        token = US_TOKEN if market == "US" else CRYPTO_TOKEN

    # العملات: قائمة الرموز المحددة إذا لم ترجع قائمة السوق
    if market == "CRYPTO" and not items:
        items = [{"symbol": s} for s in CRYPTO_SYMBOLS]

    if market == "US" and not items:
        items = [{"symbol": s} for s in US_SYMBOLS]

    # ترتيب الأكثر ارتفاعاً
    items.sort(
        key=lambda x: num(x.get("percent_change")),
        reverse=True
    )

    log.info("%s candidates: %s", market, len(items))

    semaphore = asyncio.Semaphore(MAX_WORKERS)
    sent_count = 0

    async def worker(item):
        nonlocal sent_count

        symbol = str(item.get("symbol", "")).strip().upper()
        if not symbol:
            return

        async with semaphore:
            sent = await process_symbol(
                session, market, symbol, token
            )
            if sent:
                sent_count += 1

    await asyncio.gather(*(worker(x) for x in items))

    log.info(
        "%s scan complete | candidates=%s | signals=%s",
        market, len(items), sent_count
    )

    return len(items), sent_count


# ==================================================
# MAIN 24/7
# ==================================================

async def main():
    if not CHAT_ID:
        raise RuntimeError("CHAT_ID missing")

    if not TD_KEY:
        raise RuntimeError("Twelve Data API key missing")

    if not US_TOKEN or not CRYPTO_TOKEN:
        raise RuntimeError("US_TOKEN or CRYPTO_TOKEN missing")

    connector = aiohttp.TCPConnector(limit=20, ttl_dns_cache=300)

    async with aiohttp.ClientSession(
        connector=connector,
        timeout=aiohttp.ClientTimeout(total=40)
    ) as session:

        await send_text(
            session,
            US_TOKEN,
            "💀🚀 <b>AI PRO MAX V7.0</b>\n"
            "🟢 بدأ تشغيل الماسح\n"
            "📊 EMA 10 | 14 | 25 | 50\n"
            "💧 VWAP | VOLUME\n"
            "📈 الاتجاه الصاعد\n"
            "🇺🇸 US | 🪙 CRYPTO | 🇸🇦 TASI\n"
            "🎯 TP1–TP8 | 🛑 SL 2%\n"
            "⏰ تشغيل مستمر 24/7"
        )

        last_tasi = 0
        last_report = 0

        while True:
            started = datetime.now().timestamp()

            try:
                us_result, crypto_result = await asyncio.gather(
                    scan_market(session, "US"),
                    scan_market(session, "CRYPTO")
                )

                now = datetime.now().timestamp()

                # فحص تاسي كل دقيقة
                if SAHMK_KEY and now - last_tasi >= 60:
                    tasi_result = await scan_market(session, "TASI")
                    last_tasi = now
                else:
                    tasi_result = (0, 0)

                # تقرير تشخيصي كل نصف ساعة
                if now - last_report >= 1800:
                    await send_text(
                        session,
                        US_TOKEN,
                        "📡 <b>تقرير الماسح V7.0</b>\n"
                        f"🇺🇸 الأمريكي: {us_result[0]} سهم تم جلبه\n"
                        f"🪙 العملات: {crypto_result[0]} رمز\n"
                        f"🇸🇦 السعودي: {tasi_result[0]} سهم\n"
                        "📊 تم تسجيل نتائج الفحص في سجل Railway."
                    )
                    last_report = now

            except Exception:
                log.exception("MAIN SCAN ERROR")

            elapsed = datetime.now().timestamp() - started
            await asyncio.sleep(max(10, SCAN_SECONDS - elapsed))


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.warning("Worker stopped")
