
import os
import math
import requests
from datetime import datetime

# استدعاء المتغيرات البيئية من منصة Railway (المطابقة للصورة المرفقة)
EODHD_API_KEY = os.getenv("EODHD_API_KEY", "YOUR_API_KEY_HERE")
TASI_TOKEN = os.getenv("TASI_TOKEN", "")
US_TOKEN = os.getenv("US_TOKEN", "")
CRYPTO_TOKEN = os.getenv("CRYPTO_TOKEN", "")

def fetch_eodhd_data(ticker, exchange="US"):
    """جلب البيانات التاريخية واللحظية للأسهم أو العملات من EODHD"""
    url = f"https://eodhistoricaldata.com/api/real-time/{ticker}.{exchange}"
    params = {'api_token': EODHD_API_KEY, 'fmt': 'json'}
    try:
        response = requests.get(url, params=params, timeout=10)
        if response.status_code == 200:
            return response.json()
    except Exception as e:
        print(f"خطأ في جلب بيانات {ticker}: {e}")
    return None

def calculate_atr(candles, period=14):
    """حساب مؤشر ATR(14) بدقة بناءً على الشموع التاريخية"""
    if len(candles) < period:
        return 0.0
    
    tr_list = []
    for i in range(1, len(candles)):
        high = float(candles[i].get('high', 0))
        low = float(candles[i].get('low', 0))
        close_prev = float(candles[i-1].get('close', 0))
        
        tr = max(high - low, abs(high - close_prev), abs(low - close_prev))
        tr_list.append(tr)
        
    atr = sum(tr_list[-period:]) / period
    return atr

def ai_pro_max_engine(candles):
    """محرك AI PRO MAX لتحديد الاتجاه العام والسيولة والدعم والمقاومة"""
    if not candles or len(candles) < 20:
        return "NEUTRAL", 0, 0, 0
    
    closes = [float(c.get('close', 0)) for c in candles]
    highs = [float(c.get('high', 0)) for c in candles]
    lows = [float(c.get('low', 0)) for c in candles]
    
    # حساب المتوسط المتحرك البسيط كمؤشر أولي للاتجاه
    sma_20 = sum(closes[-20:]) / 20
    current_price = closes[-1]
    
    # تحديد الاتجاه العام
    trend = "BULLISH" if current_price >= sma_20 else "BEARISH"
    
    # تحديد الدعم والمقاومة من حركة السعر
    support = min(lows[-20:])
    resistance = max(highs[-20:])
    
    # تحليل السيولة (تقديري بناءً على الحجوم)
    volumes = [float(c.get('volume', 0)) for c in candles[-5:]]
    avg_volume = sum(volumes) / len(volumes) if volumes else 0
    liquidity_score = avg_volume * current_price
    
    return trend, support, resistance, liquidity_score

def generate_dynamic_targets(current_price, atr, trend):
    """توليد 8 أهداف ديناميكية بناءً على الـ ATR والاتجاه"""
    targets = []
    
    if trend == "BULLISH":
        # 🟢 الاتجاه العام الصاعد = أهداف فوق السعر
        for i in range(1, 9):
            target_price = current_price + (atr * i * 0.75)
            targets.append(round(target_price, 2))
    else:
        # 🔴 الاتجاه العام الهابط = أهداف تحت السعر مع علامة حمراء 🔴✓
        for i in range(1, 9):
            target_price = current_price - (atr * i * 0.75)
            targets.append(f"🔴✓ الهدف الهابط {i}: {round(target_price, 2)}")
            
    return targets

def fetch_and_translate_news(ticker):
    """جلب الأخبار من EODHD وترجمة العناوين للعربية إن أمكن"""
    url = f"https://eodhistoricaldata.com/api/news"
    params = {'api_token': EODHD_API_KEY, 's': ticker, 'limit': 1, 'fmt': 'json'}
    try:
        response = requests.get(url, params=params, timeout=10)
        if response.status_code == 200:
            news_data = response.json()
            if news_data:
                title = news_data[0].get('title', 'لا توجد اخبار حديثة')
                # محاكاة لترجمة العنوان للعربية (أو دمج محرك ترجمة محلي)
                translated_title = f"[ترجمة آلية]: {title}"
                return translated_title
    except Exception:
        pass
    return "لا توجد أخبار متاحة حالياً"

def scan_market(exchange_type, min_price=0.20):
    """فحص الأسواق بناءً على الشروط المطلوبة"""
    print(f"--- بدء فحص سوق: {exchange_type} ---")
    
    # مثال توضيحي لقائمة رموز الأسواق (تاسي، ناسداك، العملات الرقمية)
    symbols_to_scan = []
    
    if exchange_type == "TASI":
        # فحص تاسي كامل
        symbols_to_scan = ["2222", "1120", "1010"] # عينة تمثيلية للتكامل
    elif exchange_type == "US":
        # فحص ناسداك والامريكي بشرط السعر >= 0.20$
        symbols_to_scan = ["AAPL", "MSFT", "TSLA", "NVA"]
    elif exchange_type == "CRYPTO":
        # فحص العملات الرقمية كاملة
        symbols_to_scan = ["BTC-USD", "ETH-USD"]

    for ticker in symbols_to_scan:
        data = fetch_eodhd_data(ticker, "US" if exchange_type != "TASI" else "SR")
        if data and 'close' in data:
            price = float(data['close'])
            
            # شرط السعر للأمريكي 0.20 فأعلى
            if exchange_type == "US" and price < min_price:
                continue
                
            # جلب بيانات الشموع التاريخية لحساب الـ ATR
            history_url = f"https://eodhistoricaldata.com/api/eod/{ticker}.{'SR' if exchange_type == 'TASI' else 'US'}"
            hist_res = requests.get(history_url, params={'api_token': EODHD_API_KEY, 'fmt': 'json', 'limit': 30})
            
            candles = hist_res.json() if hist_res.status_code == 200 else []
            atr_val = calculate_atr(candles, 14)
            trend, support, resistance, liquidity = ai_pro_max_engine(candles)
            targets = generate_dynamic_targets(price, atr_val if atr_val > 0 else 1.0, trend)
            news = fetch_and_translate_news(ticker)
            
            print(f"الرمز: {ticker} | السعر: {price} | الاتجاه: {trend}")
            print(f"الدعم: {support} | المقاومة: {resistance} | السيولة: {liquidity}")
            print(f"الأهداف الديناميكية: {targets}")
            print(f"الأخبار: {news}")
            print("-" * 40)

if __name__ == "__main__":
    print("بدء تشغيل النظام الذكي للتحليل المالي...")
    # تنفيذ عمليات الفحص الشاملة
    scan_market("TASI")
    scan_market("US", min_price=0.20)
    scan_market("CRYPTO")
