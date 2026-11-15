
import os
import io
import json
import asyncio
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import aiohttp
from PIL import Image, ImageDraw, ImageFont
import arabic_reshaper
from bidi.algorithm import get_display

# =====================================================
# AI PRO MAX — MARKET HUNTER V6.0
# US | CRYPTO | TASI | TELEGRAM
# =====================================================

TD_KEY = os.getenv("TWELVE_DATA_API_KEY") or os.getenv("TWELVEDATA_API_KEY")
SAHMK_KEY = os.getenv("SAHMK_API_KEY")
SAHMK_BASE = os.getenv("SAHMK_BASE", "https://api.sahmk.sa/api/v1").rstrip("/")

CHAT_ID = os.getenv("CHAT_ID")
US_TOKEN = os.getenv("US_TOKEN")
CRYPTO_TOKEN = os.getenv("CRYPTO_TOKEN")
TASI_TOKEN = os.getenv("TASI_TOKEN") or US_TOKEN

TD_BASE = "https://api.twelvedata.com"

SCAN_SECONDS = int(os.getenv("SCAN_SECONDS", "60"))
TASI_SCAN_SECONDS = int(os.getenv("TASI_SCAN_SECONDS", "60"))
MIN_US_PRICE = 0.15
CANDIDATES = 50
MAX_WORKERS = 3
COOLDOWN = 1800

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)
log = logging.getLogger("AI_PRO_MAX")

riyadh = ZoneInfo("Asia/Riyadh")

# ذاكرة الأهداف والإشارات
active_signals = {}
sent_alerts = {}
float_cache = {}

TIMEFRAMES = [
    ("1 دقيقة", 1),
    ("3 دقائق", 3),
    ("5 دقائق", 5),
    ("15 دقيقة", 15),
    ("1 ساعة", 60),
    ("2 ساعة", 120),
    ("4 ساعات", 240),
    ("24 ساعة", 1440),
    ("يومي", 1440),
]


# =====================================================
# HELPERS
# =====================================================

def number(v, default=0.0):
    try:
        x = float(v)
        return x if x == x else default
    except (TypeError, ValueError):
        return default


def fmt(v):
    if v is None:
        return "غير متاح"
    return f"{v:,.4f}" if abs(v) < 1 else f"{v:,.2f}"


def rtl(s):
    try:
        return get_display(arabic_reshaper.reshape(str(s)))
    except Exception:
        return str(s)


def get_font(size, bold=False):
    paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
        if bold else
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf"
    ]
    for path in paths:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            pass
    return ImageFont.load_default()


def normalize(rows):
    result = []
    if not isinstance(rows, list):
        return result

    for r in rows:
        if not isinstance(r, dict):
            continue
        close = number(r.get("close"))
        if close <= 0:
            continue

        op = number(r.get("open"), close)
        high = number(r.get("high"), max(op, close))
        low = number(r.get("low"), min(op, close))
        volume = number(r.get("volume"))

        result.append({
            "open": op,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
            "datetime": r.get("datetime", "")
        })

    return result


def aggregate(rows, minutes):
    if minutes <= 1:
        return rows[:]

    output = []
    group = []

    for row in rows:
        group.append(row)
        if len(group) == minutes:
            output.append({
                "open": group[0]["open"],
                "high": max(x["high"] for x in group),
                "low": min(x["low"] for x in group),
                "close": group[-1]["close"],
                "volume": sum(x["volume"] for x in group),
                "datetime": group[-1]["datetime"]
            })
            group = []

    return output


def metrics(rows):
    if len(rows) < 3:
        return None

    last = rows[-1]
    previous = rows[-2]
    price = last["close"]

    volumes = [x["volume"] for x in rows[-21:-1]]
    avg_volume = sum(volumes) / len(volumes) if volumes else 0

    volume_ratio = (
        last["volume"] / avg_volume if avg_volume > 0 else 0
    )

    dollar_volume = price * last["volume"]
    change = (
        (price - previous["close"]) / previous["close"] * 100
        if previous["close"] else 0
    )

    highs = [x["high"] for x in rows[-50:-1]]
    lows = [x["low"] for x in rows[-50:-1]]

    resistance = max(highs) if highs else None
    support = min(lows) if lows else None

    strong_inflow = (
        volume_ratio >= 1.2
        and price > previous["close"]
        and last["close"] >= last["open"]
    )

    return {
        "price": price,
        "volume": last["volume"],
        "average_volume": avg_volume,
        "volume_ratio": volume_ratio,
        "liquidity": dollar_volume,
        "change": change,
        "support": support,
        "resistance": resistance,
        "inflow": strong_inflow
    }


