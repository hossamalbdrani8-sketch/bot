# ============================================================
# 💀🚀 AI PRO MAX — MARKET HUNTER V4
# 🇺🇸 US | 🪙 CRYPTO | 🇸🇦 TASI
# Twelve Data + SAHMK (same providers as previous version)
# ============================================================

import os
import io
import asyncio
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from html import escape

import aiohttp
from PIL import Image, ImageDraw, ImageFont
import arabic_reshaper
from bidi.algorithm import get_display

# ------------------------- SETTINGS -------------------------

TWELVE_API_KEY = (
    os.getenv("TWELVE_DATA_API_KEY")
    or os.getenv("TWELVEDATA_API_KEY")
)
SAHMK_API_KEY = os.getenv("SAHMK_API_KEY")
CHAT_ID = os.getenv("CHAT_ID")

US_TOKEN = os.getenv("US_TOKEN")
CRYPTO_TOKEN = os.getenv("CRYPTO_TOKEN")
TASI_TOKEN = os.getenv("TASI_TOKEN") or US_TOKEN

US_SYMBOLS = os.getenv(
    "US_SYMBOLS", "AAPL,TSLA,NVDA,AMD,PLTR"
).split(",")

CRYPTO_SYMBOLS = os.getenv(
    "CRYPTO_SYMBOLS", "BTC/USD,ETH/USD,SOL/USD,XRP/USD"
).split(",")

SCAN_SECONDS = int(os.getenv("SCAN_SECONDS", "300"))
TASI_SCAN_SECONDS = int(os.getenv("TASI_SCAN_SECONDS", "1800"))
MIN_SCORE = int(os.getenv("MIN_SCORE", "65"))
MIN_VOLUME_RATIO = float(os.getenv("MIN_VOLUME_RATIO", "1.5"))
TD_INTERVAL = os.getenv("TD_INTERVAL", "5min")
TD_CANDLES = int(os.getenv("TD_CANDLES", "100"))

TD_BASE = "https://api.twelvedata.com"
SAHMK_BASE = os.getenv("SAHMK_BASE", "https://api.sahmk.sa/api/v1").rstrip("/")

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s | %(levelname)s | %(message)s"
)
log = logging.getLogger("AI_PRO_MAX")

sent_signals = {}


# ---------------------- GENERAL HELPERS ---------------------

def clean_symbols(items):
    return list(dict.fromkeys(
        item.strip().upper() for item in items if item.strip()
    ))


US_SYMBOLS = clean_symbols(US_SYMBOLS)
CRYPTO_SYMBOLS = clean_symbols(CRYPTO_SYMBOLS)


def num(value, default=0.0):
    try:
        result = float(value)
        return result if result == result else default
    except (TypeError, ValueError):
        return default


def fmt(value, digits=4):
    if value is None:
        return "غير متاح"
    return f"{value:,.{digits}f}"


def normalize_rows(rows):
    """Normalize common candle field names into open/high/low/close/volume."""
    if not isinstance(rows, list):
        return []

    normalized = []
    aliases = {
        "open": ("open", "o"),
        "high": ("high", "h"),
        "low": ("low", "l"),
        "close": ("close", "c", "price", "last"),
        "volume": ("volume", "vol", "v", "total_volume"),
    }

    for row in rows:
        if not isinstance(row, dict):
            continue
        item = {}
        lower = {str(k).lower(): v for k, v in row.items()}
        for target, keys in aliases.items():
            found = None
            for key in keys:
                if key in lower:
                    found = lower[key]
                    break
            item[target] = num(found, 0.0)

        if item["close"] > 0:
            if item["high"] <= 0:
                item["high"] = max(item["open"], item["close"])
            if item["low"] <= 0:
                item["low"] = min(item["open"] or item["close"], item["close"])
            normalized.append(item)

    return normalized


def ema(values, period):
    if len(values) < period:
        return None
    result = sum(values[:period]) / period
    alpha = 2.0 / (period + 1)
    for value in values[period:]:
        result = value * alpha + result * (1.0 - alpha)
    return result


