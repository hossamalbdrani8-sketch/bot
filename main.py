
# ============================================================
# 💀🚀 AI PRO MAX — MARKET HUNTER V5.2
# US: NYSE + NASDAQ + NYSE AMERICAN | OTC EXCLUDED
# CRYPTO | TASI | TELEGRAM | 24/7
# ============================================================

import os
import io
import asyncio
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import aiohttp
from PIL import Image, ImageDraw, ImageFont

import arabic_reshaper
from bidi.algorithm import get_display


# ===================== SETTINGS =====================

TZ = ZoneInfo("Asia/Riyadh")

TD_KEY = (
    os.getenv("TWELVE_DATA_API_KEY")
    or os.getenv("TWELVEDATA_API_KEY")
)

SAHMK_API_KEY = os.getenv("SAHMK_API_KEY")
SAHMK_BASE = os.getenv(
    "SAHMK_BASE", "https://api.sahmk.sa/api/v1"
).rstrip("/")

CHAT_ID = os.getenv("CHAT_ID")
US_TOKEN = os.getenv("US_TOKEN")
CRYPTO_TOKEN = os.getenv("CRYPTO_TOKEN")
TASI_TOKEN = os.getenv("TASI_TOKEN") or US_TOKEN

TD_BASE = "https://api.twelvedata.com"

SCAN_SECONDS = max(60, int(os.getenv("SCAN_SECONDS", "300")))
TASI_SCAN_SECONDS = max(
    300, int(os.getenv("TASI_SCAN_SECONDS", "1800"))
)
HEARTBEAT_SECONDS = max(
    3600, int(os.getenv("HEARTBEAT_SECONDS", "21600"))
)

MIN_US_PRICE = 0.15
MIN_VOLUME_RATIO = float(os.getenv("MIN_VOLUME_RATIO", "1.5"))

TD_INTERVAL = os.getenv("TD_INTERVAL", "5min")
TD_CANDLES = 100

# عدد الأسهم في كل دورة لتقليل استهلاك API
US_BATCH_SIZE = max(1, int(os.getenv("US_BATCH_SIZE", "50")))

# البورصات المسموحة فقط
ALLOWED_EXCHANGES = {
    "NASDAQ",
    "NYSE",
    "NYSE AMERICAN",
    "AMEX",
}

CRYPTO_SYMBOLS = os.getenv(
    "CRYPTO_SYMBOLS",
    "BTC/USD,ETH/USD,SOL/USD,XRP/USD"
).split(",")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

log = logging.getLogger("AI_PRO_MAX")

sent_signals = {}
us_symbols = []
us_cursor = 0
universe_updated = 0


# ===================== HELPERS =====================

def now_riyadh():
    return datetime.now(TZ)


def clean_symbols(items):
    return list(dict.fromkeys(
        str(x).strip().upper()
        for x in items if str(x).strip()
    ))


CRYPTO_SYMBOLS = clean_symbols(CRYPTO_SYMBOLS)


def number(value, default=0.0):
    try:
        result = float(value)
        return result if result == result else default
    except (TypeError, ValueError):
        return default


def price_fmt(value):
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


# ===================== CANDLES =====================

def normalize_rows(rows):
    if not isinstance(rows, list):
        return []

    output = []

    for row in rows:
        if not isinstance(row, dict):
            continue

        lower = {str(k).lower(): v for k, v in row.items()}

        def get(*keys):
            for key in keys:
                if key in lower:
                    return number(lower[key])
            return 0.0

        item = {
            "open": get("open", "o"),
            "high": get("high", "h"),
            "low": get("low", "l"),
            "close": get("close", "c", "price", "last"),
            "volume": get("volume", "vol", "v", "total_volume")
        }

        if item["close"] <= 0:
            continue

        item["high"] = max(
            item["high"], item["open"], item["close"]
        )

        if item["low"] <= 0:
            item["low"] = min(
                item["open"] or item["close"],
                item["close"]
            )

        output.append(item)

    return output


def ema(values, period):
    if len(values) < period:
        return None

    result = sum(values[:period]) / period
    alpha = 2 / (period + 1)

    for value in values[period:]:
        result = value * alpha + result * (1 - alpha)

    return result


