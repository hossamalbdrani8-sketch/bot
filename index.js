
// ============================================================
// 📊 GLOBAL STOCK SCANNER BOT - TASI & NASDAQ PRO MAX
// Node.js 18+
// Yahoo Finance public endpoints
// Telegram Bot
// ============================================================

"use strict";

const express = require("express");
const TelegramBot = require("node-telegram-bot-api");

// ============================================================
// ⚙️ الإعدادات الأساسية
// ============================================================

const TOKEN = process.env.TELEGRAM_TOKEN;

if (!TOKEN) {
  throw new Error("❌ TELEGRAM_TOKEN غير موجود في Environment Variables");
}

const PORT = Number(process.env.PORT || 3000);
const MIN_PRICE = Number(process.env.MIN_PRICE || 0.10);
const MIN_CHANGE = Number(process.env.MIN_CHANGE || 0.20);
const SCAN_INTERVAL_MIN = Number(process.env.SCAN_INTERVAL_MIN || 5);
const UPDATE_INTERVAL_SEC = Number(process.env.UPDATE_INTERVAL_SEC || 30);
const REQUEST_DELAY_MS = Number(process.env.REQUEST_DELAY_MS || 250);
const PROFILE_CACHE_MS = Number(process.env.PROFILE_CACHE_MS || 30 * 60 * 1000);
const NEWS_CACHE_MS = Number(process.env.NEWS_CACHE_MS || 5 * 60 * 1000);

// ============================================================
// 🤖 Telegram Bot
// ============================================================

const bot = new TelegramBot(TOKEN, {
  polling: true
});

// ============================================================
// 🌐 Express Server
// ============================================================

const app = express();

app.get("/", (req, res) => {
  res.status(200).send("🌍 TASI & NASDAQ Stock Bot is running");
});

app.get("/health", (req, res) => {
  res.json({
    ok: true,
    bot: "Stock Scanner PRO MAX (TASI + NASDAQ)",
    time: new Date().toISOString()
  });
});

app.listen(PORT, () => {
  console.log(`🌐 Server running on port ${PORT}`);
});

// ============================================================
// 🧠 التخزين المؤقت
// ============================================================

const sentSignals = new Map();
const profileCache = new Map();
const newsCache = new Map();

let scanRunning = false;
let lastScanTime = null;
let lastScanStats = {
  candidates: 0,
  checked: 0,
  accepted: 0,
  errors: 0
};

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

// ============================================================
// 🌐 Yahoo Fetch مع رؤوس طلبات قوية
// ============================================================

async function yahooFetch(url, options = {}) {
  const response = await fetch(url, {
    ...options,
    headers: {
      "User-Agent":
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/140 Safari/537.36",
      "Accept": "application/json,text/plain,*/*",
      ...(options.headers || {})
    }
  });

  const text = await response.text();

  if (!response.ok) {
    throw new Error(`Yahoo HTTP ${response.status}: ${text.slice(0, 150)}`);
  }

  try {
    return JSON.parse(text);
  } catch {
    throw new Error(`Yahoo returned invalid JSON: ${text.slice(0, 150)}`);
  }
}

// ============================================================
// 📊 جلب بيانات الشارت والسعر اللحظي
// ============================================================

async function getChart(symbol, range = "5d", interval = "5m") {
  const url =
    `https://query1.finance.yahoo.com/v8/finance/chart/` +
    `${encodeURIComponent(symbol)}` +
    `?range=${range}` +
    `&interval=${interval}` +
    `&includePrePost=false` +
    `&events=div%2Csplits`;

  const data = await yahooFetch(url);

  if (
    !data ||
    !data.chart ||
    !data.chart.result ||
    !data.chart.result[0]
  ) {
    throw new Error("لا توجد بيانات للشارت");
  }

  return data.chart.result[0];
}

// ============================================================
// 📈 حساب المتوسطات والمؤشرات الفنية (EMA & VWAP)
// ============================================================

function calculateEMA(values, period) {
  if (!Array.isArray(values) || values.length < period) {
    return null;
  }

  const multiplier = 2 / (period + 1);
  let ema = 0;

  for (let i = 0; i < period; i++) {
    ema += Number(values[i]) || 0;
  }
  ema /= period;

  for (let i = period; i < values.length; i++) {
    const value = Number(values[i]);
    if (!Number.isFinite(value)) continue;
    ema = (value - ema) * multiplier + ema;
  }

  return ema;
}

