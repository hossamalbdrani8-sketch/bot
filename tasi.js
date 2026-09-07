
const express = require("express");
const TelegramBot = require("node-telegram-bot-api");
const { createCanvas, loadImage } = require("canvas");

const app = express();
app.use(express.json());

// 🔑 توكن التيليجرام
const TOKEN = "8652994768:AAHg_ABByrZdvlljJ1dQfs6LSmBl37XMPXk";

const bot = new TelegramBot(TOKEN, {
  polling: {
    interval: 300,
    autoStart: true,
    params: { timeout: 10 }
  }
});

// 🔑 مفتاح الـ API
const API_KEY = "d7a0311r01qspme6c44gd7a0311r01qspme6c450";

let chatIds = new Set();
let activeScan = false;
let scanInterval = null;

// =======================
// 📊 جلب الشموع (فريم 4 ساعات)
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

async function getCompanyProfile(symbol) {
  try {
    const res = await fetch(`https://finnhub.io/api/v1/stock/profile2?symbol=${symbol}&token=${API_KEY}`);
    const data = await res.json();
    return {
      name: data.name || symbol,
      sector: data.finnhubIndustry || "غير متوفر",
      country: data.country || "SA",
      activity: data.description || "نشاط مدرج في تداول السعودية"
    };
  } catch {
    return { name: symbol, sector: "تداول", country: "SA", activity: "أسهم السوق السعودي" };
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
      if (headline.toLowerCase().includes("loss") || headline.toLowerCase().includes("drop") || headline.toLowerCase().includes("هبوط") || headline.toLowerCase().includes("خسائر")) {
        sentiment = "🔴 سلبي";
      }
      return { headline: headline, sentiment: sentiment };
    }
    return { headline: "لا توجد أخبار جوهرية حديثة", sentiment: "⚪ محايد" };
  } catch {
    return { headline: "غير متوفر", sentiment: "⚪ محايد" };
  }
}

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

  let trendColor = ema7 > ema25 ? "🟢 استمرارية صعود" : "🔴 استمرارية هبوط";
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
    isBullish: change >= 0,
    trendColor: trendColor,
    vwapSignal: vwapSignal,
    ema7: ema7,
    vwap: vwap,
    news: news.headline,
    sentiment: news.sentiment,
    tp: tp
  };
}

// =======================
// 🎨 توليد الصورة البصرية ديناميكياً (أخضر / أحمر)
async function generateVisualReport(s) {
  const width = 800;
  const height = 1100;
  const canvas = createCanvas(width, height);
  const ctx = canvas.getContext("2d");

  // 1. تحديد لون الخلفية بناءً على اتجاه السهم (أخضر صعود / أحمر هبوط)
  if (s.isBullish) {
    // تدرج أخضر احترافي
    let gradient = ctx.createLinearGradient(0, 0, 0, height);
    gradient.addColorStop(0, "#0b3d19");
    gradient.addColorStop(1, "#135d25");
    ctx.fillStyle = gradient;
  } else {
    // تدرج أحمر احترافي
    let gradient = ctx.createLinearGradient(0, 0, 0, height);
    gradient.addColorStop(0, "#4d0f0f");
    gradient.addColorStop(1, "#731717");
    ctx.fillStyle = gradient;
  }
  ctx.fillRect(0, 0, width, height);

  // 2. إعدادات النصوص
  ctx.fillStyle = "#FFFFFF";
  ctx.textAlign = "right";

  // رأس التقرير
  ctx.font = "bold 32px Arial";
  ctx.fillText("🇸🇦 تداول السعودية (تاسي)", width - 50, 60);

  // معلومات الشركة
  ctx.font = "24px Arial";
  ctx.fillText(`🏢 الشركة: ${s.name} (${s.symbol})`, width - 50, 120);
  ctx.font = "18px Arial";
  ctx.fillText(`القطاع: ${s.sector}`, width - 50, 160);
  
  // السعر والتغير
  ctx.font = "bold 28px Arial";
  let changeSign = s.change >= 0 ? "+" : "";
  ctx.fillText(`💰 السعر: ${s.price.toFixed(2)} SAR  (${changeSign}${s.change.toFixed(2)}%)`, width - 50, 220);

  // الاتجاه والمؤشرات
  ctx.font = "22px Arial";
  ctx.fillText(`📊 الاتجاه: ${s.trendColor}`, width - 50, 280);
  ctx.fillText(`🌊 EMA(7): ${s.ema7.toFixed(2)}  |  VWAP: ${s.vwap.toFixed(2)}`, width - 50, 330);
  ctx.fillText(`السيولة: ${s.vwapSignal}`, width - 50, 370);

  // الأهداف السعرية
  ctx.font = "bold 24px Arial";
  ctx.fillText("🎯 الأهداف السعرية:", width - 50, 440);

  ctx.font = "20px Arial";
  s.tp.forEach((target, index) => {
    let check = s.price >= target ? "✅ متحقق" : "";
    let yPos = 490 + (index * 45);
    ctx.fillText(`الهدف ${index + 1}: ${target.toFixed(2)}   ${check}`, width - 50, yPos);
  });

  // تذييل الصورة
  ctx.font = "16px Arial";
  ctx.fillStyle = "#dddddd";
  ctx.fillText("تم الانشاء تلقائياً بواسطة بوت تاسي الذكي", width - 50, 1050);

  return canvas.toBuffer("image/png");
}

