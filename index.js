import express from "express";
import TelegramBot from "node-telegram-bot-api";

const app = express();
app.use(express.json());

// 🔑 التوكن
const TOKEN = "8652994768:AAHwa1uXSRpqJmpL2X_yfYLjXIu437T-Dw4";
const bot = new TelegramBot(TOKEN);

// 🎯 تخزين الشات
global.chatId = null;

// =======================
// 📩 استقبال تيليجرام (Webhook)
// =======================
app.post("/webhook", (req, res) => {
  bot.processUpdate(req.body);
  res.sendStatus(200);
});

// =======================
// 🎯 أوامر البوت
// =======================
bot.on("message", (msg) => {
  global.chatId = msg.chat.id;

  if (msg.text?.includes("/start")) {
    bot.sendMessage(global.chatId, "💀 AUTO AI PRO MAX ACTIVATED");
  }
});

// =======================
// 🔥 جلب السوق (LIVE)
// =======================
async function fetchMarket() {
  try {
    const btc = await fetch("https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT")
      .then(res => res.json());

    const eth = await fetch("https://api.binance.com/api/v3/ticker/price?symbol=ETHUSDT")
      .then(res => res.json());

    const fx = await fetch("https://open.er-api.com/v6/latest/USD")
      .then(res => res.json());

    return {
      btc: btc.price,
      eth: eth.price,
      eurusd: (1 / fx.rates.EUR).toFixed(4)
    };

  } catch (err) {
    console.log("FETCH ERROR:", err);
    return null;
  }
}

// =======================
// 🧠 تحليل ذكي
// =======================
function analyze(price) {
  const p = parseFloat(price);

  if (p > 60000) return "🟢 BUY";
  if (p < 30000) return "🔴 SELL";
  return "⚪ HOLD";
}

// =======================
// 🚀 تشغيل تلقائي 24/7
// =======================
async function autoScan() {
  if (!global.chatId) return;

  const data = await fetchMarket();
  if (!data) return;

  const btcSignal = analyze(data.btc);
  const ethSignal = analyze(data.eth);

  const message = `
💀 AI PRO MAX LIVE

🇸🇦 السوق السعودي
TASI: LIVE

🇺🇸 السوق الأمريكي
NASDAQ: LIVE

💱 العملات
EUR/USD: ${data.eurusd}

🪙 Crypto
BTC: ${data.btc} → ${btcSignal}
ETH: ${data.eth} → ${ethSignal}

⚡ تحديث تلقائي كل دقيقة
`;

  bot.sendMessage(global.chatId, message);
}

// ⏱️ كل 60 ثانية
setInterval(autoScan, 60000);

// =======================
// 🌐 السيرفر
// =======================
app.get("/", (req, res) => {
  res.send("💀 AI PRO MAX RUNNING");
});

const PORT = process.env.PORT || 3000;

app.listen(PORT, () => {
  console.log("🚀 Server running on " + PORT);
});
