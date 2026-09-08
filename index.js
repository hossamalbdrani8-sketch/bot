
// ============================================================
// 📊 DUAL AUTONOMOUS STOCK SCANNER BOTS - TASI & US
// EODHD API | FULL TASI + FULL US
// Node.js 18+
// ============================================================

"use strict";

const express = require("express");
const TelegramBot = require("node-telegram-bot-api");

// ============================================================
// ⚙️ الإعدادات والمفاتيح الرسمية
// ============================================================

const TASI_TOKEN = process.env.TASI_TOKEN || "7772382813:AAECFDY04AXNEf-Q98_65UheUEz7u2HymJw"
const US_TOKEN = process.env.US_TOKEN || "8652994768:AAHg_ABByrZdvlljJ1dQfs6LSmBl37XMPXk"
const EODHD_API_KEY = process.env.EODHD_API_KEY || "6a9ef3fd5c9378.52846267"

if (
  !TASI_TOKEN ||
  !US_TOKEN ||
  !EODHD_API_KEY ||
  TASI_TOKEN.startsWith("<") ||
  US_TOKEN.startsWith("<") ||
  EODHD_API_KEY.startsWith("<")
) {
  throw new Error("❌ يرجى التأكد من توفر توكنات البوتين ومفتاح EODHD.");
}

const PORT = Number(process.env.PORT || 3000);

const MIN_PRICE_US = 0.20;
const REQUEST_DELAY_MS = 250;
const UPDATE_INTERVAL_MIN = 2;

// ============================================================
// 🤖 إنشاء البوتين مع ضبط خيارات الاتصال لمنع التعارض 409
// ============================================================

const tasiBot = new TelegramBot(TASI_TOKEN, {
  polling: {
    interval: 2000,
    autoStart: true,
    params: {
      timeout: 10
    }
  }
});

const usBot = new TelegramBot(US_TOKEN, {
  polling: {
    interval: 2000,
    autoStart: true,
    params: {
      timeout: 10
    }
  }
});

// معالجة أخطاء البولينج لتجنب انهيار التطبيق
tasiBot.on("polling_error", (error) => {
  console.log(`⚠️ TASI Bot Polling Warning: ${error.message}`);
});

usBot.on("polling_error", (error) => {
  console.log(`⚠️ US Bot Polling Warning: ${error.message}`);
});

const tasiSubscribers = new Set();
const usSubscribers = new Set();

let tasiScanRunning = false;
let usScanRunning = false;

// ============================================================
// 🌐 خادم Express للحفاظ على التشغيل ورابط Railway
// ============================================================

const app = express();

app.get("/", (req, res) => {
  res.status(200).send("🌍 TASI & US EODHD Autonomous Bots are running");
});

app.get("/health", (req, res) => {
  res.json({
    ok: true,
    tasiSubscribers: tasiSubscribers.size,
    usSubscribers: usSubscribers.size,
    tasiScanRunning,
    usScanRunning,
    time: new Date().toISOString()
  });
});

app.listen(PORT, () => {
  console.log(`🌐 Server running on port ${PORT}`);
});

// ============================================================
// ⏱️ أدوات عامة وفحص الأسواق
// ============================================================

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

async function fetchEodhd(url) {
  const response = await fetch(url, {
    headers: { "User-Agent": "Mozilla/5.0" }
  });
  const text = await response.text();
  if (!response.ok) {
    throw new Error(`EODHD HTTP ${response.status}: ${text.slice(0, 150)}`);
  }
  try {
    return JSON.parse(text);
  } catch {
    throw new Error("EODHD returned invalid JSON");
  }
}

async function getExchangeSymbols(exchange) {
  const url = `https://eodhd.com/api/exchange-symbol-list/${exchange}?api_token=${EODHD_API_KEY}&fmt=json`;
  const data = await fetchEodhd(url);
  if (!Array.isArray(data)) {
    throw new Error(`لم يتم استلام قائمة صحيحة للسوق ${exchange}`);
  }
  return data;
}

async function getFullTasiSymbols() {
  const rows = await getExchangeSymbols("SR");
  const symbols = rows
    .filter(item => {
      const type = String(item.Type || "").toLowerCase();
      return type.includes("stock") || type.includes("common");
    })
    .map(item => String(item.Code || "").trim())
    .filter(Boolean);
  return [...new Set(symbols)];
}

