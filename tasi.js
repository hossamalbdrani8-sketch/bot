const express = require("express");
const TelegramBot = require("node-telegram-bot-api");

const app = express();
app.use(express.json());

// 🇸🇦 توكن بوت تداول السعودية الجديد
const TOKEN = "7772382813:AAECFDY04AXNEf-Q98_65UheUEz7u2HymJw";

const bot = new TelegramBot(TOKEN, {
  polling: {
    interval: 300,
    autoStart: true,
    params: { timeout: 10 }
  }
});

const API_KEY = "d7a0311r01qspme6c44gd7a0311r01qspme6c450";

let chatIds = new Set();
let activeScan = false;
let scanInterval = null;

// =======================
// 📊 فريم 4 ساعات (بدون ذكر كلمة فريم)
async function getCandles(symbol) {
  try {
    let to = Math.floor(Date.now() / 1000);
    let from = to - (60 * 60 * 24 * 60);

    const res = await fetch(`https://finnhub.io/api/v1/stock/candle?symbol=${symbol}&resolution=240&from=${from}&to=${to}&token=${API_KEY}`);
    const data = await res.json();

    if (data.s !== "ok") return null;
    return { closes: data.c, volumes: data.v, highs: data.h, lows: data.l };
  } catch {
    return null;
  }
}

function calculateEMA(data, period) {
  if (!data || data.length === 0) return 0;
  let k = 2 / (period + 1);
  let ema = data[0];
  for (let i = 1; i < data.length; i++) {
    ema = data[i] * k + ema * (1 - k);
  }
  return ema;
}

function calculateVWAP(highs, lows, closes, volumes) {
  if (!highs || !lows || !closes || !volumes) return 0;
  let sumTPV = 0;
  let sumVol = 0;
  for (let i = 0; i < closes.length; i++) {
    let tp = (highs[i] + lows[i] + closes[i]) / 3;
    sumTPV += tp * (volumes[i] || 1);
    sumVol += (volumes[i] || 1);
  }
  return sumVol === 0 ? closes[closes.length - 1] : sumTPV / sumVol;
}

// =======================
// 🏢 تفاصيل الشركة (السوق السعودي)
async function getCompanyProfile(symbol) {
  try {
    const res = await fetch(`https://finnhub.io/api/v1/stock/profile2?symbol=${symbol}&token=${API_KEY}`);
    const data = await res.json();
    return {
      name: data.name || symbol,
      sector: data.finnhubIndustry || "قطاع تداول",
      country: "المملكة العربية السعودية (SA)",
      activity: data.description || "نشاط مدرج في السوق السعودي"
    };
  } catch {
    return { name: symbol, sector: "تداول السعودية", country: "المملكة العربية السعودية (SA)", activity: "أسهم تاسي" };
  }
}

async function getCompanyNews(symbol) {
  try {
    let today = new Date().toISOString().slice(0, 10);
    let past = new Date(Date.now() - 7 * 24 * 60 * 60 * 1000).toISOString().slice(0, 10);
    const res = await fetch(`https://finnhub.io/api/v1/company-news?symbol=${symbol}&from=${past}&to=${today}&token=${API_KEY}`);
    const newsList = await res.json();
    
    if (newsList && newsList.length > 0) {
      let headline = newsList[0].headline;
      let sentiment = "🟢 إيجابي";
      let lower = headline.toLowerCase();
      if (lower.includes("loss") || lower.includes("drop") || lower.includes("هبوط") || lower.includes("خسائر") || lower.includes("تراجع")) {
        sentiment = "🔴 سلبي";
      }
      return { headline: headline, sentiment: sentiment };
    }
    return { headline: "لا توجد أخبار جوهرية جديدة", sentiment: "⚪ محايد" };
  } catch {
    return { headline: "غير متوفر", sentiment: "⚪ محايد" };
  }
}

// =======================
// 🔍 التحليل الفني للسعودي
async function analyzeStock(symbol) {
  let candleData = await getCandles(symbol);
  if (!candleData || !candleData.closes || candleData.closes.length < 30) return null;

  let closes = candleData.closes;
  let price = closes[closes.length - 1];
  let prevPrice = closes[closes.length - 2];
  let change = ((price - prevPrice) / prevPrice) * 100;

  let ema7 = calculateEMA(closes, 7);
  let ema25 = calculateEMA(closes, 25);
  let vwap = calculateVWAP(candleData.highs, candleData.lows, closes, candleData.volumes);

  // اتجاه السوق: أخضر استمرارية صعود، أحمر استمرارية هبوط
  let trendSignal = ema7 > ema25 ? "🟢 استمرارية صعود" : "🔴 استمرارية هبوط";
  let vwapSignal = price >= vwap ? "🟢 فوق VWAP (دعم إيجابي)" : "🔴 تحت VWAP (ضغط سلبي)";

  let profile = await getCompanyProfile(symbol);
  let news = await getCompanyNews(symbol);

  let tp = [
    price * 1.015, price * 1.03, price * 1.05, 
    price * 1.07, price * 1.10, price * 1.15
  ];

  return {
    symbol: symbol,
    name: profile.name,
    sector: profile.sector,
    country: profile.country,
    activity: profile.activity,
    price: price,
    change: change,
    trendSignal: trendSignal,
    vwapSignal: vwapSignal,
    ema7: ema7,
    vwap: vwap,
    news: news.headline,
    sentiment: news.sentiment,
    tp: tp
  };
}

