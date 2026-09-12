

import os
import time
import requests
import pandas as pd
import pandas_ta as ta
from datetime import datetime

# ==========================================
# 1. الإعدادات (Settings from Environment Variables)
# ==========================================
# يجب وضع هذه المتغيرات في Railway كما هو موضح في صورتك الثالثة
EODHD_API_KEY = os.environ.get("EODHD_API_KEY")

# إعدادات البوتات (التوكن ومعرف المحادثة)
BOTS_CONFIG = {
    "TASI": {
        "token": os.environ.get("TASI_BOT_TOKEN"),
        "chat_id": os.environ.get("TASI_CHAT_ID"),
        "ticker": "ARAMCO.SR", # يمكنك تغييره لأي سهم سعودي آخر
        "market_name": "السوق السعودي (TASI)"
    },
    "US": {
        "token": os.environ.get("US_BOT_TOKEN"),
        "chat_id": os.environ.get("US_CHAT_ID"),
        "ticker": "TSLA.US",
        "market_name": "السوق الأمريكي (US)"
    },
    "CRYPTO": {
        "token": os.environ.get("CRYPTO_BOT_TOKEN"),
        "chat_id": os.environ.get("CRYPTO_CHAT_ID"),
        "ticker": "BTC-USD.CC",
        "market_name": "العملات الرقمية (CRYPTO)"
    }
}

# ==========================================
# 2. دالة جلب البيانات من EODHD
# ==========================================
def fetch_eod_data(ticker):
    """جلب البيانات التاريخية اليومية من EODHD"""
    url = f"https://eodhd.com/api/eod/{ticker}?api_token={EODHD_API_KEY}&fmt=json&period=d&order=a"
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        df = pd.DataFrame(data)
        return df
    except Exception as e:
        print(f"خطأ في جلب بيانات {ticker}: {e}")
        return None

# ==========================================
# 3. دالة حساب المؤشرات والإشارات
# ==========================================
def calculate_indicators(df):
    """حساب المؤشرات الفنية المطلوبة"""
    # التأكد من أن البيانات مرتبة تصاعدياً حسب التاريخ
    df['date'] = pd.to_datetime(df['date'])
    df = df.sort_values('date')
    
    # حساب المتوسطات المتحركة
    df['EMA_8'] = ta.ema(df['close'], length=8)
    df['EMA_21'] = ta.ema(df['close'], length=21)
    df['EMA_50'] = ta.ema(df['close'], length=50)
    
    # حساب مؤشر القوة النسبية RSI ومدى التقلب ATR
    df['RSI_14'] = ta.rsi(df['close'], length=14)
    df['ATR_14'] = ta.atr(df['high'], df['low'], df['close'], length=14)
    
    # حساب الدعم والمقاومة (أعلى وأدنى سعر لآخر 20 شمعة)
    df['Resistance'] = df['high'].rolling(window=20).max()
    df['Support'] = df['low'].rolling(window=20).min()
    
    # حساب الحجم النسبي (مقارنة بآخر 20 يوم)
    df['Vol_Avg'] = df['volume'].rolling(window=20).mean()
    df['Vol_Ratio'] = df['volume'] / df['Vol_Avg']
    
    return df

