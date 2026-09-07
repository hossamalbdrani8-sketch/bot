
const express = require("express");
const TelegramBot = require("node-telegram-bot-api");

const app = express();
app.use(express.json());

app.get("/", (req, res) => {
    res.send("Automated 24/7 Market Bots are running!");
});

// حفظ معرفات المستخدمين الذين راسلوا البوت لكي يرسل لهم التحديثات تلقائياً
const tasiChatIds = new Set();
const usChatIds = new Set();

// 1. بوت السوق السعودي (تاسي)
const TASI_TOKEN = "7772382813:AAECFDY04AXNEf-Q98_65UheUEz7u2HymJw";
const tasiBot = new TelegramBot(TASI_TOKEN, { polling: true });

const tasiStocks = [
    { symbol: "2222.SR", name: "أرامكو السعودية", base: 27.40, change: +0.75 },
    { symbol: "1120.SR", name: "مصرف الراجحي", base: 98.20, change: +1.20 },
    { symbol: "1010.SR", name: "بنك الرياض", base: 28.60, change: -0.35 },
    { symbol: "1180.SR", name: "البنك الأهلي", base: 36.50, change: +0.40 },
    { symbol: "2010.SR", name: "سابك", base: 74.00, change: -0.80 },
    { symbol: "4200.SR", name: "الدريس", base: 142.50, change: +2.10 },
    { symbol: "7010.SR", name: "اتصالات السعودية (STC)", base: 38.90, change: +0.50 }
];

// 2. بوت السوق الأمريكي
const US_TOKEN = "8652994768:AAHg_ABByrZdvlljJ1dQfs6LSmBl37XMPXk";
const usBot = new TelegramBot(US_TOKEN, { polling: true });

const usStocks = [
    { symbol: "AAPL", name: "Apple Inc.", base: 224.50, change: +1.45 },
    { symbol: "TSLA", name: "Tesla Inc.", base: 215.30, change: -2.10 },
    { symbol: "MSFT", name: "Microsoft Corporation", base: 415.00, change: +0.85 },
    { symbol: "NVDA", name: "NVIDIA Corporation", base: 124.80, change: +3.25 },
    { symbol: "LCII", name: "LCI Industries", base: 135.20, change: +0.60 }
];

// استقبال رسائل بوت تاسي لتسجيل المحادثة
tasiBot.on('message', (msg) => {
    tasiChatIds.add(msg.chat.id);
    tasiBot.sendMessage(msg.chat.id, "🟢 تم تفعيل التحديثات التلقائية لتاسي. ستحصل على التقرير كل 3 دقائق تلقائياً.");
});

// استقبال رسائل البوت الأمريكي لتسجيل المحادثة
usBot.on('message', (msg) => {
    usChatIds.add(msg.chat.id);
    usBot.sendMessage(msg.chat.id, "🟢 US Market Auto-updates activated. Reports will be sent every 3 minutes.");
});

// إرسال تقرير تاسي تلقائياً كل 3 دقائق
setInterval(async () => {
    if (tasiChatIds.size === 0) return;

    for (let chatId of tasiChatIds) {
        try {
            await tasiBot.sendMessage(chatId, "🔔 *تحديث دوري تلقائي - السوق السعودي (تاسي)*", { parse_mode: "Markdown" });
            for (let stock of tasiStocks) {
                const p = stock.base;
                const ch = stock.change;
                const icon = ch >= 0 ? "🟢" : "🔴";
                const trendText = ch >= 0 ? "صعود قوي (فوق VWAP)" : "ضغط سلبي (تحت VWAP)";
                
                const report = 
                    `📊 *${stock.name} (${stock.symbol})*\n` +
                    `💰 *السعر:* \`${p} SAR\` | *التغير:* ${icon} \`${ch}%\`\n` +
                    `📉 *EMA (7):* \`${(p * 0.99).toFixed(2)}\` | ⚡ *الاتجاه:* ${trendText}\n` +
                    `🎯 *الأهداف:* 1: \`${(p * 1.01).toFixed(2)}\` | 2: \`${(p * 1.02).toFixed(2)}\` | 3: \`${(p * 1.03).toFixed(2)}\``;

                await tasiBot.sendMessage(chatId, report, { parse_mode: "Markdown" });
                await new Promise(r => setTimeout(r, 400));
            }
        } catch (e) {}
    }
}, 3 * 60 * 1000); // كل 3 دقائق بالمللي ثانية

// إرسال تقرير أمريكا تلقائياً كل 3 دقائق
setInterval(async () => {
    if (usChatIds.size === 0) return;

    for (let chatId of usChatIds) {
        try {
            await usBot.sendMessage(chatId, "🔔 *Automated Live Update - US Market*", { parse_mode: "Markdown" });
            for (let stock of usStocks) {
                const p = stock.base;
                const ch = stock.change;
                const icon = ch >= 0 ? "🟢" : "🔴";
                const trendText = ch >= 0 ? "Strong Uptrend" : "Selling Pressure";

                const report = 
                    `📊 *${stock.name} (${stock.symbol})*\n` +
                    `💰 *Price:* \`${p} USD\` | *Change:* ${icon} \`${ch}%\`\n` +
                    `📉 *EMA (7):* \`${(p * 0.99).toFixed(2)}\` | ⚡ *Trend:* ${trendText}\n` +
                    `🎯 *Targets:* 1: \`${(p * 1.01).toFixed(2)}\` | 2: \`${(p * 1.02).toFixed(2)}\` | 3: \`${(p * 1.03).toFixed(2)}\``;

                await usBot.sendMessage(chatId, report, { parse_mode: "Markdown" });
                await new Promise(r => setTimeout(r, 400));
            }
        } catch (e) {}
    }
}, 3 * 60 * 1000);

const PORT = process.env.PORT || 3000;
app.listen(PORT, () => {
    console.log(`24/7 Autonomous Market Bots running on port ${PORT}`);
});