// =======================
// 📝 تصميم التقرير
async function formatMessage(s) {
  let checkTp = (target) => s.price >= target ? "✅" : "";
  
  return `
🇸🇦 **تداول السعودية (تاسي)**

🏢 **الشركة:** ${s.name} (${s.symbol})
* **القطاع والصناعة:** ${s.sector}
* **الدولة:** ${s.country}
* **نشاط السهم:** ${s.activity}
* **الأخبار:** ${s.news}
* **حالة الأخبار:** ${s.sentiment}

💰 **السعر الحالي:** ${s.price.toFixed(2)} SAR
📈 **التغيير:** ${s.change >= 0 ? "🟢 +" : "🔴 "}${s.change.toFixed(2)}%

📊 **اتجاه السوق:** 
${s.trendSignal}

🌊 **السيولة والتجميع (EMA + VWAP):**
* EMA: ${s.ema7.toFixed(2)}
* VWAP: ${s.vwap.toFixed(2)} -> ${s.vwapSignal}

🎯 **الأهداف السعرية:**
🎯 الهدف 1: ${s.tp[0].toFixed(2)} ${checkTp(s.tp[0])}
🎯 الهدف 2: ${s.tp[1].toFixed(2)} ${checkTp(s.tp[1])}
🎯 الهدف 3: ${s.tp[2].toFixed(2)} ${checkTp(s.tp[2])}
🎯 الهدف 4: ${s.tp[3].toFixed(2)} ${checkTp(s.tp[3])}
🎯 الهدف 5: ${s.tp[4].toFixed(2)} ${checkTp(s.tp[4])}
🎯 الهدف 6: ${s.tp[5].toFixed(2)} ${checkTp(s.tp[5])}
━━━━━━━━━━━━━━━━━━━━`;
}

// =======================
// 🚀 فحص أسهم السوق السعودي فقط (exchange=SA)
async function runScan() {
  try {
    const res = await fetch(`https://finnhub.io/api/v1/stock/symbol?exchange=SA&token=${API_KEY}`);
    let symbols = await res.json();

    if (!Array.isArray(symbols)) return;

    let batch = symbols.slice(0, 25);

    for (let item of batch) {
      if (!activeScan) break;
      let symbol = item.symbol;
      
      let analysis = await analyzeStock(symbol);
      if (analysis) {
        let text = await formatMessage(analysis);
        for (let id of chatIds) {
          await bot.sendMessage(id, text, { parse_mode: "Markdown" });
        }
      }
      await new Promise(r => setTimeout(r, 2000));
    }
  } catch (e) {
    console.log("TASI Error:", e);
  }
}

// =======================
// 🤖 أوامر البوت
bot.on("message", async (msg) => {
  let chatId = msg.chat.id;
  chatIds.add(chatId);
  let text = msg.text ? msg.text.trim() : "";

  if (text === "/start") {
    bot.sendMessage(chatId, "🇸🇦 أهلاً بك في بوت السوق السعودي (تاسي).\n\nالأوامر المتاحة:\n/scan - لبدء المسح الفوري\n/signals - جلب الإشارات الحالية\n/status - حالة البوت\n/stop - إيقاف المسح");
  } 
  else if (text === "/scan") {
    if (activeScan) {
      bot.sendMessage(chatId, "⚠️ الفحص يعمل بالفعل.");
    } else {
      activeScan = true;
      bot.sendMessage(chatId, "🚀 بدأ مسح السوق السعودي (تاسي)...");
      runScan();
      scanInterval = setInterval(() => {
        if (activeScan) runScan();
      }, 15 * 60 * 1000);
    }
  } 
  else if (text === "/signals" || text === "/s") {
    bot.sendMessage(chatId, "🔍 جاري جلب أحدث إشارات تاسي...");
    await runScan();
  }
  else if (text === "/status") {
    bot.sendMessage(chatId, activeScan ? "🟢 بوت تاسي يعمل بنشاط." : "🔴 بوت تاسي متوقف.");
  }
  else if (text === "/stop") {
    activeScan = false;
    if (scanInterval) clearInterval(scanInterval);
    bot.sendMessage(chatId, "🛑 تم إيقاف المسح بنجاح.");
  }
});

app.listen(3000, () => {
  console.log("🇸🇦 TASI Bot running on port 3000");
});