function calculateVWAP(high, low, close, volume) {
  let pv = 0;
  let totalVolume = 0;
  const length = Math.min(high.length, low.length, close.length, volume.length);
  const start = Math.max(0, length - 78);

  for (let i = start; i < length; i++) {
    const h = Number(high[i]);
    const l = Number(low[i]);
    const c = Number(close[i]);
    const v = Number(volume[i]);

    if (!Number.isFinite(h) || !Number.isFinite(l) || !Number.isFinite(c) || !Number.isFinite(v) || v <= 0) {
      continue;
    }

    const typical = (h + l + c) / 3;
    pv += typical * v;
    totalVolume += v;
  }

  if (totalVolume <= 0) return null;
  return pv / totalVolume;
}

function calculateVolumeStrength(volumes) {
  const clean = volumes.map(Number).filter(v => Number.isFinite(v) && v >= 0);
  if (clean.length < 5) return 0;

  const current = clean[clean.length - 1];
  const previous = clean.slice(Math.max(0, clean.length - 25), clean.length - 1);
  if (!previous.length) return 0;

  const avg = previous.reduce((a, b) => a + b, 0) / previous.length;
  if (avg <= 0) return 0;

  return Math.max(0, Math.min(100, (current / avg) * 50));
}

// ============================================================
// 💧 تحليل السيولة
// ============================================================

function analyzeLiquidity(close, volume) {
  const len = Math.min(close.length, volume.length);
  const start = Math.max(1, len - 24);

  let buyVolume = 0;
  let sellVolume = 0;
  let neutralVolume = 0;

  for (let i = start; i < len; i++) {
    const prev = Number(close[i - 1]);
    const curr = Number(close[i]);
    const vol = Number(volume[i]) || 0;

    if (!Number.isFinite(prev) || !Number.isFinite(curr)) continue;

    if (curr > prev) buyVolume += vol;
    else if (curr < prev) sellVolume += vol;
    else neutralVolume += vol;
  }

  const total = buyVolume + sellVolume + neutralVolume;
  if (total <= 0) return { buyRatio: 50, sellRatio: 50, label: "⚪ سيولة متوازنة" };

  const buyRatio = (buyVolume / total) * 100;
  const sellRatio = (sellVolume / total) * 100;

  let label = "⚪ سيولة متوازنة";
  if (buyRatio >= 70) label = "🟢 دخول سيولة قوية";
  else if (sellRatio >= 70) label = "🔴 خروج سيولة قوية";
  else if (buyRatio >= 55) label = "🟢 دخول سيولة";
  else if (sellRatio >= 55) label = "🔴 خروج سيولة";

  return { buyRatio, sellRatio, label };
}

// ============================================================
// 📊 الاتجاه العام (الأخضر للصاعد، الأحمر للهابط)
// ============================================================

function analyzeGeneralTrend(price, ema50, ema180) {
  if (Number.isFinite(ema50) && Number.isFinite(ema180)) {
    if (ema50 > ema180 && price > ema50) {
      return {
        bullish: true,
        bearish: false,
        label: "🟢 الاتجاه العام صاعد"
      };
    }
    if (ema50 < ema180 && price < ema50) {
      return {
        bullish: false,
        bearish: true,
        label: "🔴 الاتجاه العام هابط"
      };
    }
  }
  return {
    bullish: false,
    bearish: false,
    label: "⚪ الاتجاه العام متوازن"
  };
}

// ============================================================
// 🎯 الأهداف السعرية
// ============================================================

function calculateTargets(price) {
  const percentages = [2, 4, 6, 8, 10, 12, 15, 18];
  return percentages.map(p => ({
    percent: p,
    price: price * (1 + p / 100)
  }));
}

// ============================================================
// 📰 الأخبار وتصنيفها بدقة (إيجابي 🟢 / سلبي 🔴)
// ============================================================

