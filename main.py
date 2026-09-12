
import os
import time
import requests
import pandas as pd
import pandas_ta as ta
from datetime import datetime

# ==========================================
# 1. الإعدادات وقراءة المتغيرات
# ==========================================
EODHD_API_KEY = os.environ.get("EODHD_API_KEY")

# دالة مساعدة لتحليل المتغيرات المجمعة (مثال: "TOKEN,CHAT_ID")
def parse_config(config_string):
    if not config_string:
        return None, None
    parts = config_string.split(',')
    if len(parts) == 2:
        return parts[0].strip(), parts[1].strip()
    return None, None

# قراءة الإعدادات من المتغيرات الموجودة في Railway
tasi_token, tasi_chat_id = parse_config(os.environ.get("TASI_CONFIG"))
us_token, us_chat_id = parse_config(os.environ.get("US_CONFIG"))
crypto_token, crypto_chat_id = parse_config(os.environ.get("CRYPTO_CONFIG"))

BOTS_CONFIG = {
    "TASI": {
        "token": tasi_token,
        "chat_id": tasi_chat_id,
        "ticker": "2222.SAU", # تم تصحيح الرمز
        "market_name": "السوق السعودي (TASI)"
    },
    "US": {
        "token": us_token,
        "chat_id": us_chat_id,
        "ticker": "TSLA.US",
        "market_name": "السوق الأمريكي (US)"
    },
    "CRYPTO": {
        "token": crypto_token,
        "chat_id": crypto_chat_id,
        "ticker": "BTC-USD.CC",
        "market_name": "العملات الرقمية (CRYPTO)"
    }
}

# ==========================================
# 2. دالة جلب البيانات من EODHD
# ==========================================
def fetch_eod_data(ticker):
    url = f"https://eodhd.com/api/eod/{ticker}?api_token={EODHD_API_KEY}&fmt=json&period=d&order=a"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        if not data or len(data) == 0:
            print(f"تحذير: لا توجد بيانات لـ {ticker}")
            return None
        df = pd.DataFrame(data)
        return df
    except Exception as e:
        print(f"خطأ في جلب بيانات {ticker}: {e}")
        return None

# ==========================================
# 3. دالة حساب المؤشرات والإشارات
# ==========================================
def calculate_indicators(df):
    df['date'] = pd.to_datetime(df['date'])
    df = df.sort_values('date')
    
    df['EMA_8'] = ta.ema(df['close'], length=8)
    df['EMA_21'] = ta.ema(df['close'], length=21)
    df['EMA_50'] = ta.ema(df['close'], length=50)
    df['RSI_14'] = ta.rsi(df['close'], length=14)
    df['ATR_14'] = ta.atr(df['high'], df['low'], df['close'], length=14)
    
    df['Resistance'] = df['high'].rolling(window=20).max()
    df['Support'] = df['low'].rolling(window=20).min()
    df['Vol_Avg'] = df['volume'].rolling(window=20).mean()
    df['Vol_Ratio'] = df['volume'] / df['Vol_Avg']
    
    return df

