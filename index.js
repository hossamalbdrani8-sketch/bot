
"use strict";

const express = require("express");
const TelegramBot = require("node-telegram-bot-api");

// ======================================================
// 🤖 AI PRO MAX — اختبار تشغيل فقط
// لا يوجد EODHD
// لا يوجد فحص أسهم
// ======================================================

const TOKEN =
  process.env.TELEGRAM_TOKEN ||
  process.env.TELEGRAM_BOT_TOKEN ||
  process.env.BOT_TOKEN;

const PORT = process.env.PORT || 8080;

if (!TOKEN) {
  console.error("❌ لم يتم العثور على TELEGRAM_TOKEN");
  process.exit(1);
}

// ======================================================
// 🌐 خادم Railway
// ======================================================

const app = express();

app.get("/", (req, res) => {
  res.send("AI PRO MAX يعمل بنجاح 🚀");
});

app.get("/health", (req, res) => {
  res.json({
    status: "ok",
    bot: "AI PRO MAX",
    telegram: true
  });
});

app.listen(PORT, "0.0.0.0", () => {
  console.log(`🌐 الخادم يعمل على المنفذ ${PORT}`);
});

// ======================================================
// 🤖 Telegram
// ======================================================

const bot = new TelegramBot(TOKEN, {
  polling: true
});

console.log("🤖 AI PRO MAX بدأ التشغيل");
console.log("📡 Telegram polling: ON");

// ======================================================
// /start
// ======================================================

bot.onText(/^\/start$/, async (msg) => {
  const chatId = msg.chat.id;

  console.log(`📩 تم استقبال /start من Chat ID: ${chatId}`);

  await bot.sendMessage(
    chatId,
    `🚀 *AI PRO MAX*

✅ البوت يعمل بنجاح

🤖 Telegram: متصل
🟢 النظام: يعمل
📡 الاتصال: مستقر

هذه نسخة اختبار فقط.
لم يتم تشغيل فحص الأسهم أو EODHD بعد.

⏳ المرحلة التالية:
إضافة محرك الفحص تلقائيًا.`,
    {
      parse_mode: "Markdown"
    }
  );
});

// ======================================================
// أي رسالة أخرى
// ======================================================

bot.on("message", (msg) => {
  if (msg.text === "/start") return;

  console.log(`📩 رسالة من Telegram: ${msg.text || "بدون نص"}`);

  bot.sendMessage(
    msg.chat.id,
    "✅ البوت يستقبل رسالتك.\n\nاستخدم /start للاختبار."
  ).catch((err) => {
    console.error("❌ خطأ Telegram:", err.message);
  });
});

// ======================================================
// أخطاء Telegram
// ======================================================

bot.on("polling_error", (err) => {
  console.error("❌ Telegram Polling:", err.message);
});

process.on("uncaughtException", (err) => {
  console.error("❌ خطأ:", err);
});

process.on("unhandledRejection", (err) => {
  console.error("❌ خطأ:", err);
});