def calculate_rsi(values, period=14):
    if len(values) <= period:
        return 50.0

    changes = [
        values[i] - values[i - 1]
        for i in range(1, len(values))
    ]

    gains = [max(x, 0) for x in changes]
    losses = [max(-x, 0) for x in changes]

    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period

    if avg_loss == 0:
        return 100.0

    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def calculate_atr(rows, period=14):
    if len(rows) < period + 1:
        return None

    values = []

    for i in range(1, len(rows)):
        high = rows[i]["high"]
        low = rows[i]["low"]
        previous = rows[i - 1]["close"]

        values.append(max(
            high - low,
            abs(high - previous),
            abs(low - previous)
        ))

    return sum(values[-period:]) / period


def calculate_vwap(rows):
    total_value = 0
    total_volume = 0

    for row in rows:
        volume = row["volume"]

        if volume <= 0:
            continue

        typical = (
            row["high"] + row["low"] + row["close"]
        ) / 3

        total_value += typical * volume
        total_volume += volume

    return (
        total_value / total_volume
        if total_volume else None
    )


def calculate_volume_ratio(rows):
    if len(rows) < 21:
        return 0

    previous = [x["volume"] for x in rows[-21:-1]]
    average = sum(previous) / len(previous)

    if average <= 0:
        return 0

    return rows[-1]["volume"] / average


def calculate_levels(rows):
    if len(rows) < 25:
        return None

    highs = [x["high"] for x in rows]
    lows = [x["low"] for x in rows]
    price = rows[-1]["close"]

    pivot_highs = []
    pivot_lows = []

    for i in range(max(2, len(rows) - 80), len(rows) - 2):

        if (
            highs[i] >= highs[i-1]
            and highs[i] >= highs[i-2]
            and highs[i] > highs[i+1]
            and highs[i] > highs[i+2]
        ):
            pivot_highs.append(highs[i])

        if (
            lows[i] <= lows[i-1]
            and lows[i] <= lows[i-2]
            and lows[i] < lows[i+1]
            and lows[i] < lows[i+2]
        ):
            pivot_lows.append(lows[i])

    supports = sorted(
        {x for x in pivot_lows if x < price},
        reverse=True
    )

    resistances = sorted(
        {x for x in pivot_highs if x > price}
    )

    if not supports:
        supports = sorted(
            {x for x in lows[-20:] if x < price},
            reverse=True
        )

    if not resistances:
        resistances = sorted(
            {x for x in highs[-20:] if x > price}
        )

    return {
        "supports": supports[:3],
        "resistances": resistances[:3]
    }


def calculate_targets(price, atr, supports):
    if not atr or atr <= 0:
        return None

    stop = price - 1.5 * atr

    if supports:
        stop = min(stop, supports[0] - 0.15 * atr)

    return {
        "stop": stop,
        "targets": [
            price + atr * n for n in range(1, 9)
        ]
    }


# ===================== TELEGRAM =====================

async def telegram_send(session, token, message):
    if not token or not CHAT_ID:
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"

    try:
        async with session.post(
            url,
            json={
                "chat_id": CHAT_ID,
                "text": message,
                "parse_mode": "HTML",
                "disable_web_page_preview": True
            },
            timeout=aiohttp.ClientTimeout(total=20)
        ) as response:

            result = await response.json(content_type=None)

            if response.status == 200 and result.get("ok"):
                return True

            log.error("Telegram error: %s", result)

    except Exception:
        log.exception("Telegram send failed")

    return False


async def telegram_photo(session, token, photo, caption):
    if not token or not CHAT_ID:
        return False

    url = f"https://api.telegram.org/bot{token}/sendPhoto"

    form = aiohttp.FormData()
    form.add_field("chat_id", str(CHAT_ID))
    form.add_field("caption", caption[:900])
    form.add_field(
        "photo",
        photo.getvalue(),
        filename="AI_PRO_MAX.png",
        content_type="image/png"
    )

    try:
        async with session.post(
            url,
            data=form,
            timeout=aiohttp.ClientTimeout(total=30)
        ) as response:

            result = await response.json(content_type=None)

            if response.status == 200 and result.get("ok"):
                return True

            log.error("Photo error: %s", result)

    except Exception:
        log.exception("Photo sending failed")

    return False


