
# ============================================================
# 📊 AI PRO MAX SIGNAL BOT (TASI, US, CRYPTO) - Python Version
# ============================================================
import os
import time
import math
import requests
import telebot
from flask import Flask
from datetime import datetime
from threading import Thread

# ----------------------------------------------
# ⚙️ الإعدادات والمتغيرات البيئية
# ----------------------------------------------
TASI_TOKEN = os.environ.get("TASI_TOKEN")
US_TOKEN = os.environ.get("US_TOKEN")
CRYPTO_TOKEN = os.environ.get("CRYPTO_TOKEN") # لا تنسَ إضافة توكن البوت الثالث
EODHD_API_KEY = os.environ.get("EODHD_API_KEY")
PORT = int(os.environ.get("PORT", 3000))
UPDATE_INTERVAL_MIN = 3

app = Flask(__name__)

# إعداد البوتات الثلاثة
tasi_bot = telebot.TeleBot(TASI_TOKEN, threaded=False)
us_bot = telebot.TeleBot(US_TOKEN, threaded=False)
crypto_bot = telebot.TeleBot(CRYPTO_TOKEN, threaded=False)

tasi_subscribers = set()
us_subscribers = set()
crypto_subscribers = set()

print("🚀 STARTING AI PRO MAX SIGNAL BOT (PYTHON VERSION)")
print("✅ TASI_TOKEN exists:", bool(TASI_TOKEN))
print("✅ US_TOKEN exists:", bool(US_TOKEN))
print("✅ CRYPTO_TOKEN exists:", bool(CRYPTO_TOKEN))
print("✅ EODHD_API_KEY exists:", bool(EODHD_API_KEY))

# ----------------------------------------------
# 🛠️ دوال المؤشرات الفنية (Pure Python)
# ----------------------------------------------
def calculate_ema(prices, period):
    if len(prices) < period: return prices[-1]
    multiplier = 2 / (period + 1)
    ema = prices[0]
    for price in prices[1:]:
        ema = (price * multiplier) + (ema * (1 - multiplier))
    return ema

def calculate_rsi(prices, period=14):
    if len(prices) < period + 1: return 50.0
    gains, losses = 0, 0
    for i in range(1, len(prices)):
        diff = prices[i] - prices[i-1]
        if diff > 0: gains += diff
        else: losses -= diff
    avg_gain = gains / period
    avg_loss = losses / period
    if avg_loss == 0: return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def calculate_atr(highs, lows, closes, period=14):
    if len(highs) < period + 1: return 0.0
    tr_list = []
    for i in range(1, len(highs)):
        tr = max(highs[i] - lows[i], abs(highs[i] - closes[i-1]), abs(lows[i] - closes[i-1]))
        tr_list.append(tr)
    return sum(tr_list[-period:]) / period

# ----------------------------------------------
# 📡 جلب البيانات من EODHD
# ----------------------------------------------
def fetch_eodhd_data(symbol, exchange_suffix):
    formatted_symbol = f"{symbol.replace('.', '-')}.{exchange_suffix}"
    url = f"https://eodhistoricaldata.com/api/eod/{formatted_symbol}?api_token={EODHD_API_KEY}&fmt=json&period=d&limit=60"
    try:
        response = requests.get(url, timeout=15)
        if response.status_code != 200: return None
        data = response.json()
        if not isinstance(data, list) or len(data) < 20: return None
        return data
    except Exception as e:
        print(f"Error fetching {formatted_symbol}: {e}")
        return None

# ----------------------------------------------
# 🧠 تحليل السهم وإنشاء الإشارة
# ----------------------------------------------
def analyze_stock(symbol, name, exchange_suffix, market_name):
    data = fetch_eodhd_data(symbol, exchange_suffix)
    if not data: return None

    closes = [float(d['close']) for d in data]
    highs = [float(d['high']) for d in data]
    lows = [float(d['low']) for d in data]
    volumes = [float(d['volume']) for d in data]

    price = closes[-1]
    prev_close = closes[-2] if len(closes) > 1 else price
    change_pct = ((price - prev_close) / prev_close) * 100

    ema8 = calculate_ema(closes, 8)
    ema21 = calculate_ema(closes, 21)
    ema50 = calculate_ema(closes, 50)
    rsi = calculate_rsi(closes, 14)
    atr = calculate_atr(highs, lows, closes, 14)

    # حساب قوة الإشارة (0-100)
    buy_power = 50
    if price > ema8: buy_power += 10
    if price > ema21: buy_power += 10
    if ema8 > ema21: buy_power += 10
    if rsi > 50: buy_power += 10
    if rsi > 70: buy_power -= 10 # تشبع شراء
    if rsi < 30: buy_power += 15 # تشبع بيع
    
    buy_power = max(0, min(100, buy_power))
    sell_power = 100 - buy_power
    signal_strength = buy_power

    if buy_power >= 70: signal_text = "🟢 شراء قوي"
    elif buy_power <= 30: signal_text = "🔴 بيع قوي"
    elif buy_power > 50: signal_text = "🟢 شراء"
    else: signal_text = "🔴 بيع"

    # الدعم والمقاومة
    support = min(lows[-20:])
    resistance = max(highs[-20:])

    # أهداف ATR الثمانية
    targets = []
    for i in range(1, 9):
        if buy_power > 50:
            tp = price + (atr * i * 0.5)
            tp_pct = ((tp - price) / price) * 100
        else:
            tp = price - (atr * i * 0.5)
            tp_pct = ((tp - price) / price) * 100
        targets.append({"tp": i, "price": tp, "pct": tp_pct})

    # تنسيق الرسالة
    msg = f"💀🚀 <b>AI PRO MAX SIGNAL</b>\n\n"
    msg += f"📊 <b>{market_name}</b>\n"
    msg += f"<b>{symbol}.{exchange_suffix}</b>\n"
    msg += f"{name}\n\n"
    msg += f"<b>{signal_text}</b>\n\n"
    
    msg += f"السعر: {price:.2f}\n"
    msg += f"التغير: {change_pct:+.2f}%\n"
    msg += f"قوة الإشارة: {signal_strength:.0f}/100\n"
    msg += f"قوة الشراء: {buy_power:.0f}%\n"
    msg += f"قوة البيع: {sell_power:.0f}%\n"
    msg += f"الحجم: {volumes[-1]/ (sum(volumes[-20:])/20):.1f}x\n\n"

    msg += f"EMA 8: {ema8:.2f}\n"
    msg += f"EMA 21: {ema21:.2f}\n"
    msg += f"EMA 50: {ema50:.2f}\n"
    msg += f"RSI 14: {rsi:.1f}\n"
    msg += f"ATR 14: {atr:.2f}\n\n"

    msg += f"الدعم: {support:.2f}\n"
    msg += f"المقاومة: {resistance:.2f}\n"
    if buy_power > 50:
        msg += f"صاعد قوي 📈\n\n"
    else:
        msg += f"هابط قوي 📉\n\n"

    msg += f"🎯 <b>أهداف ATR الثمانية:</b>\n"
    for t in targets:
        msg += f"TP{t['tp']}: {t['price']:.2f} ({t['pct']:+.1f}%)\n"

    return msg

