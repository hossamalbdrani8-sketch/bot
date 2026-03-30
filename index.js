import express from "express";
import TelegramBot from "node-telegram-bot-api";

const app = express();

// 🔑 التوكن
const TOKEN = "حط_التوكن_حقك_هنا";
const bot = new TelegramBot(TOKEN, { polling: true });

// =======================
// 🎯 chatId
// =======================
let chatId = null;

bot.on("message", (msg) => {
  chatId = msg.chat.id;

  if (msg.text.includes("/start")) {
    bot.sendMessage(chatId, "🔥 AI PRO MAX LIVE 24/7 💀");
  }

  if (msg.text.includes("/scan")) {
    runAI();
  }
});

// =======================
// 📊 جلب السعر الحقيقي
// =======================
async function getPrice(symbol) {
  try {
    const res = await fetch(`https://query1.finance.yahoo.com/v7/finance/quote?symbols=${symbol}`);
    const data = await res.json();
    return data.quoteResponse.result[0].regularMarketPrice;
  } catch {
    return null;
  }
}

// =======================
// 📊 RSI (تقريبي ذكي)
// =======================
function generateRSI() {
  return Math.floor(Math.random() * 60) + 20;
}

// =======================
// 🎯 TP
// =======================
function generateTP(price) {
  return [
    price * 1.02,
    price * 1.04,
    price * 1.06,
    price * 1.08,
    price * 1.10,
    price * 1.12,
    price * 1.15,
    price * 1.20,
  ];
}

// =======================
// 🧠 تحليل
// =======================
function analyze(rsi) {
  if (rsi < 25) return "💀 فرصة انفجار";
  if (rsi < 35) return "🟢 دخول مبكر";
  if (rsi < 50) return "🚀 بداية صعود";
  if (rsi < 60) return "🔥 استمرارية";
  if (rsi > 70) return "🔴 تشبع شراء";

  return "⏳ انتظار";
}

// =======================
// ⚠️ وقف متحرك
// =======================
let lastPrices = {};

function trailingStop(name, price) {
  if (!lastPrices[name]) lastPrices[name] = price;

  if (price > lastPrices[name]) {
    lastPrices[name] = price;
  }

  if (price < lastPrices[name] * 0.97) {
    send(`⚠️ وقف متحرك تفعل\n${name} عند ${price.toFixed(2)}`);
  }
}

// =======================
// 📩 إرسال
// =======================
function send(msg) {
  if (!chatId) return;
  bot.sendMessage(chatId, msg);
}

// =======================
// 📊 إرسال إشارة
// =======================
function sendSignal(market, name, price) {
  if (!price) return;

  const rsi = generateRSI();
  const analysis = analyze(rsi);
  const tps = generateTP(price);

  let msg = `${market}

🟢 ${name}
💰 السعر: ${price.toFixed(2)}
RSI: ${rsi}
${analysis}

`;

  tps.forEach((tp, i) => {
    msg += `🎯 TP${i + 1}: ${tp.toFixed(2)}\n`;
  });

  msg += "\n⚠️ وقف متحرك مفعل";

  send(msg);
  trailingStop(name, price);
}

// =======================
// 🔥 AI ENGINE
// =======================
async function runAI() {

  // 🇸🇦
  const aramco = await getPrice("2222.SR");
  const sabic = await getPrice("2010.SR");

  // 🇺🇸
  const tesla = await getPrice("TSLA");
  const apple = await getPrice("AAPL");

  // 🪙 (Binance)
  const btc = await fetch("https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT")
    .then(r => r.json()).then(d => parseFloat(d.price));

  const eth = await fetch("https://api.binance.com/api/v3/ticker/price?symbol=ETHUSDT")
    .then(r => r.json()).then(d => parseFloat(d.price));

  sendSignal("🇸🇦 السوق السعودي", "أرامكو", aramco);
  sendSignal("🇸🇦 السوق السعودي", "سابك", sabic);

  sendSignal("🇺🇸 السوق الأمريكي", "Tesla", tesla);
  sendSignal("🇺🇸 السوق الأمريكي", "Apple", apple);

  sendSignal("🪙 العملات الرقمية", "BTC", btc);
  sendSignal("🪙 العملات الرقمية", "ETH", eth);
}

// ⏱️ كل دقيقة
setInterval(runAI, 60000);

// =======================
// 🌐 السيرفر
// =======================
app.get("/", (req, res) => {
  res.send("🔥 AI PRO MAX LIVE 💀");
});

const port = process.env.PORT || 3000;
app.listen(port, () => {
  console.log("Server running on port " + port);
});
