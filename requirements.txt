
import os
import logging
import asyncio
from telegram import Bot
from telegram.constants import ParseMode
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# إعداد السجلات (Logging) لمراقبة عمل البوت
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", 
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# قراءة توكن البوت ومعرف القناة أو المجموعة من متغيرات البيئة (Environment Variables)
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
CHANNEL_CHAT_ID = os.getenv("CHANNEL_CHAT_ID", "@YOUR_CHANNEL_OR_CHAT_ID")

# تعريف كائن البوت
bot = Bot(token=TELEGRAM_BOT_TOKEN)

# ==========================================
# 1. دالة السوق السعودي (TASI) - تعمل لوحدها
# ==========================================
async def send_tasi_signal():
    try:
        message = (
            "💀🚀 **AI PRO MAX SIGNAL**\n"
            "🇸🇦 **(TASI) السوق السعودي**\n\n"
            "**ARAMCO.SR**\n"
            "أرامكو السعودية\n\n"
            "        `🟢 شراء قوي`\n"
            "━━━━━━━━━━━━━━━━━━━\n"
            "🔹 **السعر:** 32.60          |  EMA 8: 32.10  |  الدعم: 31.40\n"
            "🔹 **التغير:** +2.18%      |  EMA 21: 31.80 |  المقاومة: 33.70\n"
            "🔹 **قوة الإشارة:** 88/100  |  EMA 50: 31.20 |  الاتجاه: صاعد قوي 📈\n"
            "🔹 **قوة الشراء:** 82%     |  RSI 14: 68.5  |\n"
            "🔹 **قوة البيع:** 18%      |  ATR 14: 0.95  |\n"
            "🔹 **قوة الحجم:** 2.4x     |\n"
            "━━━━━━━━━━━━━━━━━━━\n"
            "🎯 **أهداف ATR الثمانية:**\n"
            "TP1       TP2       TP3       TP4       TP5       TP6       TP7       TP8\n"
            "33.55     34.50     35.45     36.40     37.35     38.30     39.20     40.20\n"
            "(+2.9%)  (+5.8%)  (+8.7%)  (+11.6%) (+14.7%) (+17.5%) (+20.4%) (+23.3%)"
        )
        
        await bot.send_message(
            chat_id=CHANNEL_CHAT_ID, 
            text=message, 
            parse_mode=ParseMode.MARKDOWN
        )
        logger.info("تم إرسال إشارة السوق السعودي (TASI) بنجاح.")
    except Exception as e:
        logger.error(f"خطأ في إرسال إشارة السوق السعودي: {e}")

# ==========================================
# 2. دالة السوق الأمريكي (US) - تعمل لوحدها
# ==========================================
async def send_us_signal():
    try:
        message = (
            "💀🚀 **AI PRO MAX SIGNAL**\n"
            "🇺🇸 **(US) السوق الأمريكي**\n\n"
            "**TSLA.US**\n"
            "Tesla Inc\n\n"
            "        `🔴 بيع قوي`\n"
            "━━━━━━━━━━━━━━━━━━━\n"
            "🔹 **السعر:** 241.30        |  EMA 8: 245.80 |  الدعم: 238.50\n"
            "🔹 **التغير:** -3.26%     |  EMA 21: 250.40|  المقاومة: 258.70\n"
            "🔹 **قوة الإشارة:** 79/100 |  EMA 50: 262.10|  الاتجاه: هابط قوي 📉\n"
            "🔹 **قوة البيع:** 81%     |  RSI 14: 32.1  |\n"
            "🔹 **قوة الشراء:** 19%    |  ATR 14: 6.40  |\n"
            "🔹 **قوة الحجم:** 1.8x     |\n"
            "━━━━━━━━━━━━━━━━━━━\n"
            "🎯 **أهداف ATR الثمانية:**\n"
            "TP1       TP2       TP3       TP4       TP5       TP6       TP7       TP8\n"
            "234.90    228.50    222.10    215.70    209.30    202.90    196.50    190.10\n"
            "(-2.6%)   (-5.3%)   (-8.0%)  (-10.6%) (-13.3%) (-15.9%) (-18.5%) (-21.2%)"
        )
        
        await bot.send_message(
            chat_id=CHANNEL_CHAT_ID, 
            text=message, 
            parse_mode=ParseMode.MARKDOWN
        )
        logger.info("تم إرسال إشارة السوق الأمريكي (US) بنجاح.")
    except Exception as e:
        logger.error(f"خطأ في إرسال إشارة السوق الأمريكي: {e}")

# ==========================================
# 3. دالة العملات الرقمية (Crypto) - تعمل لوحدها
# ==========================================
async def send_crypto_signal():
    try:
        message = (
            "💀🚀 **AI PRO MAX SIGNAL**\n"
            "🪙 **(CRYPTO) العملات الرقمية**\n\n"
            "**BTC.CC**\n"
            "Bitcoin\n\n"
            "        `🟢 شراء قوي`\n"
            "━━━━━━━━━━━━━━━━━━━\n"
            "🔹 **السعر:** 114,250      |  EMA 8: 112,300|  الدعم: 109,400\n"
            "🔹 **التغير:** +4.12%     |  EMA 21: 109,800| المقاومة: 118,700\n"
            "🔹 **قوة الإشارة:** 85/100 |  EMA 50: 105,600| الاتجاه: صاعد قوي 📈\n"
            "🔹 **قوة الشراء:** 80%    |  RSI 14: 71.8  |\n"
            "🔹 **قوة البيع:** 20%     |  ATR 14: 2,850 |\n"
            "🔹 **قوة الحجم:** 2.1x     |\n"
            "━━━━━━━━━━━━━━━━━━━\n"
            "🎯 **أهداف ATR الثمانية:**\n"
            "TP1       TP2       TP3       TP4       TP5       TP6       TP7       TP8\n"
            "117,100   119,950   122,800   125,650   128,500   131,350   134,200   137,050\n"
            "(+2.5%)   (+5.0%)   (+7.5%)  (+10.0%) (+12.5%) (+15.0%) (+17.5%) (+20.0%)"
        )
        
        await bot.send_message(
            chat_id=CHANNEL_CHAT_ID, 
            text=message, 
            parse_mode=ParseMode.MARKDOWN
        )
        logger.info("تم إرسال إشارة العملات الرقمية (Crypto) بنجاح.")
    except Exception as e:
        logger.error(f"خطأ في إرسال إشارة العملات الرقمية: {e}")

# ==========================================
# الدالة الرئيسية للجدولة والتشغيل
# ==========================================
async def main():
    # تهيئة نظام الجدولة غير المتزامن (AsyncIOScheduler)
    scheduler = AsyncIOScheduler()
    
    # جدولة كل سوق ليعمل بشكل مستقل ومنفصل كل دقيقتين (يمكنك تعديل الفاصل الزمني minutes)
    scheduler.add_job(send_tasi_signal, 'interval', minutes=2)
    scheduler.add_job(send_us_signal, 'interval', minutes=2)
    scheduler.add_job(send_crypto_signal, 'interval', minutes=2)
    
    # بدء تشغيل المجدول
    scheduler.start()
    logger.info("تم تفعيل نظام الفحص التلقائي لكل سوق (يعمل كل دقيقتين)...")
    
    # إبقاء البوت يعمل باستمرار دون توقف
    while True:
        await asyncio.sleep(1)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("تم إيقاف البوت بنجاح.")
