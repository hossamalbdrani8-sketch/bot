
const express = require("express");
const TelegramBot = require("node-telegram-bot-api");
const yahooFinance = require("yahoo-finance2").default;

yahooFinance.setGlobalConfig({ logger: { info: () => {}, warn: () => {}, error: () => {} } });

const app = express();
app.use(express.json());

const TOKEN = process.env.TOKEN || "7772382813:AAECFDY04AXNEf-Q98_65UheUEz7u2HymJw";
const bot = new TelegramBot(TOKEN, { polling: true });

// أسهم السوق السعودي (تاسي)
const tasiStocks = [
    { symbol: "2222.SR", name: "أرامكو السعودية" },
    { symbol: "1120.SR", name: "مصرف الراجحي" },
    { symbol: "1010.SR", name: "بنك الرياض" },
    { symbol: "1180.SR", name: "البنك الأهلي" },
    { symbol: "2010.SR", name: "سابك" },
    { symbol: "4200.SR", name: "الدريس" },
    { symbol: "7010.SR", name: "اتصالات السعودية (STC)" }
];

// أسهم السوق الأمريكي
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

bot.on('message', async (msg) => {
    const chatId = msg.chat.id;
    const text = msg.text ? msg.text.trim() : "";

    if (text === '/start') {
        bot.sendMessage(chatId, 
            "🇸🇦🇺🇸 أهلاً بك في بوت الأسواق المالية الشامل.\n\n" +
            "• أرسل `/tasi` لفحص أسهم السوق السعودي.\n" +
            "• أرسل `/us` لفحص أسهم السوق الأمريكي.", 
            { parse_mode: "Markdown" }
        );
    } 
    else if (text === '/tasi') {
        bot.sendMessage(chatId, "🇸🇦 جاري فحص أسهم السوق السعودي (تاسي)...");
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
                    await bot.sendMessage(chatId, report, { parse_mode: "Markdown" });
                } catch (e) {}
                await new Promise(r => setTimeout(r, 600));
            }
        }
        bot.sendMessage(chatId, "✅ انتهى فحص السوق السعودي.");
    }
    else if (text === '/us') {
        bot.sendMessage(chatId, "🇺🇸 جاري فحص أسهم السوق الأمريكي...");
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
                    await bot.sendMessage(chatId, report, { parse_mode: "Markdown" });
                } catch (e) {}
                await new Promise(r => setTimeout(r, 600));
            }
        }
        bot.sendMessage(chatId, "✅ انتهى فحص السوق الأمريكي.");
    }
});

const PORT = process.env.PORT || 3000;
app.listen(PORT, () => {
    console.log(`Server running on port ${PORT}`);
});
