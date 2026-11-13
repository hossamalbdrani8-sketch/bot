# ============================================================
# AI PRO MAX — MARKET HUNTER V5.1
# US | CRYPTO | TASI — Telegram startup + 24/7 worker
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
SAHMK_BASE = os.getenv(
    "SAHMK_BASE", "https://api.sahmk.sa/api/v1"
).rstrip("/")

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

SCAN_SECONDS = max(30, int(os.getenv("SCAN_SECONDS", "300")))
TASI_SCAN_SECONDS = max(300, int(os.getenv("TASI_SCAN_SECONDS", "1800")))
HEARTBEAT_SECONDS = max(3600, int(os.getenv("HEARTBEAT_SECONDS", "21600")))
MIN_SCORE = int(os.getenv("MIN_SCORE", "65"))
MIN_VOLUME_RATIO = float(os.getenv("MIN_VOLUME_RATIO", "1.5"))
MIN_US_PRICE = float(os.getenv("MIN_US_PRICE", "0.15"))
TD_INTERVAL = os.getenv("TD_INTERVAL", "5min")
TD_CANDLES = int(os.getenv("TD_CANDLES", "100"))
TD_BASE = "https://api.twelvedata.com"

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s | %(levelname)s | %(message)s"
)
log = logging.getLogger("AI_PRO_MAX")
sent_signals = {}


# ------------------------- HELPERS -------------------------

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


def price_fmt(value):
    if value is None:
        return "—"
    return f"{value:,.4f}" if abs(value) < 1 else f"{value:,.2f}"


def rtl(value):
    try:
        return get_display(arabic_reshaper.reshape(str(value)))
    except Exception:
        return str(value)


def dashboard_font(size, bold=False):
    root = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(
            root, "fonts",
            "NotoKufiArabic-Bold.ttf" if bold else "NotoKufiArabic-Regular.ttf"
        ),
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
        if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf"
        if bold else "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def normalize_rows(rows):
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
        lower = {str(k).lower(): v for k, v in row.items()}
        item = {}
        for target, keys in aliases.items():
            found = next((lower[k] for k in keys if k in lower), None)
            item[target] = num(found)

        if item["close"] <= 0:
            continue
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
        high, low = rows[i]["high"], rows[i]["low"]
        prev_close = rows[i - 1]["close"]
        tr_values.append(max(
            high - low, abs(high - prev_close), abs(low - prev_close)
        ))
    return sum(tr_values[-period:]) / period


def calculate_vwap(rows):
    total_value = total_volume = 0.0
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


def calculate_levels(rows):
    if len(rows) < 25:
        return None
    highs = [x["high"] for x in rows]
    lows = [x["low"] for x in rows]
    price = rows[-1]["close"]
    pivot_highs, pivot_lows = [], []

    for i in range(max(2, len(rows) - 80), len(rows) - 2):
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
    stop = price - 1.5 * atr
    if supports:
        stop = min(stop, supports[0] - 0.15 * atr)
    return {"stop": stop, "targets": [price + atr * n for n in range(1, 9)]}


# ------------------------- TELEGRAM -------------------------

async def telegram_send(session, token, message):
    if not token or not CHAT_ID:
        log.error("Telegram token or CHAT_ID is missing")
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


async def send_startup_messages(session):
    """Send a startup confirmation through each configured bot token."""
    tokens = list(dict.fromkeys(
        token for token in (US_TOKEN, CRYPTO_TOKEN, TASI_TOKEN) if token
    ))
    if not tokens:
        log.error("No Telegram bot token configured")
        return None

    now = datetime.now(ZoneInfo("Asia/Riyadh")).strftime("%Y-%m-%d %H:%M:%S")
    welcome = (
        "💀🚀 <b>AI PRO MAX — MARKET HUNTER V5.1</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "🟢 <b>تم تشغيل خدمة البوت</b>\n"
        "⏰ نمط التشغيل: 24/7 ما دامت خدمة الاستضافة تعمل\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "🇺🇸 السوق الأمريكي: قائمة الرموز المحددة في الإعدادات\n"
        f"💲 الحد الأدنى المطبق: {MIN_US_PRICE:.2f} USD\n"
        "🪙 العملات الرقمية: قائمة الرموز المحددة في الإعدادات\n"
        "🇸🇦 السوق السعودي: عبر SAHMK عند توفر المفتاح\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"🔄 دورة الفحص: كل {SCAN_SECONDS} ثانية\n"
        f"🔄 فحص تاسي: كل {TASI_SCAN_SECONDS} ثانية\n"
        f"📡 تقرير نبض التشغيل: كل {HEARTBEAT_SECONDS // 3600} ساعات\n"
        f"🕒 توقيت الرياض: {now}\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "ℹ️ هذه رسالة تأكيد تشغيل وليست إشارة تداول."
    )

    working_token = None
    for token in tokens:
        ok = await telegram_send(session, token, welcome)
        if ok and working_token is None:
            working_token = token

    if working_token:
        log.info("Startup message delivered")
    else:
        log.error("Startup message could not be delivered")
    return working_token


