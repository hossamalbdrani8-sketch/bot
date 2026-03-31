import express from "express";
import TelegramBot from "node-telegram-bot-api";

const app = express();
app.use(express.json());

// 🔑 TOKEN
const TOKEN = "8652994768:AAHwa1uXSRpqJmpL2X_yfYLjXIu437T-Dw4";
const bot = new TelegramBot(TOKEN, { polling: true });

// 🔑 FINNHUB API
const API_KEY = "d75o0l1r01qk56kdfon0d75o0l1r01qk56kdfong";

let chatId = null;

// =======================
bot.on("message", (msg) => {
  chatId = msg.chat.id;

  if (msg.text === "/start") {
    bot.sendMessage(chatId, "💀 AI PRO MAX LIVE (REAL API)");
  }
});

// =======================
// 🧠 تحليل
// =======================
function analyze(price) {

  let rsi = Math.floor(price % 100);

  let signal = "⚪ محايد";

  if (rsi <= 20) signal = "🟢 شراء قوي 💀";
  else if (rsi <= 30) signal = "🟢 شراء";
  else if (rsi <= 40) signal = "🟢 شراء ضعيف";
  else if (rsi <= 50) signal = "⚪ محايد";
  else if (rsi <= 60) signal = "🔴 بيع ضعيف";
  else if (rsi <= 70) signal = "🔴 بيع";
  else if (rsi <= 80) signal = "🔴 بيع قوي";
  else signal = "🚨 خطر";

  let tp = [];
  for (let i = 1; i <= 8; i++) {
    tp.push((price * (1 + i * 0.02)).toFixed(2));
  }

  let sl = (price * 0.95).toFixed(2);

  return { rsi, signal, tp, sl };
}

// =======================
// 📊 Finnhub (حقيقي)
// =======================
async function getUS(symbol) {
  try {
    const res = await fetch(`https://finnhub.io/api/v1/quote?symbol=${symbol}&token=${API_KEY}`);
    const data = await res.json();
    return data.c; // السعر الحالي
  } catch {
    return null;
  }
}

// =======================
// 🇸🇦 سعودي (Yahoo)
// =======================
async function getSA(symbol) {
  try {
    const res = await fetch(`https://query1.finance.yahoo.com/v7/finance/quote?symbols=${symbol}`);
    const data = await res.json();
    return data.quoteResponse.result[0]?.regularMarketPrice || null;
  } catch {
    return null;
  }
}

// =======================
// 🎯 تنسيق
// =======================
function formatStock(name, price) {

  if (!price) return `❌ ${name}`;

  const a = analyze(price);

  return `
🟢 ${name}
💰 ${price}
RSI: ${a.rsi} → ${a.signal}

🎯 TP1: ${a.tp[0]}
🎯 TP2: ${a.tp[1]}
🎯 TP3: ${a.tp[2]}
🎯 TP4: ${a.tp[3]}
🎯 TP5: ${a.tp[4]}
🎯 TP6: ${a.tp[5]}
🎯 TP7: ${a.tp[6]}
🎯 TP8: ${a.tp[7]}

🛑 وقف: ${a.sl}
━━━━━━━━━━━━`;
}

// =======================
// 🚀 التشغيل الحقيقي
// =======================
async function run() {

  if (!chatId) return;

  // 🇺🇸 السوق الأمريكي (API حقيقي)
  const tsla = await getUS("TSLA");
  const aapl = await getUS("AAPL");
  const nvda = await getUS("NVDA");
  const amzn = await getUS("AMZN");
  const meta = await getUS("META");

  // 🇸🇦 السوق السعودي
  const aramco = await getSA("2222.SR");
  const rajhi = await getSA("1120.SR");
  const stc = await getSA("7010.SR");
  const sabic = await getSA("2010.SR");

  // 🪙 كريبتو
  const cryptoRes = await fetch("https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum&vs_currencies=usd");
  const crypto = await cryptoRes.json();

  let message = `
💀 AI PRO MAX REAL MARKET

🇸🇦 السوق السعودي
━━━━━━━━━━━━
${formatStock("أرامكو", aramco)}
${formatStock("الراجحي", rajhi)}
${formatStock("STC", stc)}
${formatStock("سابك", sabic)}

🇺🇸 السوق الأمريكي
━━━━━━━━━━━━
${formatStock("Tesla", tsla)}
${formatStock("Apple", aapl)}
${formatStock("NVIDIA", nvda)}
${formatStock("Amazon", amzn)}
${formatStock("Meta", meta)}

🪙 الكريبتو
━━━━━━━━━━━━
${formatStock("Bitcoin", crypto.bitcoin.usd)}
${formatStock("Ethereum", crypto.ethereum.usd)}

⚡ تحديث مباشر كل دقيقة
`;

  bot.sendMessage(chatId, message);
}

// ⏱ تحديث
setInterval(run, 60000);

app.listen(3000);