# =====================================================
# HTTP
# =====================================================

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
                log.warning("HTTP %s: %s", response.status, str(data)[:250])
                return None

            if isinstance(data, dict) and (
                data.get("status") == "error"
                or data.get("code") == 400
            ):
                log.warning("API error: %s", str(data)[:250])
                return None

            return data

    except Exception:
        log.exception("Request failed: %s", url)
        return None


# =====================================================
# TWELVE DATA
# =====================================================

async def get_movers(session, market):
    params = {
        "direction": "gainers",
        "outputsize": CANDIDATES,
        "apikey": TD_KEY
    }

    if market == "US":
        params["country"] = "USA"
        params["price_greater_than"] = str(MIN_US_PRICE)

    data = await get_json(
        session,
        f"{TD_BASE}/market_movers/{'stocks' if market == 'US' else 'crypto'}",
        params
    )

    if not isinstance(data, dict):
        return []

    values = data.get("values", [])
    if not isinstance(values, list):
        return []

    if market == "US":
        filtered = []
        for item in values:
            exchange = str(item.get("exchange", "")).upper()
            symbol = str(item.get("symbol", "")).upper()

            # استبعاد OTC
            if any(x in exchange for x in ("OTC", "PINK", "GREY", "OTCQX", "OTCQB")):
                continue
            if not symbol or number(item.get("last")) < MIN_US_PRICE:
                continue

            filtered.append(item)

        return filtered

    return values


async def get_td_candles(session, symbol, market):
    params = {
        "symbol": symbol,
        "interval": "1min",
        "outputsize": 500,
        "apikey": TD_KEY
    }

    if market == "US":
        params["prepost"] = "true"

    data = await get_json(
        session,
        f"{TD_BASE}/time_series",
        params
    )

    if not isinstance(data, dict) or not isinstance(data.get("values"), list):
        return []

    return normalize(list(reversed(data["values"])))


async def get_float(session, symbol):
    now = datetime.now().timestamp()
    cached = float_cache.get(symbol)

    if cached and now - cached["time"] < 43200:
        return cached["value"]

    data = await get_json(
        session,
        f"{TD_BASE}/statistics",
        {"symbol": symbol, "apikey": TD_KEY}
    )

    value = None

    if isinstance(data, dict):
        def search_float(obj):
            if isinstance(obj, dict):
                for key, val in obj.items():
                    if key.lower() in ("float_shares", "float"):
                        n = number(val)
                        if n > 0:
                            return n
                    found = search_float(val)
                    if found:
                        return found
            return None

        value = search_float(data)

    float_cache[symbol] = {"time": now, "value": value}
    return value


# =====================================================
# SAHMK — SAUDI MARKET
# =====================================================

async def get_sahmk_movers(session, endpoint):
    headers = {"X-API-Key": SAHMK_KEY}

    data = await get_json(
        session,
        f"{SAHMK_BASE}/market/{endpoint}/",
        {"limit": 50, "index": "TASI"},
        headers
    )

    if not isinstance(data, dict):
        return []

    for key in ("gainers", "volume", "data", "results", "items"):
        value = data.get(key)
        if isinstance(value, list):
            return value

    return []


