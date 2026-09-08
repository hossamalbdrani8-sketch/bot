
// ============================================================
// 📊 DUAL AUTONOMOUS STOCK SCANNER BOTS - TASI & US (EODHD API)
// نسخة محسنة لمنع التجميد وضمان سرعة إرسال الإشعارات
// ============================================================

"use strict";

const express = require("express");
const TelegramBot = require("node-telegram-bot-api");

const TASI_TOKEN = "7772382813:AAECFDY04AXNEf-Q98_65UheUEz7u2HymJw";
const US_TOKEN = "8652994768:AAHg_ABByrZdvlljJ1dQfs6LSmBl37XMPXk";
const EODHD_API_KEY = "6a9ef3fd5c9378.52846267";

const PORT = Number(process.env.PORT || 3000);
const MIN_PRICE_US = 0.20;

const tasiBot = new TelegramBot(TASI_TOKEN, { polling: true });
const usBot = new TelegramBot(US_TOKEN, { polling: true });

const tasiSubscribers = new Set();
const usSubscribers = new Set();

const app = express();
app.get("/", (req, res) => res.send("Bots are active and running!"));
app.listen(PORT, () => console.log(`Server running on port ${PORT}`));

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

async function fetchEodhd(url) {
  try {
    const response = await fetch(url);
    if (!response.ok) return null;
    return await response.json();
  } catch {
    return null;
  }
}

async function getStockData(symbol, exchange) {
  const ticker = `${symbol}.${exchange}`;
  const url = `https://eodhistoricaldata.com/api/eod/${ticker}?api_token=${EODHD_API_KEY}&fmt=json&period=d&limit=50`;
  const data = await fetchEodhd(url);
  
  if (!Array.isArray(data) || data.length < 20) return null;

  const closes = data.map(item => Number(item.close)).filter(Number.isFinite);
  const highs = data.map(item => Number(item.high)).filter(Number.isFinite);
  const lows = data.map(item => Number(item.low)).filter(Number.isFinite);
  const volumes = data.map(item => Number(item.volume)).filter(Number.isFinite);

  const price = closes[closes.length - 1];
  if (exchange === "US" && price < MIN_PRICE_US) return null;

  const prevClose = closes[closes.length - 2] || price;
  const changePercent = ((price - prevClose) / prevClose) * 100;

  const support = Math.min(...lows.slice(-15));
  const resistance = Math.max(...highs.slice(-15));
  const generalTrend = price >= support ? "🟢 الاتجاه العام صاعد" : "🔴 الاتجاه العام هابط";

  return {
    symbol,
    price,
    changePercent,
    support,
    resistance,
    generalTrend,
    exchange: exchange === "SR" ? "تداول (TADAWUL)" : "NASDAQ/NYSE",
    updatedAt: new Date()
  };
}

function buildMessage(stock, marketName) {
  const isBullish = stock.generalTrend.includes("صاعد");
  let bgIndicator = isBullish ? "اتجاه حسب السوق 🟢 صاعد" : "اتجاه حسب السوق 🔴 هابط";

  let msg = `📊 *${marketName} (EODHD)*\n\n`;
  msg += `📌 الرمز: *${stock.symbol}*\n`;
  msg += `💰 السعر اللحظي: *${stock.price.toFixed(2)}*\n`;
  msg += `📈 نسبة التغير: *${stock.changePercent.toFixed(2)}%*\n`;
  msg += `🏦 البورصة: ${stock.exchange}\n\n`;
  msg += `${bgIndicator}\n`;
  msg += `🧭 ${stock.generalTrend}\n`;
  msg += `🛡️ الدعم: *${stock.support.toFixed(2)}* | ⚔️ المقاومة: *${stock.resistance.toFixed(2)}*\n\n`;

  const timeString = stock.updatedAt.toLocaleTimeString("ar-SA", { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: true });
  msg += `🕒 التحديث: ${timeString}`;
  return msg;
}

// قائمة عينات نشطة وسريعة لضمان إرسال الفحص فوريًا بدون تعليق
const sampleTasi = ["1010", "1120", "1150", "2010", "2020", "2222", "1180", "1210"];
const sampleUs = ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "TSLA", "META", "SOFI"];

async function runTasiScan(chatId) {
  tasiBot.sendMessage(chatId, "🔍 بدأ فحص أسهم السوق السعودي وإرسال النتائج...");
  for (const sym of sampleTasi) {
    const stock = await getStockData(sym, "SR");
    if (stock) {
      await tasiBot.sendMessage(chatId, buildMessage(stock, "🇸🇦 السوق السعودي (تاسي)"), { parse_mode: "Markdown" });
    }
    await sleep(500);
  }
  tasiBot.sendMessage(chatId, "✅ انتهى فحص الدفعة الحالية بنجاح.");
}

async function runUsScan(chatId) {
  usBot.sendMessage(chatId, "🔍 بدأ فحص الأسهم الأمريكية وإرسال النتائج...");
  for (const sym of sampleUs) {
    const stock = await getStockData(sym, "US");
    if (stock) {
      await usBot.sendMessage(chatId, buildMessage(stock, "🇺🇸 السوق الأمريكي"), { parse_mode: "Markdown" });
    }
    await sleep(500);
  }
  usBot.sendMessage(chatId, "✅ انتهى فحص الدفعة الحالية بنجاح.");
}

tasiBot.onText(/\/start|\/scan/, msg => {
  const chatId = msg.chat.id;
  tasiSubscribers.add(chatId);
  runTasiScan(chatId);
});

usBot.onText(/\/start|\/scan/, msg => {
  const chatId = msg.chat.id;
  usSubscribers.add(chatId);
  runUsScan(chatId);
});

console.log("🟢 Optimized Bot is running without freezing!");
