
const express = require("express");
const TelegramBot = require("node-telegram-bot-api");

const app = express();
app.use(express.json());

app.get("/", (req, res) => {
    res.send("Bots are running successfully!");
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

// تفاعل بوت تاسي
tasiBot.on('message', async (msg) => {
    const chatId = msg.chat.id;
    await tasiBot.sendMessage(chatId, "🇸🇦 جاري إرسال تقرير السوق السعودي (تاسي)...");

    for (let stock of tasiStocks) {
        const basePrice = 32.50;
        const change = +0.89;
        const report = 
            `📊 *تداول السوق السعودي (تاسي)*\n` +
            `🔹 *الشركة:* ${stock.name} (${stock.symbol})\n` +
            `----------------------------------\n` +
            `💰 *السعر الحالي:* \`${basePrice} SAR\`\n` +
            `📈 *التغير اليومي:* 🟢 \`+${change}%\`\n` +
            `📉 *EMA (7):* \`32.10\`\n` +
            `⚡ *الاتجاه العام والزخم:* صعود قوي (فوق VWAP)\n\n` +
            `🎯 *الأهداف السعرية القادمة:*\n` +
            `  • الهدف 1: \`32.99\` 🟢\n` +
            `  • الهدف 2: \`33.48\` 🟢\n` +
            `  • الهدف 3: \`34.12\` 🟢\n` +
            `  • الهدف 4: \`34.80\` 🟢\n` +
            `  • الهدف 5: \`35.50\` 🟢\n` +
            `  • الهدف 6: \`36.20\` 🟢`;

        try {
            await tasiBot.sendMessage(chatId, report, { parse_mode: "Markdown" });
        } catch (e) {}
        await new Promise(r => setTimeout(r, 500));
    }
    await tasiBot.sendMessage(chatId, "✅ انتهى التقرير.");
});

// تفاعل البوت الأمريكي
usBot.on('message', async (msg) => {
    const chatId = msg.chat.id;
    await usBot.sendMessage(chatId, "🇺🇸 جاري إرسال تقرير السوق الأمريكي...");

    for (let stock of usStocks) {
        const basePrice = 150.00;
        const change = +1.25;
        const report = 
            `📊 *US Market Report*\n` +
            `🔹 *Company:* ${stock.name} (${stock.symbol})\n` +
            `----------------------------------\n` +
            `💰 *Current Price:* \`${basePrice} USD\`\n` +
            `📈 *Daily Change:* 🟢 \`+${change}%\`\n` +
            `📉 *EMA (7):* \`148.50\`\n` +
            `⚡ *Trend & Momentum:* Strong Uptrend\n\n` +
            `🎯 *Price Targets:*\n` +
            `  • Target 1: \`152.50\` 🟢\n` +
            `  • Target 2: \`155.00\` 🟢\n` +
            `  • Target 3: \`158.20\` 🟢\n` +
            `  • Target 4: \`161.00\` 🟢\n` +
            `  • Target 5: \`164.50\` 🟢\n` +
            `  • Target 6: \`168.00\` 🟢`;

        try {
            await usBot.sendMessage(chatId, report, { parse_mode: "Markdown" });
        } catch (e) {}
        await new Promise(r => setTimeout(r, 500));
    }
    await usBot.sendMessage(chatId, "✅ Report completed.");
});

const PORT = process.env.PORT || 3000;
app.listen(PORT, () => {
    console.log(`Server running on port ${PORT}`);
});