def calculate_rsi(values, period=14):
    if len(values) <= period:
        return 50.0
    changes = [values[i] - values[i - 1] for i in range(1, len(values))]
    gains = [max(x, 0.0) for x in changes]
    losses = [max(-x, 0.0) for x in changes]
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def calculate_atr(rows, period=14):
    if len(rows) < period + 1:
        return None
    tr_values = []
    for i in range(1, len(rows)):
        high = rows[i]["high"]
        low = rows[i]["low"]
        prev_close = rows[i - 1]["close"]
        tr_values.append(max(
            high - low,
            abs(high - prev_close),
            abs(low - prev_close)
        ))
    return sum(tr_values[-period:]) / period


def calculate_vwap(rows):
    total_value = 0.0
    total_volume = 0.0
    for row in rows:
        volume = row["volume"]
        if volume <= 0:
            continue
        typical = (row["high"] + row["low"] + row["close"]) / 3.0
        total_value += typical * volume
        total_volume += volume
    return total_value / total_volume if total_volume else None


def calculate_volume_ratio(rows):
    if len(rows) < 21:
        return 0.0
    volumes = [x["volume"] for x in rows[-21:-1]]
    average = sum(volumes) / len(volumes)
    return rows[-1]["volume"] / average if average > 0 else 0.0


# ---------------- SUPPORT / RESISTANCE ---------------------

def calculate_levels(rows):
    if len(rows) < 25:
        return None

    highs = [x["high"] for x in rows]
    lows = [x["low"] for x in rows]
    price = rows[-1]["close"]

    pivot_highs, pivot_lows = [], []
    start = max(2, len(rows) - 80)
    end = len(rows) - 2

    for i in range(start, end):
        if (highs[i] >= highs[i-1] and highs[i] >= highs[i-2]
                and highs[i] > highs[i+1] and highs[i] > highs[i+2]):
            pivot_highs.append(highs[i])
        if (lows[i] <= lows[i-1] and lows[i] <= lows[i-2]
                and lows[i] < lows[i+1] and lows[i] < lows[i+2]):
            pivot_lows.append(lows[i])

    supports = sorted({x for x in pivot_lows if x < price}, reverse=True)
    resistances = sorted({x for x in pivot_highs if x > price})

    if not supports:
        supports = sorted({x for x in lows[-20:] if x < price}, reverse=True)
    if not resistances:
        resistances = sorted({x for x in highs[-20:] if x > price})

    return {"supports": supports[:3], "resistances": resistances[:3]}


def calculate_targets(price, atr, supports):
    if not atr or atr <= 0:
        return None
    stop = price - (1.5 * atr)
    if supports:
        stop = min(stop, supports[0] - (0.15 * atr))
    return {
        "stop": stop,
        "targets": [price + atr * n for n in range(1, 9)]
    }


# ------------------------ TELEGRAM -------------------------

async def telegram_send(session, token, message):
    if not token or not CHAT_ID:
        log.error("Telegram token or CHAT_ID is missing for this market.")
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }
    try:
        async with session.post(
            url, json=payload, timeout=aiohttp.ClientTimeout(total=20)
        ) as response:
            result = await response.json(content_type=None)
            if response.status == 200 and result.get("ok") is True:
                return True
            log.error("Telegram HTTP %s: %s", response.status, str(result)[:500])
    except Exception:
        log.exception("Telegram send failed")
    return False


def rtl(text):
    """Shape Arabic text for Pillow rendering."""
    value = str(text)
    try:
        return get_display(arabic_reshaper.reshape(value))
    except Exception:
        return value


