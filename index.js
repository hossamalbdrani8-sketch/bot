import express from "express";
import TelegramBot from "node-telegram-bot-api";

const app = express();
app.use(express.json());

// 🔑 TOKEN
const TOKEN = "8652994768:AAHwa1uXSRpqJmpL2X_yfYLjXIu437T-Dw4";

// 💀 اتصال قوي ثابت
const bot = new TelegramBot(TOKEN, {
  polling: {
    interval: 300,
    autoStart: true,
    params: { timeout: 10 }
  }
});

// 🔑 API
const API_KEY = "d7a0311r01qspme6c44gd7a0311r01qspme6c450";

let chatId = null;
let memory = {};
let running = false;

// 💀 حماية من الكراش
process.on("uncaughtException", (err) => console.log("CRASH:", err.message));
process.on("unhandledRejection", (err) => console.log("PROMISE:", err));

// =======================
bot.on("message", (msg) => {
  chatId = msg.chat.id;

  if (msg.text === "/start") {
    bot.sendMessage(chatId, "💀 AI PRO MAX ELITE MODE");
    run();
  }

  if (msg.text === "/scan") {
    bot.sendMessage(chatId, "🚀 فحص السوق...");
    run();
  }
});

// =======================
function analyze(price, prev, symbol) {
  if (!price || !prev) return null;

  let change = ((price - prev) / prev) * 100;

  return {
    change,
    price,
    symbol
  };
}

// =======================
async function getQuote(symbol) {
  try {
    const res = await fetch(`https://finnhub.io/api/v1/quote?symbol=${symbol}&token=${API_KEY}`);
    const data = await res.json();

    if (!data || !data.c) return null;

    return { price: data.c, prev: data.pc };
  } catch (e) {
    return null;
  }
}

// =======================
async function run() {
  if (!chatId || running) return;
  running = true;

  try {
    let symbols = ["AAPL", "TSLA", "NVDA"]; // 💀 ثابت للتجربة

    let sent = 0;

    for (let s of symbols) {
      let q = await getQuote(s);

      if (!q) {
        await bot.sendMessage(chatId, `⚠️ ${s} API ما رجع بيانات`);
        continue;
      }

      let a = analyze(q.price, q.prev, s);
      if (!a) continue;

      await bot.sendMessage(chatId,
        `💰 ${s}\nالسعر: ${a.price}\nالتغير: ${a.change.toFixed(2)}%`
      );

      sent++;
    }

    if (sent === 0) {
      await bot.sendMessage(chatId, "❌ مافي بيانات من API");
    }

  } catch (e) {
    await bot.sendMessage(chatId, "💀 خطأ بالنظام");
  }

  running = false;
}

// 💀 تشغيل دائم
setInterval(run, 60000);

app.listen(3000, () => {
  console.log("🔥 RUNNING 24/7");
});
