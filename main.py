
import os
import time
import telebot
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime
import threading

# ================= الإعدادات الأساسية =================
BOT_TOKEN = os.getenv('API')
if not BOT_TOKEN:
    print("❌ خطأ: يجب إضافة متغير البيئة API (توكن تليجرام) في Railway")
    exit(1)

bot = telebot.TeleBot(BOT_TOKEN)

# الأسواق (يمكنك إضافة المزيد من الأسهم هنا)
TASI_STOCKS = ["2222.SR", "1120.SR", "2010.SR", "4013.SR", "2350.SR"] # أرامكو، الراجحي، سابك، الحبيب، كيان
US_STOCKS = ["TSLA", "AAPL", "NVDA", "MSFT", "AMZN", "GOOGL"]
CRYPTO_STOCKS = ["BTC-USD", "ETH-USD", "SOL-USD", "BNB-USD"]

# قاموس أسماء الأسهم بالعربية
STOCK_NAMES = {
    "2222.SR": "أرامكو السعودية", "1120.SR": "الراجحي", "2010.SR": "سابك", "4013.SR": "د. سليمان الحبيب", "2350.SR": "كيان السعودية",
    "TSLA": "تسلا", "AAPL": "أبل", "NVDA": "إنفيديا", "MSFT": "مايكروسوفت", "AMZN": "أمازون", "GOOGL": "ألفابت",
    "BTC-USD": "بيتكوين", "ETH-USD": "إيثيريوم", "SOL-USD": "سولانا", "BNB-USD": "بينانس"
}

# ================= دوال التحليل الفني =================
def calculate_indicators(df):
    try:
        # المتوسطات المتحركة الأسية
        df['EMA_8'] = df['Close'].ewm(span=8, adjust=False).mean()
        df['EMA_21'] = df['Close'].ewm(span=21, adjust=False).mean()
        df['EMA_50'] = df['Close'].ewm(span=50, adjust=False).mean()
        
        # مؤشر القوة النسبية RSI
        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df['RSI'] = 100 - (100 / (1 + rs))
        
        # مؤشر التقلب ATR
        high_low = df['High'] - df['Low']
        high_close = np.abs(df['High'] - df['Close'].shift())
        low_close = np.abs(df['Low'] - df['Close'].shift())
        ranges = pd.concat([high_low, high_close, low_close], axis=1)
        true_range = np.max(ranges, axis=1)
        df['ATR'] = true_range.rolling(14).mean()
        
        # مؤشر VWAP (متوسط السعر المرجح بالحجم)
        df['Typical_Price'] = (df['High'] + df['Low'] + df['Close']) / 3
        df['VWAP'] = (df['Typical_Price'] * df['Volume']).cumsum() / df['Volume'].cumsum()
    except Exception as e:
        print(f"Error calculating indicators: {e}")
    return df

def get_support_resistance(df, window=20):
    recent_df = df.tail(window)
    if recent_df.empty:
        return 0, 0
    support = recent_df['Low'].min()
    resistance = recent_df['High'].max()
    return support, resistance

def analyze_news(symbol):
    """تحليل أخبار السهم الأمريكي (إيجابي/سلبي)"""
    try:
        ticker = yf.Ticker(symbol)
        news = ticker.news
        if not news:
            return "لا توجد أخبار حديثة ⚪", "⚪"
        
        pos_words = ['beat', 'rise', 'growth', 'up', 'surge', 'profit', 'record', 'buy', 'strong', 'gain']
        neg_words = ['miss', 'fall', 'drop', 'down', 'loss', 'cut', 'sell', 'warn', 'weak', 'decline']
        
        pos_count = 0
        neg_count = 0
        
        for item in news[:5]: # قراءة آخر 5 أخبار
            title = item.get('title', '').lower()
            for word in pos_words:
                if word in title: pos_count += 1
            for word in neg_words:
                if word in title: neg_count += 1
                
        if pos_count > neg_count: return "أخبار إيجابية 🟢", "🟢"
        elif neg_count > pos_count: return "أخبار سلبية 🔴", "🔴"
        else: return "أخبار محايدة ⚪", "⚪"
    except Exception:
        return "تعذر جلب الأخبار", "⚪"

