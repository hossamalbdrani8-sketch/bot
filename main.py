
# ============================================================
# 💀🚀 AI PRO MAX SIGNAL BOT v3.0 (TASI, US, CRYPTO)
# ============================================================
import os, time, requests, telebot
from flask import Flask
from datetime import datetime, timedelta
from threading import Thread, Lock

# ----------------------------------------------
# ⚙️ الإعدادات
# ----------------------------------------------
TASI_TOKEN   = os.environ.get("TASI_TOKEN")
US_TOKEN     = os.environ.get("US_TOKEN")
CRYPTO_TOKEN = os.environ.get("CRYPTO_TOKEN")
API_KEY      = os.environ.get("API")
PORT         = int(os.environ.get("PORT", 3000))

SCAN_INTERVAL_MIN  = 30          # دورة كل 30 دقيقة
BATCH_SIZE_US      = 500         # 500 سهم أمريكي لكل دورة
BATCH_SIZE_TASI    = 100         # 100 سهم سعودي لكل دورة
BATCH_SIZE_CRYPTO  = 50          # 50 عملة رقمية لكل دورة
US_MIN_PRICE       = 0.20
TASI_MIN_PRICE     = 0.01
ALERT_COOLDOWN_HRS = 4           # منع تكرار التنبيه لنفس السهم قبل 4 ساعات

# ----------------------------------------------
# 🤖 البوتات + Flask
# ----------------------------------------------
app = Flask(__name__)
tasi_bot   = telebot.TeleBot(TASI_TOKEN, threaded=False)
us_bot     = telebot.TeleBot(US_TOKEN, threaded=False)
crypto_bot = telebot.TeleBot(CRYPTO_TOKEN, threaded=False)

tasi_users, us_users, crypto_users = set(), set(), set()

# الحالة (Cache + Alert dedup)
symbol_cache   = {"US": [], "SR": [], "CC": []}
symbol_fetched = {"US": 0, "SR": 0, "CC": 0}
scan_index     = {"US": 0, "SR": 0, "CC": 0}
alert_history  = {}
state_lock     = Lock()

print("🚀 AI PRO MAX SIGNAL BOT v3.0 STARTING")
print(f"✅ Tokens: TASI={bool(TASI_TOKEN)} US={bool(US_TOKEN)} CRYPTO={bool(CRYPTO_TOKEN)} API={bool(API_KEY)}")

# ----------------------------------------------
# 📐 المؤشرات الفنية
# ----------------------------------------------
def ema(prices, period):
    if len(prices) < period: return prices[-1]
    m = 2 / (period + 1)
    e = sum(prices[:period]) / period
    for p in prices[period:]:
        e = (p - e) * m + e
    return e

def rsi(prices, period=14):
    if len(prices) < period + 1: return 50.0
    gains, losses = 0.0, 0.0
    for i in range(1, len(prices)):
        d = prices[i] - prices[i-1]
        if d > 0: gains += d
        else: losses -= d
    if losses == 0: return 100.0
    rs = (gains / period) / (losses / period)
    return 100 - (100 / (1 + rs))

def atr(highs, lows, closes, period=14):
    if len(highs) < period + 1: return 0.0
    trs = []
    for i in range(1, len(highs)):
        trs.append(max(highs[i]-lows[i], abs(highs[i]-closes[i-1]), abs(lows[i]-closes[i-1])))
    return sum(trs[-period:]) / period

# ----------------------------------------------
# 📡 جلب البيانات من EODHD
# ----------------------------------------------
def get_symbol_list(exchange):
    url = f"https://eodhd.com/api/exchange-symbol-list/{exchange}?api_token={API_KEY}&fmt=json"
    try:
        r = requests.get(url, timeout=30)
        if r.status_code != 200:
            print(f"❌ Symbols {exchange}: HTTP {r.status_code}")
            return []
        data = r.json()
        if not isinstance(data, list): return []
        out = []
        for it in data:
            t = str(it.get("Type", "")).lower()
            if "stock" in t or "common" in t or exchange == "CC":
                code = str(it.get("Code", "")).strip()
                name = str(it.get("Name", code)).strip()
                if code: out.append((code, name))
        print(f"✅ Fetched {len(out)} symbols for {exchange}")
        return out
    except Exception as e:
        print(f"❌ Symbol list error {exchange}: {e}")
        return []

def get_history(symbol, exchange):
    sym = f"{symbol.replace('.', '-')}.{exchange}"
    url = f"https://eodhd.com/api/eod/{sym}?api_token={API_KEY}&fmt=json&period=d&limit=80"
    try:
        r = requests.get(url, timeout=15)
        if r.status_code != 200: return None
        d = r.json()
        return d if isinstance(d, list) and len(d) >= 50 else None
    except Exception:
        return None