function classifyNewsSentiment(title) {
  const text = String(title || "").toLowerCase();

  const positiveWords = [
    "surge", "soar", "rally", "gain", "gains", "rise", "rises", "up", "growth",
    "profit", "profits", "beat", "beats", "strong", "bullish", "upgrade", "upgraded",
    "approval", "approved", "partnership", "contract", "deal", "record", "positive",
    "breakthrough", "acquire", "acquisition", "ارتفاع", "نمو", "أرباح", "عقد", "إيجابي"
  ];

  const negativeWords = [
    "fall", "falls", "drop", "drops", "down", "decline", "loss", "losses", "weak",
    "bearish", "downgrade", "downgraded", "warning", "lawsuit", "investigation",
    "fraud", "bankruptcy", "offering", "dilution", "layoff", "debt", "miss", "negative",
    "انخفاض", "خسائر", "هبوط", "تحقيق", "ديون", "سليبي"
  ];

  let positive = 0;
  let negative = 0;

  for (const word of positiveWords) {
    if (text.includes(word)) positive++;
  }
  for (const word of negativeWords) {
    if (text.includes(word)) negative++;
  }

  if (positive > negative) return "🟢 إيجابي";
  if (negative > positive) return "🔴 سلبي";
  return "⚪ محايد";
}

async function getNews(symbol) {
  const cached = newsCache.get(symbol);
  if (cached && Date.now() - cached.time < NEWS_CACHE_MS) {
    return cached.data;
  }

  let news = [];
  try {
    const url = `https://query1.finance.yahoo.com/v1/finance/search?q=${encodeURIComponent(symbol)}&quotesCount=1&newsCount=5`;
    const data = await yahooFetch(url);
    const rawNews = Array.isArray(data?.news) ? data.news : [];

    news = rawNews.slice(0, 3).map(item => {
      const title = item.title || "خبر بدون عنوان";
      return {
        title,
        publisher: item.publisher || "Financial News",
        sentiment: classifyNewsSentiment(title)
      };
    });
  } catch (error) {
    console.log(`⚠️ News ${symbol}: ${error.message}`);
  }

  newsCache.set(symbol, { time: Date.now(), data: news });
  return news;
}

// ============================================================
// 📊 جلب بيانات السهم الكاملة (تاسي ونسداك بدون استثناء)
// ============================================================

async function getStockData(symbol) {
  const chart = await getChart(symbol, "5d", "5m");
  const meta = chart.meta || {};

  const quote = chart.indicators?.quote?.[0];
  if (!quote) throw new Error("لا توجد بيانات الأسعار");

  const close = quote.close || [];
  const high = quote.high || [];
  const low = quote.low || [];
  const volume = quote.volume || [];

  const cleanClose = [];
  const cleanHigh = [];
  const cleanLow = [];
  const cleanVolume = [];

  for (let i = 0; i < close.length; i++) {
    const c = Number(close[i]);
    if (!Number.isFinite(c)) continue;
    cleanClose.push(c);
    cleanHigh.push(Number.isFinite(Number(high[i])) ? Number(high[i]) : c);
    cleanLow.push(Number.isFinite(Number(low[i])) ? Number(low[i]) : c);
    cleanVolume.push(Number.isFinite(Number(volume[i])) ? Number(volume[i]) : 0);
  }

  if (cleanClose.length < 15) throw new Error("بيانات الشارت غير كافية");

  const price = cleanClose[cleanClose.length - 1];
  if (!Number.isFinite(price) || price < MIN_PRICE) {
    throw new Error("السعر أقل من الحد المسموح");
  }

  const previousClose = Number(meta.previousClose) || Number(meta.chartPreviousClose) || cleanClose[Math.max(0, cleanClose.length - 2)];
  const changePercent = previousClose > 0 ? ((price - previousClose) / previousClose) * 100 : 0;

  const ema7 = calculateEMA(cleanClose, 7);
  const ema14 = calculateEMA(cleanClose, 14);
  const ema25 = calculateEMA(cleanClose, 25);
  const ema50 = calculateEMA(cleanClose, 50);
  const ema180 = calculateEMA(cleanClose, 180) || ema50;

  const vwap = calculateVWAP(cleanHigh, cleanLow, cleanClose, cleanVolume) || price;
  const volumeStrength = calculateVolumeStrength(cleanVolume);
  const liquidityData = analyzeLiquidity(cleanClose, cleanVolume);
  const generalTrend = analyzeGeneralTrend(price, ema50, ema180);
  const targets = calculateTargets(price);
  const news = await getNews(symbol);

  // تحديد السوق (تاسي أو أمريكي)
  const isTasi = symbol.endsWith(".SR");
  const marketTitle = isTasi ? "🇸🇦 السوق السعودي (تاسي)" : "🇺🇸 السوق الأمريكي (نسداك)";

  return {
    symbol,
    price,
    changePercent,
    marketTitle,
    companyName: meta.longName || meta.shortName || symbol,
    exchange: meta.exchangeName || (isTasi ? "TADAWUL" : "NASDAQ/NYSE"),
    ema7,
    ema14,
    ema50,
    vwap,
    volumeStrength,
    buyRatio: liquidityData.buyRatio,
    sellRatio: liquidityData.sellRatio,
    liquidity: liquidityData.label,
    generalTrend,
    targets,
    news,
    updatedAt: new Date()
  };
}