def dashboard_font(size, bold=False):
    root = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(root, "fonts", "NotoKufiArabic-Bold.ttf") if bold
        else os.path.join(root, "fonts", "NotoKufiArabic-Regular.ttf"),
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold
        else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf" if bold
        else "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def build_dashboard_image(market, symbol, price, score, rsi, vol_ratio,
                         vwap, atr, levels, targets_data, reasons, currency):
    """Create a real-data Telegram dashboard card (no fabricated chart candles)."""
    width, height = 1200, 1540
    image = Image.new("RGB", (width, height), (7, 12, 18))
    draw = ImageDraw.Draw(image)

    bg = (7, 12, 18)
    panel = (15, 24, 33)
    panel2 = (19, 31, 41)
    green = (0, 230, 140)
    green_dim = (0, 125, 91)
    red = (255, 75, 90)
    white = (238, 245, 248)
    muted = (145, 164, 177)
    gold = (255, 195, 70)
    cyan = (69, 205, 255)

    title_font = dashboard_font(48, True)
    head_font = dashboard_font(30, True)
    body_font = dashboard_font(25)
    small_font = dashboard_font(21)
    price_font = dashboard_font(62, True)
    score_font = dashboard_font(54, True)

    def rounded(box, fill=panel, outline=(35, 57, 70), radius=24, width_line=2):
        draw.rounded_rectangle(box, radius=radius, fill=fill,
                               outline=outline, width=width_line)

    def text_right(x, y, value, font, fill=white):
        draw.text((x, y), rtl(value), font=font, fill=fill, anchor="ra")

    def text_left(x, y, value, font, fill=white):
        draw.text((x, y), str(value), font=font, fill=fill)

    # Header
    draw.rounded_rectangle((28, 24, width-28, 145), radius=28,
                           fill=(10, 27, 35), outline=green_dim, width=3)
    text_left(62, 48, "AI PRO MAX", title_font, green)
    text_right(width-62, 59, "صائد الفرص — MARKET HUNTER", head_font, white)
    text_left(64, 108, "LIVE SIGNAL  •  US / TASI / CRYPTO", small_font, muted)

    # Instrument and signal
    rounded((28, 170, width-28, 420), fill=panel2, outline=(0, 110, 82))
    text_right(width-65, 194, f"{market}  |  {symbol}", head_font, cyan)
    text_left(65, 250, f"{price:,.4f}" if price < 1 else f"{price:,.2f}", price_font, green)
    text_left(68, 330, currency, body_font, muted)
    text_right(width-65, 282, "إشارة صاعدة / اختراق", head_font, green)
    text_right(width-65, 335, f"قوة الإشارة  {score}/100", body_font, white)
    bar_x1, bar_y, bar_x2 = 650, 382, width-65
    draw.rounded_rectangle((bar_x1, bar_y, bar_x2, bar_y+18), radius=9, fill=(42, 57, 66))
    draw.rounded_rectangle((bar_x1, bar_y, bar_x1+(bar_x2-bar_x1)*max(0,min(score,100))/100, bar_y+18), radius=9, fill=green)

    # Market metrics
    rounded((28, 445, width-28, 650))
    text_right(width-65, 465, "مؤشرات السوق", head_font, gold)
    metrics = [
        ("RSI", f"{rsi:.1f}", cyan),
        ("VOLUME", f"×{vol_ratio:.2f}", green),
        ("VWAP", f"{vwap:,.4f}" if vwap is not None else "—", white),
        ("ATR", f"{atr:,.4f}", gold),
    ]
    cell_w = (width-150)//4
    for i, (label, value, color) in enumerate(metrics):
        x = 65 + i*cell_w
        draw.rounded_rectangle((x, 520, x+cell_w-18, 620), radius=16, fill=(10, 18, 26))
        text_left(x+18, 535, label, small_font, muted)
        text_left(x+18, 570, value, body_font, color)

    # Support / resistance
    rounded((28, 675, width-28, 895))
    text_right(width-65, 695, "الدعم والمقاومة", head_font, white)
    supports = levels.get("supports", [])
    resistances = levels.get("resistances", [])
    for i in range(3):
        y = 755 + i*43
        sv = supports[i] if i < len(supports) else None
        rv = resistances[i] if i < len(resistances) else None
        text_left(70, y, f"S{i+1}  {sv:,.4f}" if sv is not None else f"S{i+1}  —", body_font, green)
        text_right(width-70, y, f"R{i+1}  {rv:,.4f}" if rv is not None else f"R{i+1}  —", body_font, red)

    # Targets and stop
    rounded((28, 920, width-28, 1350))
    text_right(width-65, 940, "الأهداف السعرية TP1 — TP8", head_font, gold)
    targets = targets_data.get("targets", [])
    for i, target in enumerate(targets[:8]):
        col = i % 2
        row = i // 2
        x = 65 if col == 0 else 625
        y = 1005 + row*73
        rounded((x, y, x+510, y+58), fill=(10, 26, 27), outline=(0, 91, 69), radius=13, width_line=1)
        text_left(x+18, y+12, f"TP{i+1}", body_font, green)
        text_right(x+485, y+12, f"{target:,.4f}" if target < 1 else f"{target:,.2f}", body_font, white)

    stop = targets_data.get("stop")
    rounded((28, 1370, width-28, 1450), fill=(38, 15, 22), outline=(120, 40, 48))
    stop_text = f"وقف الخسارة الفني: {stop:,.4f} {currency}" if stop is not None else "وقف الخسارة الفني: غير متاح"
    text_right(width-65, 1390, stop_text, body_font, red)

    # Footer
    footer = datetime.now(ZoneInfo("Asia/Riyadh")).strftime("%Y-%m-%d  %H:%M:%S")
    text_right(width-45, 1480, f"تحليل آلي من البيانات المستلمة  •  {footer} بتوقيت الرياض", small_font, muted)

    output = io.BytesIO()
    image.save(output, format="PNG", optimize=True)
    output.seek(0)
    return output