def generate_signal(df, ticker, market_name):
    """توليد الإشارة والأهداف بناءً على البيانات"""
    latest = df.iloc[-1]
    
    current_price = latest['close']
    prev_close = df.iloc[-2]['close']
    change_pct = ((current_price - prev_close) / prev_close) * 100
    
    ema8 = latest['EMA_8']
    ema21 = latest['EMA_21']
    ema50 = latest['EMA_50']
    rsi = latest['RSI_14']
    atr = latest['ATR_14']
    resistance = latest['Resistance']
    support = latest['Support']
    vol_ratio = latest['Vol_Ratio']
    
    # تحديد الاتجاه والإشارة
    is_buy = ema8 > ema21 and ema21 > ema50 and rsi > 50
    is_sell = ema8 < ema21 and ema21 < ema50 and rsi < 50
    
    signal_type = "شراء قوي" if is_buy else ("بيع قوي" if is_sell else "حياد / انتظار")
    signal_emoji = "🟢" if is_buy else ("🔴" if is_sell else "⚪")
    arrow = "📈" if is_buy else ("📉" if is_sell else "➡️")
    
    trend_text = "صاعد قوي" if is_buy else ("هابط قوي" if is_sell else "عرضي")
    
    # حساب قوة الإشارة (تقديرية)
    signal_strength = min(100, max(0, int(abs(ema8 - ema50) / current_price * 1000 + (rsi if is_buy else 100 - rsi))))
    
    # حساب قوة الشراء والبيع
    buy_power = int((ema8 / ema50) * 50 + (rsi / 2))
    buy_power = min(100, max(0, buy_power))
    sell_power = 100 - buy_power
    
    # حساب أهداف ATR الثمانية
    targets = []
    for i in range(1, 9):
        if is_buy:
            tp = current_price + (atr * i)
            tp_pct = ((tp - current_price) / current_price) * 100
        else:
            tp = current_price - (atr * i)
            tp_pct = ((tp - current_price) / current_price) * 100
        targets.append(f"TP{i}: {tp:.2f} ({tp_pct:+.1f}%)")
    
    # تنسيق الأهداف في صفين
    tp_row1 = " | ".join(targets[:4])
    tp_row2 = " | ".join(targets[4:])
    
    # بناء الرسالة
    message = f"""
🦅 <b>AI PRO MAX SIGNAL</b>
🏢 {market_name}
<b>{ticker}</b>

{signal_emoji} <b>{signal_type}</b>

السعر: <code>{current_price:.2f}</code>
التغير: <code>{change_pct:+.2f}%</code>
قوة الإشارة: <code>{signal_strength}/100</code>
قوة الشراء: <code>{buy_power}%</code>
قوة البيع: <code>{sell_power}%</code>
الحجم: <code>{vol_ratio:.1f}x</code>

EMA 8:  <code>{ema8:.2f}</code>
EMA 21: <code>{ema21:.2f}</code>
EMA 50: <code>{ema50:.2f}</code>
RSI 14: <code>{rsi:.1f}</code>
ATR 14: <code>{atr:.2f}</code>

الدعم: <code>{support:.2f}</code>
المقاومة: <code>{resistance:.2f}</code>
الاتجاه: {trend_text} {arrow}

🎯 <b>أهداف ATR الثمانية:</b>
<code>{tp_row1}</code>
<code>{tp_row2}</code>
"""
    return message, signal_type

# ==========================================
# 4. دالة إرسال الرسالة إلى تيليجرام
# ==========================================
def send_telegram_message(bot_token, chat_id, message):
    """إرسال الرسالة عبر Telegram Bot API"""
    if not bot_token or not chat_id:
        print("خطأ: توكن البوت أو معرف المحادثة غير موجود.")
        return
        
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML"
    }
    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
        print(f"تم الإرسال بنجاح إلى {chat_id}")
    except Exception as e:
        print(f"فشل الإرسال: {e}")

# ==========================================
# 5. الحلقة الرئيسية (Main Loop)
# ==========================================
def main():
    print("بدء تشغيل بوت AI PRO MAX...")
    
    while True:
        for bot_name, config in BOTS_CONFIG.items():
            print(f"جاري فحص {config['ticker']}...")
            
            # 1. جلب البيانات
            df = fetch_eod_data(config['ticker'])
            if df is None or df.empty:
                continue
                
            # 2. حساب المؤشرات
            df = calculate_indicators(df)
            
            # 3. توليد الإشارة والرسالة
            message, signal_type = generate_signal(df, config['ticker'], config['market_name'])
            
            # 4. إرسال الرسالة (يمكنك إضافة شرط لإرسال الإشارات القوية فقط)
            # هنا نقوم بالإرسال دائماً، ولكن يمكنك وضع شرط if signal_type != "حياد / انتظار":
            send_telegram_message(config['token'], config['chat_id'], message)
            
            time.sleep(2) # فاصل بسيط بين البوتات
            
        print("اكتمل الفحص. الانتظار لمدة دقيقتين...")
        time.sleep(120) # الفحص كل دقيقتين كما هو مذكور في صورتك

if __name__ == "__main__":
    main()