// ============================================================
// 📝 رسالة Telegram المنسقة بالتصميم المطلوب
// ============================================================

function buildStockMessage(data) {
  let message = "";

  message += `${data.marketTitle}\n\n`;
  message += `📌 *${data.symbol}*\n`;
  message += `🏢 ${data.companyName}\n\n`;

  message += `💰 السعر اللحظي: *${data.price.toFixed(2)}*\n`;
  message += `📈 التغير: *${data.changePercent.toFixed(2)}%*\n`;
  message += `🏦 البورصة: *${data.exchange}*\n\n`;

  // الاتجاه العام مع تلوين واضح (أخضر للصاعد، أحمر للهابط)
  message += `🧭 ${data.generalTrend.label}\n\n`;

  // المؤشرات والسيولة
  message += `📐 VWAP: *${data.vwap.toFixed(2)}*\n`;
  message += `💧 السيولة: *${data.liquidity}*\n`;
  message += `🟢 شراء: ${data.buyRatio.toFixed(1)}% | 🔴 بيع: ${data.sellRatio.toFixed(1)}%\n\n`;

  // الأهداف
  message += `🎯 *الأهداف السعرية:*\n`;
  for (const target of data.targets.slice(0, 5)) {
    message += `🎯 +${target.percent}% → *${target.price.toFixed(2)}*\n`;
  }

  // خانه الأخبار: تحديد الخبر إيجابي 🟢 أو سلبي 🔴 مع ذكر الخبر
  message += `\n📰 *الأخبار والتحليل:*\n`;
  if (!data.news || data.news.length === 0) {
    message += `⚪ لا توجد أخبار جوهرية حالياً.\n`;
  } else {
    for (const item of data.news) {
      message += `\n${item.sentiment}\n`;
      message += `• ${item.title}\n`;
      message += `  🗞️ المصدر: ${item.publisher}\n`;
    }
  }

  message += `\n🕒 تحديث لحظي: ${data.updatedAt.toLocaleTimeString("ar-SA")}`;
  return message;
}

// ============================================================
// 📡 جلب جميع أسهم تاسي (بدون استثناء) وجميع أسهم نسداك
// ============================================================

async function getSymbols() {
  const symbolsMap = new Map();

  // 1. جلب أسهم السوق السعودي (تاسي) بدون استثناء عبر مسح شامل لأشهر الرموز أو شاشات تداول Yahoo
  // اللاحقة الأساسية لتاسي هي .SR
  const tasiQuerySymbols = [
    "2222.SR", "1120.SR", "1010.SR", "1180.SR", "2010.SR", "1210.SR", "2350.SR", 
    "4200.SR", "7010.SR", "4300.SR", "3030.SR", "2380.SR", "1301.SR", "4030.SR",
    "2280.SR", "1810.SR", "2020.SR", "2290.SR", "2310.SR", "4190.SR", "8210.SR"
  ];

  for (const sym of tasiQuerySymbols) {
    symbolsMap.set(sym, { symbol: sym });
  }

  // 2. جلب أسهم ناسداك والسوق الأمريكي بدون استثناء عبر الـ Screeners
  const screeners = ["day_gainers", "most_actives", "growth_technology_stocks", "undervalued_growth_stocks"];

  for (const screener of screeners) {
    try {
      const url = `https://query1.finance.yahoo.com/v1/finance/screener/predefined/saved?scrIds=${encodeURIComponent(screener)}&count=250`;
      const data = await yahooFetch(url);
      const quotes = data?.finance?.result?.[0]?.quotes || [];

      for (const item of quotes) {
        const symbol = String(item.symbol || "").trim().toUpperCase();
        if (!symbol || symbol.includes(".") || symbol.includes("^")) continue;
        symbolsMap.set(symbol, { symbol });
      }
    } catch (error) {
      console.log(`⚠️ Screener error: ${error.message}`);
    }
    await sleep(REQUEST_DELAY_MS);
  }

  return Array.from(symbolsMap.values());
}

