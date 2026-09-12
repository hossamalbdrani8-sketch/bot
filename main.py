
# ============================================================
# 📊 CLEAN PURE STOCK SCANNER BOT (TASI & US) - Python Version
# ============================================================
# ✅ هذه النسخة جديدة ونظيفة تماماً - لا يوجد شرط قناة
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
EODHD_API_KEY = os.environ.get("EODHD_API_KEY")
PORT = int(os.environ.get("PORT", 3000))
REQUEST_DELAY_SEC = 0.3
UPDATE_INTERVAL_MIN = 3

app = Flask(__name__)

# إعداد البوتات
tasi_bot = telebot.TeleBot(TASI_TOKEN, threaded=False)
us_bot = telebot.TeleBot(US_TOKEN, threaded=False)

tasi_subscribers = set()
us_subscribers = set()

tasi_scan_running = False
us_scan_running = False

print("🚀 THIS IS THE NEW CLEAN PYTHON VERSION WITHOUT CHANNEL CHECK")
print("✅ TASI_TOKEN exists:", bool(TASI_TOKEN))
print("✅ US_TOKEN exists:", bool(US_TOKEN))
print("✅ EODHD_API_KEY exists:", bool(EODHD_API_KEY))

# ----------------------------------------------
# 🛠️ الدوال المساعدة
# ----------------------------------------------
def sleep_ms(ms):
    time.sleep(ms / 1000.0)

def fetch_eodhd(url):
    headers = {"User-Agent": "Mozilla/5.0"}
    response = requests.get(url, headers=headers, timeout=15)
    if response.status_code != 200:
        raise Exception(f"EODHD HTTP {response.status_code}")
    return response.json()

def get_exchange_symbols(exchange):
    url = f"https://eodhd.com/api/exchange-symbol-list/{exchange}?api_token={EODHD_API_KEY}&fmt=json"
    data = fetch_eodhd(url)
    if not isinstance(data, list):
        raise Exception("Invalid symbols list")
    
    symbols = []
    for item in data:
        type_str = str(item.get("Type", "")).lower()
        if "stock" in type_str or "common" in type_str:
            code = str(item.get("Code", "")).strip()
            if code:
                symbols.append(code)
    return symbols

def calculate_atr(highs, lows, closes, period=14):
    if len(highs) < period + 1:
        return 0.0
    tr_list = []
    for i in range(1, len(highs)):
        tr = max(highs[i] - lows[i], abs(highs[i] - closes[i-1]), abs(lows[i] - closes[i-1]))
        tr_list.append(tr)
    recent_tr = tr_list[-period:]
    return sum(recent_tr) / len(recent_tr)

def analyze_liquidity(closes, volumes):
    length = min(len(closes), len(volumes))
    start = max(1, length - 10)
    buy_vol, sell_vol, neut_vol = 0, 0, 0
    
    for i in range(start, length):
        prev = closes[i-1]
        curr = closes[i]
        vol = volumes[i] if i < len(volumes) else 0
        if curr > prev: buy_vol += vol
        elif curr < prev: sell_vol += vol
        else: neut_vol += vol
        
    total = buy_vol + sell_vol + neut_vol
    if total <= 0:
        return {"buy_ratio": 50, "label": "⚪ سيولة متوازنة"}
        
    buy_ratio = (buy_vol / total) * 100
    sell_ratio = (sell_vol / total) * 100
    
    label = "⚪ سيولة متوازنة"
    if buy_ratio >= 65: label = "🟢 دخول سيولة قوية"
    elif sell_ratio >= 65: label = "🔴 خروج سيولة قوية"
    elif buy_ratio >= 53: label = "🟢 دخول سيولة"
    elif sell_ratio >= 53: label = "🔴 خروج سيولة"
    
    return {"buy_ratio": buy_ratio, "label": label}

def ai_pro_max_trend(closes, highs, lows):
    if not closes:
        return {"direction": "NEUTRAL", "label": "⚖️ اتجاه عرضي متوازن"}
        
    current_price = closes[-1]
    short_len = min(len(closes), 14)
    momentum_score = 0
    
    for i in range(len(closes) - short_len, len(closes)):
        if closes[i] > closes[i-1]: momentum_score += 1
        elif closes[i] < closes[i-1]: momentum_score -= 1
        
    recent_high = max(highs[-10:]) if len(highs) >= 10 else current_price
    recent_low = min(lows[-10:]) if len(lows) >= 10 else current_price
    
    if momentum_score >= 3 and current_price >= recent_low * 1.02:
        return {"direction": "UP", "label": "🚀 اتجاه صاعد"}
    elif momentum_score <= -3 or current_price <= recent_high * 0.98:
        return {"direction": "DOWN", "label": "⚠️ اتجاه هابط"}
        
    return {"direction": "NEUTRAL", "label": "⚖️ اتجاه عرضي متوازن"}

