import express from "express";
import TelegramBot from "node-telegram-bot-api";

const app = express();
app.use(express.json());

// 🔑 التوكن
const TOKEN = "8652994768:AAHwa1uXSRpqJmpL2X_yfYLjXIu437T-Dw4";

// ❌ بدون polling
const bot = new TelegramBot(TOKEN);

// =======================
// 🎯 استقبال (Webhook)
// =======================
app.post("/webhook", (req, res) => {
  bot.processUpdate(req.body);
  res.sendStatus(200);
});

// =======================
// 🎯 أوامر البوت
// =======================
bot.on("message", (msg) => {
  const chatId = msg.chat.id;

  if (msg.text && msg.text.includes("/start")) {
    bot.sendMessage(chatId, "💀 AI PRO MAX CONNECTED");
  }

  if (msg.text && msg.text.includes("/scan")) {
    bot.sendMessage(chatId, "🚀 جاري الفحص...");
  }
});

// =======================
// 🌐 السيرفر
// =======================
const port = process.env.PORT || 3000;
app.listen(port, () => {
  console.log("🚀 Server running on " + port);
});