async def send_heartbeat(session, token):
    now = datetime.now(ZoneInfo("Asia/Riyadh")).strftime("%Y-%m-%d %H:%M:%S")
    message = (
        "💀🚀 <b>AI PRO MAX — نبض التشغيل</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "🟢 الخدمة ما زالت تعمل\n"
        "⏰ نمط التشغيل: 24/7\n"
        "🌍 الأسواق: US | CRYPTO | TASI\n"
        f"🕒 {now} — توقيت الرياض\n"
        "━━━━━━━━━━━━━━━━━━"
    )
    return await telegram_send(session, token, message)


async def telegram_send_photo(session, token, photo, caption):
    if not token or not CHAT_ID:
        return False
    url = f"https://api.telegram.org/bot{token}/sendPhoto"
    form = aiohttp.FormData()
    form.add_field("chat_id", str(CHAT_ID))
    form.add_field("caption", caption[:900])
    form.add_field(
        "photo", photo.getvalue(),
        filename="ai_pro_max_signal.png",
        content_type="image/png"
    )
    try:
        async with session.post(
            url, data=form, timeout=aiohttp.ClientTimeout(total=30)
        ) as response:
            result = await response.json(content_type=None)
            if response.status == 200 and result.get("ok") is True:
                return True
            log.error("Telegram photo HTTP %s: %s", response.status, str(result)[:500])
    except Exception:
        log.exception("Telegram photo send failed")
    return False


# ------------------------- DASHBOARD -------------------------

def build_dashboard_image(
    market, symbol, price, score, rsi, vol_ratio, vwap, atr,
    levels, targets_data, reasons, currency, current_volume=0, liquidity=0
):
    width, height = 1600, 2200
    image = Image.new("RGB", (width, height), (7, 12, 18))
    draw = ImageDraw.Draw(image)

    green = (0, 230, 140)
    green_dim = (0, 125, 91)
    red = (255, 75, 90)
    white = (238, 245, 248)
    muted = (145, 164, 177)
    gold = (255, 195, 70)
    cyan = (69, 205, 255)
    panel = (15, 24, 33)
    panel2 = (10, 18, 26)

    title_font = dashboard_font(60, True)
    head_font = dashboard_font(43, True)
    body_font = dashboard_font(36, True)
    small_font = dashboard_font(29)
    value_font = dashboard_font(38, True)
    price_font = dashboard_font(75, True)

    def rounded(box, fill=panel, outline=(35, 57, 70), radius=24):
        draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=3)

    def left(x, y, value, f=body_font, color=white):
        draw.text((x, y), str(value), font=f, fill=color)

    def right(x, y, value, f=body_font, color=white):
        draw.text((x, y), rtl(value), font=f, fill=color, anchor="ra")

    rounded((25, 25, width-25, 185), (10, 27, 35), green_dim)
    left(65, 55, "AI PRO MAX", title_font, green)
    right(width-65, 65, "صائد الفرص — MARKET HUNTER", head_font, white)
    left(70, 125, "LIVE SIGNAL  •  US / TASI / CRYPTO", small_font, muted)

    rounded((25, 210, width-25, 520), (19, 31, 41), green_dim)
    right(width-65, 235, f"{market} | {symbol}", head_font, cyan)
    left(70, 315, price_fmt(price), price_font, green)
    left(75, 410, currency, body_font, muted)
    right(width-65, 330, "قوة الإشارة", head_font, gold)
    right(width-65, 395, f"{score}/100", price_font, green)

    x1, y1, x2 = 750, 465, width-65
    draw.rounded_rectangle((x1, y1, x2, y1+25), radius=12, fill=(42, 57, 66))
    draw.rounded_rectangle(
        (x1, y1, x1+int((x2-x1)*max(0, min(score, 100))/100), y1+25),
        radius=12, fill=green
    )

    rounded((25, 550, width-25, 1030))
    right(width-65, 575, "الحجم والسيولة والنشاط", head_font, gold)

    metrics = [
        ("VOLUME", f"{current_volume:,.0f}", cyan),
        ("LIQUIDITY*", f"{liquidity:,.2f} {currency}", green),
        ("ACTIVITY", f"x{vol_ratio:.2f}", gold),
        ("RSI", f"{rsi:.1f}", cyan),
        ("VWAP", price_fmt(vwap) if vwap is not None else "—", white),
        ("ATR", price_fmt(atr) if atr is not None else "—", gold),
    ]
    positions = [(65, 665), (575, 665), (1085, 665),
                 (65, 845), (575, 845), (1085, 845)]
    for (label, value, color), (x, y) in zip(metrics, positions):
        rounded((x, y, x+450, y+145), panel2, (30, 65, 75), 18)
        left(x+20, y+15, label, small_font, muted)
        left(x+20, y+67, value, value_font, color)

    rounded((25, 1060, width-25, 1390))
    right(width-65, 1085, "الدعم والمقاومة", head_font, gold)
    supports = levels.get("supports", [])
    resistances = levels.get("resistances", [])
    for i in range(3):
        y = 1170 + i*65
        sv = price_fmt(supports[i]) if i < len(supports) else "—"
        rv = price_fmt(resistances[i]) if i < len(resistances) else "—"
        left(70, y, f"S{i+1}  {sv}", body_font, green)
        right(width-70, y, f"R{i+1}  {rv}", body_font, red)

    rounded((25, 1420, width-25, 1970))
    right(width-65, 1445, "الأهداف السعرية TP1 — TP8", head_font, gold)
    targets = targets_data.get("targets", [])
    for i, target in enumerate(targets[:8]):
        col, row = i % 2, i // 2
        x = 65 if col == 0 else 825
        y = 1520 + row*105
        rounded((x, y, x+710, y+82), (10, 26, 27), (0, 91, 69), 15)
        left(x+20, y+18, f"TP{i+1}", body_font, green)
        right(x+685, y+10, price_fmt(target), body_font, white)
        change = ((target-price)/price*100) if price > 0 else 0
        right(x+685, y+48, f"{change:+.2f}%", small_font, green)

    stop = targets_data.get("stop")
    rounded((25, 1995, width-25, 2110), (38, 15, 22), (120, 40, 48))
    right(width-65, 2025, f"وقف الخسارة الفني: {price_fmt(stop)} {currency}", head_font, red)

    footer = datetime.now(ZoneInfo("Asia/Riyadh")).strftime("%Y-%m-%d %H:%M:%S")
    right(width-45, 2140, f"* قيمة تداول الشمعة الأخيرة تقديرياً | {footer} الرياض", small_font, muted)

    output = io.BytesIO()
    image.save(output, format="PNG", optimize=True)
    output.seek(0)
    return output