async function getFullUsSymbols() {
  const rows = await getExchangeSymbols("US");
  const symbols = rows
    .filter(item => {
      const type = String(item.Type || "").toLowerCase();
      return type.includes("stock") || type.includes("common") || type.includes("preferred");
    })
    .map(item => String(item.Code || "").trim())
    .filter(Boolean);
  return [...new Set(symbols)];
}

function normalizeTickerForEodhd(symbol) {
  return String(symbol || "").trim().replace(/\./g, "-");
}

function calculateEMA(values, period) {
  if (!Array.isArray(values) || values.length < period) return null;
  const multiplier = 2 / (period + 1);
  let ema = 0;
  for (let i = 0; i < period; i++) {
    ema += Number(values[i]) || 0;
  }
  ema /= period;
  for (let i = period; i < values.length; i++) {
    const val = Number(values[i]);
    if (Number.isFinite(val)) {
      ema = (val - ema) * multiplier + ema;
    }
  }
  return ema;
}

function calculateVWAP(high, low, close, volume) {
  let pv = 0;
  let totalVolume = 0;
  const len = Math.min(high.length, low.length, close.length, volume.length);
  const start = Math.max(0, len - 30);
  for (let i = start; i < len; i++) {
    const h = Number(high[i]);
    const l = Number(low[i]);
    const c = Number(close[i]);
    const v = Number(volume[i]);
    if (!Number.isFinite(h) || !Number.isFinite(l) || !Number.isFinite(c) || !Number.isFinite(v) || v <= 0) continue;
    pv += ((h + l + c) / 3) * v;
    totalVolume += v;
  }
  return totalVolume > 0 ? pv / totalVolume : null;
}

function analyzeLiquidity(close, volume) {
  const len = Math.min(close.length, volume.length);
  const start = Math.max(1, len - 10);
  let buyVol = 0, sellVol = 0, neutVol = 0;
  for (let i = start; i < len; i++) {
    const prev = Number(close[i - 1]);
    const curr = Number(close[i]);
    const vol = Number(volume[i]) || 0;
    if (!Number.isFinite(prev) || !Number.isFinite(curr)) continue;
    if (curr > prev) buyVol += vol;
    else if (curr < prev) sellVol += vol;
    else neutVol += vol;
  }
  const total = buyVol + sellVol + neutVol;
  if (total <= 0) return { buyRatio: 50, sellRatio: 50, label: "⚪ سيولة متوازنة" };
  const buyRatio = (buyVol / total) * 100;
  const sellRatio = (sellVol / total) * 100;
  let label = "⚪ سيولة متوازنة";
  if (buyRatio >= 65) label = "🟢 دخول سيولة قوية";
  else if (sellRatio >= 65) label = "🔴 خروج سيولة قوية";
  else if (buyRatio >= 53) label = "🟢 دخول سيولة";
  else if (sellRatio >= 53) label = "🔴 خروج سيولة";
  return { buyRatio, sellRatio, label };
}

function analyzeGeneralTrend(price, ema50, ema180) {
  if (Number.isFinite(ema50) && Number.isFinite(ema180)) {
    if (ema50 > ema180 && price > ema50) return "🟢 الاتجاه العام صاعد";
    if (ema50 < ema180 && price < ema50) return "🔴 الاتجاه العام هابط";
  }
  return "⚪ الاتجاه العام متوازن";
}

function calculateSupportResistance(highs, lows, price) {
  const pivotHighs = [];
  const pivotLows = [];
  const leftRight = 3;
  for (let i = leftRight; i < highs.length - leftRight; i++) {
    const currentHigh = Number(highs[i]);
    const currentLow = Number(lows[i]);
    if (!Number.isFinite(currentHigh) || !Number.isFinite(currentLow)) continue;
    let isHigh = true, isLow = true;
    for (let j = 1; j <= leftRight; j++) {
      if (currentHigh <= Number(highs[i - j]) || currentHigh <= Number(highs[i + j])) isHigh = false;
      if (currentLow >= Number(lows[i - j]) || currentLow >= Number(lows[i + j])) isLow = false;
    }
    if (isHigh) pivotHighs.push(currentHigh);
    if (isLow) pivotLows.push(currentLow);
  }
  const tolerance = Math.max(price * 0.003, 0.01);
  function clusterLevels(levels) {
    const sorted = [...levels].sort((a, b) => a - b);
    const clusters = [];
    for (const level of sorted) {
      const last = clusters[clusters.length - 1];
      if (!last || Math.abs(level - last.price) > tolerance) {
        clusters.push({ price: level, count: 1 });
      } else {
        last.price = (last.price * last.count + level) / (last.count + 1);
        last.count++;
      }
    }
    return clusters;
  }
  const supports = clusterLevels(pivotLows.filter(l => l < price)).sort((a, b) => b.price - a.price).slice(0, 3).map(x => x.price);
  const resistances = clusterLevels(pivotHighs.filter(l => l > price)).sort((a, b) => a.price - b.price).slice(0, 3).map(x => x.price);
  return { supports, resistances };
}