// =======================
// 🚀 تنفيذ الفحص الشامل وإرسال الصور
async function runScan() {
  try {
    const res = await fetch(`https://finnhub.io/api/v1/stock/symbol?exchange=SA&token=${API_KEY}`);
    const symbols = await res.json();

    if (!Array.isArray(symbols)) return;

    let batch = symbols.slice(0, 30); // فحص عينة سريعة

    for (let item of batch) {
      if (!activeScan) break;
      let symbol = item.symbol;
      
      let analysis = await analyzeStock(symbol);
      if (analysis && Math.abs(analysis.change) >= 0.3) { // الأسهم النشطة صعوداً أو هبوطاً
        let imageBuffer = await generateVisualReport(analysis);
        
        for (let id of chatIds) {
          await bot.sendPhoto(id, imageBuffer, {
            caption: `تقرير فوري لـ ${analysis.symbol}`
          });
        }
      }
      await new Promise(r => setTimeout(r, 2000));
    }
  } catch (e) {
    console.log("Scan Error:", e);
  }
}

// =======================
// 🤖 أوامر البوت
bot.on("message", async (msg) => {
  let chatId = msg.chat.id;
  chatIds.add(chatId);
  let text = msg.text ? msg.text.trim() : "";

  if (text === "/start") {
    bot.sendMessage(chatId, "💀 تم تشغيل بوت الأسهم السعودية (تاسي) للتقارير البصرية.\n\n/signals - جلب فحص سريع فوري\n/stop - إيقاف المسح");
  } 
  else if (text === "/scan") {
    if (activeScan) {
      bot.sendMessage(chatId, "⚠️ الفحص يعمل بالفعل في الخلفية.");
    } else {
      activeScan = true;
      bot.sendMessage(chatId, "🚀 بدأ مسح السوق السعودي وإرسال التقارير البصرية...");
      runScan();
      scanInterval = setInterval(() => {
        if (activeScan) runScan();
      }, 15 * 60 * 1000);
    }
  } 
  else if (text === "/signals" || text === "/s") {
    bot.sendMessage(chatId, "🔍 جاري جلب وإنشاء أحدث التقارير البصرية للسوق السعودي...");
    await runScan();
    bot.sendMessage(chatId, "✅ انتهى التقرير الحالي.");
  }
  else if (text === "/stop") {
    activeScan = false;
    if (scanInterval) clearInterval(scanInterval);
    bot.sendMessage(chatId, "🛑 تم إيقاف المسح التلقائي.");
  }
});

app.listen(3000, () => {
  console.log("🇸🇦 TASI Visual Bot Server running on port 3000");
});
