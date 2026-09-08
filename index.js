
// ============================================================
// 📊 EODHD PROFESSIONAL STOCK SCANNER BOT (TASI & US)
// Clean, Robust, and Optimized Architecture
// ============================================================

"use strict";

const express = require("express");
const TelegramBot = require("node-telegram-bot-api");

// التوكنات والمفاتيح المباشرة للتجربة الفورية
const TASI_TOKEN = "7772382813:AAECFDY04AXNEf-Q98_65UheUEz7u2HymJw";
const US_TOKEN = "8652994768:AAHg_ABByrZdvlljJ1dQfs6LSmBl37XMPXk";
const EODHD_API_KEY = "6a9ef3fd5c9378.52846267";

const PORT = Number(process.env.PORT || 3000);
const REQUEST_DELAY_MS = 300;

// إعداد خادم السيرفر للاستجابة السريعة على المنصات السحابية
const app = express();
app.use(express.json());

// تهيئة البوتات بدون Polling مبدئي لتفادي أخطاء التعارض 409
const tasiBot = new TelegramBot(TASI_TOKEN, { polling: false });
const usBot = new TelegramBot(US_TOKEN, { polling: false });

const tasiSubscribers = new Set();
const usSubscribers = new Set();

let isScanningTasi = false;
let isScanningUs = false;

// نقاط تفقد الصحة والسيرفر
app.get("/", (req, res) => {
  res.status(200).send("🚀 EODHD Professional Stock Scanner is Online and Active.");
});

app.get("/health", (req, res) => {
  res.status(200).json({
    status: "healthy",
    tasiSubs: tasiSubscribers.size,
    usSubs: usSubscribers.size,
    scanningTasi: isScanningTasi,
    scanningUs: isScanningUs,
    timestamp: new Date().toISOString()
  });
});

// بدء التشغيل وإدارة الاتصال بنظافة تامة
app.listen(PORT, async () => {
  console.log(`🌐 Server is successfully listening on port ${PORT}`);
  try {
    await tasiBot.deleteWebHook();
    await usBot.deleteWebHook();
    
    await tasiBot.startPolling();
    await usBot.startPolling();
    console.log("✅ Telegram Bots successfully connected and polling started.");
  } catch (error) {
    console.error("⚠️ Error during bot startup sequence:", error.message);
  }
});

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

// دالة جلب البيانات مع معالجة احترافية للأخطاء
async function fetchEodhdApi(url) {
  try {
    const response = await fetch(url, {
      headers: { "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)" }
    });
    if (!response.ok) {
      throw new Error(`HTTP Error Status: ${response.status}`);
    }
    const text = await response.text();
    return JSON.parse(text);
  } catch (err) {
    throw new Error(`API Fetch Failed: ${err.message}`);
  }
}

// جلب الرموز للسوق المطلوب
async function getExchangeSymbols(exchangeCode) {
  const url = `https://eodhd.com/api/exchange-symbol-list/${exchangeCode}?api_token=${EODHD_API_KEY}&fmt=json`;
  const data = await fetchEodhdApi(url);
  if (!Array.isArray(data)) throw new Error("Invalid exchange symbol list received.");
  return data
    .filter(item => {
      const type = String(item.Type || "").toLowerCase();
      return type.includes("stock") || type.includes("common");
    })
    .map(item => String(item.Code || "").trim())
    .filter(Boolean);
}