async def send_startup(session):
    tokens = list(dict.fromkeys(
        x for x in (US_TOKEN, CRYPTO_TOKEN, TASI_TOKEN) if x
    ))

    message = (
        "💀🚀 <b>AI PRO MAX — MARKET HUNTER V5.2</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "🟢 تم تشغيل البوت بنجاح\n"
        "⏰ التشغيل المستمر 24/7 حسب خدمة الاستضافة\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "🇺🇸 NYSE | NASDAQ | NYSE AMERICAN\n"
        "🚫 OTC مستبعد بالكامل\n"
        "💲 أقل سعر: 0.15 USD\n"
        "🚀 اختراق أو دخول سيولة قوية\n"
        "🪙 CRYPTO مفعل حسب الإعدادات\n"
        "🇸🇦 TASI عند توفر SAHMK\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"🔄 دورة الفحص: {SCAN_SECONDS} ثانية\n"
        f"🕒 {now_riyadh().strftime('%Y-%m-%d %H:%M:%S')}\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "ℹ️ رسالة تأكيد تشغيل وليست إشارة تداول."
    )

    working = None

    for token in tokens:
        if await telegram_send(session, token, message):
            if working is None:
                working = token

    return working


async def heartbeat(session, token):
    await telegram_send(
        session,
        token,
        "💀🚀 <b>AI PRO MAX</b>\n"
        "🟢 البوت يعمل حالياً\n"
        "⏰ 24/7\n"
        f"🕒 {now_riyadh().strftime('%Y-%m-%d %H:%M:%S')}"
    )


# ===================== DASHBOARD =====================

def build_dashboard(
    market, symbol, price, score, rsi,
    vol_ratio, vwap, atr, levels, targets_data,
    reasons, currency, volume=0, liquidity=0
):
    width, height = 1600, 2200

    img = Image.new("RGB", (width, height), (7, 12, 18))
    draw = ImageDraw.Draw(img)

    green = (0, 230, 140)
    red = (255, 75, 90)
    white = (238, 245, 248)
    gold = (255, 195, 70)
    cyan = (69, 205, 255)
    muted = (145, 164, 177)
    panel = (15, 24, 33)

    title = font(60, True)
    head = font(43, True)
    body = font(36, True)
    small = font(29)
    value = font(38, True)
    big = font(75, True)

    def box(coords, fill=panel):
        draw.rounded_rectangle(
            coords, radius=24, fill=fill,
            outline=(35, 57, 70), width=3
        )

    def left(x, y, text, f=body, color=white):
        draw.text((x, y), str(text), font=f, fill=color)

    def right(x, y, text, f=body, color=white):
        draw.text(
            (x, y), rtl(text), font=f,
            fill=color, anchor="ra"
        )

    box((25, 25, 1575, 185), (10, 27, 35))
    left(65, 55, "AI PRO MAX", title, green)
    right(1535, 65, "صائد الفرص MARKET HUNTER", head)
    left(70, 125, "LIVE SIGNAL • US / TASI / CRYPTO", small, muted)

    box((25, 210, 1575, 520), (19, 31, 41))
    right(1535, 235, f"{market} | {symbol}", head, cyan)
    left(70, 315, price_fmt(price), big, green)
    left(75, 410, currency, body, muted)
    right(1535, 330, "قوة الإشارة", head, gold)
    right(1535, 395, f"{score}/100", big, green)

    x1, y1, x2 = 750, 465, 1535
    draw.rounded_rectangle(
        (x1, y1, x2, y1 + 25),
        radius=12, fill=(42, 57, 66)
    )
    draw.rounded_rectangle(
        (x1, y1, x1 + int((x2-x1)*max(0, min(score, 100))/100),
         y1 + 25),
        radius=12, fill=green
    )

    box((25, 550, 1575, 1030))
    right(1535, 575, "الحجم والسيولة والنشاط", head, gold)

    metrics = [
        ("VOLUME", f"{volume:,.0f}", cyan),
        ("LIQUIDITY*", f"{liquidity:,.2f} {currency}", green),
        ("ACTIVITY", f"x{vol_ratio:.2f}", gold),
        ("RSI", f"{rsi:.1f}", cyan),
        ("VWAP", price_fmt(vwap), white),
        ("ATR", price_fmt(atr), gold)
    ]

    positions = [
        (65, 665), (575, 665), (1085, 665),
        (65, 845), (575, 845), (1085, 845)
    ]

    for (label, val, color), (x, y) in zip(metrics, positions):
        box((x, y, x+450, y+145))
        left(x+20, y+15, label, small, muted)
        left(x+20, y+67, val, value, color)

    box((25, 1060, 1575, 1390))
    right(1535, 1085, "الدعم والمقاومة", head, gold)

    supports = levels.get("supports", [])
    resistances = levels.get("resistances", [])

    for i in range(3):
        y = 1170 + i * 65
        sv = price_fmt(supports[i]) if i < len(supports) else "—"
        rv = price_fmt(resistances[i]) if i < len(resistances) else "—"

        left(70, y, f"S{i+1}  {sv}", body, green)
        right(1530, y, f"R{i+1}  {rv}", body, red)

    box((25, 1420, 1575, 1970))
    right(1535, 1445, "الأهداف السعرية TP1 — TP8", head, gold)

    for i, target in enumerate(targets_data["targets"][:8]):
        col = i % 2
        row = i // 2
        x = 65 if col == 0 else 825
        y = 1520 + row * 105

        draw.rounded_rectangle(
            (x, y, x+710, y+82),
            radius=15, fill=(10, 26, 27),
            outline=(0, 91, 69), width=2
        )

        left(x+20, y+18, f"TP{i+1}", body, green)
        right(x+685, y+10, price_fmt(target), body, white)

        change = (target-price)/price*100 if price else 0

        right(
            x+685, y+48,
            f"{change:+.2f}%", small, green
        )

    box((25, 1995, 1575, 2110), (38, 15, 22))
    right(
        1535, 2025,
        f"وقف الخسارة الفني: {price_fmt(targets_data['stop'])} {currency}",
        head, red
    )

    right(
        1550, 2140,
        f"{now_riyadh().strftime('%Y-%m-%d %H:%M:%S')} الرياض",
        small, muted
    )

    output = io.BytesIO()
    img.save(output, format="PNG", optimize=True)
    output.seek(0)

    return output


