
import os
import time
import telebot
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime
import threading

# ================= الإعدادات =================
# استخدام التوكن الأساسي (API) الموجود في إعدادات Railway
BOT_TOKEN = os.getenv('API') 
if not BOT_TOKEN:
    raise ValueError("يجب إضافة متغير البيئة API (توكن تليجرام)")

bot = telebot.TeleBot(BOT_TOKEN)

# قوائم الأسهم للمتابعة (يمكنك التعديل عليها)
TASI_STOCKS = ["2222.SR", "1120.SR", "2010.SR", "4013.SR"] # أرامكو، الراجحي، سابك، د. سليمان الحبيب
US_STOCKS = ["TSLA", "AAPL", "NVDA", "MSFT"]
CRYPTO_STOCKS = ["BTC-USD", "ETH-USD", "SOL-USD"]

# أسماء العرض بالعربية
STOCK_NAMES = {
    "2222.SR": "أرامكو السعودية", "1120.SR": "الراجحي", "2010.SR": "سابك", "4013.SR": "د. سليمان الحبيب",
    "TSLA": "Tesla Inc", "AAPL": "Apple Inc", "NVDA": "NVIDIA", "MSFT": "Microsoft",
    "BTC-USD": "Bitcoin", "ETH-USD": "Ethereum", "SOL-USD": "Solana"
}

# ================= دوال المؤشرات الفنية =================
def calculate_indicators(df):
    # EMA
    df['EMA_8'] = df['Close'].ewm(span=8, adjust=False).mean()
    df['EMA_21'] = df['Close'].ewm(span=21, adjust=False).mean()
    df['EMA_50'] = df['Close'].ewm(span=50, adjust=False).mean()
    
    # RSI
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))
    
    # ATR
    high_low = df['High'] - df['Low']
    high_close = np.abs(df['High'] - df['Close'].shift())
    low_close = np.abs(df['Low'] - df['Close'].shift())
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = np.max(ranges, axis=1)
    df['ATR'] = true_range.rolling(14).mean()
    
    # VWAP (تقريبي لليوم)
    df['Typical_Price'] = (df['High'] + df['Low'] + df['Close']) / 3
    df['VWAP'] = (df['Typical_Price'] * df['Volume']).cumsum() / df['Volume'].cumsum()
    
    return df

def get_support_resistance(df, window=20):
    recent_df = df.tail(window)
    support = recent_df['Low'].min()
    resistance = recent_df['High'].max()
    return support, resistance

def analyze_news(symbol):
    """تحليل أخبار السهم (للسوق الأمريكي)"""
    try:
        ticker = yf.Ticker(symbol)
        news = ticker.news
        if not news:
            return "لا توجد أخبار حديثة ⚪", "⚪"
        
        # تحليل بسيط للعناوين
        pos_words = ['beat', 'rise', 'growth', 'up', 'surge', 'profit', 'record', 'buy']
        neg_words = ['miss', 'fall', 'drop', 'down', 'loss', 'cut', 'sell', 'warn']
        
        pos_count = 0
        neg_count = 0
        
        for item in news[:5]: # قراءة آخر 5 أخبار
            title = item.get('title', '').lower()
            for word in pos_words:
                if word in title: pos_count += 1
            for word in neg_words:
                if word in title: neg_count += 1
                
        if pos_count > neg_count:
            return "أخبار إيجابية 🟢", "🟢"
        elif neg_count > pos_count:
            return "أخبار سلبية 🔴", "🔴"
        else:
            return "أخبار محايدة ⚪", "⚪"
    except Exception as e:
        return "تعذر جلب الأخبار", "⚪"

