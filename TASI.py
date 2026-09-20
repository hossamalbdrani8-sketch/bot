 🇸🇦 TASI.py — مستقل عن أمريكا والعملات
# يعتمد على SAHMK فقط لبيانات تاسي.
# لا يستهلك TWELVE_DATA_API_KEY.
# المتغيرات المستخدمة من Railway:
# TASI_TOKEN / SAHMK_API_KEY / CHAT_ID

import os
import time
import requests
from datetime import datetime
from zoneinfo import ZoneInfo

CHAT_ID = os.getenv("CHAT_ID", "").strip()
TASI_TOKEN = os.getenv("TASI_TOKEN", "").strip()
SAHMK_API_KEY = os.getenv("SAHMK_API_KEY", "").strip()

BASE = "https://api.sahmk.sa/api/v1"
RIYADH = ZoneInfo("Asia/Riyadh")

# SAHMK Free = 100 requests/day.
# نستخدم 3 طلبات سوق في كل دورة فقط:
# summary + gainers + losers
# مع فاصل 15 دقيقة داخل الجلسة حتى لا نستهلك الحصة.
SCAN_SECONDS = 15 * 60

session = requests.Session()
session.headers.update({
    "X-API-Key": SAHMK_API_KEY,
    "Accept-Encoding": "gzip",
    "User-Agent": "TASI-AI-PRO-MAX/1.0",
})

last_sent = {}
previous = {}


def sahmk(path, params=None):
    if not SAHMK_API_KEY:
        return None

    try:
        r = session.get(
            BASE + path,
            params=params or {},
            timeout=(10, 30),
        )
        if r.status_code == 429:
            print("🟠 SAHMK: تم بلوغ حد الطلبات — انتظار")
            return None
        if r.status_code != 200:
            print(f"🔴 SAHMK HTTP {r.status_code}: {path}")
            return None

        data = r.json()
        if isinstance(data, dict) and data.get("error"):
            print("🔴 SAHMK:", data.get("error"))
            return None
        return data

    except Exception as e:
        print("🔴 SAHMK:", e)
        return None


def telegram(text):
    if not TASI_TOKEN or not CHAT_ID:
        return False

    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TASI_TOKEN}/sendMessage",
            data={
                "chat_id": CHAT_ID,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            },
            timeout=20,
        )
        return r.ok
    except Exception as e:
        print("🔴 Telegram:", e)
        return False


def market_is_active():
    # التشغيل البرمجي 24/7، لكن إرسال إشارات تاسي يكون عندما
    # تكون بيانات SAHMK محدثة/جلسة السوق فعالة.
    now = datetime.now(RIYADH)

    # الأحد إلى الخميس
    if now.weekday() not in (6, 0, 1, 2, 3):
        return False

    # مزاد الافتتاح يبدأ 09:30، والتداول الرئيسي 10:00-15:00.
    # نبدأ مراقبة البيانات من 09:30 ونترك SAHMK يحدد حداثة البيانات.
    minutes = now.hour * 60 + now.minute
    return 9 * 60 + 30 <= minutes < 15 * 60


def extract(rows_key, data):
    if not isinstance(data, dict):
        return []
    rows = data.get(rows_key, [])
    return rows if isinstance(rows, list) else []


def collect():
    summary = sahmk("/market/summary/", {
        "index": "TASI",
        "data_mode": "delayed",
    })

    gainers = sahmk("/market/gainers/", {
        "index": "TASI",
        "limit": 50,
        "data_mode": "delayed",
    })

    losers = sahmk("/market/losers/", {
        "index": "TASI",
        "limit": 50,
        "data_mode": "delayed",
    })

    return summary, extract("gainers", gainers), extract("losers", losers)


def score(row, direction):
    try:
        ch = abs(float(row.get("change_percent", 0) or 0))
        vol = float(row.get("volume", 0) or 0)
    except Exception:
        return 0

    # درجة حركة وصفية مبنية فقط على البيانات التي يوفرها SAHMK.
    s = min(70, ch * 7)

    if vol > 10_000_000:
        s += 20
    elif vol > 3_000_000:
        s += 15
    elif vol > 1_000_000:
        s += 10
    elif vol > 250_000:
        s += 5

    return int(max(0, min(100, s)))