# ===================== TWELVE DATA =====================

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
                log.error("HTTP %s: %s", response.status, data)
                return None

            if isinstance(data, dict):
                if data.get("status") == "error":
                    log.error("API error: %s", data)
                    return None

                if data.get("code") == 400:
                    log.error("API error: %s", data)
                    return None

            return data

    except Exception:
        log.exception("Request failed: %s", url)
        return None


# ===================== US STOCK UNIVERSE =====================

def valid_us_exchange(item):
    exchange = str(
        item.get("exchange") or item.get("mic_code") or ""
    ).strip().upper()

    if exchange in ALLOWED_EXCHANGES:
        return True

    if "NASDAQ" in exchange:
        return True

    if exchange == "NYSE":
        return True

    if "NYSE AMERICAN" in exchange:
        return True

    if exchange == "AMEX":
        return True

    return False


async def get_us_universe(session):
    global us_symbols, universe_updated

    # تحديث قائمة الأسهم كل 24 ساعة
    if us_symbols and datetime.now().timestamp() - universe_updated < 86400:
        return us_symbols

    if not TD_KEY:
        log.error("Twelve Data key missing")
        return us_symbols

    exchanges = ["NASDAQ", "NYSE", "NYSE American", "AMEX"]
    discovered = set()

    for exchange in exchanges:
        params = {
            "country": "United States",
            "exchange": exchange,
            "type": "Common Stock",
            "apikey": TD_KEY
        }

        data = await get_json(
            session,
            f"{TD_BASE}/stocks",
            params=params
        )

        if not isinstance(data, dict):
            continue

        items = data.get("data", [])

        if not isinstance(items, list):
            continue

        for item in items:
            if not isinstance(item, dict):
                continue

            symbol = str(item.get("symbol") or "").strip().upper()

            if not symbol:
                continue

            # لا نقبل إلا البورصات المحددة
            if not valid_us_exchange(item):
                continue

            # استبعاد أي رمز مصنف OTC
            if "OTC" in str(item.get("exchange", "")).upper():
                continue

            discovered.add(symbol)

    if discovered:
        us_symbols = sorted(discovered)
        universe_updated = datetime.now().timestamp()

        log.info(
            "US universe loaded: %s symbols",
            len(us_symbols)
        )

        await telegram_send(
            session,
            US_TOKEN,
            "🇺🇸 <b>تم تحديث قائمة الأسهم الأمريكية</b>\n"
            f"📊 عدد الرموز المكتشفة: {len(us_symbols)}\n"
            "NYSE | NASDAQ | NYSE AMERICAN\n"
            "🚫 OTC مستبعد"
        )

    else:
        log.error("Could not load US stock universe")

    return us_symbols