async def telegram_send_photo(session, token, photo, caption):
    if not token or not CHAT_ID:
        return False
    url = f"https://api.telegram.org/bot{token}/sendPhoto"
    form = aiohttp.FormData()
    form.add_field("chat_id", str(CHAT_ID))
    form.add_field("caption", caption[:900])
    form.add_field("photo", photo.getvalue(), filename="ai_pro_max_signal.png",
                    content_type="image/png")
    try:
        async with session.post(url, data=form,
                               timeout=aiohttp.ClientTimeout(total=30)) as response:
            result = await response.json(content_type=None)
            if response.status == 200 and result.get("ok") is True:
                return True
            log.error("Telegram photo HTTP %s: %s", response.status, str(result)[:500])
    except Exception:
        log.exception("Telegram photo send failed")
    return False


def build_signal_message(market, symbol, price, score, rsi, vol_ratio,
                         vwap, atr, levels, targets_data, reasons, currency):
    supports = levels["supports"]
    resistances = levels["resistances"]
    targets = targets_data["targets"]
    stop = targets_data["stop"]

    def pct(value):
        return ((value - price) / price * 100.0) if price > 0 else 0.0

    if score >= 85:
        title = "🚀 اختراق قوي"
    elif score >= 70:
        title = "🟢 إشارة صاعدة"
    else:
        title = "🟡 مراقبة مبكرة"

    lines = [
        "💀🚀 <b>AI PRO MAX — MARKET HUNTER V4</b>",
        "━━━━━━━━━━━━━━━━━━",
        f"🌍 السوق: <b>{escape(str(market))}</b>",
        f"🔢 الرمز: <b>{escape(str(symbol))}</b>",
        f"💰 السعر: <b>{fmt(price)} {currency}</b>",
        f"⭐ قوة الإشارة: <b>{score}/100</b>",
        f"📊 RSI: {rsi:.1f}",
        f"💹 حجم التداول: ×{vol_ratio:.2f}",
        f"📈 VWAP: {fmt(vwap)}",
        f"📏 ATR: {fmt(atr)}",
        "━━━━━━━━━━━━━━━━━━",
        "🟢 <b>مناطق الدعم</b>"
    ]

    for i in range(3):
        value = supports[i] if i < len(supports) else None
        lines.append(f"S{i+1}: {fmt(value)}")

    lines.append("")
    lines.append("🔴 <b>مناطق المقاومة</b>")
    for i in range(3):
        value = resistances[i] if i < len(resistances) else None
        lines.append(f"R{i+1}: {fmt(value)}")

    lines += ["━━━━━━━━━━━━━━━━━━", "🎯 <b>الأهداف السعرية</b>"]
    for i, target in enumerate(targets, 1):
        lines.append(f"🟢 TP{i}: {fmt(target)} ({pct(target):+.2f}%)")

    lines += [
        "━━━━━━━━━━━━━━━━━━",
        f"🛑 <b>وقف الخسارة الفني:</b> {fmt(stop)} {currency} ({pct(stop):+.2f}%)",
        "━━━━━━━━━━━━━━━━━━",
        f"🧠 <b>{title}</b>"
    ]
    lines.extend(f"✅ {escape(str(reason))}" for reason in reasons)
    lines += [
        "━━━━━━━━━━━━━━━━━━",
        "⚠️ المستويات محسوبة من الشموع المستلمة.",
        "⚠️ الأهداف احتمالات فنية وليست ضماناً.",
        "⚠️ التحليل ليس توصية شراء أو بيع."
    ]
    return "\n".join(lines)


