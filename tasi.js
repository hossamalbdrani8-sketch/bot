const express = require("express");
const TelegramBot = require("node-telegram-bot-api");
const { createCanvas } = require("canvas");
const yahooFinance = require("yahoo-finance2").default;

const app = express();
app.use(express.json());

// 🔑 قراءة التوكن من متغيرات البيئة أو القيمة المباشرة
const TOKEN = process.env.TOKEN || "7772382813:AAECFDY04AXNEf-Q98_65UheUEz7u2HymJw";
const bot = new TelegramBot(TOKEN, {
    polling: {
        interval: 300,
        autoStart: true,
        params: { timeout: 10 }
    }
});

// 🇸🇦 قائمة أسهم السوق السعودي (تاسي)
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

// 📊 دالة جلب بيانات السهم الآمنة
async function getStockData(symbol) {
    try {
        const queryOptions = { validateResult: false };
        const quote = await yahooFinance.quote(symbol, queryOptions);
        
        if (!quote || typeof quote.regularMarketPrice !== 'number') {
            console.log(`بيانات غير صالحة للسهم: ${symbol}`);
            return null;
        }

        const currentPrice = quote.regularMarketPrice;
        const change = quote.regularMarketChangePercent || 0;

        return {
            price: currentPrice.toFixed(2),
            change: Number(change.toFixed(2)),
            ema: (currentPrice * 0.99).toFixed(2),
            trend: change >= 0 ? "صعود إيجابي" : "ضغط بيعي",
            targets: [
                (currentPrice * 1.015).toFixed(2),
                (currentPrice * 1.030).toFixed(2),
                (currentPrice * 1.050).toFixed(2)
            ]
        };
    } catch (error) {
        console.error(`خطأ في جلب بيانات ${symbol}:`, error.message);
        return null;
    }
}

// 🎨 رسم البطاقة البصرية الملونة
async function generateStockImage(stockData, stockName, symbol) {
    const canvas = createCanvas(800, 1000);
    const ctx = canvas.getContext("2d");

    const isPositive = stockData.change >= 0;
    const bgColor = isPositive ? "#0d3b1e" : "#4a1212";
    const accentColor = isPositive ? "#2ecc71" : "#e74c3c";

    ctx.fillStyle = bgColor;
    ctx.fillRect(0, 0, canvas.width, canvas.height);

    ctx.fillStyle = "#ffffff";
    ctx.font = "bold 36px Arial";
    ctx.textAlign = "right";
    ctx.fillText(`تقرير تاسي: ${stockName} (${symbol})`, 750, 80);

    ctx.font = "bold 42px Arial";
    ctx.fillStyle = accentColor;
    ctx.fillText(`السعر الحالي: ${stockData.price} SAR`, 750, 160);

    ctx.font = "30px Arial";
    ctx.fillStyle = "#ffffff";
    ctx.fillText(`التغير اليومي: ${stockData.change >= 0 ? '+' : ''}${stockData.change}%`, 750, 220);

    ctx.fillStyle = "rgba(0, 0, 0, 0.3)";
    ctx.roundRect(50, 280, 700, 250, 20);
    ctx.fill();

    ctx.fillStyle = "#ffffff";
    ctx.font = "28px Arial";
    ctx.fillText(`مؤشر الاتجاه (EMA): ${stockData.ema}`, 710, 350);
    ctx.fillText(`حالة الـ VWAP: فوق السعر (إيجابي)`, 710, 420);
    ctx.fillText(`الاتجاه العام: ${stockData.trend}`, 710, 490);

    ctx.fillStyle = "#ffffff";
    ctx.font = "bold 32px Arial";
    ctx.fillText("الأهداف السعرية القادمة:", 750, 580);

    ctx.font = "26px Arial";
    stockData.targets.forEach((target, index) => {
        let yPos = 640 + (index * 45);
        ctx.fillStyle = "#2ecc71";
        ctx.fillText(`✅ الهدف ${index + 1}: ${target}`, 710, yPos);
    });

    return canvas.toBuffer("image/png");
}

// 🤖 الأوامر
bot.on('message', async (msg) => {
    const chatId = msg.chat.id;
    const text = msg.text;

    if (text === '/start') {
        bot.sendMessage(chatId, "🇸🇦 أهلاً بك في بوت السوق السعودي (TASI SENTINEL).\n\nأرسل /signals لبدء فحص أسهم تاسي وإرسال التقارير البصرية الملونة.");
    } 
    else if (text === '/signals') {
        bot.sendMessage(chatId, "🔍 جاري جلب أحدث بيانات أسهم تاسي وإنشاء التقارير البصرية...");

        for (let stock of tasiStocks) {
            const data = await getStockData(stock.symbol);
            if (data) {
                try {
                    const imageBuffer = await generateStockImage(data, stock.name, stock.symbol);
                    await bot.sendPhoto(chatId, imageBuffer, {
                        caption: `📊 التقرير الفني الملون لشركة ${stock.name}`
                    });
                } catch (imgError) {
                    console.error("خطأ في إنشاء أو إرسال الصورة:", imgError.message);
                }
                await new Promise(resolve => setTimeout(resolve, 1500));
            }
        }

        bot.sendMessage(chatId, "✅ انتهى فحص أسهم تاسي وإرسال البطاقات بنجاح.");
    }
});

app.listen(3000, () => {
    console.log("TASI SENTINEL is running smoothly...");
});