# ------------------------- SIGNAL ANALYSIS -------------------------

def allow_signal(key, cooldown=1800):
    return datetime.now().timestamp() - sent_signals.get(key, 0) >= cooldown


async def analyze_rows(session, symbol, market, rows, token, currency):
    rows = normalize_rows(rows)
    if len(rows) < 25:
        return

    closes = [x["close"] for x in rows]
    if any(x <= 0 for x in closes[-25:]):
        return

    price, previous_price = closes[-1], closes[-2]
    if market == "US" and price < MIN_US_PRICE:
        return

    ema9, ema21 = ema(closes, 9), ema(closes, 21)
    rsi = calculate_rsi(closes)
    atr = calculate_atr(rows)
    vwap = calculate_vwap(rows)
    vol_ratio = calculate_volume_ratio(rows)

    if not atr or atr <= 0:
        return

    prior_levels = calculate_levels(rows[:-1])
    display_levels = calculate_levels(rows)
    if not prior_levels or not display_levels:
        return

    targets_data = calculate_targets(price, atr, display_levels["supports"])
    if not targets_data:
        return

    score, reasons = 0, []

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

    prior_resistance = prior_levels["resistances"][0] if prior_levels["resistances"] else None
    breakout = (
        prior_resistance is not None
        and price > prior_resistance
        and previous_price <= prior_resistance
    )
    if breakout:
        score += 25
        reasons.append(f"اختراق مقاومة سابقة عند {fmt(prior_resistance)}")

    if ema9 is not None and price > ema9 and previous_price <= ema9:
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
    key = f"{market}:{symbol}:{signal}"
    if not allow_signal(key):
        return

    current_volume = rows[-1]["volume"]
    liquidity = price * current_volume

    dashboard = build_dashboard_image(
        market, symbol, price, score, rsi, vol_ratio,
        vwap, atr, display_levels, targets_data, reasons,
        currency, current_volume, liquidity
    )
    caption = (
        f"💀🚀 AI PRO MAX — {symbol}\n"
        f"🟢 قوة الإشارة: {score}/100\n"
        "تفاصيل الدعم والمقاومة والأهداف داخل اللوحة.\n"
        "⚠️ ليست توصية استثمارية."
    )

    photo_ok = await telegram_send_photo(session, token, dashboard, caption)
    if photo_ok:
        sent_signals[key] = datetime.now().timestamp()
        log.info("Signal sent: %s %s score=%s", market, symbol, score)