# ----------------------------------------------
# 🔄 دوال الفحص لكل سوق
# ----------------------------------------------
# قائمة الرموز (يمكنك زيادتها لكن احذر استهلاك API)
TASI_SYMBOLS = [("2222", "أرامكو السعودية"), ("1120", "الراجحي"), ("2010", "سابك"), ("1180", "الأهلي"), ("2350", "كيان")]
US_SYMBOLS = [("AAPL", "Apple Inc"), ("TSLA", "Tesla Inc"), ("MSFT", "Microsoft"), ("NVDA", "NVIDIA"), ("AMZN", "Amazon")]
CRYPTO_SYMBOLS = [("BTC", "Bitcoin"), ("ETH", "Ethereum"), ("SOL", "Solana"), ("BNB", "Binance Coin"), ("XRP", "Ripple")]

def scan_market(market_type):
    if market_type == "TASI":
        subscribers = tasi_subscribers
        symbols = TASI_SYMBOLS
        suffix = "SR"
        market_name = "🇸🇦 السوق السعودي (TASI)"
        bot = tasi_bot
    elif market_type == "US":
        subscribers = us_subscribers
        symbols = US_SYMBOLS
        suffix = "US"
        market_name = "🇺🇸 السوق الأمريكي (US)"
        bot = us_bot
    else:
        subscribers = crypto_subscribers
        symbols = CRYPTO_SYMBOLS
        suffix = "CC"
        market_name = "🪙 العملات الرقمية (CRYPTO)"
        bot = crypto_bot

    if not subscribers: return

    for sym, name in symbols:
        try:
            msg = analyze_stock(sym, name, suffix, market_name)
            if msg:
                for chat_id in list(subscribers):
                    try:
                        bot.send_message(chat_id, msg, parse_mode="HTML")
                        time.sleep(0.2)
                    except Exception as e:
                        print(f"Send Error {market_type}: {e}")
        except Exception as e:
            print(f"Scan Error {market_type} {sym}: {e}")
        time.sleep(1) # تأخير لتجنب حظر API

def run_scheduled_scans():
    while True:
        time.sleep(UPDATE_INTERVAL_MIN * 60)
        print("⏰ Running scheduled scans...")
        scan_market("TASI")
        scan_market("US")
        scan_market("CRYPTO")

# ----------------------------------------------
# 🤖 معالجة أوامر البوتات
# ----------------------------------------------
def setup_handlers(bot, subscribers, market_type, welcome_msg):
    @bot.message_handler(commands=['start', 'scan'])
    def start_handler(message):
        chat_id = message.chat.id
        print(f"📩 {market_type} command from {chat_id}")
        subscribers.add(chat_id)
        bot.send_message(chat_id, welcome_msg, parse_mode="HTML")
        scan_market(market_type)

setup_handlers(tasi_bot, tasi_subscribers, "TASI", "🟢 مرحباً! بوت السوق السعودي (AI PRO MAX) يعمل الآن.\nجاري الفحص...")
setup_handlers(us_bot, us_subscribers, "US", "🟢 مرحباً! بوت السوق الأمريكي (AI PRO MAX) يعمل الآن.\nجاري الفحص...")
setup_handlers(crypto_bot, crypto_subscribers, "CRYPTO", "🟢 مرحباً! بوت العملات الرقمية (AI PRO MAX) يعمل الآن.\nجاري الفحص...")

# ----------------------------------------------
# 🌐 خادم الويب (لـ Railway)
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
    flask_thread = Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()
    
    # 2. المجدول التلقائي
    scheduler_thread = Thread(target=run_scheduled_scans)
    scheduler_thread.daemon = True
    scheduler_thread.start()
    
    # 3. تشغيل البوتات
    print("✅ All Bots started polling cleanly.")
    t1 = Thread(target=tasi_bot.polling, kwargs={"none_stop": True}); t1.start()
    t2 = Thread(target=us_bot.polling, kwargs={"none_stop": True}); t2.start()
    t3 = Thread(target=crypto_bot.polling, kwargs={"none_stop": True}); t3.start()
    
    while True:
        time.sleep(1)