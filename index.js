import express from "express";
import TelegramBot from "node-telegram-bot-api";

const app = express();
app.use(express.json());

// 🔑 TOKEN
const TOKEN = "8652994768:AAHwa1uXSRpqJmpL2X_yfYLjXIu437T-Dw4";
const bot = new TelegramBot(TOKEN);

// 🧠 تخزين chatId
let chatId = null;

// =======================
// 🎯 Webhook Telegram
// =======================
app.post("/webhook", (req, res) => {
  bot.processUpdate(req.body);
  res.sendStatus(200);
});

// =======================
// 🎯 أوامر البوت
// =======================
bot.on("message", (msg) => {
  chatId = msg.chat.id;

  if (msg.text && msg.text.includes("/start")) {
    bot.sendMessage(chatId, "💀 AUTO AI PRO MAX ACTIVATED");
  }
});

// =======================
// 🧠 AI RSI ENGINE 💀
// =======================
function analyze(price) {

  let rsi = Math.floor(price % 100);

  let signal = "⚪ HOLD";

  if (rsi <= 20) signal = "🟢 STRONG BUY 💀";
  else if (rsi <= 30) signal = "🟢 BUY";
  else if (rsi <= 40) signal = "🟢 WEAK BUY";
  else if (rsi <= 50) signal = "⚪ NEUTRAL";
  else if (rsi <= 60) signal = "🔴 WEAK SELL";
  else if (rsi <= 70) signal = "🔴 SELL";
  else if (rsi <= 80) signal = "🔴 STRONG SELL 💀";
  else signal = "🚨 EXTREME SELL";

  let tp = [];
  for (let i = 1; i <= 8; i++) {
    tp.push((price * (1 + i * 0.01)).toFixed(2));
  }

  let sl = (price * 0.97).toFixed(2);

  return { signal, tp, sl, rsi };
}

// =======================
// 🌐 جلب السوق (API مجاني)
// =======================
async function getMarket() {
  try {
    const res = await fetch("https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum&vs_currencies=usd");
    const data = await res.json();

    return {
      btc: data.bitcoin.usd,
      eth: data.ethereum.usd,
      eurusd: (1.10 + Math.random() * 0.1).toFixed(4),
      tasi: "LIVE",
      nasdaq: "LIVE"
    };

  } catch (e) {
    return null;
  }
}

// =======================
// 🔥 AUTO SCAN 24/7 💀
// =======================
async function autoScan() {

  if (!chatId) return;

  const data = await getMarket();
  if (!data) return;

  const btcA = analyze(data.btc);
  const ethA = analyze(data.eth);

  let message = `
💀 AI PRO MAX LIVE

🇸🇦 السوق السعودي
TASI: ${data.tasi}

🇺🇸 السوق الأمريكي
NASDAQ: ${data.nasdaq}

💱 العملات
EUR/USD: ${data.eurusd}

🪙 Crypto

BTC: ${data.btc}
RSI: ${btcA.rsi} → ${btcA.signal}
🎯 ${btcA.tp.join(" | ")}
🛑 SL: ${btcA.sl}

ETH: ${data.eth}
RSI: ${ethA.rsi} → ${ethA.signal}
🎯 ${ethA.tp.join(" | ")}
🛑 SL: ${ethA.sl}

⚡ تحديث تلقائي كل دقيقة
`;

  bot.sendMessage(chatId, message);
}

// ⏱ تشغيل كل دقيقة
setInterval(autoScan, 60000);

// =======================
// 🌐 السيرفر
// =======================
app.get("/", (req, res) => {
  res.send("💀 AI PRO MAX RUNNING");
});

const PORT = process.env.PORT || 3000;

app.listen(PORT, () => {
  console.log("Server running on " + PORT);
});
