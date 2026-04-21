import express from "express";
import TelegramBot from "node-telegram-bot-api";
import fetch from "node-fetch"; // ✅ مهم

const app = express();
app.use(express.json());

// 🔑 TOKEN
const TOKEN = "PUT_YOUR_TOKEN_HERE";

// 🔑 API
const API_KEY = "PUT_YOUR_API_KEY_HERE";

// 💀 اتصال ثابت
const bot = new TelegramBot(TOKEN, {
  polling: true
});

let chatIds = new Set();
let running = false;
let lastData = {};

// =======================
async function getQuote(symbol) {
  try {
    const res = await fetch(`https://finnhub.io/api/v1/quote?symbol=${symbol}&token=${API_KEY}`);
    const data = await res.json();

    if (!data?.c || !data?.pc) return null;

    lastData[symbol] = { price: data.c, prev: data.pc };
    return lastData[symbol];

  } catch {
    return null;
  }
}

// =======================
async function getUSSymbols() {
  try {
    const res = await fetch(`https://finnhub.io/api/v1/stock/symbol?exchange=US&token=${API_KEY}`);
    return await res.json();
  } catch { return []; }
}

// =======================
function analyze(price, prev) {
  let change = ((price - prev) / prev) * 100;

  let signal = "⚪";
  if (change > 3) signal = "🚀 قوي";
  else if (change > 1) signal = "🔥 صعود";
  else if (change < -3) signal = "🚨 هبوط";

  let tp = [
    price*1.02, price*1.04, price*1.06, price*1.08,
    price*1.10, price*1.12, price*1.15, price*1.18
  ];

  return { change, signal, tp };
}

// =======================
function format(s) {
  return `
${s.name}

💰 ${s.price.toFixed(2)}
📊 ${s.signal}

🎯 ${s.tp[0].toFixed(2)}
🎯 ${s.tp[1].toFixed(2)}
🎯 ${s.tp[2].toFixed(2)}
🎯 ${s.tp[3].toFixed(2)}
🎯 ${s.tp[4].toFixed(2)}
🎯 ${s.tp[5].toFixed(2)}
🎯 ${s.tp[6].toFixed(2)}
🎯 ${s.tp[7].toFixed(2)}

━━━━━━━━━━━━`;
}

// =======================
bot.on("message", (msg) => {
  chatIds.add(msg.chat.id);

  if (msg.text === "/start") {
    bot.sendMessage(msg.chat.id, "💀 RUNNING 24/7");
  }

  if (msg.text === "/scan") {
    run();
  }
});

// =======================
// 💀 الحل الحقيقي هنا
async function run() {
  if (running) return;
  running = true;

  try {
    let us = await getUSSymbols();

    // 🔥 خفف الضغط (بدل السوق كامل دفعة وحدة)
    let batchSize = 10;

    for (let i = 0; i < us.length; i += batchSize) {

      let batch = us.slice(i, i + batchSize);

      for (let s of batch) {
        let q = await getQuote(s.symbol);
        if (!q) continue;

        let a = analyze(q.price, q.prev);
        if (!a) continue;

        // 🔥 فلترة خفيفة (بدونها راح ينفجر البوت)
        if (a.change < 1) continue;

        let text = format({
          name: s.symbol,
          price: q.price,
          ...a
        });

        for (let id of chatIds) {
          try {
            await bot.sendMessage(id, text);
            await new Promise(r => setTimeout(r, 200)); // 🚫 منع حظر تيليجرام
          } catch {}
        }
      }

      await new Promise(r => setTimeout(r, 2000)); // 🚫 منع حظر API
    }

  } catch (e) {
    console.log("ERROR:", e.message);
  }

  running = false;
}

// =======================
// 💀 تشغيل دائم فعلي
setInterval(() => {
  run();
}, 15000); // كل 15 ثانية

app.listen(3000, () => {
  console.log("💀 BOT RUNNING STABLE");
});
