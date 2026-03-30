import express from "express";
import TelegramBot from "node-telegram-bot-api";

const app = express();

// 🔑 حط التوكن هنا
const TOKEN = "PUT_YOUR_BOT_TOKEN_HERE";

const bot = new TelegramBot(TOKEN, { polling: true });

// 🤖 رد تلقائي
bot.on("message", (msg) => {
  const chatId = msg.chat.id;
  const text = msg.text;

  if (text === "/start") {
    bot.sendMessage(chatId, "🔥 هلا! البوت شغال وجاهز 🚀");
  } else {
    bot.sendMessage(chatId, "🤖 قلت: " + text);
  }
});

// 🌐 API
app.get("/", (req, res) => {
  res.send("🚀 Telegram Bot is running!");
});

const port = process.env.PORT || 3000;
app.listen(port, () => {
  console.log("Server running on port " + port);
});