def generate_signal(df, ticker, market_name):
    latest = df.iloc[-1]
    prev_close = df.iloc[-2]['close']
    current_price = latest['close']
    change_pct = ((current_price - prev_close) / prev_close) * 100
    
    ema8 = latest['EMA_8']
    ema21 = latest['EMA_21']
    ema50 = latest['EMA_50']
    rsi = latest['RSI_14']
    atr = latest['ATR_14']
    resistance = latest['Resistance']
    support = latest['Support']
    vol_ratio = latest['Vol_Ratio']
    
    # تحديد الاتجاه بناءً على المتوسطات و RSI
    is_buy = ema8 > ema21 and ema21 > ema50 and rsi > 50
    is_sell = ema8 < ema21 and ema21 < ema50 and rsi < 50
    
    signal_type = "شراء قوي" if is_buy else ("بيع قوي" if is_sell else "حياد / انتظار")
    signal_emoji = "🟢" if is_buy else ("🔴" if is_sell else "⚪")
    
    # تحديد الملصق (Sticker) حسب الاتجاه
    # تم استخدام ملفات GIF متحركة (ملصقات) لتمثيل السهم الصاعد والهابط
    if is_buy:
        sticker_id = "https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExbnd5NnF4eWZ5eWZ5eWZ5eWZ5eWZ5eWZ5eWZ5eWZ5eWZ5eWZ5JmVwPXYxX2ludGVybmFsX2dpZl9ieV9pZCZjdD1n/3o7TKVUn7iM8FMEU24/giphy.gif" # سهم أخضر صاعد
    elif is_sell:
        sticker_id = "https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExbnd5NnF4eWZ5eWZ5eWZ5eWZ5eWZ5eWZ5eWZ5eWZ5eWZ5eWZ5JmVwPXYxX2ludGVybmFsX2dpZl9ieV9pZCZjdD1n/3o7TKVUn7iM8FMEU24/giphy.gif" # سهم أحمر هابط (سيتم استبداله)
    else:
        sticker_id = None
        
    trend_text = "صاعد قوي" if is_buy else ("هابط قوي" if is_sell else "عرضي")
    
    signal_strength = min(100, max(0, int(abs(ema8 - ema50) / current_price * 1000 + (rsi if is_buy else 100 - rsi))))
    
    buy_power = int((ema8 / ema50) * 50 + (rsi / 2))
    buy_power = min(100, max(0, buy_power))
    sell_power = 100 - buy_power
    
    targets = []
    for i in range(1, 9):
        if is_buy:
            tp = current_price + (atr * i)
            tp_pct = ((tp - current_price) / current_price) * 100
        else:
            tp = current_price - (atr * i)
            tp_pct = ((tp - current_price) / current_price) * 100
        targets.append(f"TP{i}: {tp:.2f} ({tp_pct:+.1f}%)")
    
    tp_row1 = " | ".join(targets[:4])
    tp_row2 = " | ".join(targets[4:])
    
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
الاتجاه: {trend_text}

🎯 <b>أهداف ATR الثمانية:</b>
<code>{tp_row1}</code>
<code>{tp_row2}</code>
"""
    return message, sticker_id

# ==========================================
# 4. دالة إرسال الرسالة والملصق إلى تيليجرام
# ==========================================
def send_telegram_message(bot_token, chat_id, message, sticker_url=None):
    if not bot_token or not chat_id:
        print("خطأ: توكن البوت أو معرف المحادثة غير موجود.")
        return
        
    # إرسال الرسالة النصية
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {"chat_id": chat_id, "text": message, "parse_mode": "HTML"}
    try:
        requests.post(url, json=payload)
        print(f"تم إرسال الرسالة النصية إلى {chat_id}")
    except Exception as e:
        print(f"فشل إرسال الرسالة: {e}")
        return

    # إرسال الملصق المتحرك إذا وجد
    if sticker_url:
        sticker_url_api = f"https://api.telegram.org/bot{bot_token}/sendAnimation"
        sticker_payload = {"chat_id": chat_id, "animation": sticker_url}
        try:
            requests.post(sticker_url_api, json=sticker_payload)
            print(f"تم إرسال الملصق المتحرك إلى {chat_id}")
        except Exception as e:
            print(f"فشل إرسال الملصق: {e}")

# ==========================================
# 5. الحلقة الرئيسية (Main Loop)
# ==========================================
def main():
    print("بدء تشغيل بوت AI PRO MAX...")
    
    while True:
        for bot_name, config in BOTS_CONFIG.items():
            print(f"جاري فحص {config['ticker']}...")
            
            df = fetch_eod_data(config['ticker'])
            if df is None or df.empty:
                continue
                
            df = calculate_indicators(df)
            message, sticker_url = generate_signal(df, config['ticker'], config['market_name'])
            
            # إرسال الرسالة والملصق
            send_telegram_message(config['token'], config['chat_id'], message, sticker_url)
            
            time.sleep(2)
            
        print("اكتمل الفحص. الانتظار لمدة 30 دقيقة...")
        time.sleep(1800) # تم زيادة الوقت لتجنب حظر مفتاح EODHD

if __name__ == "__main__":
    main()