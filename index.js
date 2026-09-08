
// ============================================================
// 📊 DUAL AUTONOMOUS STOCK SCANNER BOTS - TASI & US (EODHD API)
// Node.js 18+ | بوت تاسي وبوت أمريكي مدعومان بمفتاح EODHD
// ============================================================

"use strict";

const express = require("express");
const TelegramBot = require("node-telegram-bot-api");

// ============================================================
// ⚙️ الإعدادات والمفاتيح الرسمية
// ============================================================

const TASI_TOKEN = "7772382813:AAECFDY04AXNEf-Q98_65UheUEz7u2HymJw";
const US_TOKEN = "8652994768:AAHg_ABByrZdvlljJ1dQfs6LSmBl37XMPXk";
const EODHD_API_KEY = "6a9ef3fd5c9378.52846267";

if (!TASI_TOKEN || !US_TOKEN) {
  throw new Error("❌ يرجى التأكد من توفر توكنات البوتين.");
}

const PORT = Number(process.env.PORT || 3000);
const MIN_PRICE_US = 0.20; // الحد الأدنى لسعر السهم الأمريكي
const REQUEST_DELAY_MS = 250;
const UPDATE_INTERVAL_MIN = 2; // التحديث التلقائي كل دقيقتين

// ============================================================
// 🤖 إنشاء البوتين بشكل منفصل
// ============================================================

const tasiBot = new TelegramBot(TASI_TOKEN, { polling: true });
const usBot = new TelegramBot(US_TOKEN, { polling: true });

const tasiSubscribers = new Set();
const usSubscribers = new Set();

// ============================================================
// 🌐 خادم Express للحفاظ على تشغيل البوت 24/7
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
    time: new Date().toISOString()
  });
});

app.listen(PORT, () => {
  console.log(`🌐 Server running on port ${PORT}`);
});

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

