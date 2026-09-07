
const express = require("express");
const TelegramBot = require("node-telegram-bot-api");

const app = express();
app.use(express.json());

const TOKEN = process.env.TOKEN || "7772382813:AAECFDY04AXNEf-Q98_65UheUEz7u2HymJw";
const bot = new TelegramBot(TOKEN, { polling: true });

bot.on('message', (msg) => {
    const chatId = msg.chat.id;
    const text = msg.text ? msg.text.trim() : "";

    if (text === '/start') {
        bot.sendMessage(chatId, "✅ البوت يعمل بنجاح تام! أرسل /tasi للسوق السعودي أو /us للسوق الأمريكي.");
    } else if (text === '/tasi') {
        bot.sendMessage(chatId, "🇸🇦 تم استلام أمر السوق السعودي (تاسي).");
    } else if (text === '/us') {
        bot.sendMessage(chatId, "🇺🇸 تم استلام أمر السوق الأمريكي.");
    }
});

const PORT = process.env.PORT || 3000;
app.listen(PORT, () => {
    console.log(`Server running on port ${PORT}`);
});