def get_news(symbol, exchange, limit=2):
    sym = f"{symbol.replace('.', '-')}.{exchange}"
    url = f"https://eodhd.com/api/news?api_token={API_KEY}&s={sym}&limit={limit}&fmt=json"
    try:
        r = requests.get(url, timeout=10)
        if r.status_code != 200: return []
        return r.json() if isinstance(r.json(), list) else []
    except Exception:
        return []

# ----------------------------------------------
# 🧠 التحليل وبناء الرسالة
# ----------------------------------------------
def build_signal(symbol, name, exchange, market_title, market_flag, min_price):
    data = get_history(symbol, exchange)
    if not data: return None

    closes  = [float(d["close"])  for d in data if d.get("close")]
    highs   = [float(d["high"])   for d in data if d.get("high")]
    lows    = [float(d["low"])    for d in data if d.get("low")]
    volumes = [float(d["volume"]) for d in data if d.get("volume")]

    if len(closes) < 50: return None
    price = closes[-1]
    if price < min_price: return None

    prev = closes[-2]
    chg  = ((price - prev) / prev) * 100

    e8, e21, e50 = ema(closes, 8), ema(closes, 21), ema(closes, 50)
    r_val = rsi(closes, 14)
    a_val = atr(highs, lows, closes, 14)

    # قوة الإشارة
    bp = 50
    if price > e8:  bp += 10
    if price > e21: bp += 10
    if price > e50: bp += 10
    if e8 > e21 > e50: bp += 10
    if r_val > 55: bp += 5
    if r_val > 75: bp -= 15
    if r_val < 30: bp += 15
    bp = max(5, min(95, bp))
    sp = 100 - bp

    # تحديد الاتجاه
    is_up = bp > 50
    if bp >= 75:    signal_text = "🟢 شراء قوي"
    elif bp >= 60:  signal_text = "🟢 شراء"
    elif bp <= 25:  signal_text = "🔴 بيع قوي"
    elif bp <= 40:  signal_text = "🔴 بيع"
    else:           signal_text = "⚪ حياد"

    support    = min(lows[-20:])
    resistance = max(highs[-20:])
    vol_avg    = sum(volumes[-20:]) / max(1, len(volumes[-20:]))
    vol_ratio  = volumes[-1] / vol_avg if vol_avg > 0 else 1.0

    # الأهداف + وقف الخسارة
    targets = []
    for i in range(1, 9):
        if is_up:
            tp  = price + a_val * i * 0.6
            pct = ((tp - price) / price) * 100
            targets.append(("🟢", i, tp, pct))
        else:
            tp  = price - a_val * i * 0.6
            pct = ((tp - price) / price) * 100
            targets.append(("🔴", i, tp, pct))

    stop_loss = price - a_val * 1.5 if is_up else price + a_val * 1.5
    sl_pct    = ((stop_loss - price) / price) * 100

    trend_icon = "📈 صاعد قوي" if is_up else "📉 هابط قوي"
    color_bar  = "🟢" if is_up else "🔴"

    # الأخبار
    news = get_news(symbol, exchange, limit=2)

    # بناء الرسالة
    msg  = f"💀🚀 <b>AI PRO MAX SIGNAL</b>\n\n"
    msg += f"📊 <b>{market_flag} {market_title}</b>\n"
    msg += f"<b>{symbol}.{exchange}</b>\n"
    msg += f"{name}\n\n"
    msg += f"<b>{signal_text}</b>   {color_bar * (1 if is_up else 1)}\n\n"

    msg += f"<b>السعر:</b> {price:.2f}      | <b>EMA 8:</b> {e8:.2f}      | <b>الدعم:</b> {support:.2f}\n"
    msg += f"<b>التغير:</b> {chg:+.2f}%   | <b>EMA 21:</b> {e21:.2f}    | <b>المقاومة:</b> {resistance:.2f}\n"
    msg += f"<b>قوة الإشارة:</b> {bp:.0f}/100 | <b>EMA 50:</b> {e50:.2f}    | <b>الاتجاه:</b> {trend_icon}\n"
    msg += f"<b>قوة الشراء:</b> {bp:.0f}%   | <b>RSI 14:</b> {r_val:.1f}\n"
    msg += f"<b>قوة البيع:</b> {sp:.0f}%    | <b>ATR 14:</b> {a_val:.2f}\n"
    msg += f"<b>الحجم:</b> {vol_ratio:.1f}x       | <b>وقف الخسارة:</b> {stop_loss:.2f} ({sl_pct:+.1f}%)\n\n"

    msg += f"🎯 <b>أهداف ATR الثمانية:</b>\n"
    line1 = " | ".join([f"{t[0]}TP{t[1]} {t[2]:.2f} ({t[3]:+.1f}%)" for t in targets[:4]])
    line2 = " | ".join([f"{t[0]}TP{t[1]} {t[2]:.2f} ({t[3]:+.1f}%)" for t in targets[4:]])
    msg += f"{line1}\n{line2}\n"

    if news:
        msg += "\n📰 <b>آخر الأخبار:</b>\n"
        for n in news[:2]:
            title = n.get("title", "")[:80]
            msg += f"• {title}\n"

    msg += f"\n🕒 {datetime.now().strftime('%I:%M %p')}"
    return msg, is_up