# ---------------------- SIGNAL ANALYSIS ---------------------

def allow_signal(symbol, signal, cooldown=1800):
    key = f"{symbol}:{signal}"
    last = sent_signals.get(key, 0)
    return datetime.now().timestamp() - last >= cooldown


async def analyze_rows(session, symbol, market, rows, token, currency):
    rows = normalize_rows(rows)
    if len(rows) < 25:
        log.info("%s %s: candles أقل من 25", market, symbol)
        return

    closes = [x["close"] for x in rows]
    if any(x <= 0 for x in closes[-25:]):
        return

    price = closes[-1]
    previous_price = closes[-2]
    ema9 = ema(closes, 9)
    ema21 = ema(closes, 21)
    rsi = calculate_rsi(closes)
    atr = calculate_atr(rows)
    vwap = calculate_vwap(rows)
    vol_ratio = calculate_volume_ratio(rows)

    if not atr or atr <= 0:
        return

    # مستويات المقاومة تحسب من الشموع السابقة فقط، لتجنب استحالة شرط الاختراق.
    prior_levels = calculate_levels(rows[:-1])
    display_levels = calculate_levels(rows)
    if not prior_levels or not display_levels:
        return

    targets_data = calculate_targets(price, atr, display_levels["supports"])
    if not targets_data:
        return

    score = 0
    reasons = []

    if ema9 is not None and ema21 is not None and ema9 > ema21:
        score += 15
        reasons.append("المتوسط EMA9 أعلى من EMA21")

    if vwap is not None and price > vwap:
        score += 15
        reasons.append("السعر أعلى VWAP")

    if vol_ratio >= MIN_VOLUME_RATIO:
        score += 20
        reasons.append(f"حجم التداول أعلى من المتوسط ×{vol_ratio:.2f}")

    if 50 <= rsi <= 75:
        score += 10
        reasons.append(f"RSI إيجابي {rsi:.1f}")

    prior_resistance = (
        prior_levels["resistances"][0]
        if prior_levels["resistances"] else None
    )
    breakout = (
        prior_resistance is not None
        and price > prior_resistance
        and previous_price <= prior_resistance
    )
    if breakout:
        score += 25
        reasons.append(f"اختراق مقاومة سابقة عند {fmt(prior_resistance)}")

    early = (
        ema9 is not None and price > ema9 and previous_price <= ema9
    )
    if early:
        score += 10
        reasons.append("بداية تحرك فوق EMA9")

    candle_range = rows[-1]["high"] - rows[-1]["low"]
    if candle_range > 0:
        close_position = (price - rows[-1]["low"]) / candle_range
        if close_position >= 0.75:
            score += 5
            reasons.append("إغلاق قريب من قمة الشمعة")

    if score < MIN_SCORE:
        return

    signal = "BREAKOUT" if breakout else "EARLY"
    if not allow_signal(f"{market}:{symbol}", signal):
        return

    message = build_signal_message(
        market, symbol, price, score, rsi, vol_ratio,
        vwap, atr, display_levels, targets_data, reasons, currency
    )
    dashboard = build_dashboard_image(
        market, symbol, price, score, rsi, vol_ratio,
        vwap, atr, display_levels, targets_data, reasons, currency
    )
    caption = (
        f"💀🚀 AI PRO MAX — {symbol}\n"
        f"🟢 قوة الإشارة: {score}/100\n"
        "تفاصيل المستويات والأهداف في الرسالة التالية."
    )
    photo_ok = await telegram_send_photo(session, token, dashboard, caption)
    text_ok = await telegram_send(session, token, message)
    if photo_ok or text_ok:
        sent_signals[f"{market}:{symbol}:{signal}"] = datetime.now().timestamp()
        log.info("تم إرسال لوحة/تنبيه %s %s score=%s photo=%s text=%s",
                 market, symbol, score, photo_ok, text_ok)
    else:
        log.error("تعذر إرسال الصورة والرسالة للرمز %s", symbol)


