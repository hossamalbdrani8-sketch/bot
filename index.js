import express from "express";
import TelegramBot from "node-telegram-bot-api";

const app = express();

// 🔑 التوكن
const TOKEN = "8652994768:AAHwa1uXSRpqJmpL2X_yfYLjXIu437T-Dw4";
const bot = new TelegramBot(TOKEN, { polling: true });

let chatId = null;

// =======================
// 🎯 استقبال
// =======================
bot.on("message", (msg) => {
  chatId = msg.chat.id;

  if (msg.text?.includes("/start")) {
    bot.sendMessage(chatId, "💀 AI PRO MAX FULL MARKET ACTIVE");
  }

  if (msg.text?.includes("/scan")) {
    runAI();
  }
});

// =======================
// 📊 جلب السوق كامل
// =======================

// 🇸🇦 السوق السعودي
async function getSaudi() {
  const res = await fetch("https://www.tadawulgroup.sa/wps/portal/tadawul/market-participants/issuers-list?locale=en");
  const data = await res.json();

  return data.issuers.map(x => ({
    symbol: x.symbol + ".SR",
    name: x.nameEn
  }));
}

// 🇺🇸 السوق الأمريكي
async function getUS() {
  const res = await fetch("https://api.nasdaq.com/api/screener/stocks?tableonly=true&limit=4000");
  const data = await res.json();

  return data.data.rows.map(x => ({
    symbol: x.symbol,
    name: x.name
  }));
}

// 🪙 العملات
async function getCrypto() {
  const res = await fetch("https://api.binance.com/api/v3/ticker/price");
  const data = await res.json();

  return data.map(x => ({
    symbol: x.symbol,
    name: x.symbol
  }));
}

// =======================
// 💰 السعر الحقيقي
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
// 📊 RSI
// =======================
let history = {};

function rsiCalc(symbol, price) {

  if (!history[symbol]) history[symbol] = [];
  history[symbol].push(price);

  if (history[symbol].length > 20) history[symbol].shift();
  if (history[symbol].length < 14) return 50;

  let gain = 0, loss = 0;

  for (let i = 1; i < history[symbol].length; i++) {
    let diff = history[symbol][i] - history[symbol][i - 1];
    if (diff > 0) gain += diff;
    else loss -= diff;
  }

  let rs = gain / (loss || 1);
  return 100 - (100 / (1 + rs));
}

// =======================
// 💀 تحليل + انفجار
// =======================
function analyze(rsi) {

  if (rsi < 25) return "💀 انفجار قريب";
  if (rsi < 40) return "🟢 دخول مبكر";
  if (rsi < 60) return "⚖️ ترند";
  if (rsi < 75) return "🔥 قوة";

  return "🔴 تصريف";
}

// =======================
// 🎯 أهداف
// =======================
function targets(price) {
  return [
    price*1.02, price*1.04, price*1.06, price*1.08,
    price*1.10, price*1.12, price*1.15, price*1.20
  ];
}

// =======================
// 📩 إرسال
// =======================
function send(msg) {
  if (!chatId) return;
  bot.sendMessage(chatId, msg);
}

// =======================
// 🔥 فلترة قوية (AI)
// =======================
function strongSignal(rsi) {
  return rsi < 35 || rsi > 70;
}

// =======================
// 🔥 تحليل سهم
// =======================
async function process(asset, marketFlag) {

  const price = await getPrice(asset.symbol);
  if (!price) return;

  const rsi = rsiCalc(asset.symbol, price);

  if (!strongSignal(rsi)) return; // 💀 فلترة

  const signal = analyze(rsi);

  let msg = `${marketFlag} ${asset.name}

💰 ${price.toFixed(2)}
RSI: ${rsi.toFixed(1)}

${signal}
`;

  targets(price).forEach((t,i)=>{
    msg += `🎯 TP${i+1}: ${t.toFixed(2)}\n`;
  });

  send(msg);
}

// =======================
// 🔥 تشغيل السوق كامل
// =======================
async function runAI() {

  try {

    const saudi = await getSaudi();
    const us = await getUS();
    const crypto = await getCrypto();

    for (let s of saudi) await process(s, "🇸🇦");
    for (let s of us) await process(s, "🇺🇸");
    for (let c of crypto) await process(c, "🪙");

  } catch (e) {
    console.log("ERROR:", e.message);
  }
}

// ⏱️ كل 5 دقائق (أفضل)
setInterval(runAI, 300000);

// =======================
app.get("/", (req, res) => {
  res.send("💀 AI PRO MAX FULL MARKET RUNNING");
});

app.listen(3000);
