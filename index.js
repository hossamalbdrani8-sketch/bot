
// ============================================================
// 📊 EODHD AI PRO MAX STOCK SCANNER BOT (TASI & US)
// ============================================================

"use strict";

const express = require("express");
const TelegramBot = require("node-telegram-bot-api");

const TASI_TOKEN = process.env.TASI_TOKEN;
const US_TOKEN = process.env.US_TOKEN;
const EODHD_API_KEY = process.env.EODHD_API_KEY;

const PORT = Number(process.env.PORT || 3000);
const REQUEST_DELAY_MS = 300;
const UPDATE_INTERVAL_MIN = 3;

const app = express();
app.use(express.json());

const tasiBot = new TelegramBot(TASI_TOKEN, { polling: false });
const usBot = new TelegramBot(US_TOKEN, { polling: false });

const tasiSubscribers = new Set();
const usSubscribers = new Set();

let tasiScanRunning = false;
let usScanRunning = false;

app.get("/", (req, res) => {
  res.status(200).send("🚀 EODHD AI PRO MAX Stock Scanner is Online");
});

app.listen(PORT, async () => {
  console.log(`🌐 Server running on port ${PORT}`);
  try {
    await tasiBot.deleteWebHook({ drop_pending_updates: true });
    await usBot.deleteWebHook({ drop_pending_updates: true });
    
    await tasiBot.startPolling();
    await usBot.startPolling();
    console.log("✅ Telegram Bots started polling cleanly.");
  } catch (e) {
    console.log("⚠️ Polling notice:", e.message);
  }
});

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

async function fetchEodhd(url) {
  const response = await fetch(url, {
    headers: { "User-Agent": "Mozilla/5.0" }
  });
  const text = await response.text();
  if (!response.ok) {
    throw new Error(`EODHD HTTP ${response.status}`);
  }
  try {
    return JSON.parse(text);
  } catch {
    throw new Error("Invalid JSON");
  }
}

async function getExchangeSymbols(exchange) {
  const url = `https://eodhd.com/api/exchange-symbol-list/${exchange}?api_token=${EODHD_API_KEY}&fmt=json`;
  const data = await fetchEodhd(url);
  if (!Array.isArray(data)) throw new Error("Invalid symbols list");
  return data
    .filter(item => {
      const type = String(item.Type || "").toLowerCase();
      return type.includes("stock") || type.includes("common");
    })
    .map(item => String(item.Code || "").trim())
    .filter(Boolean);
}

async function calculateATR(highs, lows, closes, period = 14) {
  if (highs.length < period + 1) return 0;
  let trList = [];
  for (let i = 1; i < highs.length; i++) {
    const tr = Math.max(highs[i] - lows[i], Math.abs(highs[i] - closes[i - 1]), Math.abs(lows[i] - closes[i - 1]));
    trList.push(tr);
  }
  const recentTr = trList.slice(-period);
  return recentTr.reduce((a, b) => a + b, 0) / recentTr.length;
}

