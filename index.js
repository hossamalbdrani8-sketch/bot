import express from "express";
import TelegramBot from "node-telegram-bot-api";

const app = express();

const TOKEN = "حط_التوكن_حقك_هنا";
const bot = new TelegramBot(TOKEN, { polling: true });

let chatId = null;

bot.on("message", (msg) => {
  chatId = msg.chat.id;

  if (msg.text.includes("/start")) {
    bot.sendMessage(chatId, "💀 FULL REAL MARKET ACTIVE");
  }

  if (msg.text.includes("/scan")) {
    runAI();
  }
});

// =======================
// 📊 جلب السوق السعودي كامل
// =======================
async function getSaudi() {
  const res = await fetch("https://www.tadawulgroup.sa/wps/portal/tadawul/market-participants/issuers-list?locale=en");
  const data = await res.json();
  return data.issuers.map(x => x.symbol);
}

// =======================
// 📊 السوق الأمريكي (Nasdaq + NYSE)
// =======================
async function getUS() {
  const res = await fetch("https://api.nasdaq.com/api/screener/stocks?tableonly=true&limit=4000");
  const data = await res.json();
  return data.data.rows.map(x => x.symbol);
}

// =======================
// 🪙 العملات كاملة
// =======================
async function getCrypto() {
  const res = await fetch("https://api.binance.com/api/v3/ticker/price");
  const data = await res.json();
  return data.map(x => x.symbol);
}

// =======================
// 💰 السعر
// =======================
async function getPrice(symbol) {
  try {
    const res = await fetch(`https://query1.finance.yahoo.com/v7/finance/quote?symbols=${symbol}`);
    const data = await res.json();
    return data.quoteResponse.result[0]?.regularMarketPrice;
  } catch {
    return null;
  }
}

// =======================
// 📊 تحليل بسيط
// =======================
function analyze(price) {
  if (!price) return "⏳";
  return price % 2 === 0 ? "🟢 فرصة" : "🔴 حذر";
}

// =======================
// 📩 إرسال
// =======================
function send(msg) {
  if (!chatId) return;
  bot.sendMessage(chatId, msg);
}

// =======================
// 🔥 تشغيل كامل السوق
// =======================
async function runAI() {

  const saudi = await getSaudi();
  const us = await getUS();
  const crypto = await getCrypto();

  for (const s of saudi) {
    const price = await getPrice(s + ".SR");
    send(`🇸🇦 ${s} - ${price}`);
  }

  for (const s of us) {
    const price = await getPrice(s);
    send(`🇺🇸 ${s} - ${price}`);
  }

  for (const c of crypto) {
    send(`🪙 ${c}`);
  }
}

// =======================
setInterval(runAI, 600000);

app.get("/", (req, res) => {
  res.send("💀 REAL MARKET RUNNING");
});

app.listen(3000);
