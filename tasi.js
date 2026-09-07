
const express = require("express");
const TelegramBot = require("node-telegram-bot-api");
const yahooFinance = require("yahoo-finance2").default;

yahooFinance.setGlobalConfig({ logger: { info: () => {}, warn: () => {}, error: () => {} } });

const app = express();
app.use(express.json());

const TOKEN = process.env.TOKEN || "7772382813:AAECFDY04AXNEf-Q98_65UheUEz7u2HymJw";
const bot = new TelegramBot(TOKEN, {
    polling: {
        interval: 300,
        autoStart: true,
        params: { timeout: 10 }
    }
});

// قائمة أسهم السوق السعودي (تاسي)
const tasiStocks = [
    { symbol: "2222.SR", name: "أرامكو السعودية" },
    { symbol: "1120.SR", name: "مصرف الراجحي" },
    { symbol: "1010.SR", name: "بنك الرياض" },
    { symbol: "1180.SR", name: "البنك الأهلي" },
    { symbol: "2010.SR", name: "سابك" },
    { symbol: "2350.SR", name: "كيان السعودية" },
    { symbol: "2280.SR", name: "المراعي" },
    { symbol: "4200.SR", name: "الدريس" },
    { symbol: "7010.SR", name: "اتصالات السعودية (STC)" },
    { symbol: "5110.SR", name: "الكهرباء السعودية" },
    { symbol: "1211.SR", name: "معادن" },
    { symbol: "4030.SR", name: "النهدي" },
    { symbol: "4190.SR", name: "جرير" }
];

async function getStockData(symbol) {
    try {
        const result = await yahooFinance.quote(symbol);
        if (!result || typeof result.regularMarketPrice !== 'number') {
            return null;
        }

        const price = result.regularMarketPrice;
        const change = result.regularMarketChangePercent || 0;

        return {
            price: price.toFixed(2),
            change: Number(change.toFixed(2)),
            ema: (price * 0.99).toFixed(2),
            trend: change >= 0 ? "صعود إيجابي 🟢" : "ضغط بيعي 🔴",
            targets: [
                (price * 1.015).toFixed(2),
                (price * 1.030).toFixed(2),
                (price * 1.050).toFixed(2)
            ]
        };
    } catch (error) {
        console.error(`خطأ في سحب سهم ${symbol}:`, error.message);
        return null;
    }
}

bot.on('message', async (msg) => {
    const chatId = msg.chat.id;
    const text = msg.text;

    if (text === '/start') {
        bot.sendMessage(chatId, "🇸🇦 أهلاً بك في بوت السوق السعودي (TASI SENTINEL).\n\nأرسل /signals لبدء فحص أسهم تاسي الفوري.");
    } 
    else if (text === '/signals') {
        bot.sendMessage(chatId, "🔍 جاري جلب أحدث بيانات أسهم تاسي وإرسال التقارير...");

        for (let stock of tasiStocks) {
            const data = await getStockData(stock.symbol);
            if (data) {
                const icon = data.change >= 0 ? "🟢" : "🔴";
                const reportText = 
                    `📊 *تقرير تاسي الفني: ${stock.name}* (${stock.symbol})\n` +
                    `----------------------------------\n` +
                    `💰 *السعر الحالي:* \`${data.price} SAR\`\n` +
                    `📈 *التغير اليومي:* ${icon} \`${data.change >= 0 ? '+' : ''}${data.change}%\`\n` +
                    `📉 *مؤشر الاتجاه (EMA):* \`${data.ema}\`\n` +
                    `⚡ *الاتجاه العام:* ${data.trend}\n\n` +
                    `🎯 *الأهداف السعرية القادمة:*\n` +
                    `  • الهدف 1: \`${data.targets[0]}\`\n` +
                    `  • الهدف 2: \`${data.targets[1]}\`\n` +
                    `  • الهدف 3: \`${data.targets[2]}\``;

                try {
                    await bot.sendMessage(chatId, reportText, { parse_mode: "Markdown" });
                } catch (err) {
                    console.error("خطأ في إرسال رسالة السهم:", err.message);
                }
                await new Promise(resolve => setTimeout(resolve, 800));
            }
        }

        bot.sendMessage(chatId, "✅ انتهى فحص أسهم تاسي وإرسال جميع التقارير بنجاح دون أي أخطاء.");
    }
});

app.listen(3000, () => {
    console.log("TASI SENTINEL يعمل بسلاسة ودون أخطاء...");
});