function analyzeLiquidity(closes, volumes) {
  const len = Math.min(closes.length, volumes.length);
  const start = Math.max(1, len - 10);
  let buyVol = 0, sellVol = 0, neutVol = 0;
  for (let i = start; i < len; i++) {
    const prev = closes[i - 1];
    const curr = closes[i];
    const vol = volumes[i] || 0;
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

function aiProMaxTrend(closes, highs, lows) {
  const currentPrice = closes[closes.length - 1];
  const shortLen = Math.min(closes.length, 14);
  let momentumScore = 0;
  
  for (let i = closes.length - shortLen; i < closes.length; i++) {
    if (closes[i] > closes[i - 1]) momentumScore++;
    else if (closes[i] < closes[i - 1]) momentumScore--;
  }

  const recentHigh = Math.max(...highs.slice(-10));
  const recentLow = Math.min(...lows.slice(-10));
  
  if (momentumScore >= 3 && currentPrice >= recentLow * 1.02) {
    return { direction: "UP", label: "🚀 اتجاه صاعد (AI PRO MAX)" };
  } else if (momentumScore <= -3 || currentPrice <= recentHigh * 0.98) {
    return { direction: "DOWN", label: "⚠️ اتجاه هابط (AI PRO MAX)" };
  }
  return { direction: "NEUTRAL", label: "⚖️ اتجاه عرضي متوازن" };
}

function calculateSupportResistance(highs, lows, price) {
  const pivotHighs = [];
  const pivotLows = [];
  for (let i = 2; i < highs.length - 2; i++) {
    if (highs[i] > highs[i - 1] && highs[i] > highs[i + 1]) pivotHighs.push(highs[i]);
    if (lows[i] < lows[i - 1] && lows[i] < lows[i + 1]) pivotLows.push(lows[i]);
  }
  const supports = pivotLows.filter(l => l < price).sort((a, b) => b - a).slice(0, 2);
  const resistances = pivotHighs.filter(h => h > price).sort((a, b) => a - b).slice(0, 2);
  return {
    supports: supports.length ? supports : [price * 0.95],
    resistances: resistances.length ? resistances : [price * 1.05]
  };
}

async function getStockData(symbol, exchangeSuffix, minPrice) {
  const formattedSymbol = `${symbol.replace(/\./g, "-")}.${exchangeSuffix}`;
  const url = `https://eodhistoricaldata.com/api/eod/${formattedSymbol}?api_token=${EODHD_API_KEY}&fmt=json&period=d&limit=60`;
  
  const data = await fetchEodhd(url);
  if (!Array.isArray(data) || data.length < 20) throw new Error("بيانات غير كافية");

  const closes = data.map(i => Number(i.close)).filter(Number.isFinite);
  const highs = data.map(i => Number(i.high)).filter(Number.isFinite);
  const lows = data.map(i => Number(i.low)).filter(Number.isFinite);
  const volumes = data.map(i => Number(i.volume)).filter(Number.isFinite);

  const price = closes[closes.length - 1];
  if (!Number.isFinite(price) || price < minPrice) throw new Error("السعر أقل");

  const prevClose = closes[closes.length - 2] || price;
  const changePercent = ((price - prevClose) / prevClose) * 100;

  const trendObj = aiProMaxTrend(closes, highs, lows);
  const atr = await calculateATR(highs, lows, closes, 14);
  const liquidity = analyzeLiquidity(closes, volumes);
  const levels = calculateSupportResistance(highs, lows, price);

  let targets = [];
  const icon = trendObj.direction === "UP" ? "✅" : "🔴";
  
  for (let i = 1; i <= 4; i++) {
    let targetPrice = trendObj.direction === "UP" ? price + (atr * i * 0.6) : price - (atr * i * 0.6);
    let reached = trendObj.direction === "UP" ? price >= targetPrice : price <= targetPrice;
    targets.push({
      level: i,
      price: targetPrice,
      status: reached ? `${icon} (تحقق)` : `⏳ (قيد الانتظار)`
    });
  }

  return {
    symbol,
    price,
    changePercent,
    trend: trendObj.label,
    liquidity: liquidity.label,
    buyRatio: liquidity.buyRatio,
    supports: levels.supports,
    resistances: levels.resistances,
    targets,
    updated: new Date()
  };
}

function buildAlertMessage(stock, marketName) {
  let msg = `📊 *${marketName}*\n\n`;
  msg += `📌 الرمز: *${stock.symbol}*\n`;
  msg += `💰 السعر: *${stock.price.toFixed(2)}*\n`;
  msg += `📈 التغير: *${stock.changePercent.toFixed(2)}%*\n\n`;
  msg += `🤖 *${stock.trend}*\n`;
  msg += `💧 السيولة: *${stock.liquidity}* (${stock.buyRatio.toFixed(1)}%)\n\n`;
  
  msg += `🎯 *الأهداف الذكية (ATR):*\n`;
  stock.targets.forEach(t => {
    msg += `• الهدف ${t.level}: *${t.price.toFixed(2)}* ${t.status}\n`;
  });

  msg += `\n📉 *الدعوم:* ${stock.supports.map(s => s.toFixed(2)).join(" | ")}\n`;
  msg += `📈 *المقاومات:* ${stock.resistances.map(r => r.toFixed(2)).join(" | ")}\n\n`;
  msg += `🕒 ${stock.updated.toLocaleTimeString("ar-SA")}`;
  return msg;
}

async function runTasiScan() {
  if (tasiScanRunning || tasiSubscribers.size === 0) return;
  tasiScanRunning = true;
  try {
    const symbols = await getExchangeSymbols("SR");
    for (const sym of symbols.slice(0, 10)) {
      try {
        const stock = await getStockData(sym, "SR", 0.01);
        for (const chatId of tasiSubscribers) {
          await tasiBot.sendMessage(chatId, buildAlertMessage(stock, "🇸🇦 السوق السعودي (تاسي)"), { parse_mode: "Markdown" });
          await sleep(200);
        }
      } catch (e) {}
      await sleep(REQUEST_DELAY_MS);
    }
  } finally {
    tasiScanRunning = false;
  }
}

async function runUsScan() {
  if (usScanRunning || usSubscribers.size === 0) return;
  usScanRunning = true;
  try {
    const symbols = await getExchangeSymbols("US");
    for (const sym of symbols.slice(0, 10)) {
      try {
        const stock = await getStockData(sym, "US", 0.20);
        for (const chatId of usSubscribers) {
          await usBot.sendMessage(chatId, buildAlertMessage(stock, "🇺🇸 السوق الأمريكي"), { parse_mode: "Markdown" });
          await sleep(200);
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
  await tasiBot.sendMessage(chatId, "🇸🇦 تم تفعيل بوت السوق السعودي بنجاح، جاري جلب التحليلات الفورية...", { parse_mode: "Markdown" });
  runTasiScan();
});

usBot.onText(/\/start|\/scan/, async msg => {
  const chatId = msg.chat.id;
  usSubscribers.add(chatId);
  await usBot.sendMessage(chatId, "🇺🇸 تم تفعيل بوت السوق الأمريكي بنجاح، جاري جلب التحليلات الفورية...", { parse_mode: "Markdown" });
  runUsScan();
});

setInterval(runTasiScan, UPDATE_INTERVAL_MIN * 60 * 1000);
setInterval(runUsScan, UPDATE_INTERVAL_MIN * 60 * 1000);

console.log("💎 Bot Engine Running Cleanly.");
