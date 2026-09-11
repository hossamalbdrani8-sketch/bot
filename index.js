
// ============================================================
// 🤖 AI PRO MAX - INSTANT TEST & SCANNER
// ============================================================

"use strict";

const express = require("express");
const TelegramBot = require("node-telegram-bot-api");

const EODHD_API_KEY = process.env.EODHD_API_KEY;

const US_TOKEN = process.env.US_TOKEN;
const TASI_TOKEN = process.env.TASI_TOKEN;
const CRYPTO_TOKEN = process.env.CRYPTO_TOKEN;

const PORT = Number(process.env.PORT || 3000);

const app = express();
app.use(express.json());

app.get("/", (req, res) => res.status(200).send("AI PRO MAX is running"));
app.get("/health", (req, res) => res.status(200).json({ status: "online" }));

app.listen(PORT, "0.0.0.0", () => {
    console.log(`Server running on port ${PORT}`);
});

const usBot = US_TOKEN ? new TelegramBot(US_TOKEN, { polling: true }) : null;
const tasiBot = TASI_TOKEN ? new TelegramBot(TASI_TOKEN, { polling: true }) : null;
const cryptoBot = CRYPTO_TOKEN ? new TelegramBot(CRYPTO_TOKEN, { polling: true }) : null;

const usChatIds = new Set();
const tasiChatIds = new Set();
const cryptoChatIds = new Set();

// دالة طلبات EODHD المبسطة
async function eodhd(path, params = {}) {
    if (!EODHD_API_KEY) throw new Error("API Key missing");
    const url = new URL(`https://eodhd.com/api/${path}`);
    url.searchParams.set("api_token", EODHD_API_KEY);
    url.searchParams.set("fmt", "json");
    for (const [k, v] of Object.entries(params)) url.searchParams.set(k, v);

    const res = await fetch(url);
    const text = await res.text();
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return text ? JSON.parse(text) : null;
}

// دالة تفاعلية لربط البوتات وإرسال نتيجة فورية للتأكد
function setupBot(bot, chatIds, marketName) {
    if (!bot) return;
    bot.onText(/\/start|\/scan/, async (msg) => {
        const chatId = msg.chat.id;
        chatIds.add(chatId);
        
        // رسالة تایید فورية لترى أن البوت يستجيب
        await bot.sendMessage(chatId, `✅ تم استلام أمرك في ${marketName}!\nجاري جلب وعرض عينة من الأسهم للتأكد من الاتصال...`, { parse_mode: "HTML" });

        try {
            let symbols = [];
            if (marketName.includes("الأمريكي")) {
                const data = await eodhd("exchange-symbol-list/US", { type: "common_stock" });
                symbols = data.slice(0, 3); // أول 3 أسهم للاختبار السريع
            } else if (marketName.includes("السعودي")) {
                const data = await eodhd("exchange-symbol-list/SR", { type: "common_stock" });
                symbols = data.slice(0, 3);
            } else {
                const data = await eodhd("exchange-symbol-list/CC");
                symbols = data.slice(0, 3);
            }

            for (const item of symbols) {
                const code = item.Code || item.code;
                const name = item.Name || code;
                const symbolStr = marketName.includes("العملات") ? `${code}.CC` : (marketName.includes("السعودي") ? `${code}.SR` : `${code}.US`);
                
                // جلب بيانات الأسعار آخر يومين
                const eodData = await eodhd(`eod/${symbolStr}`, { period: "d", limit: 5 });
                const lastPrice = eodData && eodData.length > 0 ? eodData[eodData.length - 1].close : "غير متوفر";

                const message = `<b>📊 فحص تجريبي - ${marketName}</b>\n\n` +
                                `<b>الرمز:</b> ${symbolStr}\n` +
                                `<b>الاسم:</b> ${name}\n` +
                                `<b>السعر الحالي:</b> ${lastPrice}\n` +
                                `<b>الحالة:</b> 🟢 متصل ويدعم الفحص الفوري`;

                await bot.sendMessage(chatId, message, { parse_mode: "HTML" });
            }
        } catch (err) {
            await bot.sendMessage(chatId, `⚠️ ملاحظة جلب البيانات: ${err.message}`);
        }
    });
}

setupBot(usBot, usChatIds, "السوق الأمريكي");
setupBot(tasiBot, tasiChatIds, "السوق السعودي");
setupBot(cryptoBot, cryptoChatIds, "العملات الرقمية");
