import express from "express";
import TelegramBot from "node-telegram-bot-api";

const app = express();
app.use(express.json());

// 🔑 التوكن
const TOKEN = "8652994768:AAHwa1uXSRpqJmpL2X_yfYLjXIu437T-Dw4";

// تشغيل البوت بدون polling
const bot = new TelegramBot(TOKEN);

// =======================
// 🎯 Webhook endpoint
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

  if (msg.text?.includes("/start")) {
    bot.sendMessage(chatId, "💀 AI PRO MAX CONNECTED");
  }

  if (msg.text?.includes("/scan")) {
    bot.sendMessage(chatId, "🚀 جاري الفحص...");
  }
});

// =======================
// 🌐 السيرفر
// =======================
const PORT = process.env.PORT || 8080;

app.get("/", (req, res) => {
  res.send("Bot is running 💀");
});

app.listen(PORT, () => {
  console.log("🚀 Server running on " + PORT);
});