// جلب البيانات التاريخية والتحليل الفني السريع للرمز
async function analyzeStock(symbol, exchangeSuffix, minPrice) {
  const formattedSymbol = `${symbol.replace(/\./g, "-")}.${exchangeSuffix}`;
  const url = `https://eodhistoricaldata.com/api/eod/${formattedSymbol}?api_token=${EODHD_API_KEY}&fmt=json&period=d&limit=100`;
  
  const data = await fetchEodhdApi(url);
  if (!Array.isArray(data) || data.length < 30) throw new Error("Insufficient historical data");

  const closes = data.map(i => Number(i.close)).filter(Number.isFinite);
  const highs = data.map(i => Number(i.high)).filter(Number.isFinite);
  const lows = data.map(i => Number(i.low)).filter(Number.isFinite);
  const volumes = data.map(i => Number(i.volume)).filter(Number.isFinite);

  const currentPrice = closes[closes.length - 1];
  if (!Number.isFinite(currentPrice) || currentPrice < minPrice) throw new Error("Price below threshold");

  const prevClose = closes[closes.length - 2] || currentPrice;
  const changePct = ((currentPrice - prevClose) / prevClose) * 100;

  // حساب السيولة البسيطة لآخر 10 جلسات
  let buyVol = 0, sellVol = 0;
  const len = Math.min(closes.length, volumes.length);
  for (let i = Math.max(1, len - 10); i < len; i++) {
    if (closes[i] > closes[i - 1]) buyVol += volumes[i];
    else if (closes[i] < closes[i - 1]) sellVol += volumes[i];
  }
  const totalVol = buyVol + sellVol;
  const buyRatio = totalVol > 0 ? (buyVol / totalVol) * 100 : 50;
  
  let liquidityState = "⚪ سيولة متوازنة";
  if (buyRatio >= 60) liquidityState = "🟢 دخول سيولة قوية";
  else if (buyRatio <= 40) liquidityState = "🔴 خروج سيولة قوية";

  return {
    symbol,
    price: currentPrice,
    change: changePct,
    liquidity: liquidityState,
    buyRatio,
    updated: new Date()
  };
}

// تنسيق رسالة التنبيه الاحترافية
function formatAlertMessage(stock, marketTitle) {
  let emoji = stock.change >= 0 ? "🟢" : "🔴";
  let msg = `📊 *${marketTitle}*\n\n`;
  msg += `📌 الرمز: *${stock.symbol}*\n`;
  msg += `💰 السعر: *${stock.price.toFixed(2)}*\n`;
  msg += `${emoji} التغير: *${stock.change.toFixed(2)}%*\n`;
  msg += `💧 السيولة: *${stock.liquidity}* (${stock.buyRatio.toFixed(1)}% شراء)\n\n`;
  msg += `🕒 التحديث: ${stock.updated.toLocaleTimeString("ar-SA")}`;
  return msg;
}

// فحص السوق السعودي وتنبيه المشتركين
async function executeTasiScan() {
  if (isScanningTasi || tasiSubscribers.size === 0) return;
  isScanningTasi = true;
  try {
    const symbols = await getExchangeSymbols("SR");
    // نأخذ عينة أولية سريعة للتجربة (أو القائمة كاملة)
    for (const sym of symbols.slice(0, 15)) {
      try {
        const stockInfo = await analyzeStock(sym, "SR", 0.01);
        const text = formatAlertMessage(stockInfo, "🇸🇦 السوق السعودي (تاسي)");
        for (const chatId of tasiSubscribers) {
          await tasiBot.sendMessage(chatId, text, { parse_mode: "Markdown" });
          await sleep(200);
        }
      } catch (err) {
        // تخطي الأسهم التي تعود بأخطاء مؤقتة
      }
      await sleep(REQUEST_DELAY_MS);
    }
  } catch (e) {
    console.error("TASI Scan Error:", e.message);
  } finally {
    isScanningTasi = false;
  }
}

// استقبال الأوامر وتفعيل الاشتراك الفوري
tasiBot.onText(/\/start|\/scan/, async msg => {
  const chatId = msg.chat.id;
  tasiSubscribers.add(chatId);
  await tasiBot.sendMessage(chatId, "🇸🇦 تم تفعيل بوت تاسي بنجاح! جاري فحص عينة من الأسهم وإرسال النتائج الآن...");
  executeTasiScan();
});

usBot.onText(/\/start|\/scan/, async msg => {
  const chatId = msg.chat.id;
  usSubscribers.add(chatId);
  await usBot.sendMessage(chatId, "🇺🇸 تم تفعيل بوت السوق الأمريكي بنجاح!");
});

console.log("💎 Professional Stock Bot script loaded completely.");