async def get_td_candles(session, symbol, market):
    if not TD_KEY:
        return None

    params = {
        "symbol": symbol,
        "interval": TD_INTERVAL,
        "outputsize": TD_CANDLES,
        "apikey": TD_KEY
    }

    if market == "US":
        params["prepost"] = "true"

    data = await get_json(
        session,
        f"{TD_BASE}/time_series",
        params=params
    )

    if not isinstance(data, dict):
        return None

    values = data.get("values")

    if not isinstance(values, list):
        return None

    return list(reversed(values))


# ===================== SIGNAL ANALYSIS =====================

def signal_cooldown(key, seconds=1800):
    last = sent_signals.get(key, 0)
    return datetime.now().timestamp() - last >= seconds


async def analyze_rows(
    session, symbol, market, rows, token, currency
):
    rows = normalize_rows(rows)

    if len(rows) < 25:
        return

    closes = [x["close"] for x in rows]

    price = closes[-1]
    previous_price = closes[-2]

    # الحد الأدنى للسهم الأمريكي
    if market == "US" and price < MIN_US_PRICE:
        return

    ema9 = ema(closes, 9)
    ema21 = ema(closes, 21)

    rsi = calculate_rsi(closes)
    atr = calculate_atr(rows)
    vwap = calculate_vwap(rows)
    vol_ratio = calculate_volume_ratio(rows)

    if not atr or atr <= 0:
        return

    prior_levels = calculate_levels(rows[:-1])
    levels = calculate_levels(rows)

    if not prior_levels or not levels:
        return

    targets_data = calculate_targets(
        price, atr, levels["supports"]
    )

    if not targets_data:
        return

    score = 0
    reasons = []

    if ema9 and ema21 and ema9 > ema21:
        score += 15
        reasons.append("اتجاه EMA إيجابي")

    if vwap and price > vwap:
        score += 15
        reasons.append("السعر أعلى VWAP")

    if vol_ratio >= MIN_VOLUME_RATIO:
        score += 20
        reasons.append(
            f"دخول سيولة قوية x{vol_ratio:.2f}"
        )

    if 50 <= rsi <= 75:
        score += 10
        reasons.append(f"RSI إيجابي {rsi:.1f}")

    # اختراق مقاومة
    resistance = (
        prior_levels["resistances"][0]
        if prior_levels["resistances"] else None
    )

    breakout = (
        resistance is not None
        and price > resistance
        and previous_price <= resistance
    )

    if breakout:
        score += 25
        reasons.append(
            f"اختراق مقاومة {price_fmt(resistance)}"
        )

    if ema9 and price > ema9 and previous_price <= ema9:
        score += 10
        reasons.append("بداية تحرك صاعد")

    candle_range = rows[-1]["high"] - rows[-1]["low"]

    if candle_range > 0:
        close_position = (
            price - rows[-1]["low"]
        ) / candle_range

        if close_position >= 0.75:
            score += 5
            reasons.append("إغلاق قوي للشمعة")

    # ==================================================
    # الشرط الجديد:
    # اختراق مقاومة OR دخول سيولة قوية
    # لا يوجد حد أدنى للنقاط
    # ==================================================

    strong_liquidity = vol_ratio >= MIN_VOLUME_RATIO

    if not breakout and not strong_liquidity:
        return

    signal_type = []

    if breakout:
        signal_type.append("BREAKOUT")

    if strong_liquidity:
        signal_type.append("SMART MONEY")

    signal = "+".join(signal_type)
    key = f"{market}:{symbol}:{signal}"

    if not signal_cooldown(key):
        return

    current_volume = rows[-1]["volume"]
    liquidity = price * current_volume

    dashboard = build_dashboard(
        market,
        symbol,
        price,
        min(score, 100),
        rsi,
        vol_ratio,
        vwap,
        atr,
        levels,
        targets_data,
        reasons,
        currency,
        current_volume,
        liquidity
    )

    reason_text = "\n".join(
        f"• {x}" for x in reasons
    )

    caption = (
        f"💀🚀 <b>AI PRO MAX V5.2</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📌 <b>{symbol}</b>\n"
        f"🌍 السوق: {market}\n"
        f"💰 السعر: {price_fmt(price)} {currency}\n"
        f"🚀 نوع الإشارة: {signal}\n"
        f"📊 قوة التحليل: {min(score, 100)}/100\n"
        f"📈 نشاط الحجم: x{vol_ratio:.2f}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"{reason_text}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"⚠️ ليست توصية استثمارية."
    )

    success = await telegram_photo(
        session, token, dashboard, caption
    )

    if success:
        sent_signals[key] = datetime.now().timestamp()

        log.info(
            "SIGNAL SENT: %s %s %s",
            market, symbol, signal
        )