def alert(row, direction):
    symbol = str(row.get("symbol", "")).strip()
    if not symbol:
        return

    price = row.get("price", "-")
    change = row.get("change_percent", 0)
    volume = row.get("volume", 0)

    try:
        change_f = float(change)
    except Exception:
        change_f = 0.0

    # لا نكرر نفس الإشارة لنفس الرمز إلا إذا تغيرت الحركة بشكل واضح.
    key = f"{symbol}:{direction}"
    old = last_sent.get(key)

    if old is not None and abs(change_f - old) < 1.0:
        return

    # لا نرسل كل تغير صغير؛ نرسل الحركة الواضحة فقط.
    if abs(change_f) < 2.0:
        return

    last_sent[key] = change_f

    if direction == "UP":
        badge = "🟢 <b>حركة صاعدة</b>"
        arrow = "↗️"
    else:
        badge = "🔴 <b>حركة هابطة</b>"
        arrow = "↘️"

    s = score(row, direction)

    text = (
        "💀🚀 <b>AI PRO MAX — تاسي</b>\n"
        "🇸🇦 <b>SAHMK</b>\n\n"
        f"📌 <b>{symbol}</b>\n"
        f"{badge} {arrow}   <b>{s}/100</b>\n"
        f"💰 السعر: <b>{price}</b>\n"
        f"📊 التغير: <b>{change_f:+.2f}%</b>\n"
        f"📦 الحجم: <b>{volume:,}</b>\n\n"
        "🔄 <b>المصدر: بيانات SAHMK</b>\n"
        "🕒 <b>وقت الرصد:</b> "
        f"{datetime.now(RIYADH).strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        "⚠️ <i>رصد آلي وليس توصية استثمارية.</i>"
    )

    if telegram(text):
        print(f"📲 TASI {symbol} {direction} {change_f:+.2f}%")


def run_cycle():
    print("=" * 60)
    print("🇸🇦 TASI مستقل — SAHMK فقط")
    print(datetime.now(RIYADH).strftime("%Y-%m-%d %H:%M:%S"))

    summary, gainers, losers = collect()

    if summary:
        print(
            "🟢 TASI:",
            summary.get("index_value", "-"),
            "| change=",
            summary.get("index_change_percent", "-"),
            "| mood=",
            summary.get("market_mood", "-"),
        )

    print(f"🟢 Gainers: {len(gainers)} | 🔴 Losers: {len(losers)}")

    # نحدد أفضل حركة صاعدة وأفضل حركة هابطة من بيانات SAHMK.
    if gainers:
        best_up = max(
            gainers,
            key=lambda x: float(x.get("change_percent", 0) or 0)
        )
        alert(best_up, "UP")

    if losers:
        best_down = min(
            losers,
            key=lambda x: float(x.get("change_percent", 0) or 0)
        )
        alert(best_down, "DOWN")


def main():
    print("💀🚀 TASI SERVICE START")
    print("🇸🇦 SAHMK: مستقل")
    print("📲 Telegram: " + ("OK" if TASI_TOKEN and CHAT_ID else "MISSING"))
    print("🟢 SAHMK: " + ("OK" if SAHMK_API_KEY else "MISSING"))
    print("⏱️ الخدمة تعمل 24/7، والإشارات تُرسل عند توفر جلسة/بيانات تاسي.")

    if not TASI_TOKEN or not CHAT_ID or not SAHMK_API_KEY:
        print("❌ متغير مطلوب غير موجود: TASI_TOKEN / SAHMK_API_KEY / CHAT_ID")
        return

    while True:
        try:
            if market_is_active():
                run_cycle()
            else:
                print(
                    "⏸️ تاسي خارج جلسة المراقبة — "
                    "الخدمة ما زالت تعمل وتنتظر بيانات SAHMK."
                )
        except Exception as e:
            print("🔴 TASI loop:", e)

        time.sleep(SCAN_SECONDS)


if __name__ == "__main__":
    main()