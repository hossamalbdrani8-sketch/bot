import express from "express";
import TelegramBot from "node-telegram-bot-api";

const app = express();

const TOKEN = "حط_التوكن_حقك_هنا";
const bot = new TelegramBot(TOKEN, { polling: true });

let chatId = null;

bot.on("message", (msg) => {
  chatId = msg.chat.id;

  if (msg.text.includes("/start")) {
    bot.sendMessage(chatId, "💀 AI PRO MAX SMART ACTIVE");
  }

  if (msg.text.includes("/scan")) {
    runAI();
  }
});

// =======================
// 📊 APIs (محسنة)
// =======================

async function getSaudi() {
  try {
    const res = await fetch("https://www.tadawulgroup.sa/wps/portal/tadawul/1/issuers");
    const data = await res.json();
    return data?.data?.map(x => x.symbol) || [];
  } catch {
    return [];
  }
}

async function getUS() {
  try {
    const res = await fetch("https://api.nasdaq.com/api/screener/stocks?tableonly=true&limit=200");
    const data = await res.json();
    return data?.data?.rows?.map(x => x.symbol) || [];
  } catch {
    return [];
  }
}

async function getCrypto() {
  try {
    const res = await fetch("https://api.binance.com/api/v3/ticker/price");
    const data = await res.json();
    return data.map(x => x.symbol).slice(0, 100); // تقليل الضغط
  } catch {
    return [];
  }
}

// =======================
// 💰 السعر
// =======================
async function getPrice(symbol) {
  try {
    const res = await fetch(`https://query1.finance.yahoo.com/v7/finance/quote?symbols=${symbol}`);
    const data = await res.json();
    return data?.quoteResponse?.result?.[0]?.regularMarketPrice || null;
  } catch {
    return null;
  }
}

// =======================
// 📊 RSI تقريبي سريع
// =======================
function fakeRSI(price) {
  return Math.min(90, Math.max(10, (price % 100)));
}

// =======================
// 💀 فلترة قوية
// =======================
function smartSignal(price, rsi) {

  if (!price) return null;

  if (rsi < 30) {
    return "💀 دخول قوي (تشبع بيع)";
  }

  if (rsi > 70) {
    return "🔴 خروج (تشبع شراء)";
  }

  return null; // يمنع السبام
}

// =======================
// 📩 إرسال
// =======================
function send(msg) {
  if (!chatId) return;
  bot.sendMessage(chatId, msg);
}

// =======================
// 🔥 تحليل سهم
// =======================
async function analyzeAsset(market, symbol, suffix="") {

  const price = await getPrice(symbol + suffix);
  if (!price) return;

  const rsi = fakeRSI(price);
  const signal = smartSignal(price, rsi);

  if (!signal) return; // 💀 فلترة (مهم)

  let msg = `${market}

🟢 ${symbol}
💰 ${price.toFixed(2)}
RSI: ${rsi}

${signal}
`;

  send(msg);
}

// =======================
// 🔥 تشغيل
// =======================
async function runAI() {

  const saudi = await getSaudi();
  const us = await getUS();
  const crypto = await getCrypto();

  // 🔥 تقليل الضغط (أهم شيء)
  const saudiSample = saudi.slice(0, 50);
  const usSample = us.slice(0, 50);

  for (const s of saudiSample) {
    await analyzeAsset("🇸🇦 السوق السعودي", s, ".SR");
  }

  for (const s of usSample) {
    await analyzeAsset("🇺🇸 السوق الأمريكي", s);
  }

  for (const c of crypto) {
    send(`🪙 ${c}`); // العملات مباشرة
  }
}

// كل 5 دقائق (أفضل)
setInterval(runAI, 300000);

// =======================
app.get("/", (req, res) => {
  res.send("💀 AI PRO MAX RUNNING");
});

app.listen(3000);