# ===================== US SCANNER =====================

async def scan_us_market(session):
    global us_cursor

    symbols = await get_us_universe(session)

    if not symbols:
        log.warning("No US symbols available")
        return

    total = len(symbols)

    start = us_cursor
    end = min(start + US_BATCH_SIZE, total)

    batch = symbols[start:end]

    if not batch:
        us_cursor = 0
        batch = symbols[:US_BATCH_SIZE]
        end = min(US_BATCH_SIZE, total)

    log.info(
        "US scan batch: %s/%s",
        len(batch), total
    )

    semaphore = asyncio.Semaphore(2)

    async def worker(symbol):
        async with semaphore:
            try:
                rows = await get_td_candles(
                    session, symbol, "US"
                )

                if rows:
                    await analyze_rows(
                        session,
                        symbol,
                        "US",
                        rows,
                        US_TOKEN,
                        "USD"
                    )

            except Exception:
                log.exception("US worker failed: %s", symbol)

    await asyncio.gather(
        *(worker(symbol) for symbol in batch)
    )

    us_cursor = end

    if us_cursor >= total:
        us_cursor = 0
        log.info("US full universe rotation completed")


# ===================== CRYPTO SCANNER =====================

async def scan_crypto(session):
    if not CRYPTO_TOKEN:
        return

    semaphore = asyncio.Semaphore(2)

    async def worker(symbol):
        async with semaphore:
            try:
                rows = await get_td_candles(
                    session, symbol, "CRYPTO"
                )

                if rows:
                    await analyze_rows(
                        session,
                        symbol,
                        "CRYPTO",
                        rows,
                        CRYPTO_TOKEN,
                        "USD"
                    )

            except Exception:
                log.exception("Crypto worker failed: %s", symbol)

    await asyncio.gather(
        *(worker(s) for s in CRYPTO_SYMBOLS)
    )


# ===================== TASI / SAHMK =====================

async def get_sahmk_history(session, symbol):
    if not SAHMK_API_KEY:
        return None

    headers = {"X-API-Key": SAHMK_API_KEY}

    today = now_riyadh().date()
    start = today - timedelta(days=180)

    params = {
        "interval": "1d",
        "from": start.isoformat(),
        "to": today.isoformat(),
        "limit": 100,
        "offset": 0
    }

    data = await get_json(
        session,
        f"{SAHMK_BASE}/historical/{symbol}/",
        params=params,
        headers=headers
    )

    if not isinstance(data, dict):
        return None

    rows = data.get("data")

    if isinstance(rows, dict):
        rows = (
            rows.get("results")
            or rows.get("items")
            or rows.get("candles")
        )

    return rows if isinstance(rows, list) else None


async def get_sahmk_list(session, endpoint):
    if not SAHMK_API_KEY:
        return []

    headers = {"X-API-Key": SAHMK_API_KEY}

    data = await get_json(
        session,
        f"{SAHMK_BASE}/market/{endpoint}/",
        params={"limit": 30, "market": "TASI"},
        headers=headers
    )

    if not isinstance(data, dict):
        return []

    for key in (
        "data", "results", "gainers",
        "leaders", "stocks", "items"
    ):
        value = data.get(key)

        if isinstance(value, list):
            return value

    return []