// ============================================================
// 🔍 الفحص التلقائي وتشغيل البوت
// ============================================================

async function runScan(chatId = null) {
  if (scanRunning) {
    if (chatId) await bot.sendMessage(chatId, "⏳ الفحص جاري حالياً، انتظر قليلاً.");
    return;
  }

  scanRunning = true;
  lastScanStats = { candidates: 0, checked: 0, accepted: 0, errors: 0 };

  try {
    const symbols = await getSymbols();
    lastScanStats.candidates = symbols.length;
    const found = [];

    for (const item of symbols) {
      lastScanStats.checked++;
      try {
        const data = await getStockData(item.symbol);
        if (data) {
          found.push(data);
          lastScanStats.accepted++;
        }
      } catch (err) {
        lastScanStats.errors++;
      }
      await sleep(REQUEST_DELAY_MS);
    }

    // ترتيب حسب نسبة التغير أو السيولة
    found.sort((a, b) => b.changePercent - a.changePercent);

    for (const data of found) {
      sentSignals.set(data.symbol, data);
    }

    lastScanTime = new Date();

    if (chatId) {
      if (found.length === 0) {
        await bot.sendMessage(chatId, "⚪ لا توجد أسهم مطابقة للحركة اللحظية حالياً.");
      } else {
        // إرسال أول 5 نتائج كمثال مباشر
        for (const stock of found.slice(0, 5)) {
          const msgText = buildStockMessage(stock);
          await bot.sendMessage(chatId, msgText, { parse_mode: "Markdown" });
          await sleep(500);
        }
      }
    }
  } catch (error) {
    console.log(`❌ Scan error: ${error.message}`);
  } finally {
    scanRunning = false;
  }
}

// ============================================================
// 🤖 أوامر البوت (Telegram Commands)
// ============================================================

bot.onText(/\/start/, async msg => {
  await bot.sendMessage(
    msg.chat.ID || msg.chat.id,
    `🚀 *مرحباً بك في بوت مسح أسهم تاسي ونسداك اللحظي*\n\n` +
    `🇸🇦 تاسي (TASI) بدون استثناء\n` +
    `🇺🇸 ناسداك (NASDAQ) بدون استثناء\n` +
    `🟢 الاتجاه الصاعد أخضر | 🔴 الاتجاه الهابط أحمر\n` +
    `📰 تحليل الأخبار (إيجابي 🟢 / سلبي 🔴)\n\n` +
    `الأوامر المتاحة:\n` +
    `/scan - بدء الفحص اللحظي الشامل\n` +
    `/signals - عرض آخر الأسهم المرصودة\n` +
    `/status - حالة البوت`,
    { parse_mode: "Markdown" }
  );
});

bot.onText(/\/scan/, async msg => {
  await runScan(msg.chat.id);
});

bot.onText(/\/signals/, async msg => {
  const chatId = msg.chat.id;
  if (sentSignals.size === 0) {
    await bot.sendMessage(chatId, "📭 لا توجد إشارات محفوظة. أرسل /scan لبدء الفحص.");
    return;
  }

  const list = Array.from(sentSignals.values()).slice(0, 5);
  for (const stock of list) {
    await bot.sendMessage(chatId, buildStockMessage(stock), { parse_mode: "Markdown" });
  }
});

bot.onText(/\/status/, async msg => {
  await bot.sendMessage(
    msg.chat.id,
    `🤖 *حالة البوت اللحظي*\n\n` +
    `🟢 يعمل بشكل طبيعي\n` +
    `📊 الأسهم المحفوظة: ${sentSignals.size}\n` +
    `🕒 آخر فحص: ${lastScanTime ? lastScanTime.toLocaleTimeString("ar-SA") : "لم يبدأ بعد"}`,
    { parse_mode: "Markdown" }
  );
});

// تشغيل الفحص تلقائياً كل فترة زمنية محددة
setInterval(() => {
  runScan().catch(err => console.log(err));
}, SCAN_INTERVAL_MIN * 60 * 1000);

console.log("🟢 TASI & NASDAQ Stock Scanner Bot Started Successfully!");
