import express from "express";
import TelegramBot from "node-telegram-bot-api";

const app = express();
app.use(express.json());

// 🔑 TOKEN
const TOKEN = "8652994768:AAHwa1uXSRpqJmpL2X_yfYLjXIu437T-Dw4";

     
/اتصال قوي ثابت
const bot = new TelegramBot(TOKEN, {
  polling: {
    interval: 300,
    autoStart: true,
    params: { timeout: 10 }
  }
});

// 🔑 API
const API_KEY = "d75o0l1r01qk56kdfon0d75o0l1r01qk56kdfong";

let chatId = null;
let memory = {};
let running = false;

// 💀 حماية من الكراش
process.on("uncaughtException", (err) => {
  console.log("💀 CRASH:", err.message);
});

process.on("unhandledRejection", (err) => {
  console.log("💀 PROMISE ERROR:", err);
});

// =======================
bot.on("message", (msg) => {
  chatId = msg.chat.id;

  if (msg.text === "/start") {
    bot.sendMessage(chatId, "💀 AI PRO MAX ELITE MODE (ULTIMATE)");
    run();
  }

  if (msg.text === "/scan") {
    bot.sendMessage(chatId, "🚀 فحص السوق...");
    run();
  }
});

// =======================
function analyze(price, prev, symbol) {
  if (!price || !prev || prev === 0 || price <= 0) return null;

  let change = ((price - prev) / prev) * 100;

  let signal = "⚪ محايد";
  let emoji = "";
  let smart = "";
  let type = "🐠 مضاربين";
  let entry = "⏳ انتظر";
  let decision = "❌ ممنوع الدخول"; // 💀 الجديد

  if (!memory[symbol]) {
    memory[symbol] = {
      price: price,
      low: price,
      high: price,
      lastBreak: false
    };
  }

  let prevData = memory[symbol];

  if (price < prevData.low) {
    prevData.low = price;
  }

  if (price > prevData.high) {
    prevData.high = price;
  }

  let fromLow = ((price - prevData.low) / prevData.low) * 100;

  let breakHigh = price > prevData.high * 0.995;

  let flow = price > prevData.price ? "💹 سيولة مستمرة" : "⚠️ ضعف السيولة";

  if (change > 3) {
    signal = "💰 دخول مؤسسات فعلي";
    emoji = "⚡️";
    smart = "🔥 Smart Money";
    type = "🦈 هوامير";
  } 
  else if (change > 1.5) {
    signal = "🧠 تجميع صامت";
    smart = "📈 Accumulation";
  } 
  else if (change < -3) {
    signal = "🚨 تصريف ذكي";
    emoji = "⚡️";
    smart = "📉 Distribution";
    type = "🦈 هوامير";
  }

  if (fromLow > 2 && fromLow < 6 && change > 0.5) {
    entry = "💀 دخول من القاع";
  }

  if (fromLow >= 6 && change > 2 && flow.includes("💹")) {
    entry = "🚀 انطلاق موجة قوية";
  }

  if (fromLow > 3 && breakHigh && flow.includes("💹") && change > 2) {
    entry = "💀🔥 دخول احترافي مؤكد";
  }

  // =======================
  // 💀 القرار الذكي التلقائي
  // =======================

  // 💀 دخول كامل
  if (
    type === "🦈 هوامير" &&
    flow.includes("💹") &&
    change > 2 &&
    fromLow > 2
  ) {
    decision = "💀 ادخل الآن بكامل السيولة";
  }

  // ⚠️ دخول جزئي
  else if (
    flow.includes("💹") &&
    change > 1 &&
    fromLow > 1
  ) {
    decision = "⚠️ دخول جزئي";
  }

  // ❌ ممنوع
  else {
    decision = "❌ ممنوع الدخول";
  }

  function fix(n) {
    return Number(n).toFixed(price < 1 ? 6 : 2);
  }

  let tpRaw = [
    price * 1.02,
    price * 1.04,
    price * 1.06,
    price * 1.08,
    price * 1.10,
    price * 1.12,
    price * 1.15,
    price * 1.18,
  ];

  let tp = tpRaw.map(v => fix(v));
  let tpStatus = tpRaw.map(v => price >= v);
  let sl = fix(price * 0.95);

  memory[symbol] = {
    price,
    low: prevData.low,
    high: prevData.high
  };

  return {
    signal, tp, sl, emoji, change, smart,
    type, entry, flow, tpStatus, fromLow,
    decision // 💀 الجديد
  };
}

// =======================
function format(s) {
  return `
${s.market}
${s.type}

${s.emoji} ${s.name}

💰 ${Number(s.price).toFixed(s.price < 1 ? 6 : 2)}
📉 من القاع: ${s.fromLow.toFixed(2)}%

📊 ${s.signal} (${s.change.toFixed(2)}%)
${s.smart ? "🧠 " + s.smart : ""}

🎯 TP1: ${s.tp[0]} ${s.tpStatus[0] ? "✅" : ""}
🎯 TP2: ${s.tp[1]} ${s.tpStatus[1] ? "✅" : ""}
🎯 TP3: ${s.tp[2]} ${s.tpStatus[2] ? "✅" : ""}
🎯 TP4: ${s.tp[3]} ${s.tpStatus[3] ? "✅" : ""}
🎯 TP5: ${s.tp[4]} ${s.tpStatus[4] ? "✅" : ""}
🎯 TP6: ${s.tp[5]} ${s.tpStatus[5] ? "✅" : ""}
🎯 TP7: ${s.tp[6]} ${s.tpStatus[6] ? "✅" : ""}
🎯 TP8: ${s.tp[7]} ${s.tpStatus[7] ? "✅" : ""}

🛑 SL: ${s.sl}

${s.entry}
${s.flow}

${s.decision} 💀

━━━━━━━━━━━━`;
}

// =======================
// باقي الكود نفسه بدون أي تغيير