# ================= توليد التقرير =================
def generate_report(symbol):
    try:
        # جلب البيانات (فريم 15 دقيقة لآخر 5 أيام لضمان وجود بيانات كافية)
        ticker = yf.Ticker(symbol)
        df = ticker.history(period="5d", interval="15m")
        
        if df.empty or len(df) < 50:
            return None # لا توجد بيانات كافية
            
        df = calculate_indicators(df)
        df = df.dropna() # إزالة القيم الفارغة
        
        if df.empty:
            return None

        current_price = df['Close'].iloc[-1]
        prev_price = df['Close'].iloc[-2] if len(df) > 1 else current_price
        change_pct = ((current_price - prev_price) / prev_price) * 100
        
        ema8 = df['EMA_8'].iloc[-1]
        ema21 = df['EMA_21'].iloc[-1]
        ema50 = df['EMA_50'].iloc[-1]
        rsi = df['RSI'].iloc[-1]
        atr = df['ATR'].iloc[-1]
        vwap = df['VWAP'].iloc[-1]
        
        support, resistance = get_support_resistance(df)
        
        # تحديد اتجاه السهم (أخضر/أحمر)
        if ema8 > ema21 > ema50:
            trend_arrow = "📈"
            trend_text = "صاعد قوي"
        elif ema8 < ema21 < ema50:
            trend_arrow = "📉"
            trend_text = "هابط قوي"
        else:
            trend_arrow = "↔️"
            trend_text = "عرضي"
            
        # تحديد الإشارة بناءً على VWAP والمتوسطات
        signal = "⚪ محايد"
        signal_color = "⚪"
        if current_price > vwap and ema8 > ema21 and rsi > 50:
            signal = "🟢 شراء قوي"
            signal_color = "🟢"
        elif current_price < vwap and ema8 < ema21 and rsi < 50:
            signal = "🔴 بيع قوي"
            signal_color = "🔴"
            
        # حساب 8 أهداف بناءً على ATR
        targets = []
        for i in range(1, 9):
            if signal_color == "🟢":
                target_price = current_price + (i * atr)
                target_pct = ((target_price - current_price) / current_price) * 100
                targets.append(f"🎯 TP{i}: {target_price:.2f} ({target_pct:+.1f}%)")
            else:
                target_price = current_price - (i * atr)
                target_pct = ((target_price - current_price) / current_price) * 100
                targets.append(f"🎯 TP{i}: {target_price:.2f} ({target_pct:+.1f}%)")
                
        # تحليل الأخبار للسوق الأمريكي
        news_text = ""
        if symbol in US_STOCKS:
            news_text, _ = analyze_news(symbol)
            
        name = STOCK_NAMES.get(symbol, symbol)
        
        # تنسيق الرسالة
        msg = f"💀🚀 <b>AI PRO MAX SIGNAL</b>\n"
        msg += f"━━━━━━━━━━━━━━━━━━\n"
        if symbol.endswith(".SR"): msg += f"🇸🇦 السوق السعودي (TASI)\n"
        elif symbol in US_STOCKS: msg += f"🇺🇸 السوق الأمريكي (US)\n"
        elif "-USD" in symbol: msg += f"🪙 العملات الرقمية (CRYPTO)\n"
            
        msg += f"<b>{symbol}</b> | {name}\n\n"
        msg += f"💰 السعر: <b>{current_price:.2f}</b>\n"
        msg += f"📊 التغير: <b>{change_pct:+.2f}%</b>\n"
        msg += f"🎯 الإشارة: <b>{signal}</b>\n"
        msg += f"📈 الاتجاه: {trend_text} {trend_arrow}\n"
        if news_text: msg += f"📰 الأخبار: {news_text}\n"
        msg += f"\n"
        
        msg += f"📉 <b>المؤشرات الفنية:</b>\n"
        msg += f"EMA 8: {ema8:.2f} | EMA 21: {ema21:.2f}\n"
        msg += f"EMA 50: {ema50:.2f} | RSI: {rsi:.1f}\n"
        msg += f"ATR: {atr:.2f} | VWAP: {vwap:.2f}\n\n"
        
        msg += f"🛡️ <b>الدعم والمقاومة:</b>\n"
        msg += f"الدعم: {support:.2f} | المقاومة: {resistance:.2f}\n\n"
        
        msg += f"🎯 <b>أهداف ATR الثمانية:</b>\n"
        msg += " | ".join(targets[:4]) + "\n"
        msg += " | ".join(targets[4:]) + "\n"
        msg += f"━━━━━━━━━━━━━━━━━━"
        
        return msg
        
    except Exception as e:
        print(f"Error analyzing {symbol}: {e}")
        return None

