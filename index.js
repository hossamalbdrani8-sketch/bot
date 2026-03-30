import express from "express";
import TelegramBot from "node-telegram-bot-api";

const app = express();

const TOKEN = "8652994768:AAHwa1uXSRpqJmpL2X_yfYLjXIu437T-Dw4";

const bot = new TelegramBot(TOKEN, { polling: true });

bot.on("message", (msg) => {
  const chatId = msg.chat.id;
  const text = msg.text;

  if (text === "/start") {
    bot.sendMessage(chatId, "🔥 البوت شغال وجاهز");
  } else {
    bot.sendMessage(chatId, "🤖 قلت: " + text);
  }
});

app.get("/", (req, res) => {
  res.send("🚀 Bot is running!");
});

const port = process.env.PORT || 3000;
app.listen(port, () => {
  console.log("Server running on port " + port);
});