def calculate_support_resistance(highs, lows, price):
    pivot_highs, pivot_lows = [], []
    for i in range(2, len(highs) - 2):
        if highs[i] > highs[i-1] and highs[i] > highs[i+1]:
            pivot_highs.append(highs[i])
        if lows[i] < lows[i-1] and lows[i] < lows[i+1]:
            pivot_lows.append(lows[i])
            
    supports = sorted([l for l in pivot_lows if l < price], reverse=True)[:2]
    resistances = sorted([h for h in pivot_highs if h > price])[:2]
    
    if not supports: supports = [price * 0.95]
    if not resistances: resistances = [price * 1.05]
    
    return {"supports": supports, "resistances": resistances}

def get_stock_data(symbol, exchange_suffix, min_price):
    formatted_symbol = f"{symbol.replace('.', '-')}.{exchange_suffix}"
    url = f"https://eodhistoricaldata.com/api/eod/{formatted_symbol}?api_token={EODHD_API_KEY}&fmt=json&period=d&limit=60"
    
    data = fetch_eodhd(url)
    if not isinstance(data, list) or len(data) < 20:
        raise Exception("بيانات غير كافية")
        
    closes = [float(i["close"]) for i in data if "close" in i and i["close"] is not None]
    highs = [float(i["high"]) for i in data if "high" in i and i["high"] is not None]
    lows = [float(i["low"]) for i in data if "low" in i and i["low"] is not None]
    volumes = [float(i["volume"]) for i in data if "volume" in i and i["volume"] is not None]
    
    if not closes:
        raise Exception("لا توجد أسعار")
        
    price = closes[-1]
    if price < min_price:
        raise Exception("السعر أقل من الحد الأدنى")
        
    prev_close = closes[-2] if len(closes) > 1 else price
    change_percent = ((price - prev_close) / prev_close) * 100
    
    trend_obj = ai_pro_max_trend(closes, highs, lows)
    atr = calculate_atr(highs, lows, closes, 14)
    liquidity = analyze_liquidity(closes, volumes)
    levels = calculate_support_resistance(highs, lows, price)
    
    targets = []
    icon = "✅" if trend_obj["direction"] == "UP" else "🔴"
    
    for i in range(1, 5):
        target_price = price + (atr * i * 0.6) if trend_obj["direction"] == "UP" else price - (atr * i * 0.6)
        reached = price >= target_price if trend_obj["direction"] == "UP" else price <= target_price
        targets.append({
            "level": i,
            "price": target_price,
            "status": f"{icon} (تحقق)" if reached else "⏳ (قيد الانتظار)"
        })
        
    return {
        "symbol": symbol,
        "price": price,
        "change_percent": change_percent,
        "trend": trend_obj["label"],
        "liquidity": liquidity["label"],
        "buy_ratio": liquidity["buy_ratio"],
        "supports": levels["supports"],
        "resistances": levels["resistances"],
        "targets": targets,
        "updated": datetime.now()
    }

def build_alert_message(stock, market_name):
    msg = f"📊 *{market_name}*\n\n"
    msg += f"📌 الرمز: *{stock['symbol']}*\n"
    msg += f"💰 السعر: *{stock['price']:.2f}*\n"
    msg += f"📈 التغير: *{stock['change_percent']:.2f}%*\n\n"
    msg += f"🤖 *{stock['trend']}*\n"
    msg += f"💧 السيولة: *{stock['liquidity']}* ({stock['buy_ratio']:.1f}%)\n\n"
    msg += "🎯 *الأهداف الذكية (ATR):*\n"
    
    for t in stock["targets"]:
        msg += f"• الهدف {t['level']}: *{t['price']:.2f}* {t['status']}\n"
        
    supports_str = " | ".join([f"{s:.2f}" for s in stock['supports']])
    resistances_str = " | ".join([f"{r:.2f}" for r in stock['resistances']])
    
    msg += f"\n📉 *الدعوم:* {supports_str}\n"
    msg += f"📈 *المقاومات:* {resistances_str}\n\n"
    msg += f"🕒 {stock['updated'].strftime('%I:%M:%S %p')}"
    return msg