# ---------------------- TWELVE DATA -------------------------

async def get_json(session, url, params=None, headers=None):
    try:
        async with session.get(
            url, params=params, headers=headers,
            timeout=aiohttp.ClientTimeout(total=25)
        ) as response:
            data = await response.json(content_type=None)
            if response.status != 200:
                log.error("HTTP %s %s: %s", response.status, url, str(data)[:350])
                return None
            if isinstance(data, dict) and (
                data.get("status") == "error" or data.get("code") == 400
                or data.get("message") and not data.get("values")
            ):
                log.error("API returned error for %s: %s", url, str(data)[:350])
                return None
            return data
    except Exception:
        log.exception("HTTP request failed: %s", url)
        return None


async def get_td_candles(session, symbol, market):
    if not TWELVE_API_KEY:
        return None
    params = {
        "symbol": symbol,
        "interval": TD_INTERVAL,
        "outputsize": TD_CANDLES,
        "apikey": TWELVE_API_KEY
    }
    if market == "US":
        params["prepost"] = "true"

    data = await get_json(session, f"{TD_BASE}/time_series", params=params)
    if not isinstance(data, dict) or not isinstance(data.get("values"), list):
        log.warning("Twelve Data returned no candles for %s: %s",
                    symbol, str(data)[:250])
        return None
    return list(reversed(data["values"]))


async def scan_td_market(session, symbols, market):
    token = US_TOKEN if market == "US" else CRYPTO_TOKEN
    semaphore = asyncio.Semaphore(2)

    async def worker(symbol):
        async with semaphore:
            try:
                rows = await get_td_candles(session, symbol, market)
                if rows:
                    await analyze_rows(
                        session, symbol, market, rows, token, "USD"
                    )
            except Exception:
                log.exception("Worker failed: %s %s", market, symbol)

    await asyncio.gather(*(worker(s) for s in symbols))


# ------------------------- SAHMK ----------------------------
# تنبيه: أبقينا مسارات SAHMK الموجودة في نسختك السابقة كما هي.
# إذا كانت غير مطابقة لتوثيق حسابك فستظهر رسالة HTTP/API واضحة في Railway Logs.

async def get_sahmk_history(session, symbol):
    if not SAHMK_API_KEY:
        return None

    headers = {"X-API-Key": SAHMK_API_KEY}
    today = datetime.now(ZoneInfo("Asia/Riyadh")).date()
    start = today - timedelta(days=180)
    params = {
        "interval": "1d",
        "from": start.isoformat(),
        "to": today.isoformat(),
        "limit": 100,
        "offset": 0
    }

    data = await get_json(
        session, f"{SAHMK_BASE}/historical/{symbol}/",
        params=params, headers=headers
    )
    if not isinstance(data, dict):
        return None

    rows = data.get("data")
    if isinstance(rows, dict):
        rows = rows.get("results") or rows.get("items") or rows.get("candles")
    if not isinstance(rows, list):
        log.warning("SAHMK history format not recognized for %s: %s",
                    symbol, str(data)[:350])
        return None
    return rows


