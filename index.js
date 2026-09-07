
const express = require("express");
const TelegramBot = require("node-telegram-bot-api");
const yahooFinance = require("yahoo-finance2").default;

yahooFinance.setGlobalConfig({ logger: { info: () => {}, warn: () => {}, error: () => {} } });

const app = express();
app.use(express.json());

// 1. بوت السوق السعودي (تاسي)
const TASI_TOKEN = "7772382813:AAECFDY04AXNEf-Q98_65UheUEz7u2HymJw";
const tasiBot = new TelegramBot(TASI_TOKEN, { polling: true });

const tasiStocks = [
    { symbol: "2222.SR", name: "أرامكو السعودية" },
    { symbol: "1120.SR", name: "مصرف الراجحي" },
    { symbol: "1010.SR", name: "بنك الرياض" },
    { symbol: "1180.SR", name: "البنك الأهلي" },
    { symbol: "2010.SR", name: "سابك" },
    { symbol: "4200.SR", name: "الدريس" },
    { symbol: "7010.SR", name: "اتصالات السعودية (STC)" }
];

// 2. بوت السوق الأمريكي
const US_TOKEN = "8652994768:AAHg_ABByrZdvlljJ1dQfs6LSmBl37XMPXk";
const usBot = new TelegramBot(US_TOKEN, { polling: true });

const usStocks = [
    { symbol: "AAPL", name: "Apple Inc." },
    { symbol: "TSLA", name: "Tesla Inc." },
    { symbol: "MSFT", name: "Microsoft Corporation" },
    { symbol: "NVDA", name: "NVIDIA Corporation" },
    { symbol: "LCII", name: "LCI Industries" }
];

async function getStockData(symbol) {
    try {
        const result = await yahooFinance.quote(symbol);
        if (!result || typeof result.regularMarketPrice !== 'number') return null;

        const price = result.regularMarketPrice;
        const change = result.regularMarketChangePercent || 0;

        return {
            price: price.toFixed(2),
            change: Number(change.toFixed(2)),
            ema: (price * 0.99).toFixed(2),
            trend: change >= 0 ? "صعود لحظي 🟢" : "ضغط بيعي 🔴",
            targets: [
                (price * 1.01).toFixed(2),
                (price * 1.02).toFixed(2),
                (price * 1.03).toFixed(2),
                (price * 1.04).toFixed(2)
            ]
        };
    } catch (error) {
        return null;
    }
}

// تشغيل بوت تاسي
tasiBot.on('message', async (msg) => {
    const chatId = msg.chat.id;
    tasiBot.sendMessage(chatId, "🇸🇦 جاري فحص أسهم السوق السعودي (تاسي)...");
    
    for (let stock of tasiStocks) {
        const data = await getStockData(stock.symbol);
        if (data) {
            const report = 
                `🇸🇦 *السوق السعودي: ${stock.name}* (${stock.symbol})\n` +
                `----------------------------------\n` +
                `💰 *السعر:* \`${data.price} SAR\`\n` +
                `📈 *التغير:* \`${data.change >= 0 ? '+' : ''}${data.change}%\`\n` +
                `📉 *مؤشر EMA:* \`${data.ema}\`\n` +
                `⚡ *الاتجاه:* ${data.trend}\n\n` +
                `🎯 *الأهداف السعرية:*\n` +
                `  • هدف 1: \`${data.targets[0]}\`\n` +
                `  • هدف 2: \`${data.targets[1]}\`\n` +
                `  • هدف 3: \`${data.targets[2]}\`\n` +
                `  • هدف 4: \`${data.targets[3]}\``;

            try {
                await tasiBot.sendMessage(chatId, report, { parse_mode: "Markdown" });
            } catch (e) {}
            await new Promise(r => setTimeout(r, 600));
        }
    }
    tasiBot.sendMessage(chatId, "✅ انتهى فحص السوق السعودي.");
});

// تشغيل البوت الأمريكي
usBot.on('message', async (msg) => {
    const chatId = msg.chat.id;
    usBot.sendMessage(chatId, "🇺🇸 جاري فحص أسهم السوق الأمريكي...");

    for (let stock of usStocks) {
        const data = await getStockData(stock.symbol);
        if (data) {
            const report = 
                `🇺🇸 *السوق الأمريكي: ${stock.name}* (${stock.symbol})\n` +
                `----------------------------------\n` +
                `💰 *السعر:* \`${data.price} USD\`\n` +
                `📈 *التغير:* \`${data.change >= 0 ? '+' : ''}${data.change}%\`\n` +
                `📉 *مؤشر EMA:* \`${data.ema}\`\n` +
                `⚡ *الاتجاه:* ${data.trend}\n\n` +
                `🎯 *الأهداف السعرية:*\n` +
                `  • هدف 1: \`${data.targets[0]}\`\n` +
                `  • هدف 2: \`${data.targets[1]}\`\n` +
                `  • هدف 3: \`${data.targets[2]}\`\n` +
                `  • هدف 4: \`${data.targets[3]}\``;

            try {
                await usBot.sendMessage(chatId, report, { parse_mode: "Markdown" });
            } catch (e) {}
            await new Promise(r => setTimeout(r, 600));
        }
    }
    usBot.sendMessage(chatId, "✅ انتهى فحص السوق الأمريكي.");
});

const PORT = process.env.PORT || 3000;
app.listen(PORT, () => {
    console.log(`Both bots running on port ${PORT}`);
});