async function fetchEodhd(url) {
  const response = await fetch(url, {
    headers: {
      "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    }
  });

  const text = await response.text();
  if (!response.ok) {
    throw new Error(`EODHD HTTP ${response.status}: ${text.slice(0, 100)}`);
  }

  try {
    return JSON.parse(text);
  } catch {
    throw new Error("EODHD returned invalid JSON");
  }
}

// جلب البيانات التاريخية واللحظية باستخدام مفتاح EODHD
async function getStockDataFromEodhd(symbol, exchangeSuffix, minPriceAllowed) {
  const ticker = `${symbol}.${exchangeSuffix}`;
  const url = `https://eodhistoricaldata.com/api/eod/${ticker}?api_token=${EODHD_API_KEY}&fmt=json&period=d&limit=200`;
  
  const data = await fetchEodhd(url);
  if (!Array.isArray(data) || data.length < 50) {
    throw new Error("بيانات غير كافية من EODHD");
  }

  const closes = data.map(item => Number(item.close)).filter(Number.isFinite);
  const highs = data.map(item => Number(item.high)).filter(Number.isFinite);
  const lows = data.map(item => Number(item.low)).filter(Number.isFinite);
  const volumes = data.map(item => Number(item.volume)).filter(Number.isFinite);

  const price = closes[closes.length - 1];
  if (price < minPriceAllowed) throw new Error("السعر أقل من الحد الأدنى");

  const prevClose = closes[closes.length - 2] || price;
  const changePercent = prevClose > 0 ? ((price - prevClose) / prevClose) * 100 : 0;

  // حساب المتوسطات الأسية EMA (7, 14, 25, 50, 180)
  const ema7 = calculateEMA(closes, 7);
  const ema14 = calculateEMA(closes, 14);
  const ema25 = calculateEMA(closes, 25);
  const ema50 = calculateEMA(closes, 50);
  const ema180 = calculateEMA(closes, 180) || ema50;

  const vwap = calculateVWAP(highs, lows, closes, volumes) || price;
  const liquidity = analyzeLiquidity(closes, volumes);
  const generalTrend = analyzeGeneralTrend(price, ema50, ema180);
  const targets = calculateTargets(price);

  return {
    symbol,
    price,
    changePercent,
    companyName: symbol,
    exchange: exchangeSuffix === "SR" ? "تداول (TADAWUL)" : "NASDAQ/NYSE",
    vwap,
    ema7,
    ema14,
    ema25,
    ema50,
    ema180,
    buyRatio: liquidity.buyRatio,
    sellRatio: liquidity.sellRatio,
    liquidityLabel: liquidity.label,
    generalTrend,
    targets,
    updatedAt: new Date()
  };
}

function calculateEMA(values, period) {
  if (!Array.isArray(values) || values.length < period) return null;
  const multiplier = 2 / (period + 1);
  let ema = 0;
  for (let i = 0; i < period; i++) ema += Number(values[i]) || 0;
  ema /= period;
  for (let i = period; i < values.length; i++) {
    const val = Number(values[i]);
    if (Number.isFinite(val)) ema = (val - ema) * multiplier + ema;
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
    const prev = Number(close[i - 1]), curr = Number(close[i]), vol = Number(volume[i]) || 0;
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

function calculateTargets(price) {
  const percentages = [2, 4, 6, 8, 10, 12, 15, 18];
  return percentages.map(p => {
    const targetPrice = price * (1 + p / 100);
    const achieved = price >= targetPrice;
    return { percent: p, price: targetPrice, achieved };
  });
}

function buildMessage(stock, marketName) {
  let msg = `📊 *${marketName} (EODHD)*\n\n`;
  msg += `📌 الرمز: *${stock.symbol}*\n`;
  msg += `🏢 الشركة: ${stock.companyName}\n\n`;
  msg += `💰 السعر اللحظي: *${stock.price.toFixed(2)}*\n`;
  msg += `📈 نسبة التغير: *${stock.changePercent.toFixed(2)}%*\n`;
  msg += `🏦 البورصة: ${stock.exchange}\n\n`;

  msg += `🧭 ${stock.generalTrend}\n`;
  msg += `📐 VWAP: *${stock.vwap.toFixed(2)}*\n`;
  msg += `💧 السيولة: *${stock.liquidityLabel}* (شراء ${stock.buyRatio.toFixed(1)}% | بيع ${stock.sellRatio.toFixed(1)}%)\n\n`;

  msg += `📊 *المتوسطات الأسية (EMA):*\n`;
  msg += `• EMA 7: ${stock.ema7 ? stock.ema7.toFixed(2) : "N/A"}\n`;
  msg += `• EMA 14: ${stock.ema14 ? stock.ema14.toFixed(2) : "N/A"}\n`;
  msg += `• EMA 25: ${stock.ema25 ? stock.ema25.toFixed(2) : "N/A"}\n`;
  msg += `• EMA 50: ${stock.ema50 ? stock.ema50.toFixed(2) : "N/A"}\n`;
  msg += `• EMA 180: ${stock.ema180 ? stock.ema180.toFixed(2) : "N/A"}\n\n`;

  msg += `🎯 *الأهداف السعرية (8 أهداف):*\n`;
  for (const t of stock.targets) {
    const statusMark = t.achieved ? " ✅" : "";
    msg += `• +${t.percent}% ➔ *${t.price.toFixed(2)}*${statusMark}\n`;
  }

  msg += `\n🕒 التحديث: ${stock.updatedAt.toLocaleTimeString("ar-SA")}`;
  return msg;
}

// ============================================================
// 🇸🇦 قوائم الأسهم السعودية والأمريكية
// ============================================================

const tasiSymbols = [
  "1010","1020","1030","1040","1050","1060","1080","1090","1111","1120",
  "1140","1150","1180","1201","1202","1210","1211","1212","1301","1302",
  "1303","1304","1320","1810","1820","1830","2001","2002","2010","2020",
  "2021","2030","2040","2050","2060","2070","2080","2090","2100","2110",
  "2120","2130","2140","2150","2160","2170","2180","2190","2200","2210",
  "2220","2222","2230","2240","2250","2270","2280","2282","2290","2300",
  "2310","2320","2330","2340","2350","2360","2370","2380","2381","2382",
  "3001","3002","3003","3004","3005","3007","3008","3010","3020","3030",
  "3040","3050","4001","4002","4003","4004","4005","4006","4007","4008",
  "4009","4010","4020","4030","4031","4040","4050","4051","4061","4071",
  "4081","4082","4090","4100","4110","4130","4140","4150","4160","4161",
  "4162","4163","4164","4180","4190","4191","4192","4193","4200","4210",
  "4220","4230","4240","4250","4260","4270","4280","4290","4300","4310",
  "4320","4321","4322","4323","4330","4331","4332","4333","4334","4335",
  "4336","4337","4338","4339","4340","6001","6002","6004","6010","6020",
  "6040","6060","7010","7020","7030","7040","7200","8010","8012","8020",
  "8030","8040","8050","8060","8070","8080","8090","8100","8110","8120",
  "8130","8140","8150","8160","8170","8180","8190","8200","8210","8230",
  "8240","8250","8260","8270","8280","8300","8310","8311","9510","9520",
  "9530","9540","9550","9560","9570","9580","9590"
];

const usSymbols = [
  "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "TSLA", "META", "NFLX", "AMD", "INTC", 
  "PLTR", "SNDK", "RIVN", "NIO", "PLUG", "SOFI", "BAC", "F", "VALE", "T"
];

async function runTasiAutoScan() {
  if (tasiSubscribers.size === 0) return;
  for (const sym of tasiSymbols) {
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
}

async function runUsAutoScan() {
  if (usSubscribers.size === 0) return;
  for (const sym of usSymbols) {
    try {
      const stock = await getStockDataFromEodhd(sym, "US", MIN_PRICE_US);
      if (stock) {
        for (const chatId of usSubscribers) {
          await usBot.sendMessage(chatId, buildMessage(stock, "🇺🇸 السوق الأمريكي"), { parse_mode: "Markdown" });
          await sleep(200);
        }
      }
    } catch (e) {}
    await sleep(REQUEST_DELAY_MS);
  }
}

// ============================================================
// 🤖 أوامر البوتات
// ============================================================

tasiBot.onText(/\/start/, async msg => {
  const chatId = msg.chat.id;
  tasiSubscribers.add(chatId);
  await tasiBot.sendMessage(chatId, "🇸🇦 *تم تفعيل بوت السوق السعودي عبر EODHD بنجاح!*", { parse_mode: "Markdown" });
  runTasiAutoScan();
});

tasiBot.onText(/\/scan/, async msg => {
  const chatId = msg.chat.id;
  tasiSubscribers.add(chatId);
  await tasiBot.sendMessage(chatId, "🔍 جاري الفحص الشامل لأسهم تاسي...");
  await runTasiAutoScan();
});

usBot.onText(/\/start/, async msg => {
  const chatId = msg.chat.id;
  usSubscribers.add(chatId);
  await usBot.sendMessage(chatId, "🇺🇸 *تم تفعيل بوت السوق الأمريكي عبر EODHD بنجاح!*", { parse_mode: "Markdown" });
  runUsAutoScan();
});

usBot.onText(/\/scan/, async msg => {
  const chatId = msg.chat.id;
  usSubscribers.add(chatId);
  await usBot.sendMessage(chatId, "🔍 جاري الفحص الشامل للأسهم الأمريكية...");
  await runUsAutoScan();
});

// الجدولة التلقائية كل دقيقتين
setInterval(runTasiAutoScan, UPDATE_INTERVAL_MIN * 60 * 1000);
setInterval(runUsAutoScan, UPDATE_INTERVAL_MIN * 60 * 1000);

console.log("🟢 EODHD Stock Scanners are running successfully!");
