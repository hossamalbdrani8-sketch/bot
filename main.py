
# ============================================================
# 💀🚀 AI PRO MAX SIGNAL BOT (TASI, US, CRYPTO) - Python
# ============================================================
import os
import time
import requests
import telebot
from flask import Flask
from datetime import datetime
from threading import Thread

# ----------------------------------------------
# ⚙️ الإعدادات
# ----------------------------------------------
TASI_TOKEN = os.environ.get("TASI_TOKEN")
US_TOKEN = os.environ.get("US_TOKEN")
CRYPTO_TOKEN = os.environ.get("CRYPTO_TOKEN")
API_KEY = os.environ.get("API") # اسم المفتاح كما طلبت
PORT = int(os.environ.get("PORT", 3000))
UPDATE_INTERVAL_MIN = 3

app = Flask(__name__)

# ----------------------------------------------
# 🤖 إعداد البوتات الثلاثة (بدون أي تداخل)
# ----------------------------------------------
tasi_bot = telebot.TeleBot(TASI_TOKEN, threaded=False)
us_bot = telebot.TeleBot(US_TOKEN, threaded=False)
crypto_bot = telebot.TeleBot(CRYPTO_TOKEN, threaded=False)

tasi_users = set()
us_users = set()
crypto_users = set()

print("🚀 STARTING AI PRO MAX SIGNAL BOT (PYTHON VERSION)")
print("✅ TASI_TOKEN:", bool(TASI_TOKEN))
print("✅ US_TOKEN:", bool(US_TOKEN))
print("✅ CRYPTO_TOKEN:", bool(CRYPTO_TOKEN))
print("✅ API Key:", bool(API_KEY))

# ----------------------------------------------
# 🛠️ المؤشرات الفنية (حسابات يدوية)
# ----------------------------------------------
def calc_ema(prices, period):
    if len(prices) < period: return prices[-1]
    mult = 2 / (period + 1)
    ema = prices[0]
    for p in prices[1:]:
        ema = (p * mult) + (ema * (1 - mult))
    return ema

def calc_rsi(prices, period=14):
    if len(prices) < period + 1: return 50.0
    gains, losses = 0, 0
    for i in range(1, len(prices)):
        diff = prices[i] - prices[i-1]
        if diff > 0: gains += diff
        else: losses -= diff
    if losses == 0: return 100.0
    rs = (gains / period) / (losses / period)
    return 100 - (100 / (1 + rs))

def calc_atr(highs, lows, closes, period=14):
    if len(highs) < period + 1: return 0.0
    trs = []
    for i in range(1, len(highs)):
        tr = max(highs[i] - lows[i], abs(highs[i] - closes[i-1]), abs(lows[i] - closes[i-1]))
        trs.append(tr)
    return sum(trs[-period:]) / period

# ----------------------------------------------
# 📡 جلب البيانات من EODHD
# ----------------------------------------------
def get_data(symbol, exchange):
    fmt_symbol = f"{symbol.replace('.', '-')}.{exchange}"
    url = f"https://eodhd.com/api/eod/{fmt_symbol}?api_token={API_KEY}&fmt=json&period=d&limit=60"
    try:
        r = requests.get(url, timeout=15)
        if r.status_code != 200: return None
        data = r.json()
        if not isinstance(data, list) or len(data) < 20: return None
        return data
    except Exception as e:
        print(f"Error fetching {fmt_symbol}: {e}")
        return None

# ----------------------------------------------
# 🧠 التحليل وإنشاء الرسالة
# ----------------------------------------------
def analyze_and_build(symbol, name, exchange, market_title):
    data = get_data(symbol, exchange)
    if not data: return None

    closes = [float(d['close']) for d in data]
    highs = [float(d['high']) for d in data]
    lows = [float(d['low']) for d in data]
    volumes = [float(d['volume']) for d in data]

    price = closes[-1]
    prev = closes[-2] if len(closes) > 1 else price
    change = ((price - prev) / prev) * 100

    ema8 = calc_ema(closes, 8)
    ema21 = calc_ema(closes, 21)
    ema50 = calc_ema(closes, 50)
    rsi = calc_rsi(closes)
    atr = calc_atr(highs, lows, closes)

    # حساب قوة الإشارة
    buy_power = 50
    if price > ema8: buy_power += 10
    if price > ema21: buy_power += 10
    if ema8 > ema21: buy_power += 10
    if rsi > 50: buy_power += 10
    if rsi > 70: buy_power -= 10
    if rsi < 30: buy_power += 15
    buy_power = max(0, min(100, buy_power))
    sell_power = 100 - buy_power

    if buy_power >= 70: signal = "🟢 شراء قوي"
    elif buy_power <= 30: signal = "🔴 بيع قوي"
    elif buy_power > 50: signal = "🟢 شراء"
    else: signal = "🔴 بيع"

    support = min(lows[-20:])
    resistance = max(highs[-20:])
    trend = "📈 صاعد قوي" if buy_power > 50 else "📉 هابط قوي"
    vol_ratio = volumes[-1] / (sum(volumes[-20:]) / 20) if sum(volumes[-20:]) > 0 else 1.0

    # أهداف ATR
    targets = []
    for i in range(1, 9):
        if buy_power > 50:
            tp = price + (atr * i * 0.6)
            pct = ((tp - price) / price) * 100
        else:
            tp = price - (atr * i * 0.6)
            pct = ((tp - price) / price) * 100
        targets.append((i, tp, pct))

    # بناء الرسالة بنفس تصميم الصورة
    msg = f"💀🚀 <b>AI PRO MAX SIGNAL</b>\n\n"
    msg += f"📊 <b>{market_title}</b>\n"
    msg += f"<b>{symbol}.{exchange}</b>\n"
    msg += f"{name}\n"
    msg += f"<b>{signal}</b>\n\n"
    
    msg += f"<b>السعر:</b> {price:.2f}     |  <b>EMA 8:</b> {ema8:.2f}     |  <b>الدعم:</b> {support:.2f}\n"
    msg += f"<b>التغير:</b> {change:+.2f}%  |  <b>EMA 21:</b> {ema21:.2f}    |  <b>المقاومة:</b> {resistance:.2f}\n"
    msg += f"<b>قوة الإشارة:</b> {buy_power:.0f}/100 |  <b>EMA 50:</b> {ema50:.2f}    |  <b>الاتجاه:</b> {trend}\n"
    msg += f"<b>قوة الشراء:</b> {buy_power:.0f}%  |  <b>RSI 14:</b> {rsi:.1f}       |\n"
    msg += f"<b>قوة البيع:</b> {sell_power:.0f}%   |  <b>ATR 14:</b> {atr:.2f}       |\n"
    msg += f"<b>الحجم:</b> {vol_ratio:.1f}x      |\n\n"

    msg += f"🎯 <b>أهداف ATR الثمانية:</b>\n"
    line1 = " | ".join([f"TP{t[0]} {t[1]:.2f} ({t[2]:+.1f}%)" for t in targets[:4]])
    line2 = " | ".join([f"TP{t[0]} {t[1]:.2f} ({t[2]:+.1f}%)" for t in targets[4:]])
    msg += f"{line1}\n"
    msg += f"{line2}\n"

    return msg