# ------------------------- TWELVE DATA SCANNERS -------------------------

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
        log.warning("No Twelve Data candles for %s: %s", symbol, str(data)[:200])
        return None
    return list(reversed(data["values"]))


async def get_json(session, url, params=None, headers=None):
    try:
        async with session.get(
            url, params=params, headers=headers,
            timeout=aiohttp.ClientTimeout(total=25)
        ) as response:
            data = await response.json(content_type=None)
            if response.status != 200:
                log.error("HTTP %s %s: %s", response.status, url, str(data)[:300])
                return None
            if isinstance(data, dict) and (
                data.get("status") == "error"
                or data.get("code") == 400
                or (data.get("message") and not data.get("values"))
            ):
                log.error("API error %s: %s", url, str(data)[:300])
                return None
            return data
    except Exception:
        log.exception("HTTP request failed: %s", url)
        return None


async def scan_td_market(session, symbols, market):
    token = US_TOKEN if market == "US" else CRYPTO_TOKEN
    semaphore = asyncio.Semaphore(2)

    async def worker(symbol):
        async with semaphore:
            try:
                rows = await get_td_candles(session, symbol, market)
                if rows:
                    await analyze_rows(session, symbol, market, rows, token, "USD")
            except Exception:
                log.exception("Worker failed: %s %s", market, symbol)

    await asyncio.gather(*(worker(s) for s in symbols))


# ------------------------- SAHMK TASI -------------------------

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
    return rows if isinstance(rows, list) else None


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
    log.warning("Unrecognized SAHMK list response for %s", endpoint)
    return []


async def scan_tasi(session):
    if not SAHMK_API_KEY:
        log.warning("SAHMK_API_KEY missing — TASI skipped")
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

    log.info("TASI selected symbols: %s", len(selected))
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


# ------------------------- MAIN — 24/7 -------------------------

async def main():
    if not CHAT_ID:
        raise RuntimeError("CHAT_ID غير موجود في Railway Variables")

    connector = aiohttp.TCPConnector(limit=15, ttl_dns_cache=300)
    timeout = aiohttp.ClientTimeout(total=40)

    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
        # Send startup message before checking market data credentials.
        alert_token = await send_startup_messages(session)
        if not alert_token:
            raise RuntimeError(
                "لم تصل رسالة الترحيب. تحقق من CHAT_ID والتوكن واضغط Start في البوت."
            )

        if not TWELVE_API_KEY:
            await telegram_send(
                session, alert_token,
                "🔴 <b>خطأ إعداد:</b> مفتاح Twelve Data غير موجود. "
                "أضف TWELVE_DATA_API_KEY في Railway Variables."
            )
            raise RuntimeError("TWELVE_DATA_API_KEY is missing")

        if not US_TOKEN:
            log.warning("US_TOKEN missing — US Telegram signals disabled")
        if not CRYPTO_TOKEN:
            log.warning("CRYPTO_TOKEN missing — crypto Telegram signals disabled")
        if not SAHMK_API_KEY:
            log.warning("SAHMK_API_KEY missing — TASI scanning disabled")

        last_tasi_scan = 0.0
        last_heartbeat = datetime.now().timestamp()
        last_error_notice = 0.0

        log.info("AI PRO MAX V5.1 started — continuous worker loop")

        while True:
            started = datetime.now().timestamp()
            try:
                if US_SYMBOLS and US_TOKEN:
                    await scan_td_market(session, US_SYMBOLS, "US")
                if CRYPTO_SYMBOLS and CRYPTO_TOKEN:
                    await scan_td_market(session, CRYPTO_SYMBOLS, "CRYPTO")

                now = datetime.now().timestamp()
                if now - last_tasi_scan >= TASI_SCAN_SECONDS:
                    if SAHMK_API_KEY:
                        await scan_tasi(session)
                    last_tasi_scan = now

            except Exception as error:
                log.exception("Main scan cycle failed")
                now = datetime.now().timestamp()
                if now - last_error_notice >= 900:
                    await telegram_send(
                        session, alert_token,
                        "⚠️ <b>حدث خطأ في دورة الفحص</b>\n"
                        f"<code>{escape(str(error)[:450])}</code>\n"
                        "سيواصل النظام المحاولة في الدورة التالية."
                    )
                    last_error_notice = now

            now = datetime.now().timestamp()
            if now - last_heartbeat >= HEARTBEAT_SECONDS:
                await send_heartbeat(session, alert_token)
                last_heartbeat = now

            elapsed = datetime.now().timestamp() - started
            wait = max(15, SCAN_SECONDS - elapsed)
            log.info("Cycle finished; next scan in %.0f seconds", wait)
            await asyncio.sleep(wait)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.warning("AI PRO MAX stopped manually")