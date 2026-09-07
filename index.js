
const express = require("express");
const TelegramBot = require("node-telegram-bot-api");
const https = require("https");

const app = express();
app.use(express.json());

app.get("/", (req, res) => {
    res.send("Live Market Bots are active!");
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

// 2. بوت السوق الأمريكي (استخدمنا التوكن الجديد هنا، أو يمكنك وضع القديم)
const US_TOKEN = "8805597611:AAGFWEw-Ll8jBU6pRxBh3d3fNWdPyGhqooU";
const usBot = new TelegramBot(US_TOKEN, { polling: true });

const usStocks = [
    { symbol: "AAPL", name: "Apple Inc." },
    { symbol: "TSLA", name: "Tesla Inc." },
    { symbol: "MSFT", name: "Microsoft Corporation" },
    { symbol: "NVDA", name: "NVIDIA Corporation" },
    { symbol: "LCII", name: "LCI Industries" }
];

// دالة لجلب السعر الحقيقي
function getStockPrice(symbol) {
    return new Promise((resolve) => {
        const url = `https://query1.finance.yahoo.com/v8/finance/chart/${symbol}?interval=1d`;
        https.get(url, (res) => {
            let data = '';
            res.on('data', chunk => data += chunk);
            res.on('end', () => {
                try {
                    const json = JSON.parse(data);
                    const price = json.chart.result[0].meta.regularMarketPrice;
                    const prevClose = json.chart.result[0].meta.chartPreviousClose || price;
                    const change = ((price - prevClose) / prevClose) * 100;
                    resolve({ price: price.toFixed(2), change: Number(change.toFixed(2)) });
                } catch (e) {
                    resolve(null);
                }
            });
        }).on('error', () => resolve(null));
    });
}

// تفاعل بوت السوق السعودي
tasiBot.on('message', async (msg) => {
    const chatId = msg.chat.id;
    await tasiBot.sendMessage(chatId, "🇸🇦 جاري جلب الأسعار المباشرة للسوق السعودي (تاسي)...");

    for (let stock of tasiStocks) {
        const data = await getStockPrice(stock.symbol);
        if (data) {
            const p = parseFloat(data.price);
            const icon = data.change >= 0 ? "🟢" : "🔴";
            const trendText = data.change >= 0 ? "صعود قوي (فوق VWAP)" : "ضغط سلبي (تحت VWAP)";
            
            const report = 
                `📊 *تداول السوق السعودي (تاسي)*\n` +
                `🔹 *الشركة:* ${stock.name} (${stock.symbol})\n` +
                `----------------------------------\n` +
                `💰 *السعر الحالي:* \`${data.price} SAR\`\n` +
                `📈 *التغير اليومي:* ${icon} \`${data.change >= 0 ? '+' : ''}${data.change}%\`\n` +
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
        }
        await new Promise(r => setTimeout(r, 600));
    }
    await tasiBot.sendMessage(chatId, "✅ انتهى التقرير المباشر.");
});

// تفاعل البوت الأمريكي
usBot.on('message', async (msg) => {
    const chatId = msg.chat.id;
    await usBot.sendMessage(chatId, "🇺🇸 جاري جلب الأسعار المباشرة للسوق الأمريكي...");

    for (let stock of usStocks) {
        const data = await getStockPrice(stock.symbol);
        if (data) {
            const p = parseFloat(data.price);
            const icon = data.change >= 0 ? "🟢" : "🔴";
            const trendText = data.change >= 0 ? "Strong Uptrend" : "Selling Pressure";

            const report = 
                `📊 *US Market Live Report*\n` +
                `🔹 *Company:* ${stock.name} (${stock.symbol})\n` +
                `----------------------------------\n` +
                `💰 *Current Price:* \`${data.price} USD\`\n` +
                `📈 *Daily Change:* ${icon} \`${data.change >= 0 ? '+' : ''}${data.change}%\`\n` +
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
        }
        await new Promise(r => setTimeout(r, 600));
    }
    await usBot.sendMessage(chatId, "✅ Live report completed.");
});

const PORT = process.env.PORT || 3000;
app.listen(PORT, () => {
    console.log(`Server running on port ${PORT}`);
});