# ----------------------------------------------
# 🔄 الفحص التلقائي لكل سوق
# ----------------------------------------------
TASI_SYMBOLS = [("2222", "أرامكو السعودية"), ("1120", "الراجحي"), ("2010", "سابك"), ("1180", "الأهلي")]
US_SYMBOLS = [("AAPL", "Apple Inc"), ("TSLA", "Tesla Inc"), ("MSFT", "Microsoft"), ("NVDA", "NVIDIA")]
CRYPTO_SYMBOLS = [("BTC", "Bitcoin"), ("ETH", "Ethereum"), ("SOL", "Solana")]

def scan_market(market_type):
    if market_type == "TASI":
        users, symbols, exch, title, bot = tasi_users, TASI_SYMBOLS, "SR", "🇸🇦 السوق السعودي (TASI)", tasi_bot
    elif market_type == "US":
        users, symbols, exch, title, bot = us_users, US_SYMBOLS, "US", "🇺🇸 السوق الأمريكي (US)", us_bot
    else:
        users, symbols, exch, title, bot = crypto_users, CRYPTO_SYMBOLS, "CC", "🪙 العملات الرقمية (CRYPTO)", crypto_bot

    if not users: return

    for sym, name in symbols:
        try:
            msg = analyze_and_build(sym, name, exch, title)
            if msg:
                for chat_id in list(users):
                    try:
                        bot.send_message(chat_id, msg, parse_mode="HTML")
                        time.sleep(0.2)
                    except Exception as e:
                        print(f"Send Error {market_type}: {e}")
        except Exception as e:
            print(f"Scan Error {market_type} {sym}: {e}")
        time.sleep(1)

def scheduler():
    while True:
        time.sleep(UPDATE_INTERVAL_MIN * 60)
        print("⏰ Running scheduled scans...")
        scan_market("TASI")
        scan_market("US")
        scan_market("CRYPTO")

# ----------------------------------------------
# 🤖 أوامر البوتات
# ----------------------------------------------
def setup_bot(bot, users, market_type, welcome):
    @bot.message_handler(commands=['start', 'scan'])
    def handler(message):
        chat_id = message.chat.id
        print(f"📩 {market_type} command from {chat_id}")
        users.add(chat_id)
        bot.send_message(chat_id, welcome, parse_mode="HTML")
        scan_market(market_type)

setup_bot(tasi_bot, tasi_users, "TASI", "🟢 مرحباً! بوت السوق السعودي (AI PRO MAX) يعمل الآن.\nجاري الفحص...")
setup_bot(us_bot, us_users, "US", "🟢 مرحباً! بوت السوق الأمريكي (AI PRO MAX) يعمل الآن.\nجاري الفحص...")
setup_bot(crypto_bot, crypto_users, "CRYPTO", "🟢 مرحباً! بوت العملات الرقمية (AI PRO MAX) يعمل الآن.\nجاري الفحص...")

# ----------------------------------------------
# 🌐 خادم الويب لـ Railway
# ----------------------------------------------
@app.route("/")
def home():
    return "🚀 AI PRO MAX SIGNAL BOT is Online"

def run_flask():
    app.run(host="0.0.0.0", port=PORT)

# ----------------------------------------------
# 🚀 نقطة البداية
# ----------------------------------------------
if __name__ == "__main__":
    # 1. خادم الويب
    Thread(target=run_flask, daemon=True).start()
    
    # 2. المجدول التلقائي
    Thread(target=scheduler, daemon=True).start()
    
    # 3. تشغيل البوتات الثلاثة
    print("✅ All Bots started polling cleanly.")
    Thread(target=tasi_bot.polling, kwargs={"none_stop": True}, daemon=True).start()
    Thread(target=us_bot.polling, kwargs={"none_stop": True}, daemon=True).start()
    Thread(target=crypto_bot.polling, kwargs={"none_stop": True}, daemon=True).start()
    
    while True:
        time.sleep(1)