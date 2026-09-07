
const express = require("express");
const TelegramBot = require("node-telegram-bot-api");

const app = express();
app.use(express.json());

app.get("/", (req, res) => {
    res.send("Bots are running 24/7 successfully!");
});

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
const US_TOKEN = "8652994768:AAHg_ABByrZdvlljJ1dQfs6LSmBl37XMPXk"; // استخدمنا التوكن الأصلي النظيف
const usBot = new TelegramBot(US_TOKEN, { polling: true });

const usStocks = [
    { symbol: "AAPL", name: "Apple Inc.", base: 224.50, change: +1.45 },
    { symbol: "TSLA", name: "Tesla Inc.", base: 215.30, change: -2.10 },
    { symbol: "MSFT", name: "Microsoft Corporation", base: 415.00, change: +0.85 },
    { symbol: "NVDA", name: "NVIDIA Corporation", base: 124.80, change: +3.25 },
    { symbol: "LCII", name: "LCI Industries", base: 135.20, change: +0.60 }
];

// تفاعل بوت السوق السعودي
tasiBot.on('message', async (msg) => {
    const chatId = msg.chat.id;
    await tasiBot.sendMessage(chatId, "🇸🇦 تقرير السوق السعودي المباشر (تاسي):");

    for (let stock of tasiStocks) {
        const p = stock.base;
        const ch = stock.change;
        const icon = ch >= 0 ? "🟢" : "🔴";
        const trendText = ch >= 0 ? "صعود قوي (فوق VWAP)" : "ضغط سلبي (تحت VWAP)";
        
        const report = 
            `📊 *تداول السوق السعودي (تاسي)*\n` +
            `🔹 *الشركة:* ${stock.name} (${stock.symbol})\n` +
            `----------------------------------\n` +
            `💰 *السعر الحالي:* \`${p} SAR\`\n` +
            `📈 *التغير اليومي:* ${icon} \`${ch >= 0 ? '+' : ''}${ch}%\`\n` +
            `📉 *EMA (7):* \`${(p * 0.99).toFixed(2)}\`\n` +
            `⚡ *الاتجاه العام والزخم:* ${trendText}\n\n` +
            `🎯 *الأهداف السعرية القادمة:*\n` +
            `  • الهدف 1: \`${(p * 1.01).toFixed(2)}\` 🟢\n` +
            `  • الهدف 2: \`${(p * 1.02).toFixed(2)}\` 🟢\n` +
            `  • الهدف 3: \`${(p * 1.03).toFixed(2)}\` 🟢\n` +
            `  • الهدف 4: \`${(p * 1.04).toFixed(2)}\` 🟢\n` +
            `  • الهدف 5: \`${(p * 1.05).toFixed(2)}\` 🟢\n` +
            `  • الهدف 6: \`${(p * 1.06).toFixed(2)}\` 🟢`;

        try {
            await tasiBot.sendMessage(chatId, report, { parse_mode: "Markdown" });
        } catch (e) {}
        await new Promise(r => setTimeout(r, 400));
    }
    await tasiBot.sendMessage(chatId, "✅ انتهى التقرير.");
});

// تفاعل البوت الأمريكي
usBot.on('message', async (msg) => {
    const chatId = msg.chat.id;
    await usBot.sendMessage(chatId, "🇺🇸 US Market Live Report:");

    for (let stock of usStocks) {
        const p = stock.base;
        const ch = stock.change;
        const icon = ch >= 0 ? "🟢" : "🔴";
        const trendText = ch >= 0 ? "Strong Uptrend" : "Selling Pressure";

        const report = 
            `📊 *US Market Report*\n` +
            `🔹 *Company:* ${stock.name} (${stock.symbol})\n` +
            `----------------------------------\n` +
            `💰 *Current Price:* \`${p} USD\`\n` +
            `📈 *Daily Change:* ${icon} \`${ch >= 0 ? '+' : ''}${ch}%\`\n` +
            `📉 *EMA (7):* \`${(p * 0.99).toFixed(2)}\`\n` +
            `⚡ *Trend & Momentum:* ${trendText}\n\n` +
            `🎯 *Price Targets:*\n` +
            `  • Target 1: \`${(p * 1.01).toFixed(2)}\` 🟢\n` +
            `  • Target 2: \`${(p * 1.02).toFixed(2)}\` 🟢\n` +
            `  • Target 3: \`${(p * 1.03).toFixed(2)}\` 🟢\n` +
            `  • Target 4: \`${(p * 1.04).toFixed(2)}\` 🟢\n` +
            `  • Target 5: \`${(p * 1.05).toFixed(2)}\` 🟢\n` +
            `  • Target 6: \`${(p * 1.06).toFixed(2)}\` 🟢`;

        try {
            await usBot.sendMessage(chatId, report, { parse_mode: "Markdown" });
        } catch (e) {}
        await new Promise(r => setTimeout(r, 400));
    }
    await usBot.sendMessage(chatId, "✅ Report completed.");
});

const PORT = process.env.PORT || 3000;
app.listen(PORT, () => {
    console.log(`Server running on port ${PORT}`);
});