function calculateTargets(price) {
  return [2, 4, 6, 8, 10, 12, 15, 18].map(p => ({
    percent: p,
    price: price * (1 + p / 100),
    achieved: price >= price * (1 + p / 100)
  }));
}

const sourceArabicMap = {
  "Reuters": "رويترز", "Bloomberg": "بلومبرغ", "Yahoo Finance": "ياهو المالية",
  "MarketWatch": "ماركت ووتش", "CNBC": "سي إن بي سي", "Business Wire": "بيزنس واير",
  "GlobeNewswire": "غلوب نيوز واير", "PR Newswire": "بي آر نيوزواير", "Seeking Alpha": "سيكنغ ألفا"
};

function translateSourceToArabic(source) {
  if (!source) return "مصدر مالي";
  const clean = String(source).trim();
  return sourceArabicMap[clean] || clean;
}

async function translateToArabic(text) {
  if (!text) return "";
  const original = String(text).trim();
  if (!original || /[\u0600-\u06FF]/.test(original)) return original;
  try {
    const url = `https://translate.googleapis.com/translate_a/single?client=gtx&sl=auto&tl=ar&dt=t&q=${encodeURIComponent(original)}`;
    const response = await fetch(url);
    if (!response.ok) return original;
    const data = await response.json();
    return data?.[0]?.[0]?.[0] || original;
  } catch {
    return original;
  }
}

const newsCache = new Map();
const NEWS_CACHE_MS = 5 * 60 * 1000;

async function getStockNews(symbol, exchange) {
  const ticker = `${normalizeTickerForEodhd(symbol)}.${exchange}`;
  const cached = newsCache.get(ticker);
  if (cached && Date.now() - cached.time < NEWS_CACHE_MS) return cached.news;
  const url = `https://eodhd.com/api/news?s=${encodeURIComponent(ticker)}&offset=0&limit=3&api_token=${EODHD_API_KEY}&fmt=json`;
  try {
    const data = await fetchEodhd(url);
    if (!Array.isArray(data)) return [];
    const news = [];
    for (const item of data.slice(0, 3)) {
      news.push({
        title: await translateToArabic(item.title || item.content || ""),
        source: translateSourceToArabic(item.source || item.site || ""),
        date: item.date || item.publishedAt || ""
      });
    }
    newsCache.set(ticker, { time: Date.now(), news });
    return news;
  } catch {
    return [];
  }
}

async function getStockDataFromEodhd(symbol, exchangeSuffix, minPriceAllowed) {
  const ticker = `${normalizeTickerForEodhd(symbol)}.${exchangeSuffix}`;
  const url = `https://eodhistoricaldata.com/api/eod/${ticker}?api_token=${EODHD_API_KEY}&fmt=json&period=d&limit=200`;
  const data = await fetchEodhd(url);
  if (!Array.isArray(data) || data.length < 50) throw new Error("بيانات غير كافية");
  const closes = data.map(i => Number(i.close)).filter(Number.isFinite);
  const highs = data.map(i => Number(i.high)).filter(Number.isFinite);
  const lows = data.map(i => Number(i.low)).filter(Number.isFinite);
  const volumes = data.map(i => Number(i.volume)).filter(Number.isFinite);
  const price = closes[closes.length - 1];
  if (!Number.isFinite(price) || price < minPriceAllowed) throw new Error("السعر أقل من الحد الأدنى");
  const prevClose = closes[closes.length - 2] || price;
  const changePercent = prevClose > 0 ? ((price - prevClose) / prevClose) * 100 : 0;
  
  const liquidity = analyzeLiquidity(closes, volumes);
  const levels = calculateSupportResistance(highs, lows, price);

  return {
    symbol,
    price,
    changePercent,
    companyName: symbol,
    exchange: exchangeSuffix === "SR" ? "تداول (تاسي)" : "السوق الأمريكي",
    vwap: calculateVWAP(highs, lows, closes, volumes) || price,
    ema7: calculateEMA(closes, 7),
    ema14: calculateEMA(closes, 14),
    ema25: calculateEMA(closes, 25),
    ema50: calculateEMA(closes, 50),
    ema180: calculateEMA(closes, 180) || calculateEMA(closes, 50),
    buyRatio: liquidity.buyRatio,
    sellRatio: liquidity.sellRatio,
    liquidityLabel: liquidity.label,
    generalTrend: analyzeGeneralTrend(price, calculateEMA(closes, 50), calculateEMA(closes, 180)),
    supports: levels.supports,
    resistances: levels.resistances,
    targets: calculateTargets(price),
    news: await getStockNews(symbol, exchangeSuffix),
    updatedAt: new Date()
  };
}