# ----------------------------------------------
# 🔄 منطق المسح مع التقسيم (Batches)
# ----------------------------------------------
def should_alert(symbol, exchange):
    key = f"{symbol}.{exchange}"
    now = datetime.now()
    last = alert_history.get(key)
    if last and (now - last) < timedelta(hours=ALERT_COOLDOWN_HRS):
        return False
    alert_history[key] = now
    return True

def get_next_batch(market, size):
    """يرجع دفعة أسهم جديدة من الكاش مع تحديث المؤشر الدوري"""
    if not symbol_cache[market]:
        exch = {"US": "US", "SR": "SR", "CC": "CC"}[market]
        symbol_cache[market] = get_symbol_list(exch)
        symbol_fetched[market] = time.time()

    lst = symbol_cache[market]
    if not lst: return []
    start = scan_index[market] % len(lst)
    end   = min(start + size, len(lst))
    batch = lst[start:end]
    scan_index[market] = (end) % len(lst)
    return batch

def scan_market(market):
    if market == "TASI":
        users, exch, title, flag, minp, size, bot = tasi_users, "SR", "السوق السعودي (TASI)", "🇸🇦", TASI_MIN_PRICE, BATCH_SIZE_TASI, tasi_bot
    elif market == "US":
        users, exch, title, flag, minp, size, bot = us_users, "US", "السوق الأمريكي (US)", "🇺🇸", US_MIN_PRICE, BATCH_SIZE_US, us_bot
    else:
        users, exch, title, flag, minp, size, bot = crypto_users, "CC", "العملات الرقمية (CRYPTO)", "🪙", 0.0, BATCH_SIZE_CRYPTO, crypto_bot

    if not users: return

    batch = get_next_batch(exch, size)
    print(f"🔍 [{market}] Scanning {len(batch)} symbols (idx={scan_index[exch]})")

    signals_found = 0
    for symbol, name in batch:
        try:
            result = build_signal(symbol, name, exch, title, flag, minp)
            if not result: 
                time.sleep(0.15); continue
            msg, _ = result
            if not should_alert(symbol, exch):
                continue
            for chat_id in list(users):
                try:
                    bot.send_message(chat_id, msg, parse_mode="HTML")
                    time.sleep(0.2)
                except Exception as e:
                    print(f"Send error: {e}")
            signals_found += 1
        except Exception as e:
            print(f"Err {symbol}: {e}")
        time.sleep(0.15)
    print(f"✅ [{market}] Done. Sent {signals_found} alerts.")

def scheduler():
    while True:
        try:
            scan_market("TASI")
            scan_market("US")
            scan_market("CRYPTO")
        except Exception as e:
            print(f"Scheduler error: {e}")
        time.sleep(SCAN_INTERVAL_MIN * 60)

# ----------------------------------------------
# 🤖 معالجة الأوامر
# ----------------------------------------------
def setup_bot(bot, users, market, welcome):
    @bot.message_handler(commands=["start", "scan"])
    def handler(message):
        users.add(message.chat.id)
        bot.send_message(message.chat.id, welcome, parse_mode="HTML")
        Thread(target=scan_market, args=(market,), daemon=True).start()

setup_bot(tasi_bot,   tasi_users,   "TASI",   "🟢 مرحباً! بوت السوق السعودي (AI PRO MAX)\n🔍 بدأ الفحص التلقائي الشامل ...")
setup_bot(us_bot,     us_users,     "US",     "🟢 مرحباً! بوت الأسهم الأمريكية (AI PRO MAX)\n🔍 بدأ الفحص التلقائي الشامل ...")
setup_bot(crypto_bot, crypto_users, "CRYPTO", "🟢 مرحباً! بوت العملات الرقمية (AI PRO MAX)\n🔍 بدأ الفحص التلقائي الشامل ...")

# ----------------------------------------------
# 🌐 Flask + نقطة البداية
# ----------------------------------------------
@app.route("/")
def home(): return "🚀 AI PRO MAX SIGNAL BOT v3.0 Online"

def run_flask(): app.run(host="0.0.0.0", port=PORT)

if __name__ == "__main__":
    Thread(target=run_flask, daemon=True).start()
    Thread(target=scheduler, daemon=True).start()
    print("✅ All bots polling...")
    Thread(target=tasi_bot.polling,   kwargs={"none_stop": True}, daemon=True).start()
    Thread(target=us_bot.polling,     kwargs={"none_stop": True}, daemon=True).start()
    Thread(target=crypto_bot.polling, kwargs={"none_stop": True}, daemon=True).start()
    while True: time.sleep(1)