async def get_sahmk_market_list(session, endpoint):
    if not SAHMK_API_KEY:
        return []
    headers = {"X-API-Key": SAHMK_API_KEY}
    data = await get_json(
        session, f"{SAHMK_BASE}/market/{endpoint}/",
        params={"limit": 30, "market": "TASI"},
        headers=headers
    )
    if not isinstance(data, dict):
        return []
    for key in ("data", "results", "gainers", "leaders", "stocks", "items"):
        value = data.get(key)
        if isinstance(value, list):
            return value
    log.warning("SAHMK market list format not recognized (%s): %s",
                endpoint, str(data)[:350])
    return []


async def scan_tasi(session):
    if not SAHMK_API_KEY:
        log.warning("SAHMK_API_KEY missing — TASI scan skipped")
        return

    gainers, volume = await asyncio.gather(
        get_sahmk_market_list(session, "gainers"),
        get_sahmk_market_list(session, "volume")
    )

    selected = {}
    for item in gainers + volume:
        if not isinstance(item, dict):
            continue
        symbol = str(item.get("symbol") or item.get("ticker") or "").strip()
        if symbol:
            selected[symbol] = item

    log.info("TASI symbols selected: %s", len(selected))
    semaphore = asyncio.Semaphore(2)

    async def worker(symbol):
        async with semaphore:
            try:
                rows = await get_sahmk_history(session, symbol)
                if rows:
                    await analyze_rows(
                        session, symbol, "السوق السعودي",
                        rows, TASI_TOKEN, "SAR"
                    )
            except Exception:
                log.exception("TASI worker failed: %s", symbol)

    await asyncio.gather(*(worker(s) for s in selected))


# --------------------------- MAIN ---------------------------

async def main():
    if not CHAT_ID:
        raise RuntimeError("CHAT_ID غير موجود في Railway Variables")
    if not TWELVE_API_KEY:
        raise RuntimeError("TWELVE_DATA_API_KEY أو TWELVEDATA_API_KEY غير موجود")

    if not US_TOKEN:
        log.warning("US_TOKEN missing — US alerts will not be sent")
    if not CRYPTO_TOKEN:
        log.warning("CRYPTO_TOKEN missing — crypto alerts will not be sent")
    if not SAHMK_API_KEY:
        log.warning("SAHMK_API_KEY missing — TASI scanning is disabled")

    log.info(
        "AI PRO MAX V4 started | US=%s | CRYPTO=%s | interval=%s",
        len(US_SYMBOLS), len(CRYPTO_SYMBOLS), TD_INTERVAL
    )

    connector = aiohttp.TCPConnector(limit=10, ttl_dns_cache=300)
    timeout = aiohttp.ClientTimeout(total=30)

    async with aiohttp.ClientSession(
        connector=connector, timeout=timeout
    ) as session:
        last_tasi_scan = 0.0

        while True:
            started = datetime.now().timestamp()
            try:
                if US_SYMBOLS:
                    await scan_td_market(session, US_SYMBOLS, "US")
                if CRYPTO_SYMBOLS:
                    await scan_td_market(session, CRYPTO_SYMBOLS, "CRYPTO")

                now = datetime.now().timestamp()
                if now - last_tasi_scan >= TASI_SCAN_SECONDS:
                    await scan_tasi(session)
                    last_tasi_scan = now

            except Exception:
                log.exception("Main scan cycle failed")

            elapsed = datetime.now().timestamp() - started
            wait = max(15, SCAN_SECONDS - elapsed)
            log.info("Scan cycle finished; next scan in %.0f seconds", wait)
            await asyncio.sleep(wait)


if __name__ == "__main__":
    asyncio.run(main())