function buildMessage(stock, marketName) {
  let msg = `📊 *${marketName}*\n\n`;
  msg += `📌 الرمز: *${stock.symbol}*\n`;
  msg += `💰 السعر: *${stock.price.toFixed(2)}*\n`;
  msg += `📈 نسبة التغير: *${stock.changePercent.toFixed(2)}%*\n\n`;
  msg += `🧭 ${stock.generalTrend}\n`;
  msg += `📐 VWAP: *${stock.vwap.toFixed(2)}*\n`;
  msg += `💧 السيولة: *${stock.liquidityLabel}* (شراء ${stock.buyRatio.toFixed(1)}% | بيع ${stock.sellRatio.toFixed(1)}%)\n\n`;
  
  msg += `📉 *الدعوم:*\n`;
  (stock.supports.length ? stock.supports : [0]).forEach((l, i) => {
    msg += `• دعم ${i + 1}: *${l.toFixed(2)}*\n`;
  });
  
  msg += `\n🔴 *المقاومات:*\n`;
  (stock.resistances.length ? stock.resistances : [0]).forEach((l, i) => {
    msg += `• مقاومة ${i + 1}: *${l.toFixed(2)}*\n`;
  });
  
  msg += `\n🕒 التحديث: ${stock.updatedAt.toLocaleTimeString("ar-SA")}`;
  return msg;
}

async function runTasiAutoScan() {
  if (tasiScanRunning || tasiSubscribers.size === 0) return;
  tasiScanRunning = true;
  try {
    const symbols = await getFullTasiSymbols();
    for (const sym of symbols) {
      try {
        const stock = await getStockDataFromEodhd(sym, "SR", 0.01);
        if (stock) {
          for (const chatId of tasiSubscribers) {
            await tasiBot.sendMessage(chatId, buildMessage(stock, "🇸🇦 السوق السعودي (تاسي)"), { parse_mode: "Markdown" });
            await sleep(200);
          }
        }
      } catch (e) {}
      await sleep(REQUEST_DELAY_MS);
    }
  } finally {
    tasiScanRunning = false;
  }
}

async function runUsAutoScan() {
  if (usScanRunning || usSubscribers.size === 0) return;
  usScanRunning = true;
  try {
    const symbols = await getFullUsSymbols();
    for (const sym of symbols) {
      try {
        const stock = await getStockDataFromEodhd(sym, "US", MIN_PRICE_US);
        if (stock) {
          for (const chatId of usSubscribers) {
            await usBot.sendMessage(chatId, buildMessage(stock, "🇺🇸 السوق الأمريكي"), { parse_mode: "Markdown"  });
            await sleep(200);
          }
        }
      } catch (e) {}
      await sleep(REQUEST_DELAY_MS);
    }
  } finally {
    usScanRunning = false;
  }
}

tasiBot.onText(/\/start|\/scan/, async msg => {
  const chatId = msg.chat.id;
  tasiSubscribers.add(chatId);
  await tasiBot.sendMessage(chatId, "🇸🇦 تم تفعيل بوت السوق السعودي وبدء الفحص...");
  runTasiAutoScan();
});

usBot.onText(/\/start|\/scan/, async msg => {
  const chatId = msg.chat.id;
  usSubscribers.add(chatId);
  await usBot.sendMessage(chatId, "🇺🇸 تم تفعيل بوت السوق الأمريكي وبدء الفحص...");
  runUsAutoScan();
});

setInterval(runTasiAutoScan, UPDATE_INTERVAL_MIN * 60 * 1000);
setInterval(runUsAutoScan, UPDATE_INTERVAL_MIN * 60 * 1000);

console.log("🟢 EODHD Stock Scanners are running successfully!");