# ----------------------------------------------
# 🔄 دوال المسح
# ----------------------------------------------
def run_tasi_scan():
    global tasi_scan_running
    if tasi_scan_running or not tasi_subscribers:
        return
    tasi_scan_running = True
    
    try:
        symbols = get_exchange_symbols("SR")
        for sym in symbols[:10]:  # فحص أول 10 أسهم لتجنب استهلاك API
            try:
                stock = get_stock_data(sym, "SR", 0.01)
                for chat_id in list(tasi_subscribers):
                    try:
                        tasi_bot.send_message(chat_id, build_alert_message(stock, "🇸🇦 السوق السعودي (تاسي)"), parse_mode="Markdown")
                        sleep_ms(200)
                    except Exception as e:
                        print(f"TASI Send Error to {chat_id}: {e}")
            except Exception:
                pass
            sleep_ms(300)
    except Exception as e:
        print(f"TASI Scan Error: {e}")
    finally:
        tasi_scan_running = False

def run_us_scan():
    global us_scan_running
    if us_scan_running or not us_subscribers:
        return
    us_scan_running = True
    
    try:
        symbols = get_exchange_symbols("US")
        for sym in symbols[:10]:
            try:
                stock = get_stock_data(sym, "US", 0.20)
                for chat_id in list(us_subscribers):
                    try:
                        us_bot.send_message(chat_id, build_alert_message(stock, "🇺🇸 السوق الأمريكي"), parse_mode="Markdown")
                        sleep_ms(200)
                    except Exception as e:
                        print(f"US Send Error to {chat_id}: {e}")
            except Exception:
                pass
            sleep_ms(300)
    except Exception as e:
        print(f"US Scan Error: {e}")
    finally:
        us_scan_running = False

# ----------------------------------------------
# 🤖 معالجة أوامر البوت
# ----------------------------------------------
@tasi_bot.message_handler(commands=['start', 'scan'])
def tasi_start(message):
    chat_id = message.chat.id
    print(f"📩 TASI command received from {chat_id}: {message.text}")
    tasi_subscribers.add(chat_id)
    
    # رسالة جديدة تماماً مختلفة عن القديمة
    tasi_bot.send_message(
        chat_id, 
        "🟢 مرحباً! هذا البوت الجديد للسوق السعودي (بدون شرط قناة).\nجاري جلب التحليلات الفورية...", 
        parse_mode="Markdown"
    )
    run_tasi_scan()

@us_bot.message_handler(commands=['start', 'scan'])
def us_start(message):
    chat_id = message.chat.id
    print(f"📩 US command received from {chat_id}: {message.text}")
    us_subscribers.add(chat_id)
    
    # رسالة جديدة تماماً مختلفة عن القديمة
    us_bot.send_message(
        chat_id, 
        "🟢 مرحباً! هذا البوت الجديد للسوق الأمريكي (بدون شرط قناة).\nجاري جلب التحليلات الفورية...", 
        parse_mode="Markdown"
    )
    run_us_scan()

# ----------------------------------------------
# 🌐 خادم الويب (لـ Railway Health Check)
# ----------------------------------------------
@app.route("/")
def home():
    return "🚀 Clean Stock Scanner Bot is Online (Python Version)"

def run_flask():
    app.run(host="0.0.0.0", port=PORT)

# ----------------------------------------------
# ⏱️ المجدول التلقائي (كل 3 دقائق)
# ----------------------------------------------
def scheduler():
    while True:
        time.sleep(UPDATE_INTERVAL_MIN * 60)
        print("⏰ Running scheduled scans...")
        run_tasi_scan()
        run_us_scan()

# ----------------------------------------------
# 🚀 نقطة البداية
# ----------------------------------------------
if __name__ == "__main__":
    # 1. تشغيل خادم الويب في خيط منفصل
    flask_thread = Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()
    
    # 2. تشغيل المجدول التلقائي في خيط منفصل
    scheduler_thread = Thread(target=scheduler)
    scheduler_thread.daemon = True
    scheduler_thread.start()
    
    # 3. تشغيل البوتات
    print("✅ Telegram Bots started polling cleanly.")
    
    tasi_thread = Thread(target=tasi_bot.polling, kwargs={"none_stop": True})
    tasi_thread.daemon = True
    tasi_thread.start()
    
    us_thread = Thread(target=us_bot.polling, kwargs={"none_stop": True})
    us_thread.daemon = True
    us_thread.start()
    
    # 4. إبقاء البرنامج يعمل
    while True:
        time.sleep(1)