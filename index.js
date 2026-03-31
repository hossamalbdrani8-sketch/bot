import express from "express";
import TelegramBot from "node-telegram-bot-api";

const app = express();
app.use(express.json());

// 🔑 التوكن (خلاص حطيته لك)
const TOKEN = "8652994768:AAHwa1uXSRpqJmpL2X_yfYLjXIu437T-Dw4";
const bot = new TelegramBot(TOKEN, { polling: true });

// 🎯 chatId
let chatId = null;

// =======================
// 📩 استقبال من تيليجرام
// =======================
bot.on("message", (msg) => {
  chatId = msg.chat.id;

  if (msg.text && msg.text.includes("/start")) {
    bot.sendMessage(chatId, "💀 AI PRO MAX CONNECTED");
  }
});

// =======================
// 🔥 استقبال من TradingView
// =======================
app.post("/webhook", (req, res) => {
  const data = req.body;

  if (!chatId) {
    return res.send("No chatId yet");
  }

  let message = `
🚨 AI PRO MAX SIGNAL

📊 ${data.symbol}
💰 السعر: ${data.price}
RSI: ${data.rsi}

${data.signal}

🎯 TP1: ${data.tp1}
🎯 TP2: ${data.tp2}
🎯 TP3: ${data.tp3}
🎯 TP4: ${data.tp4}
🎯 TP5: ${data.tp5}
🎯 TP6: ${data.tp6}
🎯 TP7: ${data.tp7}
🎯 TP8: ${data.tp8}
`;

  bot.sendMessage(chatId, message);

  res.send("OK");
});

// =======================
// 🌐 سيرفر
// =======================
app.get("/", (req, res) => {
  res.send("💀 AI PRO MAX RUNNING");
});

const PORT = process.env.PORT || 3000;

app.listen(PORT, () => {
  console.log("Server running on port " + PORT);
});