# ================= أوامر البوت =================
@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    welcome_text = (
        "أهلاً بك في <b>AI PRO MAX</b> 🤖🚀\n\n"
        "البوت المدمج لتحليل الأسواق المالية:\n"
        "🇸🇦 السوق السعودي (TASI)\n"
        "🇺🇸 السوق الأمريكي (US)\n"
        "🪙 العملات الرقمية (Crypto)\n\n"
        "الأوامر المتاحة:\n"
        "/tasi - تحليل السوق السعودي\n"
        "/us - تحليل السوق الأمريكي\n"
        "/crypto - تحليل العملات الرقمية\n"
        "/all - تحليل كافة الأسواق\n"
    )
    bot.reply_to(message, welcome_text, parse_mode='HTML')

def send_reports(chat_id, symbols):
    for symbol in symbols:
        report = generate_report(symbol)
        if report:
            try:
                bot.send_message(chat_id, report, parse_mode='HTML')
                time.sleep(1.5) # تجنب الحظر من تليجرام
            except Exception as e:
                print(f"Telegram Send Error: {e}")

@bot.message_handler(commands=['tasi'])
def scan_tasi(message):
    bot.reply_to(message, "⏳ جاري فحص السوق السعودي...")
    send_reports(message.chat.id, TASI_STOCKS)

@bot.message_handler(commands=['us'])
def scan_us(message):
    bot.reply_to(message, "⏳ جاري فحص السوق الأمريكي...")
    send_reports(message.chat.id, US_STOCKS)

@bot.message_handler(commands=['crypto'])
def scan_crypto(message):
    bot.reply_to(message, "⏳ جاري فحص العملات الرقمية...")
    send_reports(message.chat.id, CRYPTO_STOCKS)

@bot.message_handler(commands=['all'])
def scan_all(message):
    bot.reply_to(message, "⏳ جاري فحص جميع الأسواق... قد يستغرق الأمر بعض الوقت.")
    send_reports(message.chat.id, TASI_STOCKS + US_STOCKS + CRYPTO_STOCKS)

# ================= الفحص التلقائي (كل دقيقتين) =================
def auto_scanner():
    CHAT_ID = os.getenv('CHAT_ID') 
    if not CHAT_ID:
        print("⚠️ لم يتم تحديد CHAT_ID. الفحص التلقائي معطل.")
        return

    while True:
        try:
            print(f"⏳ بدء الفحص التلقائي: {datetime.now()}")
            all_stocks = TASI_STOCKS + US_STOCKS + CRYPTO_STOCKS
            send_reports(CHAT_ID, all_stocks)
            print("✅ انتهى الفحص. الانتظار دقيقتين...")
            time.sleep(120) # الانتظار دقيقتين
        except Exception as e:
            print(f"خطأ في الفحص التلقائي: {e}")
            time.sleep(60)

# تشغيل الفحص التلقائي في الخلفية
if os.getenv('CHAT_ID'):
    threading.Thread(target=auto_scanner, daemon=True).start()

print("🚀 AI PRO MAX Bot is running...")
bot.infinity_polling()