# ================= توليد التقرير =================
def generate_report(symbol):
    try:
        # جلب البيانات (فريم 5 دقائق لآخر يومين)
        df = yf.download(symbol, period="2d", interval="5m", progress=False)
        if df.empty:
            return None
        
        # تنظيف البيانات
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
            
        df = calculate_indicators(df)
        
        # آخر سعر وبيانات
        current_price = df['Close'].iloc[-1]
        prev_price = df['Close'].iloc[-2]
        change_pct = ((current_price - prev_price) / prev_price) * 100
        
        ema8 = df['EMA_8'].iloc[-1]
        ema21 = df['EMA_21'].iloc[-1]
        ema50 = df['EMA_50'].iloc[-1]
        rsi = df['RSI'].iloc[-1]
        atr = df['ATR'].iloc[-1]
        vwap = df['VWAP'].iloc[-1]
        
        support, resistance = get_support_resistance(df)
        
        # تحديد الاتجاه
        trend_arrow = "📈" if ema8 > ema21 else "📉"
        trend_text = "صاعد قوي" if ema8 > ema21 > ema50 else ("هابط قوي" if ema8 < ema21 < ema50 else "عرضي")
        
        # تحديد الإشارة
        signal = "⚪ محايد"
        signal_color = "⚪"
        if current_price > vwap and ema8 > ema21 and rsi > 50:
            signal = "🟢 شراء قوي"
            signal_color = "🟢"
        elif current_price < vwap and ema8 < ema21 and rsi < 50:
            signal = "🔴 بيع قوي"
            signal_color = "🔴"
            
        # حساب الأهداف الثمانية بناءً على ATR
        targets = []
        for i in range(1, 9):
            target_price = current_price + (i * atr) if signal_color == "🟢" else current_price - (i * atr)
            target_pct = ((target_price - current_price) / current_price) * 100
            targets.append(f"TP{i}: {target_price:.2f} ({target_pct:+.1f}%)")
            
        # تحليل الأخبار للسوق الأمريكي فقط
        news_text = ""
        news_emoji = ""
        if symbol in US_STOCKS:
            news_text, news_emoji = analyze_news(symbol)
            
        # تنسيق الرسالة
        name = STOCK_NAMES.get(symbol, symbol)
        
        msg = f"💀🚀 <b>AI PRO MAX SIGNAL</b>\n"
        msg += f"━━━━━━━━━━━━━━━━━━\n"
        if symbol.endswith(".SR"):
            msg += f"🇸🇦 السوق السعودي (TASI)\n"
        elif symbol in US_STOCKS:
            msg += f"🇺🇸 السوق الأمريكي (US)\n"
        elif "-USD" in symbol:
            msg += f"🪙 العملات الرقمية (CRYPTO)\n"
            
        msg += f"<b>{symbol}</b> | {name}\n\n"
        msg += f"💰 السعر: <b>{current_price:.2f}</b>\n"
        msg += f"📊 التغير: <b>{change_pct:+.2f}%</b>\n"
        msg += f"🎯 الإشارة: <b>{signal}</b>\n"
        msg += f"📈 الاتجاه: {trend_text} {trend_arrow}\n"
        if news_text:
            msg += f"📰 الأخبار: {news_text} {news_emoji}\n"
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
        "/scan - تشغيل الفحص التلقائي الآن"
    )
    bot.reply_to(message, welcome_text, parse_mode='HTML')

@bot.message_handler(commands=['tasi'])
def scan_tasi(message):
    bot.reply_to(message, "⏳ جاري فحص السوق السعودي...")
    for symbol in TASI_STOCKS:
        report = generate_report(symbol)
        if report:
            bot.send_message(message.chat.id, report, parse_mode='HTML')
            time.sleep(2) # تجنب الحظر

@bot.message_handler(commands=['us'])
def scan_us(message):
    bot.reply_to(message, "⏳ جاري فحص السوق الأمريكي...")
    for symbol in US_STOCKS:
        report = generate_report(symbol)
        if report:
            bot.send_message(message.chat.id, report, parse_mode='HTML')
            time.sleep(2)

@bot.message_handler(commands=['crypto'])
def scan_crypto(message):
    bot.reply_to(message, "⏳ جاري فحص العملات الرقمية...")
    for symbol in CRYPTO_STOCKS:
        report = generate_report(symbol)
        if report:
            bot.send_message(message.chat.id, report, parse_mode='HTML')
            time.sleep(2)

@bot.message_handler(commands=['all'])
def scan_all(message):
    bot.reply_to(message, "⏳ جاري فحص جميع الأسواق... قد يستغرق الأمر بعض الوقت.")
    all_stocks = TASI_STOCKS + US_STOCKS + CRYPTO_STOCKS
    for symbol in all_stocks:
        report = generate_report(symbol)
        if report:
            bot.send_message(message.chat.id, report, parse_mode='HTML')
            time.sleep(2)

# ================= الفحص التلقائي (كل دقيقتين) =================
def auto_scanner():
    # ضع هنا ID المحادثة الخاصة بك ليرسل التلقائي لك (يمكنك الحصول عليه من @userinfobot)
    # أو اتركه None وسيرسل للمجموعة إذا أضفت البوت إليها ووضعت الـ ID
    CHAT_ID = os.getenv('CHAT_ID') 
    if not CHAT_ID:
        print("⚠️ لم يتم تحديد CHAT_ID. الفحص التلقائي معطل.")
        return

    while True:
        try:
            print(f"⏳ بدء الفحص التلقائي: {datetime.now()}")
            all_stocks = TASI_STOCKS + US_STOCKS + CRYPTO_STOCKS
            for symbol in all_stocks:
                report = generate_report(symbol)
                if report:
                    bot.send_message(CHAT_ID, report, parse_mode='HTML')
                    time.sleep(3)
            
            print("✅ انتهى الفحص. الانتظار دقيقتين...")
            time.sleep(120) # الانتظار دقيقتين
        except Exception as e:
            print(f"خطأ في الفحص التلقائي: {e}")
            time.sleep(60)

# تشغيل الفحص التلقائي في الخلفية
if os.getenv('CHAT_ID'):
    threading.Thread(target=auto_scanner, daemon=True).start()

# تشغيل البوت
print("🚀 AI PRO MAX Bot is running...")
bot.infinity_polling()