async def get_sahmk_candles(session, symbol):
    today = datetime.now(riyadh).date()
    start = today - timedelta(days=10)

    data = await get_json(
        session,
        f"{SAHMK_BASE}/historical/{symbol}/",
        {
            "interval": "1min",
            "from": start.isoformat(),
            "to": today.isoformat(),
            "limit": 500,
            "offset": 0
        },
        {"X-API-Key": SAHMK_KEY}
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


# =====================================================
# IMAGE DASHBOARD
# =====================================================

def make_dashboard(market, symbol, m, float_value, goals, entry, stop, tf):
    W, H = 1400, 1850
    img = Image.new("RGB", (W, H), (8, 14, 23))
    d = ImageDraw.Draw(img)

    green = (0, 235, 145)
    red = (255, 75, 90)
    gold = (255, 196, 65)
    white = (240, 245, 250)
    muted = (155, 175, 190)
    panel = (18, 31, 43)

    title = get_font(55, True)
    head = get_font(37, True)
    body = get_font(30, True)
    small = get_font(25)

    def box(y1, y2):
        d.rounded_rectangle(
            (30, y1, W-30, y2),
            radius=25,
            fill=panel,
            outline=(40, 75, 90),
            width=3
        )

    def right(y, text, font=body, color=white):
        d.text((W-65, y), rtl(text), font=font, fill=color, anchor="ra")

    def left(x, y, text, font=body, color=white):
        d.text((x, y), str(text), font=font, fill=color)

    box(25, 170)
    left(65, 55, "AI PRO MAX", title, green)
    right(105, "MARKET HUNTER V6.0", head, white)

    box(195, 430)
    right(225, f"{market} | {symbol}", head, gold)
    left(70, 300, fmt(m["price"]), title, green)
    right(355, f"التغير: {m['change']:+.2f}%", body, green)

    box(455, 820)
    right(485, "بيانات التداول", head, gold)

    values = [
        ("الحجم الفعلي", f'{m["volume"]:,.0f}'),
        ("قيمة السيولة", f'{m["liquidity"]:,.2f}'),
        ("نشاط التداول", f'x{m["volume_ratio"]:.2f}'),
        ("الأسهم الحرة", f'{float_value:,.0f}' if float_value else "غير متاح"),
        ("الفاصل", tf),
        ("الدخول", fmt(entry)),
    ]

    for i, (label, value) in enumerate(values):
        y = 555 + i * 42
        right(y, f"{label}: {value}", body, white)

    box(845, 1120)
    right(875, "الدعم والمقاومة", head, gold)
    right(965, f"المقاومة: {fmt(m['resistance'])}", body, red)
    right(1035, f"الدعم: {fmt(m['support'])}", body, green)
    right(1085, f"وقف الخسارة: {fmt(stop)} (-2%)", body, red)

    box(1145, 1665)
    right(1175, "الأهداف السعرية", head, gold)

    for i, target in enumerate(goals):
        row = i // 2
        col = i % 2
        x = 75 if col == 0 else 730
        y = 1260 + row * 90
        d.rounded_rectangle(
            (x, y, x+590, y+70),
            radius=14,
            fill=(10, 42, 35),
            outline=(0, 115, 80),
            width=2
        )
        left(x+20, y+15, f"TP{i+1}", body, green)
        d.text(
            (x+550, y+15),
            f"{fmt(target)}",
            font=body,
            fill=white,
            anchor="ra"
        )

    right(1710, "AI PRO MAX | LIVE MARKET SCANNER", small, muted)
    right(1760, datetime.now(riyadh).strftime("%Y-%m-%d %H:%M:%S الرياض"), small, muted)

    output = io.BytesIO()
    img.save(output, format="PNG", optimize=True)
    output.seek(0)
    return output


# =====================================================
# TELEGRAM
# =====================================================

async def send_photo(session, token, photo, caption):
    if not token or not CHAT_ID:
        return False

    form = aiohttp.FormData()
    form.add_field("chat_id", str(CHAT_ID))
    form.add_field("caption", caption[:1000])
    form.add_field(
        "photo",
        photo.getvalue(),
        filename="AI_PRO_MAX.png",
        content_type="image/png"
    )

    try:
        async with session.post(
            f"https://api.telegram.org/bot{token}/sendPhoto",
            data=form
        ) as response:
            result = await response.json(content_type=None)
            if result.get("ok"):
                return True
            log.error("Telegram: %s", result)
    except Exception:
        log.exception("Telegram photo error")

    return False


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
            return bool(data.get("ok"))
    except Exception:
        log.exception("Telegram message error")
        return False


# =====================================================
# SIGNALS AND TARGET TRACKING
# =====================================================

async def update_targets(session, token, market, symbol, price):
    key = f"{market}:{symbol}"
    signal = active_signals.get(key)

    if not signal:
        return

    changed = False
    for i, target in enumerate(signal["targets"]):
        if not signal["hit"][i] and price >= target:
            signal["hit"][i] = True
            changed = True

    if changed:
        status = "\n".join(
            f'{"✅" if signal["hit"][i] else "⬜"} TP{i+1}: {fmt(v)}'
            for i, v in enumerate(signal["targets"])
        )

        await send_text(
            session,
            token,
            f"💀🚀 <b>تحقق هدف — {symbol}</b>\n\n"
            f"السعر الحالي: {fmt(price)}\n{status}"
        )


async def process_symbol(session, market, item, token):
    symbol = str(item.get("symbol", "")).strip().upper()
    if not symbol:
        return

    try:
        if market == "السعودي":
            rows = await get_sahmk_candles(session, symbol)
        else:
            rows = await get_td_candles(session, symbol, market)

        if len(rows) < 30:
            return

        m = metrics(rows)
        if not m:
            return

        price = m["price"]

        if market == "US" and price < MIN_US_PRICE:
            return

        await update_targets(session, token, market, symbol, price)

        # تحليل الفواصل من بيانات الدقيقة
        timeframe_results = {}
        for label, minutes in TIMEFRAMES:
            bars = aggregate(rows, minutes)
            result = metrics(bars)
            if result:
                timeframe_results[label] = result

        # عرض السيولة والنشاط وترتيب الأسهم الصاعدة
        # لا يوجد شرط نقاط 65
        if not m["inflow"] and m["change"] <= 0:
            return

        now = datetime.now().timestamp()
        key = f"{market}:{symbol}"

        if now - sent_alerts.get(key, 0) < COOLDOWN:
            return

        float_value = None
        if market == "US":
            float_value = await get_float(session, symbol)

        entry = price
        stop = entry * 0.98

        goals = [entry * (1 + (0.02 * i)) for i in range(1, 9)]

        active_signals[key] = {
            "entry": entry,
            "stop": stop,
            "targets": goals,
            "hit": [False] * 8
        }

        # اختيار الفاصل الأقوى من حيث نشاط الحجم
        best_tf = max(
            timeframe_results,
            key=lambda x: timeframe_results[x]["volume_ratio"],
            default="1 دقيقة"
        )

        dashboard = make_dashboard(
            market, symbol, m, float_value,
            goals, entry, stop, best_tf
        )

        caption = (
            f"💀🚀 <b>AI PRO MAX — {symbol}</b>\n"
            f"📈 التغير: {m['change']:+.2f}%\n"
            f"💰 الدخول: {fmt(entry)}\n"
            f"💧 السيولة: {m['liquidity']:,.2f}\n"
            f"📊 نشاط الحجم: x{m['volume_ratio']:.2f}\n"
            f"⏱ الفاصل الأقوى: {best_tf}\n"
            f"🛑 وقف الخسارة: {fmt(stop)}\n"
            "🎯 الأهداف TP1–TP8 داخل الصورة\n"
            "⚠️ بيانات تحليلية وليست توصية استثمارية."
        )

        sent = await send_photo(session, token, dashboard, caption)

        if sent:
            sent_alerts[key] = now
            log.info("SIGNAL SENT %s %s", market, symbol)

    except Exception:
        log.exception("Symbol processing failed: %s %s", market, symbol)


# =====================================================
# MARKET SCANNERS
# =====================================================

async def scan_market(session, market):
    if market == "US":
        items = await get_movers(session, "US")
        token = US_TOKEN

    elif market == "CRYPTO":
        items = await get_movers(session, "CRYPTO")
        token = CRYPTO_TOKEN

    else:
        gainers, volume = await asyncio.gather(
            get_sahmk_movers(session, "gainers"),
            get_sahmk_movers(session, "volume")
        )

        combined = {}
        for item in gainers + volume:
            symbol = str(item.get("symbol", "")).strip()
            if symbol:
                combined[symbol] = item

        items = list(combined.values())
        token = TASI_TOKEN

    if not items:
        log.warning("No market candidates: %s", market)
        return

    # ترتيب الأكثر ارتفاعاً أولاً
    items.sort(
        key=lambda x: number(
            x.get("percent_change", x.get("change_percent", 0))
        ),
        reverse=True
    )

    semaphore = asyncio.Semaphore(MAX_WORKERS)

    async def worker(item):
        async with semaphore:
            await process_symbol(session, market, item, token)

    await asyncio.gather(*(worker(x) for x in items))


# =====================================================
# STARTUP AND 24/7 WORKER
# =====================================================

async def main():
    if not CHAT_ID:
        raise RuntimeError("CHAT_ID is missing")

    if not TD_KEY:
        raise RuntimeError("TWELVE_DATA_API_KEY is missing")

    if not US_TOKEN or not CRYPTO_TOKEN:
        raise RuntimeError("US_TOKEN or CRYPTO_TOKEN is missing")

    connector = aiohttp.TCPConnector(
        limit=20,
        ttl_dns_cache=300
    )

    async with aiohttp.ClientSession(
        connector=connector,
        timeout=aiohttp.ClientTimeout(total=40)
    ) as session:

        await send_text(
            session,
            US_TOKEN,
            "💀🚀 <b>AI PRO MAX V6.0</b>\n"
            "🟢 تم تشغيل الماسح\n"
            "🇺🇸 US | 🪙 CRYPTO | 🇸🇦 TASI\n"
            "📊 الفواصل المتعددة\n"
            "🎯 الأهداف TP1–TP8\n"
            "🛑 وقف الخسارة 2%\n"
            "⏰ الخدمة تعمل ما دامت الاستضافة متاحة."
        )

        last_tasi = 0

        while True:
            started = datetime.now().timestamp()

            try:
                # الأمريكي والعملات
                await asyncio.gather(
                    scan_market(session, "US"),
                    scan_market(session, "CRYPTO")
                )

                # السعودي
                now = datetime.now().timestamp()
                if now - last_tasi >= TASI_SCAN_SECONDS:
                    if SAHMK_KEY:
                        await scan_market(session, "السعودي")
                    last_tasi = now

            except Exception:
                log.exception("Main scanning cycle error")

            elapsed = datetime.now().timestamp() - started
            await asyncio.sleep(max(10, SCAN_SECONDS - elapsed))


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.warning("Worker stopped")