async def scan_tasi(session):
    if not SAHMK_API_KEY:
        return

    gainers, volumes = await asyncio.gather(
        get_sahmk_list(session, "gainers"),
        get_sahmk_list(session, "volume")
    )

    selected = {}

    for item in gainers + volumes:
        if not isinstance(item, dict):
            continue

        symbol = str(
            item.get("symbol") or item.get("ticker") or ""
        ).strip()

        if symbol:
            selected[symbol] = item

    log.info("TASI symbols: %s", len(selected))

    semaphore = asyncio.Semaphore(2)

    async def worker(symbol):
        async with semaphore:
            try:
                rows = await get_sahmk_history(
                    session, symbol
                )

                if rows:
                    await analyze_rows(
                        session,
                        symbol,
                        "TASI",
                        rows,
                        TASI_TOKEN,
                        "SAR"
                    )

            except Exception:
                log.exception("TASI worker failed: %s", symbol)

    await asyncio.gather(
        *(worker(s) for s in selected)
    )


# ===================== MAIN 24/7 =====================

async def main():

    if not CHAT_ID:
        raise RuntimeError("CHAT_ID missing")

    connector = aiohttp.TCPConnector(
        limit=15,
        ttl_dns_cache=300
    )

    timeout = aiohttp.ClientTimeout(total=40)

    async with aiohttp.ClientSession(
        connector=connector,
        timeout=timeout
    ) as session:

        alert_token = await send_startup(session)

        if not alert_token:
            raise RuntimeError(
                "Telegram startup failed. Check tokens and CHAT_ID."
            )

        if not TD_KEY:
            await telegram_send(
                session,
                alert_token,
                "🔴 مفتاح Twelve Data غير موجود"
            )
            raise RuntimeError("Twelve Data key missing")

        if not US_TOKEN:
            log.warning("US_TOKEN missing")

        if not CRYPTO_TOKEN:
            log.warning("CRYPTO_TOKEN missing")

        if not SAHMK_API_KEY:
            log.warning("SAHMK_API_KEY missing")

        # تحميل قائمة الأسهم الأمريكية
        if US_TOKEN:
            await get_us_universe(session)

        last_tasi = 0
        last_heartbeat = datetime.now().timestamp()
        last_status = 0

        log.info("AI PRO MAX V5.2 STARTED")

        await telegram_send(
            session,
            alert_token,
            "🟢 <b>بدأ ماسح السوق</b>\n"
            "🚀 البحث عن الاختراق والسيولة\n"
            "🚫 OTC مستبعد\n"
            "💲 الحد الأدنى 0.15 USD"
        )

        while True:

            started = datetime.now().timestamp()

            try:

                if US_TOKEN:
                    await scan_us_market(session)

                if CRYPTO_TOKEN:
                    await scan_crypto(session)

                now = datetime.now().timestamp()

                if (
                    SAHMK_API_KEY
                    and now - last_tasi >= TASI_SCAN_SECONDS
                ):
                    await scan_tasi(session)
                    last_tasi = now

                if now - last_status >= 21600:
                    await telegram_send(
                        session,
                        alert_token,
                        "📡 <b>تقرير الماسح</b>\n"
                        "🟢 الخدمة تعمل\n"
                        f"🇺🇸 الأسهم المحملة: {len(us_symbols)}\n"
                        f"🔄 حجم الدفعة: {US_BATCH_SIZE}\n"
                        f"🕒 {now_riyadh().strftime('%H:%M:%S')}"
                    )
                    last_status = now

            except Exception:
                log.exception("Main scanning error")

            now = datetime.now().timestamp()

            if now - last_heartbeat >= HEARTBEAT_SECONDS:
                await heartbeat(session, alert_token)
                last_heartbeat = now

            elapsed = datetime.now().timestamp() - started

            wait = max(15, SCAN_SECONDS - elapsed)

            log.info(
                "Cycle completed. Next scan in %.0f seconds",
                wait
            )

            await asyncio.sleep(wait)


if __name__ == "__main__":
    try:
        asyncio.run(main())

    except KeyboardInterrupt:
        log.warning("Bot stopped manually")
