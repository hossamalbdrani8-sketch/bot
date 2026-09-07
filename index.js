
const express = require("express");
const TelegramBot = require("node-telegram-bot-api");
const yahooFinance = require("yahoo-finance2").default;

yahooFinance.setGlobalConfig({ logger: { info: () => {}, warn: () => {}, error: () => {} } });

const app = express();
app.use(express.json());

// مسار رئيسي لكي يبقى السيرفر نشطاً على Railway
app.get("/", (req, res) => {
    res.send("Market Bots are active and running!");
});

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
            trend: change >= 0 ? "صعود قوي 🟢 (فوق VWAP)" : "ضغط سلبي 🔴 (تحت VWAP)",
            targets: [
                (price * 1.01).toFixed(2),
                (price * 1.02).toFixed(2),
                (price * 1.03).toFixed(2),
                (price * 1.04).toFixed(2),
                (price * 1.05).toFixed(2),
                (price * 1.06).toFixed(2)
            ]
        };
    } catch (error) {
        return null;
    }
}

// تفاعل بوت السوق السعودي
tasiBot.on('message', async (msg) => {
    const chatId = msg.chat.id;
    await tasiBot.sendMessage(chatId, "🇸🇦 جاري تحليل وتحديث أسهم السوق السعودي (تاسي)...");

    for (let stock of tasiStocks) {
        const data = await getStockData(stock.symbol);
        if (data) {
            const icon = data.change >= 0 ? "🟢" : "🔴";
            const report = 
                `📊 *تداول السوق السعودي (تاسي)*\n` +
                `🔹 *الشركة:* ${stock.name} (${stock.symbol})\n` +
                `----------------------------------\n` +
                `💰 *السعر:* \`${data.price} SAR\`\n` +
                `📈 *التغير:* ${icon} \`${data.change >= 0 ? '+' : ''}${data.change}%\`\n` +
                `📉 *EMA (7):* \`${data.ema}\`\n` +
                `⚡ *الاتجاه والزخم:* ${data.trend}\n\n` +
                `🎯 *الأهداف السعرية:*\n` +
                `  • الهدف 1: \`${data.targets[0]}\`\n` +
                `  • الهدف 2: \`${data.targets[1]}\`\n` +
                `  • الهدف 3: \`${data.targets[2]}\`\n` +
                `  • الهدف 4: \`${data.targets[3]}\`\n` +
                `  • الهدف 5: \`${data.targets[4]}\`\n` +
                `  • الهدف 6: \`${data.targets[5]}\``;

            try {
                await tasiBot.sendMessage(chatId, report, { parse_mode: "Markdown" });
            } catch (e) {}
            await new Promise(r => setTimeout(r, 700));
        }
    }
    await tasiBot.sendMessage(chatId, "✅ انتهى تحليل السوق السعودي.");
});

// تفاعل بوت السوق الأمريكي
usBot.on('message', async (msg) => {
    const chatId = msg.chat.id;
    await usBot.sendMessage(chatId, "🇺🇸 جاري تحليل وتحديث أسهم السوق الأمريكي...");

    for (let stock of usStocks) {
        const data = await getStockData(stock.symbol);
        if (data) {
            const icon = data.change >= 0 ? "🟢" : "🔴";
            const report = 
                `📊 *تداول السوق الأمريكي*\n` +
                `🔹 *Company:* ${stock.name} (${stock.symbol})\n` +
                `----------------------------------\n` +
                `💰 *Price:* \`${data.price} USD\`\n` +
                `📈 *Change:* ${icon} \`${data.change >= 0 ? '+' : ''}${data.change}%\`\n` +
                `📉 *EMA (7):* \`${data.ema}\`\n` +
                `⚡ *Trend & Momentum:* ${data.trend}\n\n` +
                `🎯 *Price Targets:*\n` +
                `  • Target 1: \`${data.targets[0]}\`\n` +
                `  • Target 2: \`${data.targets[1]}\`\n` +
                `  • Target 3: \`${data.targets[2]}\`\n` +
                `  • Target 4: \`${data.targets[3]}\`\n` +
                `  • Target 5: \`${data.targets[4]}\`\n` +
                `  • Target 6: \`${data.targets[5]}\``;

            try {
                await usBot.sendMessage(chatId, report, { parse_mode: "Markdown" });
            } catch (e) {}
            await new Promise(r => setTimeout(r, 700));
        }
    }
    await usBot.sendMessage(chatId, "✅ انتهى تحليل السوق الأمريكي.");
});

const PORT = process.env.PORT || 3000;
app.listen(PORT, () => {
    console.log(`Market Bots running on port ${PORT}`);
});
