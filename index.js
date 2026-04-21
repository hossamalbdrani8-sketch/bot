import express from "express";
import TelegramBot from "node-telegram-bot-api";
import fetch from "node-fetch"; // ✅ حل المشكلة

const app = express();
app.use(express.json());

// 🔑 TOKEN
const TOKEN = "PUT_TOKEN_HERE";

// 🔑 API
const API_KEY = "PUT_API_KEY_HERE";

// 💀 اتصال
const bot = new TelegramBot(TOKEN, { polling: true });

let chatIds = new Set();
let running = false;
let lastData = {};
let sentSignals = {}; // ✅ لتحديث الأهداف

// =======================
async function getQuote(symbol) {
  try {
    const res = await fetch(`https://finnhub.io/api/v1/quote?symbol=${symbol}&token=${API_KEY}`);

    if (res.status === 429) return null;

    const data = await res.json();

    if (!data?.c || !data?.pc) return null;

    lastData[symbol] = { price: data.c, prev: data.pc };
    return lastData[symbol];

  } catch {
    return null;
  }
}

// =======================
function analyze(price, prev) {
  let change = ((price - prev) / prev) * 100;

  let signal = "⚪";
  if (change > 3) signal = "💀🚀 انفجار";
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

  function check(tp) {
    return s.price >= tp ? "✅" : "";
  }

  return `
${s.market}

${s.name}

💰 ${s.price.toFixed(2)}

📊 ${s.signal}

🎯 ${s.tp[0].toFixed(2)} ${check(s.tp[0])}
🎯 ${s.tp[1].toFixed(2)} ${check(s.tp[1])}
🎯 ${s.tp[2].toFixed(2)} ${check(s.tp[2])}
🎯 ${s.tp[3].toFixed(2)} ${check(s.tp[3])}
🎯 ${s.tp[4].toFixed(2)} ${check(s.tp[4])}
🎯 ${s.tp[5].toFixed(2)} ${check(s.tp[5])}
🎯 ${s.tp[6].toFixed(2)} ${check(s.tp[6])}
🎯 ${s.tp[7].toFixed(2)} ${check(s.tp[7])}

━━━━━━━━━━━━`;
}

// =======================
async function getUSSymbols() {
  try {
    const res = await fetch(`https://finnhub.io/api/v1/stock/symbol?exchange=US&token=${API_KEY}`);
    return await res.json();
  } catch { return []; }
}

// =======================
bot.on("message", (msg) => {
  chatIds.add(msg.chat.id);

  if (msg.text === "/start") {
    bot.sendMessage(msg.chat.id, "💀 RUNNING 24/7");
  }

  if (msg.text === "/scan") {
    bot.sendMessage(msg.chat.id, "🚀 جاري الفحص...");
    run();
  }
});

// =======================
// 💀🔥 تشغيل ذكي + تحديث تلقائي للأهداف
async function run() {
  if (running) return;
  running = true;

  try {
    let us = await getUSSymbols();

    let batchSize = 20;

    for (let i = 0; i < us.length; i += batchSize) {

      let batch = us.slice(i, i + batchSize);

      for (let s of batch) {
        let q = await getQuote(s.symbol);
        if (!q) continue;

        let a = analyze(q.price, q.prev);
        if (!a) continue;

        // 🔥 فلترة خفيفة فقط
        if (a.change < 0.3) continue;

        let data = {
          name: s.symbol,
          market: "🇺🇸 السوق الأمريكي",
          price: q.price,
          ...a
        };

        // ✅ حفظ الإشارة لتحديثها لاحقًا
        sentSignals[s.symbol] = data;

        let text = format(data);

        for (let id of chatIds) {
          await bot.sendMessage(id, text);
          await new Promise(r => setTimeout(r, 200));
        }
      }

      await new Promise(r => setTimeout(r, 2000));
    }

  } catch (e) {
    console.log("ERROR:", e);
  }

  running = false;
}

// =======================
// 💀 تحديث الأهداف تلقائي
setInterval(async () => {
  for (let symbol in sentSignals) {
    let q = await getQuote(symbol);
    if (!q) continue;

    let s = sentSignals[symbol];
    s.price = q.price;

    let text = format(s);

    for (let id of chatIds) {
      await bot.sendMessage(id, text);
      await new Promise(r => setTimeout(r, 200));
    }
  }
}, 15000);

// =======================
setInterval(() => {
  run();
}, 20000);

app.listen(3000, () => {
  console.log("💀 BOT RUNNING STABLE");
});
